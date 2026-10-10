"""
data-api · FastAPI 实装
E1-E7/E15/E16/E19（M1 部分）+ Bearer token 三档鉴权
§5.1/§5.2 · 造物评审 21 条"必须"项已应用

绑定 127.0.0.1:8787，永不公网。
"""
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

import yaml
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Depends, Request, Query, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, StreamingResponse
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("data-api")

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"
TZ_CST = timezone(timedelta(hours=8))

# ─── Config ────────────────────────────────────────────────────────────

def load_secrets() -> dict:
    if SECRETS_PATH.exists():
        with open(SECRETS_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}

def load_meta() -> dict:
    """表白名单 + 字段元数据。"""
    return {
        "allowed_tables": [
            "trade_cal", "session_def",
            "index_daily", "index_minute",
            "stock_daily", "stock_minute", "etf_daily",
            "zt_pool", "zb_pool", "dt_pool", "yzt_pool",
            "sentiment_daily", "bidding_list",
            "global_daily", "global_minute",
            "fund_flow_stock", "fund_flow_sector",
            "northbound_daily", "northbound_intraday",
            "margin_daily", "margin_stock",
            "block_trade", "dragon_tiger",
            "holder_num", "lockup_calendar", "dividend", "share_structure",
            "sector_daily", "stock_sector_map", "theme_heat",
            "macro_indicators", "policy_calendar", "earnings_calendar",
            "financial_reports", "finance_snapshot", "f10_text",
            "consensus_eps", "research_reports", "valuation_daily",
            "news_telegraph", "stock_news", "announcements", "market_messages",
            "option_contracts", "option_tquote", "option_greeks_iv",
            "cognition", "prediction", "base_rate", "calibration_view",
            "instrument_master", "watchlist",
            "ingest_log", "quarantine", "job_registry",
            "verify_source", "verify_diff",
        ],
        "code_aliases": {
            "KS11": "KOSPI",
            "N225": "NK225",
        }
    }

META = load_meta()

# ─── DB connections ────────────────────────────────────────────────────

_reader_pool = None
_d12writer_pool = None

def get_reader_conn():
    secrets = load_secrets()
    db = secrets.get("database", {})
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "market-tsdb"),
        port=int(os.getenv("MARKET_TSDB_PORT", "5432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER_READER", "duser_reader"),
        password=db.get("duser_reader_password", ""),
        options="-c statement_timeout=30s",
    )

def get_d12writer_conn():
    secrets = load_secrets()
    db = secrets.get("database", {})
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "market-tsdb"),
        port=int(os.getenv("MARKET_TSDB_PORT", "5432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER_D12WRITER", "duser_d12writer"),
        password=db.get("duser_d12writer_password", ""),
    )

# ─── Auth ──────────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail={"code": "AUTH", "msg": "Missing bearer token"})
    secrets = load_secrets()
    api_cfg = secrets.get("api", {})
    token = credentials.credentials
    valid_tokens = {
        api_cfg.get("bearer_token_read", ""): "read",
        api_cfg.get("bearer_token_write", ""): "write",
        api_cfg.get("bearer_token_admin", ""): "admin",
    }
    role = valid_tokens.get(token)
    if not role:
        raise HTTPException(status_code=401, detail={"code": "AUTH", "msg": "Invalid token"})
    return role

def require_read(role: str = Depends(verify_token)) -> str:
    if role not in ("read", "write", "admin"):
        raise HTTPException(status_code=403, detail={"code": "AUTH", "msg": "Insufficient permissions"})
    return role

def require_write(role: str = Depends(verify_token)) -> str:
    if role not in ("write", "admin"):
        raise HTTPException(status_code=403, detail={"code": "AUTH", "msg": "Write permission required"})
    return role

def require_admin(role: str = Depends(verify_token)) -> str:
    if role != "admin":
        raise HTTPException(status_code=403, detail={"code": "AUTH", "msg": "Admin permission required"})
    return role

# ─── Response envelope ─────────────────────────────────────────────────

def envelope(data: Any, rows: int = None, next_cursor: str = None) -> dict:
    return {
        "data": data,
        "meta": {
            "rows": rows or (len(data) if isinstance(data, list) else 1),
            "next_cursor": next_cursor,
            "server_ts": datetime.now(TZ_CST).isoformat(),
            "request_id": str(uuid.uuid4()),
        }
    }

def error_response(code: str, msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "msg": msg, "request_id": str(uuid.uuid4())}}
    )

# ─── App ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 data-api starting on 127.0.0.1:8787")
    yield
    logger.info("data-api shutting down")

app = FastAPI(
    title="观势数据层 API",
    version="1.0.0",
    description="观势数据层 REST API · E1-E19 端点 · Bearer token 三档鉴权",
    lifespan=lifespan,
)

# ─── E1 /health ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        conn = get_reader_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception as e:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "server_ts": datetime.now(TZ_CST).isoformat(),
    }

# ─── E2 /meta/tables ──────────────────────────────────────────────────

@app.get("/meta/tables")
async def meta_tables(domain: str = None, _=Depends(require_read)):
    tables = META["allowed_tables"]
    if domain:
        # Filter by domain prefix (simplified)
        pass
    return envelope(tables)

# ─── E3 /meta/trade_cal ───────────────────────────────────────────────

@app.get("/meta/trade_cal")
async def trade_cal(
    market: str = "CN",
    start: str = None,
    end: str = None,
    _=Depends(require_read)
):
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT market, cal_date, is_open, prev_open_date, note FROM trade_cal WHERE market = %s"
        params = [market]
        if start:
            sql += " AND cal_date >= %s"
            params.append(start)
        if end:
            sql += " AND cal_date <= %s"
            params.append(end)
        sql += " ORDER BY cal_date LIMIT 5000"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E4 /meta/instruments ─────────────────────────────────────────────

@app.get("/meta/instruments")
async def instruments(
    market: str = None,
    type: str = None,
    keyword: str = None,
    code: str = None,
    _=Depends(require_read)
):
    # 别名解析
    resolved_code = META["code_aliases"].get(code, code) if code else None

    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT code, name, aliases, market, inst_type, board, status FROM instrument_master WHERE 1=1"
        params = []
        if resolved_code:
            sql += " AND (code = %s OR aliases @> %s::jsonb)"
            params.extend([resolved_code, json.dumps({code: ""})])
        if market:
            sql += " AND market = %s"
            params.append(market)
        if type:
            sql += " AND inst_type = %s"
            params.append(type)
        if keyword:
            sql += " AND (name ILIKE %s OR code ILIKE %s)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        sql += " ORDER BY code LIMIT 5000"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E8 /data/base_rate (必须在 E5 /data/{table} 之前，避免被通配拦截) ──

@app.get("/data/base_rate")
async def base_rate_query(
    regime: str = None,
    category: str = None,
    horizon: str = None,
    window_type: str = "both",
    window_end: str = None,
    _=Depends(require_read)
):
    """E8 基率查询 · 口径1-5 · docs/base_rate_calibration_spec.md"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM base_rate WHERE 1=1"
        params = []
        if regime:
            sql += " AND regime = %s"
            params.append(regime)
        if category:
            sql += " AND category = %s"
            params.append(category)
        if horizon:
            sql += " AND horizon = %s"
            params.append(horizon)
        if window_type != "both":
            sql += " AND window_type = %s"
            params.append(window_type)
        if window_end:
            sql += " AND window_end = %s"
            params.append(window_end)
        else:
            sql += " AND window_end = (SELECT MAX(window_end) FROM base_rate)"
        sql += " ORDER BY regime, category, horizon, window_type"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E5 /data/{table} ─────────────────────────────────────────────────

@app.get("/data/{table}")
async def data_query(
    table: str,
    start: str = None,
    end: str = None,
    codes: str = None,
    fields: str = None,
    limit: int = Query(default=5000, le=50000),
    cursor: str = None,
    order: str = "desc",
    format: str = "json",
    _=Depends(require_read)
):
    # 白名单校验
    if table not in META["allowed_tables"]:
        return error_response("TABLE_NOT_ALLOWED", f"Table '{table}' not in whitelist", 403)

    # 构造安全 SQL
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # 字段白名单
        select_fields = "*"
        if fields:
            allowed = [f.strip() for f in fields.split(",") if f.strip().isidentifier()]
            if allowed:
                select_fields = ", ".join(allowed)

        sql = f"SELECT {select_fields} FROM {table} WHERE 1=1"
        params = []

        # 日期过滤
        if start:
            date_col = "date" if table not in ("news_telegraph", "stock_news", "announcements") else "pub_ts"
            sql += f" AND {date_col} >= %s"
            params.append(start)
        if end:
            date_col = "date" if table not in ("news_telegraph", "stock_news", "announcements") else "pub_ts"
            sql += f" AND {date_col} <= %s"
            params.append(end)

        # 代码过滤
        if codes:
            code_list = [c.strip() for c in codes.split(",") if c.strip()]
            if code_list:
                placeholders = ", ".join(["%s"] * len(code_list))
                sql += f" AND code IN ({placeholders})"
                params.extend(code_list)

        # 游标分页
        if cursor:
            sql += " AND (date, code) < (%s, %s)"
            try:
                c_date, c_code = cursor.split("|")
                params.extend([c_date, c_code])
            except ValueError:
                pass

        order_dir = "DESC" if order.lower() == "desc" else "ASC"
        # 检查表是否有 code 列
        no_code_tables = ["sentiment_daily", "trade_cal", "session_def", "margin_daily",
                          "northbound_daily", "macro_indicators", "policy_calendar"]
        if table in no_code_tables:
            sql += f" ORDER BY date {order_dir} LIMIT %s"
        else:
            sql += f" ORDER BY date {order_dir}, code {order_dir} LIMIT %s"
        params.append(limit)

        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    conn.close()

    # 计算 next_cursor
    next_cursor = None
    if len(rows) == limit and rows:
        last = rows[-1]
        next_cursor = f"{last.get('date', '')}|{last.get('code', '')}"

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return Response(content=output.getvalue(), media_type="text/csv")

    return envelope(rows, next_cursor=next_cursor)

# ─── E6 /data/sentiment/latest ────────────────────────────────────────

@app.get("/data/sentiment/latest")
async def sentiment_latest(n: int = Query(default=1, le=30), _=Depends(require_read)):
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM sentiment_daily
            ORDER BY date DESC LIMIT %s
        """, (n,))
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E7 /data/global/overnight ────────────────────────────────────────

@app.get("/data/global/overnight")
async def global_overnight(date: str = None, _=Depends(require_read)):
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if date:
            cur.execute("""
                SELECT code, name, market, close, pct, session
                FROM global_daily WHERE date = %s
                ORDER BY market, code
            """, (date,))
        else:
            cur.execute("""
                SELECT DISTINCT ON (code) code, name, market, close, pct, session, date
                FROM global_daily
                ORDER BY code, date DESC
            """)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E15 /watchlist ───────────────────────────────────────────────────

@app.get("/watchlist")
async def watchlist_get(_=Depends(require_read)):
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM watchlist WHERE active = true ORDER BY added_at DESC LIMIT 200")
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

@app.put("/watchlist")
async def watchlist_put(
    request: Request,
    _=Depends(require_write)
):
    body = await request.json()
    code = body.get("code")
    name = body.get("name")
    reason = body.get("reason", "")
    active = body.get("active", True)

    if not code:
        return error_response("BAD_PARAM", "code is required")

    # 使用 writer 连接进行 watchlist 写入
    secrets = load_secrets()
    db = secrets.get("database", {})
    conn = psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "market-tsdb"),
        port=int(os.getenv("MARKET_TSDB_PORT", "5432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user=os.getenv("MARKET_TSDB_USER_WRITER", "duser_writer"),
        password=db.get("duser_writer_password", ""),
    )
    with conn.cursor() as cur:
        # 硬校验上限 200
        cur.execute("SELECT COUNT(*) FROM watchlist WHERE active = true")
        count = cur.fetchone()[0]
        if count >= 200 and active:
            conn.close()
            return error_response("WATCHLIST_FULL", "Watchlist limit 200 reached", 400)

        cur.execute("""
            INSERT INTO watchlist (code, name, reason, active, source)
            VALUES (%s, %s, %s, %s, 'guanshi')
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                reason = EXCLUDED.reason,
                active = EXCLUDED.active,
                added_at = now()
        """, (code, name, reason, active))
    conn.commit()
    conn.close()
    return envelope({"updated": code})

# ─── E16 /ingest/status ───────────────────────────────────────────────

@app.get("/ingest/status")
async def ingest_status(
    date: str = None,
    table: str = None,
    job: str = None,
    _=Depends(require_read)
):
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM ingest_log WHERE 1=1"
        params = []
        if date:
            sql += " AND ts::date = %s"
            params.append(date)
        if table:
            sql += " AND target_table = %s"
            params.append(table)
        if job:
            sql += " AND job = %s"
            params.append(job)
        sql += " ORDER BY ts DESC LIMIT 100"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E9 /calibration ─────────────────────────────────────────────────

@app.get("/calibration")
async def calibration_query(
    category: str = None,
    window: str = None,
    _=Depends(require_read)
):
    """E9 校准视图 · 口径4 · 按月分桶"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = 'SELECT * FROM calibration_view WHERE 1=1'
        params = []
        if category:
            sql += " AND category = %s"
            params.append(category)
        if window:
            if ":" in window:
                start, end = window.split(":", 1)
                sql += ' AND "window" >= %s AND "window" <= %s'
                params.extend([start, end])
            else:
                sql += ' AND "window" = %s'
                params.append(window)
        else:
            # 默认最近 12 个月
            sql += ' AND "window" >= (CURRENT_DATE - INTERVAL \'12 months\')::date'
        sql += ' ORDER BY "window" DESC, category'
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── D12 写端点 ──────────────────────────────────────────────────────

import re

COGNITION_ID_PATTERN = re.compile(r"^[FCHM]-\d{3}$")

@app.post("/d12/cognition")
async def create_cognition(
    request: Request,
    _=Depends(require_write)
):
    """创建认知条目。cognition_id 格式校验: ^[FCHM]-\d{3}$"""
    body = await request.json()
    cid = body.get("cognition_id", "")

    # 格式校验
    if not COGNITION_ID_PATTERN.match(cid):
        return error_response("BAD_PARAM", f"cognition_id must match ^[FCHM]-\\d{{3}}$, got '{cid}'", 400)

    # 必填字段
    for field in ("type", "title", "statement", "source"):
        if not body.get(field):
            return error_response("BAD_PARAM", f"'{field}' is required", 400)

    conn = get_d12writer_conn()
    with conn.cursor() as cur:
        # 重复检测
        cur.execute("SELECT version FROM cognition WHERE cognition_id = %s ORDER BY version DESC LIMIT 1", (cid,))
        existing = cur.fetchone()
        if existing:
            conn.close()
            return error_response("CONFLICT", f"cognition_id '{cid}' already exists (version={existing[0]})", 409)

        version = body.get("version", 1)
        cur.execute("""
            INSERT INTO cognition (cognition_id, version, type, title, statement, source,
                                   confidence, regime_scope, validations, falsifications,
                                   derives_from, status, actor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            cid, version, body["type"], body["title"], body["statement"], body["source"],
            body.get("confidence"),
            json.dumps(body.get("regime_scope")) if body.get("regime_scope") else None,
            json.dumps(body.get("validations")) if body.get("validations") else None,
            json.dumps(body.get("falsifications")) if body.get("falsifications") else None,
            json.dumps(body.get("derives_from")) if body.get("derives_from") else None,
            body.get("status", "active"),
            body.get("actor", "guanshi"),
        ))
    conn.commit()
    conn.close()
    return envelope({"created": cid, "version": version})


@app.post("/d12/prediction")
async def create_prediction(
    request: Request,
    _=Depends(require_write)
):
    """创建预测条目。"""
    body = await request.json()
    pid = body.get("prediction_id", "")

    # 必填字段
    for field in ("prediction_id", "statement", "category", "confidence_pct", "check_date", "falsify"):
        if field not in body or body[field] is None:
            return error_response("BAD_PARAM", f"'{field}' is required", 400)

    # confidence_pct 范围校验
    conf = body.get("confidence_pct")
    if not isinstance(conf, int) or conf < 0 or conf > 100:
        return error_response("BAD_PARAM", "confidence_pct must be int 0-100", 400)

    # horizon 校验 (可选但推荐)
    horizon = body.get("horizon")
    if horizon and horizon not in ("T1", "T3", "T5", "W1"):
        return error_response("BAD_PARAM", "horizon must be T1/T3/T5/W1", 400)

    conn = get_d12writer_conn()
    with conn.cursor() as cur:
        # 重复检测
        cur.execute("SELECT prediction_id FROM prediction WHERE prediction_id = %s", (pid,))
        if cur.fetchone():
            conn.close()
            return error_response("CONFLICT", f"prediction_id '{pid}' already exists", 409)

        cur.execute("""
            INSERT INTO prediction (prediction_id, statement, category, confidence_pct,
                                    base_rate_ref, conditions, falsify, check_date,
                                    regime_at_create, horizon, result, actor, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            pid, body["statement"], body["category"], conf,
            body.get("base_rate_ref"),
            json.dumps(body.get("conditions")) if body.get("conditions") else None,
            json.dumps(body["falsify"]),
            body["check_date"],
            body.get("regime_at_create"),
            horizon,
            body.get("result", "pending"),
            body.get("actor", "guanshi"),
            body.get("source", "guanshi"),
        ))
    conn.commit()
    conn.close()
    return envelope({"created": pid})


@app.put("/d12/prediction/{prediction_id}/result")
async def update_prediction_result(
    prediction_id: str,
    request: Request,
    _=Depends(require_write)
):
    """人工改判 prediction result。result_note 必填。"""
    body = await request.json()
    result = body.get("result")
    result_note = body.get("result_note")

    if result not in ("hit", "miss", "pending", "invalid", "expired"):
        return error_response("BAD_PARAM", f"result must be hit/miss/pending/invalid/expired, got '{result}'", 400)
    if not result_note:
        return error_response("BAD_PARAM", "result_note is required for manual override", 400)

    conn = get_d12writer_conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE prediction
            SET result = %s, result_note = %s, checked_at = now()
            WHERE prediction_id = %s
            RETURNING prediction_id
        """, (result, result_note, prediction_id))
        updated = cur.fetchone()
    conn.commit()
    conn.close()

    if not updated:
        return error_response("NOT_FOUND", f"prediction_id '{prediction_id}' not found", 404)

    return envelope({"updated": prediction_id, "result": result, "base_rate_stale": True})


@app.get("/d12/prediction/due")
async def prediction_due(
    date: str = None,
    status: str = "pending",
    _=Depends(require_read)
):
    """E13 到期待验清单。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = """
            SELECT prediction_id, statement, category, confidence_pct, check_date,
                   result, result_note, created_at
            FROM prediction
            WHERE result = %s
        """
        params = [status]
        if date:
            sql += " AND check_date <= %s"
            params.append(date)
        else:
            sql += " AND check_date < CURRENT_DATE"
        sql += " ORDER BY check_date ASC LIMIT 200"
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

# ─── E19 /docs + /openapi.json ────────────────────────────────────────
# 由 FastAPI 自动生成

# ─── Error handlers ───────────────────────────────────────────────────

@app.exception_handler(psycopg2.errors.QueryCanceled)
async def timeout_handler(request, exc):
    return error_response("TIMEOUT", "Query exceeded 30s limit", 504)

@app.exception_handler(Exception)
async def generic_handler(request, exc):
    logger.error(f"Unhandled error: {exc}")
    return error_response("INTERNAL", str(exc), 500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
