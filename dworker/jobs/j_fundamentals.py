"""解禁、股本、财报、披露预约。只写源里有的字段，没有的留空。"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT_TYPE = {"1": "一季报", "2": "半年报", "3": "三季报", "4": "年报"}


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    today = (job_ctx.params or {}).get("date") or datetime.now(TZ).strftime("%Y-%m-%d")
    end = (datetime.fromisoformat(today) + timedelta(days=80)).date().isoformat()
    lock_n = _lockup(conn, today, end)
    share_n = _share(conn, today)
    fin_n = _finance(conn, today)
    earn_n = _earnings(conn)
    try:
        raw_archiver.archive("D9", "j_fundamentals", "eastmoney", {
            "lockup": lock_n, "share": share_n, "finance": fin_n, "earnings": earn_n,
        })
    except Exception as e:
        logger.warning(f"[j_fundamentals] archive {e}")
    ok = lock_n + share_n + fin_n + earn_n > 0
    return {
        "success": ok, "source_used": "eastmoney",
        "rows_in": lock_n + share_n + fin_n + earn_n,
        "rows_written": lock_n + share_n + fin_n + earn_n,
        "rows_quarantined": 0,
        "note": (
            f"from={today} lockup={lock_n} share={share_n} finance={fin_n} earnings={earn_n}; "
            f"lockup shares are 万股*10000, mv is 万元*10000; "
            f"f10_text/consensus_eps/research_reports have no table in migrations"
        ),
    }


def _get(report, page, filt, sort_col="SECURITY_CODE"):
    resp = requests.get(URL, params={
        "reportName": report, "columns": "ALL", "pageSize": 500, "pageNumber": page,
        "sortColumns": sort_col, "sortTypes": "1", "filter": filt,
    }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}, timeout=30)
    body = resp.json()
    result = body.get("result") or {}
    return result.get("data") or []


def _lockup(conn, start, end) -> int:
    rows = _get("RPT_LIFT_STAGE", 1, f"(FREE_DATE>='{start}')(FREE_DATE<='{end}')", "FREE_DATE")
    n = 0
    with conn.cursor() as cur:
        for item in rows:
            day = _day(item.get("FREE_DATE"))
            code = _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE"))
            lock_type = (item.get("FREE_SHARES_TYPE") or "unknown").strip()
            shares = item.get("CURRENT_FREE_SHARES")
            mv = item.get("LIFT_MARKET_CAP")
            ratio = item.get("FREE_RATIO")
            if not day or not code:
                continue
            cur.execute("""
                INSERT INTO lockup_calendar
                    (unlock_date, code, name, unlock_shares, unlock_mv, unlock_pct, lock_type, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (unlock_date, code, lock_type) DO UPDATE SET
                    name=EXCLUDED.name, unlock_shares=EXCLUDED.unlock_shares,
                    unlock_mv=EXCLUDED.unlock_mv, unlock_pct=EXCLUDED.unlock_pct, ingest_ts=now()
            """, (
                day, code, item.get("SECURITY_NAME_ABBR"),
                None if shares is None else float(shares) * 10000,
                None if mv is None else float(mv) * 10000,
                None if ratio is None else float(ratio) * 100,
                lock_type[:200],
            ))
            n += 1
    conn.commit()
    return n


def _share(conn, day) -> int:
    start = (datetime.fromisoformat(day) - timedelta(days=4)).date().isoformat()
    rows = _get("RPT_F10_EH_EQUITY", 1, f"(END_DATE>='{start}')(END_DATE<='{day}')", "END_DATE")
    n = 0
    with conn.cursor() as cur:
        for item in rows:
            d = _day(item.get("END_DATE"))
            code = _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE"))
            total = item.get("TOTAL_SHARES")
            circ = item.get("UNLIMITED_SHARES")
            limited = item.get("LIMITED_SHARES")
            if limited is None and total is not None and circ is not None:
                limited = max(float(total) - float(circ), 0)
            if not d or not code or total is None:
                continue
            cur.execute("""
                INSERT INTO share_structure
                    (date, code, total_shares, circ_shares, limited_shares, detail, source)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,'eastmoney')
                ON CONFLICT (date, code) DO UPDATE SET
                    total_shares=EXCLUDED.total_shares, circ_shares=EXCLUDED.circ_shares,
                    limited_shares=EXCLUDED.limited_shares, detail=EXCLUDED.detail, ingest_ts=now()
            """, (d, code, total, circ, limited, _json_reason(item.get("CHANGE_REASON"))))
            n += 1
    conn.commit()
    return n


def _finance(conn, day) -> int:
    start = (datetime.fromisoformat(day) - timedelta(days=2)).date().isoformat()
    rows = _get("RPT_LICO_FN_CPD", 1, f"(UPDATE_DATE>='{start}')(UPDATE_DATE<='{day}')", "UPDATE_DATE")
    n = 0
    with conn.cursor() as cur:
        for item in rows:
            announce = _day(item.get("NOTICE_DATE")) or _day(item.get("UPDATE_DATE"))
            period = _day(item.get("REPORTDATE"))
            code = _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE"))
            if not announce or not period or not code:
                continue
            cur.execute("""
                INSERT INTO financial_reports (
                    announce_date, code, report_period, revenue, revenue_yoy, net_profit,
                    net_profit_yoy, eps, roe, gross_margin, net_margin, source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (announce_date, code, report_period) DO UPDATE SET
                    revenue=EXCLUDED.revenue, revenue_yoy=EXCLUDED.revenue_yoy,
                    net_profit=EXCLUDED.net_profit, net_profit_yoy=EXCLUDED.net_profit_yoy,
                    eps=EXCLUDED.eps, roe=EXCLUDED.roe, gross_margin=EXCLUDED.gross_margin,
                    net_margin=EXCLUDED.net_margin, ingest_ts=now()
            """, (
                announce, code, period,
                item.get("TOTAL_OPERATE_INCOME"), item.get("YSTZ"),
                item.get("PARENT_NETPROFIT"), item.get("SJLTZ"),
                item.get("BASIC_EPS"), item.get("WEIGHTAVG_ROE"),
                item.get("XSMLL"), item.get("SJLHZ"),
            ))
            cur.execute("""
                INSERT INTO finance_snapshot (
                    date, code, metrics, roe, gross_margin, net_margin,
                    revenue_yoy, net_profit_yoy, eps, source
                ) VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (date, code) DO UPDATE SET
                    metrics=EXCLUDED.metrics, roe=EXCLUDED.roe, gross_margin=EXCLUDED.gross_margin,
                    net_margin=EXCLUDED.net_margin, revenue_yoy=EXCLUDED.revenue_yoy,
                    net_profit_yoy=EXCLUDED.net_profit_yoy, eps=EXCLUDED.eps, ingest_ts=now()
            """, (
                announce, code,
                _json_reason(item.get("SECURITY_NAME_ABBR")),
                item.get("WEIGHTAVG_ROE"), item.get("XSMLL"), item.get("SJLHZ"),
                item.get("YSTZ"), item.get("SJLTZ"), item.get("BASIC_EPS"),
            ))
            n += 1
    conn.commit()
    return n


def _earnings(conn) -> int:
    rows = []
    for page in range(1, 20):
        batch = _get(
            "RPT_PUBLIC_BS_APPOIN", page,
            "(APPOINT_PUBLISH_DATE>='2026-10-01')(APPOINT_PUBLISH_DATE<='2026-12-31')",
            "APPOINT_PUBLISH_DATE",
        )
        rows.extend(batch)
        if len(batch) < 500:
            break
        time.sleep(0.05)
    n = 0
    with conn.cursor() as cur:
        for item in rows:
            pre = _day(item.get("APPOINT_PUBLISH_DATE"))
            period = _day(item.get("REPORT_DATE"))
            code = _prefix(item.get("SECURITY_CODE"), item.get("SECUCODE"))
            if not pre or not period or not code:
                continue
            actual = _day(item.get("ACTUAL_PUBLISH_DATE"))
            cur.execute("""
                INSERT INTO earnings_calendar
                    (pre_date, code, name, report_period, report_type, actual_date, status, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'eastmoney')
                ON CONFLICT (pre_date, code, report_period) DO UPDATE SET
                    name=EXCLUDED.name, report_type=EXCLUDED.report_type,
                    actual_date=EXCLUDED.actual_date, status=EXCLUDED.status, ingest_ts=now()
            """, (
                pre, code, item.get("SECURITY_NAME_ABBR"), period,
                REPORT_TYPE.get(str(item.get("REPORT_TYPE")), str(item.get("REPORT_TYPE") or "unknown")),
                actual, "published" if actual else "scheduled",
            ))
            n += 1
    conn.commit()
    return n


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


def _day(v):
    if not v:
        return None
    return str(v)[:10]


def _json_reason(text):
    import json
    return json.dumps({"label": text} if text else {}, ensure_ascii=False)
