#!/usr/bin/env python3
"""把预测结果画成三张图：风向个股、可能的一板、可能的二板。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
OUT_DIR = Path(__file__).resolve().parent.parent / "reports"

W = 1080
PAD = 36
BG = (246, 243, 236)
INK = (28, 32, 28)
MUTED = (90, 96, 88)
LINE = (220, 214, 202)
CARD = (255, 252, 246)
HEAD = (24, 48, 36)
PILL = (24, 48, 36)

KINDS = (
    ("leaders", "风向个股", "看这些票，就能看到题材的情绪还在不在、还能不能延续。"),
    ("first", "可能的一板", "不是过往龙头的反包。前期缩量后连续放量，或急跌之后放量上影还在放大，并且踩在风口上。"),
    ("second", "可能的二板", "今天的首板里，明天有机会连上的。概率是同日同排名的历史晋级率，不是必涨。"),
)


def _font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def _code(raw) -> str:
    s = str(raw or "")
    return s[2:] if s[:2] in ("sh", "sz", "bj") else s


def _extra(kind, it) -> str:
    if kind == "leaders":
        b = int(it.get("board") or 0)
        return f"{b}连板" if b else "涨停"
    return f"{it.get('prob', '')}%"


def _sections(result, kind):
    rows = []
    for g in result.get("watchlist") or []:
        items = g.get(kind) or []
        if not items:
            continue
        rows.append((f"{g.get('theme') or '未归属'}    {g.get('phase') or ''}".strip(), items))
    return rows


def _draw_one(result, kind, title, note, path: Path) -> Path:
    title_f = _font(40, True)
    note_f = _font(22)
    head_f = _font(26, True)
    name_f = _font(30, True)
    code_f = _font(28, True)
    extra_f = _font(24)
    foot_f = _font(20)
    sections = _sections(result, kind)
    note_lines = _wrap(note, note_f, W - PAD * 2)
    body_h = 150 + len(note_lines) * 34
    if not sections:
        body_h += 80
    for head, items in sections:
        body_h += 64 + len(items) * 72 + 18
    body_h += 70
    img = Image.new("RGB", (W, body_h), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 92), fill=HEAD)
    d.text((PAD, 24), title, font=title_f, fill=(255, 250, 240))
    y = 112
    for line in note_lines:
        d.text((PAD, y), line, font=note_f, fill=MUTED)
        y += 34
    y += 8
    as_of = result.get("as_of") or ""
    nxt = result.get("next_trade_date") or result.get("next_date") or ""
    if not sections:
        d.text((PAD, y), "这一类今天没有。", font=name_f, fill=INK)
        y += 70
    for head, items in sections:
        d.rounded_rectangle((PAD - 8, y, W - PAD + 8, y + 52 + len(items) * 72), radius=12, fill=CARD)
        d.text((PAD + 8, y + 12), head, font=head_f, fill=HEAD)
        y += 58
        for it in items:
            d.line((PAD + 8, y, W - PAD - 8, y), fill=LINE, width=1)
            y += 16
            d.text((PAD + 8, y), str(it.get("name") or ""), font=name_f, fill=INK)
            code = _code(it.get("code"))
            pill_w = int(code_f.getlength(code)) + 28
            d.rounded_rectangle((430, y - 4, 430 + pill_w, y + 40), radius=8, fill=PILL)
            d.text((444, y), code, font=code_f, fill=(255, 250, 240))
            extra = _extra(kind, it)
            d.text((W - PAD - int(extra_f.getlength(extra)) - 8, y + 2), extra, font=extra_f, fill=MUTED)
            y += 56
        y += 22
    d.text((PAD, y), f"截至 {as_of} 收盘    看的是 {nxt}", font=foot_f, fill=MUTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return path


def _wrap(text, font, width):
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


def render_three(result: dict, out_dir: Path | None = None) -> list[Path]:
    day = str(result.get("as_of") or "unknown").replace("-", "")
    base = out_dir or OUT_DIR
    paths = []
    for kind, title, note in KINDS:
        paths.append(_draw_one(result, kind, title, note, base / f"watchlist_{day}_{kind}.png"))
    return paths


def main():
    from data_api.predict_limitup import get_conn, predict

    conn = get_conn()
    try:
        result = predict(conn)
    finally:
        conn.close()
    for p in render_three(result):
        print(p)


if __name__ == "__main__":
    main()
