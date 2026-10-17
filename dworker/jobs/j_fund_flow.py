"""
j_fund_flow - 个股与板块资金流
目标表：fund_flow_stock, fund_flow_sector

个股报价、名称仍用新浪 MoneyFlow。五档净额用东财，同一套口径：
  主力净流入 = 超大单 + 大单，主力净占比是占成交额的百分数。
  新浪列表只有超大单和小单，留着会和东财的大单、中单对不上，所以五档一起写。
  东财列表失败时，用新浪个股明细 r0/r1/r2/r3 补，明细同样五档一起写。
板块 ssl_bkzj_bk：netamount 写入 main_net_inflow，ratioamount 写入 main_net_pct。
  板块代码是新浪分类（gn_* / new_*），和 sector_daily 的 801xxx 不是同一套，按名称对照，不要按代码 join。

报价无交易日字段。用个股涨跌幅对 stock_daily 最近交易日做抽样核对，对不上就整批不写。
params['date'] 仅当它等于核对出来的交易日才允许写入。
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from psycopg2.extras import execute_values

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))
PAGE = 100
MAX_PAGES = 80
EM_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
EM_FIELDS = "f12,f13,f14,f62,f184,f66,f72,f78,f84"
EM_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


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
    n_bucket, bucket_source = _fill_buckets(conn, trade_date)
    missing = _missing_main(conn, trade_date)
    note = (
        f"date={trade_date} source={bucket_source} stocks={n_stock} sectors={n_sector} "
        f"buckets={n_bucket} main_missing={missing} align={sample_note} "
        f"five nets are one caliber; sector codes are sina category ids, not 801xxx "
        f"elapsed={time.time()-t0:.1f}s"
    )
    logger.info(f"[j_fund_flow] {note}")
    filled = n_stock == 0 or missing <= max(400, int(n_stock * 0.08))
    return {
        "success": (n_stock + n_sector) > 0 and filled, "source_used": bucket_source,
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
                    date, sector_code, sector_name, kind, pct, main_net_inflow, main_net_pct,
                    lead_stock_code, lead_stock_name, source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'sina')
                ON CONFLICT (date, sector_code) DO UPDATE SET
                    sector_name=EXCLUDED.sector_name, kind=EXCLUDED.kind,
                    pct=EXCLUDED.pct, main_net_inflow=EXCLUDED.main_net_inflow,
                    main_net_pct=EXCLUDED.main_net_pct,
                    lead_stock_code=EXCLUDED.lead_stock_code,
                    lead_stock_name=EXCLUDED.lead_stock_name,
                    source=EXCLUDED.source, ingest_ts=now()
            """, (
                trade_date, code, item.get("name"), item.get("_kind") or "concept",
                _pct(item.get("avg_changeratio")), _num(item.get("netamount")),
                _pct(item.get("ratioamount")),
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
    """新浪 changeratio、ratioamount 是小数（0.09=9%）。库内用百分数点。"""
    n = _num(v)
    if n is None:
        return None
    return round(n * 100, 4)


def _fill_buckets(conn, trade_date: str):
    """补主力、主力净占比、大单、中单，并把超大单、小单改成同一套。"""
    rows = _fetch_eastmoney_clist()
    source = "sina"
    if len(rows) >= 4000:
        _update_buckets(conn, trade_date, rows, "sina+eastmoney")
        source = "sina+eastmoney"
    else:
        logger.warning(f"[j_fund_flow] eastmoney clist only {len(rows)}, use sina detail")
    extra = _fill_from_sina_detail(conn, trade_date)
    return len(rows) + extra, source


def _fetch_eastmoney_clist() -> list:
    rows = []
    page = 1
    total = None
    while page <= 160:
        batch = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    "https://push2.eastmoney.com/api/qt/clist/get",
                    params={
                        "pn": page, "pz": PAGE, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                        "fid": "f12", "fs": EM_FS, "fields": EM_FIELDS,
                    },
                    headers=EM_HEADERS, timeout=20,
                )
                data = (resp.json().get("data") or {})
                total = data.get("total") if data.get("total") is not None else total
                diff = data.get("diff") or []
                if isinstance(diff, dict):
                    diff = list(diff.values())
                batch = diff
                break
            except Exception as e:
                logger.warning(f"[j_fund_flow] eastmoney page {page} try {attempt + 1}: {e}")
                time.sleep(1 + attempt)
        if batch is None:
            break
        if not batch:
            break
        for item in batch:
            code = _em_code(item.get("f12"), item.get("f13"))
            main = _num(item.get("f62"))
            if not code or main is None:
                continue
            rows.append((
                code, main, _num(item.get("f184")), _num(item.get("f66")),
                _num(item.get("f72")), _num(item.get("f78")), _num(item.get("f84")),
            ))
        if len(batch) < PAGE or (total and page * PAGE >= total):
            break
        page += 1
        time.sleep(0.05)
    return rows


def _em_code(num, market):
    num = str(num or "")
    if not num.isdigit():
        return None
    market = str(market)
    if market == "1" and num.startswith(("60", "68")):
        return "sh" + num
    if market == "0" and num.startswith(("00", "30")):
        return "sz" + num
    if market == "0" and num.startswith(("43", "83", "87", "92")):
        return "bj" + num
    return None


def _update_buckets(conn, trade_date: str, rows: list, source: str) -> None:
    if not rows:
        return
    payload = [
        (trade_date, code, main, main_pct, super, large, medium, small, source)
        for code, main, main_pct, super, large, medium, small in rows
    ]
    sql = """
        UPDATE fund_flow_stock AS f SET
            main_net_inflow = v.main,
            main_net_pct = v.main_pct,
            super_large_net = v.super,
            large_net = v.large,
            medium_net = v.medium,
            small_net = v.small,
            source = v.source,
            ingest_ts = now()
        FROM (VALUES %s) AS v(day, code, main, main_pct, super, large, medium, small, source)
        WHERE f.date = v.day::date AND f.code = v.code
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, payload,
            template="(%s,%s,%s::float8,%s::float8,%s::float8,%s::float8,%s::float8,%s::float8,%s)",
            page_size=2000,
        )
    conn.commit()


def _missing_main(conn, trade_date: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM fund_flow_stock WHERE date = %s AND main_net_inflow IS NULL",
            (trade_date,),
        )
        return cur.fetchone()[0]


def _fill_from_sina_detail(conn, trade_date: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT code FROM fund_flow_stock WHERE date = %s AND main_net_inflow IS NULL",
            (trade_date,),
        )
        codes = [r[0] for r in cur.fetchall()]
    if not codes:
        return 0
    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for code, nets in pool.map(_sina_detail, codes):
            if nets is None:
                continue
            rows.append((code, *nets))
    _update_buckets(conn, trade_date, rows, "sina")
    return len(rows)


def _sina_detail(code: str):
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"MoneyFlow.ssi_ssfx_flzjtj?daima={code}"
    )
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://vip.stock.finance.sina.com.cn/",
        }, timeout=20)
        item = resp.json()
        if not isinstance(item, dict):
            return code, None
    except Exception as e:
        logger.warning(f"[j_fund_flow] sina detail {code}: {e}")
        return code, None
    nets = []
    gross = 0.0
    for i in range(4):
        inn = _num(item.get(f"r{i}_in"))
        out = _num(item.get(f"r{i}_out"))
        bucket = _num(item.get(f"r{i}"))
        if inn is None or out is None or bucket is None:
            return code, None
        nets.append(inn - out)
        gross += bucket
    main = nets[0] + nets[1]
    main_pct = round(main / gross * 100, 4) if gross else None
    return code, (main, main_pct, nets[0], nets[1], nets[2], nets[3])


def backfill_buckets(conn, since: str = "2026-10-12") -> dict:
    """用东财日 K 把已有个股行的五档净额补上。只更新已有日期，不新开行。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT code FROM fund_flow_stock WHERE date >= %s ORDER BY code",
            (since,),
        )
        codes = [r[0] for r in cur.fetchall()]
    updated = 0
    empty = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, (rows, ok) in enumerate(pool.map(lambda c: _eastmoney_dayk(c, since), codes), start=1):
            if not ok:
                errors += 1
            elif not rows:
                empty += 1
            else:
                _update_bucket_days(conn, rows)
                updated += len(rows)
            if i % 250 == 0 or i == len(codes):
                print(
                    f"[j_fund_flow] backfill {i}/{len(codes)} "
                    f"rows={updated} empty={empty} errors={errors}",
                    flush=True,
                )
    return {"codes": len(codes), "rows": updated, "empty": empty, "errors": errors}


def _eastmoney_dayk(code: str, since: str):
    secid = ("1." if code.startswith("sh") else "0.") + code[2:]
    last = None
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                params={
                    "lmt": 12, "klt": 101, "secid": secid,
                    "fields1": "f1,f2,f3,f7",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
                },
                headers=EM_HEADERS, timeout=20,
            )
            klines = ((resp.json().get("data") or {}).get("klines")) or []
            rows = []
            for line in klines:
                parts = str(line).split(",")
                if len(parts) < 7 or parts[0] < since:
                    continue
                main = _num(parts[1])
                if main is None:
                    continue
                rows.append((
                    parts[0], code, main, _num(parts[6]), _num(parts[5]),
                    _num(parts[4]), _num(parts[3]), _num(parts[2]),
                ))
            return rows, True
        except Exception as e:
            last = e
            time.sleep(0.5 + attempt)
    logger.warning(f"[j_fund_flow] dayk {code}: {last}")
    return [], False


def _update_bucket_days(conn, rows: list) -> None:
    if not rows:
        return
    sql = """
        UPDATE fund_flow_stock AS f SET
            main_net_inflow = v.main,
            main_net_pct = v.main_pct,
            super_large_net = v.super,
            large_net = v.large,
            medium_net = v.medium,
            small_net = v.small,
            source = 'sina+eastmoney',
            ingest_ts = now()
        FROM (VALUES %s) AS v(day, code, main, main_pct, super, large, medium, small)
        WHERE f.date = v.day::date AND f.code = v.code
    """
    with conn.cursor() as cur:
        execute_values(
            cur, sql, rows,
            template="(%s,%s,%s::float8,%s::float8,%s::float8,%s::float8,%s::float8,%s::float8)",
            page_size=2000,
        )
    conn.commit()
