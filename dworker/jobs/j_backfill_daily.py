"""补最近一个交易日还是空的表。已经有行的作业不再重跑。"""
import logging
from datetime import datetime, timedelta, timezone

from dworker.core.runner import execute_job

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
GAPS = (
    ("zt_pool", "date", "j_zt_pools"),
    ("sector_daily", "date", "j_sector_daily"),
    ("fund_flow_stock", "date", "j_fund_flow"),
    ("etf_daily", "date", "j_etf_daily"),
    ("announcements", "ann_date", "j_announcements"),
    ("block_trade", "date", "j_block_trade"),
    ("margin_daily", "date", "j_margin_daily"),
    ("index_minute", "ts::date", "j_index_minute"),
)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT max(cal_date) FROM trade_cal
            WHERE market = 'SSE' AND is_open = 1 AND cal_date < %s
        """, (datetime.now(TZ).date().isoformat(),))
        day = cur.fetchone()[0]
    if day is None:
        return {"success": False, "source_used": "none", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: no prior open day"}
    day_s = day.isoformat()
    filled = []
    skipped = []
    for table, col, job in GAPS:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {table} WHERE {col} = %s", (day,))
            n = cur.fetchone()[0]
        if n > 0:
            skipped.append(job)
            continue
        ok, note = execute_job(job, trigger="backfill", extra_params={"date": day_s})
        filled.append(f"{job}:{'OK' if ok else 'FAIL'}")
        logger.info(f"[j_backfill_daily] {job} {note}")
    return {"success": True, "source_used": "sql", "rows_in": len(GAPS),
            "rows_written": len(filled), "rows_quarantined": 0,
            "note": f"day={day_s} filled={filled or 'none'} already={len(skipped)}"}
