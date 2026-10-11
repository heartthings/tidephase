"""北向日频。沪股通、深股通、北向合计的成交额从 2024-08-16 起就是空的。空值不写入，记 MISS。"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
# 001 沪股通 003 深股通 005 北向合计。002/004/006 是南向，不写进这张表。
NORTH = {"001": "hgt", "003": "sgt", "005": "total"}


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_northbound", "D4", "northbound_daily", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    try:
        row = _fetch(trade_date)
    except Exception as e:
        return {"success": False, "source_used": "eastmoney", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": f"MISS: {e}"}
    if row is None:
        note = (
            f"MISS: northbound buy/sell unpublished for {trade_date}; "
            f"eastmoney RPT_NORTH_NETBUY ends 2024-08-16; southbound figures are not written here"
        )
        try:
            ingest_logger.log_run("j_northbound", "D4", "northbound_daily", "eastmoney", "MISS", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "eastmoney",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    try:
        raw_archiver.archive("D4", "j_northbound", "eastmoney", row)
    except Exception as e:
        logger.warning(f"[j_northbound] archive {e}")
    _write(conn, trade_date, row)
    return {"success": True, "source_used": "eastmoney", "rows_in": 1, "rows_written": 1,
            "rows_quarantined": 0, "note": f"date={trade_date} total_net={row['total_net']}"}


def _fetch(trade_date: str):
    resp = requests.get(URL, params={
        "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "ALL",
        "pageSize": 20,
        "pageNumber": 1,
        "filter": f"(TRADE_DATE='{trade_date}')",
    }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=20)
    data = (resp.json().get("result") or {}).get("data") or []
    picked = {}
    for item in data:
        kind = NORTH.get(str(item.get("MUTUAL_TYPE")))
        if not kind or item.get("NET_DEAL_AMT") is None:
            continue
        if str(item.get("TRADE_DATE") or "")[:10] != trade_date:
            continue
        picked[kind] = item
    if "total" not in picked and "hgt" not in picked and "sgt" not in picked:
        return None
    def net(k):
        return None if k not in picked else float(picked[k]["NET_DEAL_AMT"])
    def side(k, field):
        return None if k not in picked or picked[k].get(field) is None else float(picked[k][field])
    return {
        "hgt_net": net("hgt"), "sgt_net": net("sgt"), "total_net": net("total"),
        "hgt_buy": side("hgt", "BUY_AMT"), "hgt_sell": side("hgt", "SELL_AMT"),
        "sgt_buy": side("sgt", "BUY_AMT"), "sgt_sell": side("sgt", "SELL_AMT"),
    }


def _write(conn, trade_date: str, row: dict):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO northbound_daily (
                date, hgt_net, sgt_net, total_net, hgt_buy, hgt_sell, sgt_buy, sgt_sell, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
            ON CONFLICT (date) DO UPDATE SET
                hgt_net=EXCLUDED.hgt_net, sgt_net=EXCLUDED.sgt_net, total_net=EXCLUDED.total_net,
                hgt_buy=EXCLUDED.hgt_buy, hgt_sell=EXCLUDED.hgt_sell,
                sgt_buy=EXCLUDED.sgt_buy, sgt_sell=EXCLUDED.sgt_sell, ingest_ts=now()
        """, (trade_date, row["hgt_net"], row["sgt_net"], row["total_net"],
              row["hgt_buy"], row["hgt_sell"], row["sgt_buy"], row["sgt_sell"]))
    conn.commit()
