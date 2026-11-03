#!/usr/bin/env python3
"""
index_daily pct 回填 (B1 修复)
走同一代码路径（j_index_daily._fetch_* + _write_to_db），禁止手工 SQL UPDATE。

逻辑：
1. 查询 index_daily WHERE pct IS NULL 的日期列表
2. 用 tencent/eastmoney 源取 10 天数据（含前收），计算 pct
3. 只回填 pct IS NULL 的那些行（ON CONFLICT UPDATE pct）
4. 首日无前收确实算不出的，如实保持 NULL 并在报告写明

验收：SELECT count(*) FROM index_daily WHERE pct IS NULL = 0
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

import psycopg2
import yaml

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dworker.jobs.j_index_daily import (
    _fetch_tencent, _fetch_eastmoney, _fetch_akshare, _write_to_db, INDEX_CODES
)

LOG_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "backfill_index_daily_pct.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backfill_index_daily_pct")

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"


def get_conn():
    with open(SECRETS_PATH) as f:
        s = yaml.safe_load(f)
    pw = s["database"]["duser_admin_password"]
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="postgres", password=pw,
    )


def get_null_dates(conn) -> list:
    """获取 pct IS NULL 的日期列表（返回字符串格式）。"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT date FROM index_daily
            WHERE pct IS NULL
            ORDER BY date
        """)
        # 统一转为字符串，避免 str vs date 类型不匹配
        return [str(r[0]) for r in cur.fetchall()]


def fetch_with_pct(source_name: str) -> list:
    """从指定源获取数据（含 pct）。"""
    if source_name == "tencent":
        return _fetch_tencent()
    elif source_name == "eastmoney":
        return _fetch_eastmoney()
    elif source_name == "akshare":
        return _fetch_akshare()
    return []


def fetch_full_history_akshare(target_dates: set) -> list:
    """从 akshare 取全量历史数据，计算 pct，仅返回覆盖 target_dates 的行。
    用于处理 tencent 10 天窗口覆盖不到的老日期（如 2025-06-12）。
    """
    import akshare as ak
    from dworker.jobs.j_index_daily import INDEX_CODES

    code_map = {
        "sh000001": "000001", "sz399001": "399001", "sz399006": "399006",
        "sh000300": "000300", "sh000016": "000016", "sh000688": "000688",
    }
    rows = []
    for code, name in INDEX_CODES:
        try:
            idx = code_map.get(code, code[2:])
            symbol = f"sh{idx}" if code.startswith("sh") else f"sz{idx}"
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                continue
            # 计算全量 pct
            df = df.sort_values("date")
            df["prev_close"] = df["close"].shift(1)
            df["pct"] = df.apply(
                lambda r: round((r["close"] - r["prev_close"]) / r["prev_close"] * 100, 4)
                if r["prev_close"] and r["prev_close"] > 0 else None, axis=1
            )
            for _, row in df.iterrows():
                d = str(row.get("date", ""))[:10]
                if d in target_dates:
                    rows.append({
                        "date": d, "code": code, "name": name,
                        "open": float(row.get("open", 0)),
                        "close": float(row.get("close", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "volume": float(row.get("volume", 0)),
                        "amount": 0,
                        "pct": row["pct"],
                    })
        except Exception as e:
            logger.warning(f"akshare full history failed for {code}: {e}")
    return rows


def backfill(conn, dry_run: bool = False):
    """回填 pct。"""
    null_dates = get_null_dates(conn)
    if not null_dates:
        logger.info("✅ 没有 pct IS NULL 的行，无需回填")
        return

    logger.info(f"需要回填的日期: {[str(d) for d in null_dates]}")
    logger.info(f"共 {len(null_dates)} 个日期")

    # 尝试多个源，取能覆盖最多日期的
    all_rows = []
    source_used = None
    for src in ["tencent", "eastmoney", "akshare"]:
        try:
            rows = fetch_with_pct(src)
            if rows:
                # 过滤出有 pct 的行
                rows_with_pct = [r for r in rows if r.get("pct") is not None]
                logger.info(f"  {src}: {len(rows)} rows, {len(rows_with_pct)} with pct")
                if len(rows_with_pct) > len(all_rows):
                    all_rows = rows
                    source_used = src
        except Exception as e:
            logger.warning(f"  {src} failed: {e}")

    if not all_rows:
        logger.error("所有源都无法获取数据")
        return

    null_date_set = set(null_dates)

    # 检查哪些日期还没被覆盖
    covered_dates = set(r.get("date") for r in all_rows if r.get("pct") is not None) & null_date_set
    uncovered = null_date_set - covered_dates
    if uncovered:
        logger.info(f"10天窗口未覆盖的日期: {[str(d) for d in uncovered]}，用 akshare 全量历史补充")
        try:
            extra_rows = fetch_full_history_akshare(null_date_set)
            if extra_rows:
                # 合并（去重：同 date+code 以 extra 覆盖）
                existing_keys = {(r["date"], r["code"]) for r in all_rows}
                for er in extra_rows:
                    key = (er["date"], er["code"])
                    if key not in existing_keys:
                        all_rows.append(er)
                        existing_keys.add(key)
                    elif er.get("pct") is not None:
                        # 更新已有行的 pct
                        for i, r in enumerate(all_rows):
                            if (r["date"], r["code"]) == key:
                                all_rows[i]["pct"] = er["pct"]
                                break
                logger.info(f"  akshare 全量补充: {len(extra_rows)} 行")
        except Exception as e:
            logger.warning(f"  akshare 全量补充失败: {e}")

    target_rows = [r for r in all_rows if r.get("date") in null_date_set and r.get("pct") is not None]

    logger.info(f"使用源: {source_used}")
    logger.info(f"将回填 {len(target_rows)} 行（{len(null_dates)} 日期 × 最多 {len(INDEX_CODES)} 指数）")

    # 列出无法回填的行（pct 仍为 None）
    cannot_fill = [r for r in all_rows if r.get("date") in null_date_set and r.get("pct") is None]
    if cannot_fill:
        logger.warning(f"⚠️ {len(cannot_fill)} 行无法计算 pct（首日无前收）:")
        for r in cannot_fill:
            logger.warning(f"   {r.get('date')} {r.get('code')} close={r.get('close')}")

    if dry_run:
        logger.info("DRY RUN - 不写库")
        for r in target_rows:
            logger.info(f"  {r['date']} {r['code']} pct={r['pct']}")
        return

    # 写库（走同一 _write_to_db）
    written = _write_to_db(conn, target_rows, source_used)
    logger.info(f"✅ 回填完成: {written} 行")

    # 验证
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM index_daily WHERE pct IS NULL")
        remaining = cur.fetchone()[0]
    logger.info(f"验证: pct IS NULL 剩余 {remaining} 行")

    if remaining > 0:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, code, close, source FROM index_daily
                WHERE pct IS NULL ORDER BY date, code
            """)
            for r in cur.fetchall():
                logger.warning(f"  仍未填: {r[0]} {r[1]} close={r[2]} src={r[3]}")


def main():
    dry_run = "--dry-run" in sys.argv
    logger.info("=" * 60)
    logger.info(f"index_daily pct 回填 (B1) {'[DRY RUN]' if dry_run else ''}")
    logger.info(f"  PID: {os.getpid()}")
    logger.info("=" * 60)

    conn = get_conn()
    conn.autocommit = True
    try:
        backfill(conn, dry_run=dry_run)
    finally:
        conn.close()
    logger.info("完成")


if __name__ == "__main__":
    main()
