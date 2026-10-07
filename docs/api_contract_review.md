# data-api 契约评审意见（T2.11 初稿）

> 编制：造物（wuzao）| 2026-10-07 | v0.1 初稿
> 评审对象：dujun-tech-proposal.md v1.2 §5.2 全部 19 端点（E1–E19）
> 评审视角：产品/消费方（观势 skill 封装的易用性、参数一致性、错误处理完备性）
> 分级：**必须**（阻塞上线，铸码必须修复）/ **建议**（不阻塞但影响易用性，优先修复）

---

## 1. 通用约定评审

### 1.1 响应包络

方案定义：
```json
{"data": [...], "meta": {"rows": n, "next_cursor": "...", "server_ts": "...+08:00"}}
```

**评审意见**：
- ✅ 结构清晰，`meta.rows` + `next_cursor` 满足分页需求
- **建议-1**：`meta` 应增加 `total_count`（可选，仅当查询可枚举总数时返回）。观势 skill 在展示"共 XX 条结果"时需要此字段。若 keyset 分页无法高效获取 total，可返回 `total_count: null` 并文档说明。
- **建议-2**：`server_ts` 格式应明确为 ISO8601 `YYYY-MM-DDTHH:MM:SS+08:00`（非 Unix timestamp）。

### 1.2 错误包络

方案定义：
```json
{"error": {"code": "TABLE_NOT_ALLOWED|BAD_PARAM|TIMEOUT|AUTH", "msg": "..."}}
```

**评审意见**：
- **必须-1**：错误码覆盖不足。建议扩展为：

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| `AUTH_MISSING` | 401 | 未携带 Bearer token |
| `AUTH_INVALID` | 401 | token 无效/过期 |
| `AUTH_INSUFFICIENT` | 403 | token 权限不足（如 read token 尝试写） |
| `TABLE_NOT_ALLOWED` | 403 | 表名不在白名单 |
| `BAD_PARAM` | 400 | 参数格式/类型/范围错误 |
| `NOT_FOUND` | 404 | 资源不存在（如 cognition_id 不存在） |
| `CONFLICT` | 409 | 资源冲突（如 prediction_id 已存在） |
| `TIMEOUT` | 504 | 查询超时（statement_timeout=30s） |
| `RATE_LIMITED` | 429 | 请求频率超限 |
| `INTERNAL` | 500 | 内部错误 |
| `MAINTENANCE` | 503 | 维护中 |

- **必须-2**：错误响应应附带 `request_id`（每个请求的唯一 ID，方便日志排查）。格式：`{"error": {"code": "...", "msg": "...", "request_id": "uuid"}}`

### 1.3 分页游标语义

方案定义：keyset 分页（date/ts+code）

**评审意见**：
- ✅ keyset 分页对时序数据友好（无 OFFSET 性能问题）
- **必须-3**：游标应为不透明字符串（opaque cursor），前端不解析其内部结构。文档需明确：游标格式可能变更，前端只透传。
- **建议-3**：E5 通用查询的 `cursor` 参数命名统一——所有端点用 `cursor`（非 `page_token` / `after` 等别名）。
- **建议-4**：首页请求不传 `cursor`；后续请求传 `meta.next_cursor` 的值。`next_cursor = null` 表示无更多数据。

### 1.4 时间格式

方案定义：ISO8601 `+08:00`

**评审意见**：
- **必须-4**：所有时间输出统一为 `YYYY-MM-DDTHH:MM:SS+08:00`（带时区偏移），DATE 类型输出为 `YYYY-MM-DD`（无时区）。**不允许**出现 `YYYY-MM-DD HH:MM:SS`（空格分隔）或无时区的格式。
- **建议-5**：输入参数（start/end/date）应同时接受 `YYYY-MM-DD` 和 `YYYY-MM-DDTHH:MM:SS+08:00` 两种格式，内部统一处理。

---

## 2. 逐端点评审

### E1 GET /health

| 项 | 意见 |
|----|------|
| 参数 | ✅ 无参数 |
| 响应 | **建议-6**：应包含 `db_connected: bool`、`last_heartbeat`（最近一次 j_heartbeat 时间）、`version`（API 版本号） |
| 错误 | ✅ 200/503 即可 |
| 分级 | — |

### E2 GET /meta/tables

| 项 | 意见 |
|----|------|
| 参数 | `domain` 可选过滤 ✅ |
| 响应 | **建议-7**：返回字段应包含 `units`（单位）、`enums`（枚举值列表）、`description`（中文说明），与 `validation_rules.yaml` 同源 |
| 分级 | — |

### E3 GET /meta/trade_cal

| 项 | 意见 |
|----|------|
| 参数 | `market, start, end` ✅ |
| 响应 | ✅ |
| **建议-8** | 增加 `is_open_today` 便捷字段（当前日期是否交易日），减少观势 skill 侧判断逻辑 |
| 分级 | 建议 |

### E4 GET /meta/instruments

| 项 | 意见 |
|----|------|
| 参数 | `market, type, keyword, code` ✅ |
| **必须-5** | `code` 参数应支持**别名解析**：输入 `KS11` 自动返回 `KOSPI` 的 instrument 信息（查 `instrument_master.aliases`）。这是 lovetrade 迁移后旧码兼容的硬需求（§6.1 代码归一）。文档需明确：`code` 参数同时接受 canonical 码和 aliases |
| **建议-9** | 支持批量查询：`codes=sh600519,sz000001`（逗号分隔），减少请求次数 |
| 分级 | 必须（别名解析） |

### E5 GET /data/{table}

| 项 | 意见 |
|----|------|
| 参数 | `start, end, codes, fields, limit, cursor, order, format` ✅ |
| **必须-6** | `fields` 参数应支持 `*` 通配（默认值），且返回字段顺序稳定（按 DDL 定义顺序）。观势 skill 封装时不传 fields 即返回全部 |
| **必须-7** | `format=csv` 的响应应设置 `Content-Type: text/csv; charset=utf-8` + `Content-Disposition: attachment; filename="{table}_{start}_{end}.csv"` |
| **建议-10** | `order` 参数默认值应为 `desc`（时序数据通常关注最新），文档明确 |
| **建议-11** | `limit` 默认 5000、max 50000 合理，但应在 `meta` 中返回 `limited: true/false` 标记，告知观势是否触顶 |
| 分级 | 必须（fields 通配、CSV header） |

### E6 GET /data/sentiment/latest

| 项 | 意见 |
|----|------|
| 参数 | `n=1` ✅ |
| **建议-12** | 返回应包含 `trend` 字段（与前一交易日对比的涨跌标记），方便观势盘前简报直接引用 |
| 分级 | 建议 |

### E7 GET /data/global/overnight

| 项 | 意见 |
|----|------|
| 参数 | `date` ✅ |
| **必须-8** | "红标新闻计数"在方案中提到但未在响应结构中明确。应定义返回结构：`{data: [{code, name, close, pct, session, news_red_count}], meta: {...}}` |
| **建议-13** | 增加 `futures_latest` 字段（期货盘前最新值，可能比 close 更新），观势盘前简报需要 |
| 分级 | 必须（红标计数结构） |

### E8 GET /data/base_rate

| 项 | 意见 |
|----|------|
| 参数 | `regime, category, horizon, window_end=latest` ✅ |
| **必须-9** | 应与 `base_rate_calibration_spec.md` 口径对齐：返回 `n_samples, hit_rate, stat_json`（含 Wilson CI）、`reliability` 标记。方案 §5.2 仅列参数未列响应字段，需补齐 |
| **必须-10** | `window_end=latest` 语义需明确：返回最新一条 or 最新双口径（滚动90+全历史）两行？建议默认返回双口径，参数 `window_type=rolling_90|full|both` 可过滤 |
| **建议-14** | 返回 `stat_json` 时应解析为结构化 JSON（非字符串），方便观势 skill 直接消费 |
| 分级 | 必须（响应字段定义、双口径） |

### E9 GET /calibration

| 项 | 意见 |
|----|------|
| 参数 | `category, window` ✅ |
| **必须-11** | 应与 `base_rate_calibration_spec.md` 口径对齐：返回 `n, avg_conf_pct, hit_rate, brier`。方案 §5.2 未列响应字段 |
| **建议-15** | `window` 参数格式建议 `YYYY-MM`（单月）或 `YYYY-MM:YYYY-MM`（范围），文档明确 |
| **建议-16** | 增加 `bucket_by=month|confidence` 参数（V1 仅实现 month），为 V2 confidence 分桶预留 |
| 分级 | 必须（响应字段定义） |

### E10 GET /cognition/active

| 项 | 意见 |
|----|------|
| 参数 | `regime, type` ✅ |
| **建议-17** | 返回应包含 `cognition_id`（F/C/H/M 前缀编号）、`version`、`title`、`statement`、`confidence`、`regime_scope`、`updated_at`。文档明确字段列表 |
| 分级 | 建议 |

### E11 GET /cognition/{id}

| 项 | 意见 |
|----|------|
| 参数 | `version`（可选，默认全部版本） ✅ |
| **建议-18** | 返回按 `version DESC` 排序的版本链数组，每个元素含完整字段。方便观势查看认知演变历史 |
| 分级 | 建议 |

### E12 POST /cognition; PUT /cognition/{id}

| 项 | 意见 |
|----|------|
| 参数 | body=认知字段 ✅ |
| **必须-12** | PUT 响应应返回新创建的 version 号（`{"version": 3, "cognition_id": "F-001"}`），观势需确认升版成功 |
| **必须-13** | POST 时 `cognition_id` 由观势传入（F/C/H/M 前缀），API 不自动生成（§10-Q8 冻结：ID 分配权在观势认知库）。若 ID 已存在且 version=1，返回 `CONFLICT` |
| **建议-19** | 请求体应做 schema 校验（必填字段：cognition_id, type, title, statement, confidence），校验失败返回 `BAD_PARAM` + 具体字段错误列表 |
| 分级 | 必须（返回 version、不自动生成 ID） |

### E13 POST /prediction; PUT /prediction/{id}/result; GET /prediction/due

| 项 | 意见 |
|----|------|
| **必须-14** | 三个操作合在一个端点编号不清晰。建议拆分为 E13a `POST /prediction`、E13b `PUT /prediction/{id}/result`、E13c `GET /prediction/due`，在文档中分别列出 |
| **必须-15** | `PUT /prediction/{id}/result` 的请求体应明确：`{result: "hit"|"miss"|"invalid", result_note: "必填改判理由"}`。若 `result_note` 为空，返回 `BAD_PARAM` |
| **必须-16** | `GET /prediction/due` 应支持 `status=pending|expired` 过滤，默认 `pending`。返回按 `check_date ASC` 排序 |
| **建议-20** | `POST /prediction` 响应应包含 `base_rate_ref` 的当前值（若引用了基率），方便观势确认引用时的基率快照 |
| 分级 | 必须（拆分端点、result_note 必填、due 过滤） |

### E14 GET /realtime/quote

| 项 | 意见 |
|----|------|
| 参数 | `codes` ✅ |
| **必须-17** | 应明确缓存策略：15s 缓存期间返回的数据是否带 `cached: true` 标记？建议标记，观势可据此判断数据新鲜度 |
| **建议-21** | 支持 `codes=*` 返回观察池全部（读 watchlist 表），减少两次请求 |
| 分级 | 必须（缓存标记） |

### E15 GET/PUT /watchlist

| 项 | 意见 |
|----|------|
| **必须-18** | PUT 操作应支持批量：`{add: [{code, reason}], remove: [code]}`。单条增删效率太低 |
| **必须-19** | 200 硬校验应在 PUT 响应中体现：若添加后超限，返回 `BAD_PARAM` + `{"current": 198, "requested_add": 5, "limit": 200}` |
| 分级 | 必须 |

### E16 GET /ingest/status

| 项 | 意见 |
|----|------|
| 参数 | `date, table, job` ✅ |
| **建议-22** | 返回应包含 `last_success_ts`（该表/作业最后一次成功时间），方便观势判断数据新鲜度 |
| 分级 | 建议 |

### E17 POST /data/replay/quarantine/{q_id}

| 项 | 意见 |
|----|------|
| **必须-20** | admin token 鉴权，其他 token 返回 `AUTH_INSUFFICIENT` |
| **建议-23** | 响应应包含回放结果（成功写入目标表 or 仍失败+原因） |
| 分级 | 必须（鉴权） |

### E18 POST /data/import/predictions

| 项 | 意见 |
|----|------|
| **必须-21** | 迁移专用端点，应在文档中标注 `deprecated`（迁移完成后下线）。正式写入走 E13 `POST /prediction` |
| **建议-24** | 响应应包含导入统计：`{total: 100, created: 95, skipped: 5, skipped_ids: [...]}` |
| 分级 | 必须（标注 deprecated） |

### E19 GET /docs, /openapi.json

| 项 | 意见 |
|----|------|
| ✅ | FastAPI 自动生成，无额外意见 |

---

## 3. E8/E9 与口径文档对齐性

| 检查项 | base_rate_calibration_spec.md | 方案 v1.2 §5.2 | 对齐状态 |
|--------|------------------------------|-----------------|----------|
| E8 参数 | regime, category, horizon, window_end | regime, category, horizon, window_end=latest | ✅ 一致 |
| E8 响应 | n_samples, hit_rate, stat_json, reliability | 未定义 | ⚠️ 需补齐（必须-9） |
| E8 双口径 | 滚动90+全历史两行 | 未提及 | ⚠️ 需补齐（必须-10） |
| E9 参数 | category, window | category, window | ✅ 一致 |
| E9 响应 | n, avg_conf_pct, hit_rate, brier | 未定义 | ⚠️ 需补齐（必须-11） |
| E9 分桶 | 按月（V1），按 confidence（V2） | 未提及 | ⚠️ 需预留参数（建议-16） |

---

## 4. 观势 skill 封装易用性风险

| # | 风险 | 影响 | 建议 |
|---|------|------|------|
| 1 | **时间格式不一致** | 观势 skill 需处理多种时间格式（DATE vs TIMESTAMPTZ vs ISO8601），增加解析复杂度 | 必须-4：统一输出格式；建议-5：输入宽容解析 |
| 2 | **code 格式不统一** | A股 `sh600519`、港股 `hk00700`、美股 `AAPL`、指数 `sh000001`——观势 skill 需维护格式映射 | **建议-25**：E4 增加 `code_format=canonical|display` 参数，`display` 返回人类可读格式（如"贵州茅台"、"沪深300"） |
| 3 | **错误码不够细** | `BAD_PARAM` 过于笼统，观势 skill 难以针对性处理（如区分"参数缺失"vs"参数类型错"vs"参数范围越界"） | 必须-1：扩展错误码 |
| 4 | **分页游标不透明** | 若游标内部结构暴露（如 `date=2026-10-01;code=sh600519`），观势可能自行拼接而非透传 | 必须-3：文档明确游标不透明 |
| 5 | **E13 三合一** | POST/PUT/GET 合在一个端点编号，OpenAPI 文档中不易发现三个操作 | 必须-14：拆分 |
| 6 | **base_rate 的 horizon 反推** | 若不加显式列，观势 skill 消费 base_rate 时无法直接过滤 horizon | 待观势确认-2 |

---

## 5. 评审意见汇总（按分级）

### 必须（14 条，阻塞上线）

| 编号 | 端点 | 意见 |
|------|------|------|
| 必须-1 | 通用 | 扩展错误码（11 种）+ request_id |
| 必须-2 | 通用 | 错误响应附带 request_id |
| 必须-3 | 通用 | 游标不透明，文档明确 |
| 必须-4 | 通用 | 时间输出格式统一 ISO8601 +08:00 |
| 必须-5 | E4 | code 参数支持别名解析 |
| 必须-6 | E5 | fields 支持 `*` 通配 |
| 必须-7 | E5 | CSV 响应 Content-Type + filename |
| 必须-8 | E7 | 红标新闻计数响应结构明确 |
| 必须-9 | E8 | 响应字段补齐（n_samples, hit_rate, stat_json, reliability） |
| 必须-10 | E8 | 双口径（滚动90+全历史）默认返回 |
| 必须-11 | E9 | 响应字段补齐（n, avg_conf_pct, hit_rate, brier） |
| 必须-12 | E12 | PUT 返回新 version 号 |
| 必须-13 | E12 | POST 不自动生成 cognition_id |
| 必须-14 | E13 | 拆分为 E13a/E13b/E13c |
| 必须-15 | E13b | result_note 必填 |
| 必须-16 | E13c | 支持 status 过滤 |
| 必须-17 | E14 | 缓存标记 cached |
| 必须-18 | E15 | PUT 支持批量 |
| 必须-19 | E15 | 200 硬校验响应 |
| 必须-20 | E17 | admin token 鉴权 |
| 必须-21 | E18 | 标注 deprecated |

### 建议（16 条，优先修复）

| 编号 | 端点 | 意见 |
|------|------|------|
| 建议-1 | 通用 | meta 增加 total_count |
| 建议-2 | 通用 | server_ts 格式明确 |
| 建议-3 | 通用 | cursor 参数命名统一 |
| 建议-4 | 通用 | 首页不传 cursor，next_cursor=null 表示结束 |
| 建议-5 | 通用 | 输入时间格式宽容 |
| 建议-6 | E1 | 增加 db_connected/version |
| 建议-7 | E2 | 返回 units/enums/description |
| 建议-8 | E3 | 增加 is_open_today |
| 建议-9 | E4 | 支持批量 codes |
| 建议-10 | E5 | order 默认 desc |
| 建议-11 | E5 | meta.limited 标记 |
| 建议-12 | E6 | 增加 trend 字段 |
| 建议-13 | E7 | 增加 futures_latest |
| 建议-14 | E8 | stat_json 返回结构化 JSON |
| 建议-15 | E9 | window 参数格式明确 |
| 建议-16 | E9 | 预留 bucket_by 参数 |
| 建议-17~24 | E10~E16 | 各端点字段增强 |
| 建议-25 | 通用 | code_format 参数 |

---

## 附录 B：端点编号重排建议

当前 E13 包含三个操作，建议重排为：

| 原编号 | 建议编号 | 方法与路径 |
|--------|---------|-----------|
| E13 (POST) | E13 | POST /prediction |
| E13 (PUT) | E14 | PUT /prediction/{id}/result |
| E13 (GET) | E15 | GET /prediction/due |
| 原 E14 | E16 | GET /realtime/quote |
| 原 E15 | E17 | GET/PUT /watchlist |
| ... | ... | 后续顺延 |

或保持 E13 编号但在 OpenAPI 中拆分为三个独立 operationId。
