"""
calendar_gate - 交易日历门禁
休市/非交易日作业写 ingest_log status='SKIP' 后 return，禁止落业务表。
§Z7 修复：stock_daily 2026-10-10（周六）5224 行误写根因。
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def check_trade_gate(conn, market: str = "SSE", check_date: str = None) -> dict:
    """
    检查 trade_cal 判断当日是否可写入业务表。

    Returns:
        {"allowed": True}  — 交易日，可写入
        {"allowed": False, "reason": str}  — 休市/非交易日，禁止写入
    """
    if check_date is None:
        check_date = datetime.now().strftime("%Y-%m-%d")

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_open, note FROM trade_cal WHERE market = %s AND cal_date = %s",
                (market, check_date)
            )
            row = cur.fetchone()
    except Exception as e:
        # 查不到日历时保守放行但记 warn，避免阻断所有采集
        logger.warning(f"[calendar_gate] trade_cal query failed: {e}")
        return {"allowed": True, "reason": "trade_cal query failed, permissive fallback"}

    if row is None:
        # 日历中没有该日期 → 视为非交易日
        logger.warning(f"[calendar_gate] No trade_cal entry for market={market} date={check_date}, treating as non-trading day")
        return {"allowed": False, "reason": f"no trade_cal entry for {market}/{check_date}"}

    is_open = int(row[0])
    if is_open == 0:
        note = row[1] or ""
        return {"allowed": False, "reason": f"market closed on {check_date} ({note})"}

    return {"allowed": True}
