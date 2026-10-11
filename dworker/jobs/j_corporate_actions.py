"""分红实施公告。东财按公告日过滤。业绩预告和解禁不在这份报表里，备注里写明。"""
import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        rows = _fetch(trade_date)
    except Exception as e:
        return {"success": False, "source_used": "eastmoney", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": f"MISS: {e}"}
    try:
        raw_archiver.archive("D5", "j_corporate_actions", "eastmoney", rows[:20])
    except Exception as e:
        logger.warning(f"[j_corporate_actions] archive {e}")
    n = _write(conn, rows)
    return {"success": True, "source_used": "eastmoney",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"announce_date={trade_date} dividends={n}; earnings_calendar and lockup not in this report"}


def _fetch(trade_date: str) -> list:
    resp = requests.get(URL, params={
        "reportName": "RPT_SHAREBONUS_DET", "columns": "ALL",
        "pageSize": 500, "pageNumber": 1,
        "filter": f"(NOTICE_DATE='{trade_date}')",
    }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=30)
    data = (resp.json().get("result") or {}).get("data") or []
    rows = []
    for item in data:
        notice = str(item.get("NOTICE_DATE") or "")[:10]
        period = str(item.get("REPORT_DATE") or "")[:10]
        progress = (item.get("ASSIGN_PROGRESS") or "plan").strip() or "plan"
        if notice != trade_date or not period:
            continue
        yld = item.get("DIVIDENT_RATIO")
        rows.append({
            "code": _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE")),
            "report_period": period,
            "announce_date": notice,
            "plan": item.get("IMPL_PLAN_PROFILE"),
            "cash_div_tax": item.get("PRETAX_BONUS_RMB"),
            "stock_div": item.get("BONUS_RATIO"),
            "transfer": item.get("IT_RATIO"),
            "record_date": _day(item.get("EQUITY_RECORD_DATE")),
            "ex_date": _day(item.get("EX_DIVIDEND_DATE")),
            "div_yield": None if yld is None else float(yld) * 100,
            "progress": progress,
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO dividend
                    (code, report_period, announce_date, plan, cash_div_tax, stock_div, transfer,
                     record_date, ex_date, div_yield, progress, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (code, report_period, announce_date, progress) DO UPDATE SET
                    plan=EXCLUDED.plan, cash_div_tax=EXCLUDED.cash_div_tax, stock_div=EXCLUDED.stock_div,
                    transfer=EXCLUDED.transfer, record_date=EXCLUDED.record_date, ex_date=EXCLUDED.ex_date,
                    div_yield=EXCLUDED.div_yield, ingest_ts=now()
            """, (r["code"], r["report_period"], r["announce_date"], r["plan"], r["cash_div_tax"],
                  r["stock_div"], r["transfer"], r["record_date"], r["ex_date"], r["div_yield"], r["progress"]))
            n += 1
    conn.commit()
    return n


def _prefix(code, secucode) -> str:
    suffix = str(secucode or "").split(".")[-1].upper()
    c = str(code or "").zfill(6)
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix, "") + c


def _day(v):
    if not v:
        return None
    return str(v)[:10]
