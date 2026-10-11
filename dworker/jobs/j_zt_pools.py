"""
j_zt_pools - 涨停 / 炸板 / 跌停池
目标表：zt_pool, zb_pool, dt_pool（yzt_pool 源端无带日期的昨涨今现接口，显式 MISS）

主源：同花顺 data.10jqka.com.cn/dataapi/limit_up/*
备源：东财 push2ex（本机实测 rc=205，留着但不当主源）

门禁：非交易日 SKIP。params['date'] 可指定补采日（YYYY-MM-DD）。
缺字段写 NULL，不编数。
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))

POOLS = (
    ("limit_up_pool", "zt_pool"),
    ("open_limit_pool", "zb_pool"),
    ("lower_limit_pool", "dt_pool"),
)

THS_FIELDS = (
    "199112,10,9001,330323,330324,330325,9002,330329,"
    "133971,133970,1968584,3475914,9003,48"
)


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    t0 = time.time()
    trade_date = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")

    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_zt_pools] {note}")
        try:
            ingest_logger.log_run(
                "j_zt_pools", "D3", "zt_pool", "none", "SKIP",
                note=note, trigger=trigger,
            )
        except Exception as e:
            logger.warning(f"[j_zt_pools] ingest SKIP failed: {e}")
        return {
            "success": True, "source_used": "none", "already_logged": True,
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
        }

    ymd = trade_date.replace("-", "")
    source_used = None
    pools = {}
    for name in source_chain or ["ths"]:
        try:
            if name == "ths":
                pools = _fetch_ths(ymd)
            elif name == "eastmoney":
                pools = _fetch_eastmoney(ymd)
            else:
                continue
        except Exception as e:
            logger.warning(f"[j_zt_pools] {name} failed: {e}")
            pools = {}
        if pools.get("zt_pool"):
            source_used = name
            break

    if not pools.get("zt_pool"):
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": f"MISS: no zt_pool for {trade_date}",
        }

    try:
        raw_archiver.archive("D3", "j_zt_pools", source_used, {
            k: v[:20] for k, v in pools.items()
        })
    except Exception as e:
        logger.warning(f"[j_zt_pools] archive failed: {e}")

    written = _write_pools(conn, pools, source_used, trade_date)
    rows_in = sum(len(v) for v in pools.values())
    note = (
        f"date={trade_date} source={source_used} "
        f"zt={len(pools.get('zt_pool', []))} "
        f"zb={len(pools.get('zb_pool', []))} "
        f"dt={len(pools.get('dt_pool', []))} "
        f"written={written} "
        f"yzt_pool MISS: 同花顺无带日期的昨涨今现端点，不编数 "
        f"elapsed={time.time()-t0:.1f}s"
    )
    logger.info(f"[j_zt_pools] {note}")
    return {
        "success": True, "source_used": source_used,
        "rows_in": rows_in, "rows_written": written, "rows_quarantined": 0,
        "note": note,
    }


def _fetch_ths(ymd: str) -> dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://data.10jqka.com.cn/",
    })
    out = {}
    for endpoint, table in POOLS:
        rows = []
        page = 1
        while page <= 20:
            resp = session.get(
                f"https://data.10jqka.com.cn/dataapi/limit_up/{endpoint}",
                params={
                    "page": page, "limit": 200, "date": ymd,
                    "field": THS_FIELDS, "filter": "HS,GEM2STAR",
                    "order_field": "199112", "order_type": 0,
                },
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status_code") not in (0, "0", None):
                break
            data = payload.get("data") or {}
            info = data.get("info") or []
            for item in info:
                mapped = _map_ths(item)
                if mapped:
                    rows.append(mapped)
            total = ((data.get("page") or {}).get("total")) or 0
            if not info or page * 200 >= int(total):
                break
            page += 1
        out[table] = rows
    return out


def _map_ths(item: dict) -> dict:
    raw = str(item.get("code") or "").strip()
    if not raw.isdigit():
        return None
    raw = raw.zfill(6)
    if raw.startswith("6"):
        code = "sh" + raw
    elif raw.startswith(("0", "3")):
        code = "sz" + raw
    elif raw.startswith(("4", "8")):
        code = "bj" + raw
    else:
        return None
    return {
        "code": code,
        "name": item.get("name"),
        "close": _num(item.get("latest")),
        "pct": _num(item.get("change_rate")),
        "amount": None,
        "circ_mv": _num(item.get("currency_value")),
        "turnover_rate": _num(item.get("turnover_rate")),
        "seal_amount": _num(item.get("order_amount")),
        "first_seal_time": _clock(item.get("first_limit_up_time")),
        "last_seal_time": _clock(item.get("last_limit_up_time")),
        "break_times": _int(item.get("open_num")),
        "board_days": _board_days(item.get("high_days")),
        "industry": None,
        "theme": item.get("reason_type"),
        "reason": item.get("reason_type") or item.get("limit_up_type"),
    }


def _fetch_eastmoney(ymd: str) -> dict:
    """备源。本机常返回 rc=205，调用方以空池视为失败。"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    })
    spec = (
        ("getTopicZTPool", "zt_pool"),
        ("getTopicZBPool", "zb_pool"),
        ("getTopicDTPool", "dt_pool"),
    )
    out = {}
    for path, table in spec:
        resp = session.get(
            f"https://push2ex.eastmoney.com/{path}",
            params={
                "ut": "7eea3edcaed734bea9cbfc244709108",
                "dpt": "wz.ztzt", "Pageindex": 0, "pagesize": 500,
                "sort": "fbt:asc", "date": ymd,
            },
            timeout=15,
        )
        pool = ((resp.json() or {}).get("data") or {}).get("pool") or []
        rows = []
        for item in pool:
            raw = str(item.get("c") or "")
            if not raw.isdigit():
                continue
            raw = raw.zfill(6)
            code = ("sh" + raw) if raw.startswith("6") else ("sz" + raw)
            rows.append({
                "code": code,
                "name": item.get("n"),
                "close": _num(item.get("p")),
                "pct": _num(item.get("zdp")),
                "amount": _num(item.get("amount")),
                "circ_mv": _num(item.get("ltsz")),
                "turnover_rate": _num(item.get("hs")),
                "seal_amount": _num(item.get("fund")),
                "first_seal_time": None,
                "last_seal_time": None,
                "break_times": _int(item.get("zbc")),
                "board_days": _int(item.get("lbc")),
                "industry": item.get("hybk"),
                "theme": None,
                "reason": None,
            })
        out[table] = rows
    return out


def _write_pools(conn, pools: dict, source: str, trade_date: str) -> int:
    written = 0
    with conn.cursor() as cur:
        for row in pools.get("zt_pool") or []:
            cur.execute("""
                INSERT INTO zt_pool (
                    date, code, name, close, pct, amount, circ_mv, turnover_rate,
                    seal_amount, first_seal_time, last_seal_time, break_times,
                    board_days, industry, theme, reason, source
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s,%s
                )
                ON CONFLICT (date, code) DO UPDATE SET
                    name=EXCLUDED.name, close=EXCLUDED.close, pct=EXCLUDED.pct,
                    circ_mv=EXCLUDED.circ_mv, turnover_rate=EXCLUDED.turnover_rate,
                    seal_amount=EXCLUDED.seal_amount,
                    first_seal_time=EXCLUDED.first_seal_time,
                    last_seal_time=EXCLUDED.last_seal_time,
                    break_times=EXCLUDED.break_times, board_days=EXCLUDED.board_days,
                    theme=EXCLUDED.theme, reason=EXCLUDED.reason,
                    source=EXCLUDED.source, ingest_ts=now()
            """, (
                trade_date, row["code"], row["name"], row["close"], row["pct"],
                row["amount"], row["circ_mv"], row["turnover_rate"],
                row["seal_amount"], row["first_seal_time"], row["last_seal_time"],
                row["break_times"], row["board_days"], row["industry"],
                row["theme"], row["reason"], source,
            ))
            written += 1
        for table in ("zb_pool", "dt_pool"):
            for row in pools.get(table) or []:
                if table == "zb_pool":
                    cur.execute("""
                        INSERT INTO zb_pool (
                            date, code, name, close, pct, amount, circ_mv, turnover_rate,
                            first_seal_time, break_times, board_days, industry, source
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (date, code) DO UPDATE SET
                            name=EXCLUDED.name, close=EXCLUDED.close, pct=EXCLUDED.pct,
                            circ_mv=EXCLUDED.circ_mv, turnover_rate=EXCLUDED.turnover_rate,
                            break_times=EXCLUDED.break_times, source=EXCLUDED.source,
                            ingest_ts=now()
                    """, (
                        trade_date, row["code"], row["name"], row["close"], row["pct"],
                        row["amount"], row["circ_mv"], row["turnover_rate"],
                        row["first_seal_time"], row["break_times"], row["board_days"],
                        row["industry"], source,
                    ))
                else:
                    cur.execute("""
                        INSERT INTO dt_pool (
                            date, code, name, close, pct, amount, circ_mv, turnover_rate,
                            seal_amount, first_seal_time, last_seal_time, break_times,
                            board_days, industry, source
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (date, code) DO UPDATE SET
                            name=EXCLUDED.name, close=EXCLUDED.close, pct=EXCLUDED.pct,
                            circ_mv=EXCLUDED.circ_mv, turnover_rate=EXCLUDED.turnover_rate,
                            seal_amount=EXCLUDED.seal_amount,
                            break_times=EXCLUDED.break_times, source=EXCLUDED.source,
                            ingest_ts=now()
                    """, (
                        trade_date, row["code"], row["name"], row["close"], row["pct"],
                        row["amount"], row["circ_mv"], row["turnover_rate"],
                        row["seal_amount"], row["first_seal_time"], row["last_seal_time"],
                        row["break_times"], row["board_days"], row["industry"], source,
                    ))
                written += 1
    conn.commit()
    return written


def _num(v):
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def _int(v):
    n = _num(v)
    if n is None:
        return None
    return int(n)


def _board_days(text):
    if not text:
        return None
    s = str(text)
    if s == "首板":
        return 1
    import re
    m = re.search(r"(\d+)板", s)
    if m:
        return int(m.group(1))
    return None


def _clock(v):
    if v is None or v == "":
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if n > 10_000_000_000:
        n = n / 1000
    if n < 1_000_000_000:
        return None
    dt = datetime.fromtimestamp(n, TZ)
    return dt.strftime("%H:%M:%S")
