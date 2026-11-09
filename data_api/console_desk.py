"""观势台聚合接口。把盘中胶带、涨跌停池、大盘直播、覆盖一次打包给 console。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import psycopg2.extras
from fastapi import APIRouter, Query

from data_api.board_logic import clip_line, yuan_to_yi
from data_api.lovetrade_routes import get_reader_conn
from data_api.mind_db import get_mind_reader_conn

logger = logging.getLogger("data-api.console-desk")
router = APIRouter(prefix="/api/console", tags=["console-desk"])
TZ = timezone(timedelta(hours=8))

INDEX_NAMES = {
    "sh000001": "上证",
    "sz399001": "深成",
    "sz399006": "创业板",
    "sh000300": "沪深300",
    "sh000016": "上证50",
    "sh000688": "科创50",
}


def _now() -> datetime:
    return datetime.now(TZ)


def _num(value, digits: int = 2):
    if value is None:
        return None
    return round(float(value), digits)


def _clock(ts):
    if ts is None:
        return ""
    if hasattr(ts, "astimezone"):
        return ts.astimezone(TZ).strftime("%H:%M")
    if hasattr(ts, "strftime"):
        return ts.strftime("%H:%M")
    return str(ts)


def _query(sql: str, params=None, mind: bool = False):
    conn = get_mind_reader_conn() if mind else get_reader_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _try(sql: str, params=None, mind: bool = False):
    try:
        return _query(sql, params, mind)
    except Exception as exc:
        logger.info("console desk skip: %s %s", exc.__class__.__name__, exc)
        return None


def _trade_day(day: date | None) -> date:
    if day is None:
        day = _now().date()
    rows = _try(
        """
        SELECT cal_date FROM trade_cal
        WHERE market='SSE' AND cal_date <= %s AND is_open = 1
        ORDER BY cal_date DESC LIMIT 1
        """,
        [day],
    )
    if rows:
        return rows[0]["cal_date"]
    return day


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _envelope(data, gaps=None):
    body = {
        "code": 0,
        "data": data,
        "message": "ok",
        "meta": {"rows": 1, "server_ts": _now().isoformat()},
    }
    if gaps:
        body["gaps"] = gaps
    return body


@router.get("/desk")
async def console_desk(date_str: str | None = Query(default=None, alias="date")):
    """观势台首页/盘面用的一页数。"""
    day = _trade_day(_parse_day(date_str))
    gaps: list[str] = []
    data: dict = {"date": day.isoformat(), "asOf": _now().strftime("%Y-%m-%d %H:%M:%S")}

    open_row = _try(
        "SELECT is_open FROM trade_cal WHERE market='SSE' AND cal_date=%s",
        [day],
    )
    data["isTradingDay"] = bool(open_row and open_row[0]["is_open"] == 1)

    index_rows = _try(
        """
        SELECT code, name, open, high, low, close, pct, volume, amount
        FROM index_daily
        WHERE date = %s AND code = ANY(%s)
        ORDER BY code
        """,
        [day, list(INDEX_NAMES)],
    ) or []
    data["indices"] = [{
        "code": row["code"],
        "name": INDEX_NAMES.get(row["code"], row["name"] or row["code"]),
        "open": _num(row["open"]),
        "high": _num(row["high"]),
        "low": _num(row["low"]),
        "close": _num(row["close"]),
        "pct": _num(row["pct"]),
        "volumeYi": _num(float(row["volume"] or 0) / 1e8, 2) if row["volume"] is not None else None,
        "amountYi": _num(float(row["amount"] or 0) / 1e8, 2) if row["amount"] is not None else None,
    } for row in index_rows]
    if not data["indices"]:
        gaps.append("指数日线还没有")

    breadth = _try(
        """
        SELECT
          count(*) FILTER (WHERE pct > 0)::int AS up_n,
          count(*) FILTER (WHERE pct < 0)::int AS down_n,
          count(*) FILTER (WHERE pct = 0)::int AS flat_n,
          count(*) FILTER (WHERE pct >= 9.5)::int AS limit_up_zone,
          count(*) FILTER (WHERE pct <= -9.5)::int AS limit_down_zone,
          avg(pct) AS avg_pct,
          percentile_cont(0.5) WITHIN GROUP (ORDER BY pct) AS median_pct
        FROM stock_daily
        WHERE date = %s AND pct IS NOT NULL
          AND code ~ '^(sh60|sz00|sz30|sh688)'
        """,
        [day],
    )
    if breadth:
        row = breadth[0]
        data["breadth"] = {
            "upN": row["up_n"],
            "downN": row["down_n"],
            "flatN": row["flat_n"],
            "limitUpZone": row["limit_up_zone"],
            "limitDownZone": row["limit_down_zone"],
            "avgPct": _num(row["avg_pct"]),
            "medianPct": _num(row["median_pct"]),
        }
    else:
        data["breadth"] = {}
        gaps.append("涨跌家数还没有")

    sentiment = _try(
        """
        SELECT date, limit_up, limit_down, seal_rate, broken_rate, max_board,
               promote_rate, up_cnt, down_cnt, flat_cnt, dbcgl, dbyll,
               yest_rase, sentiment_score
        FROM sentiment_daily
        WHERE date = %s
        """,
        [day],
    )
    if sentiment:
        row = sentiment[0]
        data["sentiment"] = {
            "limitUp": row.get("limit_up"),
            "limitDown": row.get("limit_down"),
            "sealRate": _num(row.get("seal_rate")),
            "brokenRate": _num(row.get("broken_rate")),
            "maxBoard": row.get("max_board"),
            "promoteRate": _num(row.get("promote_rate")),
            "upCnt": row.get("up_cnt"),
            "downCnt": row.get("down_cnt"),
            "flatCnt": row.get("flat_cnt"),
            "dbcgl": _num(row.get("dbcgl")),
            "dbyll": _num(row.get("dbyll")),
            "yestRase": _num(row.get("yest_rase")),
            "score": _num(row.get("sentiment_score")),
        }
    else:
        data["sentiment"] = {}
        gaps.append("情绪日线还没有")

    def pool(table: str, limit: int = 40):
        rows = _try(
            f"""
            SELECT code, name, close, pct, amount, circ_mv, turnover_rate,
                   seal_amount, first_seal_time, last_seal_time, break_times,
                   up_days, board_days, industry, theme, reason
            FROM {table}
            WHERE date = %s
            ORDER BY board_days DESC NULLS LAST, pct DESC NULLS LAST
            LIMIT %s
            """,
            [day, limit],
        )
        if not rows:
            return []
        out = []
        for row in rows:
            circ = row.get("circ_mv")
            circ_yi = None
            if circ is not None:
                circ_f = float(circ)
                circ_yi = _num(circ_f / 1e8, 2) if circ_f > 1e6 else _num(circ_f)
            out.append({
                "code": row["code"],
                "name": row["name"],
                "close": _num(row["close"]),
                "pct": _num(row["pct"]),
                "amountYi": yuan_to_yi(row["amount"]) if row.get("amount") is not None else None,
                "circMvYi": circ_yi,
                "turnover": _num(row["turnover_rate"]),
                "sealYi": yuan_to_yi(row["seal_amount"]) if row.get("seal_amount") is not None else None,
                "firstSeal": str(row["first_seal_time"] or "")[:8],
                "lastSeal": str(row["last_seal_time"] or "")[:8],
                "breakTimes": row.get("break_times"),
                "boardDays": row.get("board_days"),
                "industry": row.get("industry") or "",
                "theme": row.get("theme") or "",
                "reason": clip_line(row.get("reason") or "", 40),
            })
        return out

    data["ztPool"] = pool("zt_pool", 80)
    data["zbPool"] = pool("zb_pool", 40)
    data["dtPool"] = pool("dt_pool", 40)
    if not data["ztPool"]:
        gaps.append("涨停池还没有")
    # 情绪表里涨停数字常空，用池子补上
    sent = data.get("sentiment") or {}
    if sent.get("limitUp") is None and data["ztPool"]:
        sent["limitUp"] = len(data["ztPool"])
    if sent.get("limitDown") is None and data["dtPool"]:
        sent["limitDown"] = len(data["dtPool"])
    if sent.get("maxBoard") is None and data["ztPool"]:
        boards = [r.get("boardDays") for r in data["ztPool"] if r.get("boardDays") is not None]
        if boards:
            sent["maxBoard"] = max(boards)
    if sent.get("brokenRate") is None and data["ztPool"]:
        broken = sum(1 for r in data["ztPool"] if (r.get("breakTimes") or 0) > 0)
        sent["brokenRate"] = _num(100.0 * broken / len(data["ztPool"]), 1)
    data["sentiment"] = sent

    sectors_up = _try(
        """
        SELECT sector_name AS name, pct, main_net_inflow, up_cnt, down_cnt
        FROM sector_daily WHERE date = %s AND pct IS NOT NULL
        ORDER BY pct DESC NULLS LAST LIMIT 12
        """,
        [day],
    ) or []
    sectors_down = _try(
        """
        SELECT sector_name AS name, pct, main_net_inflow
        FROM sector_daily WHERE date = %s AND pct IS NOT NULL
        ORDER BY pct ASC NULLS LAST LIMIT 12
        """,
        [day],
    ) or []
    sectors_flow = _try(
        """
        SELECT sector_name AS name, pct, main_net_inflow, turnover
        FROM sector_daily WHERE date = %s AND main_net_inflow IS NOT NULL
        ORDER BY main_net_inflow DESC NULLS LAST LIMIT 12
        """,
        [day],
    ) or []
    data["sectors"] = {
        "gainers": [{
            "name": r["name"], "pct": _num(r["pct"]),
            "inflowYi": yuan_to_yi(r.get("main_net_inflow")),
            "up": r.get("up_cnt"), "down": r.get("down_cnt"),
        } for r in sectors_up],
        "losers": [{
            "name": r["name"], "pct": _num(r["pct"]),
            "inflowYi": yuan_to_yi(r.get("main_net_inflow")),
        } for r in sectors_down],
        "inflow": [{
            "name": r["name"], "pct": _num(r["pct"]),
            "inflowYi": yuan_to_yi(r.get("main_net_inflow")),
            "amountYi": yuan_to_yi(r.get("turnover")),
        } for r in sectors_flow],
    }

    leaders_up = _try(
        """
        SELECT code, name, pct, amount
        FROM stock_daily WHERE date = %s AND pct IS NOT NULL
        ORDER BY pct DESC NULLS LAST LIMIT 15
        """,
        [day],
    ) or []
    leaders_down = _try(
        """
        SELECT code, name, pct, amount
        FROM stock_daily WHERE date = %s AND pct IS NOT NULL
        ORDER BY pct ASC NULLS LAST LIMIT 15
        """,
        [day],
    ) or []
    data["leaders"] = {
        "up": [{"code": r["code"], "name": r["name"], "pct": _num(r["pct"]), "amountYi": yuan_to_yi(r.get("amount"))} for r in leaders_up],
        "down": [{"code": r["code"], "name": r["name"], "pct": _num(r["pct"]), "amountYi": yuan_to_yi(r.get("amount"))} for r in leaders_down],
    }

    auction = _try(
        """
        SELECT code, name, jjzf, ssbk, jjje
        FROM bidding_list
        WHERE date = %s AND quotations_type = 9
        ORDER BY jjzf DESC NULLS LAST
        LIMIT 20
        """,
        [day],
    ) or []
    data["auction"] = [{
        "code": r["code"],
        "name": r["name"],
        "pct": _num(r["jjzf"]),
        "sector": r.get("ssbk") or "",
        "amountYi": yuan_to_yi(r.get("jjje")) if r.get("jjje") is not None else None,
    } for r in auction]

    live = _try(
        """
        SELECT ts, event_id, event_type, title, content, extra
        FROM radar_event
        WHERE ts::date = %s AND source = 'kaipanla_zhibo'
        ORDER BY ts DESC
        LIMIT 40
        """,
        [day],
    ) or []
    data["live"] = []
    for row in live:
        extra = row["extra"] if isinstance(row["extra"], dict) else {}
        data["live"].append({
            "id": row["event_id"],
            "time": _clock(row["ts"]),
            "plate": (extra.get("stock_name") or row["event_type"] or "").strip(),
            "pct": extra.get("lb_status") or "",
            "content": row["content"] or "",
            "stocks": extra.get("stocks") or [],
        })
    if not data["live"]:
        gaps.append("大盘直播还没有")

    messages = _try(
        """
        SELECT msg_ts, msg_id, title, content, source
        FROM market_messages
        WHERE msg_ts::date = %s
        ORDER BY msg_ts DESC
        LIMIT 30
        """,
        [day],
    ) or []
    data["messages"] = [{
        "id": r["msg_id"],
        "time": _clock(r["msg_ts"]),
        "title": r.get("title") or "",
        "content": clip_line(r.get("content") or r.get("title") or "", 120),
        "source": r.get("source") or "",
    } for r in messages]

    quotes = _try(
        """
        SELECT code, name, pct, close
        FROM global_daily
        WHERE session = 'close' AND date = (
            SELECT MAX(date) FROM global_daily WHERE date <= %s AND session = 'close'
        )
        ORDER BY code
        """,
        [day],
    ) or []
    data["overnight"] = [{
        "code": r["code"],
        "name": r["name"] or r["code"],
        "pct": _num(r["pct"]),
        "close": _num(r["close"]),
    } for r in quotes if r.get("pct") is not None]

    north = _try(
        """
        SELECT date, total_net, hgt_net, sgt_net, hgt_buy, hgt_sell, sgt_buy, sgt_sell
        FROM northbound_daily
        WHERE date <= %s
        ORDER BY date DESC
        LIMIT 5
        """,
        [day],
    ) or []
    data["northbound"] = [{
        "date": r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"]),
        "netYi": yuan_to_yi(r.get("total_net")),
        "hgtYi": yuan_to_yi(r.get("hgt_net")),
        "sgtYi": yuan_to_yi(r.get("sgt_net")),
        "buyYi": yuan_to_yi((r.get("hgt_buy") or 0) + (r.get("sgt_buy") or 0)),
        "sellYi": yuan_to_yi((r.get("hgt_sell") or 0) + (r.get("sgt_sell") or 0)),
    } for r in north]

    coverage = _try(
        """
        SELECT job, status, note, ts, rows_written, source_used
        FROM ingest_log
        WHERE ts::date = %s
        ORDER BY ts DESC
        LIMIT 50
        """,
        [day],
    ) or []
    data["coverage"] = [{
        "job": r.get("job"),
        "status": r.get("status"),
        "note": clip_line(r.get("note") or "", 60),
        "at": _clock(r.get("ts")),
        "rows": r.get("rows_written"),
        "source": r.get("source_used") or "",
    } for r in coverage]

    tables = [
        ("index_daily", "date"),
        ("stock_daily", "date"),
        ("zt_pool", "date"),
        ("sentiment_daily", "date"),
        ("sector_daily", "date"),
        ("bidding_list", "date"),
        ("radar_event", "ts"),
        ("market_messages", "msg_ts"),
        ("northbound_daily", "date"),
        ("global_daily", "date"),
    ]
    freshness = []
    for table, col in tables:
        rows = _try(f"SELECT max({col}) AS latest, count(*)::int AS n FROM {table}")
        if not rows:
            continue
        latest = rows[0]["latest"]
        freshness.append({
            "table": table,
            "latest": latest.isoformat() if hasattr(latest, "isoformat") else (str(latest) if latest else None),
            "rows": rows[0]["n"],
        })
    data["freshness"] = freshness

    preds = _try(
        """
        SELECT prediction_id, title, status, created_at
        FROM prediction
        ORDER BY created_at DESC
        LIMIT 12
        """,
        mind=True,
    ) or []
    data["predictions"] = [{
        "id": r.get("prediction_id"),
        "title": r.get("title") or "",
        "status": r.get("status") or "",
        "at": _clock(r.get("created_at")),
    } for r in preds]

    cognitions = _try(
        """
        SELECT cognition_id, title, cognition_type, status, confidence
        FROM cognition_current
        WHERE domain = 'investing'
        ORDER BY importance DESC NULLS LAST, cognition_id
        LIMIT 20
        """,
        mind=True,
    ) or []
    data["cognitions"] = [{
        "id": r.get("cognition_id"),
        "title": r.get("title") or "",
        "type": r.get("cognition_type") or "",
        "status": r.get("status") or "",
        "confidence": _num(r.get("confidence"), 2),
    } for r in cognitions]

    topic_n = _try("SELECT count(*)::int AS n FROM topic")
    data["topicCount"] = topic_n[0]["n"] if topic_n else 0

    return _envelope(data, gaps=gaps)
