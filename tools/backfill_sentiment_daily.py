#!/usr/bin/env python3
"""
sentiment_daily 30日回填（龙虎 Emotion 端点）
- 仅限 Emotion 端点，约 30 次请求，≤1rps
- 日志落盘
"""
import json, logging, os, sys, time
from datetime import datetime
from pathlib import Path

import psycopg2
import requests
import yaml

LOG_DIR = Path("/home/hello/application/dev/market-datalayer/data")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "backfill_sentiment_daily.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backfill_sentiment")

SECRETS_PATH = Path("/home/hello/application/dev/market-datalayer/configs/secrets.yaml")

def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}

def get_tsdb_conn(secrets):
    db = secrets.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432,
        dbname="market_tsdb",
        user="postgres", password=db.get("duser_admin_password", ""),
    )

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

def upsert_sentiment_daily(conn, rows: list):
    """Upsert into sentiment_daily."""
    if not rows:
        return 0
    
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO sentiment_daily (date, dbcgl, dbyll, source, ingest_ts)
                VALUES (%s, %s, %s, 'longhu-emotion', now())
                ON CONFLICT (date) DO UPDATE SET
                    dbcgl = EXCLUDED.dbcgl,
                    dbyll = EXCLUDED.dbyll,
                    source = EXCLUDED.source,
                    ingest_ts = now()
            """, (r["date"], r["dbcgl"], r["dbyll"]))
    conn.commit()
    return len(rows)

def main():
    logger.info("=" * 60)
    logger.info("sentiment_daily 30日回填启动（龙虎 Emotion）")
    logger.info(f"  PID: {os.getpid()}")
    logger.info("=" * 60)
    
    secrets = load_secrets()
    conn = get_tsdb_conn(secrets)
    
    # Fetch Emotion data
    rows = fetch_emotion(secrets)
    if not rows:
        logger.error("No data fetched, exiting")
        conn.close()
        return
    
    # Show date range
    dates = [r["date"] for r in rows if r["date"]]
    if dates:
        logger.info(f"日期范围: {min(dates)} ~ {max(dates)}")
    
    # Upsert
    written = upsert_sentiment_daily(conn, rows)
    logger.info(f"写入 sentiment_daily: {written} 行")
    
    # Verify
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), min(date), max(date) FROM sentiment_daily")
        cnt, min_d, max_d = cur.fetchone()
    logger.info(f"sentiment_daily 总计: {cnt} 行 ({min_d} ~ {max_d})")
    
    conn.close()
    logger.info("完成")

if __name__ == "__main__":
    main()
