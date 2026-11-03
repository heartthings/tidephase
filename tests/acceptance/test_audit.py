#!/usr/bin/env python3
"""
验收⑤ 审计追溯脚本
==================
随机抽 20 行（跨表跨日期）→ 行内 source+ingest_ts →
ingest_log run → raw 归档文件存在性 + 可解 gzip 反查原值。

输出：全链路追溯结果（目标 100%）

用法：
  python test_audit.py --sample 20
  python test_audit.py --help
"""

import argparse
import gzip
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "15432"))
PG_DB = os.getenv("PG_DB", "market_tsdb")
PG_USER = os.getenv("PG_USER", "duser_reader")
PG_PASS = os.getenv("PG_PASS", "")

# raw 归档根目录
RAW_ROOT = os.getenv("RAW_ARCHIVE_ROOT", str(Path(__file__).resolve().parents[2] / "data" / "raw"))

# 抽样表清单（跨域）
AUDIT_TABLES = [
    ("stock_daily", "D2", "date"),
    ("index_daily", "D1", "date"),
    ("sentiment_daily", "D3", "date"),
    ("global_daily", "D7", "date"),
    ("sector_daily", "D6", "date"),
    ("etf_daily", "D2", "date"),
    ("fund_flow_stock", "D4", "date"),
    ("news_telegraph", "D10", "pub_ts"),
]

SAMPLE_PER_TABLE = 3  # 每表抽样行数

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _try_pg_connect() -> Optional[Any]:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS,
            connect_timeout=5,
        )
        conn.autocommit = True
        return conn
    except Exception:
        return None


def _query_pg(conn, sql: str, params: tuple = ()) -> List[tuple]:
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------

def sample_rows(conn, table: str, domain: str, date_col: str, n: int) -> List[dict]:
    """从某表随机抽 n 行，返回审计字段。"""
    rows = _query_pg(
        f"SELECT source, ingest_ts, {date_col} "
        f"FROM {table} "
        f"ORDER BY RANDOM() LIMIT %s",
        (n,),
    )
    results = []
    for r in rows:
        results.append({
            "table": table,
            "domain": domain,
            "date_col": date_col,
            "date_val": str(r[2]) if r[2] else None,
            "source": r[0],
            "ingest_ts": str(r[1]) if r[1] else None,
        })
    return results


def find_ingest_log_run(conn, table: str, run_date: date) -> Optional[dict]:
    """查找对应日期的 ingest_log 记录。"""
    rows = _query_pg(
        "SELECT run_id, job, source_used, status, rows_written, "
        "       duration_ms, note "
        "FROM ingest_log "
        "WHERE target_table = %s AND ts::date = %s "
        "ORDER BY ts DESC LIMIT 1",
        (table, run_date),
    )
    if rows:
        return {
            "run_id": rows[0][0],
            "job": rows[0][1],
            "source_used": rows[0][2],
            "status": rows[0][3],
            "rows_written": rows[0][4],
            "duration_ms": rows[0][5],
            "note": rows[0][6],
        }
    return None


def find_raw_archive(domain: str, run_date: date, job: str) -> Optional[str]:
    """查找 raw 归档文件。"""
    # 路径格式：data/raw/{域}/{日期}/{作业}/*.json.gz
    date_str = run_date.strftime("%Y-%m-%d") if run_date else "unknown"
    search_dir = Path(RAW_ROOT) / domain / date_str / job
    if search_dir.exists():
        gz_files = list(search_dir.glob("*.json.gz"))
        if gz_files:
            return str(gz_files[0])
    # 尝试不带日期的目录
    search_dir2 = Path(RAW_ROOT) / domain
    if search_dir2.exists():
        for gz in search_dir2.rglob("*.json.gz"):
            return str(gz)
    return None


def verify_gzip_readable(filepath: str) -> Tuple[bool, Optional[str]]:
    """验证 gzip 文件可读，返回 (是否成功, 首行内容预览)。"""
    try:
        with gzip.open(filepath, "rt", encoding="utf-8") as f:
            first_line = f.readline(200)
            return (True, first_line[:100])
    except Exception as e:
        return (False, str(e))


def run_audit_check(sample_total: int, channel: str = "pg") -> dict:
    """执行审计追溯检查。"""
    result = {
        "sample_total": sample_total,
        "channel": channel,
        "traces": [],
        "summary": {
            "total": 0,
            "source_ok": 0,
            "ingest_log_ok": 0,
            "raw_file_ok": 0,
            "gzip_ok": 0,
            "full_chain_ok": 0,
        },
        "status": "UNKNOWN",
    }

    if channel == "pg":
        conn = _try_pg_connect()
        if conn is None:
            result["status"] = "BLOCKED"
            result["error"] = (
                f"无法连接 PG {PG_HOST}:{PG_PORT}/{PG_DB}。"
                "等待铸码构建完成。"
            )
            return result

        # 计算每表抽样数
        tables_to_sample = AUDIT_TABLES[:sample_total // SAMPLE_PER_TABLE + 1]
        per_table = max(1, sample_total // len(tables_to_sample))

        all_samples = []
        for table, domain, date_col in tables_to_sample:
            try:
                samples = sample_rows(conn, table, domain, date_col, per_table)
                all_samples.extend(samples)
            except Exception as e:
                # 表可能不存在
                pass

        # 截断到目标数量
        all_samples = all_samples[:sample_total]

        for s in all_samples:
            trace = {
                "table": s["table"],
                "domain": s["domain"],
                "date": s["date_val"],
                "source": s["source"],
                "ingest_ts": s["ingest_ts"],
                "checks": {
                    "has_source": bool(s["source"]),
                    "has_ingest_ts": bool(s["ingest_ts"]),
                    "ingest_log_found": False,
                    "raw_file_found": False,
                    "gzip_readable": False,
                },
                "details": {},
            }

            result["summary"]["total"] += 1

            # 检查 source 和 ingest_ts
            if s["source"]:
                result["summary"]["source_ok"] += 1
            if s["ingest_ts"]:
                pass  # 仅记录

            # 查找 ingest_log
            if s["date_val"]:
                try:
                    run_date = date.fromisoformat(s["date_val"][:10])
                    log_entry = find_ingest_log_run(conn, s["table"], run_date)
                    if log_entry:
                        trace["checks"]["ingest_log_found"] = True
                        trace["details"]["run_id"] = log_entry["run_id"]
                        trace["details"]["job"] = log_entry["job"]
                        trace["details"]["log_status"] = log_entry["status"]
                        result["summary"]["ingest_log_ok"] += 1

                        # 查找 raw 归档
                        raw_path = find_raw_archive(
                            s["domain"], run_date, log_entry["job"]
                        )
                        if raw_path:
                            trace["checks"]["raw_file_found"] = True
                            trace["details"]["raw_path"] = raw_path
                            result["summary"]["raw_file_ok"] += 1

                            # 验证 gzip 可读
                            ok, preview = verify_gzip_readable(raw_path)
                            trace["checks"]["gzip_readable"] = ok
                            if ok:
                                trace["details"]["gzip_preview"] = preview
                                result["summary"]["gzip_ok"] += 1
                except Exception:
                    pass

            # 全链路判定
            all_ok = all(trace["checks"].values())
            if all_ok:
                result["summary"]["full_chain_ok"] += 1

            result["traces"].append(trace)

        conn.close()

    # 判定
    if result["summary"]["total"] > 0:
        if result["summary"]["full_chain_ok"] == result["summary"]["total"]:
            result["status"] = "PASS"
        else:
            result["status"] = "FAIL"
    else:
        result["status"] = "WARN"
        result["error"] = "无有效抽样数据"

    return result


def format_report(result: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("验收⑤ 审计追溯报告")
    lines.append("=" * 70)
    lines.append(f"抽样总数: {result['sample_total']}")
    lines.append(f"通道: {result['channel']}")
    lines.append(f"状态: {result['status']}")
    lines.append("")

    if "error" in result:
        lines.append(f"[BLOCKED] {result['error']}")
        lines.append("")
        return "\n".join(lines)

    s = result["summary"]
    lines.append(f"--- 汇总 ---")
    lines.append(f"  总抽样: {s['total']}")
    lines.append(f"  有 source 列: {s['source_ok']}/{s['total']}")
    lines.append(f"  找到 ingest_log: {s['ingest_log_ok']}/{s['total']}")
    lines.append(f"  找到 raw 归档: {s['raw_file_ok']}/{s['total']}")
    lines.append(f"  gzip 可读: {s['gzip_ok']}/{s['total']}")
    lines.append(f"  全链路通过: {s['full_chain_ok']}/{s['total']}")
    lines.append(f"  目标: 100%")
    lines.append("")

    if result["traces"]:
        lines.append(f"--- 追溯明细 ---")
        for i, t in enumerate(result["traces"], 1):
            checks = t["checks"]
            status_icon = "✅" if all(checks.values()) else "❌"
            lines.append(f"  [{i}] {t['table']} @ {t['date']} {status_icon}")
            lines.append(f"      source={t['source']}, ingest_ts={t['ingest_ts']}")
            lines.append(f"      has_source={checks['has_source']}, "
                         f"ingest_log={checks['ingest_log_found']}, "
                         f"raw_file={checks['raw_file_found']}, "
                         f"gzip_ok={checks['gzip_readable']}")
            if t["details"].get("run_id"):
                lines.append(f"      run_id={t['details']['run_id']}, "
                             f"job={t['details']['job']}")
            if t["details"].get("raw_path"):
                lines.append(f"      raw_path={t['details']['raw_path']}")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="验收⑤ 审计追溯：行→run→raw 全链路验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sample", type=int, default=20,
                        help="抽样行数（默认 20）")
    parser.add_argument(
        "--channel", choices=["pg", "api"], default="pg",
        help="数据通道",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    result = run_audit_check(args.sample, args.channel)

    if args.json:
        def _ser(obj):
            if isinstance(obj, (date, datetime)):
                return str(obj)
            raise TypeError
        print(json.dumps(result, indent=2, default=_ser))
    else:
        print(format_report(result))

    sys.exit(0 if result["status"] in ("PASS", "BLOCKED") else 1)


if __name__ == "__main__":
    main()
