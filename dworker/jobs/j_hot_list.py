"""同花顺热股榜。休市不落库。东财 getTodayChance 本机 rc=102，不写入。"""
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
            ingest_logger.log_run("j_hot_list", "D6", "theme_heat", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}
    stocks = _fetch_stocks(trade_date)
    concepts = _fetch_concepts(trade_date)
    rows = stocks + concepts
    if not rows:
        return {"success": False, "source_used": "ths", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0, "note": "MISS: ths hot list empty"}
    try:
        raw_archiver.archive("D6", "j_hot_list", "ths", rows[:20])
    except Exception as e:
        logger.warning(f"[j_hot_list] archive {e}")
    n = _write(conn, rows)
    return {"success": n > 0, "source_used": "ths", "rows_in": len(rows),
            "rows_written": n, "rows_quarantined": 0,
            "note": (
                f"date={trade_date} stocks={len(stocks)} concepts={len(concepts)}; "
                f"eastmoney getTodayChance rc=102 and 98dou have no list, not polled"
            )}


def _fetch_stocks(trade_date: str) -> list:
    url = ("https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
           "?stock_type=a&type=hour&list_type=normal")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}, timeout=20)
    stocks = ((resp.json().get("data") or {}).get("stock_list")) or []
    rows = []
    for i, item in enumerate(stocks, start=1):
        row = _stock_row(trade_date, i, item)
        if row:
            rows.append(row)
    return rows


def _stock_row(trade_date, rank, item):
    raw = str(item.get("code") or "").zfill(6)
    code = _prefix(raw)
    if not code:
        return None
    heat = item.get("rate")
    return {
        "date": trade_date, "kind": "hot_stock", "code": code, "name": item.get("name"),
        "rank": rank, "heat": None if heat is None else float(heat),
        "extra": {"pct": item.get("rise_and_fall")},
    }


def _fetch_concepts(trade_date: str) -> list:
    url = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/plate?type=concept"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"}, timeout=20)
    plates = ((resp.json().get("data") or {}).get("plate_list")) or []
    rows = []
    for i, item in enumerate(plates, start=1):
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        heat = item.get("rate")
        rows.append({
            "date": trade_date, "kind": "hot_concept", "code": code, "name": item.get("name"),
            "rank": i, "heat": None if heat is None else float(heat),
            "extra": {"pct": item.get("rise_and_fall"), "tag": item.get("tag")},
        })
    return rows


def _prefix(raw: str) -> str:
    if raw.startswith("6"):
        return "sh" + raw
    if raw.startswith(("0", "3")):
        return "sz" + raw
    if raw.startswith(("4", "8")) or raw.startswith("92"):
        return "bj" + raw
    return ""


def _write(conn, rows: list) -> int:
    import json
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO theme_heat
                    (date, item_kind, item_code, item_name, rank, heat_score, extra, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'ths')
                ON CONFLICT (date, item_kind, item_code, source) DO UPDATE SET
                    item_name=EXCLUDED.item_name, rank=EXCLUDED.rank,
                    heat_score=EXCLUDED.heat_score, extra=EXCLUDED.extra, ingest_ts=now()
            """, (r["date"], r["kind"], r["code"], r["name"], r["rank"], r["heat"],
                  json.dumps(r["extra"], ensure_ascii=False)))
            n += 1
    conn.commit()
    return n
