"""
data_api/lovetrade_routes.py
Z8 W2 · lovetrade API 补全（Web 与观势共用）

路由组：
- catalyst: impacts/predictions/system-states/active-messages/accuracy/dashboard
- topic: tree/graph/intro/category-stocks/node CRUD
- market: radars/messages/dynamic-news/plate-movements/interval-stats/daily-metrics
- note: notes+categories CRUD
- report: list/get + morning/evening send → feishu webhook
- calendar: is-trading-day/trading-session/month-trading-days
- home: summary
- auth: login (username+password → bearer token)
"""
import hashlib
import json
import logging
import os
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
import yaml
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger("data-api.lovetrade")
TZ_CST = timezone(timedelta(hours=8))

router = APIRouter(tags=["lovetrade"])

# ─── Helpers ──────────────────────────────────────────────────────────

SECRETS_PATH = os.path.join(os.path.dirname(__file__), "..", "configs", "secrets.yaml")


def load_secrets() -> dict:
    if os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_reader_conn():
    secrets = load_secrets()
    db = secrets.get("database", {})
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER_READER", "duser_reader"),
        password=db.get("duser_reader_password", ""),
        options="-c statement_timeout=30s",
    )


def get_writer_conn():
    secrets = load_secrets()
    db = secrets.get("database", {})
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER_WRITER", "duser_writer"),
        password=db.get("duser_writer_password", ""),
    )


def envelope(data, rows=None):
    """Java 兼容响应格式: {code: 0, data: ..., message: 'ok'}
    web 端 isBackendSuccess 检查 code === '0'; transformBackendResponse 提取 data.
    """
    return {
        "code": 0,
        "data": data,
        "message": "ok",
        "meta": {
            "rows": rows or (len(data) if isinstance(data, list) else 1),
            "server_ts": datetime.now(TZ_CST).isoformat(),
        }
    }


def verify_token_from_header(authorization: str) -> str:
    """Simple token verification for this router."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "AUTH", "msg": "Missing bearer token"})
    token = authorization[7:]
    secrets = load_secrets()
    api_cfg = secrets.get("api", {})
    valid_tokens = {
        api_cfg.get("bearer_token_read", ""): "read",
        api_cfg.get("bearer_token_write", ""): "write",
        api_cfg.get("bearer_token_admin", ""): "admin",
    }
    role = valid_tokens.get(token)
    if not role:
        raise HTTPException(status_code=401, detail={"code": "AUTH", "msg": "Invalid token"})
    return role


# ─── Catalyst 组 ─────────────────────────────────────────────────────

@router.get("/api/catalyst/impacts")
async def catalyst_impacts_list(
    date_from: str = None, date_to: str = None,
    message_type: str = None, lifecycle_stage: str = None,
    limit: int = Query(default=100, le=1000),
    authorization: str = None,
):
    """catalyst_impacts 列表（Z7-ext: 映射到 catalyst_impact 表）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT impact_id as id, date, message_summary, message_type, impact_level,
                        lifecycle_stage, remaining_influence, confidence, global_coupling,
                        verified_result, created_time, updated_time
                 FROM catalyst_impact WHERE 1=1"""
        params = []
        if date_from:
            sql += " AND date >= %s"
            params.append(date_from)
        if date_to:
            sql += " AND date <= %s"
            params.append(date_to)
        if message_type:
            sql += " AND message_type = %s"
            params.append(message_type)
        if lifecycle_stage:
            sql += " AND lifecycle_stage = %s"
            params.append(lifecycle_stage)
        sql += " ORDER BY date DESC, impact_level DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/catalyst/impacts/{impact_id}")
async def catalyst_impact_get(impact_id: str, authorization: str = None):
    """单个 impact 详情"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT * FROM catalyst_impact WHERE impact_id = %s""", (impact_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Impact not found")
    return envelope(dict(row))


@router.get("/api/catalyst/predictions")
async def catalyst_predictions_list(
    status: str = None, category: str = None,
    limit: int = Query(default=100, le=1000),
    authorization: str = None,
):
    """catalyst_predictions 列表（映射到 prediction 表 P- 前缀）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT prediction_id as id, created_at, statement, category,
                        confidence_pct, falsify, check_date, horizon, result, result_note
                 FROM prediction WHERE prediction_id LIKE 'P-%'"""
        params = []
        if status:
            sql += " AND result = %s"
            params.append(status)
        if category:
            sql += " AND category = %s"
            params.append(category)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/catalyst/predictions/{prediction_id}")
async def catalyst_prediction_get(prediction_id: str, authorization: str = None):
    """单个 prediction 详情"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM prediction WHERE prediction_id = %s", (prediction_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return envelope(dict(row))


@router.get("/api/catalyst/system-states")
async def catalyst_system_states_list(
    limit: int = Query(default=50, le=500),
    authorization: str = None,
):
    """system_states 列表（Z7-ext: 映射到 catalyst_system_state 表）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT scan_session, date, scan_time, overall_phase,
                              overall_note, global_coupling, sentiment,
                              created_time, updated_time
                       FROM catalyst_system_state
                       ORDER BY date DESC, scan_time DESC LIMIT %s""", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/catalyst/system-states/{state_id}")
async def catalyst_system_state_get(state_id: str, authorization: str = None):
    """单个 system_state 详情"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM catalyst_system_state WHERE scan_session = %s", (state_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="System state not found")
    return envelope(dict(row))


@router.get("/api/catalyst/active-messages")
async def catalyst_active_messages_list(
    is_active: bool = True,
    limit: int = Query(default=100, le=500),
    authorization: str = None,
):
    """active_messages（Z7-ext: 映射到 catalyst_active_message 表）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT am_id as id, impact_id, message_title, current_stage,
                        remaining_influence, is_active, expected_decay_date,
                        daily_updates, created_time, updated_time
                 FROM catalyst_active_message WHERE 1=1"""
        if is_active:
            sql += " AND is_active = true"
        sql += " ORDER BY updated_time DESC LIMIT %s"
        cur.execute(sql, (limit,))
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/catalyst/accuracy")
async def catalyst_accuracy(
    category: str = None,
    horizon: str = None,
    authorization: str = None,
):
    """预测准确率聚合"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT category, horizon,
                        COUNT(*) as total,
                        SUM(CASE WHEN result = 'hit' THEN 1 WHEN result = 'partial' THEN 0.5 ELSE 0 END) as hits,
                        SUM((result = 'miss')::int) as misses,
                        ROUND(
                            SUM(CASE WHEN result = 'hit' THEN 1 WHEN result = 'partial' THEN 0.5 ELSE 0 END)::numeric
                            / NULLIF(SUM((result IN ('hit','miss','partial'))::int), 0) * 100, 1) as hit_rate_pct
                 FROM prediction
                 WHERE prediction_id LIKE 'P-%' AND result IN ('hit','miss','partial')"""
        params = []
        if category:
            sql += " AND category = %s"
            params.append(category)
        if horizon:
            sql += " AND horizon = %s"
            params.append(horizon)
        sql += " GROUP BY category, horizon ORDER BY category, horizon"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/catalyst/dashboard")
async def catalyst_dashboard(authorization: str = None):
    """catalyst 聚合看板"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 总览 (Z7-ext: 使用新催化雷达表)
        cur.execute("""SELECT
            (SELECT COUNT(*) FROM catalyst_impact) as total_impacts,
            (SELECT COUNT(*) FROM catalyst_impact WHERE lifecycle_stage NOT IN ('decay','closed')) as active_impacts,
            (SELECT COUNT(*) FROM prediction WHERE prediction_id LIKE 'P-%') as total_predictions,
            (SELECT COUNT(*) FROM prediction WHERE prediction_id LIKE 'P-%' AND result='pending') as pending_predictions,
            (SELECT COUNT(*) FROM catalyst_system_state) as total_system_states
        """)
        overview = dict(cur.fetchone())
        # 最近 5 条 impact
        cur.execute("""SELECT impact_id as id, message_summary, lifecycle_stage, date
                       FROM catalyst_impact
                       ORDER BY date DESC LIMIT 5""")
        recent_impacts = [dict(r) for r in cur.fetchall()]
        # 最近 5 条 prediction
        cur.execute("""SELECT prediction_id as id, statement, result, check_date
                       FROM prediction WHERE prediction_id LIKE 'P-%'
                       ORDER BY created_at DESC LIMIT 5""")
        recent_predictions = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope({
        "overview": overview,
        "recent_impacts": recent_impacts,
        "recent_predictions": recent_predictions,
    })


# ─── Topic 组 ─────────────────────────────────────────────────────────

@router.get("/api/topic/tree")
async def topic_tree(authorization: str = None):
    """题材树形结构（topic → topic_category 层级）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT t.topic_id, t.theme_id, t.name, t.brief_intro,
                              t.topic_group_id, g.name as group_name
                       FROM topic t LEFT JOIN topic_group g ON t.topic_group_id = g.id
                       ORDER BY g.name, t.name""")
        topics = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT id, topic_id, parent_id, name FROM topic_category ORDER BY topic_id, parent_id, name""")
        categories = [dict(r) for r in cur.fetchall()]
    conn.close()
    # Build tree
    cat_by_topic = {}
    for c in categories:
        tid = c["topic_id"]
        if tid not in cat_by_topic:
            cat_by_topic[tid] = []
        cat_by_topic[tid].append(c)
    for t in topics:
        t["categories"] = cat_by_topic.get(t["topic_id"], [])
    return envelope(topics)


@router.get("/api/topic/graph")
async def topic_graph(authorization: str = None):
    """题材关联图谱（nodes + edges）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT topic_id as id, name FROM topic")
        nodes = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT id, source_topic_id, source_name, target_topic_id,
                              target_name, relation FROM topic_links""")
        edges = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope({"nodes": nodes, "edges": edges})


@router.get("/api/topic/intro/{topic_id}")
async def topic_intro(topic_id: str, authorization: str = None):
    """题材详情（含 AI 解析）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT t.*, g.name as group_name
                       FROM topic t LEFT JOIN topic_group g ON t.topic_group_id = g.id
                       WHERE t.topic_id = %s""", (topic_id,))
        topic = cur.fetchone()
        if not topic:
            conn.close()
            raise HTTPException(status_code=404, detail="Topic not found")
        cur.execute("""SELECT id, parent_id, name FROM topic_category WHERE topic_id = %s ORDER BY parent_id, name""",
                    (topic_id,))
        categories = [dict(r) for r in cur.fetchall()]
    conn.close()
    result = dict(topic)
    result["categories"] = categories
    return envelope(result)


@router.get("/api/topic/category-stocks/{category_id}")
async def topic_category_stocks(category_id: str, authorization: str = None):
    """题材分类下的个股列表（从 stock_sector_map 查）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT code, sector_name FROM stock_sector_map
                       WHERE sector_code = %s AND kind = 'theme'
                       ORDER BY code""", (f"theme_{category_id}",))
        stocks = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(stocks)


def _fmt_amount(v):
    if v is None:
        return "-"
    n = float(v)
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1e8:
        return f"{sign}{a / 1e8:.2f}亿"
    if a >= 1e4:
        return f"{sign}{a / 1e4:.2f}万"
    return f"{n:.2f}"


def _iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else (str(d) if d is not None else None)


@router.get("/api/trading/dashboard/plates")
async def trading_dashboard_plates(authorization: str = None):
    """资金流向气泡。主力净额按亿返回，和页面 formatYi 一致。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT ON (sector_code)
                   sector_code, sector_name, pct, turnover, main_net_inflow, up_cnt
            FROM sector_daily
            ORDER BY sector_code, date DESC
        """)
        rows = cur.fetchall()
    conn.close()
    data = []
    for r in rows:
        inflow = r["main_net_inflow"]
        data.append({
            "code": r["sector_code"],
            "name": r["sector_name"] or r["sector_code"],
            "latestGrowthRate": r["pct"],
            "latestCje": r["turnover"],
            "latestLargeForce": (float(inflow) / 1e8) if inflow is not None else 0,
            "latestStrong": r["up_cnt"] if r["up_cnt"] is not None else (abs(r["pct"]) if r["pct"] is not None else 0),
        })
    return envelope(data)


@router.get("/api/market/index/shanghai/daily-k")
async def shanghai_daily_k(startDate: str = None, endDate: str = None, authorization: str = None):
    """上证指数日 K。页面用 startDate/endDate。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT date, open, high, low, close,
                        COALESCE(volume, 0) AS volume, COALESCE(amount, 0) AS amount
                 FROM index_daily WHERE code = 'sh000001'"""
        params = []
        if startDate:
            sql += " AND date >= %s"
            params.append(startDate)
        if endDate:
            sql += " AND date <= %s"
            params.append(endDate)
        sql += " ORDER BY date"
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    data = [{
        "date": _iso(r["date"]),
        "open": r["open"] or 0,
        "high": r["high"] or 0,
        "low": r["low"] or 0,
        "close": r["close"] or 0,
        "volume": r["volume"] or 0,
        "amount": r["amount"] or 0,
    } for r in rows]
    return envelope(data)


@router.get("/api/trading/dashboard/plate/interval-stats")
async def plate_interval_stats(startDate: str = None, endDate: str = None, authorization: str = None):
    """区间统计。按板块汇总 sector_daily。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT date, sector_code, sector_name, pct, main_net_inflow, turnover
                 FROM sector_daily WHERE 1=1"""
        params = []
        if startDate:
            sql += " AND date >= %s"
            params.append(startDate)
        if endDate:
            sql += " AND date <= %s"
            params.append(endDate)
        sql += " ORDER BY sector_code, date"
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    buckets = {}
    for r in rows:
        b = buckets.setdefault(r["sector_code"], {
            "code": r["sector_code"],
            "name": r["sector_name"] or r["sector_code"],
            "growth": 0.0,
            "net": 0.0,
            "turnover": 0.0,
            "strength": 0.0,
            "days": [],
        })
        pct = float(r["pct"] or 0)
        net = float(r["main_net_inflow"] or 0)
        turn = float(r["turnover"] or 0)
        b["growth"] += pct
        b["net"] += net
        b["turnover"] += turn
        b["strength"] = max(b["strength"], abs(pct))
        b["days"].append(net)
    data = []
    for b in buckets.values():
        streak = 0
        for net in reversed(b["days"]):
            if net > 0:
                streak += 1
            else:
                break
        data.append({
            "code": b["code"],
            "name": b["name"],
            "intervalGrowthRateSum": round(b["growth"], 4),
            "intervalNetAmount": _fmt_amount(b["net"]),
            "intervalNetAmountRaw": b["net"],
            "intervalStrength": round(b["strength"], 4),
            "intervalTurnover": _fmt_amount(b["turnover"]),
            "intervalTurnoverRaw": b["turnover"],
            "netInflowStreakDays": streak,
        })
    data.sort(key=lambda x: x["intervalNetAmountRaw"], reverse=True)
    return envelope(data)


@router.get("/api/trading/dashboard/plate/daily-metrics")
async def plate_daily_metrics(code: str, authorization: str = None):
    """单板块日频序列，供区间统计详情图。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT date, pct, main_net_inflow, turnover
            FROM sector_daily WHERE sector_code = %s ORDER BY date
        """, (code,))
        rows = cur.fetchall()
    conn.close()
    data = [{
        "date": _iso(r["date"]),
        "growthRate": r["pct"],
        "largeForce": float(r["main_net_inflow"] or 0) / 1e8,
        "strength": abs(float(r["pct"] or 0)),
        "turnover": float(r["turnover"] or 0),
    } for r in rows]
    return envelope(data)


@router.get("/api/topic/graph/neo4j-structure")
async def topic_neo4j_structure(authorization: str = None):
    """题材库图谱。节点 id 用名称，topicId 供详情查询。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT t.topic_id, t.name, COALESCE(g.name, '未分类') AS group_name
            FROM topic t
            LEFT JOIN topic_group g ON t.topic_group_id = g.id
            ORDER BY g.name, t.name
        """)
        topics = cur.fetchall()
        cur.execute("""SELECT source_topic_id, target_topic_id, relation FROM topic_links""")
        edges = cur.fetchall()
    conn.close()
    id_of = {}
    used = set()
    nodes = []
    for t in topics:
        label = t["name"] or t["topic_id"]
        node_id = label
        if node_id in used:
            node_id = f"{label}#{t['topic_id']}"
        used.add(node_id)
        id_of[t["topic_id"]] = node_id
        nodes.append({"id": node_id, "topicId": t["topic_id"], "group": t["group_name"] or "未分类"})
    links = []
    for e in edges:
        src = id_of.get(e["source_topic_id"])
        dst = id_of.get(e["target_topic_id"])
        if src and dst:
            links.append({"source": src, "target": dst, "relation": e["relation"] or ""})
    return envelope({"nodes": nodes, "links": links})


@router.get("/api/topic/intro")
async def topic_intro_query(topicId: str, authorization: str = None):
    """题材简介。页面用 query topicId。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT topic_id, name, brief_intro, introduction, ai_introduction
                       FROM topic WHERE topic_id = %s""", (topicId,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Topic not found")
    return envelope({
        "topicId": row["topic_id"],
        "name": row["name"],
        "briefIntro": row["brief_intro"] or "",
        "introduction": row["introduction"] or "",
        "aiIntroduction": row["ai_introduction"] or "",
    })


@router.get("/api/topic/category-stocks")
async def topic_category_stocks_by_topic(topicId: str, authorization: str = None):
    """题材下的分类树和个股。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT topic_id, name FROM topic WHERE topic_id = %s", (topicId,))
        topic = cur.fetchone()
        if not topic:
            conn.close()
            raise HTTPException(status_code=404, detail="Topic not found")
        cur.execute("""SELECT id, parent_id, name FROM topic_category
                       WHERE topic_id = %s ORDER BY parent_id, name""", (topicId,))
        cats = [dict(r) for r in cur.fetchall()]
        codes = [f"theme_{c['id']}" for c in cats]
        stocks_by_cat = {}
        if codes:
            cur.execute("""
                SELECT m.sector_code, m.code, COALESCE(i.name, '') AS stock_name
                FROM stock_sector_map m
                LEFT JOIN instrument_master i ON i.code = m.code
                WHERE m.kind = 'theme' AND m.sector_code = ANY(%s)
                ORDER BY m.code
            """, (codes,))
            for s in cur.fetchall():
                cid = s["sector_code"].replace("theme_", "", 1)
                stocks_by_cat.setdefault(cid, []).append({
                    "stockId": s["code"],
                    "stockName": s["stock_name"] or "",
                    "reason": "",
                })
    conn.close()
    nodes = {}
    for c in cats:
        nodes[c["id"]] = {
            "id": c["id"],
            "name": c["name"],
            "stocks": stocks_by_cat.get(c["id"], []),
            "children": [],
            "_parent": c["parent_id"],
        }
    roots = []
    for n in nodes.values():
        pid = n.pop("_parent")
        if pid and pid != "0" and pid in nodes:
            nodes[pid]["children"].append(n)
        else:
            roots.append(n)
    return envelope({
        "topicId": topic["topic_id"],
        "topicName": topic["name"],
        "categories": roots,
    })


# ─── Market 组 ────────────────────────────────────────────────────────

@router.get("/api/market/radars")
async def market_radars(
    date: str = None,
    limit: int = Query(default=100, le=1000),
    authorization: str = None,
):
    """市场雷达列表"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM radar_event WHERE 1=1"
        params = []
        if date:
            sql += " AND ts::date = %s"
            params.append(date)
        sql += " ORDER BY ts DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/market/messages")
async def market_messages(
    date: str = None,
    limit: int = Query(default=100, le=1000),
    authorization: str = None,
):
    """市场消息列表"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM market_messages WHERE 1=1"
        params = []
        if date:
            sql += " AND msg_ts::date = %s"
            params.append(date)
        sql += " ORDER BY msg_ts DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/market/dynamic-news")
async def market_dynamic_news(
    date: str = None,
    limit: int = Query(default=100, le=1000),
    authorization: str = None,
):
    """盘中动态新闻"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM news_telegraph WHERE 1=1"
        params = []
        if date:
            sql += " AND pub_ts::date = %s"
            params.append(date)
        sql += " ORDER BY pub_ts DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


def _clock(ts):
    if ts is None:
        return "", ""
    return _iso(ts)[:10], ts.strftime("%H:%M:%S") if hasattr(ts, "strftime") else ""


@router.get("/api/market/dynamic/news")
async def market_dynamic_news_alias(date: str = None, limit: int = Query(default=200, le=1000), authorization: str = None):
    """盘中动态。页面要 comment/stock/time。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT msg_ts, msg_id, code, title, content
                 FROM market_messages WHERE 1=1"""
        params = []
        if date:
            sql += " AND msg_ts::date = %s"
            params.append(date)
        sql += " ORDER BY msg_ts DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    data = []
    for r in rows:
        day, clock = _clock(r["msg_ts"])
        data.append({
            "id": r["msg_id"],
            "date": day,
            "time": clock,
            "comment": r["content"] or r["title"] or "",
            "stock": r["code"] or "",
        })
    return envelope(data)


@router.get("/api/market/market-radars")
async def market_radars_alias(date: str = None, limit: int = Query(default=200, le=1000), authorization: str = None):
    """市场雷达。页面要 stockName/lbStatus/status/content。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT ts, event_id, event_type, title, content, extra
                 FROM radar_event WHERE 1=1"""
        params = []
        if date:
            sql += " AND ts::date = %s"
            params.append(date)
        sql += " ORDER BY ts DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    data = []
    for r in rows:
        extra = r["extra"] if isinstance(r["extra"], dict) else {}
        day, clock = _clock(r["ts"])
        data.append({
            "id": r["event_id"],
            "date": day,
            "time": clock,
            "content": r["content"] or r["title"] or "",
            "stockName": extra.get("stock_name") or r["title"] or "",
            "lbStatus": extra.get("lb_status") or r["event_type"] or "",
            "status": extra.get("status") or "",
        })
    return envelope(data)


@router.get("/api/market/plate-movements")
async def plate_movements(
    date: str = None, freq: str = "daily",
    limit: int = Query(default=100, le=1000),
    authorization: str = None,
):
    """板块异动（daily 或 intraday）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if freq == "5m":
            sql = "SELECT * FROM plate_movement_intraday WHERE 1=1"
            params = []
            if date:
                sql += " AND ts::date = %s"
                params.append(date)
            sql += " ORDER BY ts DESC LIMIT %s"
            params.append(limit)
        else:
            sql = "SELECT * FROM sector_daily WHERE 1=1"
            params = []
            if date:
                sql += " AND date = %s"
                params.append(date)
            sql += " ORDER BY date DESC, pct DESC LIMIT %s"
            params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/market/interval-stats")
async def market_interval_stats(
    date: str = None,
    authorization: str = None,
):
    """盘中区间统计（从 plate_movement_intraday 聚合）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT sector_code, sector_name,
                        COUNT(*) as intervals,
                        AVG(pct) as avg_pct,
                        SUM(main_net_inflow) as total_inflow
                 FROM plate_movement_intraday WHERE 1=1"""
        params = []
        if date:
            sql += " AND ts::date = %s"
            params.append(date)
        else:
            sql += " AND ts::date = CURRENT_DATE"
        sql += " GROUP BY sector_code, sector_name ORDER BY total_inflow DESC LIMIT 50"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/market/daily-metrics")
async def market_daily_metrics(
    date: str = None,
    authorization: str = None,
):
    """日频板块指标"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM sector_daily WHERE 1=1"
        params = []
        if date:
            sql += " AND date = %s"
            params.append(date)
        else:
            sql += " AND date = (SELECT MAX(date) FROM sector_daily)"
        sql += " ORDER BY pct DESC LIMIT 100"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


# ─── Note 组 ──────────────────────────────────────────────────────────

@router.get("/api/note/list")
async def notes_list(
    category_id: str = None,
    limit: int = Query(default=50, le=200),
    authorization: str = None,
):
    """笔记列表"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """SELECT n.*, c.name as category_name
                 FROM trading_note n LEFT JOIN note_category c ON n.category_id = c.id WHERE 1=1"""
        params = []
        if category_id:
            sql += " AND n.category_id = %s"
            params.append(category_id)
        sql += " ORDER BY n.created_time DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/note/{note_id}")
async def note_get(note_id: str, authorization: str = None):
    """笔记详情"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM trading_note WHERE id = %s", (note_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")
    return envelope(dict(row))


class NoteCreate(BaseModel):
    category_id: str
    title: str
    content: str
    tags: Optional[str] = None


@router.post("/api/note")
async def note_create(note: NoteCreate, authorization: str = None):
    """创建笔记"""
    conn = get_writer_conn()
    note_id = f"note_{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO trading_note (id, category_id, title, content, tags, source, ingest_ts)
                       VALUES (%s,%s,%s,%s,%s,'web', now())""",
                    (note_id, note.category_id, note.title, note.content, note.tags))
    conn.commit()
    conn.close()
    return envelope({"id": note_id, "created": True})


@router.get("/api/note/category/enabled")
async def note_categories_list(authorization: str = None):
    """笔记分类列表"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM note_category ORDER BY sort_order, name")
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


# ─── Report 组 ────────────────────────────────────────────────────────

@router.get("/api/reports")
async def reports_list(
    type: str = None, date: str = None,
    limit: int = Query(default=20, le=100),
    authorization: str = None,
):
    """报告列表"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT id, type, title, report_date, generate_time, send_status, send_time FROM report WHERE 1=1"
        params = []
        if type:
            sql += " AND type = %s"
            params.append(type)
        if date:
            sql += " AND report_date = %s"
            params.append(date)
        sql += " ORDER BY generate_time DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.get("/api/reports/{report_id}")
async def report_get(report_id: str, authorization: str = None):
    """报告详情"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM report WHERE id = %s", (report_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return envelope(dict(row))


@router.post("/api/reports/{report_type}/send")
async def report_send(report_type: str, authorization: str = None):
    """发送报告到飞书 webhook（morning/evening）"""
    secrets = load_secrets()
    feishu_cfg = secrets.get("feishu", {})
    webhook_url = feishu_cfg.get("webhook_url")
    if not webhook_url or webhook_url == "PENDING":
        raise HTTPException(status_code=503, detail="Feishu webhook not configured")

    # Get latest report of this type
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT * FROM report WHERE type = %s
                       ORDER BY generate_time DESC LIMIT 1""", (report_type,))
        report = cur.fetchone()
    conn.close()
    if not report:
        raise HTTPException(status_code=404, detail=f"No {report_type} report found")

    # Send to Feishu
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": report["title"]}},
            "elements": [{"tag": "markdown", "content": report["content"][:2000]}]
        }
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"Feishu returned {resp.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Feishu send failed: {e}")

    # Update send status
    conn = get_writer_conn()
    with conn.cursor() as cur:
        cur.execute("""UPDATE report SET send_status = 1, send_time = now() WHERE id = %s""",
                    (report["id"],))
    conn.commit()
    conn.close()
    return envelope({"sent": True, "report_id": report["id"]})


# ─── Calendar 组 ──────────────────────────────────────────────────────

@router.get("/api/meta/calendar/is-trading-day")
async def calendar_is_trading_day(date: str = None, authorization: str = None):
    """判断是否交易日"""
    check_date = date or datetime.now(TZ_CST).strftime("%Y-%m-%d")
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT cal_date, is_open FROM trade_cal
                       WHERE market = 'SSE' AND cal_date = %s""", (check_date,))
        row = cur.fetchone()
    conn.close()
    if not row:
        return envelope({"date": check_date, "is_trading_day": False, "note": "no record"})
    return envelope({"date": check_date, "is_trading_day": row["is_open"] == 1})


@router.get("/api/meta/calendar/trading-session")
async def calendar_trading_session(authorization: str = None):
    """当前交易时段判断"""
    now = datetime.now(TZ_CST)
    t = now.hour * 100 + now.minute
    if 915 <= t <= 925:
        session = "call_auction"
    elif 930 <= t <= 1130:
        session = "morning_continuous"
    elif 1300 <= t <= 1500:
        session = "afternoon_continuous"
    elif 1500 < t <= 1530:
        session = "closing"
    else:
        session = "closed"
    return envelope({
        "datetime": now.isoformat(),
        "session": session,
        "is_trading_hours": session in ("call_auction", "morning_continuous", "afternoon_continuous"),
    })


@router.get("/api/trading/calendar/is-trading-day")
async def calendar_is_trading_day_compat(date: str = None, authorization: str = None):
    """query.py 旧路径。日历市场是 SSE。"""
    return await calendar_is_trading_day(date, authorization)


@router.get("/api/trading/calendar/trading-session")
async def calendar_trading_session_compat(authorization: str = None):
    return await calendar_trading_session(authorization)


@router.get("/api/trading/calendar/in-trading-time")
async def calendar_in_trading_time(authorization: str = None):
    body = await calendar_trading_session(authorization)
    data = body["data"]
    return envelope({
        "in_trading_time": data["is_trading_hours"],
        "session": data["session"],
        "datetime": data["datetime"],
    })


@router.get("/api/category/enabled")
async def category_enabled_compat(authorization: str = None):
    return await note_categories_list(authorization)


@router.get("/api/meta/calendar/month-trading-days")
async def calendar_month_trading_days(year: int = None, month: int = None, authorization: str = None):
    """月度交易日列表"""
    now = datetime.now(TZ_CST)
    y = year or now.year
    m = month or now.month
    start = f"{y}-{m:02d}-01"
    end = f"{y}-{m:02d}-31"
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""SELECT cal_date, is_open FROM trade_cal
                       WHERE market = 'SSE' AND cal_date >= %s AND cal_date <= %s AND is_open = 1
                       ORDER BY cal_date""", (start, end))
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope({"year": y, "month": m, "trading_days": [r["cal_date"] for r in rows]})


# ─── Home Summary ─────────────────────────────────────────────────────

@router.get("/api/home/summary")
async def home_summary(authorization: str = None):
    """首页聚合摘要"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 今日是否交易日
        cur.execute("""SELECT is_open FROM trade_cal WHERE market='CN' AND cal_date = CURRENT_DATE""")
        row = cur.fetchone()
        is_trading = row["is_open"] == 1 if row else False
        # 最新指数
        cur.execute("""SELECT code, close, pct FROM index_daily
                       WHERE date = (SELECT MAX(date) FROM index_daily) ORDER BY code LIMIT 6""")
        indices = [dict(r) for r in cur.fetchall()]
        # 最新情绪
        cur.execute("""SELECT * FROM sentiment_daily ORDER BY date DESC LIMIT 1""")
        sentiment = cur.fetchone()
        # 题材数
        cur.execute("SELECT COUNT(*) as cnt FROM topic")
        topic_cnt = cur.fetchone()["cnt"]
        # 待验预测
        cur.execute("""SELECT COUNT(*) as cnt FROM prediction
                       WHERE prediction_id LIKE 'P-%' AND result = 'pending'""")
        pending_pred = cur.fetchone()["cnt"]
    conn.close()
    return envelope({
        "is_trading_day": is_trading,
        "latest_indices": indices,
        "latest_sentiment": dict(sentiment) if sentiment else None,
        "topic_count": topic_cnt,
        "pending_predictions": pending_pred,
    })


# ─── Auth /login ──────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
@router.post("/api/user/login")
async def auth_login(req: LoginRequest):
    """用户名密码登录 → 返回 bearer token。/auth/login 为 web 新路径，/api/user/login 保留兼容。"""
    secrets = load_secrets()
    web_cfg = secrets.get("web", {})
    users = web_cfg.get("users", [])

    for u in users:
        if u["username"] == req.username:
            # MD5(salt + password)
            salted = u["salt"] + req.password
            hashed = hashlib.md5(salted.encode()).hexdigest()
            if hashed == u["password_hash"]:
                # Return corresponding token
                role = u.get("role", "read")
                api_cfg = secrets.get("api", {})
                if role == "admin":
                    token = api_cfg.get("bearer_token_admin", "")
                elif role == "write":
                    token = api_cfg.get("bearer_token_write", "")
                else:
                    token = api_cfg.get("bearer_token_read", "")
                return envelope({"token": token, "role": role, "username": req.username})

    raise HTTPException(status_code=401, detail={"code": "AUTH", "msg": "Invalid credentials"})


# ─── Web 兼容端点（Z9A 补全） ────────────────────────────────────────

@router.get("/api/note/count/month")
async def note_count_month(
    month: str = None,
    authorization: str = None,
):
    """按月统计笔记数（web NOTE_URLS.COUNT_MONTH）"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if month:
            cur.execute("""
                SELECT date_trunc('month', created_time)::date AS date, COUNT(*) AS count
                FROM trading_note
                WHERE date_trunc('month', created_time)::date = %s::date
                GROUP BY 1 ORDER BY 1
            """, (f"{month}-01",))
        else:
            cur.execute("""
                SELECT date_trunc('month', created_time)::date AS date, COUNT(*) AS count
                FROM trading_note
                GROUP BY 1 ORDER BY 1 DESC LIMIT 12
            """)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@router.post("/api/note/{note_id}/top")
async def note_top(note_id: str, authorization: str = None):
    """置顶/取消置顶笔记（web NOTE_URLS.TOP）"""
    conn = get_writer_conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE trading_note SET is_top = NOT COALESCE(is_top, false), updated_time = now()
            WHERE id = %s RETURNING id
        """, (note_id,))
        updated = cur.fetchone()
    conn.commit()
    conn.close()
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")
    return envelope(True)


@router.put("/api/note")
async def note_update(request: Request, authorization: str = None):
    """更新笔记（web note.ts updateNote）"""
    body = await request.json()
    note_id = body.get("id")
    if not note_id:
        raise HTTPException(status_code=400, detail="id is required")
    conn = get_writer_conn()
    with conn.cursor() as cur:
        sets = ["updated_time = now()"]
        params = []
        for field in ("category_id", "title", "content", "tags"):
            if field in body:
                sets.append(f"{field} = %s")
                params.append(body[field])
        if len(sets) <= 1:
            conn.close()
            return envelope(False)
        params.append(note_id)
        cur.execute(f"UPDATE trading_note SET {', '.join(sets)} WHERE id = %s RETURNING id", params)
        updated = cur.fetchone()
    conn.commit()
    conn.close()
    return envelope(bool(updated))


@router.delete("/api/note/{note_id}")
async def note_delete(note_id: str, authorization: str = None):
    """删除笔记（web note.ts deleteNote）"""
    conn = get_writer_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trading_note WHERE id = %s RETURNING id", (note_id,))
        deleted = cur.fetchone()
    conn.commit()
    conn.close()
    return envelope(bool(deleted))


@router.get("/api/user/personal")
async def user_personal(authorize: str = None):
    """获取当前用户信息（web AUTH_URLS.GET_USER_INFO）"""
    # Simplified: return a default user profile
    return envelope({
        "userId": "1",
        "userName": "admin",
        "roles": ["R_SUPER"],
        "buttons": [],
        "avatar": "",
    })


@router.post("/api/auth/refreshToken")
async def auth_refresh_token(request: Request):
    """刷新 token（web AUTH_URLS.REFRESH_TOKEN）"""
    body = await request.json()
    refresh_token = body.get("refreshToken", "")
    # For now, return the same read token (simplified)
    secrets = load_secrets()
    api_cfg = secrets.get("api", {})
    return envelope({
        "token": api_cfg.get("bearer_token_read", ""),
        "refreshToken": refresh_token,
    })


@router.get("/api/route/getConstantRoutes")
async def route_get_constant(authorization: str = None):
    """获取常量路由（web ROUTE_URLS）"""
    # Return static route config - web uses VITE_AUTH_ROUTE_MODE=static
    return envelope([])


@router.get("/api/route/getReactUserRoutes")
async def route_get_user_routes(authorization: str = None):
    """获取用户路由（web ROUTE_URLS）"""
    return envelope({"routes": [], "home": "/home"})


@router.get("/api/route/isRouteExist")
async def route_is_exist(routeName: str = None, authorization: str = None):
    """路由是否存在检查"""
    return envelope(True)


# ─── Trading System 组（web TRADING_SYSTEM_URLS） ────────────────────

@router.get("/api/trading-system/tree")
async def trading_system_tree(authorization: str = None):
    """交易系统节点树"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, parent_id, name, description, sort_order, color,
                   created_time, updated_time
            FROM trading_system_node
            ORDER BY sort_order, created_time
        """)
        nodes = [dict(r) for r in cur.fetchall()]
    conn.close()
    # Build tree
    node_map = {}
    roots = []
    for n in nodes:
        n["children"] = []
        node_map[n["id"]] = n
    for n in nodes:
        pid = n.get("parent_id")
        if pid and pid in node_map:
            node_map[pid]["children"].append(n)
        else:
            roots.append(n)
    return envelope(roots)


@router.get("/api/trading-system/node/{node_id}")
async def trading_system_node_get(node_id: str, authorization: str = None):
    """单个节点详情"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM trading_system_node WHERE id = %s", (node_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Node not found")
    return envelope(dict(row))


@router.post("/api/trading-system/node")
async def trading_system_node_create(request: Request, authorization: str = None):
    """创建节点"""
    body = await request.json()
    node_id = f"tsn_{datetime.now(TZ_CST).strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    conn = get_writer_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO trading_system_node (id, parent_id, name, description, sort_order, color)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            node_id, body.get("parentId") or "0", body.get("name", ""),
            body.get("description", ""),
            body.get("sortOrder", 0), body.get("color"),
        ))
    conn.commit()
    conn.close()
    return envelope({"id": node_id})


@router.put("/api/trading-system/node/{node_id}")
async def trading_system_node_update(node_id: str, request: Request, authorization: str = None):
    """更新节点"""
    body = await request.json()
    conn = get_writer_conn()
    with conn.cursor() as cur:
        sets = ["updated_time = now()"]
        params = []
        for field, col in [("name", "name"), ("description", "description"),
                           ("parentId", "parent_id"), ("sortOrder", "sort_order"),
                           ("color", "color")]:
            if field in body:
                sets.append(f"{col} = %s")
                params.append(body[field])
        params.append(node_id)
        cur.execute(f"UPDATE trading_system_node SET {', '.join(sets)} WHERE id = %s RETURNING id", params)
        updated = cur.fetchone()
    conn.commit()
    conn.close()
    if not updated:
        raise HTTPException(status_code=404, detail="Node not found")
    return envelope({"id": node_id})


@router.delete("/api/trading-system/node/{node_id}")
async def trading_system_node_delete(node_id: str, authorization: str = None):
    """删除节点"""
    conn = get_writer_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM trading_system_node WHERE id = %s RETURNING id", (node_id,))
        deleted = cur.fetchone()
    conn.commit()
    conn.close()
    return envelope(bool(deleted))


# ─── System Manage 组（web SYSTEM_MANAGE_URLS · 简化桩） ─────────────

@router.get("/api/systemManage/getRoleList")
async def system_get_role_list(authorization: str = None):
    """角色列表（桩）"""
    return envelope({"list": [{"id": "1", "roleName": "admin", "roleCode": "R_SUPER", "status": 1}], "total": 1})


@router.get("/api/systemManage/getAllRoles")
async def system_get_all_roles(authorization: str = None):
    """所有启用角色（桩）"""
    return envelope([{"id": "1", "roleName": "admin", "roleCode": "R_SUPER"}])


@router.get("/api/systemManage/getUserList")
async def system_get_user_list(authorization: str = None):
    """用户列表（桩）"""
    return envelope({"list": [{"id": "1", "userName": "admin", "status": 1}], "total": 1})


@router.get("/api/systemManage/getMenuList/v2")
async def system_get_menu_list(authorization: str = None):
    """菜单列表（桩）"""
    return envelope([])


@router.get("/api/systemManage/getAllPages")
async def system_get_all_pages(authorization: str = None):
    """所有页面（桩）"""
    return envelope([])


@router.get("/api/systemManage/getMenuTree")
async def system_get_menu_tree(authorization: str = None):
    """菜单树（桩）"""
    return envelope([])


# ─── Public Catalyst 组（web PUBLIC_CATALYST_URLS · 免鉴权） ─────────

@router.get("/api/public/catalyst/dashboard")
async def public_catalyst_dashboard():
    """公开看板（免鉴权，X-Public-Token 验证由 nginx/网关层做）"""
    return await catalyst_dashboard()


@router.get("/api/public/catalyst/impacts")
async def public_catalyst_impacts(
    date_from: str = None, date_to: str = None,
    limit: int = Query(default=100, le=1000),
):
    return await catalyst_impacts_list(date_from=date_from, date_to=date_to, limit=limit)


@router.get("/api/public/catalyst/system-states")
async def public_catalyst_system_states(limit: int = Query(default=50, le=500)):
    return await catalyst_system_states_list(limit=limit)


@router.get("/api/public/catalyst/active-messages")
async def public_catalyst_active_messages(limit: int = Query(default=100, le=500)):
    return await catalyst_active_messages_list(limit=limit)
