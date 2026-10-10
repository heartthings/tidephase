"""
j_sentiment_calc - 龙虎 Emotion 情绪日度
数据源: 龙虎 GetMoneyDate 端点（CGL/YLL 涨跌停封板率等）
输出: sentiment_daily 表
复用: tools/backfill_sentiment_daily.py 取数逻辑

频率: 15:40 每日（依赖 j_zt_pools + j_stock_daily）
"""
import logging
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
import yaml

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)

SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "secrets.yaml"


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def fetch_emotion(secrets) -> list:
    """Fetch 30-day CGL/YLL series from longhu Emotion endpoint."""
    longhu = secrets.get("longhu", {})
    hosts = longhu.get("hosts", {})
    apphis = hosts.get("apphis", "")
    device_id = longhu.get("emotion_device_id", "")

    if not apphis or not device_id:
        logger.error("Missing longhu Emotion credentials")
        return []

    payload = {
        "app": "app_cjh",
        "DeviceId": device_id,
        "version": "64",
        "c": "Emotion",
        "a": "GetMoneyDate",
    }

    try:
        resp = requests.post(apphis, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        zy_list = data.get("ZY", [])
        rows = []
        for item in zy_list:
            date_str = item.get("Day", "")
            cgl = float(item.get("CGL", 0)) if item.get("CGL") else None
            yll = float(item.get("YLL", 0)) if item.get("YLL") else None
            if date_str:
                rows.append({
                    "date": date_str,
                    "dbcgl": cgl,
                    "dbyll": yll,
                })
        logger.info(f"Fetched {len(rows)} days from Emotion endpoint")
        return rows
    except Exception as e:
        logger.error(f"Emotion fetch failed: {e}")
        return []


def upsert_sentiment_daily(conn, rows: list) -> int:
    """Upsert into sentiment_daily."""
    if not rows:
        return 0

    written = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO sentiment_daily (date, dbcgl, dbyll, source, ingest_ts)
                VALUES (%s, %s, %s, 'longhu-emotion', now())
                ON CONFLICT (date) DO UPDATE SET
                    dbcgl = COALESCE(EXCLUDED.dbcgl, sentiment_daily.dbcgl),
                    dbyll = COALESCE(EXCLUDED.dbyll, sentiment_daily.dbyll),
                    source = 'longhu-emotion',
                    ingest_ts = now()
            """, (r["date"], r["dbcgl"], r["dbyll"]))
            written += 1
    conn.commit()
    return written


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_sentiment_calc."""
    t0 = time.time()

    # 日历门禁
    today = datetime.now().strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_sentiment_calc] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": note}

    secrets = load_secrets()

    # Fetch Emotion data
    rows = fetch_emotion(secrets)
    if not rows:
        elapsed = time.time() - t0
        return {"success": False, "source_used": "longhu",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
                "note": f"FAIL: no emotion data, elapsed={elapsed:.1f}s"}

    # Upsert
    written = upsert_sentiment_daily(conn, rows)

    # Verify
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), min(date), max(date) FROM sentiment_daily")
        cnt, min_d, max_d = cur.fetchone()

    elapsed = time.time() - t0
    note = f"written={written} total={cnt} ({min_d}~{max_d}) elapsed={elapsed:.1f}s"
    logger.info(f"[j_sentiment_calc] {note}")

    return {
        "success": True,
        "source_used": "longhu",
        "rows_in": len(rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }
