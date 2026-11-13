#!/usr/bin/env python3
"""交易日早上的低吸股票池。

按掌阅科技这一类来筛：近 20 个交易日有过 3 板或 3 次涨停，
调整至少 4 个交易日，现价低于那一波最高价 12%–25%，
并且已经出现低吸信号（打到调整低点后收回 4% 以上，量能低于高潮，收盘仍低于前高）。
前一交易日被带动涨停的，单独放在「被带动」，不放进可盯。

--push：文字和图片合并成一条消息，标题「低吸股票池」，发到观势早间同一个飞书。
不是交易日不发。同一天发过不再发。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "configs" / "secrets.yaml"
TZ = ZoneInfo("Asia/Shanghai")
TITLE = "低吸股票池"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

W = 1080
PAD = 36
BG = (246, 243, 236)
INK = (28, 32, 28)
MUTED = (90, 96, 88)
LINE = (220, 214, 202)
CARD = (255, 252, 246)
HEAD = (24, 48, 36)
PILL = (24, 48, 36)
RED = (168, 48, 40)

# 这些词单独出现时，不算市场叫得出的题材。
NOISE_PARTS = (
    "羊字辈", "三季报", "业绩", "减亏", "扭亏", "分红", "高送转",
    "国企改革", "国资", "央企", "股权转让", "控制权", "预重整", "重组",
    "亏损收窄", "单季增长",
)


def connect():
    db = yaml.safe_load(SECRETS.read_text()).get("database") or {}
    return psycopg2.connect(
        host="127.0.0.1", port=15432, dbname="market_tsdb",
        user="duser_reader", password=db.get("duser_reader_password", ""),
    )


def _cache_dir() -> Path:
    path = ROOT / "data" / "cache" / "dip_pool"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _push_bin() -> Path:
    if os.environ.get("GUANSHI_FEISHU_PUSH"):
        return Path(os.environ["GUANSHI_FEISHU_PUSH"])
    local = ROOT / "configs" / "local.yaml"
    cfg = yaml.safe_load(local.read_text()) or {}
    return Path(str(cfg["feishu_push"]))


def _font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def _code(raw: str) -> str:
    s = str(raw or "")
    return s[2:] if s[:2] in ("sh", "sz", "bj") else s


def _theme_tokens(raw: str) -> list[str]:
    text = (raw or "").replace("，", "+").replace("、", "+")
    out = []
    for part in text.split("+"):
        part = part.strip()
        if not part or any(noise in part for noise in NOISE_PARTS):
            continue
        if "羊" in part and "字辈" in part:
            continue
        if part not in out:
            out.append(part)
    return out


def _ymd(day) -> str:
    return day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)


def _md(day) -> str:
    return day.strftime("%m-%d") if hasattr(day, "strftime") else str(day)[5:]


def _board_label(row: dict) -> str:
    if row["max_board"] >= 3:
        return f"{row['max_board']}板"
    return f"{row['zt_n']}次"


def screen(conn) -> dict:
    today = datetime.now(TZ).date()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_open FROM trade_cal WHERE market='SSE' AND cal_date=%s",
            (today,),
        )
        row = cur.fetchone()
    if not row or row[0] != 1:
        return {"skip": "今日非交易日，不推送"}

    with conn.cursor() as cur:
        cur.execute("SELECT max(date) FROM stock_daily")
        as_of = cur.fetchone()[0]
        cur.execute(
            """
            SELECT cal_date FROM trade_cal
            WHERE market='SSE' AND is_open=1 AND cal_date<=%s
            ORDER BY cal_date DESC LIMIT 40
            """,
            (as_of,),
        )
        days = [r[0] for r in cur.fetchall()]
    days.reverse()
    if len(days) < 20 or days[-1] != as_of:
        raise SystemExit(f"交易日或日线不齐，截至 {_ymd(as_of)}")
    pos = {d: i for i, d in enumerate(days)}
    window = days[-20:]
    recent = set(days[-8:])

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT code, name, date, board_days,
                   coalesce(nullif(theme, ''), nullif(reason, ''), '') AS theme
            FROM zt_pool
            WHERE date>=%s AND date<=%s
              AND name NOT LIKE '%%ST%%' AND name NOT LIKE '%%退%%'
            """,
            (window[0], as_of),
        )
        limits = list(cur.fetchall())
    by_code: dict[str, list] = {}
    for row in limits:
        by_code.setdefault(row["code"], []).append(row)

    recognized = []
    for code, rows in by_code.items():
        rows.sort(key=lambda r: (r["date"], r["board_days"] or 0))
        prior = [r for r in rows if r["date"] < as_of]
        base = prior if prior else rows
        if len(base) < 3 and max((r["board_days"] or 0) for r in base) < 3:
            continue
        theme_row = max(base, key=lambda r: (r["board_days"] or 0, r["date"]))
        tokens = _theme_tokens(theme_row["theme"])
        if not tokens:
            continue
        recognized.append({
            "code": code,
            "name": theme_row["name"],
            "theme": "、".join(tokens[:3]),
            "zt_n": len(base),
            "max_board": max((r["board_days"] or 0) for r in base),
            "first_zt": base[0]["date"],
            "last_zt": base[-1]["date"],
            "hit_today": any(r["date"] == as_of for r in rows),
        })
    if not recognized:
        return {"skip": None, "as_of": as_of, "watch": [], "lifted": []}

    codes = [r["code"] for r in recognized]
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT code, date, high, low, close, pct, volume
            FROM stock_daily
            WHERE code = ANY(%s) AND date>=%s AND date<=%s
            ORDER BY code, date
            """,
            (codes, window[0], as_of),
        )
        bars: dict[str, list] = {}
        for row in cur.fetchall():
            bars.setdefault(row["code"], []).append(row)

    watch, lifted = [], []
    for item in recognized:
        series = [b for b in bars.get(item["code"], []) if b["date"] >= item["first_zt"]]
        if not series or series[-1]["date"] != as_of:
            continue
        last_i = pos.get(item["last_zt"])
        if last_i is None:
            continue
        after = [b for b in series if b["date"] > item["last_zt"]]
        wave = [b for b in series if item["first_zt"] <= b["date"] <= item["last_zt"]]
        # 前高算到涨停后两个交易日，盖住封板次日的冲高。
        tail = days[last_i: last_i + 3]
        wave_high = max(
            (float(b["high"]) for b in series if b["date"] in tail or b["date"] <= item["last_zt"]),
            default=0,
        )
        wave_vol = max((float(b["volume"] or 0) for b in wave), default=0)
        if wave_high <= 0 or wave_vol <= 0:
            continue
        close = float(series[-1]["close"])
        prev = series[-2] if len(series) >= 2 else None

        if item["hit_today"] and prev is not None:
            # 连板中途的一天不算被带动。上一板至少隔了 4 个交易日。
            if pos[as_of] - last_i >= 4:
                prev_close = float(prev["close"])
                off_prev = prev_close / wave_high - 1
                if -0.30 <= off_prev <= -0.08:
                    lifted.append({
                        **item,
                        "close": close,
                        "off_pct": round((close / wave_high - 1) * 100, 1),
                    })
            continue

        gap = pos[as_of] - last_i
        if gap < 4 or not after:
            continue
        off = close / wave_high - 1
        if not (-0.25 <= off <= -0.12):
            continue
        if gap > 10 and len(after) >= 3:
            earlier = min(float(b["low"]) for b in after[:-2])
            recent_low = min(float(b["low"]) for b in after[-2:])
            if recent_low <= earlier:
                continue

        dip = min(after, key=lambda b: (float(b["low"]), -pos.get(b["date"], 0)))
        if dip["date"] not in recent:
            continue
        low = float(dip["low"])
        dip_close = float(dip["close"])
        if low <= 0 or dip_close < low * 1.04:
            continue
        if float(dip["volume"] or 0) >= wave_vol:
            continue
        if dip_close > wave_high * 0.90:
            continue
        watch.append({
            **item,
            "close": close,
            "off_pct": round(off * 100, 1),
            "signal": dip["date"],
            "reclaim": round((dip_close / low - 1) * 100, 1),
            "wave_high": round(wave_high, 2),
        })

    watch.sort(key=lambda r: (r["signal"], r["reclaim"]), reverse=True)
    lifted.sort(key=lambda r: (r["max_board"], r["zt_n"]), reverse=True)
    return {"skip": None, "as_of": as_of, "watch": watch[:12], "lifted": lifted[:8]}


def _text(result: dict) -> str:
    as_of = _ymd(result["as_of"])
    lines = [
        f"截至 {as_of} 收盘。有辨识度，调整还在，低吸信号已经出现，还没被带动回前高。",
        "",
        "可盯",
    ]
    if not result["watch"]:
        lines.append("今天没有符合的。")
    for row in result["watch"]:
        lines.append(
            f"- {row['name']} {_code(row['code'])} · {row['theme']} · {_board_label(row)}"
            f" · 距前高 {row['off_pct']}%"
            f" · 信号 {_md(row['signal'])} 从最低收回 {row['reclaim']}%"
            f" · 收盘 {row['close']:.2f}"
        )
    lines += ["", "被带动"]
    if not result["lifted"]:
        lines.append("前一交易日没有这类涨停。")
    for row in result["lifted"]:
        lines.append(
            f"- {row['name']} {_code(row['code'])} · {row['theme']} · {_board_label(row)} · 前一交易日涨停"
        )
    lines += ["", "被带动的不在可盯里。"]
    return "\n".join(lines)


def _clip(text: str, font, width: int) -> str:
    if font.getlength(text) <= width:
        return text
    ell = "…"
    while text and font.getlength(text + ell) > width:
        text = text[:-1]
    return text + ell


def _wrap(text: str, font, width: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if font.getlength(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def render(result: dict) -> Path:
    title_f = _font(40, True)
    note_f = _font(22)
    head_f = _font(26, True)
    name_f = _font(30, True)
    code_f = _font(24, True)
    sub_f = _font(22)
    foot_f = _font(20)
    note = "3板或3次涨停后调整，现价低于前高12%–25%，低吸信号已出现，还没被带动回前高。"
    note_lines = _wrap(note, note_f, W - PAD * 2)
    sections = [("可盯", result["watch"]), ("被带动", result["lifted"])]
    body = 128 + len(note_lines) * 34
    for _, rows in sections:
        body += 70 + max(len(rows), 1) * 94 + 24
    body += 56
    img = Image.new("RGB", (W, body), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 92), fill=HEAD)
    d.text((PAD, 24), TITLE, font=title_f, fill=(255, 250, 240))
    y = 112
    for line in note_lines:
        d.text((PAD, y), line, font=note_f, fill=MUTED)
        y += 34
    y += 12
    for title, rows in sections:
        d.text((PAD, y), title, font=head_f, fill=HEAD)
        y += 46
        show = rows or [{"_empty": "今天没有符合的。" if title == "可盯" else "前一交易日没有这类涨停。"}]
        for row in show:
            h = 86
            d.rounded_rectangle((PAD - 8, y, W - PAD + 8, y + h), radius=12, fill=CARD)
            if row.get("_empty"):
                d.text((PAD + 8, y + 26), row["_empty"], font=name_f, fill=INK)
                y += h + 8
                continue
            d.text((PAD + 8, y + 10), row["name"], font=name_f, fill=INK)
            code = _code(row["code"])
            pill_w = int(code_f.getlength(code)) + 24
            d.rounded_rectangle((250, y + 10, 250 + pill_w, y + 42), radius=8, fill=PILL)
            d.text((262, y + 12), code, font=code_f, fill=(255, 250, 240))
            if "signal" in row:
                right = f"距前高 {row['off_pct']}%"
                tail = f"信号 {_md(row['signal'])} 收回 {row['reclaim']}% · 收盘 {row['close']:.2f}"
            else:
                right = "涨停"
                tail = f"{_board_label(row)} · 前一交易日被带动"
            room = W - PAD * 2 - 16 - int(sub_f.getlength(" · " + tail))
            theme = _clip(row["theme"], sub_f, max(room, 80))
            sub = f"{theme} · {tail}"
            d.text((W - PAD - int(sub_f.getlength(right)) - 8, y + 14), right, font=sub_f, fill=RED)
            d.text((PAD + 8, y + 50), _clip(sub, sub_f, W - PAD * 2 - 16), font=sub_f, fill=MUTED)
            y += h + 8
        y += 8
    d.text((PAD, y), f"截至 {_ymd(result['as_of'])} 收盘", font=foot_f, fill=MUTED)
    path = _cache_dir() / f"dip_pool_{_ymd(result['as_of']).replace('-', '')}.png"
    img.save(path, "PNG")
    return path


def _send(content: str, image: Path) -> None:
    push = _push_bin()
    combined = subprocess.run(
        [sys.executable, str(push), "--sender", "yan", "--title", TITLE,
         "--content", content, "--image", str(image), "--priority", "normal"],
    )
    if combined.returncode == 0:
        return
    # 图片上传失败时退回纯文字，避免一条都不发。
    text = subprocess.run(
        [sys.executable, str(push), "--sender", "yan", "--title", TITLE,
         "--content", content, "--priority", "normal"],
    )
    if text.returncode != 0:
        raise SystemExit(text.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    today = datetime.now(TZ).date().isoformat()
    marker = _cache_dir() / f".sent-{today}"
    if args.push and marker.is_file():
        print(f"already sent {today}")
        return
    conn = connect()
    try:
        result = screen(conn)
    finally:
        conn.close()
    if result.get("skip"):
        print(result["skip"])
        return
    content = _text(result)
    image = render(result)
    print(content)
    print(image)
    if not args.push:
        return
    _send(content, image)
    marker.write_text(f"watch={len(result['watch'])} lifted={len(result['lifted'])}\n")
    print(f"已推送 可盯 {len(result['watch'])} 被带动 {len(result['lifted'])}")


if __name__ == "__main__":
    main()
