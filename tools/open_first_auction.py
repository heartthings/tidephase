#!/usr/bin/env python3
"""9:25 可能的一板。全市场看当天竞价，不看昨天的候选名单。

prepare 在开盘前把全市场代码、名称、昨天涨停、板块成分写好。
push 在 9:25 只对这批代码取一次报价，按抢筹、高开、小口袋一起动来排序。
小口袋里至少两只一起动才算板块异动。同花顺「今天炒什么」和隔夜消息只加分。直接发一条短文字。

竞价额在 9:25 那一拍经常不齐。09:26 的撮合终版才到齐，所以到点之后先看覆盖，齐了再算。代码和板块可以提前备。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
import yaml

ROOT = Path("/home/hello/application/dev/market-datalayer")
SECRETS = ROOT / "configs/secrets.yaml"
PACK = ROOT / "data/cache/open_first_pack.json"
MARKER_DIR = ROOT / "data/cache"
PUSH = Path("/home/hello/application/red/workdsh/runtime/preview/agents/skills/feishu-push/scripts/feishu_push.py")
TZ = ZoneInfo("Asia/Shanghai")

POCKET = {
    "业绩增长", "中报增长", "三季报增长", "年报增长", "预盈预增",
    "股权转让", "国有企业", "地方国企", "央企", "国企改革", "央国企改革",
    "超跌", "低价股", "沪股通", "深股通", "融资融券", "证金持股",
}
# 自己高开的下限。同板块其他人涨过这条就算在一起动。
GAP = 3.0
PEER = 2.0
# 真正的板块异动：小口袋里至少两只一起动。一只单独高开不算。
MIN_TOGETHER = 2
# 小口袋：太小不成板块，太大是宽标签。
MIN_MEMBERS = 5
MAX_MEMBERS = 40
# 竞价额至少这么多，或者达到昨天成交额的这个比例，才算抢筹。
MIN_AUCTION_YUAN = 5_000_000
MIN_AMOUNT_RATIO = 0.02
TOP_N = 12
# 10 月 09:26 终版的实际覆盖：全市场有额大约 97% 起，涨过 2% 的有额不低于 99%。
# 没到这个程度就还没齐，不算。
READY_ALL = 0.97
READY_MOVER = 0.99


def now_sh() -> datetime:
    return datetime.now(TZ)


def connect():
    db = yaml.safe_load(SECRETS.read_text()).get("database") or {}
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="duser_reader", password=db.get("duser_reader_password", ""),
    )


def trade_open(conn, day: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_open FROM trade_cal WHERE market='SSE' AND cal_date=%s",
            (day,),
        )
        row = cur.fetchone()
    return bool(row and row[0] == 1)


def limit_line(code: str) -> float:
    if code.startswith(("sz30", "sh68")):
        return 19.5
    if code.startswith("bj"):
        return 29.5
    return 9.5


def prepare() -> None:
    """全市场底稿：代码、名称、上一交易日涨停、开盘啦板块成分。不读预测名单。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(date) FROM stock_daily")
            as_of = cur.fetchone()[0]
            if as_of is None:
                raise SystemExit("stock_daily 是空的")
            cur.execute(
                """
                SELECT cal_date FROM trade_cal
                WHERE market='SSE' AND is_open=1 AND cal_date > %s
                ORDER BY cal_date LIMIT 1
                """,
                (as_of,),
            )
            nxt = cur.fetchone()
            if not nxt:
                raise SystemExit(f"{as_of} 之后没有交易日")
            trade_date = nxt[0]
            cur.execute(
                """
                SELECT code, coalesce(name, ''), coalesce(amount, 0)
                FROM stock_daily
                WHERE date=%s AND volume > 0 AND NOT is_st
                  AND coalesce(name, '') NOT LIKE '%%ST%%'
                """,
                (as_of,),
            )
            names = {}
            yday_amount = {}
            for code, name, amount in cur.fetchall():
                names[code] = name
                yday_amount[code] = float(amount or 0)
            cur.execute("SELECT code FROM zt_pool WHERE date=%s", (as_of,))
            yesterday_limit = sorted(code for (code,) in cur.fetchall())
            cur.execute(
                """
                SELECT sector_name, code
                FROM stock_sector_map
                WHERE kind='theme' AND sector_code LIKE '801%%'
                  AND effective_from <= %s
                  AND (effective_to IS NULL OR effective_to > %s)
                """,
                (as_of, as_of),
            )
            grouped: dict[str, set[str]] = defaultdict(set)
            for name, code in cur.fetchall():
                if not name or name in POCKET or code not in names:
                    continue
                grouped[name].add(code)
    finally:
        conn.close()

    sectors = {
        name: sorted(codes)
        for name, codes in grouped.items()
        if MIN_MEMBERS <= len(codes) <= MAX_MEMBERS
    }
    covered = {code for codes in sectors.values() for code in codes}
    pack = {
        "as_of": str(as_of),
        "trade_date": str(trade_date),
        "prepared_at": now_sh().isoformat(timespec="seconds"),
        "names": {code: names[code] for code in covered},
        "yday_amount": {code: yday_amount.get(code, 0) for code in covered},
        "yesterday_limit": yesterday_limit,
        "sectors": sectors,
    }
    PACK.parent.mkdir(parents=True, exist_ok=True)
    PACK.write_text(json.dumps(pack, ensure_ascii=False))
    print(
        f"prepared {pack['trade_date']} from {pack['as_of']} "
        f"stocks={len(pack['names'])} sectors={len(sectors)}"
    )


def fetch_quotes(codes: list[str]) -> dict[str, dict]:
    """只查备好的代码。pct 是百分数，amount 是竞价额（元）。"""
    if not codes:
        return {}
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    batches = [codes[i:i + 60] for i in range(0, len(codes), 60)]

    def one(batch: list[str]) -> dict[str, dict]:
        resp = session.get(
            "https://qt.gtimg.cn/q=" + ",".join(batch),
            timeout=8,
        )
        resp.raise_for_status()
        out = {}
        for entry in resp.text.split(";"):
            entry = entry.strip()
            if "=" not in entry:
                continue
            fields = entry.split("=", 1)[1].strip().strip('"').split("~")
            if len(fields) < 38:
                continue
            market_id, code_raw = fields[0], fields[2]
            if market_id == "1":
                code = f"sh{code_raw}"
            elif market_id == "51":
                code = f"sz{code_raw}"
            else:
                continue
            try:
                pct = float(fields[32] or 0)
                amount = float(fields[37] or 0) * 10000
            except ValueError:
                continue
            price = float(fields[3] or 0)
            prev = float(fields[4] or 0)
            if pct == 0 and price > 0 and prev > 0:
                pct = (price / prev - 1) * 100
            out[code] = {"pct": pct, "amount": amount}
        return out

    found: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(one, batch) for batch in batches]
        for fut in as_completed(futs, timeout=45):
            try:
                found.update(fut.result())
            except Exception:
                continue
    return found


def _sector_codes(sector) -> list[str]:
    if isinstance(sector, dict):
        return [m["code"] if isinstance(m, dict) else m for m in sector.get("members") or []]
    return list(sector or [])


def _pct(quotes: dict, code: str) -> float | None:
    q = quotes.get(code)
    if q is None:
        return None
    if isinstance(q, dict):
        return q.get("pct")
    return q


def _amount(quotes: dict, code: str) -> float:
    q = quotes.get(code)
    if isinstance(q, dict):
        return float(q.get("amount") or 0)
    return 0.0


def _scramble_ok(amount: float, yday_wan: float) -> tuple[bool, float | None]:
    """竞价额（元）相对昨天成交额（万元）。

    额还是 0，多半是撮合数字还没印出来，先留着，抢筹分记 0，排到有真金的后面。
    额已经出来但很小，当成空心高开，不进榜。
    """
    if amount <= 0:
        return True, None
    ratio = (amount / (yday_wan * 10000)) if yday_wan and yday_wan > 0 else None
    ok = amount >= MIN_AUCTION_YUAN or (ratio is not None and ratio >= MIN_AMOUNT_RATIO)
    return ok, ratio


def _score(pct: float, limit: float, n: int, size: int, ratio: float | None, bonus: float) -> float:
    count_pts = min(n, 6) / 6 * 40
    density_pts = min(n / max(size, 1), 0.35) / 0.35 * 8
    scramble_pts = min(ratio or 0, 0.12) / 0.12 * 32
    gap_pts = min(max(pct - GAP, 0) / max(limit - GAP, 1), 1) * 15
    return round(count_pts + density_pts + scramble_pts + gap_pts + min(bonus, 10), 1)


def select_rows(pack: dict, quotes: dict, hot_names: set[str] | None = None,
                hot_codes: set[str] | None = None, news_names: set[str] | None = None) -> list[dict]:
    """全市场当天竞价。昨天涨停和 ST 已在底稿里剔除。

    留下：高开、没封死、竞价有真金、小口袋里还有别的票一起动。
    一起动的越多、抢筹越狠、越靠近涨停，排序越前。同花顺和消息只加分。
    """
    names = pack.get("names") or {}
    zt = set(pack.get("yesterday_limit") or [])
    yday_amount = pack.get("yday_amount") or {}
    sectors = pack.get("sectors") or {}
    hot_names = hot_names or set()
    hot_codes = hot_codes or set()
    news_names = news_names or set()

    movers: dict[str, list[str]] = {}
    for name, sector in sectors.items():
        codes = _sector_codes(sector)
        if not (MIN_MEMBERS <= len(codes) <= MAX_MEMBERS):
            continue
        hit = []
        for code in codes:
            pct = _pct(quotes, code)
            if pct is not None and pct >= PEER:
                hit.append(code)
        if len(hit) >= MIN_TOGETHER:
            movers[name] = hit

    best: dict[str, tuple] = {}
    for name, hit in movers.items():
        size = len(_sector_codes(sectors[name]))
        others = set(hit)
        for code in hit:
            if code in zt or code not in names:
                continue
            pct = _pct(quotes, code)
            if pct is None or pct < GAP or pct >= limit_line(code):
                continue
            if len(others - {code}) < MIN_TOGETHER - 1:
                continue
            amount = _amount(quotes, code)
            ok, ratio = _scramble_ok(amount, float(yday_amount.get(code) or 0))
            if not ok:
                continue
            key = (len(hit), -size)
            old = best.get(code)
            if old is None or key > old[0]:
                best[code] = (key, name, pct, ratio, amount, len(hit), size)

    rows = []
    for code, (_, leaf, pct, ratio, amount, n, size) in best.items():
        tags = []
        bonus = 0.0
        if code in hot_codes or leaf in hot_names:
            bonus += 6
            tags.append("同花顺")
        if leaf in news_names:
            bonus += 4
            tags.append("消息")
        rows.append({
            "leaf": leaf,
            "code": code,
            "name": names.get(code) or code,
            "pct": pct,
            "ratio": ratio,
            "amount": amount,
            "movers": n,
            "score": _score(pct, limit_line(code), n, size, ratio, bonus),
            "tags": tags,
        })
    rows.sort(key=lambda r: (-r["score"], -r["movers"], -(r["ratio"] or 0), -r["pct"], r["code"]))
    return rows


def render(day: str, rows: list[dict]) -> str:
    if not rows:
        return (
            f"{day} 竞价结束。全市场里没有同时满足的："
            "高开、竞价有真金、小口袋里还有别的票一起动，并且昨天没涨停。"
        )
    shown = rows[:TOP_N]
    lines = [
        f"{day} 撮合额到齐后才排。这是今天的竞价排序，不是昨天的预测概率。",
        "分越高：小口袋里一起动的越多、竞价抢筹越狠、高开越靠近涨停。一只单独高开不算板块异动。同花顺今天炒什么、隔夜消息只加分。",
    ]
    for i, r in enumerate(shown, start=1):
        if r["ratio"] is not None:
            chase = f"抢筹{r['ratio'] * 100:.0f}%昨额"
        else:
            chase = f"竞价{r['amount'] / 1e4:.0f}万"
        extra = (" " + " ".join(r["tags"])) if r["tags"] else ""
        lines.append(
            f"{i}. {r['name']} {r['code']}  {r['score']:.0f}分  "
            f"{r['pct']:+.1f}%  {chase}  {r['leaf']} {r['movers']}只{extra}"
        )
    left = len(rows) - len(shown)
    if left > 0:
        lines.append(f"还有 {left} 只，同一口径，这次没展开。")
    return "\n".join(lines)


JTC_URL = (
    "https://news.10jqka.com.cn/app/concept_v2_api/open/api"
    "/concept/event/jtcsm/v1/event/list"
)
JTC_REFERER = "https://news.10jqka.com.cn/app/hot_concept/v2/main"


def _prefix_code(raw: str) -> str:
    raw = str(raw or "").zfill(6)
    if raw.startswith("6"):
        return "sh" + raw
    if raw.startswith(("0", "3")):
        return "sz" + raw
    if raw.startswith(("4", "8")) or raw.startswith("92"):
        return "bj" + raw
    return ""


def fetch_jtcsm(day: str | None = None, before: datetime | None = None) -> tuple[set[str], set[str]]:
    """同花顺「今天炒什么」。akshare 没有这一路，直接调这个接口。

    不传 day 时取最新一页。before 用来回看：只留这个时刻之前已经挂出来的事件。
    返回方向名、以及事件里点名的个股。失败就当没有加分，不挡住推送。
    """
    import requests
    names: set[str] = set()
    codes: set[str] = set()
    cutoff = before or now_sh()
    try:
        resp = requests.get(
            JTC_URL,
            headers={"User-Agent": "Mozilla/5.0", "Referer": JTC_REFERER},
            timeout=8,
        )
        pages = (resp.json().get("data") or [])
    except Exception:
        return names, codes
    if day:
        pages = [page for page in pages if str(page.get("date") or "") == day]
    elif pages:
        newest = str(pages[0].get("date") or "")
        pages = [page for page in pages if str(page.get("date") or "") == newest]
    for page in pages:
        for event in page.get("eventList") or []:
            posted_raw = event.get("createTime")
            if posted_raw:
                posted = datetime.fromtimestamp(int(posted_raw), TZ)
                if posted > cutoff:
                    continue
            direction = str(event.get("investmentDirection") or "").strip()
            if len(direction) >= 2:
                names.add(direction)
            for theme in event.get("themes") or []:
                show = str(theme.get("showName") or theme.get("indexName") or "").strip()
                if len(show) >= 2:
                    names.add(show)
            for stock in event.get("topStocks") or []:
                code = _prefix_code(stock.get("stockCode"))
                if code:
                    codes.add(code)
    return names, codes


def news_hit(pack: dict) -> set[str]:
    """上一交易日 15:00 之后的财联社标题里，出现了哪些小口袋的名字。"""
    as_of = pack.get("as_of")
    sectors = list((pack.get("sectors") or {}).keys())
    if not as_of or not sectors:
        return set()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT coalesce(title, '')
                FROM market_messages
                WHERE source='cls'
                  AND msg_ts >= (%s::timestamp + time '15:00') AT TIME ZONE 'Asia/Shanghai'
                """,
                (as_of,),
            )
            titles = "\n".join(row[0] for row in cur.fetchall())
    except Exception:
        return set()
    finally:
        conn.close()
    return {name for name in sectors if len(name) >= 2 and name in titles}


def send(title: str, content: str) -> None:
    proc = subprocess.run(
        [
            sys.executable, str(PUSH),
            "--sender", "yan",
            "--title", title,
            "--content", content,
            "--priority", "normal",
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def send_image(title: str, path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable, str(PUSH),
            "--sender", "yan",
            "--title", title,
            "--image", str(path),
            "--priority", "normal",
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def render_image(day: str, rows: list[dict]) -> Path:
    """和同一条文字展开的名单一致，只画前 TOP_N 只。"""
    from PIL import Image, ImageDraw, ImageFont

    font = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    font_b = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    out_dir = Path("/home/hello/文档/deepseek-harness/default-workspace/观势简报")
    title_f = ImageFont.truetype(font_b, 40)
    note_f = ImageFont.truetype(font, 22)
    name_f = ImageFont.truetype(font_b, 30)
    code_f = ImageFont.truetype(font_b, 28)
    extra_f = ImageFont.truetype(font, 24)
    foot_f = ImageFont.truetype(font, 20)
    w, pad = 1080, 36
    bg, ink, muted = (246, 243, 236), (28, 32, 28), (90, 96, 88)
    line, card, head, pill = (220, 214, 202), (255, 252, 246), (24, 48, 36), (24, 48, 36)
    shown = rows[:TOP_N]
    note = (
        f"{day} 竞价。高开、竞价有真金、小口袋里一起动。昨天已经涨停的不在这里。"
        "分数不是昨天的预测概率。和同时发出的文字是同一份前 12 只。"
    )
    def wrap(text, fnt, width):
        lines, cur = [], ""
        for ch in text:
            trial = cur + ch
            if fnt.getlength(trial) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines or [""]
    note_lines = wrap(note, note_f, w - pad * 2)
    row_h = 88
    body_h = 150 + len(note_lines) * 34 + 64 + len(shown) * row_h + 18 + 70
    img = Image.new("RGB", (w, body_h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 92), fill=head)
    d.text((pad, 24), "可能的一板", font=title_f, fill=(255, 250, 240))
    y = 112
    for ln in note_lines:
        d.text((pad, y), ln, font=note_f, fill=muted)
        y += 34
    y += 16
    d.rounded_rectangle((pad - 8, y, w - pad + 8, y + 52 + len(shown) * row_h), radius=12, fill=card)
    d.text((pad + 8, y + 12), f"竞价排序    前 {len(shown)} 只", font=ImageFont.truetype(font_b, 26), fill=head)
    y += 58
    for r in shown:
        d.line((pad + 8, y, w - pad - 8, y), fill=line, width=1)
        y += 16
        d.text((pad + 8, y), str(r["name"]), font=name_f, fill=ink)
        code = str(r["code"])
        code = code[2:] if code[:2] in ("sh", "sz", "bj") else code
        pill_w = int(code_f.getlength(code)) + 28
        d.rounded_rectangle((430, y - 4, 430 + pill_w, y + 40), radius=8, fill=pill)
        d.text((444, y), code, font=code_f, fill=(255, 250, 240))
        if r["ratio"] is not None:
            chase = f"抢筹{r['ratio'] * 100:.0f}%"
        else:
            chase = f"{r['amount'] / 1e4:.0f}万"
        extra = f"{r['score']:.0f}分  {r['pct']:+.1f}%  {chase}"
        d.text((w - pad - int(extra_f.getlength(extra)) - 8, y + 2), extra, font=extra_f, fill=muted)
        sub = f"{r['leaf']}  {r['movers']}只一起动"
        if r.get("tags"):
            sub += "  " + " ".join(r["tags"])
        d.text((pad + 8, y + 40), sub, font=note_f, fill=muted)
        y += row_h - 16
    y += 22
    d.text((pad, y), f"{day} 09:26 竞价终版", font=foot_f, fill=muted)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"open_first_{day.replace('-', '')}.png"
    img.save(path, "PNG")
    return path


def _fill_counts(quotes: dict) -> tuple[int, int, int, int]:
    vals = [q for q in quotes.values() if isinstance(q, dict)]
    filled = sum(1 for q in vals if float(q.get("amount") or 0) > 0)
    movers = [q for q in vals if float(q.get("pct") or 0) >= PEER]
    mover_filled = sum(1 for q in movers if float(q.get("amount") or 0) > 0)
    return len(vals), filled, len(movers), mover_filled


def amount_ready(quotes: dict, requested: int) -> bool:
    """竞价额到了 10 月 09:26 终版那个程度，才算到齐。"""
    n, filled, movers, mover_filled = _fill_counts(quotes)
    if requested <= 0 or n < requested * 0.90:
        return False
    if n == 0 or filled / n < READY_ALL:
        return False
    if movers == 0:
        return False
    need = 1.0 if movers < 10 else READY_MOVER
    return mover_filled / movers >= need


def wait_for_amounts(codes: list[str]) -> tuple[dict, str]:
    """09:26 之后开始取。没齐就隔几秒再取，09:28:30 仍不齐就停。

    09:30 开盘之后成交额不再是竞价额，过了这个点不再取。
    """
    start = now_sh().replace(hour=9, minute=26, second=0, microsecond=0)
    deadline = now_sh().replace(hour=9, minute=28, second=30, microsecond=0)
    opened = now_sh().replace(hour=9, minute=30, second=0, microsecond=0)
    last: dict = {}
    while True:
        now = now_sh()
        if now >= opened:
            return last, "opened"
        if now < start:
            time.sleep(min(5.0, (start - now).total_seconds()))
            continue
        last = fetch_quotes(codes)
        if amount_ready(last, len(codes)):
            return last, "ready"
        if now_sh() >= deadline:
            return last, "late"
        time.sleep(3)


def push(dry_run: bool = False) -> None:
    import fcntl

    day = now_sh().strftime("%Y-%m-%d")
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = MARKER_DIR / "open_first_push.lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = MARKER_DIR / f".open-first-sent-{day}"
        if marker.is_file():
            print(f"already sent {day}")
            return
        conn = connect()
        try:
            opened = trade_open(conn, day)
        finally:
            conn.close()
        if not opened:
            print(f"not a trade day {day}")
            return
        if not PACK.is_file():
            text = f"{day} 开盘前的全市场底稿没有备好，这次不推。"
            if not dry_run:
                send(f"观势 · 9:25 可能的一板 {day}", text)
                marker.write_text("missing pack\n")
            print(text)
            return
        pack = json.loads(PACK.read_text())
        if pack.get("trade_date") != day:
            text = (
                f"{day} 手里的底稿是 {pack.get('trade_date') or '空'} 的，"
                "对不上今天，这次不推。"
            )
            if not dry_run:
                send(f"观势 · 9:25 可能的一板 {day}", text)
                marker.write_text("stale pack\n")
            print(text)
            return
        seen = []
        known = set()
        for sector in (pack.get("sectors") or {}).values():
            for code in _sector_codes(sector):
                if code not in known:
                    known.add(code)
                    seen.append(code)
        if dry_run:
            quotes, state = fetch_quotes(seen), "dry"
        else:
            quotes, state = wait_for_amounts(seen)
        n, filled, movers, mover_filled = _fill_counts(quotes)
        if state != "ready" and not dry_run:
            if state == "opened":
                text = f"{day} 已经开盘，竞价额和盘中成交混在一起，这次不排。"
            else:
                text = f"{day} 竞价额到 09:28:30 还没有到齐，这次不排。"
            send(f"观势 · 9:25 可能的一板 {day}", text)
            marker.write_text(f"amount {state} filled={filled}/{n} movers={mover_filled}/{movers}\n")
            print(f"amount not ready {day} {state} filled={filled}/{n} movers={mover_filled}/{movers}")
            return
        hot_names, hot_codes = fetch_jtcsm()
        news_names = news_hit(pack)
        rows = select_rows(pack, quotes, hot_names, hot_codes, news_names)
        text = render(day, rows)
        title = f"观势 · 9:25 可能的一板 {day}"
        if dry_run:
            print(title)
            print(text)
            print(f"quotes={len(quotes)} hits={len(rows)}")
            return
        send(title, text)
        if rows:
            send_image(title, render_image(day, rows))
        marker.write_text(f"hits={len(rows)} quotes={len(quotes)}\n")
        print(f"sent {day} hits={len(rows)} quotes={len(quotes)}")


def selfcheck() -> None:
    def q(pct, amount=20_000_000):
        return {"pct": pct, "amount": amount}

    pack = {
        "names": {
            "sh600001": "甲", "sh600002": "乙", "sh600009": "丙",
            "sz000008": "丁", "sz000001": "戊", "sz000002": "己",
            "sz300001": "庚", "sz300002": "辛", "sz300003": "壬",
        },
        "yday_amount": {code: 2000 for code in (
            "sh600001", "sh600002", "sh600009", "sz000008",
            "sz000001", "sz000002", "sz300001", "sz300002", "sz300003",
        )},
        "yesterday_limit": ["sh600002"],
        "sectors": {
            # 6 只，落在小口袋里。乙是昨天涨停。
            "航天": ["sh600001", "sh600002", "sh600009", "sz000008", "sz000003", "sz000004"],
            "零售": ["sz000001", "sz000002", "sz000005", "sz000006", "sz000007"],
            "软件": ["sz300001", "sz300002", "sz300003", "sh600001", "sz300004", "sz300005"],
        },
    }
    quotes = {
        "sh600001": q(6.2),
        "sh600002": q(7.0),
        "sh600009": q(3.4),
        "sz000008": q(2.4),
        "sz000001": q(5.0),
        "sz000002": q(0.4),
        "sz300001": q(15.0),
        "sz300002": q(6.0),
        "sz300003": q(4.0, amount=100_000),  # 有高开，没有抢筹
        "sh600008": q(3.0),
    }
    rows = select_rows(
        pack, quotes, hot_names={"软件"}, hot_codes=set(), news_names=set(),
    )
    got = [r["code"] for r in rows]
    # 庚高开更靠近 20% 线且有抢筹，甲有抢筹但高开较浅。壬没有抢筹。乙昨天涨停。
    if got[0] != "sz300001" or "sh600001" not in got or "sz300003" in got or "sh600002" in got:
        raise SystemExit(f"selfcheck failed: {got}")
    if rows[0]["tags"] != ["同花顺"]:
        raise SystemExit(f"bonus missing: {rows[0]}")
    thin = select_rows(pack, {**quotes, "sz300001": q(19.9)})
    if any(r["code"] == "sz300001" for r in thin):
        raise SystemExit("sealed name should be left out")
    text = render("2026-11-02", rows)
    if "庚" not in text or "乙" in text:
        raise SystemExit(text)
    full = {f"sh{i:06d}": {"pct": 1.0, "amount": 1_000_000} for i in range(100)}
    full.update({f"sh600{i:03d}": {"pct": 3.0, "amount": 2_000_000} for i in range(20)})
    if not amount_ready(full, 100):
        raise SystemExit("ready sample should pass")
    thin = {code: {"pct": q["pct"], "amount": 0} for code, q in full.items()}
    if amount_ready(thin, 100):
        raise SystemExit("empty amounts should wait")
    print("selfcheck ok")
    print(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    push_p = sub.add_parser("push")
    push_p.add_argument("--dry-run", action="store_true")
    sub.add_parser("selfcheck")
    args = parser.parse_args()
    if args.cmd == "prepare":
        prepare()
    elif args.cmd == "push":
        push(dry_run=args.dry_run)
    else:
        selfcheck()


if __name__ == "__main__":
    main()
