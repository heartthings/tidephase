"""
data_api/z7ext_routes.py
Z7-ext · 催化雷达读写端点
依据: 观势 specs/z7ext-endpoint-requirements.md §二

写端点 (Bearer write token):
  POST   /d12/impact                       冲击建档
  PUT    /d12/impact/{impact_id}            冲击更新 (note_append 幂等)
  POST   /d12/active_message               AM 建卡
  PUT    /d12/active_message/{am_id}        AM dailyUpdate (append)
  POST   /d12/system_state                 系统状态快照 (upsert)

读端点 (Bearer read token):
  GET    /d12/impact                        冲击读
  GET    /d12/active_message                AM 读
  GET    /d12/system_state                  快照读
  GET    /d12/prediction                    预测全量读 (补 /due 只有 pending 的缺口)
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, Query, Request

logger = logging.getLogger("data-api.z7ext")
TZ_CST = timezone(timedelta(hours=8))

router = APIRouter(tags=["z7ext-catalyst"])

# ─── Helpers (duplicated from main.py to avoid circular import) ────────

def _envelope(data, rows=None):
    return {
        "data": data,
        "meta": {
            "rows": rows or (len(data) if isinstance(data, list) else 1),
            "server_ts": datetime.now(TZ_CST).isoformat(),
            "request_id": str(uuid.uuid4()),
        }
    }

def _error(code, msg, status=400):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "msg": msg, "request_id": str(uuid.uuid4())}}
    )

# ─── Auth (imported at route registration time from main) ─────────────
# These will be set by main.py during registration
_require_read = None
_require_write = None
_get_reader_conn = None
_get_d12writer_conn = None


def init_auth(require_read, require_write, get_reader_conn, get_d12writer_conn):
    """Called by main.py to inject auth deps and DB factories."""
    global _require_read, _require_write, _get_reader_conn, _get_d12writer_conn
    _require_read = require_read
    _require_write = require_write
    _get_reader_conn = get_reader_conn
    _get_d12writer_conn = get_d12writer_conn


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 写端点
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/d12/impact")
async def create_impact(request: Request):
    """冲击建档。幂等键 = impact_id。"""
    body = await request.json()
    impact_id = body.get("impact_id")
    if not impact_id:
        return _error("BAD_PARAM", "impact_id is required", 400)

    for field in ("date", "message_summary", "message_type", "impact_level", "target_topics", "predicted_effect"):
        if body.get(field) is None:
            return _error("BAD_PARAM", f"'{field}' is required", 400)

    level = body["impact_level"]
    if not isinstance(level, int) or level < 1 or level > 5:
        return _error("BAD_PARAM", "impact_level must be int 1-5", 400)

    conn = _get_d12writer_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT impact_id FROM catalyst_impact WHERE impact_id = %s", (impact_id,))
            if cur.fetchone():
                conn.close()
                return _error("CONFLICT", f"impact_id '{impact_id}' already exists", 409)

            cur.execute("""
                INSERT INTO catalyst_impact (
                    impact_id, date, scan_session,
                    message_summary, message_source, message_url, message_time,
                    message_type, impact_level, target_topics,
                    system_state_before, predicted_effect, detailed_analysis,
                    decay_days, decay_type, confidence, global_coupling,
                    lifecycle_stage, remaining_influence, actor, source
                ) VALUES (
                    %s,%s,%s, %s,%s,%s,%s, %s,%s,%s, %s,%s,%s,
                    %s,%s,%s,%s, %s,%s,%s,%s
                )
            """, (
                impact_id, body["date"], body.get("scan_session"),
                body["message_summary"], body.get("message_source"), body.get("message_url"),
                body.get("message_time"),
                body["message_type"], level,
                json.dumps(body["target_topics"], ensure_ascii=False),
                json.dumps(body["system_state_before"], ensure_ascii=False) if body.get("system_state_before") else None,
                body["predicted_effect"], body.get("detailed_analysis"),
                body.get("decay_days", 3), body.get("decay_type", "normal"),
                body.get("confidence", 0.5), body.get("global_coupling", "medium"),
                body.get("lifecycle_stage", "shock"), body.get("remaining_influence", 1.0),
                body.get("actor", "guanshi"), "guanshi",
            ))
        conn.commit()
    except Exception:
        conn.close()
        raise
    finally:
        try: conn.close()
        except: pass

    return _envelope({"created": impact_id})


@router.put("/d12/impact/{impact_id}")
async def update_impact(impact_id: str, request: Request):
    """冲击更新（部分更新）。note_append 幂等键 = (impact_id, session, ts)。"""
    body = await request.json()
    conn = _get_d12writer_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT notes FROM catalyst_impact WHERE impact_id = %s", (impact_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return _error("NOT_FOUND", f"impact_id '{impact_id}' not found", 404)

            # Build SET clauses
            sets = []
            params = []
            updatable = [
                "impact_level", "lifecycle_stage", "remaining_influence", "confidence",
                "global_coupling", "verified_result", "verification_note", "verified_date",
            ]
            for field in updatable:
                if field in body:
                    sets.append(f"{field} = %s")
                    params.append(body[field])

            # jsonb fields
            for jf in ("system_state_after",):
                if jf in body:
                    sets.append(f"{jf} = %s")
                    params.append(json.dumps(body[jf], ensure_ascii=False))

            # note_append: {ts, session, text} → append to notes[]
            note_append = body.get("note_append")
            if note_append:
                if not all(k in note_append for k in ("ts", "session", "text")):
                    conn.close()
                    return _error("BAD_PARAM", "note_append requires ts, session, text", 400)
                # Idempotent append: check if (session, ts) already in notes
                existing_notes = row["notes"] or []
                dup = any(
                    n.get("session") == note_append["session"] and n.get("ts") == note_append["ts"]
                    for n in existing_notes
                )
                if not dup:
                    existing_notes.append({
                        "ts": note_append["ts"],
                        "session": note_append["session"],
                        "text": note_append["text"],
                    })
                    sets.append("notes = %s")
                    params.append(json.dumps(existing_notes, ensure_ascii=False))

            if not sets:
                conn.close()
                return _envelope({"updated": impact_id, "no_changes": True})

            params.append(impact_id)
            cur.execute(f"UPDATE catalyst_impact SET {', '.join(sets)} WHERE impact_id = %s", params)
        conn.commit()
    except Exception:
        conn.close()
        raise
    finally:
        try: conn.close()
        except: pass

    return _envelope({"updated": impact_id})


@router.post("/d12/active_message")
async def create_active_message(request: Request):
    """AM 建卡。幂等键 = am_id。"""
    body = await request.json()
    am_id = body.get("am_id")
    if not am_id:
        return _error("BAD_PARAM", "am_id is required", 400)

    for field in ("impact_id", "message_title", "current_stage"):
        if body.get(field) is None and field != "current_stage":
            return _error("BAD_PARAM", f"'{field}' is required", 400)

    conn = _get_d12writer_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT am_id FROM catalyst_active_message WHERE am_id = %s", (am_id,))
            if cur.fetchone():
                conn.close()
                return _error("CONFLICT", f"am_id '{am_id}' already exists", 409)

            cur.execute("""
                INSERT INTO catalyst_active_message (
                    am_id, impact_id, message_title,
                    current_stage, remaining_influence, is_active,
                    expected_decay_date, daily_updates
                ) VALUES (%s,%s,%s, %s,%s,%s, %s,%s)
            """, (
                am_id, body["impact_id"], body.get("message_title", ""),
                body.get("current_stage", "shock"),
                body.get("remaining_influence", 1.0),
                body.get("is_active", True),
                body.get("expected_decay_date"),
                json.dumps(body.get("daily_updates", []), ensure_ascii=False),
            ))
        conn.commit()
    except Exception:
        conn.close()
        raise
    finally:
        try: conn.close()
        except: pass

    return _envelope({"created": am_id})


@router.put("/d12/active_message/{am_id}")
async def update_active_message(am_id: str, request: Request):
    """AM dailyUpdate。daily_update append 幂等键 = (am_id, date, ts)。"""
    body = await request.json()
    conn = _get_d12writer_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT daily_updates FROM catalyst_active_message WHERE am_id = %s", (am_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return _error("NOT_FOUND", f"am_id '{am_id}' not found", 404)

            sets = []
            params = []
            for field in ("current_stage", "remaining_influence", "is_active", "expected_decay_date"):
                if field in body:
                    sets.append(f"{field} = %s")
                    params.append(body[field])

            # daily_update append
            daily_update = body.get("daily_update")
            if daily_update:
                existing = row["daily_updates"] or []
                # Idempotent: check (date, ts)
                dup = any(
                    u.get("date") == daily_update.get("date") and u.get("ts") == daily_update.get("ts")
                    for u in existing
                )
                if not dup:
                    existing.append(daily_update)
                    sets.append("daily_updates = %s")
                    params.append(json.dumps(existing, ensure_ascii=False))

            if not sets:
                conn.close()
                return _envelope({"updated": am_id, "no_changes": True})

            params.append(am_id)
            cur.execute(f"UPDATE catalyst_active_message SET {', '.join(sets)} WHERE am_id = %s", params)
        conn.commit()
    except Exception:
        conn.close()
        raise
    finally:
        try: conn.close()
        except: pass

    return _envelope({"updated": am_id})


@router.post("/d12/system_state")
async def create_system_state(request: Request):
    """系统状态快照（upsert by scan_session）。"""
    body = await request.json()
    scan_session = body.get("scan_session")
    if not scan_session:
        return _error("BAD_PARAM", "scan_session is required", 400)

    for field in ("date", "overall_phase"):
        if body.get(field) is None:
            return _error("BAD_PARAM", f"'{field}' is required", 400)

    conn = _get_d12writer_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO catalyst_system_state (
                    scan_session, date, scan_time,
                    overall_phase, overall_note, topic_states,
                    global_coupling, coupling_note, global_data,
                    sentiment, sentiment_indicators,
                    evolution_direction, evolution_note, source
                ) VALUES (%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s, %s,%s, %s)
                ON CONFLICT (scan_session) DO UPDATE SET
                    overall_phase = EXCLUDED.overall_phase,
                    overall_note = EXCLUDED.overall_note,
                    topic_states = EXCLUDED.topic_states,
                    sentiment_indicators = EXCLUDED.sentiment_indicators,
                    coupling_note = EXCLUDED.coupling_note,
                    evolution_direction = EXCLUDED.evolution_direction,
                    evolution_note = EXCLUDED.evolution_note,
                    updated_time = now()
            """, (
                scan_session, body["date"], body.get("scan_time"),
                body["overall_phase"], body.get("overall_note"),
                json.dumps(body.get("topic_states", {}), ensure_ascii=False),
                body.get("global_coupling", "medium"),
                body.get("coupling_note"),
                json.dumps(body.get("global_data"), ensure_ascii=False) if body.get("global_data") else None,
                body.get("sentiment"),
                json.dumps(body.get("sentiment_indicators"), ensure_ascii=False) if body.get("sentiment_indicators") else None,
                body.get("evolution_direction"), body.get("evolution_note"),
                "guanshi",
            ))
        conn.commit()
    except Exception:
        conn.close()
        raise
    finally:
        try: conn.close()
        except: pass

    return _envelope({"upserted": scan_session})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 读端点
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/d12/impact")
async def read_impacts(
    start: str = None, end: str = None,
    stage: str = None, min_level: int = None,
    impact_id: str = None,
    limit: int = Query(default=200, le=1000),
):
    """冲击读。"""
    conn = _get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM catalyst_impact WHERE 1=1"
        params = []
        if impact_id:
            sql += " AND impact_id = %s"
            params.append(impact_id)
        if start:
            sql += " AND date >= %s"
            params.append(start)
        if end:
            sql += " AND date <= %s"
            params.append(end)
        if stage:
            sql += " AND lifecycle_stage = %s"
            params.append(stage)
        if min_level:
            sql += " AND impact_level >= %s"
            params.append(min_level)
        sql += " ORDER BY date DESC, impact_level DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return _envelope(rows)


@router.get("/d12/active_message")
async def read_active_messages(
    active: str = "true",
    stage: str = None,
    limit: int = Query(default=200, le=1000),
):
    """AM 读。"""
    conn = _get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM catalyst_active_message WHERE 1=1"
        params = []
        if active == "true":
            sql += " AND is_active = true"
        elif active == "false":
            sql += " AND is_active = false"
        if stage:
            sql += " AND current_stage = %s"
            params.append(stage)
        sql += " ORDER BY updated_time DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return _envelope(rows)


@router.get("/d12/system_state")
async def read_system_states(
    start: str = None, end: str = None,
    scan_session: str = None,
    limit: int = Query(default=100, le=500),
):
    """快照读。"""
    conn = _get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM catalyst_system_state WHERE 1=1"
        params = []
        if scan_session:
            sql += " AND scan_session = %s"
            params.append(scan_session)
        if start:
            sql += " AND date >= %s"
            params.append(start)
        if end:
            sql += " AND date <= %s"
            params.append(end)
        sql += " ORDER BY date DESC, scan_time DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return _envelope(rows)


@router.get("/d12/prediction")
async def read_predictions(
    result: str = None,
    start: str = None, end: str = None,
    created_start: str = None, created_end: str = None,
    limit: int = Query(default=500, le=5000),
):
    """预测全量读（补 /due 只有 pending 的缺口）。"""
    conn = _get_reader_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        sql = "SELECT * FROM prediction WHERE 1=1"
        params = []
        if result:
            results = [r.strip() for r in result.split(",") if r.strip()]
            if results:
                placeholders = ", ".join(["%s"] * len(results))
                sql += f" AND result IN ({placeholders})"
                params.extend(results)
        if start:
            sql += " AND check_date >= %s"
            params.append(start)
        if end:
            sql += " AND check_date <= %s"
            params.append(end)
        if created_start:
            sql += " AND created_at >= %s"
            params.append(created_start)
        if created_end:
            sql += " AND created_at <= %s"
            params.append(created_end)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return _envelope(rows)
