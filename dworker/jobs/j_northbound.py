"""北向日频。已退役。

2024-08-19 起交易所不再公布北向买入/卖出/净买额（上证发〔2024〕106 号）。
东财、同花顺日频净买额随之停更。日频只剩成交总额与前十大活跃股，季度才有持股。
观势首板/二板与情绪简报不再使用北向净买额；本作业只记 RETIRED，不再请求接口。
"""
import logging
from datetime import datetime, timedelta, timezone

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run(
                "j_northbound", "D4", "northbound_daily", "none", "SKIP",
                note=note, trigger=trigger,
            )
        except Exception:
            pass
        return {
            "success": True, "already_logged": True, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
        }

    note = (
        f"RETIRED: northbound buy/sell/net unpublished since 2024-08-19 "
        f"(exchange disclosure change); not used in predict_limitup; date={trade_date}"
    )
    try:
        ingest_logger.log_run(
            "j_northbound", "D4", "northbound_daily", "none", "SKIP",
            note=note, trigger=trigger,
        )
    except Exception:
        pass
    logger.info("[j_northbound] %s", note)
    return {
        "success": True, "already_logged": True, "source_used": "none",
        "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
    }
