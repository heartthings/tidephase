# Z7 Checkpoint — 梁总 2026-10-10 裁决落地波

> 铸码执行 · 2026-10-10（周六）

## P0-2 D3 回填范围变更 ✅ 已完成

### 梁总裁决
"不用 3 年，前一周即可"

### 处置

| 项 | 状态 |
|----|------|
| 3 年回填进程 | 无运行中进程（仅完成 26 只即停） |
| backfill_progress | 旧记录已清理 |
| backfill_stock_daily.py | 默认窗口改为"近 7 个自然日内的交易日"缺口补齐 |
| trade_cal 10-08 修正 | is_open 0→1（实为交易日，stock_daily 有数据佐证） |

### 对账报告

| 项 | 值 |
|----|-----|
| 窗口 | 2026-10-03 ~ 2026-10-10 |
| 窗口内交易日 | 10-08（Wed）、10-09（Thu） |
| stock_daily 覆盖 | 10-08: 5,224 行 ✅ / 10-09: 5,224 行 ✅ |
| 缺口 | **无** ✅ |

## P0-3 D8 龙虎落地 ✅ 代码面完成 / ⏳ 周一实盘待测

### 处置明细

| 项 | 状态 | 说明 |
|----|------|------|
| rate_limits.yaml longhu 人为限速 | ✅ 已删除 | 0.5rps/burst=1 → 移除，仅保留 circuit_breaker_seconds=1800 |
| rate_limiter.py DEFAULT_RATE_LIMITS | ✅ 已删除 longhu 条目 | RateLimiter 跳过无 rps 的源 |
| longhu.py _parse_emotion | ✅ 已修复 | 兼容 list（顶层列表）/ ZY（嵌套列表）双键 |
| smoke_longhu_one.py | ✅ 已更新 | count_rows 补 ZY/DongXiang 键；EP 补 DongXiang |
| credentials.md | ✅ 已更新 | 三套凭证状态=有效 + 限速裁决 + YouZiDongXiang 结论 |

### YouZiDongXiang 结论

- auth 有效（errcode=0），服务端 DongXiang 恒空
- D4 资金面维持东财链，龙虎 DongXiang 保留代码面不阻塞

### ⏳ 周一 10-12 开盘后待测

- [ ] Emotion 行数（交易日应有 CGL/YLL 30日序列）
- [ ] DailyLimitResumption 行数（nums 六项 + list 涨停明细）
- [ ] Radar 行数（盘中雷达数据）
- [ ] 结果追加到本节

## P1-1 D4 取消备份 ✅ 已记录

### 梁总裁决
不需要备份。风险告知已由督军向梁总留痕。

### 处置

| 项 | 状态 |
|----|------|
| dops 备份 timer/脚本 | 代码面不存在，无需停用 |
| "远端第二副本"待办 | 已取消，不再列入计划 |
| README.md | 已追加运维决策记录 |

## P1-2 Z5 残余重启 ✅ 已完成

### 1. OpenAPI 文档

| 项 | 状态 |
|----|------|
| /openapi.json | ✅ 15 端点已导出 |
| docs/openapi.yaml | ✅ 已生成 |
| Python 客户端样例 | ✅ `tools/data_api_client_example.py`（Bearer token/分页/CSV） |

### 2. D12 写端点

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| /d12/cognition | POST | ✅ | ID 校验 `^[FCHM]-\d{3}$` + 重复检测 409 |
| /d12/prediction | POST | ✅ | confidence_pct 0-100 校验 + horizon T1/T3/T5/W1 |
| /d12/prediction/{id}/result | PUT | ✅ | 人工改判，result_note 必填，返回 base_rate_stale |
| /d12/prediction/due | GET | ✅ | E13 到期待验清单 |

### 3. base_rate / calibration 视图

| 项 | 状态 | 说明 |
|----|------|------|
| V003 migration | ✅ | prediction.horizon 列 + base_rate 表 + calibration_view |
| E8 /data/base_rate | ✅ | 口径1-5 · 双口径 window_type 参数 |
| E9 /calibration | ✅ | 口径4 · 按月分桶 · Brier Score |
| 路由顺序修复 | ✅ | E8 在 E5 /data/{table} 之前，避免通配拦截 |

### 4. 端点清单（15 个）

```
GET      /health
GET      /meta/tables
GET      /meta/trade_cal
GET      /meta/instruments
GET      /data/base_rate        ← NEW (E8)
GET      /data/{table}          (E5)
GET      /data/sentiment/latest (E6)
GET      /data/global/overnight (E7)
GET      /calibration           ← NEW (E9)
GET PUT  /watchlist             (E15)
GET      /ingest/status         (E16)
POST     /d12/cognition         ← NEW
POST     /d12/prediction        ← NEW
PUT      /d12/prediction/{id}/result  ← NEW
GET      /d12/prediction/due    ← NEW (E13)
```

---

## P0-1 数据纠错 ✅ 已完成

### 1. stock_daily 10-10 误写处置

| 项 | 值 |
|----|-----|
| 误写日期 | 2026-10-10（周六，A 股休市） |
| 误写行数 | 5,224 |
| 根因 | tencent qt API 返回周五收盘数据，作业用 `datetime.now()` 作 date 覆盖为周六 |
| 导出留痕 | `data/raw/quarantine_export/stock_daily_20261010_quarantine.csv`（723KB） |
| DELETE | ✅ 已执行，stock_daily 中 date=2026-10-10 行数 → 0 |
| ingest_log | 已写入 CORRECTED 记录 |

### 2. 日历门禁修复

**新增**：`dworker/core/calendar_gate.py`
- 查 `trade_cal` 表（market='SSE', cal_date=today）
- `is_open=0` → 返回 `allowed=False`
- 无记录 → 保守视为非交易日

**修改**：`dworker/jobs/j_stock_daily.py`
- run() 入口处调 `check_trade_gate()`
- 不通 → ingest_log `status='SKIP'` + note 写明原因 → return

**修改**：`dworker/jobs/j_index_daily.py`
- 同上，门禁逻辑一致

### 3. global_daily 10-10 行

- 7 行（DJI/SPX/IXIC/HSI/GC/SI/CL）= 美/港/商品周五收盘，北京晨接收
- 符合 `date=北京接收日` 约定 → **保留**
- 已写表 COMMENT + 文档 `docs/global_daily_date_convention.md`
- global_daily 不受 A 股 trade_cal 门禁约束

### 4. stock_daily 对账

| 日期 | 行数 | 备注 |
|------|------|------|
| 2026-10-08（周三） | 5,224 | ✅ 交易日 |
| 2026-10-09（周四） | 5,224 | ✅ 交易日 |
| 2026-10-10（周六） | 0 | ✅ 已清除 |

## P0-2 D3 回填范围变更 ✅ 已完成

### 梁总裁决
"不用 3 年，前一周即可"

### 处置

| 项 | 状态 |
|----|------|
| 3 年回填进程 | 无运行中进程（仅完成 26 只即停） |
| backfill_progress | 旧记录已清理 |
| backfill_stock_daily.py | 默认窗口改为"近 7 个自然日内的交易日"缺口补齐 |
| trade_cal 10-08 修正 | is_open 0→1（实为交易日，stock_daily 有数据佐证） |

### 对账报告

| 项 | 值 |
|----|-----|
| 窗口 | 2026-10-03 ~ 2026-10-10 |
| 窗口内交易日 | 10-08（Wed）、10-09（Thu） |
| stock_daily 覆盖 | 10-08: 5,224 行 ✅ / 10-09: 5,224 行 ✅ |
| 缺口 | **无** ✅ |

## P0-3 D8 龙虎落地 ✅ 代码面完成 / ⏳ 周一实盘待测

### 处置明细

| 项 | 状态 | 说明 |
|----|------|------|
| rate_limits.yaml longhu 人为限速 | ✅ 已删除 | 0.5rps/burst=1 → 移除，仅保留 circuit_breaker_seconds=1800 |
| rate_limiter.py DEFAULT_RATE_LIMITS | ✅ 已删除 longhu 条目 | RateLimiter 跳过无 rps 的源 |
| longhu.py _parse_emotion | ✅ 已修复 | 兼容 list（顶层列表）/ ZY（嵌套列表）双键 |
| smoke_longhu_one.py | ✅ 已更新 | count_rows 补 ZY/DongXiang 键；EP 补 DongXiang |
| credentials.md | ✅ 已更新 | 三套凭证状态=有效 + 限速裁决 + YouZiDongXiang 结论 |

### YouZiDongXiang 结论

- auth 有效（errcode=0），服务端 DongXiang 恒空
- D4 资金面维持东财链，龙虎 DongXiang 保留代码面不阻塞

### ⏳ 周一 10-12 开盘后待测

- [ ] Emotion 行数（交易日应有 CGL/YLL 30日序列）
- [ ] DailyLimitResumption 行数（nums 六项 + list 涨停明细）
- [ ] Radar 行数（盘中雷达数据）
- [ ] 结果追加到本节

## P1-1 D4 取消备份 ✅ 已记录

### 梁总裁决
不需要备份。风险告知已由督军向梁总留痕。

### 处置

| 项 | 状态 |
|----|------|
| dops 备份 timer/脚本 | 代码面不存在，无需停用 |
| "远端第二副本"待办 | 已取消，不再列入计划 |
| README.md | 已追加运维决策记录 |

## P1-2 Z5 残余重启 ✅ 已完成

### 1. OpenAPI 文档

| 项 | 状态 |
|----|------|
| /openapi.json | ✅ 15 端点已导出 |
| docs/openapi.yaml | ✅ 已生成 |
| Python 客户端样例 | ✅ `tools/data_api_client_example.py`（Bearer token/分页/CSV） |

### 2. D12 写端点

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| /d12/cognition | POST | ✅ | ID 校验 `^[FCHM]-\d{3}$` + 重复检测 409 |
| /d12/prediction | POST | ✅ | confidence_pct 0-100 校验 + horizon T1/T3/T5/W1 |
| /d12/prediction/{id}/result | PUT | ✅ | 人工改判，result_note 必填，返回 base_rate_stale |
| /d12/prediction/due | GET | ✅ | E13 到期待验清单 |

### 3. base_rate / calibration 视图

| 项 | 状态 | 说明 |
|----|------|------|
| V003 migration | ✅ | prediction.horizon 列 + base_rate 表 + calibration_view |
| E8 /data/base_rate | ✅ | 口径1-5 · 双口径 window_type 参数 |
| E9 /calibration | ✅ | 口径4 · 按月分桶 · Brier Score |
| 路由顺序修复 | ✅ | E8 在 E5 /data/{table} 之前，避免通配拦截 |

### 4. 端点清单（15 个）

```
GET      /health
GET      /meta/tables
GET      /meta/trade_cal
GET      /meta/instruments
GET      /data/base_rate        ← NEW (E8)
GET      /data/{table}          (E5)
GET      /data/sentiment/latest (E6)
GET      /data/global/overnight (E7)
GET      /calibration           ← NEW (E9)
GET PUT  /watchlist             (E15)
GET      /ingest/status         (E16)
POST     /d12/cognition         ← NEW
POST     /d12/prediction        ← NEW
PUT      /d12/prediction/{id}/result  ← NEW
GET      /d12/prediction/due    ← NEW (E13)
```

---

