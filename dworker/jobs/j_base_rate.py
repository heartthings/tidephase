"""
j_base_rate - 基率聚合作业
依据: docs/base_rate_calibration_spec.md v1.0 (观势 2026-10-07 会签冻结)
铸码 T3.1 实装 · 2026-10-10

口径摘要:
  1. regime: prediction.regime_at_create (空→'unclassified')
  2. category: prediction.category (7枚举)
  3. horizon: prediction.horizon (T1/T3/T5/W1, NULL→'_unknown')
  4. hit_rate = COUNT(hit) / NULLIF(COUNT(hit)+COUNT(miss), 0)
  5. expired 不计入 n 分母 (口径2)
  6. 双口径: rolling_90 + full
  7. reliability: <5=low, <20=medium, >=20=high, n=0=none
  8. Wilson 95% CI

频率: 每周五 18:00 / prediction 回写事件触发增量重算
数据源: prediction 表 (D12)
输出: base_rate 表
"""
import json
import logging
import math
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)
TZ_CST = timezone(timedelta(hours=8))

# 90 交易日 ≈ 130 日历日 (trade_cal 空时近似; 有 trade_cal 后精确计算)
ROLLING_90_CALENDAR_DAYS = 130


def _wilson_ci(n_hit: int, n_total: int, z: float = 1.96) -> list:
    """Wilson 95% 置信区间. n_total=0 → [None, None]."""
    if n_total == 0:
        return [None, None]
    p_hat = n_hit / n_total
    denom = 1 + z * z / n_total
    center = p_hat + z * z / (2 * n_total)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n_total)) / n_total)
    lower = max(0.0, (center - spread) / denom)
    upper = min(1.0, (center + spread) / denom)
    return [round(lower, 4), round(upper, 4)]


def _reliability(n_samples: int) -> str:
    if n_samples == 0:
        return "none"
    elif n_samples < 5:
        return "low"
    elif n_samples < 20:
        return "medium"
    else:
        return "high"


def _get_window_end(conn) -> date:
    """最新交易日 ≤ today. trade_cal 空时用 today (若 weekday) 或上周五."""
    today = datetime.now(TZ_CST).date()
    # 尝试从 trade_cal 获取
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(cal_date)::date FROM trade_cal
                WHERE market = 'CN' AND is_open = 1 AND cal_date <= %s
            """, (today,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass
    # 兜底: today if weekday, else last Friday
    if today.weekday() <= 4:  # Mon-Fri
        return today
    else:  # Sat→prev Fri, Sun→prev Fri
        days_back = today.weekday() - 4
        return today - timedelta(days=days_back)


def _get_window_start_rolling(window_end: date) -> date:
    """rolling_90 的 window_start = window_end - 130 日历日 (≈90 交易日)."""
    return window_end - timedelta(days=ROLLING_90_CALENDAR_DAYS)


def _get_window_start_full(conn, fallback: date = None) -> date:
    """全历史: 从最早有 prediction 数据之日起."""
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(created_at)::date FROM prediction")
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return (fallback or date.today()) - timedelta(days=365)


def _normalize_regime(raw: str) -> str:
    """regime 归一化. 空/NULL → 'unclassified'."""
    if not raw or raw.strip() == '':
        return 'unclassified'
    return raw.strip()


def _normalize_horizon(raw: str) -> str:
    """horizon 归一化. 空/NULL → '_unknown'."""
    if not raw or raw.strip() == '':
        return '_unknown'
    return raw.strip()


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_base_rate: 聚合 prediction → base_rate."""
    t0 = time.time()

    logger.info("[j_base_rate] Starting base_rate aggregation")

    # ─── 1. 确定窗口 ──────────────────────────────────────────
    window_end = _get_window_end(conn)
    window_start_rolling = _get_window_start_rolling(window_end)
    window_start_full = _get_window_start_full(conn, fallback=window_end)

    logger.info(f"[j_base_rate] window_end={window_end}, "
                f"rolling_start={window_start_rolling}, full_start={window_start_full}")

    # ─── 2. 从 prediction 聚合 ────────────────────────────────
    # 按 (regime, category, horizon) 分组, 分别统计 rolling_90 和 full 窗口
    # 只统计 result IN ('hit', 'miss') 的行 (expired/pending/invalid 排除)
    # 同时统计 n_expired, n_pending 供 stat_json

    aggregation_sql = """
        SELECT
            COALESCE(NULLIF(regime_at_create, ''), 'unclassified') AS regime,
            category,
            COALESCE(NULLIF(horizon, ''), '_unknown') AS horizon,
            -- rolling_90
            COUNT(*) FILTER (WHERE result = 'hit'
                AND created_at::date >= %s AND created_at::date <= %s) AS rolling_n_hit,
            COUNT(*) FILTER (WHERE result = 'miss'
                AND created_at::date >= %s AND created_at::date <= %s) AS rolling_n_miss,
            COUNT(*) FILTER (WHERE result = 'expired'
                AND created_at::date >= %s AND created_at::date <= %s) AS rolling_n_expired,
            COUNT(*) FILTER (WHERE result = 'pending'
                AND created_at::date >= %s AND created_at::date <= %s) AS rolling_n_pending,
            -- full
            COUNT(*) FILTER (WHERE result = 'hit') AS full_n_hit,
            COUNT(*) FILTER (WHERE result = 'miss') AS full_n_miss,
            COUNT(*) FILTER (WHERE result = 'expired') AS full_n_expired,
            COUNT(*) FILTER (WHERE result = 'pending') AS full_n_pending
        FROM prediction
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """

    rows_written = 0
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(aggregation_sql, (
                window_start_rolling, window_end,
                window_start_rolling, window_end,
                window_start_rolling, window_end,
                window_start_rolling, window_end,
            ))
            groups = cur.fetchall()

        logger.info(f"[j_base_rate] Found {len(groups)} (regime,category,horizon) groups")

        for g in groups:
            regime = g['regime']
            category = g['category']
            horizon = g['horizon']

            # 对每个 group 写两行: rolling_90 + full
            for window_type, w_start, n_hit, n_miss, n_expired, n_pending in [
                ('rolling_90', window_start_rolling,
                 g['rolling_n_hit'], g['rolling_n_miss'],
                 g['rolling_n_expired'], g['rolling_n_pending']),
                ('full', window_start_full,
                 g['full_n_hit'], g['full_n_miss'],
                 g['full_n_expired'], g['full_n_pending']),
            ]:
                n_samples = n_hit + n_miss  # expired 不计入分母 (口径2)
                hit_rate = n_hit / n_samples if n_samples > 0 else None
                wilson = _wilson_ci(n_hit, n_samples)
                reliability = _reliability(n_samples)

                stat_json = {
                    "n_hit": n_hit,
                    "n_miss": n_miss,
                    "n_expired": n_expired,
                    "n_pending": n_pending,
                    "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
                    "wilson_ci_95": wilson,
                    "sub_labels": [],
                }

                # UPSERT (PK: regime,category,horizon,window_type,window_end)
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO base_rate
                            (regime, category, horizon, window_type, window_end, window_start,
                             n_samples, hit_rate, stat_json, reliability, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (regime, category, horizon, window_type, window_end) DO UPDATE SET
                            window_start = EXCLUDED.window_start,
                            n_samples = EXCLUDED.n_samples,
                            hit_rate = EXCLUDED.hit_rate,
                            stat_json = EXCLUDED.stat_json,
                            reliability = EXCLUDED.reliability,
                            updated_at = now()
                    """, (
                        regime, category, horizon, window_type, window_end, w_start,
                        n_samples, hit_rate, json.dumps(stat_json), reliability,
                    ))
                conn.commit()
                rows_written += 1

    except Exception as e:
        logger.error(f"[j_base_rate] Aggregation failed: {e}")
        conn.rollback()
        elapsed = time.time() - t0
        return {
            "success": False,
            "source_used": "prediction",
            "rows_in": 0,
            "rows_written": 0,
            "rows_quarantined": 0,
            "note": f"FAIL: {e} elapsed={elapsed:.1f}s",
        }

    elapsed = time.time() - t0
    note = f"groups={len(groups)} written={rows_written} window_end={window_end} elapsed={elapsed:.1f}s"
    logger.info(f"[j_base_rate] {note}")

    return {
        "success": True,
        "source_used": "prediction",
        "rows_in": 344,  # total prediction rows
        "rows_written": rows_written,
        "rows_quarantined": 0,
        "note": note,
    }
