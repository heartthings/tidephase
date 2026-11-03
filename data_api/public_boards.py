"""Read-only board payloads for the Tidephase DSH plugin.

Browser clients never receive a write token. Layout writes are accepted
only from loopback, and they store a JSON canvas, not market rows.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import psycopg2.extras
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from data_api.board_logic import (
    assign_themes,
    clip_line,
    consecutive_height,
    fold_repeats,
    hour_rail,
    reason_verdict,
    same_push,
    session_ready,
    theme_stage,
    tomorrow_line,
    yuan_to_yi,
)
from data_api.lovetrade_routes import get_reader_conn

logger = logging.getLogger("data-api.boards")
TZ = timezone(timedelta(hours=8))
SPEC_DIR = Path(__file__).resolve().parent.parent / "dsh" / "spec"
SPEC_FILE = Path(__file__).resolve().parent.parent / "data" / "boards" / "spec.json"
router = APIRouter(prefix="/api/public/v1", tags=["public-boards"])

_predict_cache: dict = {}
_predict_inflight: set = set()
_predict_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(TZ)


def _loads(name: str) -> dict:
    path = SPEC_DIR / name
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"missing spec file {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _ok(data, gaps=None, **extra):
    body = {"ok": True, "data": data, "gaps": gaps or []}
    body.update(extra)
    return body


def _query(sql: str, params=None):
    conn = get_reader_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc


def _trade_day(requested: date | None) -> date:
    if requested:
        return requested
    rows = _query(
        """
        SELECT cal_date FROM trade_cal
        WHERE market = 'SSE' AND is_open = 1 AND cal_date <= %s
        ORDER BY cal_date DESC LIMIT 1
        """,
        [_now().date()],
    )
    if rows:
        return rows[0]["cal_date"]
    return _now().date()


def _open_dates(day: date, limit: int = 12) -> list[date]:
    rows = _query(
        """
        SELECT cal_date FROM trade_cal
        WHERE market = 'SSE' AND is_open = 1 AND cal_date <= %s
        ORDER BY cal_date DESC LIMIT %s
        """,
        [day, limit],
    )
    return [row["cal_date"] for row in rows]


def _loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def _clock(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M:%S")
    return ""


def _iso(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


@router.get("/boards/catalog")
def board_catalog():
    return _ok(_loads("catalog.json"))


@router.get("/boards/defaults")
def board_defaults():
    return _ok(_loads("defaults.json"))


@router.get("/boards/spec")
def board_spec_get():
    if SPEC_FILE.exists():
        try:
            saved = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            saved = _loads("defaults.json")
    else:
        saved = _loads("defaults.json")
    return _ok(saved)


@router.put("/boards/spec")
async def board_spec_put(request: Request):
    if not _loopback(request):
        raise HTTPException(status_code=403, detail="spec writes stay on loopback")
    payload = await request.json()
    _validate_spec(payload)
    SPEC_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPEC_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _ok({"saved": True})


def _validate_spec(payload: dict) -> None:
    catalog = _loads("catalog.json")
    allowed = {
        session: {item["type"] for item in items}
        for session, items in catalog["sessions"].items()
    }
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if payload.get("version") != 1 or not isinstance(sessions, dict):
        raise HTTPException(status_code=400, detail="spec version must be 1")
    for session, types in allowed.items():
        canvas = sessions.get(session)
        boards = canvas.get("boards") if isinstance(canvas, dict) else None
        if not isinstance(boards, list):
            raise HTTPException(status_code=400, detail=f"{session} needs boards")
        seen = set()
        for board in boards:
            if not isinstance(board, dict) or board.get("type") not in types:
                raise HTTPException(status_code=400, detail=f"unknown board in {session}")
            if board.get("id") in seen or not board.get("id"):
                raise HTTPException(status_code=400, detail="board id must be unique")
            seen.add(board["id"])
            for key, low, high in (("w", 220, 2400), ("h", 120, 1600), ("x", 0, 8000), ("y", 0, 8000)):
                value = board.get(key)
                if not isinstance(value, (int, float)) or not low <= float(value) <= high:
                    raise HTTPException(status_code=400, detail=f"{key} out of range")


@router.get("/preopen/messages")
def preopen_messages(date_str: str | None = Query(default=None, alias="date")):
    day = _trade_day(_parse_day(date_str))
    start = datetime.combine(day - timedelta(days=1), time(8, 0), TZ)
    end = datetime.combine(day, time(8, 0), TZ)
    rows = _query(
        """
        SELECT msg_ts, msg_id, title, content, source, code
        FROM market_messages
        WHERE msg_ts >= %s AND msg_ts < %s
        ORDER BY msg_ts DESC
        LIMIT 400
        """,
        [start, end],
    )
    themes = [
        row["sector_name"]
        for row in _query(
            """
            SELECT DISTINCT sector_name
            FROM stock_sector_map
            WHERE kind = 'theme' AND sector_code LIKE '801%%'
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to > %s)
              AND char_length(sector_name) BETWEEN 2 AND 12
            """,
            [day, day],
        )
    ]
    stamped = fold_repeats([{
        "id": row["msg_id"],
        "msg_ts": row["msg_ts"],
        "time": _clock(row["msg_ts"]),
        "title": row["title"] or "",
        "content": clip_line(row["content"] or row["title"], 80),
        "source": row["source"] or "",
    } for row in rows])
    rail = hour_rail(stamped)
    cards = assign_themes(stamped, themes)
    for card in cards:
        for item in card["items"]:
            item["msg_ts"] = _iso(item.get("msg_ts"))
    return _ok({
        "date": day.isoformat(),
        "window": [start.isoformat(), end.isoformat()],
        "rail": rail,
        "cards": cards,
        "total": len(stamped),
    })


@router.get("/preopen/overnight")
def preopen_overnight(date_str: str | None = Query(default=None, alias="date")):
    day = _trade_day(_parse_day(date_str))
    rows = _query(
        """
        SELECT date, code, name, pct
        FROM global_daily
        WHERE date = (
            SELECT MAX(date) FROM global_daily WHERE date <= %s
        )
        ORDER BY ABS(pct) DESC NULLS LAST
        LIMIT 16
        """,
        [day],
    )
    quotes = []
    gaps = []
    for row in rows:
        if row["pct"] is None:
            gaps.append(row["name"] or row["code"])
            continue
        quotes.append({
            "code": row["code"],
            "name": row["name"] or row["code"],
            "pct": round(float(row["pct"]), 2),
            "date": row["date"].isoformat(),
        })
    if not quotes:
        gaps.append("外盘这一日没有数")
    return _ok({"date": day.isoformat(), "quotes": quotes}, gaps=gaps)


@router.get("/intraday/radar")
def intraday_radar(date_str: str | None = Query(default=None, alias="date"), limit: int = Query(default=80, le=200)):
    day = _trade_day(_parse_day(date_str))
    rows = _query(
        """
        SELECT ts, event_id, event_type, title, content, extra
        FROM radar_event
        WHERE ts::date = %s
        ORDER BY ts DESC
        LIMIT %s
        """,
        [day, limit],
    )
    events = []
    for row in rows:
        extra = row["extra"] if isinstance(row["extra"], dict) else {}
        events.append({
            "id": row["event_id"],
            "time": _clock(row["ts"]),
            "stockName": extra.get("stock_name") or row["title"] or "",
            "lbStatus": extra.get("lb_status") or row["event_type"] or "",
            "status": extra.get("status") or "",
            "content": clip_line(row["content"] or row["title"], 72),
        })
    gaps = [] if events else ["这一天还没有雷达事件"]
    return _ok({"date": day.isoformat(), "events": events}, gaps=gaps)


@router.get("/intraday/dynamics")
def intraday_dynamics(date_str: str | None = Query(default=None, alias="date"), limit: int = Query(default=80, le=200)):
    day = _trade_day(_parse_day(date_str))
    rows = _query(
        """
        SELECT msg_ts, msg_id, code, title, content
        FROM market_messages
        WHERE msg_ts::date = %s
          AND (msg_ts::time >= TIME '09:15' AND msg_ts::time <= TIME '15:05')
        ORDER BY msg_ts DESC
        LIMIT %s
        """,
        [day, limit],
    )
    items = [{
        "id": row["msg_id"],
        "time": _clock(row["msg_ts"]),
        "stock": row["code"] or "",
        "comment": clip_line(row["content"] or row["title"], 72),
    } for row in rows]
    gaps = [] if items else ["这一天的盘中动态还没有数"]
    return _ok({"date": day.isoformat(), "items": items}, gaps=gaps)


INDEX_NAMES = {
    "sh000001": "上证",
    "sz399001": "深成",
    "sz399006": "创业板",
    "sh000300": "沪深300",
    "sh000016": "上证50",
    "sh000688": "科创50",
}


def _try(sql: str, params=None):
    try:
        return _query(sql, params)
    except Exception as exc:
        logger.info("board query skipped: %s", exc.__class__.__name__)
        return None


def _num(value, digits: int = 2):
    if value is None:
        return None
    return round(float(value), digits)


@router.get("/intraday/tape")
def intraday_tape(date_str: str | None = Query(default=None, alias="date")):
    """盘中行情看板。把指数、涨跌分布、分钟、小时成交、板块、领涨领跌、竞价、快讯和覆盖收成一份。"""
    day = _trade_day(_parse_day(date_str))
    gaps: list[str] = []
    data: dict = {"date": day.isoformat()}

    index_rows = _try(
        """
        SELECT code, name, close, pct
        FROM index_daily
        WHERE date = %s AND code = ANY(%s)
        ORDER BY code
        """,
        [day, list(INDEX_NAMES)],
    )
    if index_rows is None:
        gaps.append("指数日线还没有")
    else:
        data["indices"] = [{
            "code": row["code"],
            "name": INDEX_NAMES.get(row["code"], row["name"] or row["code"]),
            "close": _num(row["close"], 2),
            "pct": _num(row["pct"], 2),
        } for row in index_rows]
        if not data["indices"]:
            gaps.append("这一天的指数还没有收盘")

    breadth = _try(
        """
        SELECT
          count(*) FILTER (WHERE pct > 0)::int AS up_n,
          count(*) FILTER (WHERE pct < 0)::int AS down_n,
          count(*) FILTER (WHERE pct = 0)::int AS flat_n,
          count(*) FILTER (WHERE pct >= 9.5)::int AS limit_up_zone,
          count(*) FILTER (WHERE pct >= 3 AND pct < 9.5)::int AS strong_n,
          count(*) FILTER (WHERE pct > 0 AND pct < 3)::int AS up_soft,
          count(*) FILTER (WHERE pct < 0 AND pct > -3)::int AS down_soft,
          count(*) FILTER (WHERE pct <= -3 AND pct > -9.5)::int AS weak_n,
          count(*) FILTER (WHERE pct <= -9.5)::int AS limit_down_zone
        FROM stock_daily WHERE date = %s
        """,
        [day],
    )
    if not breadth:
        gaps.append("涨跌家数还没有")
    else:
        row = breadth[0]
        data["breadth"] = {
            "up": row["up_n"] or 0,
            "down": row["down_n"] or 0,
            "flat": row["flat_n"] or 0,
            "buckets": [
                {"label": "涨停附近", "count": row["limit_up_zone"] or 0},
                {"label": "强势", "count": row["strong_n"] or 0},
                {"label": "小涨", "count": row["up_soft"] or 0},
                {"label": "小跌", "count": row["down_soft"] or 0},
                {"label": "弱势", "count": row["weak_n"] or 0},
                {"label": "跌停附近", "count": row["limit_down_zone"] or 0},
            ],
        }

    sentiment_rows = _try("SELECT * FROM sentiment_daily WHERE date = %s", [day])
    pool_n = _try("SELECT count(*)::int AS n, max(board_days)::int AS height FROM zt_pool WHERE date = %s", [day])
    broken_n = _try("SELECT count(*)::int AS n FROM zb_pool WHERE date = %s", [day])
    down_n = _try("SELECT count(*)::int AS n FROM dt_pool WHERE date = %s", [day])
    if sentiment_rows or pool_n:
        sentiment = sentiment_rows[0] if sentiment_rows else {}
        data["sentiment"] = {
            "limitUp": (pool_n[0]["n"] if pool_n else None),
            "broken": (broken_n[0]["n"] if broken_n else None),
            "maxBoard": (pool_n[0]["height"] if pool_n else None),
            "limitDown": (down_n[0]["n"] if down_n else None),
            "sealRate": _num(sentiment.get("dbcgl"), 2),
            "premium": _num(sentiment.get("dbyll"), 2),
        }

    minute_rows = _try(
        """
        SELECT code, close
        FROM index_minute
        WHERE freq = '1m' AND code = ANY(%s)
          AND ts >= %s AND ts < %s::date + INTERVAL '1 day'
        ORDER BY code, ts
        """,
        [["sh000001", "sz399001", "sz399006"], day, day],
    )
    if minute_rows is None:
        gaps.append("指数分钟还没有")
    else:
        grouped: dict[str, list] = {}
        for row in minute_rows:
            grouped.setdefault(row["code"], []).append(row["close"])
        data["minutes"] = []
        for code, closes in grouped.items():
            step = max(1, len(closes) // 48)
            data["minutes"].append({
                "code": code,
                "name": INDEX_NAMES.get(code, code),
                "points": [_num(value, 2) for value in closes[::step]],
            })
        if not data["minutes"]:
            gaps.append("这一天还没有指数分钟")

    hour_rows = _try(
        """
        SELECT to_char(ts AT TIME ZONE 'Asia/Shanghai', 'HH24:MI') AS slot,
               code, volume, amount
        FROM index_hour
        WHERE (ts AT TIME ZONE 'Asia/Shanghai')::date = %s
          AND code = ANY(%s)
        ORDER BY ts, code
        """,
        [day, ["sh000001", "sz399001", "sz399006"]],
    )
    if hour_rows is None:
        gaps.append("指数小时成交还没有")
    else:
        slots: dict[str, dict] = {}
        for row in hour_rows:
            cell = slots.setdefault(row["slot"], {"slot": row["slot"]})
            prefix = {"sh000001": "sh", "sz399001": "sz", "sz399006": "cy"}[row["code"]]
            cell[prefix + "Volume"] = _num(float(row["volume"] or 0) / 1e8, 2)
            cell[prefix + "Amount"] = _num(float(row["amount"] or 0) / 1e8, 0)
        data["hours"] = list(slots.values())
        if not data["hours"]:
            gaps.append("这一天还没有小时成交")

    def _sectors(order: str, column: str):
        return _try(
            f"""
            SELECT sector_name AS name, {column} AS value
            FROM sector_daily
            WHERE date = %s AND {column} IS NOT NULL
            ORDER BY {column} {order} NULLS LAST
            LIMIT 8
            """,
            [day],
        )

    gainers = _sectors("DESC", "pct")
    losers = _sectors("ASC", "pct")
    inflow = _sectors("DESC", "main_net_inflow")
    if gainers is None and losers is None and inflow is None:
        gaps.append("板块日线还没有")
    else:
        data["sectors"] = {
            "gainers": [{"name": row["name"], "pct": _num(row["value"], 2)} for row in (gainers or [])],
            "losers": [{"name": row["name"], "pct": _num(row["value"], 2)} for row in (losers or [])],
            "inflow": [{"name": row["name"], "yi": yuan_to_yi(row["value"])} for row in (inflow or [])],
        }

    def _leaders(order: str):
        return _try(
            """
            SELECT code, name, pct
            FROM stock_daily
            WHERE date = %s AND pct IS NOT NULL
            ORDER BY pct """ + order + """ NULLS LAST
            LIMIT 8
            """,
            [day],
        )

    ups = _leaders("DESC")
    downs = _leaders("ASC")
    if ups is None and downs is None:
        gaps.append("个股涨跌还没有")
    else:
        data["leaders"] = {
            "up": [{"code": row["code"], "name": row["name"], "pct": _num(row["pct"], 2)} for row in (ups or [])],
            "down": [{"code": row["code"], "name": row["name"], "pct": _num(row["pct"], 2)} for row in (downs or [])],
        }

    auction_rows = _try(
        """
        SELECT code, name, jjzf, ssbk
        FROM bidding_list
        WHERE date = %s AND quotations_type = 9
        ORDER BY jjzf DESC NULLS LAST
        LIMIT 12
        """,
        [day],
    )
    if auction_rows is None:
        gaps.append("竞价还没有")
    else:
        data["auction"] = [{
            "code": row["code"],
            "name": row["name"],
            "pct": _num(row["jjzf"], 2),
            "sector": row["ssbk"] or "",
        } for row in auction_rows]

    quote_rows = _try(
        """
        SELECT code, name, pct FROM global_daily
        WHERE session = 'close' AND date = (
            SELECT MAX(date) FROM global_daily WHERE date <= %s AND session = 'close'
        )
        ORDER BY code
        """,
        [day],
    )
    if quote_rows:
        data["quotes"] = [{
            "code": row["code"],
            "name": row["name"] or row["code"],
            "pct": _num(row["pct"], 2),
        } for row in quote_rows if row["pct"] is not None]

    news_rows = _try(
        """
        SELECT msg_ts, title, source
        FROM market_messages
        WHERE msg_ts::date = %s
        ORDER BY msg_ts DESC
        LIMIT 16
        """,
        [day],
    )
    if news_rows:
        data["headlines"] = [{
            "time": _clock(row["msg_ts"]),
            "title": clip_line(row["title"], 72),
            "source": row["source"] or "",
        } for row in news_rows]

    wire_rows = _try(
        """
        SELECT pub_ts, title, media
        FROM news_telegraph
        ORDER BY pub_ts DESC
        LIMIT 12
        """
    )
    if wire_rows:
        data["wires"] = [{
            "time": _clock(row["pub_ts"]),
            "title": clip_line(row["title"], 72),
            "source": row["media"] or "",
        } for row in wire_rows]

    catalyst_rows = _try(
        """
        SELECT date, impact_level, left(message_summary, 72) AS summary
        FROM catalyst_impact
        ORDER BY message_time DESC NULLS LAST
        LIMIT 8
        """
    )
    if catalyst_rows:
        data["catalysts"] = [{
            "date": _iso(row["date"])[:10],
            "level": row["impact_level"] or "",
            "summary": row["summary"] or "",
        } for row in catalyst_rows]

    result_rows = _try("SELECT result, count(*)::int AS n FROM prediction GROUP BY result ORDER BY n DESC")
    recent_rows = _try(
        """
        SELECT category, result, left(statement, 48) AS statement
        FROM prediction
        ORDER BY created_at DESC
        LIMIT 6
        """
    )
    if result_rows is not None or recent_rows is not None:
        data["predictions"] = {
            "results": [{"result": row["result"] or "未核对", "count": row["n"]} for row in (result_rows or [])],
            "recent": [{
                "category": row["category"] or "",
                "result": row["result"] or "",
                "statement": row["statement"] or "",
            } for row in (recent_rows or [])],
        }

    cover_sql = """
        SELECT %s AS name, count(*)::int AS rows, max({col})::text AS latest FROM {table}
    """
    cover_targets = [
        ("指数日线", "index_daily", "date"),
        ("个股日线", "stock_daily", "date"),
        ("涨停池", "zt_pool", "date"),
        ("板块日线", "sector_daily", "date"),
        ("指数分钟", "index_minute", "ts"),
        ("快讯", "market_messages", "msg_ts"),
    ]
    coverage = []
    for label, table, column in cover_targets:
        rows = _try(cover_sql.format(col=column, table=table), [label])
        if rows:
            coverage.append({"name": label, "rows": rows[0]["rows"], "latest": (rows[0]["latest"] or "")[:19]})
    if coverage:
        data["coverage"] = coverage
    job_rows = _try(
        """
        SELECT job, status, count(*)::int AS n, to_char(max(ts), 'MM-DD HH24:MI') AS last
        FROM ingest_log
        WHERE ts > now() - interval '24 hours'
        GROUP BY job, status
        ORDER BY max(ts) DESC
        LIMIT 12
        """
    )
    if job_rows:
        data["jobs"] = [{
            "job": row["job"],
            "status": row["status"],
            "count": row["n"],
            "last": row["last"],
        } for row in job_rows]

    return _ok(data, gaps=gaps)


@router.get("/afterclose/review")
def afterclose_review(date_str: str | None = Query(default=None, alias="date")):
    day = _trade_day(_parse_day(date_str))
    gaps: list[str] = []
    opens = _open_dates(day, 12)
    if not opens:
        opens = [day]
    pools = _query(
        """
        SELECT date, code, name, theme, reason, first_seal_time, pct
        FROM zt_pool
        WHERE date = ANY(%s)
        """,
        [opens],
    )
    broken_rows = _query(
        "SELECT code, name, industry FROM zb_pool WHERE date = %s",
        [day],
    )
    down_rows = _query(
        "SELECT code, name, industry, reason FROM dt_pool WHERE date = %s",
        [day],
    ) if _has_column("dt_pool", "reason") else _query(
        "SELECT code, name, industry FROM dt_pool WHERE date = %s",
        [day],
    )
    sentiment_rows = _query("SELECT * FROM sentiment_daily WHERE date = %s", [day])
    sentiment = sentiment_rows[0] if sentiment_rows else {}
    index_rows = _query(
        """
        SELECT code, name, close, pct FROM index_daily
        WHERE date = %s AND code IN ('sh000001', 'sz399006', 'sz399001')
        """,
        [day],
    )
    by_code_dates: dict[str, set[date]] = {}
    today = []
    for row in pools:
        by_code_dates.setdefault(row["code"], set()).add(row["date"])
        if row["date"] == day:
            today.append(row)
    height_of = {
        code: consecutive_height(opens, days)
        for code, days in by_code_dates.items()
        if day in days
    }
    codes = [row["code"] for row in today]
    theme_map = _sector_map(day, codes, "theme")
    industry_map = _sector_map(day, codes, "industry")
    themes = _build_themes(today, height_of, theme_map, broken_rows, "theme")
    industries = _build_themes(today, height_of, industry_map, broken_rows, "industry")
    limit_up = int(sentiment.get("limit_up") or len(today))
    limit_down = int(sentiment.get("limit_down") or len(down_rows))
    broken = len(broken_rows)
    max_board = max(height_of.values(), default=int(sentiment.get("max_board") or 0))
    seal_rate = sentiment.get("dbcgl")
    if seal_rate is None and (limit_up or broken):
        seal_rate = round(limit_up / max(limit_up + broken, 1) * 100, 1)
    premium = sentiment.get("dbyll")
    ready = session_ready(day, _now(), len(today))
    if not ready:
        gaps.append("尚未收齐")
    flow = _money(day)
    if not flow["inflow"] and not flow["outflow"]:
        gaps.append("题材资金这一天没有数")
    candidates, predict_gaps = _candidates(day)
    gaps.extend(predict_gaps)
    line = tomorrow_line(limit_up, broken, float(seal_rate) if seal_rate is not None else None)
    return _ok({
        "date": day.isoformat(),
        "ready": ready,
        "sentiment": {
            "limitUp": limit_up,
            "broken": broken,
            "maxBoard": max_board,
            "limitDown": limit_down,
            "sealRate": None if seal_rate is None else round(float(seal_rate), 1),
            "premium": None if premium is None else round(float(premium), 2),
            "index": [
                {"code": row["code"], "name": row["name"], "pct": None if row["pct"] is None else round(float(row["pct"]), 2)}
                for row in index_rows
            ],
        },
        "themes": themes[:12],
        "industries": [{"name": item["name"], "count": item["count"]} for item in industries[:8]],
        "reasons": [
            {"name": item["name"], "verdict": item["verdict"], "line": item["line"], "count": item["count"]}
            for item in themes[:12]
        ],
        "money": flow,
        "limitCards": {
            "up": _limit_cards(today, height_of, theme_map, up=True)[:24],
            "down": _down_cards(down_rows)[:12],
        },
        "candidates": candidates,
        "fulfillment": _fulfillment(),
        "tomorrow": line,
    }, gaps=gaps)


def _has_column(table: str, column: str) -> bool:
    rows = _query(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        [table, column],
    )
    return bool(rows)


def _sector_map(day: date, codes: list[str], kind: str) -> dict[str, list[dict]]:
    if not codes:
        return {}
    like = " AND sector_code LIKE '801%%'" if kind == "theme" else ""
    rows = _query(
        f"""
        SELECT code, sector_code, sector_name
        FROM stock_sector_map
        WHERE kind = %s
          AND code = ANY(%s)
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to > %s)
          {like}
        """,
        [kind, codes, day, day],
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["code"], []).append(row)
    return grouped


def _build_themes(today, height_of, sector_of, broken_rows, kind: str) -> list[dict]:
    broken_codes = {row["code"] for row in broken_rows}
    groups: dict[str, dict] = {}
    for row in today:
        sectors = sector_of.get(row["code"]) or [{"sector_name": "未归类", "sector_code": ""}]
        # One stock can wear many labels. The reason check marks pocket labels.
        for sector in sectors[:4]:
            name = sector["sector_name"] or "未归类"
            node = groups.setdefault(name, {
                "name": name,
                "count": 0,
                "height": 0,
                "broken": 0,
                "reasons": [],
                "seals": [],
            })
            node["count"] += 1
            node["height"] = max(node["height"], height_of.get(row["code"], 1))
            if row["code"] in broken_codes:
                node["broken"] += 1
            note = row.get("reason") or row.get("theme") or ""
            if note:
                node["reasons"].append(note)
            node["seals"].append(row.get("first_seal_time"))
    items = []
    for node in groups.values():
        verdict, line = reason_verdict(node["name"], node["reasons"])
        stage = theme_stage(node["height"], node["count"], 0, node["broken"])
        items.append({
            "name": node["name"],
            "count": node["count"],
            "height": node["height"],
            "stage": stage,
            "verdict": verdict,
            "line": line,
            "push": same_push(node["seals"]),
            "kind": kind,
        })
    items.sort(key=lambda item: (item["verdict"] != "成立", -item["count"], -item["height"]))
    return items


def _limit_cards(today, height_of, theme_map, up: bool) -> list[dict]:
    cards = []
    for row in sorted(today, key=lambda item: -height_of.get(item["code"], 0)):
        themes = theme_map.get(row["code"]) or []
        theme = themes[0]["sector_name"] if themes else "未归类"
        group_rows = [item for item in today if any(
            sector["sector_name"] == theme for sector in (theme_map.get(item["code"]) or [])
        )]
        cards.append({
            "name": row["name"] or row["code"],
            "code": row["code"],
            "theme": theme,
            "height": height_of.get(row["code"], 1),
            "push": same_push([item.get("first_seal_time") for item in group_rows]),
            "line": clip_line(row.get("reason") or row.get("theme") or "没有", 28) or "没有",
            "side": "up" if up else "down",
        })
    return cards


def _down_cards(rows) -> list[dict]:
    cards = []
    for row in rows:
        cards.append({
            "name": row.get("name") or row["code"],
            "code": row["code"],
            "theme": row.get("industry") or "未归类",
            "height": 1,
            "push": "主力",
            "line": clip_line(row.get("reason") or "没有", 28) or "没有",
            "side": "down",
        })
    return cards


def _money(day: date) -> dict:
    rows = _query(
        """
        SELECT sector_name, main_net_inflow
        FROM fund_flow_sector
        WHERE date = %s AND kind = 'concept' AND main_net_inflow IS NOT NULL
        """,
        [day],
    )
    ranked = sorted(rows, key=lambda row: float(row["main_net_inflow"]))
    outflow = [{"name": row["sector_name"], "yi": yuan_to_yi(row["main_net_inflow"])} for row in ranked[:8] if float(row["main_net_inflow"]) < 0]
    inflow = [{"name": row["sector_name"], "yi": yuan_to_yi(row["main_net_inflow"])} for row in reversed(ranked[-8:]) if float(row["main_net_inflow"]) > 0]
    return {"inflow": inflow, "outflow": outflow}


def _candidates(day: date) -> tuple[dict, list[str]]:
    key = day.isoformat()
    with _predict_lock:
        cached = _predict_cache.get(key)
        if cached and (_now().timestamp() - cached["ts"]) < 1800:
            return cached["data"], cached["gaps"]
        start = key not in _predict_inflight
        if start:
            _predict_inflight.add(key)
    if not start:
        return {"first": [], "second": []}, ["次日候选还在计算"]

    def run():
        data = {"first": [], "second": []}
        gaps = ["次日候选这次没有算出来"]
        try:
            from data_api.predict_limitup import get_conn as predict_conn, predict as predict_next
            conn = predict_conn()
            try:
                result = predict_next(conn, day, 12, 8)
            finally:
                conn.close()
            data = {
                "first": _slim_groups(result.get("first_board", {}).get("groups")),
                "second": _slim_groups(result.get("second_board", {}).get("groups")),
            }
            gaps = [clip_line(item, 48) for item in (result.get("gaps") or [])[:3]]
        except Exception as exc:
            logger.warning("predict_limitup skipped: %s", exc)
        with _predict_lock:
            _predict_cache[key] = {"ts": _now().timestamp(), "data": data, "gaps": gaps}
            _predict_inflight.discard(key)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(12)
    with _predict_lock:
        cached = _predict_cache.get(key)
    if cached:
        return cached["data"], cached["gaps"]
    return {"first": [], "second": []}, ["次日候选还在计算"]


def _slim_groups(groups) -> list[dict]:
    slim = []
    for group in groups or []:
        people = []
        for item in (group.get("candidates") or [])[:6]:
            people.append({
                "name": item.get("name") or "",
                "code": item.get("code") or "",
                "prob": item.get("prob"),
            })
        slim.append({"theme": group.get("theme") or "未归类", "people": people})
    return slim[:6]


def _fulfillment() -> dict:
    try:
        rows = _query(
            """
            SELECT p.check_date, p.falsify->>'name' AS name, p.falsify->>'code' AS code,
                   p.confidence_pct, p.result, p.falsify->>'theme' AS theme
            FROM prediction p
            WHERE p.category IN ('first_board', 'second_board')
              AND p.result IN ('hit', 'miss')
              AND p.check_date >= CURRENT_DATE - 20
            ORDER BY p.check_date DESC, p.confidence_pct DESC
            LIMIT 20
            """
        )
    except Exception:
        return {"shown": [], "quietMisses": 0}
    shown = []
    quiet = 0
    for row in rows:
        prob = int(row["confidence_pct"] or 0)
        if row["result"] == "miss" and prob < 10:
            quiet += 1
            continue
        bars = []
        if row["code"]:
            series = _query(
                """
                SELECT pct FROM stock_daily
                WHERE code = %s AND date <= %s
                ORDER BY date DESC LIMIT 8
                """,
                [row["code"], row["check_date"]],
            )
            bars = [None if item["pct"] is None else round(float(item["pct"]), 2) for item in reversed(series)]
        if len(shown) < 6:
            shown.append({
                "name": row["name"] or row["code"] or "未命名",
                "theme": row["theme"] or "",
                "prob": prob,
                "result": row["result"],
                "bars": bars,
            })
        elif row["result"] == "miss" and prob < 10:
            quiet += 1
    return {"shown": shown, "quietMisses": quiet}
