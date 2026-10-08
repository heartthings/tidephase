# 凭证配置文档

## 唯一事实源

所有 API/DB 凭证统一存储在 `configs/secrets.yaml`。

### 档位说明

| 档位 | 配置路径 | 用途 |
|------|----------|------|
| admin | `api.bearer_token_admin` | data-api 管理端（全权限） |
| write | `api.bearer_token_write` | data-api 写入端 |
| read | `api.bearer_token_read` | data-api 只读端 |

### DB 凭证

| 用户 | 配置路径 | 用途 |
|------|----------|------|
| duser_writer | `database.duser_writer_password` | 采集写入 |
| duser_reader | `database.duser_reader_password` | data-api 只读查询 |
| duser_d12writer | `database.duser_d12writer_password` | D+12 写入 |
| duser_admin | `database.duser_admin_password` | 管理端 |

### 龙虎凭证

| 账号 | 配置路径 | 状态 |
|------|----------|------|
| 3167791 | `longhu.account_3167791` | token 轮换待梁总 |
| 3965820 | `longhu.account_3965820` | token 轮换待梁总 |
| Emotion | `longhu.emotion_device_id` | token 轮换待梁总 |

## 安全规则

1. **严禁在文档中写明文 token**：只写配置路径和档位
2. **严禁硬编码**：代码中必须从 `configs/secrets.yaml` 读取
3. **已废弃**：`data-api-read-2026-market` 字符串已废弃（HTTP 401），请使用 `configs/secrets.yaml` 的 `api.bearer_token_read`

## 读取方式

```python
import yaml
from pathlib import Path

secrets = yaml.safe_load(Path("configs/secrets.yaml").read_text())
read_token = secrets["api"]["bearer_token_read"]
```
