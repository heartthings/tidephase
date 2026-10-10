# URGENT FROM 督军 · 2026-10-10 21:38（Z9-A 波在途插入，先看这段再动手）

## 1. Emotion 端点根因已定位并修复（你的 Z7 结论需纠正）

**Z7-P0-3 的结论「实测响应顶层为 list（空列表）与 errcode，兼容 list/ZY 双键」是误判。**
真相：我方**请求参数不全**，源端才返回 `{"list":[],"List":[],"errcode":"0"}`（errcode=0 但空载荷）。
按 lovetrade-service Java 源码逐参复刻后，**同一端点返回 ZY 数组 30 日真实数据**（2026-08-21~2026-10-09）。

### 可用的正确请求（督军 21:35 实测 HTTP 200 / ZY=30 条 / 已写库 30 行 / 源库交叉 0 不一致）
```
POST https://apphis.longhuvip.com/w1/api/index.php
Headers:
  User-Agent: Dalvik/2.1.0 (Linux; U; Android 13; SM-G9810 Build/TP1A.220624.014)
  Host: apphis.longhuvip.com
  Connection: Keep-Alive
  Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Params（form）:
  a=GetMoneyDate  c=Emotion  st=30  index=0  apiv=w39
  PhoneOSNew=1    VerSion=5.18.0.2   DeviceID=<secrets.longhu.emotion_device_id>
响应: {"ZY":[{"CGL":"76.19","YLL":"2.10","Day":"2026-10-09"}, ...30条], "ttag":..., "errcode":"0"}
解析: 取 ZY[i].Day/CGL/YLL → sentiment_daily(date, dbcgl, dbyll)
```
证据：`reports/sentiment_30d_backfill_20261010.md`（含 raw 归档路径 data/raw/D3/2026-10-10/j_sentiment_calc/）
Java 依据：`lovetrade-service/src/main/java/ai/snowball/lovetrade/builder/SpeculativePerformanceDataParamBuilder.java:71-96`
解析依据：`.../crawler/TradingDashboardCrawler.java:329-336`（`emotionRoot.path("ZY").get(0)` → CGL/YLL）

### 你要做的（P0-3 内）
- 把上面参数集固化进 `dworker/adapters/longhu.py` 的 Emotion 分支（`ENDPOINT_MAP["Emotion"]` + 请求构造），
  **删掉"顶层 list 兜底"那套基于误判的兼容代码**（保留 ZY 主键即可，兜底改成"空载荷→写 MISS 行并告警"）
- `tools/backfill_sentiment_daily.py` 同步修（它现在也是错的参数，跑出来 0 条）
- `j_sentiment_calc` handler 落地（15:40 cron），**必须走 calendar_gate**：非交易日不写行、写 SKIP 日志
- 记名：这是 G7「注册/实测当结论」同类问题第 2 次变形（把自家请求 bug 判成源端格式变化）。**同错第 3 次即停线**，请务必先复刻 Java 参数再下结论。

## 2. 我已重启两个容器（避免你重复排查）
- `market-api` 21:20 重启 → 活体 openapi **50 paths**（你的 lovetrade_routes 31 端点已生效）
  - 顺手修了个雷：`ops/requirements-api.txt` 缺 `requests`，容器内 import 直接 ModuleNotFoundError，**下次重建镜像会崩**；已补进 requirements（未 commit，你随波提交）+ 容器内 pip 装好
- `market-sched` 21:20 重启 → seed 生效，`job_registry` 33 → **38**（你 seed_jobs.yaml 里 6 个 lovetrade 作业已入库、enabled=true）
  - 启动日志有一条 `⚠️ 1 critical jobs missed in last 24h: ['j_trade_cal']` = **误报**（j_trade_cal 是 `0 0 1 1 *` 年度作业，漏跑检测窗口按 24h 判不适用）→ 建议漏跑检测按各作业 cron 周期推算下次应跑时刻，别用固定 24h

## 3. 新发现的数据缺口（按你的 handler 归属排进去，别伪造）
- `sector_daily`：11,318 行但**只有 kind='concept'、只到 2026-09-30**（lovetrade plate_movement 迁移来的），无 '行业' 口径、10-08/10-09 全缺
  → 后果：反思证据包 S1 常亮 `SECTOR_DAILY_EMPTY`（实测 gap 已在案）
  → 需 `j_sector_daily` handler 实装（含行业/概念两口径 + 龙虎 RealRankingInfo 历史回填能力）
- `session_def=0`、`instrument_master=1`：G6 遗留第 3 天，今夜必须落地（静态/半静态表，不依赖开盘）
- `base_rate=0`：你 P0-1 的活，`calibration_view` 已建但无数据 → 首跑后我要 curl 实测非空
- `regime_daily=0`：观势侧义务（17:30 作业写），但**观势 8 个 cron 全 disabled**，我已启用 j_reflect_daily；regime_daily 若观势不写，S3/S4 永远缺锚 → 我会向梁总/观势明确这条依赖，你不用兜

## 4. 测试残留已清理（与你 19:46 的端点验证有关）
`cognition F-001（测试认知/src=test）` 与 `prediction P-20261010-001（测试预测）` 已删除，
因为它占用观势 seeding 的 F-001 命名空间（POST 会返 409）。删前快照 + 复核全部留档
`reports/TEST_RESIDUE_CLEANUP_20261010.md`。**以后端点验证请用 M-999/P-*-SMOKE 这类明显 smoke id 并当场自删**（督军 21:23 的验证就是这么做的，零残留）。

## 5. 纪律重申（梁总在场，零容忍）
不伪造数据 / 注册≠实装 / 跳过必写 MISS-SKIP 行 / 凭证只走 secrets.yaml / 同错 2 次即停换法。
每完成一项立即 commit + 追加 `reports/Z9A_checkpoint.md` + 回报我，不要攒批。

---

## 6. 【21:45 追加】reflection_pack 实测四缺陷（督军对 P-200/P-261/P-346 三条真实决策实测，证据=curl 原文）

**P0-安全（必须今夜修）：S2 查询把 falsify.metric 原样拼进 SQL**
```
实测 decision_id=P-346 → gaps:
{"section":"S2","code":"S2_QUERY_ERROR",
 "reason":"Table/column error: syntax error at or near \":\"\nLINE 2: SELECT date, 0, \"rangeHigh\": 0.5, \"shClosePct\": ...\n"}
根因：该条 prediction.falsify.metric = '{"rangeLow": -1.0, "rangeHigh": 0.5, ...}'（观势历史债，非标准 schema）
     代码未做白名单校验，直接把 metric 字符串插值进 SELECT 列表 → SQL 语法错误
要求：metric 必须匹配白名单 ^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$（table.column）才允许进 SQL；
     不匹配 → 直接返回 gap code=FALSIFY_METRIC_INVALID（含原始 metric 值），绝不拼 SQL。
     这是注入面，不是美观问题。routed_table/routed_column 同样要被校验（实测它们被切成了 '{"rangeLow": -1' 这种碎片）。
```

**P1-口径 bug①：S3 regime 窗口起止倒挂 → REGIME_DAILY_EMPTY 永亮**
```
P-261（decision_date=2026-08-31, check_date=2026-08-31）→ reason: "No regime_daily for 2026-09-01~2026-08-31"
P-346（decision_date=2026-10-09, check_date=2026-10-09）→ reason: "No regime_daily for 2026-10-10~2026-10-09"
start > end，区间为空集 → 即使观势开始写 regime_daily，S3 也永远取不到数据。修窗口计算（含 start==end 的当日情形）。
```

**P1-口径 bug②：GLOBAL_OVERNIGHT_EMPTY 用自然日查隔夜数据**
```
P-261 → reason: "No global_daily for date=2026-08-30"（8-30 是周日，本就无交易）
global_daily 实测 674 行 / 324 个交易日（2025-06-20~2026-10-10），数据是在的。
要求：按 trade_cal 取"决策日前最近一个交易日"的隔夜数据，非交易日不得报 gap（否则每个周一决策都误亮）。
```

**P1-可观测性 bug③：VOLUME_ERROR 的 reason 是字符串 "0"**
```
P-261/P-346 均出现 {"section":"S1","code":"VOLUME_ERROR","reason":"0","affected":"S1.volume"}
reason 丢失（疑似把 count 或异常码当 reason 传）。真实原因大概率是 stock_daily 无该窗口数据
（库内 stock_daily 只有 10-08/10-09 两日 = 梁总 D3 裁决"只补近一周"的必然结果，不是 bug）。
要求：把真实异常/count 写进 reason，并区分两种 code：
  VOLUME_EMPTY（查得到但窗口内无行 → 附窗口与表名）vs VOLUME_QUERY_ERROR（SQL/连接异常 → 附异常原文）。
```

**P2-数据缺口：sector_daily 无 '行业' 口径且止于 09-30**
```
实测：sector_daily 11,318 行，kind 只有 'concept'，日期 2026-08-03~2026-09-30（lovetrade plate_movement 迁来的）
后果：所有决策的 S1.sector 都亮 SECTOR_DAILY_EMPTY（P-200/P-261/P-346 三条全亮）
要求：j_sector_daily handler 实装（行业+概念双口径），并评估能否用龙虎 RealRankingInfo(ZSType=7, 支持 Date) 回填历史窗口
     —— 这条同时是"六案例回放 D6 面"的关键（墨测正在跑核对单，会量化缺哪些窗口）。
```

**已修好的（你不用管）**：sentiment_daily 已从 0 → **125 行**（2026-04-03~2026-10-09，st=250 源端上限），
SENTIMENT_DAILY_EMPTY gap 实测已消除（P-200/P-261/P-346 三条 S1.sentiment 均返回真实行）。
证据 `reports/sentiment_backfill_20261010.md`。**你只需把第 1 节的正确参数固化进 adapter/handler，别再用错参数。**
