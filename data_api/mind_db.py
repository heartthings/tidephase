"""心库（mindbase）连接。认知、预测、反思、基率、交易体系和交易笔记都在心库，tidephase 只存行情等基础数据。

容器内经 mind-net 连 mind-tsdb:5432；宿主机脚本连 127.0.0.1:15433。账号在 configs/secrets.yaml 的 mind 段。
"""

import os
from pathlib import Path

import psycopg2
import yaml

SECRETS_PATH = Path(__file__).resolve().parent.parent / "configs" / "secrets.yaml"

MIND_TABLES = frozenset({
    "cognition", "cognition_current", "prediction", "reflection", "reflection_journal",
    "base_rate", "calibration_view", "trading_system_node", "trading_note", "note_category",
})


def _mind_cfg() -> dict:
    with open(SECRETS_PATH, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("mind", {})


def _connect(role: str, **kw):
    cfg = _mind_cfg()
    return psycopg2.connect(
        host=os.getenv("MIND_DB_HOST", cfg.get("host", "127.0.0.1")),
        port=int(os.getenv("MIND_DB_PORT", cfg.get("port", 15433))),
        dbname=cfg.get("name", "mind"),
        user=f"mind_{role}",
        password=cfg.get(f"{role}_password", ""),
        **kw,
    )


def get_mind_reader_conn():
    return _connect("reader", options="-c statement_timeout=30s")


def get_mind_writer_conn():
    return _connect("writer")
