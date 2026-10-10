# Z7c 反思层证据包 Checkpoint

**日期**: 2026-10-10 20:05  
**铸码实装** | 督军派单 · 观势 19:45 来单增补2  

---

## 任务范围

合并 Z7b（反思层基础设施）+ Z7c（反思层证据包）一次落地。

### 硬约束
- 迁移版本号: V004（V003 已被 D12 基率视图占用）
- 并行冲突纪律: 未触 longhu.py / rate_limiter.py / rate_limits.yaml
- 诚实纪律: 数据缺失 → gaps[] 记录, 不做伪填充

---

## Task A: V004 DDL ✅

### 已应用变更

| 对象 | 操作 | 说明 |
|------|------|------|
| `reflection` | ALTER + CREATE | 新增 `evidence_refs JSONB`, `evidence_summary TEXT` |
| `reflection` | INDEX ×3 | `(decision_id)`, `(closed_at DESC)`, `(action_status)` |
| `reflection_journal` | VIEW RECREATE | 含 evidence 两列 |
| `regime_daily` | CREATE TABLE | 相态日序列唯一可查源 (date PK) |
| `job_registry` | ALTER | 新增 `config JSONB` |
| `prediction` | 已有 | `reasoning_trace`, `alternatives` (Z7b 已建) |
| GRANTs | 仿 V002 风格 | reader: SELECT on reflection/journal/regime_daily; d12writer: INSERT/SELECT + USAGE |
| schema_migrations | UPDATE note | 完整描述 V004 范围 |

### \d reflection 关键行
```
evidence_refs     | jsonb
evidence_summary  | text
idx_reflection_decision_id   btree (decision_id)
idx_reflection_closed_at     btree (closed_at DESC)
idx_reflection_action_status btree (action_status)
```

### \d regime_daily
```
date        | date PK
regime      | text
sub_regime  | text
quadrant    | jsonb
evidence    | jsonb
actor       | text
source      | text
ingest_ts   | timestamptz default now()
```

---

## Task B: GET /data/reflection_pack ✅

**位置**: `/data/base_rate` 之后, `/data/{table}` 之前 (避免通配拦截)

**入参**: decision_id (必填), window_start/window_end (可选), section (可选逗号分隔)

**返回结构**:
```json
{
  "decision_id": "...",
  "decision": { /* prediction 全行含 reasoning_trace/alternatives */ },
  "window": { "decision_date", "check_date", "trade_days[]" },
  "sections": {
    "S1_snapshot_at_decision": { index_daily, sentiment_daily, sector_concentration, volume, global_overnight, cognition_refs },
    "S2_falsify_actuals": { metric, routed_table, routed_column, series, threshold_check },
    "S3_attribution": { regime_daily, ingest_log, quarantine, verify_diff, falsify_definition, cognition_history, amplitude, news_critical },
    "S4_base_rate_peer": [ /* base_rate rows */ ]
  },
  "gaps": [ { section, code, reason, affected } ],
  "route_map_version": "2026-10-10.1",
  "generated_at": "..."
}
```

### 冒烟结果

| 测试 | decision_id | 状态码 | sections | gaps 数 | 关键观察 |
|------|-------------|--------|----------|---------|----------|
| ① 标准路由 | P-20261010-001 | 200 | S1-S4 全 | 6 | metric=stock_daily.pct → routed_table=stock_daily ✅ |
| ② category 兜底 | P-336 | 200 | S1-S4 全 | 6 | metric 空 → category_default[continuation]=sector.pct ✅ |

**Gaps 诚实记录**:
- S1: SENTIMENT_DAILY_EMPTY, SECTOR_DAILY_EMPTY, VOLUME_ERROR (数据尚未回填到对应日期)
- S3: REGIME_DAILY_EMPTY (表刚建, 观势尚未写入)
- S4: REGIME_MISSING (regime_at_create 全空), BASE_RATE_EMPTY (无匹配基率)

---

## Task C: route_map 配置化 ✅

### 存储
- `job_registry.config->'route_map'` where job_name='j_reflect_daily'
- 进程内缓存 TTL 60s

### 端点

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | /reflection_pack/route_map | require_read | 读回当前 route_map |
| PATCH | /reflection_pack/route_map | require_write | 整体替换, 逐条校验 table/column ∈ information_schema |

### DEFAULT_ROUTE_MAP 初值
- 12 条 metric_routes (含 dragon_tiger → dt_pool alias 兼容)
- 6 条 category_default (continuation/phase_change/spillover/reversal/情绪/产业)

### 冒烟结果

| 测试 | 状态码 | 结果 |
|------|--------|------|
| GET | 200 | version=2026-10-10.1, 12 routes, 6 defaults |
| PATCH (valid) | 200 | version bumped to 2026-10-10.2 |
| PATCH (invalid table) | 400 | code=ROUTE_MAP_INVALID, "nonexistent_table.id not found" |

---

## Task D: POST /reflection 扩展 + registry 记账 ✅

### POST /reflection 扩展
- 新增接受 `evidence_refs` (JSONB), `evidence_summary` (TEXT)
- body 缺 evidence_refs → 响应带 `warning: "NO_EVIDENCE_REFS"`

### job_registry 记账行
```sql
job_name = 'j_reflect_daily'
domain = 'D12'
schedule_cron = '45 18 * * 1-5'
owner = 'guanshi'
enabled = false  -- 刻意: dsched 无 handler, 避免 MISS 噪音
config = '{"route_map": {...}}'
note = '仅记账; 实际触发=guanshi workspace qwenpaw cron; 流程=先GET reflection_pack组包→喂观势会话→POST reflection(含evidence_refs)'
```

### 冒烟结果

| 测试 | 状态码 | 结果 |
|------|--------|------|
| POST with evidence_refs | 200 | inserted_ids=[4], 无 warning |
| POST without evidence_refs | 200 | inserted_ids=[5], warning="NO_EVIDENCE_REFS" |
| Cleanup | DELETE 2 | actor='smoke_test' 已清除 |

---

## 四端点状态码汇总

| 端点 | 方法 | 状态码 | 备注 |
|------|------|--------|------|
| /data/reflection_pack | GET | 200 | 两条冒烟均成功 |
| /reflection_pack/route_map | GET | 200 | 返回完整 route_map |
| /reflection_pack/route_map | PATCH | 200/400 | valid→200, invalid→400 |
| /reflection | POST | 200 | evidence_refs 可选, 缺则 warning |

---

## 工单与库内现实不符之处

1. **V003 冲突已规避**: 工单提到 V003 被 D12 占用, Z7b 已正确使用 V004, 本波无冲突。
2. **dragon_tiger → dt_pool**: 工单已注明口径差异, route_map 用 alias 兼容。
3. **index_daily codes**: 工单写"先探明再写死", 实际探明为 `sh000001, sh000016, sh000300, sh000688, sz399001, sz399006`, 已写死。
4. **regime_at_create 全空**: 329 行 prediction 全 NULL, S4 退化为同 category 全 regime, 符合工单预期。
5. **sentiment_daily/sector_daily 数据缺口**: 10 月中旬数据尚未回填, gaps 如实记录, 无伪填充。

---

## Commit

```
[Z7c] 反思层证据包: V004 + reflection_pack + route_map配置化 + POST /reflection 扩列
```

**Commit hash**: 37af45d

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| db/migrations/V004__reflection_layer.sql | UPDATE | 完整 DDL (Z7b+Z7c) |
| data_api/reflection_pack.py | CREATE | 证据包组装模块 (S1-S4 + route_map) |
| data_api/main.py | EDIT | 新增 reflection_pack/route_map 端点, 扩展 POST /reflection |
| reports/Z7c_reflection_pack_checkpoint.md | CREATE | 本报告 |

---

**铸码 · 2026-10-10 20:05**

---

## Z7c-fix 整改段（2026-10-10 23:00 督军验收单）

**Commit**: b422c35 `[Z7c-fix] 整改三件: FAIL-1 空metric兜底补发gap + 整改-3 prediction ORDER BY自适应 + 部署生效`

### FAIL-1（闸门c·P0）：空 metric 兜底补发 FALSIFY_METRIC_MISSING gap

**根因**: `_resolve_metric_route` 的 `if not metric:` 分支，兜底命中时直接 `metric = fallback` 静默降级，未发 gap。

**修复 diff**:
```diff
+        # Z7c-fix: 兜底命中也必须显式记录 gap，绝不静默降级
+        gaps.append({"section": section, "code": "FALSIFY_METRIC_MISSING",
+                     "reason": f"metric empty, fell back to category_default['{category}']='{fallback}'",
+                     "affected": "S2"})
         metric = fallback
```

**复测输出**:
```
gap codes: ['SECTOR_DAILY_EMPTY', 'VOLUME_QUERY_ERROR', 'FALSIFY_METRIC_MISSING', 'REGIME_DAILY_EMPTY', 'REGIME_MISSING']
FALSIFY_METRIC_MISSING present: True
  detail: {"section": "S2", "code": "FALSIFY_METRIC_MISSING", "reason": "metric empty, fell back to category_default['continuation']='sector.pct'", "affected": "S2"}
S2 routed_table: sector_daily
S2 routed_column: pct
```
✅ 通过。

### 整改-2（P0·部署缺口）：B5 commit 生效

**操作**: `docker restart market-api` → healthy → 复测三项。

**复测输出**:
1. P-336 gaps 含 FALSIFY_METRIC_MISSING ✅ + 量能 gap 变为 VOLUME_QUERY_ERROR（B5 语义）✅
2. 冒烟决策 P-SMOKE-Z7CFIX（falsify.metric='bad;metric'）→ FALSIFY_METRIC_INVALID ✅, S2 routed_table=None ✅
3. 隔夜 global_daily 按 trade_cal 取前一交易日（B5 逻辑，代码已在 2319e65 中，本次随容器重启生效）

### 整改-3（P2）：/data/prediction?limit=1 → 500

**根因**: 通用 `/data/{table}` handler 硬编码 `ORDER BY date[, code]`，prediction 表无 date 列。

**修复**: 新增 `_detect_table_sort()` 函数，通过 information_schema 探测表列，自适应选择排序列（date → created_at → ts → pub_ts → 不排序），结果缓存 5min。同步修复日期过滤、游标分页、next_cursor 计算。

**复测输出**:
```
TEST 3a: /data/prediction?limit=1 → HTTP 200, rows=1, prediction_id=P-SMOKE-Z7CFIX, created_at=2026-10-10T22:59:05
TEST 3b: /data/index_daily?limit=1 → HTTP 200, rows=1, date=2026-10-09 code=sz399006
```
✅ 通过，回归无影响。

### 冒烟清理

```
prediction deleted: 1 rows (actor='smoke_test')
reflection deleted: 0 rows
prediction smoke_test remaining: 0
reflection smoke_test remaining: 0
guanshi reflection rows: 7 (未触碰)
```

---

**铸码 · 2026-10-10 23:00 整改完成**
