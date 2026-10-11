"""巨潮公告。按交易日分页拉取，同一 ann_id 可重复跑。"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run("j_announcements", "D10", "announcements", "none", "SKIP", note=note, trigger=trigger)
        except Exception:
            pass
        return {"success": True, "already_logged": True, "source_used": "none",
                "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    rows = _fetch(trade_date)
    if not rows:
        return {"success": False, "source_used": "cninfo", "rows_in": 0,
                "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: cninfo empty for {trade_date}"}
    try:
        raw_archiver.archive("D10", "j_announcements", "cninfo", rows[:30])
    except Exception as e:
        logger.warning(f"[j_announcements] archive {e}")
    written = _write(conn, rows)
    return {"success": written > 0, "source_used": "cninfo",
            "rows_in": len(rows), "rows_written": written, "rows_quarantined": 0,
            "note": f"date={trade_date} announcements={written}"}


def _fetch(trade_date: str) -> list:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    rows = []
    seen = set()
    for page in range(1, 80):
        try:
            resp = session.post(URL, data={
                "pageNum": page, "pageSize": 30, "column": "szse",
                "tabName": "fulltext", "seDate": f"{trade_date}~{trade_date}",
                "isHLtitle": "true",
            }, timeout=25)
            anns = resp.json().get("announcements") or []
        except Exception as e:
            logger.warning(f"[j_announcements] page {page}: {e}")
            break
        if not anns:
            break
        for a in anns:
            ann_id = str(a.get("announcementId") or "")
            title = (a.get("announcementTitle") or "").strip()
            if not ann_id or not title or ann_id in seen:
                continue
            seen.add(ann_id)
            path = a.get("adjunctUrl") or ""
            rows.append({
                "ann_date": trade_date,
                "ann_id": ann_id,
                "code": _prefix(a.get("secCode")),
                "name": a.get("secName"),
                "title": title,
                "ann_type": a.get("announcementTypeName") or a.get("announcementType"),
                "url": ("http://static.cninfo.com.cn/" + path) if path else None,
            })
        if len(anns) < 30:
            break
        time.sleep(0.12)
    return rows


def _write(conn, rows: list) -> int:
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO announcements (ann_date, ann_id, code, name, title, ann_type, url, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'cninfo')
                ON CONFLICT (ann_date, ann_id) DO UPDATE SET
                    code=EXCLUDED.code, name=EXCLUDED.name, title=EXCLUDED.title,
                    ann_type=EXCLUDED.ann_type, url=EXCLUDED.url, ingest_ts=now()
            """, (r["ann_date"], r["ann_id"], r["code"], r["name"], r["title"], r["ann_type"], r["url"]))
            n += 1
    conn.commit()
    return n


def _prefix(code) -> str:
    c = str(code or "").strip().zfill(6)
    if c.startswith("6"):
        return "sh" + c
    if c.startswith(("0", "2", "3")):
        return "sz" + c
    if c.startswith(("4", "8")) or c.startswith("92"):
        return "bj" + c
    return c


def _skip():
    return None
