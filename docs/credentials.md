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
| 3167791 | `longhu.account_3167791` | ✅ 实测 errcode=0 有效（Z7 T-R1 外置） |
| 3965820 | `longhu.account_3965820` | ✅ 实测 errcode=0 有效（Z7 T-R1 外置） |
| Emotion | `longhu.emotion_device_id` | ✅ 实测 errcode=0 有效（Z7 T-R1 外置） |
| entrust_purchase | `longhu.entrust_purchase` | ✅ 实测 errcode=0 有效 |
| theme_info | `longhu.theme_info_token` | ✅ 实测 errcode=0 有效 |

### 龙虎限速（Z7 梁总 10-10 裁决）

- **人为限速已删除**：0.5rps / 日≤1500 限制不再执行
- **保留反应式熔断**：429/403 → 全源熔断 30min（`longhu.py _trigger_circuit_breaker`）
- 凭证以 lovetrade-service Java 代码为准，configs/secrets.yaml 三套实测 errcode=0

### YouZiDongXiang / DongXiang 结论（Z7）

- 实测 auth 有效（errcode=0），但服务端 DongXiang 数据恒空
- **D4 资金面维持东财链**（eastmoney adapter），不再依赖龙虎 DongXiang
- 龙虎 DongXiang 端点保留代码面，待供应商侧有数据后自动恢复

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
