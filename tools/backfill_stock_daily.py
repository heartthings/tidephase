#!/usr/bin/env python3
"""
stock_daily 3年回填（detached 模式）
- 断点续传：progress 表记录每只股票完成状态
- 日志落盘：/home/hello/application/dev/market-datalayer/data/backfill_stock_daily.log
- 速率控制：0.5-1s 随机延迟，避免被封 IP
"""
import json, logging, os, sys, time, traceback
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import yaml

# Setup logging
LOG_DIR = Path("/home/hello/application/dev/market-datalayer/data")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "backfill_stock_daily.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backfill")

SECRETS_PATH = Path("/home/hello/application/dev/market-datalayer/configs/secrets.yaml")
START_DATE = "2023-10-08"  # 3 years ago
END_DATE = "2026-10-07"    # yesterday

def get_tsdb_conn():
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f) or {}
    db = secrets.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432,
        dbname="market_tsdb",
        user="postgres", password=db.get("duser_admin_password", ""),
    )

def ensure_progress_table(conn):
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
    conn.commit()

def get_stock_list(conn) -> list:
    """Get all A-share stock codes from akshare."""
    import akshare as ak
    try:
        df = ak.stock_info_a_code_name()
        stocks = []
        for _, row in df.iterrows():
            code = str(row.get("code", ""))
            name = str(row.get("name", ""))
            if len(code) == 6 and code.isdigit():
                # Add exchange prefix
                if code.startswith("6"):
                    full_code = f"sh{code}"
                elif code.startswith(("0", "3")):
                    full_code = f"sz{code}"
                elif code.startswith(("4", "8")):
                    full_code = f"bj{code}"
                else:
                    continue
                stocks.append((full_code, name))
        return stocks
    except Exception as e:
        logger.error(f"Failed to get stock list: {e}")
        return []

def get_pending_stocks(conn, all_stocks: list) -> list:
    """Get stocks not yet completed."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code FROM backfill_progress 
            WHERE job_name='backfill_stock_daily' AND status='done'
        """)
        done = set(r[0] for r in cur.fetchall())
    return [(code, name) for code, name in all_stocks if code not in done]

def fetch_stock_hist(code: str, start: str, end: str) -> list:
    """Fetch historical daily K-line via mootdx."""
    from mootdx.quotes import Quotes
    import random
    
    # Parse code
    symbol = code[2:]  # sh600000 -> 600000
    market = 1 if code.startswith("sh") else 0
    
    try:
        api = Quotes.factory(market='std')
        # Fetch up to 800 bars (about 3 years)
        data = api.bars(category=9, market=market, code=symbol, count=800)
        if data is None or data.empty:
            return []
        
        rows = []
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        
        for _, row in data.iterrows():
            date_str = str(row.get("datetime", ""))[:10]
            try:
                row_date = datetime.strptime(date_str, "%Y-%m-%d")
                if row_date < start_dt or row_date > end_dt:
                    continue
            except:
                continue
            
            rows.append({
                "date": date_str,
                "code": code,
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "pct": 0.0,  # mootdx doesn't provide pct directly
                "volume": float(row.get("vol", 0)),
                "amount": float(row.get("amount", 0)),
                "turnover_rate": 0.0,
            })
        return rows
    except Exception as e:
        logger.warning(f"Fetch failed for {code}: {e}")
        return []

def upsert_stock_daily(conn, rows: list):
    """Batch upsert into stock_daily."""
    if not rows:
        return 0
    
    batch = []
    for r in rows:
        batch.append((
            r["date"], r["code"], None,  # name filled later if needed
            r["open"], r["high"], r["low"], r["close"],
            r["pct"], r["volume"], r["amount"], r["turnover_rate"],
            None, None, None, None, None,  # pe_ttm, total_mv, etc.
            None, None,  # is_st, is_suspended
            "backfill", None,  # verify_source, verify_diff
            "akshare"
        ))
    
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO stock_daily (date, code, name, open, high, low, close,
                                     pct, volume, amount, turnover_rate,
                                     total_mv, circ_mv, pe_ttm, pb, adj_factor,
                                     is_st, is_suspended, verify_source, verify_diff, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (date, code) DO UPDATE SET
                open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
                pct=EXCLUDED.pct, volume=EXCLUDED.volume, amount=EXCLUDED.amount,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    conn.commit()
    return len(batch)

def update_progress(conn, code: str, status: str, rows: int):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO backfill_progress (job_name, code, status, rows_written)
            VALUES ('backfill_stock_daily', %s, %s, %s)
            ON CONFLICT (job_name, code) DO UPDATE SET
                status=EXCLUDED.status, rows_written=EXCLUDED.rows_written, updated_at=now()
        """, (code, status, rows))
    conn.commit()

def main():
    logger.info("=" * 60)
    logger.info("stock_daily 3年回填启动")
    logger.info(f"  日期范围: {START_DATE} ~ {END_DATE}")
    logger.info(f"  PID: {os.getpid()}")
    logger.info("=" * 60)
    
    import random
    
    conn = get_tsdb_conn()
    ensure_progress_table(conn)
    
    all_stocks = get_stock_list(conn)
    logger.info(f"总股票数: {len(all_stocks)}")
    
    pending = get_pending_stocks(conn, all_stocks)
    logger.info(f"待回填: {len(pending)}")
    
    total_written = 0
    total_done = len(all_stocks) - len(pending)
    failed = 0
    
    for i, (code, name) in enumerate(pending):
        try:
            rows = fetch_stock_hist(code, START_DATE, END_DATE)
            if rows:
                written = upsert_stock_daily(conn, rows)
                total_written += written
                update_progress(conn, code, "done", written)
            else:
                update_progress(conn, code, "done", 0)
            
            total_done += 1
            if (i + 1) % 50 == 0:
                logger.info(f"进度: {total_done}/{len(all_stocks)} | 本批写入: {total_written} | 失败: {failed}")
            
            # Rate limit: 1-2s random delay (mootdx is more tolerant)
            time.sleep(1.0 + random.random() * 1.0)
            
        except Exception as e:
            logger.error(f"Failed {code}: {e}")
            update_progress(conn, code, "error", 0)
            failed += 1
            time.sleep(2)  # Longer delay on error
    
    logger.info("=" * 60)
    logger.info(f"回填完成: {total_done}/{len(all_stocks)} | 写入: {total_written} | 失败: {failed}")
    logger.info("=" * 60)
    conn.close()

if __name__ == "__main__":
    main()
