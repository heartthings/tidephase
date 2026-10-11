"""当天采集日志汇总，不写业务表。"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    today = datetime.now(TZ).date().isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT status, count(*) FROM ingest_log
            WHERE ts >= %s::date
            GROUP BY status ORDER BY status
        """, (today,))
        rows = cur.fetchall()
    summary = " ".join(f"{s}={n}" for s, n in rows) or "no runs"
    return {"success": True, "source_used": "ingest_log", "rows_in": sum(n for _, n in rows),
            "rows_written": 0, "rows_quarantined": 0,
            "note": f"date={today} {summary}"}
