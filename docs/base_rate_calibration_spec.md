# base_rate / calibration 口径规格书（T2.11 初稿）

> 编制：造物（wuzao）| 2026-10-07 | v0.1 初稿，待观势会签
> 依据：dujun-tech-proposal.md v1.2（§3.12 D12 表、§5.2 E8/E9/E13、§6.4 lovetrade 迁移、§10-Q2/Q10）+ data-layer-spec.md v2.0（M-005 基率、M-002 校准）+ guanshi-review-20261007.md
> 状态：**初稿 · 待观势会签后冻结**。铸码 T3.1 以此为准实装。
> 术语与方案 v1.2 保持一致，不发明新名词。

---

## 1. base_rate 口径

### 1.1 维度枚举

#### 1.1.1 regime（市场状态/相态）

| 枚举值 | 含义 | 判定来源 |
|--------|------|----------|
| `trending_up` | 上升趋势 | 观势规则引擎判定，写入 `prediction.regime_at_create`；`base_rate.stat_json.sub_labels` 可存分化子态 |
| `trending_down` | 下降趋势 | 同上 |
| `oscillation` | 震荡 | 同上 |
| `critical` | 临界态 | 同上 |
| `phase_transition` | 相变态 | 同上 |
| `news_shock` | 消息冲击 | 同上 |

**判定来源**：regime 由观势规则引擎在创建 prediction 时判定并写入 `regime_at_create`，base_rate 聚合作业（`j_base_rate`）从 `prediction` 表聚合，**不自行判定 regime**。分化子态标签（如有）存 `base_rate.stat_json.sub_labels`（字符串数组）。

**待观势确认-1**：regime 是否需要在 base_rate 聚合时按 `sentiment_daily.sentiment_score` 或 `zt_pool` 指标做二级细分（如 trending_up + 高情绪 / trending_up + 低情绪）？当前方案仅保留 `sub_labels` 兜底，建议 V1 不做二级细分，待数据积累后 V2 再议。

#### 1.1.2 category（认知/预测类别）

衔接观势认知库 F/C/H/M 编号体系，与 `prediction.category` 枚举一致：

| 枚举值 | 含义 | 对应认知库前缀 |
|--------|------|----------------|
| `地缘` | 地缘政治类预测 | F（Falsifiable 可证伪认知） |
| `全球` | 全球市场联动类 | C（Coupling 耦合认知） |
| `产业` | 产业/行业类 | H（Heuristic 启发式认知） |
| `政策` | 政策/监管类 | M（Meta 元认知） |
| `业绩` | 业绩/财报类 | — |
| `情绪` | 情绪/打板类 | — |
| `资金` | 资金面类 | — |

**说明**：F/C/H/M 前缀编号是 `cognition.cognition_id` 的编号体系（宪法层，不可重排，§10-Q8 冻结），`prediction.category` 是预测的分类维度。两者通过 `prediction.conditions`（JSONB，引用的认知 ID 列表）关联。base_rate 按 `prediction.category` 聚合，不直接按 cognition_id 聚合。

#### 1.1.3 horizon（预测窗口）

| 枚举值 | 含义 | 验证日计算 |
|--------|------|-----------|
| `T1` | 次日（1 个交易日） | `check_date = created_at + 1 交易日` |
| `T3` | 3 个交易日内 | `check_date = created_at + 3 交易日` |
| `T5` | 5 个交易日内 | `check_date = created_at + 5 交易日` |
| `W1` | 1 周（5 个自然日/下一个交易日） | `check_date = created_at + 7 自然日内的首个交易日` |

**待观势确认-2**：`horizon` 在 `prediction` 表中未作为显式字段存在，当前由 `check_date - created_at` 反推。建议在 `prediction` 表增加 `horizon` 列（V00X migration），避免反推歧义（如 W1 与 T5 在长节假日可能重合）。若不加列，需在聚合作业中明确反推规则并写入 `base_rate.stat_json`。

### 1.2 聚合窗口 window 语义

base_rate 表（`base_rate`）按 `(regime, category, horizon, window_end)` 为 PK，支持双口径：

| 口径 | window_end | window_start | 说明 |
|------|-----------|-------------|------|
| **滚动 90 交易日** | 最近一个周五（或最新交易日） | window_end 往前推 90 个交易日 | 反映近期基率，对 regime 变化敏感 |
| **全历史** | 最近一个周五（或最新交易日） | 最早有数据之日起 | 反映长期基率，样本量大但滞后 |

**聚合频率**：`j_base_rate` 每周五 18:00 运行（收盘后），也可由 prediction 回写事件触发增量重算。

**输出约定**：E8 端点 `GET /data/base_rate?regime=&category=&horizon=&window_end=latest` 默认返回最新窗口、双口径两行。若需历史窗口序列，传 `window_end` 范围。

### 1.3 n / hit_rate 判定规则

#### 1.3.1 样本定义

`n_samples` = 在 `(regime, category, horizon, window_start, window_end)` 范围内，`result IN ('hit', 'miss')` 的 prediction 行数。

**排除**：
- `result = 'pending'`（未到期/未验证）——不计入 n
- `result = 'invalid'`（人工标记无效）——不计入 n
- `result = 'expired'`（超期未验证，§3 边界情况）——**待观势确认-3**：expired 是否计入 n 的分母？建议 V1 不计入（与 invalid 同等对待），但 `stat_json` 记录 expired 数量供审计。

#### 1.3.2 hit_rate 判定

```
hit_rate = COUNT(result='hit') / NULLIF(COUNT(result IN ('hit','miss')), 0)
```

**falsify 自动判定**（§10-Q10 冻结）：
- `j_pred_writeback`（17:30）按 `prediction.falsify` JSONB 自动判定：
  - `falsify.metric`：从本库取数的指标名（如 `stock_daily.pct`、`sentiment_daily.promote_rate`）
  - `falsify.threshold`：阈值
  - `falsify.direction`：`above` / `below` / `equals`
- 自动判定结果写入 `prediction.result`（hit/miss），`checked_at = now()`

**人工改判覆盖优先级**（§10-Q10 冻结）：
- 观势经 `PUT /prediction/{id}/result` 人工改判，覆盖自动判定
- 改判时 `result_note` 必填改判理由
- **人工改判优先**：若已有 `result_note`（非 NULL），`j_pred_writeback` 不覆盖该行
- 改判后 base_rate 需在下次 `j_base_rate` 运行时重算（非实时）

#### 1.3.3 hit_rate 的置信度标注

`base_rate.stat_json` 应包含：
```json
{
  "n_hit": 42,
  "n_miss": 18,
  "n_expired": 3,
  "n_pending": 5,
  "hit_rate": 0.70,
  "wilson_ci_95": [0.56, 0.81],
  "sub_labels": ["high_sentiment"]
}
```

### 1.4 样本不足时的输出约定

| 条件 | 处理方式 |
|------|----------|
| `n_samples < 5` | E8 返回数据行，但附加 `"reliability": "low"` 标记；hit_rate 仍计算但附带 Wilson 95% CI |
| `n_samples < 20` | `"reliability": "medium"` |
| `n_samples >= 20` | `"reliability": "high"` |
| `n_samples = 0` | 不返回该行（或返回 `hit_rate: null`，`reliability: "none"`） |

**待观势确认-4**：样本不足阈值（5/20）是否合适？观势规则引擎消费 base_rate 时，是否需要对 `reliability=low` 的基率做降权或拒绝使用？

---

## 2. calibration 口径

### 2.1 calibration_view 计算定义

方案 v1.2 §3.14 已定义 `calibration_view`：

```sql
CREATE VIEW calibration_view AS
SELECT category,
       date_trunc('month', created_at)::date AS window,
       COUNT(*) AS n,
       AVG(confidence_pct) AS avg_conf_pct,
       SUM((result='hit')::int)::float
         / NULLIF(SUM((result IN ('hit','miss'))::int),0) AS hit_rate,
       AVG(power(confidence_pct/100.0 - (result='hit')::int, 2)) AS brier
FROM prediction
WHERE result IN ('hit','miss')
GROUP BY 1, 2;
```

**字段定义**：

| 字段 | 计算 | 说明 |
|------|------|------|
| `category` | 分组键 | 预测类别（同 base_rate.category 枚举） |
| `window` | `date_trunc('month', created_at)::date` | 按月分桶（自然月） |
| `n` | `COUNT(*)` | 该月该类别已判定（hit/miss）的 prediction 数 |
| `avg_conf_pct` | `AVG(confidence_pct)` | 平均置信度（0-100 整数，与 prediction.confidence_pct 同域） |
| `hit_rate` | 命中数 / NULLIF(命中+未命中, 0) | 实际命中率（0-1） |
| `brier` | `AVG((confidence_pct/100.0 - hit::int)²)` | Brier 分数，越低越好；0=完美校准，0.25=无技能（二分） |

### 2.2 confidence 字段取值域

- `prediction.confidence_pct`：`INT NOT NULL CHECK (confidence_pct BETWEEN 0 AND 100)`
- 语义：观势创建 prediction 时对该预测的主观置信度（百分比整数）
- 与 `cognition.confidence`（DOUBLE PRECISION, 0-1）不同——cognition 是认知的置信度（0-1 浮点），prediction 是预测的置信度（0-100 整数）。**两者不混用，calibration 只消费 prediction.confidence_pct**。

### 2.3 Brier 分数公式

标准 Brier Score：

```
BS = (1/N) * Σ(p_i - o_i)²
```

其中：
- `p_i = confidence_pct_i / 100.0`（预测概率，0-1）
- `o_i = 1 if result='hit' else 0`（实际结果，二值）
- 范围：[0, 1]，0=完美，0.25=随机（二分情形基线）

**calibration_view 的 `brier` 字段**即为上述公式的按月+按类别分组计算。

### 2.4 分桶策略

**当前方案**：按月分桶（`date_trunc('month')`），不做 confidence 分桶。

**建议增强（V2）**：增加 confidence 十分桶或 5 档分桶，用于绘制校准曲线（reliability diagram）：

| 方案 | 桶 | 每桶样本量要求 | 适用 |
|------|----|---------------|------|
| **5 档**（建议 V2 默认） | [0,20), [20,40), [40,60), [60,80), [80,100] | ≥10/桶 | 样本量少时更稳健 |
| 十分桶 | [0,10), [10,20), ..., [90,100] | ≥5/桶 | 样本量充足时更精细 |

**V1 建议**：保持按月分桶（与方案 v1.2 一致），在 `E9 /calibration` 端点增加 `bucket_by=month|confidence` 参数，V1 仅实现 `month`，`confidence` 分桶待数据积累后 V2 开放。

**待观势确认-5**：V1 是否接受仅按月分桶？calibration 的消费场景是否需要按 confidence 分桶绘制校准曲线？

### 2.5 窗口滚动语义

- `calibration_view` 为普通 VIEW（非物化），每次查询实时计算
- E9 端点 `GET /calibration?category=&window=` 参数：
  - `category`：可选，过滤类别
  - `window`：可选，格式 `YYYY-MM`（单月）或 `YYYY-MM:YYYY-MM`（范围），默认最近 12 个月
- 滚动语义：自然月滑动，不做交易日窗口（与 base_rate 的 90 交易日窗口不同——calibration 关注长期校准趋势，月度粒度足够）

---

## 3. 历史资产衔接（lovetrade catalyst_* 3,636 行）

### 3.1 迁移范围

lovetrade MySQL `catalyst_impacts` / `catalyst_predictions` / `catalyst_system_states` / `catalyst_active_messages` 共 3,636 行（§6.4、§10-Q13 冻结），含 `verified_date` / `actual_outcome` 已闭环记录。

### 3.2 迁移映射

| lovetrade 表 | 目标表 | 映射要点 |
|-------------|--------|----------|
| `catalyst_predictions` | `prediction` | prediction_id 按 `P-YYYYMMDD-###` 规则以原 `date` 重发；`statement` ← 预测陈述字段；`category` ← 按 lovetrade 分类映射至 7 枚举；`confidence_pct` ← 置信度字段（若为 0-1 浮点则 ×100 取整）；`check_date` ← 验证日期；`regime_at_create` ← system_state 关联；`result` ← 由 `actual_outcome` 映射为 hit/miss；`falsify` ← 构建 JSONB（若原始无此字段则根据 actual_outcome 反推） |
| `catalyst_impacts` | `prediction`（或独立 impact 归档列） | impact 语境字段（impact_level/impact_label/system_state_before/after/lifecycle_stage/decay_*/global_coupling 等）JSONB 归档随行保留；建议存入 `prediction.conditions` 或新增 `extra_json` 列 |
| `catalyst_system_states` | `base_rate.stat_json` 参考 | 系统状态快照，不直接入表，但作为 regime 判定的历史参考 |
| `catalyst_active_messages` | 不迁入 D12 | 消息类数据迁入 D10 `market_messages`（§11.5 映射） |

### 3.3 冷启动统计

迁移完成后，3,636 行历史 prediction 参与 base_rate 统计：
- 这些行的 `source = 'lovetrade-mysql'`（行级标记）
- `ingest_log` 注记 `trigger=migration`
- base_rate 聚合作业 **不区分新旧数据**，统一聚合——历史资产与新增 prediction 同口径参与统计

### 3.4 口径不一致时的处理

| 不一致类型 | 处理方式 |
|-----------|----------|
| lovetrade 的 category 无法映射至 7 枚举 | 映射至最接近类别，`result_note` 标注 `migrated-from-lovetrade, original_category=XXX` |
| lovetrade 的 confidence 为 NULL | `confidence_pct` 设 50（中性默认），`result_note` 标注 |
| lovetrade 的 check_date 缺失 | 由 `verified_date` 推导；若也缺失则 `check_date = created_at + horizon 对应天数`，`result` 设为 `pending` 待观势人工补判 |
| lovetrade 的 result 与 falsify 自动判定不一致 | 以 lovetrade 原始 `actual_outcome` 为准（历史数据优先），`result_note` 标注 `migrated, actual_outcome=XXX` |
| regime 无法从 system_state 映射 | `regime_at_create = NULL`，该行不参与 base_rate 的 regime 维度聚合（但参与 category/horizon 维度聚合） |

---

## 4. 边界情况

### 4.1 预测到期未验证（due 状态）

- `prediction.result = 'pending'` 且 `check_date < 当前日期`
- `GET /prediction/due?date=&status=pending` 返回到期待验清单（E13）
- **自动过期规则**：`check_date + 3 交易日` 仍未验证 → `result` 自动设为 `'expired'`，`result_note = 'auto-expired, check_date=YYYY-MM-DD'`
- expired 不计入 base_rate/calibration 的 n（§1.3.1），但 `stat_json.n_expired` 记录

### 4.2 改判后重算

- 观势经 `PUT /prediction/{id}/result` 改判 → `result` 更新、`checked_at = now()`、`result_note` 必填
- base_rate 不实时重算——下次 `j_base_rate` 运行时自动包含改判结果
- calibration_view 为实时 VIEW，改判后立即反映在查询结果中
- **如需立即重算 base_rate**：改判 API 返回中附带 `"base_rate_stale": true` 提示，观势可手动触发 `POST /admin/recalc-base_rate`（admin token）

### 4.3 认知升版（version+1）对归因的影响

- `cognition` 升版（`PUT /cognition/{id}` → 新行 version+1）不影响已有 prediction 的归因
- `prediction.conditions` 存的是 cognition_id 列表（不含 version），升版后同一 cognition_id 指向最新版本
- **base_rate 不受认知升版影响**——base_rate 按 `prediction.category` 聚合，不直接依赖 cognition.version
- 如需追溯"某 prediction 创建时引用的是哪个版本的 cognition"：通过 `prediction.created_at` + `cognition` 表的 `(cognition_id, version)` 时间范围关联

---

## 5. 待观势拍板清单（汇总）

| # | 问题 | 当前默认值 | 影响范围 |
|---|------|-----------|---------|
| 1 | regime 是否需要二级细分（如 trending_up + 高情绪） | V1 不做，`sub_labels` 兜底 | base_rate 粒度 |
| 2 | prediction 表是否增加 `horizon` 显式列 | 不加，由 check_date - created_at 反推 | DDL / migration |
| 3 | expired 是否计入 base_rate n 的分母 | 不计入 | hit_rate 计算 |
| 4 | 样本不足阈值（5/20）是否合适 | 5=low, 20=high | E8 输出 |
| 5 | V1 calibration 是否接受仅按月分桶 | 按月，V2 加 confidence 分桶 | E9 / calibration_view |

---

## 附录 A：与方案 v1.2 字段对齐表

| 本文档概念 | 方案 v1.2 表/字段 | 对齐状态 |
|-----------|------------------|----------|
| regime 枚举 | `base_rate.regime` / `prediction.regime_at_create` | ✅ 一致 |
| category 枚举 | `prediction.category` | ✅ 一致（7 枚举，§10-Q2 冻结） |
| horizon 枚举 | 无显式列，由 check_date 反推 | ⚠️ 待确认是否加列 |
| hit_rate | `base_rate.hit_rate` | ✅ 一致 |
| n_samples | `base_rate.n_samples` | ✅ 一致 |
| brier | `calibration_view.brier` | ✅ 公式一致 |
| confidence_pct 域 | `prediction.confidence_pct INT 0-100` | ✅ 一致 |
| falsify 判定 | `prediction.falsify JSONB` + `j_pred_writeback` | ✅ 一致（§10-Q10） |
| 人工改判优先 | `PUT /prediction/{id}/result` | ✅ 一致（§10-Q10） |
