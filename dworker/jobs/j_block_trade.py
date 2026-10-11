"""大宗交易。东财 datacenter RPT_DATA_BLOCKTRADE，按交易日过滤。"""
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
            ingest_logger.log_run("j_block_trade", "D4", "block_trade", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    rows = _fetch(trade_date)
    if not rows:
        return {"success": False, "source_used": "eastmoney", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no block trades dated {trade_date}"}
    try:
        raw_archiver.archive("D4", "j_block_trade", "eastmoney", rows[:20])
    except Exception as e:
        logger.warning(f"[j_block_trade] archive {e}")
    written = _write(conn, trade_date, rows)
    return {"success": written > 0, "source_used": "eastmoney",
            "rows_in": len(rows), "rows_written": written, "rows_quarantined": 0,
            "note": f"date={trade_date} deals={written}"}


def _fetch(trade_date: str) -> list:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
    rows = []
    for page in range(1, 40):
        try:
            resp = session.get(URL, params={
                "reportName": "RPT_DATA_BLOCKTRADE",
                "columns": "ALL",
                "pageSize": 500,
                "pageNumber": page,
                "sortColumns": "SECURITY_CODE",
                "sortTypes": "1",
                "filter": f"(TRADE_DATE='{trade_date}')",
            }, timeout=25)
            data = (resp.json().get("result") or {}).get("data") or []
        except Exception as e:
            logger.warning(f"[j_block_trade] page {page}: {e}")
            break
        if not data:
            break
        for item in data:
            premium = item.get("PREMIUM_RATIO")
            rows.append({
                "code": _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE")),
                "name": item.get("SECURITY_NAME_ABBR"),
                "deal_price": item.get("DEAL_PRICE"),
                "close_price": item.get("CLOSE_PRICE"),
                "premium_pct": None if premium is None else float(premium) * 100,
                "volume": item.get("DEAL_VOLUME"),
                "amount": item.get("DEAL_AMT"),
                "buyer": item.get("BUYER_NAME"),
                "seller": item.get("SELLER_NAME"),
            })
        if len(data) < 500:
            break
        time.sleep(0.1)
    return rows


def _write(conn, trade_date: str, rows: list) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM block_trade WHERE date = %s AND source = 'eastmoney'", (trade_date,))
        for r in rows:
            cur.execute("""
                INSERT INTO block_trade
                    (date, code, name, deal_price, close_price, premium_pct, volume, amount, buyer, seller, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
            """, (trade_date, r["code"], r["name"], r["deal_price"], r["close_price"],
                  r["premium_pct"], r["volume"], r["amount"], r["buyer"], r["seller"]))
    conn.commit()
    return len(rows)


def _prefix(code, secucode) -> str:
    suffix = str(secucode or "").split(".")[-1].upper()
    c = str(code or "").zfill(6)
    market = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix)
    if market:
        return market + c
    if c.startswith("6"):
        return "sh" + c
    if c.startswith(("4", "8")) or c.startswith("92"):
        return "bj" + c
    return "sz" + c
