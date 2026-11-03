#!/usr/bin/env python3
"""把预测结果画成三张图：风向个股、可能的一板、可能的二板。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
ROOT = Path(__file__).resolve().parent.parent


def _brief_dir() -> Path:
    if os.environ.get("GUANSHI_BRIEF_DIR"):
        return Path(os.environ["GUANSHI_BRIEF_DIR"])
    local = ROOT / "configs" / "local.yaml"
    if local.is_file():
        cfg = yaml.safe_load(local.read_text()) or {}
        if cfg.get("brief_dir"):
            return Path(str(cfg["brief_dir"]))
    return ROOT / "data" / "briefs"


OUT_DIR = _brief_dir()

W = 1080
PAD = 36
BG = (246, 243, 236)
INK = (28, 32, 28)
MUTED = (90, 96, 88)
LINE = (220, 214, 202)
CARD = (255, 252, 246)
HEAD = (24, 48, 36)
PILL = (24, 48, 36)

LEADERS = (
    "风向个股",
    "开始聚焦（当天至少 2 只涨停）也留。每条只看最高那只，用来看题材还能不能延续。",
    (("leaders", None),),
)
FIRST = (
    "可能的一板",
    "提前埋伏。买在分歧，卖在一致。题材还在聚集、正在分歧，或刚启动。发酵和高潮不在这张图里。右边是历史晋级率。",
    (("first", None),),
)
SECOND = (
    "可能的二板",
    "接力。只留题材还可能延续的：开始聚焦、启动、发酵。高潮是一致兑现，不接力。右边是历史晋级率。",
    (("second", None),),
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
    if kind == "first":
        groups = (result.get("first_board") or {}).get("groups") or []
        item_key = "candidates"
    elif kind == "second":
        groups = (result.get("second_board") or {}).get("groups") or []
        item_key = "candidates"
    else:
        groups = result.get("watchlist") or []
        item_key = "leaders"
    rows = []
    for g in groups:
        items = g.get(item_key) or []
        if not items:
            continue
        rows.append((f"{g.get('theme') or '未归属'}    {g.get('phase') or ''}".strip(), items))
    return rows


def _blocks(result, parts):
    blocks = []
    for kind, banner in parts:
        if banner:
            blocks.append(("banner", banner))
        sections = _sections(result, kind)
        if not sections:
            blocks.append(("empty", "这一类今天没有。"))
        for head, items in sections:
            blocks.append(("group", head, items, kind))
    return blocks


def _draw_one(result, title, note, parts, path: Path) -> Path:
    title_f = _font(40, True)
    note_f = _font(22)
    head_f = _font(26, True)
    name_f = _font(30, True)
    code_f = _font(28, True)
    extra_f = _font(24)
    foot_f = _font(20)
    banner_f = _font(28, True)
    blocks = _blocks(result, parts)
    note_lines = _wrap(note, note_f, W - PAD * 2)
    body_h = 150 + len(note_lines) * 34
    for block in blocks:
        if block[0] == "banner":
            body_h += 56
        elif block[0] == "empty":
            body_h += 64
        else:
            body_h += 64 + len(block[2]) * 72 + 18
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
    for block in blocks:
        if block[0] == "banner":
            d.text((PAD, y), block[1], font=banner_f, fill=HEAD)
            y += 48
            continue
        if block[0] == "empty":
            d.text((PAD, y), block[1], font=name_f, fill=INK)
            y += 56
            continue
        _, head, items, kind = block
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


def render_images(result: dict, out_dir: Path | None = None) -> list[Path]:
    day = str(result.get("as_of") or "unknown").replace("-", "")
    base = out_dir or OUT_DIR
    sheets = (
        (*LEADERS, f"watchlist_{day}_leaders.png"),
        (*FIRST, f"watchlist_{day}_first.png"),
        (*SECOND, f"watchlist_{day}_second.png"),
    )
    return [_draw_one(result, title, note, parts, base / name) for title, note, parts, name in sheets]


def render_three(result: dict, out_dir: Path | None = None) -> list[Path]:
    """兼容旧调用。现在出三张：风向个股、可能的一板、可能的二板。"""
    return render_images(result, out_dir)


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
