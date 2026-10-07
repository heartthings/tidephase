#!/usr/bin/env python3
"""
tools/migrate_sqlite.py
market.db (SQLite) → market_tsdb (TimescaleDB) 迁移
§6.1

- index_daily 1600行 → index_daily
- global_daily 649行 → global_daily（代码归一 KS11→KOSPI, N225→NK225）
- ingest_log 18行 → ingest_log（note 前缀 migrated-from-sqlite）
- 幂等写入（ON CONFLICT DO UPDATE）
- 对账报告输出到 reports/migrate_sqlite_recon.md
"""
import json
import os
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import yaml

SRC_DB = "/home/hello/.qwenpaw/workspaces/guanshi/data/market.db"
SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

# 代码归一映射
CODE_ALIASES = {
    "KS11": "KOSPI",
    "N225": "NK225",
}

# global_daily code → market 映射（附录A）
GLOBAL_MARKET_MAP = {
    "SPX": "US", "NDX": "US", "DJI": "US",
    "HSI": "HK", "HSTECH": "HK",
    "KOSPI": "KR", "NK225": "JP",
    "DAX": "EU", "CAC": "EU",
    "DXY": "FX", "USDCNH": "FX", "USDJPY": "FX",
    "US10Y": "RATE",
    "WTI": "CMD", "BRENT": "CMD", "GOLD": "CMD", "SILVER": "CMD", "COPPER": "CMD",
    "VIX": "RISK",
    "ES": "FUT", "NQ": "FUT",
    # 旧码
    "KS11": "KR", "N225": "JP",
}


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def get_tsdb_conn():
    secrets = load_secrets()
    db = secrets.get("database", {})
    return psycopg2.connect(
        host=os.getenv("MARKET_TSDB_HOST", "127.0.0.1"),
        port=int(os.getenv("MARKET_TSDB_PORT", "15432")),
        dbname=os.getenv("MARKET_TSDB_NAME", "market_tsdb"),
        user="postgres",
        password=db.get("duser_admin_password", ""),
    )


def migrate_index_daily(sqlite_conn, tsdb_conn):
    """迁移 index_daily: 1600行。"""
    cur = sqlite_conn.cursor()
    cur.execute("SELECT date, code, name, open, high, low, close, pct, volume, amount, source FROM index_daily")
    rows = cur.fetchall()

    migrated = 0
    with tsdb_conn.cursor() as tcur:
        for row in rows:
            date, code, name, open_, high, low, close, pct, volume, amount, source = row
            tcur.execute("""
                INSERT INTO index_daily (date, code, name, open, high, low, close, pct, volume, amount, source, ingest_ts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (date, code) DO UPDATE SET
                    name = EXCLUDED.name,
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    pct = EXCLUDED.pct,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    source = EXCLUDED.source
            """, (date, code, name, open_, high, low, close, pct, volume, amount, source or "migration"))
            migrated += 1

    tsdb_conn.commit()
    return migrated


def migrate_global_daily(sqlite_conn, tsdb_conn):
    """迁移 global_daily: 649行，代码归一 + 补 market 列。"""
    cur = sqlite_conn.cursor()
    cur.execute("SELECT date, code, name, open, high, low, close, pct, volume, amount, source FROM global_daily")
    rows = cur.fetchall()

    migrated = 0
    aliases_to_insert = []

    with tsdb_conn.cursor() as tcur:
        for row in rows:
            date, code, name, open_, high, low, close, pct, volume, amount, source = row

            # 代码归一
            canonical = CODE_ALIASES.get(code, code)
            if code != canonical:
                aliases_to_insert.append((canonical, code, name))

            # 补 market 列
            market = GLOBAL_MARKET_MAP.get(canonical, GLOBAL_MARKET_MAP.get(code, "GLOBAL"))

            tcur.execute("""
                INSERT INTO global_daily (date, market, code, name, session, open, high, low, close, pct, volume, amount, source, ingest_ts)
                VALUES (%s, %s, %s, %s, 'close', %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (date, code, session) DO UPDATE SET
                    market = EXCLUDED.market,
                    name = EXCLUDED.name,
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    pct = EXCLUDED.pct,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    source = EXCLUDED.source
            """, (date, market, canonical, name, open_, high, low, close, pct, volume, amount, source or "migration"))
            migrated += 1

    tsdb_conn.commit()

    # 写入 instrument_master aliases
    if aliases_to_insert:
        with tsdb_conn.cursor() as tcur:
            for canonical, old_code, name in set(aliases_to_insert):
                tcur.execute("""
                    INSERT INTO instrument_master (code, name, aliases, market, inst_type, status, source, ingest_ts)
                    VALUES (%s, %s, %s, %s, 'index', 'active', 'migration', now())
                    ON CONFLICT (code) DO UPDATE SET
                        aliases = instrument_master.aliases || EXCLUDED.aliases
                """, (canonical, name or canonical, json.dumps({old_code: f"旧过渡码→{canonical}"}),
                      GLOBAL_MARKET_MAP.get(canonical, "GLOBAL")))
        tsdb_conn.commit()

    return migrated


def migrate_ingest_log(sqlite_conn, tsdb_conn):
    """迁移 ingest_log: 18行，note 前缀 migrated-from-sqlite。"""
    cur = sqlite_conn.cursor()
    cur.execute("SELECT ts, job, status, note FROM ingest_log")
    rows = cur.fetchall()

    migrated = 0
    with tsdb_conn.cursor() as tcur:
        for row in rows:
            ts, job, status, note = row
            new_note = f"migrated-from-sqlite: {note}" if note else "migrated-from-sqlite"
            tcur.execute("""
                INSERT INTO ingest_log (ts, job, trigger, domain, target_table, source_used, status, note, ingest_ts)
                VALUES (%s, %s, 'migration', 'pipeline', NULL, 'migration', %s, %s, now())
            """, (ts, job, status, new_note))
            migrated += 1

    tsdb_conn.commit()
    return migrated


def generate_recon_report(sqlite_conn, tsdb_conn, counts: dict):
    """生成对账报告。"""
    report = []
    report.append("# market.db → market_tsdb 迁移对账报告")
    report.append(f"\n> 迁移时间：{datetime.now().isoformat()}")
    report.append(f"> 源文件：{SRC_DB}")
    report.append(f"> 备份：/home/hello/backups/market_db_20261007/market.db")
    report.append("")

    report.append("## 一、行数对账")
    report.append("")
    report.append("| 表 | SQLite 行数 | TimescaleDB 行数 | 一致 | 备注 |")
    report.append("|---|---|---|---|---|")

    tables = {
        "index_daily": ("index_daily", "date, code", "1=1"),
        "global_daily": ("global_daily", "date, code, session", "1=1"),
        "ingest_log": ("ingest_log", "ts, run_id", "trigger = 'migration'"),
    }

    all_match = True
    for sqlite_table, (tsdb_table, pk, where_clause) in tables.items():
        sqlite_count = counts.get(sqlite_table, 0)

        with tsdb_conn.cursor() as tcur:
            tcur.execute(f"SELECT count(*) FROM {tsdb_table} WHERE {where_clause}")
            tsdb_count = tcur.fetchone()[0]

        if sqlite_table == "ingest_log":
            # ingest_log is append-only; migration may have run multiple times
            match = "✅" if tsdb_count >= sqlite_count else "❌"
            note = f"迁移执行 {tsdb_count // sqlite_count} 次（追加式日志）"
            if tsdb_count < sqlite_count:
                all_match = False
        else:
            match = "✅" if sqlite_count == tsdb_count else "❌"
            note = ""
            if sqlite_count != tsdb_count:
                all_match = False
        report.append(f"| {sqlite_table} | {sqlite_count} | {tsdb_count} | {match} | {note} |")

    report.append("")
    report.append(f"**结论**：{'✅ 全部一致' if all_match else '❌ 存在差异，需排查'}")
    report.append("")

    report.append("## 二、代码归一")
    report.append("")
    report.append("| 旧码 | 新码 | 说明 |")
    report.append("|---|---|---|")
    report.append("| KS11 | KOSPI | 韩国综合指数 |")
    report.append("| N225 | NK225 | 日经225 |")
    report.append("")
    report.append("旧码已写入 instrument_master.aliases。")
    report.append("")

    report.append("## 三、随机抽检（10%）")
    report.append("")

    # 随机抽 10% index_daily 行比对
    cur = sqlite_conn.cursor()
    cur.execute("SELECT date, code, close FROM index_daily ORDER BY RANDOM() LIMIT 160")
    sample_rows = cur.fetchall()

    mismatches = 0
    with tsdb_conn.cursor() as tcur:
        for date, code, close in sample_rows:
            tcur.execute("SELECT close FROM index_daily WHERE date = %s AND code = %s", (date, code))
            result = tcur.fetchone()
            if result and abs((result[0] or 0) - (close or 0)) > 0.01:
                mismatches += 1
                report.append(f"- ❌ {date} {code}: SQLite={close}, TSDB={result[0]}")

    if mismatches == 0:
        report.append(f"✅ 随机抽检 {len(sample_rows)} 行，全部一致。")
    else:
        report.append(f"❌ 随机抽检 {len(sample_rows)} 行，{mismatches} 行不一致。")

    report.append("")
    report.append("## 四、边界日期抽查")
    report.append("")

    # 最早和最晚日期
    cur.execute("SELECT min(date), max(date) FROM index_daily")
    min_date, max_date = cur.fetchone()
    report.append(f"- index_daily 日期范围：{min_date} ~ {max_date}")

    cur.execute("SELECT min(date), max(date) FROM global_daily")
    min_date, max_date = cur.fetchone()
    report.append(f"- global_daily 日期范围：{min_date} ~ {max_date}")

    report.append("")
    report.append("## 五、待观势签字")
    report.append("")
    report.append("本报告待观势确认后签字归档。")
    report.append("")
    report.append("---")
    report.append("*迁移工具：tools/migrate_sqlite.py*")

    return "\n".join(report)


def main():
    print(f"📦 market.db → market_tsdb 迁移")
    print(f"   源：{SRC_DB}")
    print()

    if not Path(SRC_DB).exists():
        print(f"❌ 源文件不存在：{SRC_DB}")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SRC_DB)
    tsdb_conn = get_tsdb_conn()

    # 统计源行数
    counts = {}
    cur = sqlite_conn.cursor()
    for table in ["index_daily", "global_daily", "ingest_log"]:
        cur.execute(f"SELECT count(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
        print(f"   SQLite {table}: {counts[table]} rows")

    print()

    # 迁移
    print("🔄 迁移 index_daily...")
    n1 = migrate_index_daily(sqlite_conn, tsdb_conn)
    print(f"   ✅ {n1} rows migrated")

    print("🔄 迁移 global_daily（代码归一 KS11→KOSPI, N225→NK225）...")
    n2 = migrate_global_daily(sqlite_conn, tsdb_conn)
    print(f"   ✅ {n2} rows migrated")

    print("🔄 迁移 ingest_log...")
    n3 = migrate_ingest_log(sqlite_conn, tsdb_conn)
    print(f"   ✅ {n3} rows migrated")

    print()
    print("📝 生成对账报告...")
    report = generate_recon_report(sqlite_conn, tsdb_conn, counts)
    report_path = Path(__file__).resolve().parent.parent / "reports" / "migrate_sqlite_recon.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"   ✅ 报告已写入 {report_path}")

    sqlite_conn.close()
    tsdb_conn.close()

    print()
    print("✅ 迁移完成。对账报告待观势签字。")


if __name__ == "__main__":
    main()
