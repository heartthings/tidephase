"""交易日历。缺的日期用新浪交易日列表补上，已有行不改。"""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    import akshare as ak

    frame = ak.tool_trade_date_hist_sina()
    opens = {d.isoformat() if hasattr(d, "isoformat") else str(d)[:10] for d in frame.iloc[:, 0]}
    if not opens:
        return {"success": False, "source_used": "sina", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: sina trade calendar empty"}
    last_open = max(opens)
    with conn.cursor() as cur:
        cur.execute("SELECT max(cal_date) FROM trade_cal WHERE market = 'SSE'")
        current = cur.fetchone()[0]
    start = (current + timedelta(days=1)) if current else datetime.now(TZ).date()
    end = datetime.fromisoformat(last_open).date()
    written = 0
    if start <= end:
        with conn.cursor() as cur:
            day = start
            while day <= end:
                iso = day.isoformat()
                cur.execute("""
                    INSERT INTO trade_cal (market, cal_date, is_open, note, source)
                    VALUES ('SSE', %s, %s, 'sina_tool_trade_date_hist', 'sina')
                    ON CONFLICT (market, cal_date) DO NOTHING
                """, (iso, 1 if iso in opens else 0))
                written += cur.rowcount
                day += timedelta(days=1)
        conn.commit()
    horizon = datetime.now(TZ).date() + timedelta(days=60)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM trade_cal
            WHERE market = 'SSE' AND cal_date BETWEEN %s AND %s
        """, (datetime.now(TZ).date().isoformat(), horizon.isoformat()))
        have = cur.fetchone()[0]
    expected = 61
    ok = have >= expected
    return {"success": ok, "source_used": "sina", "rows_in": len(opens),
            "rows_written": written, "rows_quarantined": 0,
            "note": f"filled {written} days through {last_open}; next 60d {have}/{expected}"}
