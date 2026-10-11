"""
j_sector_daily - 概念板块日行情
目标表：sector_daily、theme_heat
主源：龙虎 RealRankingInfo ZSType=7（代码 801xxx，和 lovetrade 迁过来的历史同一套）
列语义按 docs/field_dict_longhu_draft.md：
  [4] 涨幅%  [5] 成交额元  [6] 主力净额元  [2] 强度（写入 theme_heat）
备源：腾讯 pt01 报价。腾讯没有主力净额，该列留 NULL。

params['date'] 传给龙虎 Date。实测 Date=2026-10-08 与 10-09 数值不同，
但响应里的 Day 字段会停在最近交易日，不能用 Day 来否决 Date。
"""
import logging
import math
import time
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
BATCH = 60


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    t0 = time.time()
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    trade_date = (job_ctx.params or {}).get("date") or today

    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run(
                "j_sector_daily", "D6", "sector_daily", "none", "SKIP",
                note=note, trigger=trigger,
            )
        except Exception as e:
            logger.warning(f"[j_sector_daily] ingest SKIP failed: {e}")
        return {
            "success": True, "source_used": "none", "already_logged": True,
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
        }

    rows, source_used = _fetch_rows(trade_date)
    if not rows:
        return {
            "success": False, "source_used": source_used or "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": f"MISS: no sector rows for {trade_date}",
        }

    try:
        raw_archiver.archive("D6", "j_sector_daily", source_used, rows[:30])
    except Exception as e:
        logger.warning(f"[j_sector_daily] archive failed: {e}")

    written = _write_sector(conn, rows, source_used)
    heat_written = _write_heat_from_rows(conn, rows, trade_date, source_used)

    note = (
        f"date={trade_date} source={source_used} "
        f"rows={len(rows)} written={written} theme_heat={heat_written} "
        f"elapsed={time.time()-t0:.1f}s"
    )
    logger.info(f"[j_sector_daily] {note}")
    return {
        "success": written > 0, "source_used": source_used,
        "rows_in": len(rows), "rows_written": written + heat_written,
        "rows_quarantined": 0, "note": note,
    }


def _fetch_rows(trade_date: str):
    try:
        rows = _fetch_longhu(trade_date)
        if rows:
            return rows, "longhu"
    except Exception as e:
        logger.warning(f"[j_sector_daily] longhu failed: {e}")
    return [], "longhu"


def _fetch_longhu(trade_date: str) -> list:
    from dworker.adapters.longhu import ENDPOINT_MAP, LonghuAdapter

    adapter = LonghuAdapter()
    ep = ENDPOINT_MAP["PlateMovement"]
    host = adapter._get_host_url(ep["host"])
    auth = adapter._get_auth_params(ep["auth"])
    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    rows = []
    seen = set()
    for index in range(0, 400, 80):
        req = {
            "a": ep["a"], "c": ep["c"], "PhoneOSNew": "1",
            "VerSion": "5.21.0.0", "apiv": "w42",
            "Type": "1", "Order": "1", "st": "80", "Index": str(index),
            "ZSType": "7", "Date": trade_date,
        }
        req.update(auth)
        resp = adapter.session.post(host, data=req, headers=headers, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        if str(payload.get("errcode", "0")) not in ("0", ""):
            break
        batch = payload.get("list") or []
        if not batch:
            break
        for item in batch:
            if not isinstance(item, list) or len(item) < 7:
                continue
            code = str(item[0])
            if not code or code in seen:
                continue
            seen.add(code)
            rows.append({
                "date": trade_date,
                "sector_code": code,
                "sector_name": item[1],
                "pct": _num(item[4]),
                "close": None,
                "turnover": _num(item[5]),
                "main_net": _num(item[6]),
                "heat": _num(item[2]),
                "rank": len(rows) + 1,
            })
        if len(batch) < 80:
            break
        time.sleep(0.3)
    return rows


def _load_codes(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT sector_code FROM sector_daily
            WHERE sector_code ~ '^[0-9]{6}$'
            ORDER BY 1
        """)
        return [r[0] for r in cur.fetchall()]


def _fetch_tencent(codes: list, trade_date: str) -> list:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://gu.qq.com/",
    })
    ymd = trade_date.replace("-", "")
    rows = []
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i + BATCH]
        query = ",".join("pt01" + c for c in batch)
        try:
            resp = session.get(f"https://qt.gtimg.cn/q={query}", timeout=20)
        except Exception as e:
            logger.warning(f"[j_sector_daily] batch failed: {e}")
            continue
        if resp.status_code != 200 or not resp.content:
            continue
        text = resp.content.decode("gbk", errors="replace")
        for line in text.split(";"):
            line = line.strip()
            if "=" not in line:
                continue
            val = line.split("=", 1)[1].strip().strip('"')
            parts = val.split("~")
            if len(parts) < 38:
                continue
            stamp = parts[30]
            if not stamp.startswith(ymd):
                continue
            code_raw = parts[2]
            sector_code = code_raw[2:] if code_raw.startswith("01") and len(code_raw) == 8 else code_raw
            close = _num(parts[3])
            pct = _num(parts[32])
            if close is None:
                continue
            amount_wan = _num(parts[37])
            rows.append({
                "sector_code": sector_code,
                "sector_name": parts[1],
                "close": close,
                "pct": pct,
                "turnover": None if amount_wan is None else amount_wan * 10000,
                "date": trade_date,
            })
    return rows


def _write_sector(conn, rows: list, source: str) -> int:
    written = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO sector_daily (
                    date, sector_code, sector_name, kind, pct, close,
                    main_net_inflow, turnover, source
                ) VALUES (%s,%s,%s,'concept',%s,%s,%s,%s,%s)
                ON CONFLICT (date, sector_code) DO UPDATE SET
                    sector_name=EXCLUDED.sector_name,
                    pct=EXCLUDED.pct,
                    close=COALESCE(EXCLUDED.close, sector_daily.close),
                    main_net_inflow=EXCLUDED.main_net_inflow,
                    turnover=EXCLUDED.turnover,
                    source=EXCLUDED.source, ingest_ts=now()
            """, (
                r["date"], r["sector_code"], r["sector_name"],
                r["pct"], r.get("close"), r.get("main_net"), r.get("turnover"),
                source,
            ))
            written += 1
    conn.commit()
    return written


def _write_heat_from_rows(conn, rows: list, trade_date: str, source: str) -> int:
    import json
    written = 0
    with conn.cursor() as cur:
        for r in rows:
            if r.get("heat") is None and r.get("rank") is None:
                continue
            cur.execute("""
                INSERT INTO theme_heat (
                    date, item_kind, item_code, item_name, rank, heat_score, extra, source
                ) VALUES (%s,'concept',%s,%s,%s,%s,%s,%s)
                ON CONFLICT (date, item_kind, item_code, source) DO UPDATE SET
                    item_name=EXCLUDED.item_name, rank=EXCLUDED.rank,
                    heat_score=EXCLUDED.heat_score, ingest_ts=now()
            """, (
                trade_date, r["sector_code"], r["sector_name"], r.get("rank"),
                r.get("heat"), json.dumps({"pct": r.get("pct")}, ensure_ascii=False),
                source,
            ))
            written += 1
    conn.commit()
    return written


def _fetch_heat() -> list:
    try:
        resp = requests.get(
            "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_plate/concept/data.txt",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://eq.10jqka.com.cn/"},
            timeout=15,
        )
        payload = resp.json()
    except Exception as e:
        logger.warning(f"[j_sector_daily] theme heat failed: {e}")
        return []
    plates = ((payload.get("data") or {}).get("plate_list")) or []
    rows = []
    for i, item in enumerate(plates):
        code = str(item.get("code") or "")
        if not code:
            continue
        rows.append({
            "item_code": code,
            "item_name": item.get("name"),
            "rank": item.get("order") or (i + 1),
            "heat_score": _num(item.get("rate")),
            "extra": {"hot_tag": item.get("hot_tag"), "tag": item.get("tag")},
        })
    return rows


def _write_heat(conn, rows: list, trade_date: str) -> int:
    if not rows:
        return 0
    import json
    written = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute("""
                INSERT INTO theme_heat (
                    date, item_kind, item_code, item_name, rank, heat_score, extra, source
                ) VALUES (%s,'concept',%s,%s,%s,%s,%s,'ths-hot')
                ON CONFLICT (date, item_kind, item_code, source) DO UPDATE SET
                    item_name=EXCLUDED.item_name, rank=EXCLUDED.rank,
                    heat_score=EXCLUDED.heat_score, extra=EXCLUDED.extra, ingest_ts=now()
            """, (
                trade_date, r["item_code"], r["item_name"], r["rank"],
                r["heat_score"], json.dumps(r["extra"], ensure_ascii=False),
            ))
            written += 1
    conn.commit()
    return written


def _num(v):
    if v is None or v == "" or v == "-":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or math.isinf(n):
        return None
    return n
