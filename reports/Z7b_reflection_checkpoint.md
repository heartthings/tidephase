# Z7b 反思层 checkpoint

> 2026-10-10 铸码 · 硬截止 21:30 · 优先级 > Z7 P1

## 摘要

| 项 | 状态 | 证据 |
|----|------|------|
| V004 迁移 | ✅ 已应用 | `\d reflection` 见下 |
| POST /reflection | ✅ 200 | single + records 两种 body |
| GET /reflection/recent | ✅ 200 | days=30 默认 |
| GET /reflection/action_items | ✅ 200 | status=open/done/waived/all |
| registry 记账 | ✅ | j_reflect_daily enabled=false |
| smoke 数据清理 | ✅ | DELETE 3 rows, remaining=0 |

## V004 应用证据

> 注：任务原文要求 V003，但 V003 已被 base_rate 迁移占用（untracked 文件 + 已应用到 DB），故使用 V004。

### \d reflection 关键行

```
 id              | bigint | PK (nextval reflection_id_seq)
 decision_id     | text   | NOT NULL, FK → prediction(prediction_id)
 closed_at       | timestamptz
 quadrant        | text   | CHECK IN (right_right, right_luck, wrong_right, wrong_wrong)
 error_stage     | text   | CHECK IN (regime, cognition_ref, data_premise, expression, capability_circle, noise)
 lesson_text     | text
 lesson_kind     | text   | CHECK IN (candidate_cognition, rule_revision, none)
 action_item     | text
 action_status   | text   | NOT NULL DEFAULT 'open', CHECK IN (open, done, waived)
 actor           | text
 created_at      | timestamptz | NOT NULL DEFAULT now()
```

### 口径注

观势规格（cognition/README.md §8）写 `prediction.id`，实际 PK 列名 = `prediction_id`。FK 落 `prediction(prediction_id)`，已在报告注明。

### prediction 增列

```
 reasoning_trace | jsonb | 预测出口必填 · 观势侧写入 · 2026-10-10规格增补
 alternatives    | jsonb | 预测出口必填 · 观势侧写入 · 2026-10-10规格增补
```

### 权限

| 角色 | reflection 表 | reflection_journal 视图 | sequence |
|------|--------------|------------------------|----------|
| duser_reader | SELECT | SELECT | — |
| duser_d12writer | INSERT, SELECT | — | USAGE, SELECT |

### schema_migrations 登记

```
 V004 | 反思层: reflection表 + journal视图 + prediction增列(reasoning_trace/alternatives)
```

## 三端点 curl 状态码

| 端点 | 场景 | HTTP | code |
|------|------|------|------|
| POST /reflection | single record | 200 | — |
| POST /reflection | records array | 200 | — |
| POST /reflection | bad decision_id | 404 | REF_DECISION_NOT_FOUND |
| POST /reflection | bad enum | 400 | REF_ENUM |
| GET /reflection/recent?days=30 | 正常 | 200 | — |
| GET /reflection/action_items?status=open | 正常 | 200 | — |
| GET /reflection/action_items?status=all | 正常 | 200 | — |

## registry 行

```
 job_name       | domain | schedule_cron    | owner    | enabled | note
 j_reflect_daily| D12    | 45 18 * * 1-5   | guanshi  | false   | 仅记账；实际触发=guanshi workspace qwenpaw cron
```

## 并行冲突纪律遵守

| 规则 | 遵守 |
|------|------|
| 禁触 dworker/adapters/longhu.py | ✅ 未触碰 |
| 禁触 dworker/core/rate_limiter.py | ✅ 未触碰 |
| 禁触 configs/rate_limits.yaml | ✅ 未触碰 |
| git add 点名文件 | ✅ `git add data_api/main.py db/migrations/V004__reflection_layer.sql reports/Z7b_reflection_checkpoint.md` |
| data_api/main.py 追加式 | ✅ 仅在 E19 注释后、Error handlers 前插入新区块 |
| python3 -c "import data_api.main" 验证 | ✅ OK (仅 pre-existing SyntaxWarning) |

## 任务 4 衔接项（Z7 后续 P1-2 注意）

D12 prediction 写端点 `POST /d12/prediction` payload 须接受 `reasoning_trace` / `alternatives` 两新列（V004 已建）。当前 INSERT 语句未含此二列——**Z7 P1-2 需补**：

```python
# data_api/main.py create_prediction() 需追加:
#   reasoning_trace=body.get("reasoning_trace")  # JSONB
#   alternatives=body.get("alternatives")         # JSONB
# INSERT SQL 需加对应两列
```

openapi 导出时把本波三端点一并纳入。

## 冲突风险点

`data_api/main.py` 本波改动区域：E19 注释块与 Error handlers 之间（约 L713-L860）。Z7 后续若改 D12 写端点区域（约 L540-L700），**无重叠风险**。若 Z7 也动 Error handlers 或 E19 注释块附近，需 rebase 注意。

## commit

```
 [Z7b] 反思层: V004 + API三端点 + registry记账
```
