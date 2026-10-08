#!/usr/bin/env python3
"""
tools/migrate_lovetrade.py
lovetrade MySQL → market_tsdb ETL（§11.5 映射）

实际列名已勘察确认（2026-10-07）。
幂等 upsert，行级 source='lovetrade-mysql'，quarantine 开启。
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
import psycopg2
import yaml

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

MYSQL_CONFIG = {
    "host": "81.70.207.80", "port": 8010, "user": "root",
    "password": "Gee6lXRoYRBb", "database": "lovetrade",
    "connect_timeout": 10, "read_timeout": 600,
    "cursorclass": pymysql.cursors.DictCursor,
}

# index_type string → canonical code
INDEX_TYPE_MAP = {
    "SHANGHAI": "sh000001", "SHENZHEN": "sz399001", "CHINEXT": "sz399006",
    "STAR": "sh000688", "CSI300": "sh000300", "SSE50": "sh000016",
}


def get_mysql_conn():
    return pymysql.connect(**MYSQL_CONFIG)


def get_tsdb_conn():
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f) or {}
    db = secrets.get("database", {})
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user="postgres", password=db.get("duser_admin_password", ""),
    )


def quarantine_row(tsdb_conn, job, table, row_key, payload, rules, source="lovetrade-mysql"):
    with tsdb_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO quarantine (job, target_table, row_key, payload, failed_rules, severity, status, source)
            VALUES (%s, %s, %s, %s, %s, 'block', 'pending', %s)
        """, (job, table, row_key, json.dumps(payload, default=str), json.dumps(rules), source))
    tsdb_conn.commit()


def log_mig(tsdb_conn, job, table, status, rows_in, rows_written, rows_quarantined, note=""):
    with tsdb_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingest_log (job, trigger, domain, target_table, source_used, status,
                                    rows_in, rows_written, rows_quarantined, note)
            VALUES (%s, 'migration', 'pipeline', %s, 'lovetrade-mysql', %s, %s, %s, %s, %s)
        """, (job, table, status, rows_in, rows_written, rows_quarantined, note))
    tsdb_conn.commit()


def safe_float(v):
    if v is None: return None
    try: return float(v)
    except: return None


def safe_int(v):
    if v is None: return None
    try: return int(v)
    except: return None


def normalize_code(raw):
    """Normalize 6-digit stock code to sh/sz/bj prefix."""
    raw = str(raw).strip()
    if len(raw) == 6 and raw.isdigit():
        if raw.startswith("6"): return f"sh{raw}"
        if raw.startswith(("0", "3")): return f"sz{raw}"
        if raw.startswith(("4", "8")): return f"bj{raw}"
    return raw


# ==========================================
# 1. index_trend → index_minute
# ==========================================
def migrate_index_trend(mysql_conn, tsdb_conn):
    print("\n🔄 [1/8] index_trend → index_minute")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM index_trend")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    cur.execute("SELECT * FROM index_trend ORDER BY date ASC, time ASC")
    written = quarantined = 0
    batch = []

    for row in cur:
        idx_type = row.get("index_type", "")
        code = INDEX_TYPE_MAP.get(idx_type)
        if not code:
            quarantine_row(tsdb_conn, "mig_index_trend", "index_minute",
                          f"{idx_type}_{row.get('date')}", dict(row, default=str),
                          [f"unknown index_type: {idx_type}"])
            quarantined += 1
            continue

        d = row.get("date")
        t = row.get("time", "00:00:00")
        if isinstance(d, str):
            date_str = d
        else:
            date_str = d.isoformat()
        ts = f"{date_str}T{t}+08:00"

        batch.append((
            ts, code, "1m",
            safe_float(row.get("open_price")), safe_float(row.get("high_price")),
            safe_float(row.get("low_price")), safe_float(row.get("close_price")),
            safe_float(row.get("turnover")), None,
            "lovetrade-mysql"
        ))
        written += 1

        if len(batch) >= 2000:
            _flush_index_minute(tsdb_conn, batch)
            batch = []
            if written % 10000 == 0:
                print(f"   ... {written:,}/{total:,}")

    if batch:
        _flush_index_minute(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_index_trend", "index_minute",
            "OK" if quarantined == 0 else "PARTIAL", total, written, quarantined)
    print(f"   ✅ Written: {written:,}, Quarantined: {quarantined}")
    return total, written, quarantined


def _flush_index_minute(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO index_minute (ts, code, freq, open, high, low, close, volume, amount, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (ts, code, freq) DO UPDATE SET
                open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                close=EXCLUDED.close, volume=EXCLUDED.volume, source=EXCLUDED.source
        """, batch)
    tsdb_conn.commit()


# ==========================================
# 2. market_message → market_messages
# ==========================================
def migrate_market_message(mysql_conn, tsdb_conn):
    print("\n🔄 [2/8] market_message → market_messages")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM market_message")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    cur.execute("SELECT * FROM market_message ORDER BY time ASC")
    written = quarantined = 0
    batch = []

    for row in cur:
        t = row.get("time")
        if isinstance(t, datetime):
            ts = t.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        elif t:
            ts = str(t).replace(" ", "T") + "+08:00"
        else:
            quarantined += 1
            continue

        msg_id = str(row.get("id", ""))
        batch.append((
            ts, msg_id, "lovetrade", None,
            row.get("title"), row.get("content"),
            None, safe_float(row.get("score")),
            row.get("url"), "lovetrade-mysql"
        ))
        written += 1

        if len(batch) >= 2000:
            _flush_market_messages(tsdb_conn, batch)
            batch = []
            if written % 10000 == 0:
                print(f"   ... {written:,}/{total:,}")

    if batch:
        _flush_market_messages(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_market_message", "market_messages",
            "OK" if quarantined == 0 else "PARTIAL", total, written, quarantined)
    print(f"   ✅ Written: {written:,}, Quarantined: {quarantined}")
    return total, written, quarantined


def _flush_market_messages(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO market_messages (msg_ts, msg_id, channel, code, title, content,
                                         catalyst_type, strength, url, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (msg_ts, msg_id) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content, source=EXCLUDED.source
        """, batch)
    tsdb_conn.commit()


# ==========================================
# 3. opening_stock_dynamic_news → news_telegraph
# ==========================================
def migrate_opening_news(mysql_conn, tsdb_conn):
    print("\n🔄 [3/8] opening_stock_dynamic_news → news_telegraph")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM opening_stock_dynamic_news")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    cur.execute("SELECT * FROM opening_stock_dynamic_news ORDER BY date ASC, time ASC")
    written = quarantined = 0
    batch = []

    for row in cur:
        d = row.get("date")
        t = row.get("time")
        if isinstance(d, str):
            date_str = d
        elif d:
            date_str = d.isoformat()
        else:
            quarantined += 1
            continue

        # time is unix timestamp (string)
        try:
            unix_ts = int(t)
            dt = datetime.utcfromtimestamp(unix_ts) + timedelta(hours=8)
            ts = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except:
            ts = f"{date_str}T00:00:00+08:00"

        news_id = f"live_{row.get('id', '')}"

        # Parse stock JSON array → related_codes
        stock_raw = row.get("stock", "")
        related_codes = None
        if stock_raw:
            try:
                stocks = json.loads(stock_raw)
                codes = []
                for s in stocks:
                    if isinstance(s, list) and len(s) >= 1:
                        codes.append(normalize_code(str(s[0])))
                    elif isinstance(s, dict):
                        codes.append(normalize_code(str(s.get("code", ""))))
                if codes:
                    related_codes = json.dumps(codes)
            except:
                pass

        batch.append((
            ts, news_id, "lovetrade-live",
            None, row.get("comment"),
            None, related_codes, None,
            "lovetrade-mysql"
        ))
        written += 1

        if len(batch) >= 2000:
            _flush_news_telegraph(tsdb_conn, batch)
            batch = []
            if written % 5000 == 0:
                print(f"   ... {written:,}/{total:,}")

    if batch:
        _flush_news_telegraph(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_opening_news", "news_telegraph",
            "OK" if quarantined == 0 else "PARTIAL", total, written, quarantined)
    print(f"   ✅ Written: {written:,}, Quarantined: {quarantined}")
    return total, written, quarantined


def _flush_news_telegraph(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO news_telegraph (pub_ts, news_id, media, title, content,
                                        level, related_codes, url, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (pub_ts, news_id) DO UPDATE SET
                content=EXCLUDED.content, related_codes=EXCLUDED.related_codes, source=EXCLUDED.source
        """, batch)
    tsdb_conn.commit()


# ==========================================
# 4. market_radar → radar_event
# ==========================================
def migrate_market_radar(mysql_conn, tsdb_conn):
    print("\n🔄 [4/8] market_radar → radar_event (296K rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM market_radar")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    cur.execute("SELECT * FROM market_radar ORDER BY date ASC, time ASC")
    written = quarantined = 0
    batch = []

    for row in cur:
        d = row.get("date")
        t = row.get("time")
        if isinstance(d, str):
            date_str = d
        elif d:
            date_str = d.isoformat()
        else:
            quarantined += 1
            continue

        try:
            unix_ts = int(t)
            dt = datetime.utcfromtimestamp(unix_ts) + timedelta(hours=8)
            ts = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except:
            ts = f"{date_str}T00:00:00+08:00"

        event_id = str(row.get("id", ""))
        extra = {
            "stock_name": row.get("stock_name"),
            "lb_status": row.get("lb_status"),
            "status": row.get("status"),
        }

        batch.append((
            ts, event_id, row.get("status", "radar"),
            row.get("status"), row.get("content"),
            json.dumps([normalize_code(row["stock_name"])]) if row.get("stock_name") and len(str(row.get("stock_name","")))==6 else None,
            None, json.dumps(extra, default=str),
            "lovetrade-mysql"
        ))
        written += 1

        if len(batch) >= 3000:
            _flush_radar(tsdb_conn, batch)
            batch = []
            if written % 30000 == 0:
                print(f"   ... {written:,}/{total:,}")

    if batch:
        _flush_radar(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_market_radar", "radar_event",
            "OK" if quarantined == 0 else "PARTIAL", total, written, quarantined)
    print(f"   ✅ Written: {written:,}, Quarantined: {quarantined}")
    return total, written, quarantined


def _flush_radar(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO radar_event (ts, event_id, event_type, title, content,
                                     related_codes, strength, extra, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (ts, event_id) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content,
                extra=EXCLUDED.extra, source=EXCLUDED.source
        """, batch)
    tsdb_conn.commit()


# ==========================================
# 5. plate_movement → sector_daily
# ==========================================
def migrate_plate_movement(mysql_conn, tsdb_conn):
    print("\n🔄 [5/8] plate_movement → sector_daily")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM plate_movement")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    cur.execute("SELECT * FROM plate_movement ORDER BY date ASC, time ASC")
    written = quarantined = 0
    batch = []

    for row in cur:
        d = row.get("date")
        if isinstance(d, str):
            dt = d
        elif d:
            dt = d.isoformat()
        else:
            quarantined += 1
            continue

        sector_code = str(row.get("code", ""))
        if not sector_code:
            quarantined += 1
            continue

        batch.append((
            dt, sector_code, row.get("name"), "concept",
            safe_float(row.get("growth_rate")), None,
            safe_float(row.get("large_force")), safe_float(row.get("cje")),
            None, None, None, "lovetrade-mysql"
        ))
        written += 1

        if len(batch) >= 2000:
            _flush_sector(tsdb_conn, batch)
            batch = []

    if batch:
        _flush_sector(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_plate_movement", "sector_daily",
            "OK" if quarantined == 0 else "PARTIAL", total, written, quarantined)
    print(f"   ✅ Written: {written:,}, Quarantined: {quarantined}")
    return total, written, quarantined


def _flush_sector(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO sector_daily (date, sector_code, sector_name, kind, pct, close,
                                      main_net_inflow, turnover, up_cnt, down_cnt, lead_stocks, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (date, sector_code) DO UPDATE SET
                sector_name=EXCLUDED.sector_name, pct=EXCLUDED.pct,
                main_net_inflow=EXCLUDED.main_net_inflow, turnover=EXCLUDED.turnover, source=EXCLUDED.source
        """, batch)
    tsdb_conn.commit()


# ==========================================
# 6. trading_calendar → trade_cal（仅核对）
# ==========================================
def migrate_trading_calendar(mysql_conn, tsdb_conn):
    print("\n🔄 [6/8] trading_calendar → trade_cal (核对)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM trading_calendar")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    cur.execute("SELECT * FROM trading_calendar ORDER BY date ASC")
    verified = mismatches = 0
    for row in cur:
        d = row.get("date")
        dt = d.isoformat() if d else None
        if not dt: continue
        is_open = 1 if row.get("is_trading_day") else 0

        with tsdb_conn.cursor() as tcur:
            tcur.execute("SELECT is_open FROM trade_cal WHERE market='CN' AND cal_date=%s", (dt,))
            existing = tcur.fetchone()
            if existing:
                if existing[0] != is_open:
                    mismatches += 1
            verified += 1

    log_mig(tsdb_conn, "mig_trading_cal", "trade_cal",
            "OK", total, 0, 0, f"verify_only: {verified} checked, {mismatches} mismatches")
    print(f"   ✅ Verified: {verified:,}, Mismatches: {mismatches}")
    return total, 0, 0


# ==========================================
# 7. catalyst_* → D12 prediction/cognition
# ==========================================
def migrate_catalyst(mysql_conn, tsdb_conn):
    print("\n🔄 [7/8] catalyst_* → D12 prediction/cognition")
    cur = mysql_conn.cursor()

    # catalyst_predictions → prediction
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_predictions")
    pred_total = cur.fetchone()["cnt"]
    print(f"   catalyst_predictions: {pred_total:,} rows")

    cur.execute("SELECT * FROM catalyst_predictions ORDER BY id ASC")
    written_pred = quarantined_pred = 0

    for row in cur:
        pred_id = f"P-{row.get('id', '')}"
        ct = row.get("created_time")
        if isinstance(ct, datetime):
            created_at = ct.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        elif ct:
            created_at = str(ct).replace(" ", "T") + "+08:00"
        else:
            quarantined_pred += 1
            continue

        d = row.get("date")
        check_date = d.isoformat() if isinstance(d, date) else (str(d)[:10] if d else "2026-10-07")

        # Map status to result
        status = row.get("status", "pending")
        result_map = {"verified": "hit", "failed": "miss", "pending": "pending", "expired": "expired"}
        result = result_map.get(status, "pending")

        falsify = json.dumps({
            "metric": row.get("verify_metrics") or "",
            "threshold": 0, "direction": "above",
            "target_topic": row.get("target_topic", ""),
            "time_window": row.get("time_window", ""),
        }, default=str)

        confidence = int(float(row.get("confidence", 0.5) or 0.5) * 100)
        confidence = max(0, min(100, confidence))

        with tsdb_conn.cursor() as tcur:
            tcur.execute("""
                INSERT INTO prediction (prediction_id, created_at, statement, category,
                                        confidence_pct, falsify, check_date,
                                        result, result_note, source, ingest_ts)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (prediction_id) DO UPDATE SET
                    statement=EXCLUDED.statement, result=EXCLUDED.result,
                    result_note=EXCLUDED.result_note, source=EXCLUDED.source
            """, (
                pred_id, created_at,
                row.get("prediction", ""),
                row.get("prediction_type", "产业"),
                confidence, falsify, check_date,
                result, row.get("verified_note") or row.get("actual_outcome"),
                "lovetrade-mysql"
            ))
        tsdb_conn.commit()
        written_pred += 1

    # catalyst_impacts → cognition
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_impacts")
    impact_total = cur.fetchone()["cnt"]
    print(f"   catalyst_impacts: {impact_total:,} rows")

    cur.execute("SELECT * FROM catalyst_impacts ORDER BY id ASC")
    written_cog = 0

    for row in cur:
        cog_id = f"F-{row.get('id', '')}"
        ct = row.get("created_time")
        if isinstance(ct, datetime):
            created_at = ct.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        elif ct:
            created_at = str(ct).replace(" ", "T") + "+08:00"
        else:
            continue

        confidence = float(row.get("confidence", 0.5) or 0.5)
        confidence = max(0, min(1, confidence))

        with tsdb_conn.cursor() as tcur:
            tcur.execute("""
                INSERT INTO cognition (cognition_id, version, type, title, statement, source,
                                       confidence, status, regime_scope, falsifications,
                                       created_at, updated_at, ingest_ts)
                VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (cognition_id, version) DO UPDATE SET
                    title=EXCLUDED.title, statement=EXCLUDED.statement,
                    updated_at=EXCLUDED.updated_at, source=EXCLUDED.source
            """, (
                cog_id, row.get("message_type", "impact"),
                row.get("message_summary", "")[:200],
                row.get("detailed_analysis", ""),
                "lovetrade-mysql", confidence,
                row.get("lifecycle_stage", "active"),
                json.dumps({"system_state_before": row.get("system_state_before")}, default=str) if row.get("system_state_before") else None,
                json.dumps({"verified_result": row.get("verified_result"), "verification_note": row.get("verification_note")}, default=str),
                created_at, created_at
            ))
        tsdb_conn.commit()
        written_cog += 1

    # catalyst_system_states → cognition (M- prefix)
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_system_states")
    state_total = cur.fetchone()["cnt"]
    print(f"   catalyst_system_states: {state_total:,} rows")

    cur.execute("SELECT * FROM catalyst_system_states ORDER BY id ASC")
    written_state = 0

    for row in cur:
        cog_id = f"M-{row.get('id', '')}"
        ct = row.get("created_time")
        if isinstance(ct, datetime):
            created_at = ct.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        elif ct:
            created_at = str(ct).replace(" ", "T") + "+08:00"
        else:
            continue

        with tsdb_conn.cursor() as tcur:
            tcur.execute("""
                INSERT INTO cognition (cognition_id, version, type, title, statement, source,
                                       confidence, status, regime_scope,
                                       created_at, updated_at, ingest_ts)
                VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (cognition_id, version) DO UPDATE SET
                    title=EXCLUDED.title, statement=EXCLUDED.statement, source=EXCLUDED.source
            """, (
                cog_id, "system_state",
                f"Phase: {row.get('overall_phase', '')}",
                row.get("overall_note", ""),
                "lovetrade-mysql", 0.5, "active",
                json.dumps({
                    "phase": row.get("overall_phase"),
                    "topic_states": row.get("topic_states"),
                    "global_coupling": row.get("global_coupling"),
                    "sentiment": row.get("sentiment"),
                    "evolution_direction": row.get("evolution_direction"),
                }, default=str),
                created_at, created_at
            ))
        tsdb_conn.commit()
        written_state += 1

    # catalyst_active_messages → just count
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_active_messages")
    msg_total = cur.fetchone()["cnt"]
    print(f"   catalyst_active_messages: {msg_total:,} rows (logged, not migrated separately)")

    total = pred_total + impact_total + state_total + msg_total
    written = written_pred + written_cog + written_state

    log_mig(tsdb_conn, "mig_catalyst", "prediction+cognition",
            "OK", total, written, 0,
            f"pred={written_pred} cog={written_cog} state={written_state}")
    print(f"   ✅ Written: {written:,} (pred={written_pred}, cog={written_cog}, state={written_state})")
    return total, written, 0


# ==========================================
# 8. topic_stock → stock_sector_map
# ==========================================
def migrate_topic_stock(mysql_conn, tsdb_conn):
    print("\n🔄 [8/8] topic_stock → stock_sector_map")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM topic_stock")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

    # Join with topic table for topic name
    cur.execute("""
        SELECT ts.id, ts.stock_id, ts.stock_name, ts.category_id, ts.category_name,
               ts.reason, ts.is_hot, ts.hot, ts.is_new,
               t.name as topic_name
        FROM topic_stock ts
        LEFT JOIN topic t ON ts.category_id = t.id
        ORDER BY ts.id ASC
    """)
    written = quarantined = 0
    batch = []
    today = date.today().isoformat()

    for row in cur:
        stock_id = row.get("stock_id", "")
        if not stock_id:
            quarantined += 1
            continue

        code = normalize_code(stock_id)
        sector_code = f"theme_{row.get('category_id', '')}"
        sector_name = row.get("category_name") or row.get("topic_name") or f"topic_{row.get('category_id')}"

        batch.append((
            code, sector_code, sector_name, "theme",
            today, None, "lovetrade-mysql"
        ))
        written += 1

        if len(batch) >= 2000:
            _flush_sector_map(tsdb_conn, batch)
            batch = []
            if written % 5000 == 0:
                print(f"   ... {written:,}/{total:,}")

    if batch:
        _flush_sector_map(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_topic_stock", "stock_sector_map",
            "OK" if quarantined == 0 else "PARTIAL", total, written, quarantined)
    print(f"   ✅ Written: {written:,}, Quarantined: {quarantined}")
    return total, written, quarantined


def _flush_sector_map(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO stock_sector_map (code, sector_code, sector_name, kind,
                                          effective_from, effective_to, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (code, sector_code, kind, effective_from) DO UPDATE SET
                sector_name=EXCLUDED.sector_name, source=EXCLUDED.source
        """, batch)
    tsdb_conn.commit()


# ==========================================
# Main
# ==========================================
def main():
    print("=" * 60)
    print("📦 lovetrade MySQL → market_tsdb ETL (v2)")
    print(f"   Source: {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")
    print(f"   Time: {datetime.now().isoformat()}")
    print("=" * 60)

    mysql_conn = get_mysql_conn()
    tsdb_conn = get_tsdb_conn()
    results = {}
    total_src = total_written = total_quarantined = 0

    try:
        for name, func in [
            ("index_trend", migrate_index_trend),
            ("market_message", migrate_market_message),
            ("opening_news", migrate_opening_news),
            ("market_radar", migrate_market_radar),
            ("plate_movement", migrate_plate_movement),
            ("trading_calendar", migrate_trading_calendar),
            ("catalyst", migrate_catalyst),
            ("topic_stock", migrate_topic_stock),
        ]:
            try:
                src, written, quarantined = func(mysql_conn, tsdb_conn)
                results[name] = {"source": src, "written": written, "quarantined": quarantined}
                total_src += src
                total_written += written
                total_quarantined += quarantined
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
                traceback.print_exc()
                results[name] = {"source": 0, "written": 0, "quarantined": 0, "error": str(e)}
    finally:
        mysql_conn.close()
        tsdb_conn.close()

    print("\n" + "=" * 60)
    print("📊 Migration Summary")
    print("=" * 60)
    print(f"{'Table':30s} {'Source':>10s} {'Written':>10s} {'Quarantined':>12s}")
    print("-" * 65)
    for name, r in results.items():
        err = " ❌" if "error" in r else ""
        print(f"{name:30s} {r['source']:>10,} {r['written']:>10,} {r['quarantined']:>12,}{err}")
    print("-" * 65)
    print(f"{'TOTAL':30s} {total_src:>10,} {total_written:>10,} {total_quarantined:>12,}")

    # Gate check
    gate_ok = True
    for name, r in results.items():
        if "error" in r:
            gate_ok = False
        elif r["source"] != r["written"] + r["quarantined"]:
            # trading_calendar is verify-only (written=0 is OK)
            if name == "trading_calendar":
                continue
            gate_ok = False

    if gate_ok:
        print("\n✅ Z3 门禁通过")
    else:
        print("\n❌ Z3 门禁失败")
        for name, r in results.items():
            if "error" in r:
                print(f"   {name}: ERROR - {r['error']}")
            elif r["source"] != r["written"] + r["quarantined"] and name != "trading_calendar":
                print(f"   {name}: source={r['source']}, written={r['written']}, quarantine={r['quarantined']}")

    return results, gate_ok


if __name__ == "__main__":
    results, gate_ok = main()
    sys.exit(0 if gate_ok else 1)
