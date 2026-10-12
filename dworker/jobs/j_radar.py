"""
j_radar - 市场雷达盘中采集（*/30 9-15 交易日）

龙虎 Radar / HomeDingPan。响应是当前列表，不是全天历史。
字段：time(unix)、status、stock_name、stockid、content、LBstatus。
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from dworker.adapters.longhu import LonghuAdapter
from dworker.core.calendar_gate import check_trade_gate
from dworker.core.degradation import JobContext, SourceError

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_radar."""
    t0 = time.time()
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    t = now.hour * 100 + now.minute
    if not (915 <= t <= 1131 or 1300 <= t <= 1501):
        note = "SKIP: outside trading hours"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    logger.info("[j_radar] Fetching market radar")
    adapter = LonghuAdapter()
    ctx = JobContext("j_radar", "D8", ["radar_event"], {})
    try:
        result = adapter.fetch(ctx, {"endpoint": "Radar", "extra_params": {}})
    except SourceError as e:
        return {"success": False, "source_used": "longhu", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": f"MISS: {e}"}

    rows = result.rows or []
    if not rows:
        return {"success": False, "source_used": "longhu", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": "MISS: no radar data"}

    written = 0
    try:
        with conn.cursor() as cur:
            for row in rows:
                unix = row.get("time")
                stockid = str(row.get("stockid") or "").strip()
                status = str(row.get("status") or "")
                if unix is None or not stockid:
                    continue
                ts = datetime.fromtimestamp(int(unix), TZ)
                event_id = f"{stockid}-{int(unix)}-{status}"
                code = _norm_code(stockid)
                extra = {
                    "stock_name": row.get("stock_name"),
                    "lb_status": row.get("LBstatus") or row.get("lb_status") or "",
                    "status": status,
                    "stockid": stockid,
                    "content2": row.get("content2"),
                }
                cur.execute("""
                    INSERT INTO radar_event
                        (ts, event_id, event_type, title, content, related_codes, extra, source, ingest_ts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'longhu', now())
                    ON CONFLICT (ts, event_id) DO UPDATE SET
                        title=EXCLUDED.title, content=EXCLUDED.content,
                        related_codes=EXCLUDED.related_codes, extra=EXCLUDED.extra,
                        source=EXCLUDED.source, ingest_ts=now()
                """, (
                    ts, event_id, status or "radar", status, row.get("content") or "",
                    json.dumps([code]) if code else None,
                    json.dumps(extra, ensure_ascii=False),
                ))
                written += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.warning(f"[j_radar] write failed: {e}")
        return {"success": False, "source_used": "longhu", "rows_in": len(rows), "rows_written": 0, "rows_quarantined": 0, "note": f"EXCEPTION: {e}"}

    elapsed = time.time() - t0
    note = f"radar written={written} elapsed={elapsed:.1f}s"
    logger.info(f"[j_radar] {note}")
    return {
        "success": written > 0,
        "source_used": "longhu",
        "rows_in": len(rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }


def _norm_code(raw: str) -> str:
    raw = raw.strip()
    if len(raw) == 6 and raw.isdigit():
        if raw.startswith("6"):
            return f"sh{raw}"
        if raw.startswith(("0", "3")):
            return f"sz{raw}"
        if raw.startswith(("4", "8")):
            return f"bj{raw}"
    return raw
