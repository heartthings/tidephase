#!/usr/bin/env python3
"""把市场雷达推到梁总单独的飞书机器人。

数据就是控制台「市场雷达」那一页：radar_event。
有新的一条就发一条卡片。已经发过的记在 data/cache，不重复发。

卡片按事件类型换颜色；金额、涨跌幅、封单这些数字标红；「减少」标绿。

run：交易日 09:15–15:30 补发今天还没发过的。
backfill：不看现在几点，把指定日期的市场雷达按时间顺序发完。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "configs" / "secrets.yaml"
STATE_PATH = ROOT / "data" / "cache" / "market_radar_sent.json"
TZ = ZoneInfo("Asia/Shanghai")
SEND_GAP = 0.7

# 飞书卡片 header.template。越红越要立刻看。
HEADER = {
    "连板预开": "red",
    "冲击涨停": "orange",
    "涨停回封": "orange",
    "涨停被砸": "yellow",
    "涨停打开": "yellow",
    "连板打开": "yellow",
    "封涨大减": "blue",
    "大盘直播": "blue",
}
AI_TAIL = "（该内容由AI大模型根据行情自动生成）"


def now_sh() -> datetime:
    return datetime.now(TZ)


def load_bot() -> tuple[str, str]:
    feishu = yaml.safe_load(SECRETS.read_text()).get("feishu") or {}
    url = (feishu.get("intraday_webhook_url") or "").strip()
    secret = (feishu.get("intraday_secret") or "").strip()
    if not url or not secret:
        raise SystemExit("configs/secrets.yaml 缺少 feishu.intraday_webhook_url 或 intraday_secret")
    return url, secret


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


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    kept = {}
    today = now_sh().date()
    for day, ids in state.items():
        try:
            age = (today - datetime.strptime(day, "%Y-%m-%d").date()).days
        except ValueError:
            continue
        if 0 <= age <= 10:
            kept[day] = ids
    STATE_PATH.write_text(json.dumps(kept, ensure_ascii=False))


def sign(timestamp: str, secret: str) -> str:
    raw = f"{timestamp}\n{secret}".encode()
    digest = hmac.new(raw, b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


# 正文里这些词本身就是重点，整词加粗并上色。
HOT_WORDS = (
    "连板预开", "冲击涨停", "涨停回封", "涨停被砸", "涨停打开", "连板打开", "封涨大减",
    "剩余封单", "竞价成交", "集合竞价", "当前成交额", "总成交额", "换手率", "开板概率",
    "一字涨停", "炸板", "回封", "涨停", "跌停", "缩量", "放量",
)
ORANGE_WORDS = {
    "涨停被砸", "涨停打开", "连板打开", "冲击涨停", "连板预开", "涨停回封",
    "一字涨停", "炸板", "回封", "涨停", "跌停",
}


def _mark(text: str, color: str) -> str:
    return f"<font color='{color}'>**{text}**</font>"


def paint(text: str) -> str:
    """按规则高亮：金额/涨跌幅标红，减少标绿，关键动作词加粗上色。"""
    text = text.replace("减少", _mark("减少", "green"))
    # 先标金额，万亿优先于万/亿
    text = re.sub(
        r"(-?\d+(?:\.\d+)?(?:%|万亿|亿元|万元|亿|万|元))",
        lambda m: _mark(m.group(1), "red"),
        text,
    )
    text = re.sub(
        r"(涨幅|跌幅)(-?\d+(?:\.\d+)?%)",
        lambda m: f"{m.group(1)}{_mark(m.group(2), 'red')}",
        text,
    )
    # N连板 / 四天三板，整段一次标完，避免再拆「连板」
    text = re.sub(
        r"([一二三四五六七八九十两\d]+连板|[一二三四五六七八九十两\d]+天[一二三四五六七八九十两\d]+板)",
        lambda m: _mark(m.group(1), "orange"),
        text,
    )

    def replace_word(word: str, color: str, src: str) -> str:
        out = []
        i = 0
        while i < len(src):
            j = src.find(word, i)
            if j < 0:
                out.append(src[i:])
                break
            # 已经在 **...** 里就跳过，防止套娃
            before = src[max(0, j - 2):j]
            after = src[j + len(word):j + len(word) + 2]
            if before == "**" or after == "**" or "<font" in src[max(0, j - 40):j]:
                out.append(src[i:j + len(word)])
                i = j + len(word)
                continue
            out.append(src[i:j])
            out.append(_mark(word, color))
            i = j + len(word)
        return "".join(out)

    for word in sorted(HOT_WORDS, key=len, reverse=True):
        text = replace_word(word, "orange" if word in ORANGE_WORDS else "blue", text)
    return text


def _clean_body(content: str) -> str:
    content = (content or "").strip()
    if content.endswith(AI_TAIL):
        content = content[: -len(AI_TAIL)].rstrip()
    return content


def build_card(row: dict) -> dict:
    extra = row["extra"] if isinstance(row["extra"], dict) else {}
    event_type = (row["event_type"] or extra.get("status") or "市场雷达").strip()
    name = (extra.get("stock_name") or row["title"] or "").strip()
    lb = (extra.get("lb_status") or "").strip()
    status = (extra.get("status") or event_type).strip()
    stocks = extra.get("stocks") if isinstance(extra.get("stocks"), list) else []
    content = _clean_body(row["content"] or "")
    clock = row["ts"].astimezone(TZ).strftime("%H:%M")
    color = HEADER.get(event_type, HEADER.get(status, "wathet"))
    is_live = status == "大盘直播" or event_type == "大盘直播"

    lines: list[str] = []
    if is_live:
        # 顶栏已经是「大盘直播」，正文不再重复。有板块就只亮板块。
        plate = name if name and name not in {"大盘", "大盘直播"} else ""
        if not plate and event_type not in {"大盘", "大盘直播", ""}:
            plate = event_type
        if plate:
            head = f"**{plate}**"
            if lb:
                head += f"  <font color='red'>**{lb}**</font>"
            lines.append(head)
            lines.append("")
    else:
        title = name or event_type or "—"
        lines.append(f"**{title}**" + (f"（<font color='red'>**{lb}**</font>）" if lb else ""))
        if status and status not in {title, event_type}:
            lines.append(f"<font color='orange'>**{status}**</font>")
        lines.append("")

    if content:
        lines.append(paint(content))
    if stocks:
        lines.append("")
        lines.append("相关：" + "、".join(str(s) for s in stocks[:6]))

    body = "\n".join(lines).strip()
    header_title = "大盘直播" if is_live else f"市场雷达 · {event_type}"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": header_title,
                },
                "template": color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": body,
                    },
                },
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": clock},
                    ],
                },
            ],
        },
    }


def post(url: str, secret: str, card: dict) -> None:
    last_error = "unknown"
    for attempt in range(4):
        timestamp = str(int(time.time()))
        payload = {
            "timestamp": timestamp,
            "sign": sign(timestamp, secret),
            **card,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            time.sleep(2)
            continue
        except urllib.error.URLError as exc:
            last_error = f"network {exc.reason}"
            time.sleep(2)
            continue
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            return
        last_error = f"code={result.get('code')} msg={result.get('msg')}"
        # 频率限制时多等一会儿
        if result.get("code") in (11232, 9499, 19024):
            time.sleep(5 + attempt * 2)
        else:
            time.sleep(2 + attempt)
    raise SystemExit(f"飞书发送失败: {last_error}")


def fetch(conn, day: str) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ts, event_id, event_type, title, content, extra
            FROM radar_event
            WHERE ts::date = %s
              AND source = 'kaipanla_zhibo'
            ORDER BY ts ASC, event_id ASC
            """,
            (day,),
        )
        return [dict(row) for row in cur.fetchall()]


def deliver(day: str, rows: list[dict]) -> int:
    url, secret = load_bot()
    state = load_state()
    sent = set(state.get(day) or [])
    fresh = [row for row in rows if str(row["event_id"]) not in sent]
    if not fresh:
        print(f"{day} 没有新的市场雷达")
        return 0
    print(f"{day} 待发 {len(fresh)} 条市场雷达")
    for i, row in enumerate(fresh, start=1):
        post(url, secret, build_card(row))
        sent.add(str(row["event_id"]))
        state[day] = sorted(sent)
        save_state(state)
        if i == 1 or i == len(fresh) or i % 10 == 0:
            print(f"已发 {i}/{len(fresh)}")
        if i < len(fresh):
            time.sleep(SEND_GAP)
    return len(fresh)


def cmd_backfill(day: str) -> None:
    conn = connect()
    try:
        rows = fetch(conn, day)
    finally:
        conn.close()
    n = deliver(day, rows)
    print(f"完成 {n} 条")


def cmd_run() -> None:
    now = now_sh()
    day = now.date().isoformat()
    minute = now.hour * 60 + now.minute
    if minute < 9 * 60 + 15 or minute > 15 * 60 + 30:
        return
    conn = connect()
    try:
        if not trade_open(conn, day):
            return
        rows = fetch(conn, day)
    finally:
        conn.close()
    deliver(day, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    back = sub.add_parser("backfill")
    back.add_argument("--date", default=now_sh().date().isoformat())
    sub.add_parser("run")
    args = parser.parse_args()
    if args.cmd == "backfill":
        cmd_backfill(args.date)
    else:
        cmd_run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
