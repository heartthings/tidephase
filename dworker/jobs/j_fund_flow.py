"""
j_fund_flow - 个股与板块资金流
目标表：fund_flow_stock, fund_flow_sector

东财 push2 从本机被断开。改用新浪 MoneyFlow：
  个股 ssl_bkzj_ssggzj：r0=超大单净额，r3=小单净额。大单/中单/主力这个接口没有，对应列留 NULL。
  板块 ssl_bkzj_bk：netamount 写入 main_net_inflow，source=sina。
  板块代码是新浪分类（gn_* / new_*），和 sector_daily 的 801xxx 不是同一套，按名称对照，不要按代码 join。

报价无交易日字段。用个股涨跌幅对 stock_daily 最近交易日做抽样核对，对不上就整批不写。
params['date'] 仅当它等于核对出来的交易日才允许写入。
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
PAGE = 100
MAX_PAGES = 80


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    t0 = time.time()
    requested = (job_ctx.params or {}).get("date")
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    trade_date = requested or today

    gate = check_trade_gate(conn, market="SSE", check_date=trade_date)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run(
                "j_fund_flow", "D4", "fund_flow_stock", "none", "SKIP",
                note=note, trigger=trigger,
            )
        except Exception as e:
            logger.warning(f"[j_fund_flow] ingest SKIP failed: {e}")
        return {
            "success": True, "source_used": "none", "already_logged": True,
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
        }

    stocks = _fetch_stock_pages()
    sectors = _fetch_sector_pages()
    if not stocks and not sectors:
        return {
            "success": False, "source_used": "sina",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0,
            "note": "MISS: sina MoneyFlow empty",
        }

    aligned, sample_note = _aligned_trade_date(conn, stocks)
    if requested:
        # 补采必须对得上 stock_daily，禁止把另一天的快照写进指定日期
        if aligned != requested:
            return {
                "success": False, "source_used": "sina",
                "rows_in": len(stocks), "rows_written": 0, "rows_quarantined": 0,
                "note": f"MISS: sina snapshot dates {aligned}, refused to write as {requested} ({sample_note})",
            }
        trade_date = requested
    else:
        # 定时在 15:20，当天 stock_daily 要 15:30 才落库，不能靠对账决定日期。
        # 日历门禁已确认今天开市，快照就记今天。
        trade_date = today
        sample_note = f"live session {today}; align_check={sample_note}"

    try:
        raw_archiver.archive("D4", "j_fund_flow", "sina", {
            "stocks": stocks[:20], "sectors": sectors[:10], "aligned": trade_date,
        })
    except Exception as e:
        logger.warning(f"[j_fund_flow] archive failed: {e}")

    n_stock = _write_stocks(conn, stocks, trade_date)
    n_sector = _write_sectors(conn, sectors, trade_date)
    note = (
        f"date={trade_date} source=sina stocks={n_stock} sectors={n_sector} "
        f"align={sample_note} "
        f"stock.main/large/medium NULL (sina only has r0 super-large and r3 small) "
        f"sector codes are sina category ids, not 801xxx "
        f"elapsed={time.time()-t0:.1f}s"
    )
    logger.info(f"[j_fund_flow] {note}")
    return {
        "success": (n_stock + n_sector) > 0, "source_used": "sina",
        "rows_in": len(stocks) + len(sectors),
        "rows_written": n_stock + n_sector, "rows_quarantined": 0, "note": note,
    }


def _get_json(url: str):
    resp = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://vip.stock.finance.sina.com.cn/",
    }, timeout=25)
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace").strip()
    if not text or text == "null":
        return []
    import json
    data = json.loads(text)
    return data if isinstance(data, list) else []


def _fetch_stock_pages() -> list:
    rows = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"MoneyFlow.ssl_bkzj_ssggzj?page={page}&num={PAGE}&sort=netamount&asc=0"
        )
        try:
            batch = _get_json(url)
        except Exception as e:
            logger.warning(f"[j_fund_flow] stock page {page}: {e}")
            break
        if not batch:
            break
        for item in batch:
            sym = str(item.get("symbol") or "")
            if sym.startswith(("sh6", "sz0", "sz3")):
                rows.append(item)
        if len(batch) < PAGE:
            break
        time.sleep(0.15)
    return rows


def _fetch_sector_pages() -> list:
    rows = []
    for fenlei, kind in (("1", "concept"), ("0", "industry")):
        page = 1
        while page <= 30:
            url = (
                "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                f"MoneyFlow.ssl_bkzj_bk?page={page}&num={PAGE}&sort=netamount&asc=0&fenlei={fenlei}"
            )
            try:
                batch = _get_json(url)
            except Exception as e:
                logger.warning(f"[j_fund_flow] sector fenlei={fenlei} page {page}: {e}")
                break
            if not batch:
                break
            for item in batch:
                item["_kind"] = kind
                rows.append(item)
            if len(batch) < PAGE:
                break
            page += 1
            time.sleep(0.15)
    return rows


def _aligned_trade_date(conn, stocks: list):
    """用 8 只样本的涨跌幅对 stock_daily，找出快照属于哪一个交易日。"""
    samples = []
    for item in stocks:
        pct = _pct(item.get("changeratio"))
        if pct is None:
            continue
        samples.append((item["symbol"], pct))
        if len(samples) >= 8:
            break
    if len(samples) < 3:
        return None, "fewer than 3 samples"
    codes = [s[0] for s in samples]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT date::text, code, pct
            FROM stock_daily
            WHERE code = ANY(%s) AND date >= CURRENT_DATE - 10
        """, (codes,))
        known = {}
        for d, code, pct in cur.fetchall():
            known.setdefault(d, {})[code] = pct
    best_date, best_hits = None, -1
    for d, mp in known.items():
        hits = 0
        for code, pct in samples:
            ref = mp.get(code)
            if ref is None or pct is None:
                continue
            if abs(float(ref) - pct) <= 0.35:
                hits += 1
        if hits > best_hits:
            best_date, best_hits = d, hits
    if best_hits < 3:
        return None, f"best_hits={best_hits}"
    return best_date, f"{best_date} hits={best_hits}/{len(samples)}"


def _write_stocks(conn, rows: list, trade_date: str) -> int:
    written = 0
    with conn.cursor() as cur:
        for item in rows:
            cur.execute("""
                INSERT INTO fund_flow_stock (
                    date, code, name, close, pct,
                    main_net_inflow, main_net_pct,
                    super_large_net, large_net, medium_net, small_net, source
                ) VALUES (%s,%s,%s,%s,%s, NULL, NULL, %s, NULL, NULL, %s, 'sina')
                ON CONFLICT (date, code) DO UPDATE SET
                    name=EXCLUDED.name, close=EXCLUDED.close, pct=EXCLUDED.pct,
                    super_large_net=EXCLUDED.super_large_net,
                    small_net=EXCLUDED.small_net,
                    source=EXCLUDED.source, ingest_ts=now()
            """, (
                trade_date, item["symbol"], item.get("name"),
                _num(item.get("trade")), _pct(item.get("changeratio")),
                _num(item.get("r0_net")), _num(item.get("r3_net")),
            ))
            written += 1
    conn.commit()
    return written


def _write_sectors(conn, rows: list, trade_date: str) -> int:
    written = 0
    with conn.cursor() as cur:
        for item in rows:
            code = item.get("category")
            if not code:
                continue
            cur.execute("""
                INSERT INTO fund_flow_sector (
                    date, sector_code, sector_name, kind, pct, main_net_inflow,
                    lead_stock_code, lead_stock_name, source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'sina')
                ON CONFLICT (date, sector_code) DO UPDATE SET
                    sector_name=EXCLUDED.sector_name, kind=EXCLUDED.kind,
                    pct=EXCLUDED.pct, main_net_inflow=EXCLUDED.main_net_inflow,
                    lead_stock_code=EXCLUDED.lead_stock_code,
                    lead_stock_name=EXCLUDED.lead_stock_name,
                    source=EXCLUDED.source, ingest_ts=now()
            """, (
                trade_date, code, item.get("name"), item.get("_kind") or "concept",
                _pct(item.get("avg_changeratio")), _num(item.get("netamount")),
                item.get("ts_symbol"), item.get("ts_name"),
            ))
            written += 1
    conn.commit()
    return written


def _num(v):
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def _pct(v):
    """新浪 changeratio 是小数（0.09=9%）。库内 pct 用百分数点。"""
    n = _num(v)
    if n is None:
        return None
    return round(n * 100, 4)
