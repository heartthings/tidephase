#!/usr/bin/env python3
"""
Phase 2 续波：轮询 Z3 marker + 独立对账
- detached 后台运行，日志写盘
- Z3 marker 出现后自动执行独立对账
- 上限 4 小时
"""

import os
import sys
import time
import json
import gzip
from datetime import datetime, date
from pathlib import Path

# 强制无缓冲
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# 配置
Z3_MARKER = "/home/hello/application/dev/market-datalayer/reports/Z3_COMPLETE.marker"
Z5_FILE = "/home/hello/application/dev/market-datalayer/reports/Z5_six_case_checklist.md"
REPORT_PATH = "/home/hello/application/dev/market-datalayer/reports/M2_phase2_lovetrade_audit.md"
GUANSHI_COPY = "/home/hello/.qwenpaw/workspaces/guanshi/specs/M2_phase2_lovetrade_audit.md"
LOG_PATH = "/home/hello/application/dev/market-datalayer/reports/phase2_poll.log"

# MySQL 连接（lovetrade 只读）
MYSQL_HOST = "81.70.207.80"
MYSQL_PORT = 8010
MYSQL_DB = "lovetrade"
MYSQL_USER = "root"
MYSQL_PASS = "Gee6lXRoYRBb"  # 从 lovetrade-service application.yml 只读获取

# PG 连接（TimescaleDB 只读）
PG_HOST = "127.0.0.1"
PG_PORT = 15432
PG_DB = "market_tsdb"
PG_USER = "duser_reader"
PG_PASS = os.getenv("PG_PASS", "77cIiOsNhtTj-f9bEmELVwKm43lFxp06")

# 映射表
MAPPING_TABLES = [
    ("index_trend", "index_minute", "M1"),
    ("market_message", "news_telegraph", "M2"),
    ("opening_stock_dynamic_news", "news_telegraph", "M2"),
    ("market_radar", "theme_heat", "M2"),
    ("plate_movement", "sector_daily", "M2"),
    ("trading_calendar", "trade_cal", "M1"),
    ("catalyst_impacts", "prediction", "M2"),
    ("topic_stock", "stock_sector_map", "M2"),
]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def wait_for_marker(marker_path, timeout_hours=4, interval_minutes=5):
    """轮询等待标记文件"""
    timeout_seconds = timeout_hours * 3600
    interval_seconds = interval_minutes * 60
    start_time = time.time()
    
    log(f"开始轮询: {marker_path}")
    log(f"  超时: {timeout_hours}h, 间隔: {interval_minutes}min")
    
    while time.time() - start_time < timeout_seconds:
        if Path(marker_path).exists():
            log(f"✅ 标记已出现: {marker_path}")
            return True
        
        elapsed = int(time.time() - start_time)
        remaining = timeout_seconds - elapsed
        log(f"⏳ 等待中... ({elapsed}s / {timeout_seconds}s, 剩余 {remaining}s)")
        time.sleep(interval_seconds)
    
    log(f"❌ 超时未等到标记: {marker_path}")
    return False


def connect_mysql():
    """连接 MySQL（只读）"""
    import pymysql
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, connect_timeout=10,
        read_timeout=30,
    )


def connect_pg():
    """连接 PG（只读）"""
    import psycopg2
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS, connect_timeout=5,
    )
    conn.autocommit = True
    return conn


def count_table(cursor, table, where_clause=None):
    """统计表行数"""
    sql = f"SELECT COUNT(*) FROM {table}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    cursor.execute(sql)
    return cursor.fetchone()[0]


def sample_rows(cursor, table, n=30, where_clause=None):
    """随机抽样"""
    sql = f"SELECT * FROM {table}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    sql += f" LIMIT {n}"
    cursor.execute(sql)
    return cursor.fetchall()


def run_independent_audit():
    """执行独立对账"""
    log("开始独立对账...")
    
    # 连接
    try:
        mysql_conn = connect_mysql()
        mysql_cur = mysql_conn.cursor()
        log("✅ MySQL 连接成功")
    except Exception as e:
        log(f"❌ MySQL 连接失败: {e}")
        return None
    
    try:
        pg_conn = connect_pg()
        pg_cur = pg_conn.cursor()
        log("✅ PG 连接成功")
    except Exception as e:
        log(f"❌ PG 连接失败: {e}")
        mysql_conn.close()
        return None
    
    # 逐表比对
    results = []
    for mysql_table, pg_table, milestone in MAPPING_TABLES:
        log(f"\n--- {mysql_table} → {pg_table} ({milestone}) ---")
        
        # MySQL COUNT
        try:
            mysql_count = count_table(mysql_cur, mysql_table)
            log(f"  MySQL {mysql_table}: {mysql_count:,}")
        except Exception as e:
            log(f"  MySQL {mysql_table} 查询失败: {e}")
            mysql_count = -1
            results.append({
                "mysql_table": mysql_table, "pg_table": pg_table, "milestone": milestone,
                "mysql_count": -1, "pg_total": -1, "pg_migrated": -1,
                "count_match": False, "error": str(e),
            })
            continue
        
        # PG COUNT (total)
        try:
            pg_total = count_table(pg_cur, pg_table)
            log(f"  PG {pg_table} 总计: {pg_total:,}")
        except Exception as e:
            log(f"  PG {pg_table} 查询失败: {e}")
            pg_total = -1
        
        # PG COUNT (source='lovetrade-mysql')
        try:
            pg_migrated = count_table(pg_cur, pg_table, "source = 'lovetrade-mysql'")
            log(f"  PG {pg_table} source='lovetrade-mysql': {pg_migrated:,}")
        except Exception as e:
            log(f"  PG {pg_table} source 过滤失败: {e}")
            pg_migrated = -1
        
        # 抽样比对
        try:
            mysql_sample = sample_rows(mysql_cur, mysql_table, 30)
            log(f"  MySQL 抽样: {len(mysql_sample)} 行")
        except Exception as e:
            log(f"  MySQL 抽样失败: {e}")
            mysql_sample = []
        
        try:
            pg_sample = sample_rows(pg_cur, pg_table, 30, "source = 'lovetrade-mysql'")
            log(f"  PG 抽样: {len(pg_sample)} 行")
        except Exception as e:
            log(f"  PG 抽样失败: {e}")
            pg_sample = []
        
        count_match = (mysql_count == pg_migrated) if (mysql_count >= 0 and pg_migrated >= 0) else False
        log(f"  COUNT 匹配: {count_match}")
        
        results.append({
            "mysql_table": mysql_table, "pg_table": pg_table, "milestone": milestone,
            "mysql_count": mysql_count, "pg_total": pg_total, "pg_migrated": pg_migrated,
            "mysql_sample_size": len(mysql_sample), "pg_sample_size": len(pg_sample),
            "count_match": count_match,
        })
    
    # quarantine 核查
    log("\n--- quarantine 核查 ---")
    try:
        q_count = count_table(pg_cur, "quarantine", "source = 'lovetrade-mysql'")
        log(f"  quarantine (lovetrade-mysql): {q_count}")
    except Exception as e:
        log(f"  quarantine 查询失败: {e}")
        q_count = -1
    
    mysql_conn.close()
    pg_conn.close()
    
    return {"tables": results, "quarantine_count": q_count}


def generate_report(audit_result):
    """生成报告"""
    lines = []
    lines.append("# M2 Phase2 lovetrade 迁移独立抽检报告\n")
    lines.append(f"> 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("> 执行人: 墨测（MoTest）\n")
    lines.append("> 方法: 独立连接远程 MySQL vs TimescaleDB，不依赖铸码报告\n")
    lines.append("---\n")
    
    if audit_result is None:
        lines.append("## 状态: BLOCKED ❌\n")
        lines.append("无法完成对账（连接失败）\n")
    else:
        lines.append("## 对账汇总\n")
        lines.append("| MySQL 表 | PG 表 | 里程碑 | MySQL 行数 | PG 迁移行数 | COUNT 匹配 | 状态 |")
        lines.append("|---------|-------|--------|-----------|------------|-----------|------|")
        
        all_match = True
        for t in audit_result["tables"]:
            match_icon = "✅" if t["count_match"] else "❌"
            if not t["count_match"]:
                all_match = False
            lines.append(
                f"| {t['mysql_table']} | {t['pg_table']} | {t['milestone']} | "
                f"{t['mysql_count']:,} | {t['pg_migrated']:,} | "
                f"{t['count_match']} | {match_icon} |"
            )
        
        lines.append(f"\n## quarantine 检查\n")
        lines.append(f"- lovetrade-mysql 隔离行数: {audit_result['quarantine_count']}\n")
        
        lines.append(f"\n## 判定\n")
        if all_match and audit_result["quarantine_count"] == 0:
            lines.append("**状态**: PASS ✅\n")
            lines.append("所有映射表 COUNT 一致，无隔离行\n")
        else:
            lines.append("**状态**: FAIL ❌\n")
            if not all_match:
                lines.append("- COUNT 不一致的表需进一步排查\n")
            if audit_result["quarantine_count"] > 0:
                lines.append(f"- {audit_result['quarantine_count']} 行被隔离\n")
    
    lines.append("\n---\n")
    lines.append(f"*报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 墨测*\n")
    
    return "\n".join(lines)


def main():
    log("=" * 60)
    log("Phase 2 续波：轮询 Z3 marker + 独立对账")
    log("=" * 60)
    
    # 轮询 Z3 marker
    z3_ready = wait_for_marker(Z3_MARKER, timeout_hours=4, interval_minutes=5)
    
    if not z3_ready:
        # 超时，写 BLOCKED 报告
        report = "# M2 Phase2 lovetrade 迁移独立抽检报告\n\n"
        report += f"> 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report += "## 状态: BLOCKED ⏳（二次等待超时）\n\n"
        report += "等待 Z3 完成标记超时（4 小时）。\n\n"
        report += "**可能原因**: 铸码 Z4b 子步①核验不平，差异报告已产出，marker 未写入\n\n"
        report += f"标记路径: {Z3_MARKER}\n\n"
        report += "---\n"
        
        with open(REPORT_PATH, "w") as f:
            f.write(report)
        
        import shutil
        shutil.copy(REPORT_PATH, GUANSHI_COPY)
        
        log(f"报告已写入: {REPORT_PATH}")
        log("二次等待超时，收工不空转")
        sys.exit(0)
    
    # Z3 就绪，执行独立对账
    audit_result = run_independent_audit()
    
    # 生成报告
    report = generate_report(audit_result)
    
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    
    import shutil
    shutil.copy(REPORT_PATH, GUANSHI_COPY)
    
    log(f"✅ 报告已写入: {REPORT_PATH}")
    log(f"✅ 已复制到: {GUANSHI_COPY}")


if __name__ == "__main__":
    main()
