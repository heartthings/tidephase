"""
j_instrument_master - 证券主档日更
数据源: akshare (stock_info_a_code_name) + eastmoney
输出: instrument_master 表

频率: 08:00 每日
"""
import logging
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import yaml

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)

SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "secrets.yaml"


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def fetch_akshare_stocks() -> list:
    """从 akshare 获取全市场 A 股代码+名称."""
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        rows = []
        for _, r in df.iterrows():
            code = str(r.get('code', '')).zfill(6)
            name = str(r.get('name', ''))
            if not code:
                continue
            # 判断市场
            if code.startswith(('60', '68')):
                market = 'SSE'
            elif code.startswith(('00', '30')):
                market = 'SZSE'
            elif code.startswith(('4', '8')):
                market = 'BSE'
            else:
                market = 'OTHER'
            # 判断板块
            if code.startswith('68'):
                board = 'STAR'
            elif code.startswith('30'):
                board = 'ChiNext'
            elif code.startswith('00'):
                board = 'Main'
            elif code.startswith('60'):
                board = 'Main'
            else:
                board = 'OTHER'
            rows.append({
                'code': code,
                'name': name,
                'market': market,
                'inst_type': 'stock',
                'board': board,
            })
        logger.info(f"akshare fetched {len(rows)} stocks")
        return rows
    except Exception as e:
        logger.error(f"akshare fetch failed: {e}")
        return []


def upsert_instrument_master(conn, rows: list) -> int:
    """Upsert into instrument_master."""
    if not rows:
        return 0

    written = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO instrument_master (code, name, market, inst_type, board, status, source, ingest_ts)
                VALUES (%s, %s, %s, %s, %s, 'active', 'akshare', now())
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    market = EXCLUDED.market,
                    board = EXCLUDED.board,
                    status = 'active',
                    source = 'akshare',
                    ingest_ts = now()
            """, (r['code'], r['name'], r['market'], r['inst_type'], r['board']))
            written += 1
    conn.commit()
    return written


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_instrument_master."""
    t0 = time.time()

    # Fetch stocks
    rows = fetch_akshare_stocks()
    if not rows:
        elapsed = time.time() - t0
        return {"success": False, "source_used": "akshare",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
                "note": f"FAIL: no data from akshare, elapsed={elapsed:.1f}s"}

    # Upsert
    written = upsert_instrument_master(conn, rows)

    # Verify
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM instrument_master WHERE status='active'")
        total = cur.fetchone()[0]

    elapsed = time.time() - t0
    note = f"written={written} total_active={total} elapsed={elapsed:.1f}s"
    logger.info(f"[j_instrument_master] {note}")

    return {
        "success": True,
        "source_used": "akshare",
        "rows_in": len(rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }
