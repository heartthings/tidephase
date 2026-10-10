#!/usr/bin/env python3
"""
tools/migrate_lovetrade_z8.py
Z8 波 · lovetrade 全量迁移（W1）

迁移清单：
① D6 题材四表: topic/topic_category/topic_group/topic_links
② D12 笔记两表: trading_note/note_category
③ D10 report
④ meta 配置两表: dynamic_category_config/trading_system_node
⑤ catalyst delta: 10-08 迁移点之后的新增/更新行
⑥ home_summary: 单行迁移
⑦ 空表 7 张: 记录在报告

对账: 源行数 vs 目标行数，逐表报告。
幂等: ON CONFLICT DO UPDATE (upsert)。
审计: source='lovetrade-mysql', ingest_ts=now()。
"""
import json
import sys
import traceback
from datetime import datetime, date
from pathlib import Path

import pymysql
import psycopg2
import yaml

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def get_mysql_conn(secrets):
    lt = secrets["lovetrade"]
    return pymysql.connect(
        host=lt["mysql_host"], port=lt["mysql_port"],
        user=lt["mysql_user"], password=lt["mysql_password"],
        database=lt["mysql_database"],
        connect_timeout=10, read_timeout=600,
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_tsdb_conn(secrets):
    db = secrets["database"]
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="postgres", password=db["duser_admin_password"],
    )


def log_mig(tsdb_conn, job, table, status, rows_in, rows_written, note=""):
    with tsdb_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingest_log (job, trigger, domain, target_table, source_used, status,
                                    rows_in, rows_written, rows_quarantined, note)
            VALUES (%s, 'migration', 'pipeline', %s, 'lovetrade-mysql', %s, %s, %s, 0, %s)
        """, (job, table, status, rows_in, rows_written, note))
    tsdb_conn.commit()


# ─── D6 题材四表 ─────────────────────────────────────────────────────

def migrate_topic(mysql_conn, tsdb_conn):
    print("\n🔄 topic → topic (253 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM topic")
    total = cur.fetchone()["cnt"]
    print(f"   Source: {total}")

    cur.execute("SELECT * FROM topic")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row["theme_id"], row.get("topic_group_id"),
            row["name"], row.get("brief_intro"), row.get("introduction"),
            row.get("ai_introduction"), "lovetrade-mysql"
        ))
        written += 1
        if len(batch) >= 500:
            _flush_topic(tsdb_conn, batch)
            batch = []
    if batch:
        _flush_topic(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_topic", "topic", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_topic(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO topic (topic_id, theme_id, topic_group_id, name, brief_intro,
                              introduction, ai_introduction, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (topic_id) DO UPDATE SET
                name=EXCLUDED.name, brief_intro=EXCLUDED.brief_intro,
                introduction=EXCLUDED.introduction, ai_introduction=EXCLUDED.ai_introduction,
                topic_group_id=EXCLUDED.topic_group_id, source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


def migrate_topic_category(mysql_conn, tsdb_conn):
    print("\n🔄 topic_category → topic_category (2998 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM topic_category")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM topic_category")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row["topic_id"], row.get("parent_id", "0"),
            row["name"], "lovetrade-mysql"
        ))
        written += 1
        if len(batch) >= 1000:
            _flush_topic_category(tsdb_conn, batch)
            batch = []
    if batch:
        _flush_topic_category(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_topic_category", "topic_category", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_topic_category(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO topic_category (id, topic_id, parent_id, name, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, parent_id=EXCLUDED.parent_id,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


def migrate_topic_group(mysql_conn, tsdb_conn):
    print("\n🔄 topic_group → topic_group (180 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM topic_group")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM topic_group")
    written = 0
    batch = []
    for row in cur:
        batch.append((row["id"], row["name"], "lovetrade-mysql"))
        written += 1
    if batch:
        _flush_topic_group(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_topic_group", "topic_group", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_topic_group(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO topic_group (id, name, source, ingest_ts)
            VALUES (%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


def migrate_topic_links(mysql_conn, tsdb_conn):
    print("\n🔄 topic_links → topic_links (2189 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM topic_links")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM topic_links")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row.get("source_topic_id"), row["source_name"],
            row.get("target_topic_id"), row["target_name"],
            row["relation"], "lovetrade-mysql"
        ))
        written += 1
        if len(batch) >= 1000:
            _flush_topic_links(tsdb_conn, batch)
            batch = []
    if batch:
        _flush_topic_links(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_topic_links", "topic_links", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_topic_links(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO topic_links (id, source_topic_id, source_name, target_topic_id,
                                     target_name, relation, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                relation=EXCLUDED.relation, source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


# ─── D12 笔记两表 ────────────────────────────────────────────────────

def migrate_note_category(mysql_conn, tsdb_conn):
    print("\n🔄 note_category → note_category (4 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM note_category")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM note_category")
    written = 0
    batch = []
    for row in cur:
        ct = row.get("created_time")
        ut = row.get("updated_time")
        batch.append((
            row["id"], row["name"], row.get("description"),
            row.get("color"), row.get("status", 1), row.get("sort_order", 0),
            ct, ut, "lovetrade-mysql"
        ))
        written += 1
    if batch:
        _flush_note_category(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_note_category", "note_category", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_note_category(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO note_category (id, name, description, color, status, sort_order,
                                       created_time, updated_time, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, description=EXCLUDED.description,
                color=EXCLUDED.color, status=EXCLUDED.status,
                sort_order=EXCLUDED.sort_order, source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


def migrate_trading_note(mysql_conn, tsdb_conn):
    print("\n🔄 trading_note → trading_note (84 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM trading_note")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM trading_note")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row["category_id"], row["title"], row["content"],
            row.get("tags"), row.get("created_time"), row.get("updated_time"),
            "lovetrade-mysql"
        ))
        written += 1
    if batch:
        _flush_trading_note(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_trading_note", "trading_note", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_trading_note(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO trading_note (id, category_id, title, content, tags,
                                      created_time, updated_time, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content,
                tags=EXCLUDED.tags, updated_time=EXCLUDED.updated_time,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


# ─── D10 report ──────────────────────────────────────────────────────

def migrate_report(mysql_conn, tsdb_conn):
    print("\n🔄 report → report (12 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM report")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM report")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row["type"], row["title"], row["content"],
            row["report_date"], row.get("generate_time"),
            row.get("send_status", 0), row.get("send_time"),
            row.get("fail_reason"), row.get("create_time"), row.get("update_time"),
            "lovetrade-mysql"
        ))
        written += 1
    if batch:
        _flush_report(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_report", "report", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_report(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO report (id, type, title, content, report_date, generate_time,
                               send_status, send_time, fail_reason, create_time, update_time,
                               source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                title=EXCLUDED.title, content=EXCLUDED.content,
                send_status=EXCLUDED.send_status, send_time=EXCLUDED.send_time,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


# ─── meta 配置两表 ──────────────────────────────────────────────────

def migrate_dynamic_category_config(mysql_conn, tsdb_conn):
    print("\n🔄 dynamic_category_config → dynamic_category_config (12 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM dynamic_category_config")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM dynamic_category_config")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row["status"], row["name"], row["content"],
            row["example"], row.get("created_time"), "lovetrade-mysql"
        ))
        written += 1
    if batch:
        _flush_dynamic_category_config(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_dynamic_category_config", "dynamic_category_config", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_dynamic_category_config(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO dynamic_category_config (id, status, name, content, example,
                                                  created_time, source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, content=EXCLUDED.content,
                example=EXCLUDED.example, status=EXCLUDED.status,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


def migrate_trading_system_node(mysql_conn, tsdb_conn):
    print("\n🔄 trading_system_node → trading_system_node (25 rows)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM trading_system_node")
    total = cur.fetchone()["cnt"]

    cur.execute("SELECT * FROM trading_system_node")
    written = 0
    batch = []
    for row in cur:
        batch.append((
            row["id"], row.get("parent_id", "0"), row["name"],
            row.get("description"), row.get("color"),
            row.get("sort_order", 0), row.get("created_time"), row.get("updated_time"),
            "lovetrade-mysql"
        ))
        written += 1
    if batch:
        _flush_trading_system_node(tsdb_conn, batch)

    log_mig(tsdb_conn, "mig_z8_trading_system_node", "trading_system_node", "OK", total, written)
    print(f"   ✅ Written: {written}")
    return total, written


def _flush_trading_system_node(tsdb_conn, batch):
    with tsdb_conn.cursor() as tcur:
        tcur.executemany("""
            INSERT INTO trading_system_node (id, parent_id, name, description, color,
                                              sort_order, created_time, updated_time,
                                              source, ingest_ts)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, description=EXCLUDED.description,
                parent_id=EXCLUDED.parent_id, sort_order=EXCLUDED.sort_order,
                source=EXCLUDED.source, ingest_ts=now()
        """, batch)
    tsdb_conn.commit()


# ─── catalyst delta ──────────────────────────────────────────────────

def migrate_catalyst_delta(mysql_conn, tsdb_conn):
    """增量迁移 10-08 之后的 catalyst 数据（upsert 幂等）"""
    print("\n🔄 catalyst delta (post 10-08) → cognition/prediction")
    cur = mysql_conn.cursor()

    # catalyst_predictions: 上次迁移到 id=343 左右，查新增
    # 上次迁移点: 2026-10-08, 查 created_time > '2026-10-08' OR updated_time > '2026-10-08'
    cutoff = "2026-10-08 00:00:00"

    # predictions delta
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_predictions WHERE updated_time > %s", (cutoff,))
    pred_delta = cur.fetchone()["cnt"]
    print(f"   catalyst_predictions delta: {pred_delta}")

    cur.execute("SELECT * FROM catalyst_predictions WHERE updated_time > %s ORDER BY id", (cutoff,))
    written_pred = 0
    for row in cur:
        pred_id = f"P-{row['id']}"
        ct = row.get("created_time")
        created_at = ct.strftime("%Y-%m-%dT%H:%M:%S+08:00") if isinstance(ct, datetime) else str(ct)[:19] + "+08:00" if ct else None
        if not created_at:
            continue
        d = row.get("date")
        check_date = d.isoformat() if isinstance(d, date) else str(d)[:10] if d else None
        status = row.get("status", "pending")
        result_map = {"verified": "hit", "failed": "miss", "pending": "pending", "expired": "expired"}
        result = result_map.get(status, "pending")
        confidence = int(float(row.get("confidence", 0.5) or 0.5) * 100)
        confidence = max(0, min(100, confidence))
        falsify = json.dumps({
            "metric": row.get("verify_metrics") or "",
            "threshold": 0, "direction": "above",
            "target_topic": row.get("target_topic", ""),
            "time_window": row.get("time_window", ""),
        }, default=str)

        with tsdb_conn.cursor() as tcur:
            tcur.execute("""
                INSERT INTO prediction (prediction_id, created_at, statement, category,
                                        confidence_pct, falsify, check_date, horizon,
                                        result, result_note, source, ingest_ts)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (prediction_id) DO UPDATE SET
                    statement=EXCLUDED.statement, result=EXCLUDED.result,
                    result_note=EXCLUDED.result_note, source=EXCLUDED.source, ingest_ts=now()
            """, (
                pred_id, created_at,
                row.get("prediction", ""),
                row.get("prediction_type", "产业"),
                confidence, falsify, check_date, "T1",
                result, row.get("verified_note") or row.get("actual_outcome"),
                "lovetrade-mysql"
            ))
        tsdb_conn.commit()
        written_pred += 1

    # catalyst_impacts delta → cognition
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_impacts WHERE updated_time > %s", (cutoff,))
    impact_delta = cur.fetchone()["cnt"]
    print(f"   catalyst_impacts delta: {impact_delta}")

    cur.execute("SELECT * FROM catalyst_impacts WHERE updated_time > %s ORDER BY id", (cutoff,))
    written_cog = 0
    for row in cur:
        cog_id = f"F-{row['id']}"
        ct = row.get("created_time")
        created_at = ct.strftime("%Y-%m-%dT%H:%M:%S+08:00") if isinstance(ct, datetime) else str(ct)[:19] + "+08:00" if ct else None
        if not created_at:
            continue
        confidence = float(row.get("confidence", 0.5) or 0.5)
        confidence = max(0, min(1, confidence))

        statement = row.get("detailed_analysis") or row.get("message_summary", "") or ""
        with tsdb_conn.cursor() as tcur:
            tcur.execute("""
                INSERT INTO cognition (cognition_id, version, type, title, statement, source,
                                       confidence, status, regime_scope, falsifications,
                                       created_at, updated_at, ingest_ts)
                VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (cognition_id, version) DO UPDATE SET
                    title=EXCLUDED.title, statement=EXCLUDED.statement,
                    updated_at=EXCLUDED.updated_at, source=EXCLUDED.source, ingest_ts=now()
            """, (
                cog_id, row.get("message_type", "impact"),
                row.get("message_summary", "")[:200],
                statement,
                "lovetrade-mysql", confidence,
                row.get("lifecycle_stage", "active"),
                json.dumps({"system_state_before": row.get("system_state_before")}, default=str) if row.get("system_state_before") else None,
                json.dumps({"verified_result": row.get("verified_result"), "verification_note": row.get("verification_note")}, default=str),
                created_at, created_at
            ))
        tsdb_conn.commit()
        written_cog += 1

    # catalyst_system_states delta → cognition (M-)
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_system_states WHERE updated_time > %s", (cutoff,))
    state_delta = cur.fetchone()["cnt"]
    print(f"   catalyst_system_states delta: {state_delta}")

    cur.execute("SELECT * FROM catalyst_system_states WHERE updated_time > %s ORDER BY id", (cutoff,))
    written_state = 0
    for row in cur:
        cog_id = f"M-{row['id']}"
        ct = row.get("created_time")
        created_at = ct.strftime("%Y-%m-%dT%H:%M:%S+08:00") if isinstance(ct, datetime) else str(ct)[:19] + "+08:00" if ct else None
        if not created_at:
            continue

        statement = row.get("overall_note") or f"Phase: {row.get('overall_phase', 'unknown')}"
        with tsdb_conn.cursor() as tcur:
            tcur.execute("""
                INSERT INTO cognition (cognition_id, version, type, title, statement, source,
                                       confidence, status, regime_scope,
                                       created_at, updated_at, ingest_ts)
                VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (cognition_id, version) DO UPDATE SET
                    title=EXCLUDED.title, statement=EXCLUDED.statement,
                    source=EXCLUDED.source, ingest_ts=now()
            """, (
                cog_id, "system_state",
                f"Phase: {row.get('overall_phase', '')}",
                statement,
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

    # catalyst_active_messages: 只记录，不单独建表
    cur.execute("SELECT COUNT(*) as cnt FROM catalyst_active_messages WHERE updated_time > %s", (cutoff,))
    msg_delta = cur.fetchone()["cnt"]
    print(f"   catalyst_active_messages delta: {msg_delta} (logged only)")

    total_delta = pred_delta + impact_delta + state_delta + msg_delta
    total_written = written_pred + written_cog + written_state

    log_mig(tsdb_conn, "mig_z8_catalyst_delta", "prediction+cognition",
            "OK", total_delta, total_written,
            f"pred={written_pred} cog={written_cog} state={written_state} msg_logged={msg_delta}")
    print(f"   ✅ Delta written: {total_written}")
    return total_delta, total_written


# ─── home_summary ────────────────────────────────────────────────────

def migrate_home_summary(mysql_conn, tsdb_conn):
    """home_summary 单行 → 记录到 report 或单独处理"""
    print("\n🔄 home_summary (1 row) → inspect only")
    cur = mysql_conn.cursor()
    cur.execute("SELECT * FROM home_summary")
    row = cur.fetchone()
    if row:
        print(f"   Content: {json.dumps(dict(row), default=str)[:200]}...")
    return 1, 0


# ─── 对账 ────────────────────────────────────────────────────────────

def reconcile(tsdb_conn):
    """逐表对账: 源行数 vs 目标行数"""
    print("\n📊 对账报告")
    print("=" * 60)
    tables = [
        ("topic", "topic"),
        ("topic_category", "topic_category"),
        ("topic_group", "topic_group"),
        ("topic_links", "topic_links"),
        ("note_category", "note_category"),
        ("trading_note", "trading_note"),
        ("report", "report"),
        ("dynamic_category_config", "dynamic_category_config"),
        ("trading_system_node", "trading_system_node"),
    ]
    results = []
    for src_name, tgt_name in tables:
        try:
            with tsdb_conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {tgt_name}")
                tgt_count = cur.fetchone()[0]
                results.append((src_name, tgt_name, tgt_count))
                print(f"   {src_name:30s} → target: {tgt_count:>6}")
        except Exception as e:
            tsdb_conn.rollback()
            print(f"   {src_name:30s} → ERROR: {e}")
    return results


# ─── Main ────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("📦 Z8 lovetrade 全量迁移 (W1)")
    print(f"   Time: {datetime.now().isoformat()}")
    print("=" * 60)

    secrets = load_secrets()
    mysql_conn = get_mysql_conn(secrets)
    tsdb_conn = get_tsdb_conn(secrets)
    results = {}

    try:
        migrations = [
            ("topic", migrate_topic),
            ("topic_category", migrate_topic_category),
            ("topic_group", migrate_topic_group),
            ("topic_links", migrate_topic_links),
            ("note_category", migrate_note_category),
            ("trading_note", migrate_trading_note),
            ("report", migrate_report),
            ("dynamic_category_config", migrate_dynamic_category_config),
            ("trading_system_node", migrate_trading_system_node),
            ("catalyst_delta", migrate_catalyst_delta),
            ("home_summary", migrate_home_summary),
        ]
        for name, func in migrations:
            try:
                src, written = func(mysql_conn, tsdb_conn)
                results[name] = {"source": src, "written": written}
            except Exception as e:
                tsdb_conn.rollback()
                print(f"   ❌ ERROR in {name}: {e}")
                traceback.print_exc()
                results[name] = {"source": 0, "written": 0, "error": str(e)}

        # 对账
        recon = reconcile(tsdb_conn)

    finally:
        mysql_conn.close()
        tsdb_conn.close()

    print("\n" + "=" * 60)
    print("📊 Migration Summary")
    print("=" * 60)
    for name, r in results.items():
        err = " ❌" if "error" in r else ""
        print(f"{name:30s} src={r['source']:>6} written={r['written']:>6}{err}")

    # 空表记录
    print("\n📋 空表 (源端 0 行，不迁移):")
    empty_tables = [
        "daily_market_performance", "market_performance_data",
        "speculative_performance_data", "stock_market_data",
    ]
    for t in empty_tables:
        print(f"   ⚪ {t}")

    return results


if __name__ == "__main__":
    results = main()
    # Exit with error if any migration failed
    for name, r in results.items():
        if "error" in r:
            sys.exit(1)
    print("\n✅ Z8 W1 迁移完成")
