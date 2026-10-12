# P2-2 根因分析：j_market_messages_other 周日 FAIL

**日期**: 2026-10-12 09:40  
**分析人**: 铸码  
**督军指令**: P2-2 转办（j_market_messages_other 周日 121 FAIL/71 OK，Z7-ext线）

---

## 问题描述

**现象**: 2026-10-11（周日）j_market_messages_other 作业 121 FAIL / 72 OK

**督军要求**: 自查根因，落 Z7 checkpoint

---

## 根因分析

### 失败模式

**查询**:
```sql
SELECT status, note, COUNT(*) as cnt
FROM ingest_log
WHERE job='j_market_messages_other' 
  AND ts >= '2026-10-11' AND ts < '2026-10-12'
GROUP BY status, note;
```

**结果**:
| status | note | cnt |
|--------|------|-----|
| FAIL | handler not implemented | 121 |
| OK | source=eastmoney written=50 elapsed=0.Xs | 72 |

### 时间线

| 时点 | 状态 | 说明 |
|------|------|------|
| 2026-10-11 00:00~14:56 | **FAIL** | handler not implemented（121次） |
| 2026-10-11 15:03 | **修复** | 铸码补充 handler 文件（Z7-ext 交付） |
| 2026-10-11 15:03~23:59 | **OK** | 正常采集（72次） |
| 2026-10-12 00:00~09:40 | **OK** | 持续正常（77次） |

### 根因

**注册名与文件名不一致**（Z4c "注册≠实装"事故变体）

**job_registry 注册**:
- job_name = `j_market_messages_other`
- enabled = true
- schedule_cron = `*/8 * * * *`（每8分钟）

**实际文件**（修复前）:
- ✅ `dworker/jobs/j_market_messages.py`（存在）
- ❌ `dworker/jobs/j_market_messages_other.py`（**缺失**）

**runner 查找逻辑**:
```python
# dworker/core/runner.py
handler_module = importlib.import_module(f"dworker.jobs.{job_name}")
```

当 job_name=`j_market_messages_other` 时，尝试导入 `dworker.jobs.j_market_messages_other`，但文件不存在 → `handler not implemented`

### 修复动作（已完成）

**Z7-ext 交付时修复**（2026-10-11 15:03）:

1. **补充 handler 文件**:
   - `dworker/jobs/j_market_messages_hot.py`（交易时段 */15）
   - `dworker/jobs/j_market_messages_other.py`（7x24 */8min）

2. **实现逻辑**:
   - 直采东财 7x24 快讯（主源）
   - 备源新浪
   - 不经过 lovetrade-service（已停服）

3. **验收三件套**（Z7ext_checkpoint.md §2026-10-11 15:03 复核）:
   - ✅ ingest_log: status=OK, source_used=eastmoney, rows_written=50
   - ✅ market_messages: 新增 source=eastmoney 50行
   - ✅ raw 归档: `data/raw/D10/2026-10-11/j_market_messages_other/150314_eastmoney.json.gz`

---

## 当前状态

**2026-10-12（周一）实测**:

| 指标 | 值 | 说明 |
|------|-----|------|
| 今日运行次数 | 77 | 全部 OK |
| FAIL 次数 | **0** | 修复生效 |
| 写入行数 | 189 | source=eastmoney |
| 最新消息时间 | 09:28:16 | 持续采集中 |

**结论**: ✅ **P2-2 已闭环**，无需进一步动作

---

## 教训与防范

### Z4c 事故模式再现

**Z4c 教训**（"注册≠实装"）:
- job_registry enabled=true ≠ 作业在产出
- 必须以目标表行数/injest_log OK 为准

**本次再现**:
- job_registry 注册了 j_market_messages_other
- 但 handler 文件缺失
- 导致每8分钟 FAIL

### 防范建议

**P1-6 作业实装盘点**（观势需求文档 §4）已覆盖：
> "逐作业四层归因（日历→凭证→解析键→服务端恒空）→ 修复 → 验收三件套过关"

**建议新增检查项**:
- handler 文件存在性检查（`dworker/jobs/{job_name}.py` 或 `dworker/jobs/{job_name}/__init__.py`）
- 纳入 `j_verify_daily` 或 `j_coverage_check`

---

## 关联文档

- Z7ext_checkpoint.md §2026-10-11 15:03 复核（修复记录）
- Z7EXT_HANDOVER_20261011.md（交付清单）
- 观势需求文档 §4 P1-6（作业实装盘点）

---

**铸码 · 2026-10-12 09:40**
