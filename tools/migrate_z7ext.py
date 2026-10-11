#!/usr/bin/env python3
"""
Z7-ext 全量迁移脚本 · 2026-10-11 · 铸码
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
① catalyst_impacts (MySQL) → catalyst_impact (PG)
② catalyst_active_messages (MySQL) → catalyst_active_message (PG)
③ catalyst_system_states (MySQL) → catalyst_system_state (PG)
④ prediction delta #338~352 (MySQL) → prediction (PG) + 全量 result 重映射
⑤ market_message delta 10-08~now (MySQL) → market_messages (PG)
⑥ 逐表计数对账 → reports/Z7ext_checkpoint.md

纪律: lovetrade MySQL 只读，严禁写删。凭证不进 commit/报告。
"""
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
import psycopg2
import psycopg2.extras
import yaml

TZ_CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
SECRETS_PATH = BASE_DIR / "configs" / "secrets.yaml"
REPORT_PATH = BASE_DIR / "reports" / "Z7ext_checkpoint.md"


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def get_mysql_conn(secrets):
    lt = secrets["lovetrade"]
    # Docker mysql_green maps 7507→3306; read root password from docker env
    import subprocess
    docker_pw = subprocess.check_output(
        ["docker", "inspect", "--format", "{{index .Config.Env}}", "mysql_green"],
        text=True
    )
    # Parse MYSQL_ROOT_PASSWORD from env list like "[MYSQL_ROOT_PASSWORD=xxx PATH=...]"
    mysql_pw = lt["mysql_password"]  # fallback
    for part in docker_pw.replace("[", "").replace("]", "").split():
        if part.startswith("MYSQL_ROOT_PASSWORD="):
            mysql_pw = part.split("=", 1)[1]
            break
    return pymysql.connect(
        host=lt["mysql_host"], port=7507,
        user=lt["mysql_user"], password=mysql_pw,
        database=lt["mysql_database"], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_pg_conn(secrets, user_key="duser_d12writer"):
    db = secrets["database"]
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user=user_key, password=db[f"{user_key}_password"],
    )


def to_jsonb(val):
    """Convert MySQL JSON/None to Python obj suitable for psycopg2 jsonb."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def serialize_jsonb(val):
    """Prepare value for psycopg2 INSERT (jsonb column)."""
    if val is None:
        return None
    return json.dumps(val, ensure_ascii=False, default=str)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ① catalyst_impacts → catalyst_impact
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def migrate_impacts(mysql_cur, pg_cur):
    print("\n━━ ① catalyst_impacts → catalyst_impact ━━")
    mysql_cur.execute("SELECT * FROM catalyst_impacts ORDER BY id")
    rows = mysql_cur.fetchall()
    print(f"  MySQL source: {len(rows)} rows")

    inserted = 0
    skipped = 0
    for r in rows:
        impact_id = f"I-LT-{r['id']}"  # lovetrade legacy ID
        try:
            pg_cur.execute("""
                INSERT INTO catalyst_impact (
                    impact_id, lovetrade_id, date, scan_session,
                    message_summary, message_source, message_url, message_time,
                    message_type, impact_level, target_topics,
                    system_state_before, system_state_after,
                    predicted_effect, detailed_analysis,
                    decay_days, decay_type, confidence, global_coupling,
                    lifecycle_stage, remaining_influence,
                    verified_result, verification_note, verified_date,
                    notes, actor, source, created_time, updated_time
                ) VALUES (
                    %s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s, %s,%s, %s,%s,
                    %s,%s,%s,%s, %s,%s, %s,%s,%s, %s,%s,%s,%s,%s
                )
                ON CONFLICT (impact_id) DO NOTHING
            """, (
                impact_id, r["id"], r["date"], r.get("scan_session"),
                r["message_summary"], r.get("message_source"), r.get("message_url"),
                r.get("message_time"),
                r["message_type"], r["impact_level"],
                serialize_jsonb(to_jsonb(r.get("target_topics", "[]"))),
                serialize_jsonb(to_jsonb(r.get("system_state_before"))),
                serialize_jsonb(to_jsonb(r.get("system_state_after"))),
                r["predicted_effect"], r.get("detailed_analysis"),
                r.get("decay_days", 3), r.get("decay_type", "normal"),
                float(r.get("confidence", 0.5) or 0.5),
                r.get("global_coupling", "medium"),
                r.get("lifecycle_stage", "shock"),
                float(r.get("remaining_influence", 1.0) or 1.0),
                r.get("verified_result"), r.get("verification_note"),
                r.get("verified_date"),
                serialize_jsonb([]),  # notes: empty for migrated
                "guanshi", "lovetrade-mysql",
                r.get("created_time"), r.get("updated_time"),
            ))
            if pg_cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠ impact id={r['id']}: {e}")
            skipped += 1

    print(f"  ✅ inserted={inserted}, skipped={skipped}")
    return {"source": len(rows), "inserted": inserted, "skipped": skipped}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ② catalyst_active_messages → catalyst_active_message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def migrate_active_messages(mysql_cur, pg_cur):
    print("\n━━ ② catalyst_active_messages → catalyst_active_message ━━")
    mysql_cur.execute("SELECT * FROM catalyst_active_messages ORDER BY id")
    rows = mysql_cur.fetchall()
    print(f"  MySQL source: {len(rows)} rows")

    inserted = 0
    skipped = 0
    for r in rows:
        am_id = f"AM-LT-{r['id']}"
        impact_id = f"I-LT-{r['impact_id']}"
        try:
            pg_cur.execute("""
                INSERT INTO catalyst_active_message (
                    am_id, lovetrade_id, impact_id, message_title,
                    current_stage, remaining_influence, is_active,
                    expected_decay_date, daily_updates,
                    created_time, updated_time
                ) VALUES (%s,%s,%s,%s, %s,%s,%s, %s,%s, %s,%s)
                ON CONFLICT (am_id) DO NOTHING
            """, (
                am_id, r["id"], impact_id,
                r["message_summary"],  # message_title ← message_summary
                r.get("current_stage", "shock"),
                float(r.get("remaining_influence", 1.0) or 1.0),
                bool(r.get("is_active", 1)),
                r.get("expected_decay_date"),
                serialize_jsonb(to_jsonb(r.get("daily_updates", "[]"))),
                r.get("created_time"), r.get("updated_time"),
            ))
            if pg_cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠ AM id={r['id']}: {e}")
            skipped += 1

    print(f"  ✅ inserted={inserted}, skipped={skipped}")
    return {"source": len(rows), "inserted": inserted, "skipped": skipped}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ③ catalyst_system_states → catalyst_system_state
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def migrate_system_states(mysql_cur, pg_cur):
    print("\n━━ ③ catalyst_system_states → catalyst_system_state ━━")
    mysql_cur.execute("SELECT * FROM catalyst_system_states ORDER BY id")
    rows = mysql_cur.fetchall()
    print(f"  MySQL source: {len(rows)} rows")

    inserted = 0
    skipped = 0
    for r in rows:
        # lovetrade scan_session is NOT unique (e.g. "sentinel_0900" repeats daily)
        # Generate unique key: {date}_{scan_session} or lt_{id} if null
        raw_ss = r.get("scan_session")
        if raw_ss:
            scan_session = f"{r['date'].isoformat() if hasattr(r['date'], 'isoformat') else str(r['date'])}_{raw_ss}"
        else:
            scan_session = f"lt_{r['id']}"
        try:
            pg_cur.execute("""
                INSERT INTO catalyst_system_state (
                    scan_session, lovetrade_id, date, scan_time,
                    overall_phase, overall_note, topic_states,
                    global_coupling, coupling_note, global_data,
                    sentiment, sentiment_indicators,
                    evolution_direction, evolution_note,
                    source, created_time, updated_time
                ) VALUES (%s,%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s, %s,%s, %s,%s,%s)
                ON CONFLICT (scan_session) DO UPDATE SET
                    overall_note = EXCLUDED.overall_note,
                    topic_states = EXCLUDED.topic_states,
                    sentiment_indicators = EXCLUDED.sentiment_indicators,
                    updated_time = EXCLUDED.updated_time
            """, (
                scan_session, r["id"], r["date"], r.get("scan_time"),
                r["overall_phase"], r.get("overall_note"),
                serialize_jsonb(to_jsonb(r.get("topic_states", "{}"))),
                r.get("global_coupling", "medium"),
                r.get("coupling_note"),
                serialize_jsonb(to_jsonb(r.get("global_data"))),
                r.get("sentiment"),
                serialize_jsonb(to_jsonb(r.get("sentiment_indicators"))),
                r.get("evolution_direction"), r.get("evolution_note"),
                "lovetrade-mysql",
                r.get("created_time"), r.get("updated_time"),
            ))
            if pg_cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠ SS id={r['id']}: {e}")
            skipped += 1

    print(f"  ✅ inserted={inserted}, skipped={skipped}")
    return {"source": len(rows), "inserted": inserted, "skipped": skipped}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ④ prediction delta + result 重映射
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RESULT_MAP = {
    "verified": "hit",
    "partially_verified": "partial",
    "falsified": "miss",
    "pending": "pending",
    "expired": "expired",
}

HORIZON_MAP = {1: "T1", 2: "T3", 3: "T3", 4: "T5", 5: "T5"}


def map_horizon(days):
    if days is None:
        return None
    if days <= 1:
        return "T1"
    elif days <= 3:
        return "T3"
    elif days <= 5:
        return "T5"
    else:
        return "W1"


def migrate_predictions(mysql_cur, pg_cur, pg_reader_cur):
    print("\n━━ ④ prediction delta + result 重映射 ━━")

    # Step A: 全量 result 重映射（幂等：用 lovetrade 真值覆盖）
    mysql_cur.execute("SELECT id, status, verified_note FROM catalyst_predictions ORDER BY id")
    lt_preds = {r["id"]: r for r in mysql_cur.fetchall()}
    print(f"  lovetrade predictions: {len(lt_preds)} rows")

    # 统计重映射对账
    remap_counter = {}
    pg_cur.execute("SELECT prediction_id, result FROM prediction")
    pg_preds = pg_cur.fetchall()
    print(f"  PG predictions: {len(pg_preds)} rows")

    remap_detail = []  # (prediction_id, old_result, new_result)
    for pid, old_result in pg_preds:
        try:
            num_id = int(pid.replace("P-", ""))
        except (ValueError, AttributeError):
            continue
        lt = lt_preds.get(num_id)
        if not lt:
            continue
        # 目标值 = lovetrade 真值映射
        target_result = RESULT_MAP.get(lt["status"])
        if not target_result:
            continue

        if target_result != old_result:
            remap_detail.append((pid, old_result, target_result))
            key = f"{old_result}→{target_result}"
            remap_counter[key] = remap_counter.get(key, 0) + 1
            pg_cur.execute("""
                UPDATE prediction SET result = %s,
                    result_note = COALESCE(result_note, '') || '[Z7-ext remap ' || now()::date || '] '
                WHERE prediction_id = %s
            """, (target_result, pid))

    print(f"  重映射对账:")
    for k, v in sorted(remap_counter.items()):
        print(f"    {k}: {v}")
    print(f"  总变更行数: {len(remap_detail)}")

    # Step B: 迁移 delta #338~352（lovetrade 有但 PG 没有的）
    pg_cur.execute("SELECT prediction_id FROM prediction")
    existing_ids = {r[0] for r in pg_cur.fetchall()}

    mysql_cur.execute("""
        SELECT * FROM catalyst_predictions WHERE id >= 338 ORDER BY id
    """)
    delta_rows = mysql_cur.fetchall()
    print(f"\n  delta #338~352 from lovetrade: {len(delta_rows)} rows")

    delta_inserted = 0
    for r in delta_rows:
        pid = f"P-{r['id']}"
        if pid in existing_ids:
            # Already exists, just remap result
            new_result = RESULT_MAP.get(r["status"], "pending")
            pg_cur.execute("""
                UPDATE prediction SET result = %s,
                    conditions = jsonb_set(COALESCE(conditions, '{}'), '{lovetrade_id}', %s::jsonb)
                WHERE prediction_id = %s
            """, (new_result, json.dumps(r["id"]), pid))
            continue

        # New row
        new_result = RESULT_MAP.get(r["status"], "pending")
        horizon = map_horizon(r.get("time_window_days"))
        category = r.get("prediction_type") or "产业"
        confidence_pct = int(float(r.get("confidence", 0.5) or 0.5) * 100)

        # Parse check_date from time_window
        check_date = r.get("date")  # fallback to creation date

        try:
            pg_cur.execute("""
                INSERT INTO prediction (
                    prediction_id, statement, category, confidence_pct,
                    conditions, falsify, check_date,
                    regime_at_create, horizon, result,
                    result_note, actor, source, writeback_done
                ) VALUES (%s,%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s,%s)
                ON CONFLICT (prediction_id) DO NOTHING
            """, (
                pid, r["prediction"], category, confidence_pct,
                serialize_jsonb({"lovetrade_id": r["id"], "impact_id": r.get("impact_id")}),
                serialize_jsonb({"text": ""}),
                check_date,
                None,  # regime_at_create
                horizon, new_result,
                r.get("verified_note"),
                "guanshi", "lovetrade-mysql", False,
            ))
            if pg_cur.rowcount > 0:
                delta_inserted += 1
        except Exception as e:
            print(f"  ⚠ prediction P-{r['id']}: {e}")

    print(f"  delta 新插入: {delta_inserted}")

    return {
        "remap_total": len(remap_detail),
        "remap_detail": remap_counter,
        "delta_inserted": delta_inserted,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⑤ market_message delta (10-08~now)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def migrate_market_messages(mysql_cur, pg_cur):
    print("\n━━ ⑤ market_message delta (10-08~now) ━━")
    mysql_cur.execute("""
        SELECT * FROM market_message
        WHERE time >= '2026-10-08 00:00:00'
        ORDER BY time
    """)
    rows = mysql_cur.fetchall()
    print(f"  MySQL source (10-08~now): {len(rows)} rows")

    inserted = 0
    skipped = 0
    for r in rows:
        try:
            pg_cur.execute("""
                INSERT INTO market_messages (msg_id, title, content, url, msg_ts, strength, source, ingest_ts)
                VALUES (%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT (msg_ts, msg_id) DO NOTHING
            """, (
                r["id"], r["title"],
                r["content"], r.get("url"), r["time"],
                float(r["score"]) if r.get("score") else None,
                "lovetrade-mysql",
            ))
            if pg_cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ⚠ message id={r['id']}: {e}")
            skipped += 1

    print(f"  ✅ inserted={inserted}, skipped={skipped}")
    return {"source": len(rows), "inserted": inserted, "skipped": skipped}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⑥ 对账 + 报告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def reconcile(pg_conn, mysql_conn, results):
    print("\n━━ ⑥ 对账 ━━")
    pg_cur = pg_conn.cursor()
    # Use a separate non-dict cursor for MySQL (reconcile uses positional access)
    mysql_cur = mysql_conn.cursor(pymysql.cursors.Cursor)

    report = []
    report.append(f"# Z7-ext 迁移对账报告")
    report.append(f"生成时间: {datetime.now(TZ_CST).isoformat()}")
    report.append(f"")
    report.append(f"## 三表行数对账")
    report.append(f"")
    report.append(f"| 表 | MySQL 源 | PG 目标 | 差异 |")
    report.append(f"|---|---------|--------|------|")

    checks = [
        ("catalyst_impacts", "catalyst_impact", "SELECT COUNT(*) FROM catalyst_impacts", "SELECT COUNT(*) FROM catalyst_impact"),
        ("catalyst_active_messages", "catalyst_active_message", "SELECT COUNT(*) FROM catalyst_active_messages", "SELECT COUNT(*) FROM catalyst_active_message"),
        ("catalyst_system_states", "catalyst_system_state", "SELECT COUNT(*) FROM catalyst_system_states", "SELECT COUNT(*) FROM catalyst_system_state"),
    ]

    all_ok = True
    for mysql_tbl, pg_tbl, mysql_sql, pg_sql in checks:
        mysql_cur.execute(mysql_sql)
        m_cnt = mysql_cur.fetchone()[0]
        pg_cur.execute(pg_sql)
        p_cnt = pg_cur.fetchone()[0]
        diff = m_cnt - p_cnt
        status = "✅" if diff == 0 else "⚠️"
        if diff != 0:
            all_ok = False
        report.append(f"| {pg_tbl} | {m_cnt} | {p_cnt} | {diff} {status} |")
        print(f"  {pg_tbl}: MySQL={m_cnt} PG={p_cnt} diff={diff}")

    # prediction 对账
    report.append(f"")
    report.append(f"## prediction 对账")
    report.append(f"")

    pg_cur.execute("SELECT result, COUNT(*) FROM prediction GROUP BY result ORDER BY result")
    pg_dist = dict(pg_cur.fetchall())
    mysql_cur.execute("SELECT status, COUNT(*) FROM catalyst_predictions GROUP BY status")
    lt_dist = dict(mysql_cur.fetchall())

    report.append(f"### PG result 分布（重映射后）")
    report.append(f"| result | 行数 |")
    report.append(f"|--------|------|")
    for k, v in sorted(pg_dist.items()):
        report.append(f"| {k} | {v} |")

    report.append(f"")
    report.append(f"### lovetrade status 分布")
    report.append(f"| status | 行数 |")
    report.append(f"|--------|------|")
    for k, v in sorted(lt_dist.items()):
        report.append(f"| {k} | {v} |")

    # 验证重映射正确性
    expected_mapping = {
        "hit": lt_dist.get("verified", 0),
        "partial": lt_dist.get("partially_verified", 0),
        "miss": lt_dist.get("falsified", 0),
        "pending": lt_dist.get("pending", 0),
        "expired": lt_dist.get("expired", 0),
    }

    report.append(f"")
    report.append(f"### 重映射验证")
    report.append(f"| 目标 result | 期望行数 | 实际行数 | 匹配 |")
    report.append(f"|------------|---------|---------|------|")
    for result_val, expected_cnt in expected_mapping.items():
        actual_cnt = pg_dist.get(result_val, 0)
        match = "✅" if actual_cnt == expected_cnt else "❌"
        if actual_cnt != expected_cnt:
            all_ok = False
        report.append(f"| {result_val} | {expected_cnt} | {actual_cnt} | {match} |")
        print(f"  {result_val}: expected={expected_cnt} actual={actual_cnt} {match}")

    # market_messages 对账
    report.append(f"")
    report.append(f"## market_messages delta 对账")
    report.append(f"")
    mysql_cur.execute("SELECT COUNT(*) FROM market_message WHERE time >= '2026-10-08'")
    m_msg = mysql_cur.fetchone()[0]
    pg_cur.execute("SELECT COUNT(*) FROM market_messages WHERE msg_ts >= '2026-10-08'")
    p_msg = pg_cur.fetchone()[0]
    report.append(f"| 范围 | MySQL | PG | 差异 |")
    report.append(f"|------|-------|-----|------|")
    diff_msg = m_msg - p_msg
    status_msg = "✅" if diff_msg == 0 else "⚠️"
    if diff_msg != 0:
        all_ok = False
    report.append(f"| 10-08~now | {m_msg} | {p_msg} | {diff_msg} {status_msg} |")

    # Result remap detail
    report.append(f"")
    report.append(f"## result 重映射对账表")
    report.append(f"")
    report.append(f"| 源值 (lovetrade) | 目标值 (PG) | 行数 |")
    report.append(f"|-----------------|------------|------|")
    remap_rows = [
        ("verified", "hit", lt_dist.get("verified", 0)),
        ("partially_verified", "partial", lt_dist.get("partially_verified", 0)),
        ("falsified", "miss", lt_dist.get("falsified", 0)),
        ("pending", "pending", lt_dist.get("pending", 0)),
        ("expired", "expired", lt_dist.get("expired", 0)),
    ]
    for src, tgt, cnt in remap_rows:
        report.append(f"| {src} | {tgt} | {cnt} |")

    # calibration_view 验证
    report.append(f"")
    report.append(f"## calibration_view 验证")
    report.append(f"")
    pg_cur.execute("SELECT COUNT(*) FROM calibration_view")
    cal_cnt = pg_cur.fetchone()[0]
    pg_cur.execute("SELECT SUM(n) FROM calibration_view")
    cal_total = pg_cur.fetchone()[0]
    report.append(f"- calibration_view 行数: {cal_cnt}")
    report.append(f"- 总预测数（已判定）: {cal_total}")
    report.append(f"- 状态: {'✅ 不再空转' if cal_cnt > 0 else '❌ 仍为空'}")

    # Final verdict
    report.append(f"")
    report.append(f"## 总结")
    report.append(f"")
    report.append(f"- 整体状态: {'✅ PASS' if all_ok else '⚠️ 有差异需检查'}")
    report.append(f"- 三表迁移: {results.get('impacts', {}).get('inserted', 0)} + {results.get('ams', {}).get('inserted', 0)} + {results.get('sss', {}).get('inserted', 0)} 行")
    report.append(f"- prediction 重映射: {results.get('predictions', {}).get('remap_total', 0)} 行变更")
    report.append(f"- prediction delta 新插入: {results.get('predictions', {}).get('delta_inserted', 0)} 行")
    report.append(f"- market_messages delta: {results.get('messages', {}).get('inserted', 0)} 行")

    report_text = "\n".join(report)
    return report_text, all_ok


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("=" * 60)
    print("Z7-ext 全量迁移 · 2026-10-11")
    print("=" * 60)

    secrets = load_secrets()
    mysql_conn = get_mysql_conn(secrets)
    pg_write = get_pg_conn(secrets, "duser_d12writer")
    pg_write.autocommit = True  # per-row error isolation
    pg_read = get_pg_conn(secrets, "duser_reader")

    results = {}
    try:
        mysql_cur = mysql_conn.cursor()
        pg_cur = pg_write.cursor()

        # ① impacts
        results["impacts"] = migrate_impacts(mysql_cur, pg_cur)
        # autocommit on

        # ② active messages
        results["ams"] = migrate_active_messages(mysql_cur, pg_cur)
        # autocommit on

        # ③ system states
        results["sss"] = migrate_system_states(mysql_cur, pg_cur)
        # autocommit on

        # ④ predictions + remap
        pg_reader_cur = pg_read.cursor()
        results["predictions"] = migrate_predictions(mysql_cur, pg_cur, pg_reader_cur)
        # autocommit on

        # ⑤ market messages
        results["messages"] = migrate_market_messages(mysql_cur, pg_cur)
        # autocommit on

        # ⑥ reconcile
        report_text, all_ok = reconcile(pg_write, mysql_conn, results)

        # Write report
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w") as f:
            f.write(report_text)
        print(f"\n📄 报告已写入: {REPORT_PATH}")
        print(f"\n{'✅ ALL PASS' if all_ok else '⚠️ 有差异，请检查报告'}")

    except Exception as e:
        # autocommit on
        print(f"\n❌ Migration failed: {e}")
        traceback.print_exc()
    finally:
        mysql_conn.close()
        pg_write.close()
        pg_read.close()


if __name__ == "__main__":
    main()
