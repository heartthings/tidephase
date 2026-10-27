#!/usr/bin/env python3
"""取当日预测，生成风向个股、一板、二板三张图，发到飞书文字简报所在的群。"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

TOKEN = Path("/home/hello/.qwenpaw/workspaces/guanshi/data/data_api_read_token")
API = "http://127.0.0.1:8787/data/predict_limitup?format=json"
PUSH = Path("/home/hello/application/red/workdsh/runtime/preview/agents/skills/feishu-push/scripts/feishu_push.py")
TITLES = {
    "leaders": "观势 · 风向个股",
    "first": "观势 · 可能的一板",
    "second": "观势 · 可能的二板",
}


def main() -> None:
    token = TOKEN.read_text().strip()
    req = urllib.request.Request(API, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode())
    result = payload.get("data") or payload
    if not result.get("watchlist") and not result.get("as_of"):
        raise SystemExit("预测接口没有返回可用结果")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from render_watchlist import render_three

    for path in render_three(result):
        kind = path.stem.rsplit("_", 1)[-1]
        proc = subprocess.run(
            [
                sys.executable, str(PUSH),
                "--sender", "yan",
                "--title", TITLES.get(kind, path.stem),
                "--image", str(path),
            ]
        )
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
        print(path)


if __name__ == "__main__":
    main()
