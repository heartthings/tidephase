#!/usr/bin/env python3
"""补跑 Z3 缺失迁移：catalyst_* → prediction/cognition + topic_stock → stock_sector_map"""
import json, os, sys, traceback
from datetime import datetime, date
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

def get_mysql_conn():
    return pymysql.connect(**MYSQL_CONFIG)

def get_tsdb_conn():
    with open(SECRETS_PATH) as f:
        secrets = yaml.safe_load(f) or {}
    db = secrets.get("database", {})
    return psycopg2.connect(
        host="127.0.0.1", port=15432,
        dbname="market_tsdb",
        user="postgres", password=db.get("duser_admin_password", ""),
    )

def safe_float(v):
    if v is None: return None
    try: return float(v)
    except: return None

def normalize_code(raw):
    raw = str(raw).strip()
    if len(raw) == 6 and raw.isdigit():
        if raw.startswith("6"): return f"sh{raw}"
        if raw.startswith(("0", "3")): return f"sz{raw}"
        if raw.startswith(("4", "8")): return f"bj{raw}"
    return raw

def log_mig(tsdb_conn, job, table, status, rows_in, rows_written, rows_quarantined, note=""):
    with tsdb_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingest_log (job, trigger, domain, target_table, source_used, status,
                                    rows_in, rows_written, rows_quarantined, note)
            VALUES (%s, 'migration', 'pipeline', %s, 'lovetrade-mysql', %s, %s, %s, %s, %s)
        """, (job, table, status, rows_in, rows_written, rows_quarantined, note))
    tsdb_conn.commit()

def migrate_catalyst(mysql_conn, tsdb_conn):
    print("\n🔄 catalyst_* → prediction/cognition")
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

        status = row.get("status", "pending")
        result_map = {"verified": "hit", "failed": "miss", "pending": "pending", "expired": "expired"}
        result = result_map.get(status, "pending")

        falsify = json.dumps({
            "metric": row.get("verify_metrics") or "",
            "threshold": 0, "direction": "above",
            "target_topic": row.get("target_topic") or "",
            "time_window": row.get("time_window") or "",
        }, default=str)

        confidence = int(float(row.get("confidence", 0.5) or 0.5) * 100)
        confidence = max(0, min(100, confidence))
        
        # NOT NULL guards
        category = row.get("prediction_type") or "产业"
        statement = row.get("prediction") or ""

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
                pred_id, created_at, statement, category,
                confidence, falsify, check_date,
                result, row.get("verified_note") or row.get("actual_outcome"),
                "lovetrade-mysql"
            ))
        tsdb_conn.commit()
        written_pred += 1

    print(f"   prediction: written={written_pred}, quarantined={quarantined_pred}")

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
                (row.get("message_summary") or "")[:200] or "no summary",
                row.get("detailed_analysis") or "",
                "lovetrade-mysql", confidence,
                row.get("lifecycle_stage") or "active",
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
                f"Phase: {row.get('overall_phase') or 'unknown'}",
                row.get("overall_note") or "",
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

    total_cog = written_cog + written_state
    total = pred_total + impact_total + state_total + msg_total
    written = written_pred + total_cog

    log_mig(tsdb_conn, "mig_catalyst", "prediction+cognition",
            "OK", total, written, quarantined_pred,
            f"pred={written_pred} cog={written_cog} state={written_state}")
    print(f"   ✅ catalyst total: written={written}, quarantined={quarantined_pred}")
    return total, written, quarantined_pred


def migrate_topic_stock(mysql_conn, tsdb_conn):
    print("\n🔄 topic_stock → stock_sector_map")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM topic_stock")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total:,} rows")

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
    print(f"   ✅ stock_sector_map: written={written}, quarantined={quarantined}")
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


def main():
    print("=" * 60)
    print("📦 补跑缺失迁移: catalyst + topic_stock")
    print("=" * 60)

    mysql_conn = get_mysql_conn()
    tsdb_conn = get_tsdb_conn()

    try:
        s1, w1, q1 = migrate_catalyst(mysql_conn, tsdb_conn)
        s2, w2, q2 = migrate_topic_stock(mysql_conn, tsdb_conn)

        print("\n" + "=" * 60)
        print("📊 补跑 Summary")
        print("=" * 60)
        print(f"  catalyst:    source={s1:,}  written={w1:,}  quarantine={q1}")
        print(f"  topic_stock: source={s2:,}  written={w2:,}  quarantine={q2}")
        print(f"  TOTAL:       source={s1+s2:,}  written={w1+w2:,}  quarantine={q1+q2}")

        ok = (s1 == w1 + q1) and (s2 == w2 + q2)
        print(f"\n{'✅ 补跑完成' if ok else '❌ 存在缺口'}")
    finally:
        mysql_conn.close()
        tsdb_conn.close()


if __name__ == "__main__":
    main()
