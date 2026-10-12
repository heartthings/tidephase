"""
j_plate_intraday - 板块异动盘中 5 分钟（*/5 9-15 交易日）

主源与 j_sector_daily 相同：龙虎 RealRankingInfo，ZSType=7。
列语义：代码、名称、涨幅、成交额、主力净额。
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from dworker.core.calendar_gate import check_trade_gate
from dworker.jobs.j_sector_daily import _fetch_longhu

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_plate_intraday."""
    t0 = time.time()
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    t = now.hour * 100 + now.minute
    if not (915 <= t <= 1131 or 1300 <= t <= 1501):
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": "SKIP: outside trading hours"}

    logger.info("[j_plate_intraday] Fetching plate ranking")
    try:
        rows = _fetch_longhu(today)
    except Exception as e:
        logger.warning(f"[j_plate_intraday] longhu failed: {e}")
        return {"success": False, "source_used": "longhu", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": f"EXCEPTION: {e}"}

    if not rows:
        return {"success": False, "source_used": "longhu", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": "MISS: no plate rows"}

    minute_bucket = (now.minute // 5) * 5
    ts = now.replace(minute=minute_bucket, second=0, microsecond=0)
    written = 0
    try:
        with conn.cursor() as cur:
            for row in rows:
                sector_code = row.get("sector_code")
                if not sector_code:
                    continue
                cur.execute("""
                    INSERT INTO plate_movement_intraday
                        (ts, sector_code, sector_name, kind, freq, pct, close,
                         main_net_inflow, turnover, source, ingest_ts)
                    VALUES (%s, %s, %s, 'concept', '5m', %s, %s, %s, %s, 'longhu', now())
                    ON CONFLICT (ts, sector_code, freq) DO UPDATE SET
                        sector_name=EXCLUDED.sector_name, pct=EXCLUDED.pct, close=EXCLUDED.close,
                        main_net_inflow=EXCLUDED.main_net_inflow, turnover=EXCLUDED.turnover,
                        source=EXCLUDED.source, ingest_ts=now()
                """, (
                    ts, sector_code, row.get("sector_name") or "",
                    row.get("pct"), row.get("close"),
                    row.get("main_net"), row.get("turnover"),
                ))
                written += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.warning(f"[j_plate_intraday] write failed: {e}")
        return {"success": False, "source_used": "longhu", "rows_in": len(rows), "rows_written": 0, "rows_quarantined": 0, "note": f"EXCEPTION: {e}"}

    elapsed = time.time() - t0
    note = f"plates written={written} ts={ts.isoformat()} elapsed={elapsed:.1f}s"
    logger.info(f"[j_plate_intraday] {note}")
    return {
        "success": written > 0,
        "source_used": "longhu",
        "rows_in": len(rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }
