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

LOG_DIR = Path(__file__).resolve().parent.parent / "data"
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

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

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

def fetch_emotion(secrets, st: int = 250) -> list:
    """Fetch CGL/YLL series from longhu Emotion endpoint.

    B4 修复(2026-10-10): 参数按 Java 源码逐参复刻（督军实测验证）。
    依据: SpeculativePerformanceDataParamBuilder.java:71-96
          TradingDashboardCrawler.java:329-336
    正确请求: st=250(源端上限), index=0, apiv=w39, VerSion=5.18.0.2
    """
    longhu = secrets.get("longhu", {})
    hosts = longhu.get("hosts", {})
    apphis = hosts.get("apphis", "")
    device_id = longhu.get("emotion_device_id", "")

    if not apphis or not device_id:
        logger.error("Missing longhu Emotion credentials (apphis host / emotion_device_id)")
        return []

    # B4: 固化正确参数
    payload = {
        "a": "GetMoneyDate",
        "c": "Emotion",
        "st": str(st),
        "index": "0",
        "apiv": "w39",
        "PhoneOSNew": "1",
        "VerSion": "5.18.0.2",
        "DeviceID": device_id,
    }
    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; SM-G9810 Build/TP1A.220624.014)",
        "Host": "apphis.longhuvip.com",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    try:
        resp = requests.post(apphis, data=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # B4: 只认 ZY 键
        zy_list = data.get("ZY")
        if not zy_list or not isinstance(zy_list, list):
            logger.warning(
                f"Emotion 返回空载荷 keys={list(data.keys())} errcode={data.get('errcode')}"
            )
            return []

        rows = []
        for item in zy_list:
            if not isinstance(item, dict):
                continue
            day = item.get("Day", "")
            if not day:
                continue
            rows.append({
                "date": day,
                "dbcgl": float(item["CGL"]) if item.get("CGL") else None,
                "dbyll": float(item["YLL"]) if item.get("YLL") else None,
            })
        logger.info(f"Fetched {len(rows)} days from Emotion endpoint (st={st})")
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
