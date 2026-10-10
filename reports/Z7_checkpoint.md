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

---

