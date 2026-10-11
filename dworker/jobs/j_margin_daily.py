"""两融。东财全市场日汇总 + 标的明细。源未发布该日则 MISS，不拿更早一天顶上。"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_margin_daily", "D4", "margin_daily", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    market = _market(trade_date)
    stocks = _stocks(trade_date) if market else []
    if not market:
        return {"success": False, "source_used": "eastmoney", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: margin summary not published for {trade_date}"}
    try:
        raw_archiver.archive("D4", "j_margin_daily", "eastmoney", {"market": market, "stocks": len(stocks)})
    except Exception as e:
        logger.warning(f"[j_margin_daily] archive {e}")
    written = _write(conn, trade_date, market, stocks)
    return {"success": written > 0, "source_used": "eastmoney",
            "rows_in": 1 + len(stocks), "rows_written": written, "rows_quarantined": 0,
            "note": f"date={trade_date} market=1 stocks={len(stocks)}"}


def _get(report, page, sort_col, filt):
    resp = requests.get(URL, params={
        "reportName": report, "columns": "ALL", "pageSize": 500, "pageNumber": page,
        "sortColumns": sort_col, "sortTypes": "1", "filter": filt,
    }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=30)
    return (resp.json().get("result") or {}).get("data") or []


def _market(trade_date: str) -> dict:
    try:
        data = _get("RPTA_RZRQ_LSHJ", 1, "DIM_DATE", f"(DIM_DATE='{trade_date}')")
    except Exception as e:
        logger.warning(f"[j_margin_daily] market: {e}")
        return {}
    if not data:
        return {}
    row = data[0]
    if not str(row.get("DIM_DATE") or "").startswith(trade_date):
        return {}
    buy = row.get("RZMRE")
    repay = row.get("RZCHE")
    net = None
    if buy is not None and repay is not None:
        net = float(buy) - float(repay)
    return {
        "margin_bal": row.get("RZYE"),
        "margin_buy": buy,
        "margin_repay": repay,
        "net_buy": net,
        "short_bal": row.get("RQYE"),
        "short_vol": row.get("RQYL"),
    }


def _stocks(trade_date: str) -> list:
    rows = []
    for page in range(1, 20):
        try:
            data = _get("RPTA_WEB_RZRQ_GGMX", page, "SCODE", f"(DATE='{trade_date}')")
        except Exception as e:
            logger.warning(f"[j_margin_daily] stock page {page}: {e}")
            break
        if not data:
            break
        for item in data:
            if not str(item.get("DATE") or "").startswith(trade_date):
                continue
            buy = item.get("RZMRE")
            repay = item.get("RZCHE")
            rows.append({
                "code": _prefix(item.get("SCODE"), item.get("SECUCODE")),
                "margin_bal": item.get("RZYE"),
                "margin_buy": buy,
                "margin_repay": repay,
                "short_bal": item.get("RQYE"),
                "short_vol": item.get("RQYL"),
                "net_buy": None if buy is None or repay is None else float(buy) - float(repay),
            })
        if len(data) < 500:
            break
        time.sleep(0.1)
    return rows


def _write(conn, trade_date: str, market: dict, stocks: list) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO margin_daily
                (date, margin_bal, margin_buy, margin_repay, net_buy, short_bal, short_vol, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'eastmoney')
            ON CONFLICT (date) DO UPDATE SET
                margin_bal=EXCLUDED.margin_bal, margin_buy=EXCLUDED.margin_buy,
                margin_repay=EXCLUDED.margin_repay, net_buy=EXCLUDED.net_buy,
                short_bal=EXCLUDED.short_bal, short_vol=EXCLUDED.short_vol, ingest_ts=now()
        """, (trade_date, market["margin_bal"], market["margin_buy"], market["margin_repay"],
              market["net_buy"], market["short_bal"], market["short_vol"]))
        n = 1
        for r in stocks:
            cur.execute("""
                INSERT INTO margin_stock
                    (date, code, margin_bal, margin_buy, margin_repay, short_bal, short_vol, net_buy, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (date, code) DO UPDATE SET
                    margin_bal=EXCLUDED.margin_bal, margin_buy=EXCLUDED.margin_buy,
                    margin_repay=EXCLUDED.margin_repay, short_bal=EXCLUDED.short_bal,
                    short_vol=EXCLUDED.short_vol, net_buy=EXCLUDED.net_buy, ingest_ts=now()
            """, (trade_date, r["code"], r["margin_bal"], r["margin_buy"], r["margin_repay"],
                  r["short_bal"], r["short_vol"], r["net_buy"]))
            n += 1
    conn.commit()
    return n


def _prefix(code, secucode) -> str:
    suffix = str(secucode or "").split(".")[-1].upper()
    c = str(code or "").zfill(6)
    market = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix)
    return (market + c) if market else c
