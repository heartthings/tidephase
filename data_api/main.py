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
from pydantic import BaseModel

from data_api.reflection_pack import (
    assemble_reflection_pack, get_route_map, invalidate_route_map_cache,
    DEFAULT_ROUTE_MAP,
)
from data_api.lovetrade_routes import router as lovetrade_router
from data_api.z7ext_routes import router as z7ext_router, init_auth as z7ext_init_auth

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
            # Z8 W1 新增
            "topic", "topic_category", "topic_group", "topic_links",
            "note_category", "trading_note", "report",
            "dynamic_category_config", "trading_system_node",
            "plate_movement_intraday",
            # Z7-ext 催化雷达三表
            "catalyst_impact", "catalyst_active_message", "catalyst_system_state",
            # Z7-ext 白名单补全
            "radar_event", "regime_daily",
        ],
        "no_code_tables": [
            "sector_daily", "theme_heat",
        ],
        "code_aliases": {
            "KS11": "KOSPI",
            "N225": "NK225",
        }
    }

META = load_meta()

# ─── Adaptive ORDER BY (Z7c-fix: prediction 等无 date 列的表) ─────────
_table_sort_cache: dict = {}  # table → {"date_col": str|None, "has_code": bool}
_table_sort_ts: dict = {}     # table → last_refresh_ts
_SORT_CACHE_TTL = 300  # 5 min

def _detect_table_sort(conn, table: str) -> dict:
    """探测表的排序列: 有 date 用 date; 否则 created_at/ts; 再否则主键。
    同时检测是否有 code 列。结果缓存 5min。
    """
    now = time.time()
    if table in _table_sort_cache and now - _table_sort_ts.get(table, 0) < _SORT_CACHE_TTL:
        return _table_sort_cache[table]

    try:
        cur = conn.cursor()
        # 获取所有列名
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        columns = {r[0] for r in cur.fetchall()}
        cur.close()

        # 确定日期排序列
        if "date" in columns:
            date_col = "date"
        elif "created_at" in columns:
            date_col = "created_at"
        elif "ts" in columns:
            date_col = "ts"
        elif "pub_ts" in columns:
            date_col = "pub_ts"
        else:
            date_col = None  # fallback: 不 ORDER BY date

        has_code = "code" in columns
        result = {"date_col": date_col, "has_code": has_code}
    except Exception:
        # 探测失败 → 安全降级: 假设 date + code
        result = {"date_col": "date", "has_code": True}

    _table_sort_cache[table] = result
    _table_sort_ts[table] = now
    return result

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

# Z8 W2: 注册 lovetrade 路由
app.include_router(lovetrade_router)

# Z7-ext: 注册催化雷达路由（需要在 auth 函数定义之后初始化）
z7ext_init_auth(require_read, require_write, get_reader_conn, get_d12writer_conn)
app.include_router(z7ext_router)

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

# ─── Z7c /data/reflection_pack (必须在 E5 /data/{table} 之前) ──────────

@app.get("/data/reflection_pack")
async def reflection_pack(
    decision_id: str = Query(...),
    window_start: str = None,
    window_end: str = None,
    section: str = None,
    _=Depends(require_read)
):
    """Z7c 反思层证据包. 组装 S1~S4 四维快照 + falsify 实际序列 + 归因 + base_rate 对照.
    诚实纪律: 任何数据缺失 → gaps[], 不做伪填充.
    """
    pack = assemble_reflection_pack(
        get_reader_conn, decision_id,
        window_start_override=window_start,
        window_end_override=window_end,
        sections_override=section,
    )
    if "error" in pack:
        return error_response(pack["error"], f"decision_id '{decision_id}' not found", 404)
    return envelope(pack)


# ─── Z7c /reflection_pack/route_map ──────────────────────────────────

@app.get("/reflection_pack/route_map")
async def route_map_get(_=Depends(require_read)):
    """Z7c 读回当前 route_map (从 job_registry.config->'route_map', 空则返回 DEFAULT)."""
    rm = get_route_map(get_reader_conn)
    return envelope(rm)


class RouteMapBody(BaseModel):
    route_map: dict
    route_map_version: Optional[str] = None


@app.patch("/reflection_pack/route_map")
async def route_map_patch(body: RouteMapBody, _=Depends(require_write)):
    """Z7c 整体替换 route_map. 逐条校验 table/column 在 information_schema 中存在."""
    rm = body.route_map
    if not rm or not isinstance(rm, dict):
        return error_response("BAD_PARAM", "route_map must be a non-empty dict", 400)

    # 校验 metric_routes 中 table/column 存在
    for i, mr in enumerate(rm.get("metric_routes", [])):
        tbl = mr.get("table")
        col = mr.get("column")
        if not tbl or not col:
            return error_response("ROUTE_MAP_INVALID", f"metric_routes[{i}]: missing table or column", 400)
        conn = get_reader_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                """, (tbl, col))
                if not cur.fetchone():
                    return error_response("ROUTE_MAP_INVALID",
                                          f"metric_routes[{i}]: {tbl}.{col} not found in information_schema", 400)
        finally:
            conn.close()

    # Bump version
    ver = body.route_map_version or rm.get("route_map_version", "")
    if ver and not ver.endswith("."):
        # Auto-increment: 2026-10-10.1 → 2026-10-10.2
        parts = ver.rsplit(".", 1)
        if len(parts) == 2 and parts[1].isdigit():
            ver = f"{parts[0]}.{int(parts[1]) + 1}"
    rm["route_map_version"] = ver

    # 写入 job_registry.config->'route_map'
    conn = get_d12writer_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE job_registry
                SET config = jsonb_set(COALESCE(config, '{}'), '{route_map}', %s::jsonb),
                    updated_at = now()
                WHERE job_name = 'j_reflect_daily'
            """, (json.dumps(rm),))
            if cur.rowcount == 0:
                conn.close()
                return error_response("ROUTE_MAP_INVALID", "job_registry row j_reflect_daily not found", 404)
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    invalidate_route_map_cache()
    return envelope({"route_map": rm, "route_map_version": ver})


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

        # Z7c-fix: 自适应排序列（统一探测，供日期过滤/游标/ORDER BY 共用）
        sort_info = _detect_table_sort(conn, table)

        # 日期过滤 (Z7c-fix + Z7-ext: 自适应日期列)
        _date_col_map = {
            "news_telegraph": "pub_ts", "stock_news": "pub_ts", "announcements": "pub_ts",
            "market_messages": "msg_ts",
            "prediction": "created_at",
            "radar_event": "ts",
            "catalyst_impact": "date",
            "catalyst_system_state": "date",
        }
        filter_date_col = _date_col_map.get(table) or sort_info.get("date_col") or "date"
        if start and filter_date_col:
            sql += f" AND {filter_date_col} >= %s"
            params.append(start)
        if end and filter_date_col:
            sql += f" AND {filter_date_col} <= %s"
            params.append(end)

        # 代码过滤 (Z7-ext: 自适应 code 列名)
        if codes and sort_info.get("has_code"):
            code_list = [c.strip() for c in codes.split(",") if c.strip()]
            if code_list:
                placeholders = ", ".join(["%s"] * len(code_list))
                sql += f" AND code IN ({placeholders})"
                params.extend(code_list)
        elif codes and not sort_info.get("has_code"):
            # Try sector_code for sector_daily/theme_heat
            code_col = None
            if table in ("sector_daily", "theme_heat"):
                code_col = "sector_code"
            if code_col:
                code_list = [c.strip() for c in codes.split(",") if c.strip()]
                if code_list:
                    placeholders = ", ".join(["%s"] * len(code_list))
                    sql += f" AND {code_col} IN ({placeholders})"
                    params.extend(code_list)

        # 游标分页 (Z7c-fix: 自适应排序列)
        if cursor and sort_info.get("date_col"):
            _pk_col = sort_info["date_col"]
            if sort_info.get("has_code"):
                sql += f" AND ({_pk_col}, code) < (%s, %s)"
            else:
                sql += f" AND {_pk_col} < %s"
            try:
                c_parts = cursor.split("|")
                c_date = c_parts[0]
                if sort_info.get("has_code"):
                    c_code = c_parts[1] if len(c_parts) > 1 else ""
                    params.extend([c_date, c_code])
                else:
                    params.append(c_date)
            except (ValueError, IndexError):
                pass

        order_dir = "DESC" if order.lower() == "desc" else "ASC"
        # Z7c-fix: 自适应排序列（prediction 等无 date 列的表不再 500）
        sort_col = sort_info["date_col"] or "1"  # 无日期列则用常量（不排序）
        if sort_info["has_code"] and sort_col != "1":
            sql += f" ORDER BY {sort_col} {order_dir}, code {order_dir} LIMIT %s"
        elif sort_col != "1":
            sql += f" ORDER BY {sort_col} {order_dir} LIMIT %s"
        else:
            sql += f" LIMIT %s"
        params.append(limit)

        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    conn.close()

    # 计算 next_cursor (Z7c-fix: 自适应排序列)
    next_cursor = None
    if len(rows) == limit and rows:
        last = rows[-1]
        _nc_date = last.get(sort_info.get("date_col") or "date", "")
        _nc_code = last.get("code", "") if sort_info.get("has_code") else ""
        next_cursor = f"{_nc_date}|{_nc_code}"

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

    if result not in ("hit", "miss", "partial", "pending", "invalid", "expired"):
        return error_response("BAD_PARAM", f"result must be hit/miss/partial/pending/invalid/expired, got '{result}'", 400)
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

# ─── Z7b 反思层端点 (V004) ────────────────────────────────────────────
# POST /reflection · GET /reflection/recent · GET /reflection/action_items
# 依据: cognition/README.md §8 + specs/architecture-master.md §7

VALID_QUADRANTS = {'right_right', 'right_luck', 'wrong_right', 'wrong_wrong'}
VALID_ERROR_STAGES = {'regime', 'cognition_ref', 'data_premise', 'expression', 'capability_circle', 'noise'}
VALID_LESSON_KINDS = {'candidate_cognition', 'rule_revision', 'none'}
VALID_ACTION_STATUSES = {'open', 'done', 'waived'}


def _validate_reflection_record(rec: dict) -> Optional[JSONResponse]:
    """校验单条反思记录字段，返回 None=通过，否则返回 error JSONResponse。"""
    did = rec.get("decision_id")
    if not did:
        return error_response("BAD_PARAM", "'decision_id' is required", 400)
    quad = rec.get("quadrant")
    if quad is not None and quad not in VALID_QUADRANTS:
        return error_response("REF_ENUM", f"quadrant must be one of {sorted(VALID_QUADRANTS)}, got '{quad}'", 400)
    es = rec.get("error_stage")
    if es is not None and es not in VALID_ERROR_STAGES:
        return error_response("REF_ENUM", f"error_stage must be one of {sorted(VALID_ERROR_STAGES)}, got '{es}'", 400)
    lk = rec.get("lesson_kind")
    if lk is not None and lk not in VALID_LESSON_KINDS:
        return error_response("REF_ENUM", f"lesson_kind must be one of {sorted(VALID_LESSON_KINDS)}, got '{lk}'", 400)
    ast = rec.get("action_status")
    if ast is not None and ast not in VALID_ACTION_STATUSES:
        return error_response("REF_ENUM", f"action_status must be one of {sorted(VALID_ACTION_STATUSES)}, got '{ast}'", 400)
    return None


@app.post("/reflection")
async def create_reflection(
    request: Request,
    _=Depends(require_write)
):
    """Z7b 创建反思记录。body 支持单条 object 或 {"records": [...]} 数组。"""
    body = await request.json()

    # 支持单条或 records 数组
    if isinstance(body, dict) and "records" in body:
        records = body["records"]
        if not isinstance(records, list):
            return error_response("BAD_PARAM", "'records' must be an array", 400)
    elif isinstance(body, dict):
        records = [body]
    else:
        return error_response("BAD_PARAM", "body must be an object or {'records': [...]}", 400)

    if not records:
        return error_response("BAD_PARAM", "no records provided", 400)

    # 先全量校验
    for i, rec in enumerate(records):
        err = _validate_reflection_record(rec)
        if err is not None:
            return err

    conn = get_d12writer_conn()
    inserted_ids = []
    has_evidence_refs = False
    try:
        with conn.cursor() as cur:
            # 批量校验 decision_id 存在于 prediction
            decision_ids = list({rec["decision_id"] for rec in records})
            cur.execute(
                "SELECT prediction_id FROM prediction WHERE prediction_id = ANY(%s)",
                (decision_ids,)
            )
            existing = {row[0] for row in cur.fetchall()}
            missing = [did for did in decision_ids if did not in existing]
            if missing:
                conn.close()
                return error_response(
                    "REF_DECISION_NOT_FOUND",
                    f"decision_id not found in prediction: {missing}",
                    404
                )

            # 逐条 INSERT
            for rec in records:
                if rec.get("evidence_refs") is not None:
                    has_evidence_refs = True
                cur.execute("""
                    INSERT INTO reflection (decision_id, closed_at, quadrant, error_stage,
                                            lesson_text, lesson_kind, action_item, action_status,
                                            evidence_refs, evidence_summary, actor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    rec["decision_id"],
                    rec.get("closed_at"),
                    rec.get("quadrant"),
                    rec.get("error_stage"),
                    rec.get("lesson_text"),
                    rec.get("lesson_kind"),
                    rec.get("action_item"),
                    rec.get("action_status", "open"),
                    json.dumps(rec["evidence_refs"]) if rec.get("evidence_refs") is not None else None,
                    rec.get("evidence_summary"),
                    rec.get("actor", "guanshi"),
                ))
                inserted_ids.append(cur.fetchone()[0])
        conn.commit()
    except Exception:
        conn.close()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    resp = {"inserted_ids": inserted_ids, "count": len(inserted_ids)}
    if not has_evidence_refs:
        resp["warning"] = "NO_EVIDENCE_REFS"
    return envelope(resp)


@app.get("/reflection/recent")
async def reflection_recent(
    days: int = Query(default=30, ge=1, le=365),
    _=Depends(require_read)
):
    """Z7b 近 N 天反思记录（默认30，上限365），closed_at 倒序。"""
    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM reflection
            WHERE closed_at >= now() - INTERVAL '%s days'
            ORDER BY closed_at DESC
            LIMIT 500
        """, (days,))
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)


@app.get("/reflection/action_items")
async def reflection_action_items(
    status: str = Query(default="open"),
    _=Depends(require_read)
):
    """Z7b 行动项查询。status 缺省 open，支持 open/done/waived/all。"""
    if status != "all" and status not in VALID_ACTION_STATUSES:
        return error_response("BAD_PARAM", f"status must be open/done/waived/all, got '{status}'", 400)

    conn = get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if status == "all":
            cur.execute("""
                SELECT * FROM reflection
                WHERE action_item IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 500
            """)
        else:
            cur.execute("""
                SELECT * FROM reflection
                WHERE action_status = %s AND action_item IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 500
            """, (status,))
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return envelope(rows)

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
