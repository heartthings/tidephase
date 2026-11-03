"""Pure rules for the after-close boards. No database access."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time


STAGES = ("聚集未完成", "启动", "发酵", "高潮", "分歧", "退潮")


def consecutive_height(open_dates_desc: list[date], limit_dates: set[date]) -> int:
    """Strict streak ending on the newest open day. A gap resets the count."""
    height = 0
    for day in open_dates_desc:
        if day in limit_dates:
            height += 1
        else:
            break
    return height


def theme_stage(height: int, today_n: int, prev_n: int, broken_n: int) -> str:
    """Stage names follow the cognition board, not a second vocabulary."""
    dropped = prev_n > 0 and today_n <= prev_n * 0.6
    crash = prev_n > 0 and today_n <= prev_n * 0.4
    diverge = (dropped and height >= 3) or (broken_n >= 3 and height >= 3)
    if crash and height >= 3:
        return "退潮"
    if diverge:
        return "分歧"
    if height >= 6:
        return "高潮"
    if height >= 4:
        return "发酵"
    if height >= 3:
        return "启动"
    return "聚集未完成"


def reason_verdict(theme_name: str, reasons: list[str]) -> tuple[str, str]:
    """成立 when the limit-up notes are about one thing. Otherwise 口袋."""
    heads = []
    for raw in reasons:
        text = (raw or "").strip()
        if not text:
            continue
        head = text.split("；")[0].split("+")[0].strip()[:18]
        if head:
            heads.append(head)
    if not heads:
        return "口袋", ""
    top, count = Counter(heads).most_common(1)[0]
    name = (theme_name or "").strip()
    named = sum(1 for raw in reasons if name and name in (raw or ""))
    if count >= max(2, int(len(heads) * 0.5)) or named >= max(1, int(len(reasons) * 0.5)):
        return "成立", top
    return "口袋", top


def same_push(seal_times: list[time | None]) -> str:
    """合力 when several names seal inside the same half hour. Otherwise 主力."""
    stamps = []
    for value in seal_times:
        if value is None:
            continue
        stamps.append(value.hour * 60 + value.minute)
    if len(stamps) < 3:
        return "主力"
    stamps.sort()
    best = 1
    left = 0
    for right, minute in enumerate(stamps):
        while minute - stamps[left] > 30:
            left += 1
        best = max(best, right - left + 1)
    return "合力" if best >= 3 else "主力"


def tomorrow_line(limit_up: int, broken: int, seal_rate: float | None) -> dict:
    """One status and at most three action chips. No paragraph."""
    rate = seal_rate or 0
    if limit_up >= 80 and rate >= 70:
        status = "一致看多"
        chips = ["主线还在推", "不追高潮", "看回踩承接"]
    elif limit_up < 30 or broken > max(limit_up, 1):
        status = "一致恐慌"
        chips = ["缩到试错", "等杀跌后看承接", "不抄最高板"]
    else:
        status = "中性"
        chips = ["按题材条件", "买在分歧", "不因指数改纪律"]
    return {"status": status, "chips": chips[:3]}


def fold_repeats(rows: list[dict], key: str = "title") -> list[dict]:
    """Keep the newest copy of a repeated title expanded. Older copies fold."""
    seen: set[str] = set()
    out = []
    for row in rows:
        title = (row.get(key) or "").strip()
        folded = bool(title) and title in seen
        if title:
            seen.add(title)
        out.append({**row, "folded": folded})
    return out


def assign_themes(messages: list[dict], theme_names: list[str]) -> list[dict]:
    """Attach the first theme name that appears in the title or body."""
    names = [name for name in theme_names if name and len(name) >= 2]
    names.sort(key=len, reverse=True)
    grouped: dict[str, list[dict]] = {}
    for row in messages:
        blob = f"{row.get('title') or ''} {row.get('content') or ''}"
        hit = next((name for name in names if name in blob), "未归类")
        grouped.setdefault(hit, []).append(row)
    cards = []
    for name, items in grouped.items():
        newest = items[0]
        summary = (newest.get("title") or newest.get("content") or "").strip()
        if len(summary) > 28:
            summary = summary[:28] + "…"
        cards.append({
            "theme": name,
            "count": len(items),
            "summary": summary,
            "items": items,
        })
    cards.sort(key=lambda card: (-card["count"], card["theme"] == "未归类", card["theme"]))
    return cards


def hour_rail(messages: list[dict]) -> list[dict]:
    buckets: dict[str, int] = {}
    for row in messages:
        stamp = row.get("msg_ts")
        label = stamp.strftime("%H:00") if hasattr(stamp, "strftime") else "--:--"
        buckets[label] = buckets.get(label, 0) + 1
    return [{"hour": hour, "count": count} for hour, count in sorted(buckets.items())]


def yuan_to_yi(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / 100_000_000, 2)


def clip_line(text: str | None, limit: int = 32) -> str:
    raw = " ".join((text or "").split())
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "…"


def session_ready(trade_day: date, now: datetime, row_count: int) -> bool:
    if row_count <= 0:
        return False
    if trade_day == now.date() and (now.hour, now.minute) < (15, 30):
        return False
    return True
