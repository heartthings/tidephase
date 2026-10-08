#!/usr/bin/env python3
"""
Phase 3 续波：轮询 Z5 六案例核对单 + 更新见证单
- detached 后台运行
- Z5 文件出现后自动更新 docs/replay_witness_filled.md
- 上限 3h
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

Z5_FILE = "/home/hello/application/dev/market-datalayer/reports/Z5_six_case_checklist.md"
WITNESS_PATH = "/home/hello/application/dev/market-datalayer/docs/replay_witness_filled.md"
GUANSHI_COPY = "/home/hello/.qwenpaw/workspaces/guanshi/specs/replay_witness_filled.md"
LOG_PATH = "/home/hello/application/dev/market-datalayer/reports/phase3_poll.log"

PG_HOST = "127.0.0.1"
PG_PORT = 15432
PG_DB = "market_tsdb"
PG_USER = "duser_reader"
PG_PASS = os.getenv("PG_PASS", "77cIiOsNhtTj-f9bEmELVwKm43lFxp06")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def wait_for_file(filepath, timeout_hours=3, interval_minutes=5):
    """轮询等待文件出现"""
    timeout_seconds = timeout_hours * 3600
    interval_seconds = interval_minutes * 60
    start_time = time.time()
    
    log(f"开始轮询: {filepath}")
    log(f"  超时: {timeout_hours}h, 间隔: {interval_minutes}min")
    
    while time.time() - start_time < timeout_seconds:
        if Path(filepath).exists():
            log(f"✅ 文件已出现: {filepath}")
            return True
        
        elapsed = int(time.time() - start_time)
        remaining = timeout_seconds - elapsed
        log(f"⏳ 等待中... ({elapsed}s / {timeout_seconds}s, 剩余 {remaining}s)")
        time.sleep(interval_seconds)
    
    log(f"❌ 超时未等到文件: {filepath}")
    return False


def query_data_coverage():
    """查询六案例数据面覆盖"""
    import psycopg2
    
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS, connect_timeout=5,
    )
    conn.autocommit = True
    cur = conn.cursor()
    
    cases = [
        ("C1", "7/28 创业板-7.35%", "2026-07-25", "2026-07-31"),
        ("C2", "7/30 极端分化", "2026-07-28", "2026-08-01"),
        ("C3", "8/4 多重催化失效", "2026-08-01", "2026-08-07"),
        ("C4", "8/10 样本", "2026-08-08", "2026-08-12"),
        ("C5", "9/3 脱钩样本", "2026-08-31", "2026-09-05"),
        ("C6", "9/11 样本", "2026-09-09", "2026-09-13"),
    ]
    
    data_surfaces = [
        ("D1", "index_daily", "date"),
        ("D2", "stock_daily", "date"),
        ("D3", "sentiment_daily", "date"),
        ("D6", "sector_daily", "date"),
        ("D7", "global_daily", "date"),
        ("D10", "news_telegraph", "pub_ts"),
    ]
    
    results = {}
    for case_id, case_name, start, end in cases:
        results[case_id] = {"name": case_name, "start": start, "end": end, "surfaces": {}}
        
        for surface, table, date_col in data_surfaces:
            try:
                if date_col == "pub_ts":
                    cur.execute(f"""
                        SELECT COUNT(*) FROM {table}
                        WHERE {date_col}::date BETWEEN %s AND %s
                    """, (start, end))
                else:
                    cur.execute(f"""
                        SELECT COUNT(*) FROM {table}
                        WHERE {date_col} BETWEEN %s AND %s
                    """, (start, end))
                
                count = cur.fetchone()[0]
                results[case_id]["surfaces"][surface] = count
            except Exception as e:
                results[case_id]["surfaces"][surface] = -1
    
    conn.close()
    return results


def generate_witness_report(coverage, z5_exists):
    """生成见证单"""
    lines = []
    lines.append("# 验收④ 六案例见证单（实填版·续波）\n")
    lines.append(f"> 墨测（MoTest）实测填写 | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("> 数据状态：M2 回填进行中\n")
    lines.append("---\n")
    
    if z5_exists:
        lines.append("## 交叉核对\n")
        lines.append(f"铸码 Z5 核对单已存在: {Z5_FILE}\n")
        lines.append("（差异比对需人工核对 Z5 内容）\n")
    else:
        lines.append("## 交叉核对\n")
        lines.append("铸码 Z5 核对单尚未生成\n")
    
    lines.append("\n## 数据面现状\n")
    lines.append(f"*查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    
    for case_id, case_data in coverage.items():
        lines.append(f"\n### {case_id}: {case_data['name']} ({case_data['start']} ~ {case_data['end']})\n")
        lines.append("| 数据面 | 实测行数 | 状态 |")
        lines.append("|--------|---------|------|")
        
        for surface, count in case_data["surfaces"].items():
            if count > 0:
                status = "✅"
            elif count == 0:
                status = "❌ 缺失"
            else:
                status = "⚠️ 查询失败"
            lines.append(f"| {surface} | {count:,} | {status} |")
        
        # 判定
        all_ok = all(c > 0 for c in case_data["surfaces"].values())
        if all_ok:
            lines.append(f"\n**判定**: ✅ PASS\n")
        else:
            missing = [s for s, c in case_data["surfaces"].items() if c == 0]
            lines.append(f"\n**判定**: ❌ FAIL（缺失: {', '.join(missing)}）\n")
    
    lines.append("\n---\n")
    lines.append(f"*见证单生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 墨测*\n")
    
    return "\n".join(lines)


def main():
    log("=" * 60)
    log("Phase 3 续波：轮询 Z5 + 更新见证单")
    log("=" * 60)
    
    # 轮询 Z5
    z5_ready = wait_for_file(Z5_FILE, timeout_hours=3, interval_minutes=5)
    
    # 无论 Z5 是否出现，都更新见证单（用最新数据）
    log("查询数据覆盖...")
    coverage = query_data_coverage()
    
    # 生成报告
    report = generate_witness_report(coverage, z5_ready)
    
    with open(WITNESS_PATH, "w") as f:
        f.write(report)
    
    import shutil
    shutil.copy(WITNESS_PATH, GUANSHI_COPY)
    
    log(f"✅ 见证单已更新: {WITNESS_PATH}")
    log(f"✅ 已复制到: {GUANSHI_COPY}")
    
    if z5_ready:
        log("Z5 已出现，可交叉核对")
    else:
        log("Z5 未出现，见证单已用最新数据更新")


if __name__ == "__main__":
    main()
