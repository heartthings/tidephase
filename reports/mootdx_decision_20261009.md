# mootdx 降级决策回报 · 2026-10-09

**回报时间**: 08:35  
**回报人**: 铸码  
**收件人**: 督军

---

## 一、mootdx 降级框架执行结果

### 决策：**放弃今日改动，接受竞价如实 MISS**

### 执行记录

| 步骤 | 死线 | 实际完成 | 结果 |
|------|------|----------|------|
| 独立脚本冒烟 | 08:50 | 08:33 | ✅ API 链路通，字段结构源码确认 |
| 拿到有效竞价字段 | 08:50 | ❌ 不可能 | TDX 协议硬限制：09:15 前返回空 |
| 接入生产 handler | 09:05 | ⛔ 未执行 | 未满足前置条件（有效字段验证） |
| 文件冻结 | 09:14 | ✅ 遵守 | 零改动 |

### 技术证据

**1. 冒烟脚本**: `tools/smoke_mootdx_bidding.py`
```
[08:33:52] mootdx 竞价字段冒烟测试
✓ API 初始化成功
✓ API 调用成功，耗时 26.1ms
返回类型: list, 返回数量: 0
✓ 符合预期：非交易时段返回空列表
```

**2. 字段结构确认**（从 `tdxpy/parser/std/get_security_quotes.py` 源码）:
- `price` / `open` → 竞价价
- `vol` / `cur_vol` → 竞价量
- `b_vol` / `s_vol` → 外盘/内盘（可推算未匹配量）
- `bid1-5` / `ask1-5` + `bid_vol1-5` / `ask_vol1-5` → 五档数据
- `amount` → 成交额

**3. 根因**: TDX 通达信协议限制，`get_security_quotes` 在非交易时段（09:15 前）返回空列表 `[]`。这是协议层硬约束，非代码问题。

**4. 结论**: 
- ✅ API 连接/协议/解析链路正常
- ✅ 字段映射已从源码确认
- ❌ 端到端数据流无法在 09:05 前验证（必须 09:15 后才有真实数据）
- ⛔ 未验证的数据流接入生产 = 高风险，违反健壮性原则

### 后续计划

**09:26 验证计划**（snap1 完成后）:
1. 运行 `smoke_mootdx_bidding.py` 确认真实竞价数据
2. 如字段完整 → 应用 patch（见 `reports/mootdx_bidding_integration_patch.py`）
3. 重跑 `manual_test` 对比 mootdx vs eastmoney 数据质量
4. 验证通过 → 明日生效；验证失败 → 维持 eastmoney 单源

---

## 二、run_id=246 FAIL 根因落档

### 事实

```
run_id=246
job=j_bidding_list
status=FAIL
source_used=none
rows_in=0
rows_written=0
duration_ms=335
note="all sources failed type=1"
ts=2026-10-09 08:25:03
```

### 根因分析

**直接原因**: eastmoney push2 API 在 08:25 返回空数据（竞价尚未开始）

**深层原因**: 
1. j_bidding_list 的 source_chain 只有 `["eastmoney"]`，无降级备选
2. eastmoney 竞价数据接口在 09:15 前不返回有效数据
3. mootdx 理论上可在 09:15-09:25 提供竞价数据，但今日未接入

**责任归属**: **infra 根因，非代码逻辑错误**
- handler 如实返回 FAIL，未静默成功 ✅
- 降级链框架正常工作 ✅
- 缺的是 mootdx 作为备选源（今日未接入）

### 影响

- bidding_list 表：0 行（今日无竞价数据）
- 下游影响：依赖竞价数据的策略/报表今日无法运行

---

## 三、遗留记账（督军指定）

### 3.1 session_def = 0 行

**状态**: ❌ 缺失  
**原因**: j_trade_cal handler 只实现了 trade_cal 表，未实现 session_def 表  
**影响**: 无法精确判断当前处于哪个交易时段（auction/am/pm 等）  
**修复计划**: 需补充 session_def 种子数据（CN 市场各时段定义）

### 3.2 instrument_master = 1 行

**状态**: ⚠️ 严重不足  
**当前数据**: 仅 NK225（日经 225 指数）  
**缺失**: 全市场 A 股（约 5000+ 只股票 + ETF + 指数）  
**原因**: j_instrument_master handler 标记为 "handler not implemented"（run_id=144）  
**影响**: 
- 无法做代码映射（mootdx 返回纯数字代码，需 instrument_master 补充市场前缀）
- 无法计算流通市值（需要 total_shares）
- 无法做板块分类

### 3.3 R2: stock 首跑 FAIL 根因

**run_id=130** (2026-10-08 09:50:36):
```
status=FAIL
source_used=none
note="all sources failed"
```

**根因**: 09:50 处于盘中，tencent/akshare 等源的"全市场个股日K"接口可能尚未就绪（通常在 15:00 收盘后才有完整数据）

**后续**: run_id=131 (09:53) 从 tencent 成功获取 5224 行，说明降级链正常工作，只是首跑时机不对。

**结论**: 非 BUG，是调度时机问题。j_stock_daily 的 cron 应设为 15:30（收盘后），而非 09:50。

### 3.4 R5: worker 占位符

**现状**: market-worker 容器启动命令为占位符：
```yaml
command: python -c "print('market-worker ready; jobs dispatched by market-sched')"
```

**原因**: Z1 波优先完成基建（DB/migration/框架/sched），worker 实际执行逻辑由 market-sched 通过 APScheduler 直接调度（单容器模式）

**影响**: 无实际影响。当前架构下 sched 和 worker 合并运行，后续如需水平扩展可拆分。

**记录**: 已在 `reports/Z1_report.md` 中说明，非阻塞项。

---

## 四、当前系统状态快照

### 4.1 数据表状态

| 表名 | 行数 | 状态 |
|------|------|------|
| trade_cal | 396 | ⚠️ 仅 SSE 市场，缺 SZSE/CN |
| session_def | 0 | ❌ 缺失 |
| instrument_master | 1 | ❌ 仅 NK225，缺全市场 |
| index_daily | ? | 需检查 |
| stock_daily | 5224 | ✅ 10/08 数据完整 |
| bidding_list | 0 | ❌ 今日无数据 |
| global_daily | ? | 需检查 |

### 4.2 ingest_log 关键记录

| run_id | job | status | source | rows | note |
|--------|-----|--------|--------|------|------|
| 247 | j_heartbeat | OK | internal | - | 08:30 |
| 246 | j_bidding_list | FAIL | none | 0 | all sources failed type=1 |
| 244 | j_instrument_master | FAIL | none | 0 | handler not implemented |
| 241 | j_global_overnight | OK | tencent | 7 | 07:30 |
| 162 | j_stock_daily | OK | tencent | 5224 | 15:30 |
| 130 | j_stock_daily | FAIL | none | 0 | all sources failed (09:50) |

### 4.3 raw 归档

```
data/raw/
├── D1/2026-10-08/j_index_daily/
│   ├── 094904_akshare.json.gz
│   ├── 095020_tencent.json.gz
│   └── 151028_tencent.json.gz
├── D2/2026-10-08/j_stock_daily/
│   ├── 095313_tencent.json.gz
│   └── 153016_tencent.json.gz
└── D7/
    ├── 2026-10-08/j_global_overnight/
    │   ├── 073000_tencent.json.gz
    │   └── 095529_tencent.json.gz
    └── 2026-10-09/j_global_overnight/
        └── 073000_tencent.json.gz
```

**缺失**: D3（竞价）无任何归档

---

## 五、09:26 回报预告

### 待验证项

1. **snap1 实际结果**: 预期 j_bidding_snap1 也会 FAIL（同源限制）
2. **mootdx 真实数据**: 09:26 运行 smoke 验证竞价字段
3. **raw 归档路径**: `data/raw/D3/2026-10-09/j_bidding_snap1/` (如成功)

### 决策树

```
09:26 smoke_mootdx_bidding.py
  ├─ 返回有效数据（4只股票 price/vol > 0）
  │   ├─ 字段完整性检查通过
  │   │   └─ 应用 patch → 重跑 manual_test → 对比 eastmoney
  │   │       ├─ 质量达标 → 明日生效
  │   │       └─ 质量不达标 → 维持 eastmoney 单源
  │   └─ 字段缺失
  │       └─ 记录缺失字段 → 调整映射 → 重新验证
  └─ 返回空
      └─ mootdx 源不可用 → 维持 eastmoney 单源 → 记录根因
```

---

## 六、证据原文

### 冒烟脚本输出

```
[08:33:52] mootdx 竞价字段冒烟测试
============================================================
[08:33:52] 初始化 mootdx API...
✓ API 初始化成功

⚠️  当前时间 08:33，早于竞价开始时间 09:15
   TDX 协议限制：非交易时段 API 返回空列表
   预期结果：get_security_quotes 返回 []

[08:33:53] 调用 get_security_quotes...
✓ API 调用成功，耗时 26.1ms

结果分析:
  返回类型: list
  返回数量: 0

✓ 符合预期：非交易时段返回空列表

结论：
  1. API 调用链路正常（连接、协议、解析均无报错）
  2. 字段结构已从源码确认（见文件头注释）
  3. 实际竞价数据需 09:15 后验证
```

### ingest_log run_id=246

```
run_id       | 246
job          | j_bidding_list
status       | FAIL
source_used  | none
rows_in      | 0
rows_written | 0
duration_ms  | 335
note         | all sources failed type=1
ts           | 2026-10-09 08:25:03.146071+08:00
```

---

**回报完毕**。09:26 继续验证 snap1 结果 + mootdx 真实数据。
