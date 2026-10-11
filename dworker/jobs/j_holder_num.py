"""股东户数。东财按公告日过滤。公告日没记录是正常的空结果，不是源故障。"""
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
        raw_archiver.archive("D5", "j_holder_num", "eastmoney", rows[:20])
    except Exception as e:
        logger.warning(f"[j_holder_num] archive {e}")
    n = _write(conn, rows)
    return {"success": True, "source_used": "eastmoney",
            "rows_in": len(rows), "rows_written": n, "rows_quarantined": 0,
            "note": f"announce_date={trade_date} holders={n}"}


def _fetch(trade_date: str) -> list:
    resp = requests.get(URL, params={
        "reportName": "RPT_HOLDERNUM_DET", "columns": "ALL",
        "pageSize": 500, "pageNumber": 1,
        "filter": f"(HOLD_NOTICE_DATE='{trade_date}')",
    }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=30)
    data = (resp.json().get("result") or {}).get("data") or []
    rows = []
    for item in data:
        notice = str(item.get("HOLD_NOTICE_DATE") or "")[:10]
        end = str(item.get("END_DATE") or "")[:10]
        if notice != trade_date or not end or item.get("HOLDER_NUM") is None:
            continue
        rows.append({
            "code": _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE")),
            "date": end,
            "announce_date": notice,
            "holder_num": int(item["HOLDER_NUM"]),
            "holder_num_chg": None if item.get("HOLDER_NUM_CHANGE") is None else int(item["HOLDER_NUM_CHANGE"]),
            "holder_num_chg_pct": item.get("HOLDER_NUM_RATIO"),
            "avg_hold_num": item.get("AVG_HOLD_NUM"),
        })
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO holder_num
                    (code, date, announce_date, holder_num, holder_num_chg, holder_num_chg_pct, avg_hold_num, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (code, date, announce_date) DO UPDATE SET
                    holder_num=EXCLUDED.holder_num, holder_num_chg=EXCLUDED.holder_num_chg,
                    holder_num_chg_pct=EXCLUDED.holder_num_chg_pct, avg_hold_num=EXCLUDED.avg_hold_num,
                    ingest_ts=now()
            """, (r["code"], r["date"], r["announce_date"], r["holder_num"],
                  r["holder_num_chg"], r["holder_num_chg_pct"], r["avg_hold_num"]))
            n += 1
    conn.commit()
    return n


def _prefix(code, secucode) -> str:
    suffix = str(secucode or "").split(".")[-1].upper()
    c = str(code or "").zfill(6)
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix, "") + c
