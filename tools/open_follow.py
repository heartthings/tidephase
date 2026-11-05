#!/usr/bin/env python3
"""开盘后到 10:00 的联动推送。

每分钟看一次报价。跟随必须连续两分钟还在同一档之上，单次脉冲不记。
文字至少隔五分钟，只列还能跟的票；涨停只留一行参考。名单没变就不发。10:00 停。

只留同时满足两件事的板块：至少两只在涨，并且对上了隔夜消息或同花顺今天炒什么。
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from open_first_auction import (
    PACK,
    fetch_jtcsm,
    fetch_quotes,
    limit_line,
    news_hit,
    now_sh,
    send,
    trade_open,
    connect,
    _pct,
    _sector_codes,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "cache"
FOLLOW = 3.0
SHOW_SECTORS = 5
SHOW_FOLLOW = 5
SEND_GAP = 300


def _hot(pct: float | None, code: str) -> bool:
    if pct is None:
        return False
    return pct >= FOLLOW or pct >= limit_line(code)


def classify(pack: dict, quotes: dict, prev: dict[str, float],
             hot_names: set[str], hot_codes: set[str], news_names: set[str]) -> dict:
    """返回已涨停和已确认的跟随。跟随要求上一分钟也在阈值上。"""
    names = pack.get("names") or {}
    sectors = pack.get("sectors") or {}
    hot_members: dict[str, list[str]] = {}
    for name, sector in sectors.items():
        codes = _sector_codes(sector)
        hit = [code for code in codes if _hot(_pct(quotes, code), code)]
        if len(hit) >= 2:
            hot_members[name] = hit

    qualified = {}
    for name, hit in hot_members.items():
        linked_news = name in news_names or name in hot_names or any(code in hot_codes for code in hit)
        if linked_news:
            qualified[name] = hit

    best: dict[str, tuple] = {}
    for name, hit in qualified.items():
        for code in hit:
            if code not in names:
                continue
            pct = _pct(quotes, code)
            if pct is None:
                continue
            old = best.get(code)
            if old is None or len(hit) > old[0]:
                best[code] = (len(hit), name, pct)

    sealed = []
    following = []
    for code, (n, leaf, pct) in best.items():
        row = {
            "code": code,
            "name": names.get(code) or code,
            "pct": pct,
            "leaf": leaf,
            "movers": n,
        }
        if pct >= limit_line(code):
            sealed.append(row)
            continue
        if pct >= FOLLOW and prev.get(code, -999) >= FOLLOW:
            following.append(row)
    sealed.sort(key=lambda r: (-r["movers"], r["leaf"], -r["pct"], r["code"]))
    following.sort(key=lambda r: (-r["movers"], r["leaf"], -r["pct"], r["code"]))
    return {"sealed": sealed, "following": following}


def signature(book: dict) -> list[list[str]]:
    return [
        sorted(r["code"] for r in book["sealed"]),
        sorted(r["code"] for r in book["following"]),
    ]


def _code(raw: str) -> str:
    s = str(raw or "")
    return s[2:] if s[:2] in ("sh", "sz", "bj") else s


def sections(book: dict) -> list[dict]:
    """按板块把已涨停和跟随放在一起。涨停在前，涨幅高的在前。"""
    groups: dict[str, dict] = {}
    for kind in ("sealed", "following"):
        for row in book[kind]:
            leaf = row["leaf"]
            group = groups.setdefault(leaf, {"leaf": leaf, "sealed": [], "following": []})
            group[kind].append(row)
    rows = list(groups.values())
    for group in rows:
        group["sealed"].sort(key=lambda r: (-r["pct"], r["code"]))
        group["following"].sort(key=lambda r: (-r["pct"], r["code"]))
    rows.sort(key=lambda g: (-len(g["following"]), -len(g["sealed"]), g["leaf"]))
    return rows


def shown_followers(book: dict) -> list[dict]:
    """这一轮会写出来的跟随。涨停多但没有可跟的票，这一板块不占位置。"""
    picked = []
    for group in sections(book):
        if not group["following"]:
            continue
        picked.append(group)
        if len(picked) >= SHOW_SECTORS:
            break
    return picked


def display_signature(book: dict) -> list[str]:
    codes = []
    for group in shown_followers(book):
        for row in group["following"][:SHOW_FOLLOW]:
            codes.append(row["code"])
    return sorted(codes)


def should_send(changed: bool, last_sent: datetime | None, now: datetime, end: datetime) -> bool:
    if not changed:
        return False
    if last_sent is None or now >= end:
        return True
    return (now - last_sent).total_seconds() >= SEND_GAP


def _width(text: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(1, width - _width(text))


def render(day: str, when: datetime, book: dict) -> str:
    """只展开能跟的方向。每个方向最多几只票，涨停收成一行参考。"""
    clock = when.strftime("%H:%M")
    groups = [g for g in sections(book) if g["following"]]
    shown = groups[:SHOW_SECTORS]
    lines = [
        f"{day} {clock}",
        "这一轮只列还能跟的票。涨停只作参考。跟随要连续两分钟还在。",
    ]
    if not shown:
        lines.append("这一轮没有可跟的方向。")
        return "\n".join(lines)
    for group in shown:
        lines.append("")
        lines.append(f"{group['leaf']}  跟随 {len(group['following'])}")
        visible = group["following"][:SHOW_FOLLOW]
        for row in visible:
            lines.append(f"{_pad(str(row['name']), 8)}  {_code(row['code'])}  {row['pct']:+.1f}%")
        extra = len(group["following"]) - len(visible)
        if extra > 0:
            lines.append(f"还有 {extra} 只跟随")
        if group["sealed"]:
            names = [str(r["name"]) for r in group["sealed"][:3]]
            ref = "、".join(names)
            if len(group["sealed"]) > len(names):
                ref += f" 等{len(group['sealed'])}只"
            lines.append(f"参考涨停  {ref}")
    left = len(groups) - len(shown)
    if left > 0:
        lines.append("")
        lines.append(f"还有 {left} 个方向有跟随，这次不展开。")
    return "\n".join(lines)


def _state_path(day: str) -> Path:
    return STATE_DIR / f"open_follow_{day}.json"


def _load_state(day: str) -> dict:
    path = _state_path(day)
    if not path.is_file():
        return {"sig": None, "prev": {}, "sent": False}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"sig": None, "prev": {}, "sent": False}


def _save_state(day: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(day).write_text(json.dumps(state, ensure_ascii=False))


def _sample(pack: dict, prev: dict[str, float]) -> tuple[dict, dict[str, float]]:
    codes = []
    known = set()
    for sector in (pack.get("sectors") or {}).values():
        for code in _sector_codes(sector):
            if code not in known:
                known.add(code)
                codes.append(code)
    quotes = fetch_quotes(codes)
    hot_names, hot_codes = fetch_jtcsm()
    news_names = news_hit(pack)
    book = classify(pack, quotes, prev, hot_names, hot_codes, news_names)
    nxt = {}
    for code in known:
        pct = _pct(quotes, code)
        if pct is not None:
            nxt[code] = pct
    return book, nxt


def run(dry_run: bool = False) -> None:
    day = now_sh().strftime("%Y-%m-%d")
    conn = connect()
    try:
        opened = trade_open(conn, day)
    finally:
        conn.close()
    if not opened:
        print(f"not a trade day {day}")
        return
    if not PACK.is_file():
        text = f"{day} 开盘前的板块底稿没有备好，9:30 到 10:00 不推联动。"
        if not dry_run:
            send(f"观势 · 开盘联动 {day}", text)
        print(text)
        return
    pack = json.loads(PACK.read_text())
    if pack.get("trade_date") != day:
        text = f"{day} 板块底稿是 {pack.get('trade_date') or '空'} 的，对不上今天，不推联动。"
        if not dry_run:
            send(f"观势 · 开盘联动 {day}", text)
        print(text)
        return

    start = now_sh().replace(hour=9, minute=31, second=0, microsecond=0)
    end = now_sh().replace(hour=10, minute=0, second=0, microsecond=0)
    state = _load_state(day)
    while True:
        now = now_sh()
        if now < start:
            time.sleep(min(20.0, (start - now).total_seconds()))
            continue
        prev = {k: float(v) for k, v in (state.get("prev") or {}).items()}
        book, nxt = _sample(pack, prev)
        if prev and len(nxt) < max(10, int(0.5 * len(prev))):
            print(f"quotes thin {now.strftime('%H:%M')} {len(nxt)}")
            if now >= end or dry_run:
                break
            time.sleep(60)
            continue
        sig = display_signature(book)
        changed = sig != state.get("sig")
        last_raw = state.get("last_sent")
        last_sent = datetime.fromisoformat(last_raw) if last_raw else None
        if should_send(changed, last_sent, now, end):
            _deliver(day, now, book, dry_run=dry_run)
            state["sent"] = True
            state["sig"] = sig
            state["last_sent"] = now.isoformat()
            print(f"sent {now.strftime('%H:%M')} follow={len(book['following'])} shown={len(sig)}")
        else:
            print(f"quiet {now.strftime('%H:%M')} changed={changed}")
        state["prev"] = nxt
        if not dry_run:
            _save_state(day, state)
        if now >= end or dry_run:
            break
        time.sleep(60)

    if not state.get("sent") and not dry_run:
        text = (
            f"{day} 到 10:00，没有板块同时满足："
            "至少两只在涨，并且对上了隔夜消息或同花顺今天炒什么。"
        )
        send(f"观势 · 开盘联动 {day}", text)
        state["sent"] = True
        _save_state(day, state)
        print("sent empty close")


def _deliver(day: str, when: datetime, book: dict, dry_run: bool = False) -> None:
    text = render(day, when, book)
    title = f"观势 · 开盘联动 {day} {when.strftime('%H:%M')}"
    if dry_run:
        print(title)
        print(text)
        return
    send(title, text)


def push_once(dry_run: bool = False) -> None:
    """用当前报价发一条文字。跟随仍要用上一分钟也在涨的记录。"""
    day = now_sh().strftime("%Y-%m-%d")
    if not PACK.is_file():
        raise SystemExit("pack missing")
    pack = json.loads(PACK.read_text())
    if pack.get("trade_date") != day:
        raise SystemExit(f"pack date {pack.get('trade_date')} != {day}")
    state = _load_state(day)
    prev = {k: float(v) for k, v in (state.get("prev") or {}).items()}
    book, nxt = _sample(pack, prev)
    now = now_sh()
    _deliver(day, now, book, dry_run=dry_run)
    if dry_run:
        return
    state["sent"] = True
    state["sig"] = display_signature(book)
    state["last_sent"] = now.isoformat()
    state["prev"] = nxt
    _save_state(day, state)


def selfcheck() -> None:
    pack = {
        "names": {"sh600001": "甲", "sh600002": "乙", "sz000001": "丙"},
        "sectors": {"航天": ["sh600001", "sh600002", "sz000008"], "零售": ["sz000001", "sz000002"]},
    }
    quotes = {
        "sh600001": {"pct": 10.0},
        "sh600002": {"pct": 4.0},
        "sz000001": {"pct": 6.0},
    }
    # 乙只有这一分钟在涨，还不能算跟随。丙的板块只有一只在涨，不算联动。
    first = classify(pack, quotes, {}, set(), set(), {"航天"})
    assert [r["code"] for r in first["sealed"]] == ["sh600001"]
    assert first["following"] == []
    second = classify(pack, quotes, {"sh600002": 3.5}, set(), set(), {"航天"})
    assert [r["code"] for r in second["following"]] == ["sh600002"]
    # 没有消息的板块不进。
    quiet = classify(pack, quotes, {"sh600002": 4.0}, set(), set(), set())
    assert quiet["sealed"] == [] and quiet["following"] == []
    text = render("2026-11-05", datetime(2026, 11, 5, 9, 40), second)
    assert "航天" in text and "零售" not in text
    assert "乙" in text and "600002" in text and "+4.0%" in text
    assert "参考涨停  甲" in text
    assert "+10.0%" not in text
    end = datetime(2026, 11, 5, 10, 0)
    assert should_send(True, datetime(2026, 11, 5, 9, 32), datetime(2026, 11, 5, 9, 36), end) is False
    assert should_send(True, datetime(2026, 11, 5, 9, 31), datetime(2026, 11, 5, 9, 36), end)
    assert should_send(True, datetime(2026, 11, 5, 9, 58), end, end)
    assert should_send(False, None, datetime(2026, 11, 5, 9, 36), end) is False
    print("ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "once", "selfcheck"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "selfcheck":
        selfcheck()
        return
    if args.command == "once":
        push_once(dry_run=args.dry_run)
        return
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
