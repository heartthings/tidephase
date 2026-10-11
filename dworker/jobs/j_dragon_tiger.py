"""龙虎榜。东财按交易日给出上榜原因、买卖额、净额，以及买卖前五席位。"""
import logging
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
            ingest_logger.log_run("j_dragon_tiger", "D4", "dragon_tiger", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    try:
        rows = _fetch(trade_date)
    except Exception as e:
        return {"success": False, "source_used": "eastmoney", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": f"MISS: {e}"}
    if not rows:
        return {"success": False, "source_used": "eastmoney", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: no billboard rows for {trade_date}"}
    try:
        raw_archiver.archive("D4", "j_dragon_tiger", "eastmoney", rows[:20])
    except Exception as e:
        logger.warning(f"[j_dragon_tiger] archive {e}")
    n = _write(conn, rows)
    seats = _attach_seats(conn, trade_date)
    return {"success": n > 0, "source_used": "eastmoney",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"date={trade_date} rows={n} seat_groups={seats}"}


def _fetch(trade_date: str) -> list:
    resp = requests.get(URL, params={
        "reportName": "RPT_BILLBOARD_DAILYDETAILS",
        "columns": "ALL",
        "pageSize": 500,
        "pageNumber": 1,
        "filter": f"(TRADE_DATE='{trade_date}')",
    }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=30)
    data = (resp.json().get("result") or {}).get("data") or []
    rows = []
    for item in data:
        day = str(item.get("TRADE_DATE") or "")[:10]
        reason = (item.get("EXPLANATION") or "").strip()
        if day != trade_date or not reason:
            continue
        rows.append({
            "date": trade_date,
            "code": _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE")),
            "name": item.get("SECURITY_NAME_ABBR"),
            "close": item.get("CLOSE_PRICE"),
            "pct": item.get("CHANGE_RATE"),
            "reason": reason[:200],
            "turnover_rate": item.get("TURNRATE"),
            "amount": item.get("ACCUM_AMOUNT"),
            "net_buy": item.get("TOTAL_NET"),
            "buy_amount": item.get("TOTAL_BUY"),
            "sell_amount": item.get("TOTAL_SELL"),
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO dragon_tiger (
                    date, code, name, close, pct, reason, turnover_rate, amount,
                    net_buy, buy_amount, sell_amount, source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (date, code, reason) DO UPDATE SET
                    name=EXCLUDED.name, close=EXCLUDED.close, pct=EXCLUDED.pct,
                    turnover_rate=EXCLUDED.turnover_rate, amount=EXCLUDED.amount,
                    net_buy=EXCLUDED.net_buy, buy_amount=EXCLUDED.buy_amount,
                    sell_amount=EXCLUDED.sell_amount, ingest_ts=now()
            """, (r["date"], r["code"], r["name"], r["close"], r["pct"], r["reason"],
                  r["turnover_rate"], r["amount"], r["net_buy"], r["buy_amount"], r["sell_amount"]))
            n += 1
    conn.commit()
    return n


def _attach_seats(conn, trade_date: str) -> int:
    """买卖前五来自席位明细。按上榜原因分组，金额从大到小取五条。"""
    import json
    seats = []
    for page in range(1, 6):
        try:
            resp = requests.get(URL, params={
                "reportName": "RPT_BILLBOARD_DAILYDETAILSBUY",
                "columns": "ALL", "pageSize": 500, "pageNumber": page,
                "filter": f"(TRADE_DATE='{trade_date}')",
            }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=30)
            batch = (resp.json().get("result") or {}).get("data") or []
        except Exception as e:
            logger.warning(f"[j_dragon_tiger] seats page {page}: {e}")
            break
        seats.extend(batch)
        if len(batch) < 500:
            break
    groups = {}
    for item in seats:
        if str(item.get("TRADE_DATE") or "")[:10] != trade_date:
            continue
        reason = (item.get("EXPLANATION") or "").strip()[:200]
        code = _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE"))
        if not reason or not code:
            continue
        groups.setdefault((code, reason), []).append(item)
    n = 0
    with conn.cursor() as cur:
        for (code, reason), items in groups.items():
            buy = sorted(
                ({"name": i.get("OPERATEDEPT_NAME"), "amount": i.get("BUY")}
                 for i in items if (i.get("BUY") or 0) > 0),
                key=lambda x: x["amount"] or 0, reverse=True,
            )[:5]
            sell = sorted(
                ({"name": i.get("OPERATEDEPT_NAME"), "amount": i.get("SELL")}
                 for i in items if (i.get("SELL") or 0) > 0),
                key=lambda x: x["amount"] or 0, reverse=True,
            )[:5]
            inst = [i for i in items if "机构" in str(i.get("OPERATEDEPT_NAME") or "")]
            inst_net = None
            if inst:
                inst_net = sum(float(i.get("NET") or 0) for i in inst)
            cur.execute("""
                UPDATE dragon_tiger
                SET buy_top5 = %s::jsonb, sell_top5 = %s::jsonb,
                    inst_flag = %s, inst_net = %s, ingest_ts = now()
                WHERE date = %s AND code = %s AND reason = %s
            """, (
                json.dumps(buy, ensure_ascii=False),
                json.dumps(sell, ensure_ascii=False),
                bool(inst), inst_net, trade_date, code, reason,
            ))
            n += cur.rowcount
    conn.commit()
    return n


def _prefix(code, secucode) -> str:
    suffix = str(secucode or "").split(".")[-1].upper()
    c = str(code or "").zfill(6)
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix, "") + c
