#!/usr/bin/env python3
"""
历史日K全量回填（1年，用于涨停形态回测）

数据源: 新浪 CN_MarketDataService.getKLineData (scale=240 日线, 不复权)
返回: day/open/high/low/close/volume(股)  + ma 指标

为什么选新浪:
  - eastmoney push2his 已被本机 IP 限流(RemoteDisconnected), mootdx 服务器 No route
  - 新浪不复权数据可稳定拿 datalen=260(约1年), 单次返回全量
处理口径:
  - volume 单位 股 -> 手 (除以100, 与 stock_daily 现有东财/akshare 口径一致)
  - pct 自行计算: (close/prev_close - 1)*100 (不复权, 除权日会在特征层识别排除)
  - amount/turnover_rate 新浪无, 留 NULL; 缩量判断在回测用 volume 比值

断点续传: backfill_progress(job_name='backfill_history_daily')
限速: 0.3~0.6s 随机间隔
"""
import logging
import os
import random
import time
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
        logging.FileHandler(LOG_DIR / "backfill_history_daily.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backfill_history")

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"
JOB_NAME = "backfill_history_daily"

KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
DATALEN = 260  # 约1年交易日
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}


def get_conn():
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f) or {}
    db = secrets.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="postgres", password=db.get("duser_admin_password", ""),
    )


def ensure_progress(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS backfill_progress (
                job_name text NOT NULL,
                code text NOT NULL,
                status text DEFAULT 'pending',
                rows_written int DEFAULT 0,
                updated_at timestamptz DEFAULT now(),
                PRIMARY KEY (job_name, code)
            )
        """)


def get_code_list(conn) -> list:
    """从现有 stock_daily 取全量 code, 排除北交所 bj."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT code FROM stock_daily
            WHERE code LIKE 'sh%%' OR code LIKE 'sz%%'
            ORDER BY code
        """)
        return [r[0] for r in cur.fetchall()]


def fetch_kline(session, code: str) -> list:
    """拉取 code 约1年不复权日K, 返回 [{date,open,high,low,close,volume,pct}]"""
    last_err = None
    for attempt in range(4):
        try:
            r = session.get(KLINE_URL, params={
                "symbol": code, "scale": 240, "datalen": DATALEN,
            }, timeout=25, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                return []
            rows = []
            prev_close = None
            for item in data:
                try:
                    close = float(item["close"])
                    pct = None
                    if prev_close and prev_close > 0:
                        pct = round((close / prev_close - 1) * 100, 4)
                    rows.append({
                        "date": item["day"],
                        "code": code,
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": close,
                        "volume": float(item["volume"]) / 100.0,  # 股 -> 手
                        "pct": pct,
                    })
                    prev_close = close
                except (ValueError, KeyError, TypeError):
                    continue
            return rows
        except Exception as e:
            last_err = e
            time.sleep(1.0 + attempt * 1.5)
    raise last_err


def upsert(conn, rows: list) -> int:
    if not rows:
        return 0
    batch = [(r["date"], r["code"], r["open"], r["high"], r["low"], r["close"],
              r["pct"], r["volume"]) for r in rows]
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO stock_daily (date, code, open, high, low, close,
                                     pct, volume, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'backfill_sina',now())
            ON CONFLICT (date, code) DO UPDATE SET
                open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                close=EXCLUDED.close, pct=EXCLUDED.pct, volume=EXCLUDED.volume,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    conn.commit()
    return len(batch)


def mark_progress(conn, code: str, status: str, rows: int):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO backfill_progress (job_name, code, status, rows_written)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (job_name, code) DO UPDATE SET
                status=EXCLUDED.status, rows_written=EXCLUDED.rows_written, updated_at=now()
        """, (JOB_NAME, code, status, rows))
    conn.commit()


def main():
    logger.info("=" * 60)
    logger.info(f"历史日K回填启动 (新浪, datalen={DATALEN})  pid={os.getpid()}")
    logger.info("=" * 60)

    conn = get_conn()
    ensure_progress(conn)
    codes = get_code_list(conn)
    logger.info(f"待回填股票数: {len(codes)}")

    with conn.cursor() as cur:
        cur.execute("SELECT code FROM backfill_progress WHERE job_name=%s AND status='done'", (JOB_NAME,))
        done = {r[0] for r in cur.fetchall()}
    todo = [c for c in codes if c not in done]
    logger.info(f"已完成 {len(done)}, 剩余 {len(todo)}")

    session = requests.Session()
    total_written = 0
    failed = 0

    for i, code in enumerate(todo):
        try:
            rows = fetch_kline(session, code)
            w = upsert(conn, rows)
            total_written += w
            mark_progress(conn, code, "done", w)
        except Exception as e:
            failed += 1
            mark_progress(conn, code, "error", 0)
            if failed <= 20:
                logger.warning(f"failed {code}: {type(e).__name__}")
        if (i + 1) % 100 == 0:
            logger.info(f"进度 {i+1}/{len(todo)} 写入 {total_written} 失败 {failed}")
        time.sleep(0.3 + random.random() * 0.3)

    logger.info("=" * 60)
    logger.info(f"完成: 处理 {len(todo)} | 写入 {total_written} | 失败 {failed}")
    logger.info("=" * 60)
    conn.close()


if __name__ == "__main__":
    main()