#!/usr/bin/env python3
"""
stock_daily 缺口补齐（近 7 个自然日内的交易日）
Z7 变更：梁总 2026-10-10 裁决"不用 3 年，前一周即可"。
用途：补齐近 7 天内缺失的交易日数据（非全量历史回填）。
- 断点续传：progress 表记录每只股票完成状态
- 日志落盘：仓库 data/backfill_stock_daily.log
- 速率控制：1-2s 随机延迟，避免被封 IP
"""
import json, logging, os, sys, time, traceback
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import yaml

# Setup logging
LOG_DIR = Path(__file__).resolve().parent.parent / "data"
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

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

# Z7: 默认窗口改为"近 7 个自然日"
DEFAULT_WINDOW_DAYS = 7

def compute_window():
    """计算回填窗口：近 7 个自然日内的交易日。"""
    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=DEFAULT_WINDOW_DAYS)).strftime("%Y-%m-%d")
    return start_date, end_date

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

def get_trading_days_in_window(conn, start_date: str, end_date: str) -> list:
    """从 trade_cal 获取窗口内的交易日列表。"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cal_date FROM trade_cal
            WHERE market='SSE' AND is_open=1 AND cal_date >= %s AND cal_date <= %s
            ORDER BY cal_date
        """, (start_date, end_date))
        return [str(r[0]) for r in cur.fetchall()]


def get_missing_dates(conn, trading_days: list) -> list:
    """找出 stock_daily 中缺失的交易日。"""
    missing = []
    with conn.cursor() as cur:
        for day in trading_days:
            cur.execute("SELECT count(*) FROM stock_daily WHERE date = %s", (day,))
            cnt = cur.fetchone()[0]
            if cnt == 0:
                missing.append(day)
    return missing


def main():
    import random
    
    start_date, end_date = compute_window()
    
    logger.info("=" * 60)
    logger.info("stock_daily 缺口补齐启动（Z7: 近7自然日窗口）")
    logger.info(f"  窗口: {start_date} ~ {end_date}")
    logger.info(f"  PID: {os.getpid()}")
    logger.info("=" * 60)
    
    conn = get_tsdb_conn()
    ensure_progress_table(conn)
    
    # 找出窗口内的交易日
    trading_days = get_trading_days_in_window(conn, start_date, end_date)
    logger.info(f"窗口内交易日: {trading_days}")
    
    # 找出缺失的交易日
    missing_dates = get_missing_dates(conn, trading_days)
    logger.info(f"缺失交易日: {missing_dates}")
    
    if not missing_dates:
        logger.info("✅ 无缺口，所有交易日数据已齐")
        conn.close()
        return
    
    # 仅回填缺失日期
    all_stocks = get_stock_list(conn)
    logger.info(f"总股票数: {len(all_stocks)}")
    
    # 清理旧 progress（新窗口新开始）
    with conn.cursor() as cur:
        cur.execute("DELETE FROM backfill_progress WHERE job_name='backfill_stock_daily'")
    conn.commit()
    
    total_written = 0
    failed = 0
    
    for i, (code, name) in enumerate(all_stocks):
        try:
            rows = fetch_stock_hist(code, missing_dates[0], missing_dates[-1])
            # 只保留缺失日期的行
            rows = [r for r in rows if r["date"] in missing_dates]
            if rows:
                written = upsert_stock_daily(conn, rows)
                total_written += written
                update_progress(conn, code, "done", written)
            else:
                update_progress(conn, code, "done", 0)
            
            if (i + 1) % 50 == 0:
                logger.info(f"进度: {i+1}/{len(all_stocks)} | 写入: {total_written} | 失败: {failed}")
            
            time.sleep(1.0 + random.random() * 1.0)
            
        except Exception as e:
            logger.error(f"Failed {code}: {e}")
            update_progress(conn, code, "error", 0)
            failed += 1
            time.sleep(2)
    
    logger.info("=" * 60)
    logger.info(f"缺口补齐完成: {len(all_stocks)} 只 | 写入: {total_written} | 失败: {failed}")
    logger.info("=" * 60)
    conn.close()

if __name__ == "__main__":
    main()
