"""
j_radar - 市场雷达盘中采集（*/30 9-15 交易日）
使用 longhu 适配器（已就绪）
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml

from dworker.core.calendar_gate import check_trade_gate
from dworker.adapters.longhu import LonghuAdapter

logger = logging.getLogger(__name__)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_radar."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    # 日历门禁
    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    # 交易时段检查
    now = datetime.now()
    t = now.hour * 100 + now.minute
    if not (915 <= t <= 1131 or 1300 <= t <= 1501):
        note = "SKIP: outside trading hours"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    logger.info("[j_radar] Fetching market radar")

    # Use longhu adapter
    adapter = LonghuAdapter()
    ctx = JobContext(job_name="j_radar", target_table="radar_event", date=today)
    result = adapter.fetch(ctx, "MarketRadar")

    if not result or not result.rows:
        note = "no radar data"
        logger.info(f"[j_radar] {note}")
        return {"success": True, "source_used": "longhu", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    # Write to radar_event
    written = 0
    for row in result.rows:
        try:
            ts = row.get("ts") or f"{today}T{row.get('time', '00:00:00')}+08:00"
            event_id = str(row.get("id", ""))
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO radar_event (ts, event_id, event_type, title, content, related_codes, extra, source, ingest_ts)
                    VALUES (%s, %s, 'radar', %s, %s, %s, %s, 'longhu', now())
                    ON CONFLICT (ts, event_id) DO UPDATE SET
                        title=EXCLUDED.title, content=EXCLUDED.content, source=EXCLUDED.source
                """, (ts, event_id, row.get("status", ""), row.get("content", ""),
                      json.dumps([row.get("stock_name")]) if row.get("stock_name") else None,
                      json.dumps({"lb_status": row.get("lb_status")}, default=str)))
            conn.commit()
            written += 1
        except Exception as e:
            logger.warning(f"Failed to write radar row: {e}")
            conn.rollback()

    elapsed = time.time() - t0
    note = f"radar written={written} elapsed={elapsed:.1f}s"
    logger.info(f"[j_radar] {note}")

    return {
        "success": True,
        "source_used": "longhu",
        "rows_in": len(result.rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }


# Import JobContext at module level
from dworker.core.degradation import JobContext
