"""
reflection_pack · 反思层证据包组装
Z7c · 2026-10-10 · 铸码实装
依据: cognition/README.md §8.8 + specs/architecture-master.md "数据基础（梁总指示）"

诚实纪律: 任何一段取不到数据 → gaps[] 记录, 绝不用推算/平滑/上一期值填充.
"""
import json
import re
import time
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger("data-api.reflection_pack")

TZ_CST = timezone(timedelta(hours=8))

# ─── DEFAULT_ROUTE_MAP ────────────────────────────────────────────────
# 口径注: dragon_tiger 库里实名 dt_pool, 已用 alias 兼容

DEFAULT_ROUTE_MAP = {
    "route_map_version": "2026-10-10.1",
    "metric_routes": [
        {"match": "index.pct", "table": "index_daily", "column": "pct", "dim": "code"},
        {"match": "stock_daily.pct", "table": "stock_daily", "column": "pct", "dim": "code"},
        {"match": "sentiment_score", "table": "sentiment_daily", "column": "sentiment_score", "dim": None},
        {"match": "limit_up", "table": "sentiment_daily", "column": "limit_up", "dim": None},
        {"match": "sector.pct", "table": "sector_daily", "column": "pct", "dim": "sector_name"},
        {"match": "sector.main_net_inflow", "table": "sector_daily", "column": "main_net_inflow", "dim": "sector_name"},
        {"match": "fund_flow_sector.main_net_inflow", "table": "fund_flow_sector", "column": "main_net_inflow", "dim": "sector_name"},
        {"match": "global.pct", "table": "global_daily", "column": "pct", "dim": "code"},
        {"match": "northbound.total_net", "table": "northbound_daily", "column": "total_net", "dim": None},
        {"match": "margin.margin_bal", "table": "margin_daily", "column": "margin_bal", "dim": None},
        {"match": "fund_flow_stock.main_net_inflow", "table": "fund_flow_stock", "column": "main_net_inflow", "dim": "code"},
        {"match": "dragon_tiger", "table": "dt_pool", "column": "amount", "dim": "code",
         "alias": ["龙虎", "龙头", "dt_pool"]},
    ],
    "category_default": {
        "continuation": "sector.pct",
        "phase_change": "sentiment_score",
        "spillover": "sector.main_net_inflow",
        "reversal": "index.pct",
        "情绪": "sentiment_score",
        "产业": "sector.pct",
    },
}

# ─── Route map cache ──────────────────────────────────────────────────

_route_map_cache = {"value": None, "ts": 0.0, "version": "builtin"}
CACHE_TTL = 60  # seconds


def _get_route_map_from_db(get_conn_fn) -> dict:
    """从 job_registry.config->'route_map' 读取, 空则返回 DEFAULT."""
    conn = get_conn_fn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config FROM job_registry WHERE job_name = 'j_reflect_daily'"
            )
            row = cur.fetchone()
            if row and row[0] and "route_map" in (row[0] or {}):
                return row[0]["route_map"]
    finally:
        conn.close()
    return dict(DEFAULT_ROUTE_MAP)


def get_route_map(get_conn_fn) -> dict:
    """带 60s TTL 缓存的 route_map 读取."""
    now = time.time()
    if _route_map_cache["value"] is not None and (now - _route_map_cache["ts"]) < CACHE_TTL:
        return _route_map_cache["value"]
    rm = _get_route_map_from_db(get_conn_fn)
    ver = rm.get("route_map_version", "builtin")
    _route_map_cache["value"] = rm
    _route_map_cache["ts"] = now
    _route_map_cache["version"] = ver
    return rm


def invalidate_route_map_cache():
    _route_map_cache["value"] = None
    _route_map_cache["ts"] = 0.0


# ─── Helpers ──────────────────────────────────────────────────────────

def _trade_days_near(cur, ref_date: date, n_before: int = 10, n_after: int = 5) -> list:
    """获取 ref_date 前后 N 个交易日列表 (SSE)."""
    cur.execute("""
        SELECT cal_date FROM trade_cal
        WHERE market = 'SSE' AND is_open = 1
          AND cal_date BETWEEN %s AND %s
        ORDER BY cal_date
    """, (ref_date - timedelta(days=n_before * 2), ref_date + timedelta(days=n_after * 2)))
    rows = cur.fetchall()
    # Handle both dict and tuple cursors
    if rows and isinstance(rows[0], dict):
        return [r["cal_date"] for r in rows]
    return [r[0] for r in rows]


def _nearest_trade_day(trade_days: list, target: date) -> date:
    """回退到最近交易日."""
    if not trade_days:
        return target
    for d in reversed(trade_days):
        if d <= target:
            return d
    return trade_days[0]


def _nearest_trade_day_before(trade_days: list, target: date) -> date:
    """B5 修复: 获取 target 之前（不含 target 当天）的最近交易日。
    用于隔夜数据查询（如周一应取上周五）。
    """
    if not trade_days:
        return target - timedelta(days=1)
    for d in reversed(trade_days):
        if d < target:
            return d
    # 如果 trade_days 全 >= target，返回 target 前一天
    return target - timedelta(days=1)


# B5 安全白名单: metric 必须匹配 ^table.column$ 格式（纯字母数字+下划线）
_METRIC_PATTERN = re.compile(r'^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$')
_IDENT_PATTERN = re.compile(r'^[a-z_][a-z0-9_]*$')


def _validate_metric_or_reject(metric_raw: str, gaps: list, section: str) -> Optional[str]:
    """B5 P0-安全: 校验 metric 是否为合法 table.column 格式。
    不匹配 → 返回 FALSIFY_METRIC_INVALID gap, 绝不拼 SQL。
    """
    if not metric_raw or not isinstance(metric_raw, str):
        return metric_raw  # 空值走 category_default 兜底
    if _METRIC_PATTERN.match(metric_raw):
        return metric_raw
    # 不匹配白名单
    gaps.append({
        "section": section,
        "code": "FALSIFY_METRIC_INVALID",
        "reason": f"metric '{metric_raw}' 不匹配白名单 ^table.column$（可能为非标准 schema）",
        "affected": f"{section}.falsify",
    })
    return None


def _resolve_metric_route(metric: str, category: str, route_map: dict, gaps: list, section: str) -> Optional[dict]:
    """解析 metric 到 {table, column, dim}. 匹配不到走 category_default 兜底.
    B5 安全加固: table/column 必须通过 _IDENT_PATTERN 校验。
    """
    if not metric:
        # 空 metric → category_default
        cat_def = route_map.get("category_default", {})
        fallback = cat_def.get(category)
        if not fallback:
            gaps.append({"section": section, "code": "FALSIFY_METRIC_MISSING",
                         "reason": f"metric empty and no category_default for category='{category}'",
                         "affected": "S2"})
            return None
        metric = fallback

    # B5: 校验 metric 格式
    if not _METRIC_PATTERN.match(metric):
        # 可能是非标准 metric（如 JSON 字符串），拒绝拼 SQL
        gaps.append({"section": section, "code": "FALSIFY_METRIC_INVALID",
                      "reason": f"metric '{metric}' 不匹配白名单 ^table.column$",
                      "affected": "S2"})
        return None

    # 形如 "table.column" 直接拆
    if "." in metric:
        parts = metric.split(".", 1)
        table_guess, col_guess = parts[0], parts[1]
        # B5: 校验 table 和 column 标识符
        if not _IDENT_PATTERN.match(table_guess) or not _IDENT_PATTERN.match(col_guess):
            gaps.append({"section": section, "code": "FALSIFY_METRIC_INVALID",
                          "reason": f"table/column 含非法字符: {table_guess}.{col_guess}",
                          "affected": "S2"})
            return None
        # 先查 metric_routes 精确匹配
        for mr in route_map.get("metric_routes", []):
            if mr["match"] == metric:
                return {"table": mr["table"], "column": mr["column"], "dim": mr.get("dim")}
        # 尝试 table.column 直解
        return {"table": table_guess, "column": col_guess, "dim": "code"}

    # 查 metric_routes
    for mr in route_map.get("metric_routes", []):
        if mr["match"] == metric:
            return {"table": mr["table"], "column": mr["column"], "dim": mr.get("dim")}
        # 检查 alias
        for alias in mr.get("alias", []):
            if alias == metric or alias in metric:
                return {"table": mr["table"], "column": mr["column"], "dim": mr.get("dim")}

    # 兜底 category_default
    cat_def = route_map.get("category_default", {})
    fallback = cat_def.get(category)
    if fallback:
        gaps.append({"section": section, "code": "FALSIFY_METRIC_MISSING",
                      "reason": f"metric '{metric}' not in route_map, fell back to category_default '{fallback}'",
                      "affected": "S2"})
        return _resolve_metric_route(fallback, category, route_map, gaps, section)

    gaps.append({"section": section, "code": "FALSIFY_METRIC_MISSING",
                  "reason": f"metric '{metric}' not in route_map and no category_default for '{category}'",
                  "affected": "S2"})
    return None


def _jsonb_to_python(val) -> Any:
    """Handle JSONB values from psycopg2."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


# ─── S1: 决策时点四维快照 ─────────────────────────────────────────────

def _build_s1(cur, decision_date: date, trade_days: list, reasoning_trace: Any, gaps: list) -> dict:
    """S1 决策时点快照."""
    result = {}
    nearest = _nearest_trade_day(trade_days, decision_date)
    # 决策日及前5交易日
    idx_before = trade_days.index(nearest) if nearest in trade_days else -1
    if idx_before < 0:
        # 找不到, 用日期范围兜底
        window_start = decision_date - timedelta(days=10)
        window_end = decision_date
    else:
        start_idx = max(0, idx_before - 5)
        window_start = trade_days[start_idx]
        window_end = nearest

    # ① index_daily
    try:
        cur.execute("""
            SELECT date, code, name, open, high, low, close, pct, amount
            FROM index_daily
            WHERE date BETWEEN %s AND %s
              AND code IN ('sh000001','sz399001','sz399006','sh000016','sh000300','sh000688')
            ORDER BY date, code
        """, (window_start, window_end))
        result["index_daily"] = [dict(r) for r in cur.fetchall()]
        if not result["index_daily"]:
            gaps.append({"section": "S1", "code": "INDEX_DAILY_EMPTY",
                          "reason": f"No index_daily rows for {window_start}~{window_end}", "affected": "S1.index"})
    except Exception as e:
        gaps.append({"section": "S1", "code": "INDEX_DAILY_ERROR", "reason": str(e), "affected": "S1.index"})
        result["index_daily"] = []

    # ② sentiment_daily 决策日及前2日
    sent_start = nearest - timedelta(days=5)
    try:
        cur.execute("""
            SELECT date, limit_up, limit_down, seal_rate, broken_rate, max_board,
                   promote_rate, up_cnt, down_cnt, sentiment_score
            FROM sentiment_daily
            WHERE date BETWEEN %s AND %s
            ORDER BY date
        """, (sent_start, nearest))
        result["sentiment_daily"] = [dict(r) for r in cur.fetchall()]
        if not result["sentiment_daily"]:
            gaps.append({"section": "S1", "code": "SENTIMENT_DAILY_EMPTY",
                          "reason": f"No sentiment_daily for {sent_start}~{nearest}", "affected": "S1.sentiment"})
    except Exception as e:
        gaps.append({"section": "S1", "code": "SENTIMENT_ERROR", "reason": str(e), "affected": "S1.sentiment"})
        result["sentiment_daily"] = []

    # ③ sector 集中度
    try:
        cur.execute("""
            SELECT sector_name, pct, main_net_inflow, turnover
            FROM sector_daily
            WHERE date = %s AND kind = '行业'
            ORDER BY main_net_inflow DESC NULLS LAST
            LIMIT 10
        """, (nearest,))
        top_inflow = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT sector_name, pct, main_net_inflow, turnover
            FROM sector_daily
            WHERE date = %s AND kind = '行业'
            ORDER BY pct DESC NULLS LAST
            LIMIT 10
        """, (nearest,))
        top_pct = [dict(r) for r in cur.fetchall()]

        # top5 成交额占比 + HHI
        cur.execute("""
            SELECT turnover FROM sector_daily
            WHERE date = %s AND kind = '行业' AND turnover IS NOT NULL
            ORDER BY turnover DESC
        """, (nearest,))
        rows = cur.fetchall()
        turnovers = [r["turnover"] if isinstance(r, dict) else r[0] for r in rows]
        total_to = sum(turnovers) if turnovers else 0
        top5_to = sum(turnovers[:5])
        top5_pct = (top5_to / total_to * 100) if total_to > 0 else None
        hhi = None
        if total_to > 0:
            hhi = sum((t / total_to * 100) ** 2 for t in turnovers[:10])

        result["sector_concentration"] = {
            "date": nearest,
            "top10_by_inflow": top_inflow,
            "top10_by_pct": top_pct,
            "top5_turnover_share_pct": round(top5_pct, 2) if top5_pct is not None else None,
            "hhi_top10": round(hhi, 2) if hhi is not None else None,
        }
        if not top_inflow:
            gaps.append({"section": "S1", "code": "SECTOR_DAILY_EMPTY",
                          "reason": f"No sector_daily for date={nearest} kind='行业'", "affected": "S1.sector"})
    except Exception as e:
        gaps.append({"section": "S1", "code": "SECTOR_ERROR", "reason": str(e), "affected": "S1.sector"})
        result["sector_concentration"] = {}

    # ④ 量能 (B5 修复: 区分 VOLUME_EMPTY vs VOLUME_QUERY_ERROR)
    try:
        cur.execute("""
            SELECT amount FROM index_daily
            WHERE code = 'sh000001' AND date = %s
        """, (nearest,))
        row = cur.fetchone()
        today_amount = row[0] if row else None

        cur.execute("""
            SELECT AVG(amount) FROM index_daily
            WHERE code = 'sh000001' AND date BETWEEN %s AND %s
        """, (window_start, nearest))
        avg_amount = cur.fetchone()[0]

        # 全市场量能
        cur.execute("""
            SELECT SUM(amount) FROM stock_daily WHERE date = %s
        """, (nearest,))
        mkt_today = cur.fetchone()[0]

        cur.execute("""
            SELECT SUM(amount) FROM stock_daily
            WHERE date BETWEEN %s AND %s
        """, (window_start, nearest))
        mkt_total = cur.fetchone()[0]

        # B5: 安全计算 5d avg（避免 idx_before < 0 时 KeyError）
        if idx_before >= 0:
            window_days_count = max(len(trade_days[max(start_idx, 0):idx_before + 1]), 1)
        else:
            window_days_count = 5  # 兜底
        result["volume"] = {
            "index_amount_today": today_amount,
            "index_amount_5d_avg": float(avg_amount) if avg_amount else None,
            "market_amount_today": float(mkt_today) if mkt_today else None,
            "market_amount_5d_avg": float(mkt_total / window_days_count) if mkt_total else None,
        }
        # B5: 查得到但窗口内无行 → VOLUME_EMPTY
        if not mkt_today and not today_amount:
            gaps.append({"section": "S1", "code": "VOLUME_EMPTY",
                          "reason": f"stock_daily/index_daily 窗口 {window_start}~{nearest} 内无数据",
                          "affected": "S1.volume"})
    except Exception as e:
        # B5: SQL/连接异常 → VOLUME_QUERY_ERROR，附异常原文
        gaps.append({"section": "S1", "code": "VOLUME_QUERY_ERROR",
                      "reason": f"窗口 {window_start}~{nearest} 查询异常: {type(e).__name__}: {e}",
                      "affected": "S1.volume"})
        result["volume"] = {}

    # ⑤ 隔夜 global_daily (B5 修复: 按 trade_cal 取决策日前最近交易日，非自然日)
    # 避免周一/节假日后误报（如 2026-08-30 周日无交易数据）
    prev_trade_day = _nearest_trade_day_before(trade_days, decision_date)
    try:
        cur.execute("""
            SELECT market, code, name, close, pct
            FROM global_daily
            WHERE date = %s
            ORDER BY market, code
        """, (prev_trade_day,))
        result["global_overnight"] = [dict(r) for r in cur.fetchall()]
        if not result["global_overnight"]:
            gaps.append({"section": "S1", "code": "GLOBAL_OVERNIGHT_EMPTY",
                          "reason": f"No global_daily for trade_date={prev_trade_day} (decision_date={decision_date})",
                          "affected": "S1.global"})
    except Exception as e:
        gaps.append({"section": "S1", "code": "GLOBAL_ERROR", "reason": str(e), "affected": "S1.global"})
        result["global_overnight"] = []

    # ⑥ 引用认知
    result["cognition_refs"] = []
    rt = _jsonb_to_python(reasoning_trace)
    if rt and isinstance(rt, (dict, list)):
        # 提取 F-xxx / cognition_id
        ids = set()
        rt_str = json.dumps(rt) if not isinstance(rt, str) else rt
        for m in re.finditer(r'(F-\d+|cognition[_-]?id["\s:]+([A-Za-z0-9_-]+))', rt_str):
            cid = m.group(2) or m.group(1)
            ids.add(cid)
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            try:
                cur.execute(f"""
                    SELECT cognition_id, version, title, status, validations, falsifications, derives_from, created_at
                    FROM cognition
                    WHERE cognition_id IN ({placeholders})
                      AND created_at <= %s
                    ORDER BY cognition_id, version DESC
                """, list(ids) + [datetime.combine(decision_date, datetime.max.time()).replace(tzinfo=TZ_CST)])
                result["cognition_refs"] = [dict(r) for r in cur.fetchall()]
            except Exception as e:
                gaps.append({"section": "S1", "code": "COGNITION_REF_ERROR", "reason": str(e), "affected": "S1.cognition"})

    return result


# ─── S2: falsify 指标实际序列 ─────────────────────────────────────────

def _build_s2(cur, prediction: dict, window_start: date, window_end: date,
              route_map: dict, gaps: list) -> dict:
    """S2 falsify 指标实际序列."""
    falsify = _jsonb_to_python(prediction.get("falsify"))
    if not falsify or not isinstance(falsify, dict):
        gaps.append({"section": "S2", "code": "FALSIFY_EMPTY",
                      "reason": "prediction.falsify is null or not a dict", "affected": "S2"})
        return {}

    metric_raw = falsify.get("metric", "")
    category = prediction.get("category", "")
    direction = falsify.get("direction", "")
    threshold = falsify.get("threshold")

    # B5 P0-安全: 先校验 metric 格式，不合法直接拒绝
    validated_metric = _validate_metric_or_reject(metric_raw, gaps, "S2")
    if validated_metric is None and metric_raw:
        # 校验失败，已记录 FALSIFY_METRIC_INVALID gap
        return {"metric": metric_raw, "route": None, "threshold_check": None}

    route = _resolve_metric_route(validated_metric or metric_raw, category, route_map, gaps, "S2")
    if not route:
        return {"metric": metric_raw, "route": None, "threshold_check": None}

    table = route["table"]
    column = route["column"]
    dim = route.get("dim")

    # B5: 二次校验 routed table/column（防止 route_map 本身被注入）
    if not _IDENT_PATTERN.match(table) or not _IDENT_PATTERN.match(column):
        gaps.append({"section": "S2", "code": "FALSIFY_METRIC_INVALID",
                      "reason": f"routed table/column 含非法字符: {table}.{column}",
                      "affected": "S2"})
        return {"metric": metric_raw, "route": None, "threshold_check": None}

    # 构建查询
    where_clauses = ["date BETWEEN %s AND %s"]
    params: list = [window_start, window_end]

    # 如果 falsify 带 code/target/sector_name 等, 加 WHERE
    # 注意: 不同表用不同维度列, 只加与 dim 匹配的条件
    for key in ["code", "target", "target_topic", "sector_name"]:
        val = falsify.get(key)
        if val and dim:
            if key in ("target_topic", "target"):
                # 模糊匹配: 用 dim 列 (sector_name 或 name 取决于表)
                if dim == "sector_name":
                    where_clauses.append(f"sector_name ILIKE %s")
                    params.append(f"%{val}%")
                elif dim == "code":
                    # 对于 code dim, target_topic 无法直接匹配, 跳过
                    pass
                else:
                    where_clauses.append(f"{dim} ILIKE %s")
                    params.append(f"%{val}%")
            elif key == "sector_name" and dim == "sector_name":
                where_clauses.append(f"{dim} = %s")
                params.append(val)
            elif key == "code" and dim == "code":
                where_clauses.append(f"{dim} = %s")
                params.append(val)

    where_sql = " AND ".join(where_clauses)
    try:
        cur.execute(f"""
            SELECT date, {column} as value
            FROM {table}
            WHERE {where_sql}
            ORDER BY date
        """, params)
        series = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        gaps.append({"section": "S2", "code": "S2_QUERY_ERROR",
                      "reason": f"Table/column error: {e}", "affected": f"S2.{table}.{column}"})
        series = []

    # 计算 threshold_check
    values = [r["value"] for r in series if r.get("value") is not None]
    tc = None
    if values:
        actual_first = values[0]
        actual_last = values[-1]
        actual_max = max(values)
        actual_min = min(values)
        hit = False
        if direction == "above" and threshold is not None:
            hit = any(v > threshold for v in values)
        elif direction == "below" and threshold is not None:
            hit = any(v < threshold for v in values)
        tc = {
            "direction": direction,
            "threshold": threshold,
            "actual_first": actual_first,
            "actual_last": actual_last,
            "actual_max": actual_max,
            "actual_min": actual_min,
            "hit": hit,
        }

    return {
        "metric": metric_raw,
        "routed_table": table,
        "routed_column": column,
        "series": series,
        "threshold_check": tc,
    }


# ─── S3: 归因证据 ────────────────────────────────────────────────────

def _build_s3(cur, prediction: dict, decision_date: date, window_start: date,
              window_end: date, reasoning_trace: Any, gaps: list) -> dict:
    """S3 归因证据."""
    result = {}

    # ① regime_daily 窗口内日序列
    try:
        cur.execute("""
            SELECT date, regime, sub_regime, quadrant, evidence, actor, source
            FROM regime_daily
            WHERE date BETWEEN %s AND %s
            ORDER BY date
        """, (window_start, window_end))
        result["regime_daily"] = [dict(r) for r in cur.fetchall()]
        if not result["regime_daily"]:
            gaps.append({"section": "S3", "code": "REGIME_DAILY_EMPTY",
                          "reason": f"No regime_daily for {window_start}~{window_end}", "affected": "S3.regime"})
    except Exception as e:
        gaps.append({"section": "S3", "code": "REGIME_DAILY_ERROR", "reason": str(e), "affected": "S3.regime"})
        result["regime_daily"] = []

    # ② ingest_log 决策日全部行
    try:
        cur.execute("""
            SELECT ts, run_id, job, trigger, domain, target_table, source_used,
                   status, rows_in, rows_written, rows_quarantined, note
            FROM ingest_log
            WHERE ts::date = %s
            ORDER BY ts
        """, (decision_date,))
        result["ingest_log"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        gaps.append({"section": "S3", "code": "INGEST_LOG_ERROR", "reason": str(e), "affected": "S3.ingest"})
        result["ingest_log"] = []

    # ③ quarantine 决策日 + 窗口内 severity 非空
    try:
        cur.execute("""
            SELECT ts, q_id, job, target_table, row_key, failed_rules, severity, status
            FROM quarantine
            WHERE ts::date = %s
               OR (ts::date BETWEEN %s AND %s AND severity IS NOT NULL)
            ORDER BY ts
        """, (decision_date, window_start, window_end))
        result["quarantine"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        gaps.append({"section": "S3", "code": "QUARANTINE_ERROR", "reason": str(e), "affected": "S3.quarantine"})
        result["quarantine"] = []

    # ④ verify_diff 决策日 + 窗口内
    try:
        cur.execute("""
            SELECT date, target_table, total_rows, checked_rows, warn_count, block_count, max_diff_pct
            FROM verify_diff
            WHERE date = %s OR date BETWEEN %s AND %s
            ORDER BY date
        """, (decision_date, window_start, window_end))
        result["verify_diff"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        gaps.append({"section": "S3", "code": "VERIFY_DIFF_ERROR", "reason": str(e), "affected": "S3.verify"})
        result["verify_diff"] = []

    # ⑤ falsify 定义原文 (全量 JSONB, 不裁剪)
    result["falsify_definition"] = _jsonb_to_python(prediction.get("falsify"))

    # ⑥ 认知版本史
    result["cognition_history"] = []
    rt = _jsonb_to_python(reasoning_trace)
    if rt:
        ids = set()
        rt_str = json.dumps(rt) if not isinstance(rt, str) else rt
        for m in re.finditer(r'(F-\d+|cognition[_-]?id["\s:]+([A-Za-z0-9_-]+))', rt_str):
            cid = m.group(2) or m.group(1)
            ids.add(cid)
        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            try:
                cur.execute(f"""
                    SELECT cognition_id, version, title, statement, status,
                           validations, falsifications, derives_from, created_at
                    FROM cognition
                    WHERE cognition_id IN ({placeholders})
                    ORDER BY cognition_id, version
                """, list(ids))
                result["cognition_history"] = [dict(r) for r in cur.fetchall()]
            except Exception as e:
                gaps.append({"section": "S3", "code": "COGNITION_HIST_ERROR",
                              "reason": str(e), "affected": "S3.cognition"})

    # ⑦ 当日振幅
    try:
        cur.execute("""
            SELECT code, (high - low) / NULLIF(close, 0) as amplitude
            FROM index_daily
            WHERE date = %s AND code IN ('sh000001','sz399001','sz399006')
        """, (decision_date,))
        rows = cur.fetchall()
        idx_amp = {}
        for r in rows:
            if isinstance(r, dict):
                idx_amp[r["code"]] = float(r["amplitude"]) if r.get("amplitude") else None
            else:
                idx_amp[r[0]] = float(r[1]) if r[1] else None

        cur.execute("""
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (high-low)/NULLIF(close,0))
            FROM stock_daily WHERE date = %s
        """, (decision_date,))
        row = cur.fetchone()
        mkt_median_amp = row[0] if not isinstance(row, dict) else list(row.values())[0]

        result["amplitude"] = {
            "index_amplitude": idx_amp,
            "market_median_amplitude": float(mkt_median_amp) if mkt_median_amp else None,
        }
    except Exception as e:
        gaps.append({"section": "S3", "code": "AMPLITUDE_ERROR", "reason": str(e), "affected": "S3.amplitude"})
        result["amplitude"] = {}

    # ⑧ news_telegraph level='S'
    try:
        cur.execute("""
            SELECT pub_ts, news_id, media, title, level, related_codes
            FROM news_telegraph
            WHERE level = 'S'
              AND pub_ts::date BETWEEN %s AND %s
            ORDER BY pub_ts
        """, (decision_date, window_end))
        result["news_critical"] = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        gaps.append({"section": "S3", "code": "NEWS_ERROR", "reason": str(e), "affected": "S3.news"})
        result["news_critical"] = []

    return result


# ─── S4: base_rate 同 regime 同类对照 ─────────────────────────────────

def _build_s4(cur, prediction: dict, gaps: list) -> list:
    """S4 base_rate 同 regime 同类对照."""
    regime = prediction.get("regime_at_create")
    category = prediction.get("category")
    horizon = prediction.get("horizon")

    if not regime:
        gaps.append({"section": "S4", "code": "REGIME_MISSING",
                      "reason": "prediction.regime_at_create is null, degraded to same category+horizon all regimes",
                      "affected": "S4"})

    try:
        sql = "SELECT * FROM base_rate WHERE 1=1"
        params = []
        if regime:
            sql += " AND regime = %s"
            params.append(regime)
        if category:
            sql += " AND category = %s"
            params.append(category)
        if horizon:
            sql += " AND horizon = %s"
            params.append(horizon)
        sql += " ORDER BY window_end DESC LIMIT 50"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            gaps.append({"section": "S4", "code": "BASE_RATE_EMPTY",
                          "reason": f"No base_rate for regime={regime} category={category} horizon={horizon}",
                          "affected": "S4"})
        return rows
    except Exception as e:
        gaps.append({"section": "S4", "code": "BASE_RATE_ERROR", "reason": str(e), "affected": "S4"})
        return []


# ─── Main assembly ────────────────────────────────────────────────────

def assemble_reflection_pack(get_conn_fn, decision_id: str,
                             window_start_override: Optional[str] = None,
                             window_end_override: Optional[str] = None,
                             sections_override: Optional[str] = None) -> dict:
    """
    组装反思证据包. 返回 pack dict.
    任何数据缺失 → gaps[] 记录, 不做伪填充.
    """
    gaps = []
    conn = get_conn_fn()
    conn.autocommit = True  # 避免单条查询失败导致整个事务 abort
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 查 prediction
            cur.execute("SELECT * FROM prediction WHERE prediction_id = %s", (decision_id,))
            pred_row = cur.fetchone()
            if not pred_row:
                return {"error": "PACK_DECISION_NOT_FOUND", "decision_id": decision_id}
            prediction = dict(pred_row)

            # 2. 计算窗口
            created_at = prediction.get("created_at")
            if isinstance(created_at, datetime):
                decision_date = created_at.date()
            elif isinstance(created_at, date):
                decision_date = created_at
            else:
                decision_date = date.today()

            check_date = prediction.get("check_date")
            if isinstance(check_date, datetime):
                check_date = check_date.date()

            trade_days = _trade_days_near(cur, decision_date)
            decision_td = _nearest_trade_day(trade_days, decision_date)

            # 默认窗口: 决策日 ~ check_date（B5 修复: 含 start==end 当日情形）
            if window_start_override:
                ws = datetime.strptime(window_start_override, "%Y-%m-%d").date()
            else:
                ws = decision_td  # B5: 从决策日当天开始（不再 +1 天导致倒挂）
            if window_end_override:
                we = datetime.strptime(window_end_override, "%Y-%m-%d").date()
            else:
                we = check_date if check_date else decision_td + timedelta(days=3)

            # B5: 防倒挂保护
            if ws > we:
                ws, we = we, ws
                gaps.append({"section": "S3", "code": "WINDOW_INVERTED_CORRECTED",
                              "reason": f"窗口起止倒挂 {ws}~{we}，已自动修正",
                              "affected": "S3"})

            # 3. route_map
            route_map = get_route_map(get_conn_fn)
            rm_version = route_map.get("route_map_version", "builtin")

            # 4. sections
            all_sections = {"s1", "s2", "s3", "s4"}
            if sections_override:
                requested = set(s.strip().lower() for s in sections_override.split(","))
                sections_to_build = requested & all_sections
            else:
                sections_to_build = all_sections

            sections = {}
            if "s1" in sections_to_build:
                sections["S1_snapshot_at_decision"] = _build_s1(
                    cur, decision_date, trade_days,
                    prediction.get("reasoning_trace"), gaps
                )
            if "s2" in sections_to_build:
                sections["S2_falsify_actuals"] = _build_s2(
                    cur, prediction, ws, we, route_map, gaps
                )
            if "s3" in sections_to_build:
                sections["S3_attribution"] = _build_s3(
                    cur, prediction, decision_date, ws, we,
                    prediction.get("reasoning_trace"), gaps
                )
            if "s4" in sections_to_build:
                sections["S4_base_rate_peer"] = _build_s4(cur, prediction, gaps)

            # 5. 序列化 prediction (处理 datetime/date)
            pred_out = {}
            for k, v in prediction.items():
                if isinstance(v, (datetime, date)):
                    pred_out[k] = v.isoformat()
                else:
                    pred_out[k] = _jsonb_to_python(v)

            return {
                "decision_id": decision_id,
                "decision": pred_out,
                "window": {
                    "decision_date": decision_date.isoformat(),
                    "check_date": check_date.isoformat() if check_date else None,
                    "trade_days": [d.isoformat() for d in trade_days],
                },
                "sections": sections,
                "gaps": gaps,
                "route_map_version": rm_version,
                "generated_at": datetime.now(TZ_CST).isoformat(),
            }
    finally:
        conn.close()
