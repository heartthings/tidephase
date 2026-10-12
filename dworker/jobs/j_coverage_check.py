"""覆盖检查。上一交易日的关键表有没有行。07:15 跑，当天收盘数据还没到，不把今天算进去。缺表记 FAIL。"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
CHECKS = (
    ("index_daily", "date"),
    ("stock_daily", "date"),
    ("zt_pool", "date"),
    ("sector_daily", "date"),
    ("fund_flow_stock", "date"),
)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT max(cal_date) FROM trade_cal
            WHERE market = 'SSE' AND is_open = 1 AND cal_date < %s
        """, (datetime.now(TZ).date().isoformat(),))
        day = cur.fetchone()[0]
        parts = []
        missing = []
        for table, col in CHECKS:
            cur.execute(f"SELECT count(*) FROM {table} WHERE {col} = %s", (day,))
            n = cur.fetchone()[0]
            parts.append(f"{table}={n}")
            if n == 0:
                missing.append(table)
    note = f"last_open={day} " + " ".join(parts)
    if missing:
        return {"success": False, "source_used": "sql", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": note + " MISS " + ",".join(missing)}
    return {"success": True, "source_used": "sql", "rows_in": len(CHECKS),
            "rows_written": 0, "rows_quarantined": 0, "note": note}
