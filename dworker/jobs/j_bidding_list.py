"""
j_bidding_list - 竞价列表（五维原料）
目标表：bidding_list
Q11 冻结 9 字段子集：jjzf, jjje, jjcje, jjhs, ztwme, twenty_ztwme, fd, zdfd, sjlt
源链：tencent → eastmoney（备）
quotations_type: 1=09:15, 2=09:20, 3=09:25, 9=09:26终版

整改记录（2026-10-09 督军 FAIL 整改单）：
- 根因：eastmoney push2 从本机 RemoteDisconnected；mootdx TDX 服务器全部超时/空返回
- 修复：tencent qt 为主源（已验证可用，88字段），eastmoney 降为备源
- 字段映射：基于 tencent qt 实际返回字段重新映射
- 无法计算字段：twenty_ztwme/zdfd → NULL + note 声明，禁止硬编码0充数
"""
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 重试配置 ──
RETRY_BACKOFF_S = [2, 5, 10]  # 督军整改项#3：间歇容错退避


def _quotations_type(hour_min: int):
    """竞价快照类型。09:36 之后返回 None，避免把盘中行情写成 09:26 终版。"""
    if hour_min <= 915:
        return 1
    if hour_min <= 920:
        return 2
    if hour_min <= 925:
        return 3
    if hour_min <= 935:
        return 9
    return None


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_bidding_list."""
    from dworker.core.calendar_gate import check_trade_gate

    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_bidding_list] {note}")
        try:
            ingest_logger.log_run(
                "j_bidding_list", "D3", "bidding_list", "none", "SKIP",
                note=note, trigger=trigger,
            )
        except Exception as e:
            logger.warning(f"[j_bidding_list] ingest SKIP failed: {e}")
        return {
            "success": True, "source_used": "none", "already_logged": True,
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": note,
        }

    # 1=09:15  2=09:20  3=09:25  9=09:26 终版。
    # 腾讯 qt 只在竞价时段返回竞价额。过了 09:35 再跑会把盘中成交写成终版，直接跳过。
    hour_min = now.hour * 100 + now.minute
    quotations_type = _quotations_type(hour_min)
    if quotations_type is None:
        note = f"SKIP: auction window closed at {now.strftime('%H:%M')}, refuse live quotes as type=9"
        logger.info(f"[j_bidding_list] {note}")
        return {
            "success": True, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": note,
        }

    all_rows = []
    source_used = None
    tencent_codes = _load_tencent_codes(conn)

    for source_name in source_chain:
        try:
            rows = _fetch_from_source_with_retry(
                source_name, today, quotations_type, tencent_codes
            )
            if rows:
                all_rows = rows
                source_used = source_name
                logger.info(f"[j_bidding_list] Got {len(rows)} rows from {source_name}")
                break
        except Exception as e:
            logger.warning(f"[j_bidding_list] Source {source_name} exhausted retries: {e}")
            continue

    if not all_rows:
        return {
            "success": False, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": f"all sources failed type={quotations_type}"
        }

    # Archive raw
    try:
        raw_archiver.archive("D3", "j_bidding_list", source_used, all_rows)
    except Exception as e:
        logger.warning(f"[j_bidding_list] Archive failed: {e}")

    # Write to DB
    rows_written = _write_to_db(conn, all_rows, source_used, today, quotations_type)

    return {
        "success": rows_written > 0,
        "source_used": source_used,
        "rows_in": len(all_rows),
        "rows_written": rows_written,
        "rows_quarantined": 0,
        "note": f"date={today} type={quotations_type} count={len(all_rows)}"
    }


def _fetch_from_source_with_retry(source_name: str, today: str, quotations_type: int,
                                   tencent_codes: list = None) -> list:
    """带重试的数据获取（整改项#3：间歇容错）"""
    last_err = None
    for attempt, backoff in enumerate(RETRY_BACKOFF_S):
        try:
            rows = _fetch_from_source(source_name, today, quotations_type, tencent_codes)
            if rows:
                return rows
            # 空结果不算失败，但记录
            logger.info(f"[j_bidding_list] {source_name} attempt {attempt+1}: empty result")
            return []
        except Exception as e:
            last_err = e
            logger.warning(f"[j_bidding_list] {source_name} attempt {attempt+1} failed: {e}")
            if attempt < len(RETRY_BACKOFF_S) - 1:
                time.sleep(backoff)
    raise last_err


def _load_tencent_codes(conn) -> list:
    """用证券主档的真实代码，不再扫 600000-605999 这种空号段。"""
    codes = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM instrument_master WHERE code ~ '^[0-9]{6}$'")
            for (raw,) in cur.fetchall():
                if raw.startswith("6"):
                    codes.append(f"sh{raw}")
                elif raw.startswith(("0", "3")):
                    codes.append(f"sz{raw}")
                elif raw.startswith(("4", "8")):
                    codes.append(f"bj{raw}")
    except Exception as e:
        logger.warning(f"[j_bidding_list] instrument_master lookup failed: {e}")
    return codes


def _fetch_from_source(source_name: str, today: str, quotations_type: int,
                       tencent_codes: list = None) -> list:
    if source_name == "tencent":
        return _fetch_tencent_bidding(today, quotations_type, tencent_codes or [])
    elif source_name == "eastmoney":
        return _fetch_eastmoney_bidding(today)
    return []


# ═══════════════════════════════════════════════════════════════════
# 主源：tencent qt（整改后新增）
# ═══════════════════════════════════════════════════════════════════

def _fetch_tencent_bidding(today: str, quotations_type: int, all_codes: list = None) -> list:
    """
    从 tencent qt API 获取全市场实时数据。
    竞价期间（09:15-09:25），返回的即为竞价数据。

    tencent qt 字段映射（基于 88 字段结构）：
    - [1] name, [2] code, [3] current_price, [4] last_close, [5] open
    - [6] volume(手), [37] amount(万元), [38] turnover_rate(%)
    - [44] circulating_market_cap(亿), [45] total_market_cap(亿)
      （验证：万科A [44]=383.75≈流通, [45]=471.26≈总股本×价格）

    Q11 九字段映射：
    - jjzf = [32] 涨跌幅%（竞价期间即竞价涨幅）
    - jjje = [37] * 10000 成交额(元)（竞价期间即竞价金额）
    - jjcje = [37] * 10000 竞价成交额(元)（竞价期间与 jjje 相同）
    - jjhs = [38] 换手率%（竞价期间即竞价换手）
    - ztwme = [45] * 1e8 总市值(元)（当前，非昨日；标注 note）
    - twenty_ztwme = NULL（需20日前历史数据，实时API无法计算）
    - fd = NULL（放量=当日成交量/近5日均量，需历史数据）
    - zdfd = NULL（涨跌放量定义不明确，禁止硬编码）
    - sjlt = [44] * 1e8 流通市值(元)（实时）
    """
    import requests

    rows = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    # 分步获取全市场：先获取代码列表，再批量查询
    # tencent qt 支持批量查询，每批最多 ~80 只
    # 策略：用东财 API 获取代码列表（如果可用），否则用已知代码范围

    if not all_codes:
        all_codes = _generate_all_stock_codes()
    batch_size = 80

    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i + batch_size]
        codes_str = ",".join(batch)
        try:
            resp = session.get(
                f"https://qt.gtimg.cn/q={codes_str}",
                timeout=30
            )
            if resp.status_code != 200:
                continue

            text = resp.text.strip()
            if not text:
                continue

            # 解析 tencent qt 响应（v_sz000001="...~...~..."; 格式）
            entries = text.split(";")
            for entry in entries:
                entry = entry.strip()
                if not entry or "=" not in entry:
                    continue
                try:
                    json_str = entry.split("=", 1)[1].strip().strip('"')
                    fields = json_str.split("~")
                    if len(fields) < 46:
                        continue

                    code_raw = fields[2]
                    name = fields[1]
                    price = _safe_float(fields[3])
                    last_close = _safe_float(fields[4])

                    if price <= 0 or last_close <= 0:
                        continue

                    # 标准化代码
                    market_id = fields[0]  # 51=SZ, 1=SH
                    if market_id == "1":
                        code = f"sh{code_raw}"
                    elif market_id == "51":
                        code = f"sz{code_raw}"
                    else:
                        continue

                    # Q11 九字段映射
                    jjzf = _safe_float(fields[32])  # 涨跌幅%
                    jjje = int(_safe_float(fields[37]) * 10000)  # 成交额：万→元
                    jjcje = jjje  # 竞价期间成交额=竞价成交额
                    jjhs = _safe_float(fields[38])  # 换手率%
                    ztwme_raw = _safe_float(fields[45])  # 总市值(亿) [45]=total
                    ztwme = int(ztwme_raw * 1e8) if ztwme_raw > 0 else None
                    sjlt_raw = _safe_float(fields[44])  # 流通市值(亿) [44]=circ
                    sjlt = int(sjlt_raw * 1e8) if sjlt_raw > 0 else None

                    rows.append({
                        "date": today,
                        "code": code,
                        "name": name,
                        "jjzf": round(jjzf, 2),
                        "jjje": jjje,
                        "jjcje": jjcje,
                        "jjhs": round(jjhs, 2),
                        "ztwme": ztwme,
                        "twenty_ztwme": None,  # 无法计算：需20日前总市值历史数据
                        "fd": None,  # 无法计算：需近5日平均成交量
                        "zdfd": None,  # 无法计算：定义不明确
                        "sjlt": sjlt,
                        "ssbk": "",
                        "ztsj": "",
                        "ztyy": "",
                        "bkztsl": 0,
                        "limit_up_status": "",
                        "quotations_type": quotations_type,
                        "_field_notes": {
                            "ztwme": "当前总市值(非昨日)，tencent[45]=总市值亿",
                            "twenty_ztwme": "需20日前历史总市值，实时API无法计算",
                            "fd": "需近5日均量对比，实时API无法计算",
                            "zdfd": "涨跌放量定义不明确，禁止硬编码0充数",
                        }
                    })
                except (IndexError, ValueError) as e:
                    logger.debug(f"Parse tencent entry failed: {e}")
                    continue

        except Exception as e:
            logger.warning(f"tencent batch {i} failed: {e}")
            continue

    logger.info(f"tencent bidding: got {len(rows)} rows")
    return rows


def _generate_all_stock_codes() -> list:
    """
    生成全市场 A 股代码列表（tencent qt 格式）。
    覆盖：沪市主板(60xxxx) + 科创板(688xxx) + 深市主板(00xxxx) + 创业板(30xxxx) + 北交所(8xxxxx/4xxxxx)
    """
    codes = []
    # 沪市主板 600000-605999
    for i in range(600000, 606000):
        codes.append(f"sh{i}")
    # 科创板 688000-689999
    for i in range(688000, 690000):
        codes.append(f"sh{i}")
    # 深市主板 000001-004999
    for i in range(1, 5000):
        codes.append(f"sz{i:06d}")
    # 创业板 300000-302999
    for i in range(300000, 303000):
        codes.append(f"sz{i}")
    # 北交所 8xxxxx, 4xxxxx (较少，可选)
    # 暂不覆盖北交所，减少无效请求

    return codes


# ═══════════════════════════════════════════════════════════════════
# 备源：eastmoney（整改后保留，但降为第二位）
# ═══════════════════════════════════════════════════════════════════

def _fetch_eastmoney_bidding(today: str) -> list:
    """
    从 eastmoney push2 API 获取。
    注意：从本机经常 RemoteDisconnected，仅作备源。

    字段映射修正（整改项#2）：
    - f3 = 涨跌幅% → jjzf ✓
    - f6 = 成交额(元) → jjje（竞价期间可能为0→NULL）
    - f5 = 成交量(手) → jjhs 的分子（竞价期间通常0→NULL）
    - f20 = 总市值 → ztwme（修正：原错误映射为 jjcje）
    - f21 = 流通市值 → sjlt（修正：原错误映射为 ztwme）
    - f8 = 换手率% → 竞价期间通常为0→NULL
    """
    import requests
    rows = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/"
    })

    try:
        resp = session.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 5000, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            for item in items:
                code_raw = str(item.get("f12", ""))
                code = _to_standard_code(code_raw)
                close = _safe_float(item.get("f2"))
                if close <= 0:
                    continue

                # 修正后的字段映射
                f5_vol = _safe_float(item.get("f5"))  # 成交量(手)
                f6_amount = _safe_float(item.get("f6"))  # 成交额(元)
                f8_turnover = _safe_float(item.get("f8"))  # 换手率%
                f20_total_cap = _safe_float(item.get("f20"))  # 总市值
                f21_circ_cap = _safe_float(item.get("f21"))  # 流通市值

                rows.append({
                    "date": today,
                    "code": code,
                    "name": str(item.get("f14", "")),
                    "jjzf": _safe_float(item.get("f3")),  # 涨跌幅%
                    "jjje": int(f6_amount) if f6_amount > 0 else None,  # 成交额，0则NULL
                    "jjcje": int(f6_amount) if f6_amount > 0 else None,  # 竞价期间=成交额
                    "jjhs": f8_turnover if f8_turnover > 0 else None,  # 换手率，0则NULL
                    "ztwme": int(f20_total_cap) if f20_total_cap > 0 else None,  # f20=总市值
                    "twenty_ztwme": None,  # 无法计算
                    "fd": None,  # 无法计算
                    "zdfd": None,  # 无法计算
                    "sjlt": int(f21_circ_cap) if f21_circ_cap > 0 else None,  # f21=流通市值
                    "ssbk": "",
                    "ztsj": "",
                    "ztyy": "",
                    "bkztsl": 0,
                    "limit_up_status": "",
                    "quotations_type": 1,
                    "_field_notes": {
                        "twenty_ztwme": "需20日前历史总市值",
                        "fd": "需近5日均量对比",
                        "zdfd": "定义不明确",
                    }
                })
    except Exception as e:
        logger.warning(f"eastmoney bidding fetch failed: {e}")

    return rows


def _to_standard_code(raw_code: str) -> str:
    raw_code = raw_code.strip()
    if len(raw_code) == 6 and raw_code.isdigit():
        if raw_code.startswith("6"):
            return f"sh{raw_code}"
        elif raw_code.startswith(("0", "3")):
            return f"sz{raw_code}"
        elif raw_code.startswith(("4", "8")):
            return f"bj{raw_code}"
    return raw_code


def _safe_float(val) -> float:
    if val is None or val == "-" or val == "":
        return 0.0
    try:
        v = float(val)
        return v if v == v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _write_to_db(conn, rows: list, source: str, today: str, quotations_type: int) -> int:
    """Write to bidding_list. Returns count written."""
    if not rows:
        return 0

    count = 0
    with conn.cursor() as cur:
        for row in rows:
            try:
                cur.execute("""
                    INSERT INTO bidding_list
                        (date, code, name, jjzf, jjje, jjcje, jjhs,
                         ztwme, twenty_ztwme, fd, zdfd, sjlt,
                         ssbk, ztsj, ztyy, bkztsl, limit_up_status,
                         quotations_type, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (date, code, quotations_type) DO UPDATE SET
                        name = EXCLUDED.name,
                        jjzf = EXCLUDED.jjzf, jjje = EXCLUDED.jjje,
                        jjcje = EXCLUDED.jjcje, jjhs = EXCLUDED.jjhs,
                        ztwme = EXCLUDED.ztwme, twenty_ztwme = EXCLUDED.twenty_ztwme,
                        fd = EXCLUDED.fd, zdfd = EXCLUDED.zdfd,
                        sjlt = EXCLUDED.sjlt,
                        ssbk = EXCLUDED.ssbk, ztsj = EXCLUDED.ztsj,
                        ztyy = EXCLUDED.ztyy, bkztsl = EXCLUDED.bkztsl,
                        limit_up_status = EXCLUDED.limit_up_status,
                        source = EXCLUDED.source,
                        ingest_ts = now()
                """, (
                    row["date"], row["code"], row.get("name"),
                    row.get("jjzf", 0), row.get("jjje"),
                    row.get("jjcje"), row.get("jjhs"),
                    row.get("ztwme"), row.get("twenty_ztwme"),
                    row.get("fd"), row.get("zdfd"),
                    row.get("sjlt"), row.get("ssbk", ""),
                    row.get("ztsj", ""), row.get("ztyy", ""),
                    row.get("bkztsl", 0), row.get("limit_up_status", ""),
                    quotations_type, source,
                ))
                count += 1
            except Exception as e:
                logger.debug(f"Write bidding_list failed for {row.get('code')}: {e}")
        conn.commit()
    return count
