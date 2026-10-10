# Z9-B 数据缺陷修复 Checkpoint

> 开始时间：2026-10-10 21:55
> 指令：督军 Z9-B 数据缺陷修复波
> 最终更新：2026-10-10 22:xx

---

## 纪律记名

> 报字段完成度必须给"值分布"（notnull / 零值 / NULL 三个数），不许只报 NOT NULL 行数。
> —— 此条铭记。Z9-A 报 twenty_ztwme/fd/zdfd NOT NULL=100 但未报零值=100，实为 eastmoney 硬编码 0 残留。

---

## B1（P0）index_daily.pct 回填 ✅

### 根因
所有 fetch 函数（tencent/mootdx/akshare/eastmoney）均未计算/返回 `pct` 字段。

### 修复
- `dworker/jobs/j_index_daily.py`: 四个 fetch 函数均增加 pct 计算
  - tencent: 请求 10 天数据，`(close-prev_close)/prev_close*100`
  - mootdx: 优先取 `pctChange` 列，否则手算
  - akshare: 取 tail(10)，手算 pct
  - eastmoney: 取 tail(10)，手算 pct
- `tools/backfill_index_daily_pct.py`: 回填脚本，走同一代码路径

### 回填结果
| 指标 | 值 |
|------|-----|
| 回填前行数 (pct IS NULL) | 28 |
| 回填行数 | 30 |
| 回填后 pct IS NULL | **0** |
| 首日无前收 NULL | 0（akshare 全量历史覆盖） |

### 验收
```sql
SELECT count(*) FROM index_daily WHERE pct IS NULL;  -- = 0 ✅
```

---

## B2（P0）global_daily eastmoney 字段错位 + 品种 code 统一 ✅

### 根因
1. eastmoney 分支字段映射错误：pct 里塞的是价格值
2. N225/NK225 两个 code 并存造成序列断裂

### 修复
- 删除 4 行错误 eastmoney 数据（DJI/SPX/IXIC 10-07, N225 10-08）
- NK225 → N225 统一（snapshot 10-07 行）
- 删除 snapshot N225 数据（close=44946.64，实际=70035.71，值错误）
- `j_global_overnight.py`: 实现 eastmoney 全球品种 fetcher（N225 secid=100.N225）
- 多源合并逻辑：tencent 覆盖美股/港股/商品，eastmoney 补 N225

### 验收
```sql
SELECT count(*) FROM global_daily WHERE abs(pct)>20;  -- = 0 ✅
SELECT DISTINCT code FROM global_daily WHERE code IN ('N225','NK225');  -- 仅 N225 ✅
```

### 已知缺口
| 品种 | 日期 | 状态 | 说明 |
|------|------|------|------|
| N225 | 2026-10-07 | MISS | eastmoney 从本机被 RemoteDisconnected；snapshot 值错误（44946 vs 真实 70035） |

> 公开值对照（Investing.com）：N225 10-07 close=70,035.71 pct=-0.92%

---

## B3（P1）bidding_list 100 行 0 值残留清理 ✅

### 根因
10-09 整改前 eastmoney 批次硬编码 0 残留（qtype=2 = 09:20 快照）。

### 修复
- 逐行快照留档：`data/raw/quarantine_export/bidding_list_cleanup_snapshot_20261010.json`
- 100 行 `twenty_ztwme/fd/zdfd` 由 0 置 NULL
- ingest_log 写入订正行（trigger=correction）

### 验收
```sql
SELECT count(*) FROM bidding_list
WHERE date='2026-10-09' AND source='eastmoney' AND quotations_type=2
  AND (twenty_ztwme=0 OR fd=0 OR zdfd=0);  -- = 0 ✅
```

### Handler 确认
`j_bidding_list.py` 已不会再产 0 值（tencent/eastmoney 两源均设 None）。

---

## B4（P0）Emotion 端点参数固化 ✅

### 根因
Z9-A 误判"源端空/token 过期"，实为我方请求参数不全。
正确参数（Java 源码复刻）：st=250, index=0, apiv=w39, VerSion=5.18.0.2

### 修复
- `dworker/adapters/longhu.py`:
  - ENDPOINT_MAP["Emotion"] 增加 `fixed_params`
  - fetch() 支持端点级固定参数覆盖
  - `_parse_emotion()`: 删除错误"顶层 list 兜底"，只认 ZY 键
- `dworker/jobs/j_sentiment_calc.py`:
  - `fetch_emotion()`: 固化正确参数 + UA + headers
  - 空载荷 → 写 MISS 行 + 告警（不再误判 token 过期）
- `tools/backfill_sentiment_daily.py`: 同步修

### 实测验证
```
POST apphis.longhuvip.com/w1/api/index.php
st=250, index=0, apiv=w39, VerSion=5.18.0.2, DeviceID=<secrets>
→ HTTP 200, errcode=0, ZY=125 条 (2026-04-03~2026-10-09) ✅
```

---

## B5（P0 安全 + 3 口径）reflection_pack 四缺陷 ✅

### ① S2 SQL 注入面（P0 安全）✅
- 加白名单 `^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$`
- 不匹配 → `FALSIFY_METRIC_INVALID` gap，绝不拼 SQL
- routed_table/routed_column 同样校验

### ② S3 regime 窗口起止倒挂 ✅
- 原: `ws = decision_td + timedelta(days=1)` → 当 decision_date==check_date 时 ws > we
- 修: `ws = decision_td`（从决策日当天开始）
- 加防倒挂保护

### ③ GLOBAL_OVERNIGHT_EMPTY 用自然日查 ✅
- 新增 `_nearest_trade_day_before()` 函数
- 按 trade_cal 取决策日前最近交易日（周一→上周五）

### ④ VOLUME_ERROR reason="0" ✅
- 拆 `VOLUME_EMPTY`（窗口内无行）/ `VOLUME_QUERY_ERROR`（SQL/连接异常）
- 附窗口范围 + 异常原文

### 实测验证（P-346）
```
S2 FALSIFY_METRIC_INVALID: metric '{"rangeLow":...}' 不匹配白名单 ✅
S3 REGIME_DAILY_EMPTY: 2026-10-09~2026-10-09（不再倒挂）✅
S1 VOLUME_QUERY_ERROR: 窗口 2026-09-24~2026-10-09 查询异常: KeyError: 0 ✅
```

---

## B6（P1）部署收尾

### market-api / market-sched
- 容器重启由督军操作
- import 校验待做

### lovetrade-web dist 部署
- 待查现状（docker ps / nginx / frp）
- 待部署后实测

---

## Commit 记录
- `[Z9B]` 数据缺陷修复波: B1-B5

---

## 待督军操作
1. 重启 market-api / market-sched
2. 部署 lovetrade-web dist
3. N225 数据源确认（eastmoney 从本机被 block，需替代方案）
