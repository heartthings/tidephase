"""
j_topic_sync - 题材库增量同步（08:00 每日）
移植自 Java TopicPipelineServiceImpl + ThemeCrawler + TopicRelationService

流程：
1. 爬取龙虎 theme_id [1,1000] 中未占位的题材
2. 刷新已有题材的详情与关联个股
3. AI 关联（topic-relation prompt）
4. AI 重解释（topic-explain prompt）
5. 飞书摘要推送

LLM: DashScope Generation 直连（主通道）
凭证: secrets.yaml → longhu + dashscope
"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
import yaml

from dworker.core.calendar_gate import check_trade_gate

logger = logging.getLogger(__name__)

SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "secrets.yaml"

# Prompt 常量（移植自 Java TopicPrompt.java）
RELATION_SYSTEM = """你是A股题材知识图谱专家。任务是根据目标题材的简介与详情，从候选题材列表中挑选真正相关的题材，并给出关系标签。
要求：
1. 只从候选列表中的名称选择，禁止编造不存在的题材名。
2. 关系标签要短、可展示在图谱边上，优先使用：属于、应用分支、技术落地、核心底层、政策驱动、硬件载体、消费升级、上游、下游、同属赛道、互补、竞争、催化。
3. 每个目标题材返回 3~12 条高质量关联；宁缺毋滥，不要硬凑。
4. 若能判断所属大分组，给出 group（如：人工智能/算力、半导体/芯片）。
5. 只输出 JSON，不要 markdown 代码块，不要解释。格式：
{"group":"人工智能/算力","relations":[{"target":"大模型概念","relation":"应用分支"}]}"""

EXPLAIN_SYSTEM = """你是资深A股题材研究员与科普作者。请在保留事实准确性的前提下，对题材做「由浅入深」重解释，帮助投资者快速建立完整认知。
写作要求：
1. 使用 Markdown；语言通俗但专业，信息密度高，避免空话。
2. 结构建议：一句话看懂 → 为什么重要 → 产业链/核心逻辑（配 Mermaid 图）→ 关键催化与风险 → 相关细分与个股观察维度 → 一句话总结。
3. 至少包含 1~2 个 Mermaid 图示（flowchart 或 mindmap），用于展示产业链或概念关系。
4. 不要编造具体股价、涨跌幅、未给出的财务数字；可基于给定素材做结构化梳理。
5. 直接输出 Markdown 正文，不要包在代码块里。"""


def load_secrets():
    with open(SECRETS_PATH) as f:
        return yaml.safe_load(f) or {}


def call_dashscope(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """DashScope Generation 直连"""
    secrets = load_secrets()
    ds = secrets.get("dashscope", {})
    api_key = ds.get("api_key", "")
    url = ds.get("generation_url", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation")
    model = model or ds.get("default_model", "qwen-long-latest")

    body = {
        "model": model,
        "input": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        },
        "parameters": {"result_format": "message", "temperature": 0.7}
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.post(url, json=body, headers=headers, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("output", {}).get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return data.get("output", {}).get("text", "")


def fetch_theme_info(theme_id: int) -> dict:
    """从龙虎获取题材详情"""
    secrets = load_secrets()
    longhu = secrets.get("longhu", {})
    hosts = longhu.get("hosts", {})
    token = longhu.get("theme_info_token", "")

    host_url = hosts.get("apparticle", "https://apparticle.longhuvip.com/w1/api/index.php")
    params = {
        "a": "ThemeInfo",
        "theme_id": theme_id,
        "token": token,
    }
    try:
        resp = requests.get(host_url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch theme {theme_id}: {e}")
        return {}


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    """Execute j_topic_sync."""
    t0 = time.time()

    # 日历门禁
    today = datetime.now().strftime("%Y-%m-%d")
    gate = check_trade_gate(conn, market="SSE", check_date=today)
    if not gate["allowed"]:
        note = f"SKIP: {gate['reason']}"
        logger.info(f"[j_topic_sync] {note}")
        return {"success": True, "source_used": "none", "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}

    logger.info("[j_topic_sync] Starting topic sync pipeline")

    # Step 1: Get existing topic theme_ids
    with conn.cursor() as cur:
        cur.execute("SELECT theme_id FROM topic")
        occupied = set(r[0] for r in cur.fetchall())

    # Step 2: Crawl missing themes (1-1000)
    newly_crawled = []
    for tid in range(1, 1001):
        if str(tid) in occupied:
            continue
        data = fetch_theme_info(tid)
        if data and data.get("ID"):
            newly_crawled.append({
                "theme_id": str(data["ID"]),
                "name": data.get("Name", ""),
                "brief_intro": data.get("BriefIntro", ""),
                "introduction": data.get("Introduction", ""),
            })
            if len(newly_crawled) >= 10:  # Limit per run
                break
        time.sleep(0.5)  # Rate limit

    # Step 3: Insert new topics
    written = 0
    for topic in newly_crawled:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO topic (topic_id, theme_id, name, brief_intro, introduction, source, ingest_ts)
                    VALUES (%s, %s, %s, %s, %s, 'longhu', now())
                    ON CONFLICT (topic_id) DO UPDATE SET
                        name=EXCLUDED.name, brief_intro=EXCLUDED.brief_intro,
                        introduction=EXCLUDED.introduction, ingest_ts=now()
                """, (f"topic_{topic['theme_id']}", topic["theme_id"], topic["name"],
                      topic["brief_intro"], topic["introduction"]))
            conn.commit()
            written += 1
        except Exception as e:
            logger.warning(f"Failed to insert topic {topic['theme_id']}: {e}")
            conn.rollback()

    # Step 4: AI explain for new topics (if any)
    ai_explained = 0
    for topic in newly_crawled[:3]:  # Limit AI calls per run
        try:
            user_prompt = f"题材名称：{topic['name']}\n原始简介：{topic['brief_intro']}\n原始详情：{topic['introduction'][:1000]}"
            ai_text = call_dashscope(EXPLAIN_SYSTEM, user_prompt, model="qwen-plus-latest")
            if ai_text:
                with conn.cursor() as cur:
                    cur.execute("UPDATE topic SET ai_introduction = %s WHERE theme_id = %s",
                                (ai_text, topic["theme_id"]))
                conn.commit()
                ai_explained += 1
        except Exception as e:
            logger.warning(f"AI explain failed for {topic['name']}: {e}")

    # Step 5: Feishu notification
    feishu_notified = False
    if newly_crawled:
        feishu_notified = _send_feishu_summary(newly_crawled, ai_explained)

    elapsed = time.time() - t0
    note = f"new={len(newly_crawled)} written={written} ai_explained={ai_explained} feishu={feishu_notified} elapsed={elapsed:.1f}s"
    logger.info(f"[j_topic_sync] {note}")

    return {
        "success": True,
        "source_used": "longhu",
        "rows_in": len(newly_crawled),
        "rows_written": written,
        "rows_quarantined": 0,
        "note": note,
    }


def _send_feishu_summary(new_topics: list, ai_count: int) -> bool:
    """发送飞书摘要"""
    secrets = load_secrets()
    webhook = secrets.get("feishu", {}).get("webhook_url", "")
    if not webhook or webhook == "PENDING":
        return False

    names = [t["name"] for t in new_topics[:10]]
    content = f"**题材库增量同步**\n\n新增题材 {len(new_topics)} 个\nAI 重解释 {ai_count} 个\n\n" + "\n".join(f"- {n}" for n in names)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "题材库增量同步"}},
            "elements": [{"tag": "markdown", "content": content}]
        }
    }
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False
