#!/usr/bin/env python3
"""取当日预测，生成可能的一板这一张图，发到飞书文字简报所在的群。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8787/data/predict_limitup?format=json"


def _machine_path(key: str) -> Path | None:
    env = {"feishu_push": "GUANSHI_FEISHU_PUSH", "brief_dir": "GUANSHI_BRIEF_DIR"}[key]
    if os.environ.get(env):
        return Path(os.environ[env])
    local = ROOT / "configs" / "local.yaml"
    if local.is_file():
        cfg = yaml.safe_load(local.read_text()) or {}
        if cfg.get(key):
            return Path(str(cfg[key]))
    return None


def _read_token() -> str:
    sec = yaml.safe_load((ROOT / "configs" / "secrets.yaml").read_text())
    return sec["api"]["bearer_token_read"]


PUSH = _machine_path("feishu_push")
MARKER_DIR = _machine_path("brief_dir") or (ROOT / "data" / "briefs")
TITLES = {
    "first": "观势 · 可能的一板",
}


def main() -> None:
    if PUSH is None:
        raise SystemExit("Set feishu_push in configs/local.yaml or GUANSHI_FEISHU_PUSH")
    token = _read_token()
    req = urllib.request.Request(API, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode())
    result = payload.get("data") or payload
    if not result.get("watchlist") and not result.get("as_of"):
        raise SystemExit("预测接口没有返回可用结果")
    day = str(result.get("as_of") or "unknown")
    marker = MARKER_DIR / f".watchlist-sent-{day}"
    if marker.is_file():
        print(f"already sent {day}")
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from render_watchlist import render_images

    sent = []
    for path in render_images(result):
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
        sent.append(path)
        print(path)
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text("\n".join(str(p) for p in sent) + "\n")


if __name__ == "__main__":
    main()
