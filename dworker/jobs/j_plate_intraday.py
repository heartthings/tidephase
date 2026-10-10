"""
j_plate_intraday - 板块异动盘中5min降采样（0 */5 9-15 交易日）
梁总 10-10 批准降采样

从 longhu DailyLimitResumption 获取板块数据，5min 粒度写入 plate_movement_intraday
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml

from dworker.core.calendar_gate import check_trade_gate
from dworker.adapters.longhu import LonghuAdapter
from dworker.core.degradation import JobContext

logger = logging.getLogger(__name__)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_plate_intraday."""
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    # 日历门禁
    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    # 交易时段检查
    now = datetime.now()
    t = now.hour * 100 + now.minute
    if not (915 <= t <= 1131 or 1300 <= t <= 1501):
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": "SKIP: outside trading hours"}

    logger.info("[j_plate_intraday] Fetching plate movements")

    # Use longhu adapter for plate data
    adapter = LonghuAdapter()
    ctx = JobContext(job_name="j_plate_intraday", target_table="plate_movement_intraday", date=today)
    result = adapter.fetch(ctx, "DailyLimitResumption")

    if not result or not result.rows:
        note = "no plate data"
        return {"success": True, "source_used": "longhu", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    # 5min 降采样时间戳
    minute_bucket = (now.minute // 5) * 5
    ts = f"{today}T{now.hour:02d}:{minute_bucket:02d}:00+08:00"

    # Write to plate_movement_intraday
    written = 0
    for row in result.rows:
        try:
            sector_code = row.get("code") or row.get("plate_code")
            if not sector_code:
                continue
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO plate_movement_intraday (ts, sector_code, sector_name, kind, freq, pct, close,
                                                         main_net_inflow, turnover, up_cnt, down_cnt, source, ingest_ts)
                    VALUES (%s, %s, %s, 'concept', '5m', %s, %s, %s, %s, %s, %s, 'longhu', now())
                    ON CONFLICT (ts, sector_code, freq) DO UPDATE SET
                        sector_name=EXCLUDED.sector_name, pct=EXCLUDED.pct,
                        main_net_inflow=EXCLUDED.main_net_inflow, turnover=EXCLUDED.turnover,
                        source=EXCLUDED.source, ingest_ts=now()
                """, (ts, sector_code, row.get("name", ""),
                      row.get("growth_rate") or row.get("pct"),
                      row.get("close"), row.get("large_force") or row.get("main_net_inflow"),
                      row.get("cje") or row.get("turnover"),
                      row.get("up_cnt"), row.get("down_cnt")))
            conn.commit()
            written += 1
        except Exception as e:
            logger.warning(f"Failed to write plate row: {e}")
            conn.rollback()

    elapsed = time.time() - t0
    note = f"plates written={written} ts={ts} elapsed={elapsed:.1f}s"
    logger.info(f"[j_plate_intraday] {note}")

    return {
        "success": True,
        "source_used": "longhu",
        "rows_in": len(result.rows),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }
