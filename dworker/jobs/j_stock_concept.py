"""个股所属题材与行业。

题材：龙虎 GetConceptJXBKw23，一只股票一条，CCode/CName 写入 stock_sector_map，kind=theme。
行业：优先东财所属行业；东财断开时用新浪行业分类。kind=industry。
每个交易日 08:20 全量刷新，题材接口 16 路并发。某只股票这次没取到，就不改它已经打开的记录。
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
WORKERS = 16
LONGHU_URL = "https://apparticle.longhuvip.com/w1/api/index.php"
EM_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
EM_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81"


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        try:
            ingest_logger.log_run(
                "j_stock_concept", "D6", "stock_sector_map", "none", "SKIP",
                note=note, trigger=trigger,
            )
        except Exception:
            pass
        return {
            "success": True, "already_logged": True, "source_used": "none",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note,
        }

    stats = sync(conn, today)
    note = (
        f"date={today} stocks={stats['stocks']} themes={stats['themes']} "
        f"theme_stocks={stats['theme_stocks']} industry={stats['industry']} "
        f"empty={stats['empty']} errors={stats['errors']} "
        f"opened={stats['opened']} closed={stats['closed']}"
    )
    logger.info(f"[j_stock_concept] {note}")
    covered = stats["theme_stocks"] >= int(stats["stocks"] * 0.8) if stats["stocks"] else False
    return {
        "success": covered and stats["errors"] < stats["stocks"],
        "source_used": "longhu+eastmoney",
        "rows_in": stats["themes"] + stats["industry"],
        "rows_written": stats["opened"],
        "rows_quarantined": 0,
        "note": note,
    }


def sync(conn, today: str) -> dict:
    codes = _load_codes(conn)
    industries = _fetch_industries()
    themes = {}
    empty = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, (code, items, ok) in enumerate(pool.map(_fetch_concepts, codes), start=1):
            if not ok:
                errors += 1
            elif not items:
                empty += 1
                themes[code] = []
            else:
                themes[code] = items
            if i % 300 == 0 or i == len(codes):
                print(
                    f"[j_stock_concept] {i}/{len(codes)} themes={sum(len(v) for v in themes.values())} "
                    f"empty={empty} errors={errors}",
                    flush=True,
                )
    opened, closed = _apply(conn, themes, industries, today)
    return {
        "stocks": len(codes),
        "themes": sum(len(v) for v in themes.values()),
        "theme_stocks": len(themes),
        "industry": sum(1 for code in codes if code in industries),
        "empty": empty,
        "errors": errors,
        "opened": opened,
        "closed": closed,
    }


def _load_codes(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code FROM instrument_master
            WHERE inst_type = 'stock' AND status = 'active'
            ORDER BY code
        """)
        return [_prefix(row[0]) for row in cur.fetchall()]


def _prefix(code: str) -> str:
    if code.startswith(("60", "68")):
        return "sh" + code
    if code.startswith(("43", "83", "87", "92")):
        return "bj" + code
    return "sz" + code


def _fetch_concepts(code: str):
    stock_id = code[2:]
    last = None
    for attempt in range(2):
        try:
            resp = requests.post(
                LONGHU_URL,
                data={
                    "a": "GetConceptJXBKw23",
                    "c": "StockF10Basic",
                    "PhoneOSNew": "1",
                    "DeviceID": "271a33c60fc2b3cc",
                    "VerSion": "5.21.0.0",
                    "apiv": "w42",
                    "StockID": stock_id,
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            payload = resp.json()
            if str(payload.get("errcode")) != "0":
                raise RuntimeError(f"errcode {payload.get('errcode')}")
            items = []
            seen = set()
            for item in payload.get("List") or []:
                sector_code = str(item.get("CCode") or "").strip()
                name = str(item.get("CName") or "").strip()
                if not sector_code or not name or sector_code in seen:
                    continue
                seen.add(sector_code)
                items.append((sector_code, name))
            return code, items, True
        except Exception as e:
            last = e
            time.sleep(0.6)
    logger.warning(f"[j_stock_concept] {code}: {last}")
    return code, [], False


def _fetch_industries() -> dict:
    """code -> (板块代码, 行业名)。东财够用就用东财，否则用新浪行业。"""
    found = _fetch_industries_eastmoney()
    if len(found) >= 3000:
        return found
    logger.warning(f"[j_stock_concept] eastmoney industry only {len(found)}, fallback sina")
    sina = _fetch_industries_sina()
    return sina if len(sina) > len(found) else found


def _fetch_industries_eastmoney() -> dict:
    """名称对上东财行业板块；对不上时用行业名本身当代码。"""
    names = _industry_boards()
    found = {}
    page = 1
    while page <= 80:
        diff = None
        data = {}
        for attempt in range(3):
            try:
                resp = requests.get(
                    "https://push2.eastmoney.com/api/qt/clist/get",
                    params={
                        "pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                        "fid": "f12", "fs": EM_FS, "fields": "f12,f13,f100",
                    },
                    headers=EM_HEADERS, timeout=20,
                )
                data = resp.json().get("data") or {}
                diff = data.get("diff") or []
                if isinstance(diff, dict):
                    diff = list(diff.values())
                break
            except Exception as e:
                logger.warning(f"[j_stock_concept] industry page {page} try {attempt + 1}: {e}")
                time.sleep(1 + attempt)
        if diff is None:
            break
        if not diff:
            break
        for item in diff:
            code = _em_code(item.get("f12"), item.get("f13"))
            name = str(item.get("f100") or "").strip()
            if not code or not name or name == "-":
                continue
            sector_code = names.get(name) or f"ind:{name}"
            found[code] = (sector_code, name)
        total = data.get("total") or 0
        if len(diff) < 100 or (total and page * 100 >= total):
            break
        page += 1
        time.sleep(0.05)
    return found


def _industry_boards() -> dict:
    names = {}
    page = 1
    while page <= 10:
        try:
            resp = requests.get(
                "https://push2.eastmoney.com/api/qt/clist/get",
                params={
                    "pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                    "fid": "f12", "fs": "m:90+t:2", "fields": "f12,f14",
                },
                headers=EM_HEADERS, timeout=20,
            )
            diff = (resp.json().get("data") or {}).get("diff") or []
            if isinstance(diff, dict):
                diff = list(diff.values())
        except Exception as e:
            logger.warning(f"[j_stock_concept] industry boards: {e}")
            break
        if not diff:
            break
        for item in diff:
            name = str(item.get("f14") or "").strip()
            code = str(item.get("f12") or "").strip()
            if name and code:
                names[name] = code
        if len(diff) < 100:
            break
        page += 1
    return names


def _fetch_industries_sina() -> dict:
    nodes = _sina_industry_nodes()
    found = {}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://vip.stock.finance.sina.com.cn/"}
    for name, node in nodes:
        page = 1
        while page <= 40:
            try:
                resp = requests.get(
                    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
                    params={"page": page, "num": 80, "sort": "symbol", "asc": 1, "node": node},
                    headers=headers, timeout=20,
                )
                batch = resp.json()
                if not isinstance(batch, list):
                    break
            except Exception as e:
                logger.warning(f"[j_stock_concept] sina industry {node} page {page}: {e}")
                break
            if not batch:
                break
            for item in batch:
                code = str(item.get("symbol") or "")
                if code.startswith(("sh", "sz", "bj")) and code not in found:
                    found[code] = (node, name)
            if len(batch) < 80:
                break
            page += 1
            time.sleep(0.05)
    return found


def _sina_industry_nodes() -> list:
    resp = requests.get(
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodes",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://vip.stock.finance.sina.com.cn/"},
        timeout=20,
    )
    branch = _find_named(resp.json(), "申万行业")
    nodes = []
    for item in branch or []:
        if isinstance(item, list) and len(item) >= 3 and item[0] and item[2]:
            nodes.append((str(item[0]), str(item[2])))
    return nodes


def _find_named(node, name):
    if isinstance(node, list) and node and node[0] == name:
        return node[1] if len(node) > 1 else []
    if isinstance(node, list):
        for child in node:
            found = _find_named(child, name)
            if found is not None:
                return found
    return None


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


def _apply(conn, themes: dict, industries: dict, today: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT code, sector_code, kind
            FROM stock_sector_map
            WHERE effective_to IS NULL AND kind IN ('theme', 'industry')
        """)
        open_rows = {(code, sector_code, kind) for code, sector_code, kind in cur.fetchall()}

    desired = []
    for code, items in themes.items():
        for sector_code, name in items:
            desired.append((code, sector_code, name, "theme", "longhu"))
    for code, (sector_code, name) in industries.items():
        desired.append((code, sector_code, name, "industry", "eastmoney"))

    desired_keys = {(code, sector_code, kind) for code, sector_code, _name, kind, _src in desired}
    refreshed_theme = set(themes)
    refreshed_industry = set(industries)
    closing = []
    for code, sector_code, kind in open_rows:
        if (code, sector_code, kind) in desired_keys:
            continue
        if kind == "theme" and code in refreshed_theme:
            closing.append((code, sector_code, kind, today))
        elif kind == "industry" and code in refreshed_industry:
            closing.append((code, sector_code, kind, today))

    opening = [
        (code, sector_code, name, kind, today, source)
        for code, sector_code, name, kind, source in desired
        if (code, sector_code, kind) not in open_rows
    ]
    keeping = [
        (name, source, code, sector_code, kind)
        for code, sector_code, name, kind, source in desired
        if (code, sector_code, kind) in open_rows
    ]
    if closing:
        sql = """
            UPDATE stock_sector_map AS m SET
                effective_to = v.day::date,
                updated_at = now()
            FROM (VALUES %s) AS v(code, sector_code, kind, day)
            WHERE m.code = v.code AND m.sector_code = v.sector_code
              AND m.kind = v.kind AND m.effective_to IS NULL
        """
        with conn.cursor() as cur:
            execute_values(cur, sql, closing, page_size=2000)
    if keeping:
        sql = """
            UPDATE stock_sector_map AS m SET
                sector_name = v.name,
                source = v.source,
                updated_at = now()
            FROM (VALUES %s) AS v(name, source, code, sector_code, kind)
            WHERE m.code = v.code AND m.sector_code = v.sector_code
              AND m.kind = v.kind AND m.effective_to IS NULL
        """
        with conn.cursor() as cur:
            execute_values(cur, sql, keeping, page_size=2000)
    if opening:
        sql = """
            INSERT INTO stock_sector_map
                (code, sector_code, sector_name, kind, effective_from, effective_to, source)
            VALUES %s
            ON CONFLICT (code, sector_code, kind, effective_from) DO UPDATE SET
                sector_name = EXCLUDED.sector_name,
                effective_to = NULL,
                source = EXCLUDED.source,
                updated_at = now()
        """
        with conn.cursor() as cur:
            execute_values(
                cur, sql, opening,
                template="(%s,%s,%s,%s,%s::date,NULL,%s)",
                page_size=2000,
            )
    conn.commit()
    return len(opening), len(closing)
