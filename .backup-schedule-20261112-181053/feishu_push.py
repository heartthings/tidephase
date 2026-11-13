#!/usr/bin/env python3
"""
飞书 Webhook 消息推送脚本
使用 Card JSON 1.0 格式，多元素组合实现良好排版。

飞书 markdown 元素支持的语法（有限）：
- 加粗 **text**
- 斜体 *text*
- 删除线 ~~text~~
- 行内代码 `code`
- 链接 [text](url)
- 无序列表 - item
- 换行（两个空格+换行 或 \n）

不支持：## 标题、--- 分隔线、表格、引用块、图片（需单独 img 元素）

解决方案：用多个元素（markdown + hr + div）组合排版。
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/bd17d9a8-9b2a-47d6-a70c-4f8eea53193c"

PRIORITY_CONFIG = {
    "normal": {"template": "blue", "prefix": "📋"},
    "important": {"template": "orange", "prefix": "⚠️"},
    "urgent": {"template": "red", "prefix": "🚨"},
}


def normalize_content(content: str) -> str:
    """将字面 \\n 转换为真正的换行符"""
    content = content.replace("\\n", "\n")
    content = content.replace("\\t", "\t")
    return content


def parse_content_to_elements(content: str) -> list:
    """
    将 Markdown 内容解析为飞书卡片元素列表。

    解析规则：
    - `## xxx` 或 `### xxx` → markdown 元素（加粗标题）
    - `---` → hr 分隔线元素
    - 普通文本 → markdown 元素
    - 连续空行 → 压缩为一个空行
    """
    content = normalize_content(content)
    lines = content.split("\n")
    elements = []
    current_block = []

    def flush_block():
        """将当前累积的文本块作为一个 markdown 元素输出"""
        if current_block:
            text = "\n".join(current_block)
            # 飞书 markdown 不支持 ## 标题语法，转为加粗
            text = text.replace("## ", "**").replace("### ", "**")
            # 关闭未闭合的加粗
            if text.endswith("**"):
                text = text[:-2]
            # 处理行内的 ## 标题（不在行首的情况）
            import re
            text = re.sub(r'(?<!\*)\*\*(?!\s)', '**', text)
            elements.append({"tag": "markdown", "content": text})
            current_block.clear()

    for line in lines:
        stripped = line.strip()

        # 分隔线 ---
        if stripped == "---":
            flush_block()
            elements.append({"tag": "hr"})
            continue

        # 标题行 ## 或 ###
        if stripped.startswith("## ") or stripped.startswith("### "):
            flush_block()
            title_text = stripped.lstrip("#").strip()
            elements.append({"tag": "markdown", "content": f"**{title_text}**"})
            continue

        # 空行
        if stripped == "":
            if current_block:
                current_block.append("")
            continue

        # 普通文本行
        current_block.append(line)

    flush_block()
    return elements


def build_card(sender: str, title: str, content: str, priority: str) -> dict:
    """构建飞书交互卡片消息（Card JSON 1.0）"""
    config = PRIORITY_CONFIG.get(priority, PRIORITY_CONFIG["normal"])
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 解析内容为多个元素
    body_elements = parse_content_to_elements(content)

    # 添加分隔线和底部信息
    footer_elements = [
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"📤 来自: **{sender}** | 🕐 {now}",
        },
    ]

    all_elements = body_elements + footer_elements

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{config['prefix']} {title}",
                },
                "template": config["template"],
            },
            "elements": all_elements,
        },
    }
    return card


def send_webhook(card: dict, retry: bool = True) -> bool:
    """发送消息到 Webhook，支持重试"""
    data = json.dumps(card).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    max_attempts = 2 if retry else 1
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                WEBHOOK_URL, data=data, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))

            if result.get("code") == 0:
                print("✅ 消息发送成功")
                return True
            else:
                code = result.get("code", "unknown")
                msg = result.get("msg", "unknown error")
                print(f"❌ Webhook 返回错误: code={code}, msg={msg}", file=sys.stderr)

                error_hints = {
                    19021: "签名校验失败，检查 webhook secret",
                    19022: "签名过期，检查系统时间是否同步",
                    19024: "IP 不在白名单，检查网络配置",
                }
                if code in error_hints:
                    print(f"💡 提示: {error_hints[code]}", file=sys.stderr)

                if attempt < max_attempts - 1:
                    print("🔄 1 秒后重试...", file=sys.stderr)
                    time.sleep(1)
                    continue
                return False

        except urllib.error.HTTPError as e:
            print(f"❌ HTTP 错误: {e.code} {e.reason}", file=sys.stderr)
            if attempt < max_attempts - 1:
                print("🔄 1 秒后重试...", file=sys.stderr)
                time.sleep(1)
                continue
        except urllib.error.URLError as e:
            print(f"❌ 网络错误: {e.reason}", file=sys.stderr)
            if attempt < max_attempts - 1:
                print("🔄 1 秒后重试...", file=sys.stderr)
                time.sleep(1)
                continue
        except Exception as e:
            print(f"❌ 未知错误: {e}", file=sys.stderr)
            return False

    return False


def upload_image(path: str) -> str:
    """用已登录的飞书应用上传图片，返回 image_key。

    lark-cli 读文件路径会报 cannot open file，改从标准输入送。
    """
    with open(path, "rb") as fh:
        proc = subprocess.run(
            [
                "lark-cli", "im", "images", "create",
                "--as", "bot",
                "--data", json.dumps({"image_type": "message"}),
                "--file", "image=-",
            ],
            stdin=fh,
            capture_output=True,
        )
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        raise RuntimeError(err.strip() or out.strip() or "图片上传失败")
    key = _find_key(json.loads(out or "{}"))
    if not key:
        raise RuntimeError("上传成功但没有返回 image_key")
    return key


def _find_key(node):
    if isinstance(node, dict):
        if node.get("image_key"):
            return node["image_key"]
        for v in node.values():
            found = _find_key(v)
            if found:
                return found
    return None


def send_image(image_key: str, title: str) -> bool:
    """图片消息发到同一个 webhook 群。带一行标题，避免关键词校验把纯图片丢掉。"""
    body = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [
                        [{"tag": "text", "text": title}],
                        [{"tag": "img", "image_key": image_key}],
                    ],
                }
            }
        },
    }
    return send_webhook(body)


def main():
    parser = argparse.ArgumentParser(description="飞书 Webhook 消息推送")
    parser.add_argument("--sender", required=True, help="发送方标识，如 admin、zhiqi")
    parser.add_argument("--title", required=True, help="消息标题")
    parser.add_argument("--content", default="", help="消息正文，支持 Markdown")
    parser.add_argument("--image", default="", help="要随消息发出的本地图片路径")
    parser.add_argument(
        "--priority",
        choices=["normal", "important", "urgent"],
        default="normal",
        help="优先级：normal（默认）、important、urgent",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印消息内容，不实际发送",
    )

    args = parser.parse_args()

    if args.image:
        if args.dry_run:
            print(json.dumps({"image": args.image, "title": args.title}, ensure_ascii=False))
            return
        try:
            key = upload_image(args.image)
        except Exception as e:
            print(f"❌ 图片上传失败: {e}", file=sys.stderr)
            sys.exit(1)
        success = send_image(key, args.title)
        sys.exit(0 if success else 1)

    if not args.content:
        print("❌ 文本消息需要 --content", file=sys.stderr)
        sys.exit(1)

    card = build_card(args.sender, args.title, args.content, args.priority)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    success = send_webhook(card)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
