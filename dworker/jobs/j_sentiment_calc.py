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


def fetch_emotion(secrets, st: int = 250) -> list:
    """Fetch CGL/YLL series from longhu Emotion endpoint.

    B4 修复(2026-10-10): 参数按 Java 源码逐参复刻（督军实测验证）。
    依据: SpeculativePerformanceDataParamBuilder.java:71-96
          TradingDashboardCrawler.java:329-336
    正确请求: st=250(源端上限), index=0, apiv=w39, VerSion=5.18.0.2
    响应: {"ZY":[{"CGL":"76.19","YLL":"2.10","Day":"2026-10-09"},...], "errcode":"0"}
    解析: ZY[i].Day/CGL/YLL → sentiment_daily(date, dbcgl, dbyll)
    """
    longhu = secrets.get("longhu", {})
    hosts = longhu.get("hosts", {})
    apphis = hosts.get("apphis", "")
    device_id = longhu.get("emotion_device_id", "")

    if not apphis or not device_id:
        logger.error("Missing longhu Emotion credentials (apphis host / emotion_device_id)")
        return []

    # B4: 固化正确参数（不再用错误的 app/DeviceId/version）
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

        # B4: 只认 ZY 键，不再兜底顶层 list（那是请求参数不全的误判）
        zy_list = data.get("ZY")
        if not zy_list or not isinstance(zy_list, list):
            logger.warning(
                f"[j_sentiment_calc] Emotion 返回空载荷 keys={list(data.keys())} "
                f"errcode={data.get('errcode')}。请求参数可能变更。"
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
        # B4: 空载荷 → 写 MISS 行 + 告警（不再误判为"token 过期/源端空"）
        elapsed = time.time() - t0
        note = f"MISS: Emotion 端点返回空载荷（请求参数可能变更），elapsed={elapsed:.1f}s"
        logger.warning(f"[j_sentiment_calc] {note}")
        try:
            ingest_logger.log_run(
                "j_sentiment_calc", "D3", "sentiment_daily", "longhu", "MISS",
                rows_in=0, rows_written=0, rows_quarantined=0,
                note=note, trigger=trigger,
            )
        except Exception as e:
            logger.warning(f"[j_sentiment_calc] ingest_log MISS failed: {e}")
        return {"success": False, "source_used": "longhu",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
                "note": note}

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
