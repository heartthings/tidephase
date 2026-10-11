"""期权。新浪合约行情和东财报表目前都拿不到合约。记 MISS，不编合约。"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_option_daily", "D11", "option_contracts", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}
    note = (
        f"MISS: no option contracts for {trade_date}; "
        f"sina option board empty, eastmoney has no option report"
    )
    try:
        names = requests.get(
            "https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getStockName",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=15,
        ).json()
        cates = ((names.get("result") or {}).get("data") or {}).get("cateList") or []
        if cates:
            note += f"; sina cateList={len(cates)} but no contract ids"
    except Exception as e:
        logger.warning(f"[j_option_daily] {e}")
    try:
        ingest_logger.log_run("j_option_daily", "D11", "option_contracts", "sina", "MISS", note=note, trigger=trigger)
    except Exception:
        pass
    return {"success": True, "already_logged": True, "source_used": "sina",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}
