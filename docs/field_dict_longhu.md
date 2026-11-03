# 龙虎字段字典草稿（T-R4 协同预备）

> 从 lovetrade-service Java 源码提取龙虎端点解析逻辑 + MySQL 表中文注释。
> 供铸码 T-R4 冻结用。
> 
> 来源：
> - Java 实体类 + Crawler 解析代码（只读参照）
> - MySQL 表注释（lovetrade 数据库）
> 
> 状态：草稿 v0.1（2026-10-07 墨测初版，待铸码复核）

---

## 1. DailyLimitResumption（涨停复牌）— list 19 元素数组

**端点**: `GetPlateInfo_w38 / DailyLimitResumption`
**主机**: `apphwhq.longhuvip.com`
**认证**: DeviceID
**响应结构**: `nums{...}` + `list[]`（18 个申万板块组），每股 `StockList[][]` 19 元素数组

### 19 列数组语义对照

| 列序号 | Java 解析位置 | 语义 | 类型 | 来源代码 | MySQL 落库字段 | 备注 |
|--------|-------------|------|------|---------|---------------|------|
| [0] | ArenaStockCrawler.parseDailyLimitResponse | 股票代码 | String | ArenaStockCrawler.java:165 | — | 如 "600519" |
| [1] | ArenaStockCrawler.parseDailyLimitResponse | 股票名称 | String | ArenaStockCrawler.java:166 | — | 如 "贵州茅台" |
| [2] | TradingDashboardCrawler.processDragonHeadStocksResponse | 涨停时间戳 | String/Long | TradingDashboardCrawler.java:381 | ztsj | 时间格式或 Unix 时间戳 |
| [3] | 同上 | 板序（'首板'/'二板'/…） | String | TradingDashboardCrawler.java:382 | limit_up_status | 龙虎独有：连板层级文字描述 |
| [4] | 同上 | 涨停时间（另一格式） | String | TradingDashboardCrawler.java:381 | ztsj | 与 [2] 可能重复，需实测确认 |
| [5] | 同上 | 涨停原因+题材 | String | TradingDashboardCrawler.java:382 | ztyy | **龙虎独有**：含财联社电报+题材关联逻辑长文本 |
| [6] | 同上 | 封单（元） | Long | TradingDashboardCrawler.java:383 | fd | 涨停封单金额 |
| [7] | 同上 | 最大封单（元） | Long | TradingDashboardCrawler.java:384 | zdfd | 当日最大封单金额 |
| [8] | 同上 | 主力净额（元） | Long | TradingDashboardCrawler.java:385 | zlje | |
| [9] | 同上 | 主力买入（元） | Long | TradingDashboardCrawler.java:386 | zlmr | |
| [10] | 同上 | 主力卖出（元） | Long | TradingDashboardCrawler.java:387 | zlmc | |
| [11] | 同上 | 成交额（元） | Long | TradingDashboardCrawler.java:388 | cje | |
| [12] | 同上 | 所属板块 | String | TradingDashboardCrawler.java:389 | ssbk | |
| [13] | 同上 | 实际流通市值（元） | Double | TradingDashboardCrawler.java:390 | sjlt | |
| [14] | 同上 | 实际换手率（%） | Double | TradingDashboardCrawler.java:391 | sjhs | |
| [15] | 待确认 | 预留/未知 | — | — | — | 需实测抓包确认 |
| [16] | 待确认 | 题材命中（概念名） | String | — | theme | 对应 spec §3.3 zt_pool.theme |
| [17] | 同上 | 振幅（%） | Double | TradingDashboardCrawler.java:393 | zf | |
| [18] | 同上 | 涨停状态（连板数） | String | TradingDashboardCrawler.java:395-408 | limit_up_status | 若空则用板块类型推导 "N 连板" |
| [19] | 同上（index 20） | 板块涨停数量 | Int | TradingDashboardCrawler.java:380 | bkztsl | 注意：Java 代码用 item.get(20)，即第 21 个元素 |

> **注意**：Java 代码中 `item.size() >= 20` 且 `item.get(20)` 取板块涨停数量，实际数组可能 ≥21 元素。T-R4 需实测确认精确列数。

### nums 对象字段（情绪指标直采）

| JSON 路径 | 语义 | 类型 | 映射目标表字段 |
|-----------|------|------|--------------|
| nums.SZJS | 上涨家数 | Int | sentiment_daily.up_cnt |
| nums.XDJS | 下跌家数 | Int | sentiment_daily.down_cnt |
| nums.ZT | 涨停家数 | Int | sentiment_daily.limit_up |
| nums.DT | 跌停家数 | Int | sentiment_daily.limit_down |
| nums.ZBL | 炸板率（%） | Double | sentiment_daily.broken_rate |
| nums.yestRase | 昨日涨停今表现（%） | Double | sentiment_daily.yest_rase |

---

## 2. Emotion（情绪 30 日序列）

**端点**: `GetMoneyDate / Emotion`（st=30）
**主机**: `apphis.longhuvip.com`
**认证**: DeviceID，凭证放在本机 secrets.yaml
**响应结构**: `ZY[]` 30 个交易日对象

| JSON 路径 | 语义 | 类型 | 映射目标表字段 | 来源 |
|-----------|------|------|--------------|------|
| ZY[].CGL | 打板成功率（%） | Double | sentiment_daily.dbcgl | TradingDashboardCrawler.java:246 |
| ZY[].YLL | 打板盈利率（%） | Double | sentiment_daily.dbyll | TradingDashboardCrawler.java:247 |
| ZY[].Day | 日期 | String | sentiment_daily.date | |
| ZY[].ZRLBJ | 昨日连板今表现（%） | Double | sentiment_daily.zrlbjbx（参考） | |

---

## 3. RealRankingInfo（板块排名 19 列数组）

**端点**: `RealRankingInfo / ZhiShuRanking`（ZSType=7 申万）
**主机**: `apphwhq.longhuvip.com`
**认证**: DeviceID
**特殊**: 支持 `Date` 历史参数（可回填历史）
**响应结构**: `list[]` 数组，每元素 19 列数组

### 19 列数组语义对照

| 列序号 | Java 解析位置 | 语义 | 类型 | 来源代码 | MySQL 落库字段 |
|--------|-------------|------|------|---------|---------------|
| [0] | TradingDashboardCrawler.processPlateMovementList | 板块代码 | String | TradingDashboardCrawler.java:339 | code |
| [1] | 同上 | 板块名称 | String | TradingDashboardCrawler.java:340 | name |
| [2] | 同上 | 强度 | Long | TradingDashboardCrawler.java:333 | strong |
| [3] | 待确认 | 家数（板块内个股数） | Int | — | — |
| [4] | 同上 | 涨幅（%） | Double | TradingDashboardCrawler.java:334 | growth_rate |
| [5] | 同上 | 成交额（元） | Long | TradingDashboardCrawler.java:336 | cje |
| [6] | 同上 | 主力净额（元） | Long | TradingDashboardCrawler.java:335 | large_force |
| [7] | 待确认 | 超大单净额（元） | Long | — | — |
| [8-11] | 待确认 | 预留 | — | — | — |
| [12] | 同上 | 300 万大单净额（万元） | Long | TradingDashboardCrawler.java:338 | large_force_300 |
| [13-17] | 待确认 | 预留 | — | — | — |
| [18] | 待确认 | 总市值（元） | Long | — | — |

> **注意**：Java 代码中 `item.size() >= 7` 为最小解析条件，`item.size() >= 13` 时取 large_force_300。完整 19 列语义需 T-R4 实测冻结。

---

## 4. MorningBiddingList（竞价列表）

**端点**: `MorningBiddingList / HomeDingPan`（Type=4）
**主机**: `apphwhq.longhuvip.com`
**认证**: 账号凭证，放在本机 secrets.yaml
**响应结构**: `info[]` 数组，每元素为 JSONArray

### 竞价委买数组语义（落库 stock_market_data）

| 列序号 | Java 解析位置 | 语义 | 类型 | 来源代码 | MySQL 落库字段 | 中文注释 |
|--------|-------------|------|------|---------|---------------|---------|
| [0] | TradingDashboardCrawler.processStockEntrustPurchaseDataResponse | 股票代码 | String | TradingDashboardCrawler.java:290 | code | 个股代码 |
| [1] | 同上 | 股票名称 | String | TradingDashboardCrawler.java:291 | name | 个股名称 |
| [2] | 待确认 | 预留 | — | — | — | |
| [3] | 同上 | 竞价涨幅（%） | Double | TradingDashboardCrawler.java:293 | jjzf | 竞价涨幅 |
| [4] | 同上 | 涨停委买额（元） | Double | TradingDashboardCrawler.java:292 | ztwme | 涨停委买额 |
| [5] | 同上 | 实时涨幅（%） | Double | TradingDashboardCrawler.java:294 | sszf | 实时涨幅 |
| [6] | 同上 | 竞价净额（元） | Double | TradingDashboardCrawler.java:295 | jjje | 竞价净额 |
| [7] | 同上 | 竞价换手（%） | Double | TradingDashboardCrawler.java:296 | jjhs | 竞价换手 |
| [8] | 同上 | 竞价成交额（元） | Double | TradingDashboardCrawler.java:297 | jjcje | 竞价成交额 |
| [9] | 同上 | 9:20 后涨停委买（元） | Double | TradingDashboardCrawler.java:298 | twenty_ztwme | 20 分后涨停委买（撤单检测） |
| [10] | 待确认 | 预留 | — | — | — | |
| [11] | 同上 | 所属板块 | String | TradingDashboardCrawler.java:299 | ssbk | 所属板块 |
| [12] | 同上 | 实际流通市值（元） | Double | TradingDashboardCrawler.java:300 | sjlt | 实际流通 |

---

## 5. DailyLimitPerformance / HomeDingPan（龙头异动）

**端点**: `DailyLimitPerformance / HomeDingPan`（Type=4/20, st=2000）
**主机**: `apphwhq.longhuvip.com`
**认证**: DeviceID
**响应结构**: `info[0][]` 数组，每元素 ≥20 列

### 龙头异动数组语义（落库 stock_market_data, quotations_type=2）

| 列序号 | Java 解析位置 | 语义 | 类型 | 来源代码 | MySQL 落库字段 |
|--------|-------------|------|------|---------|---------------|
| [0] | TradingDashboardCrawler.processDragonHeadStocksResponse | 股票代码 | String | TradingDashboardCrawler.java:375 | code |
| [1] | 同上 | 股票名称 | String | TradingDashboardCrawler.java:376 | name |
| [2-3] | 待确认 | 预留 | — | — | — |
| [4] | 同上 | 涨停时间 | String | TradingDashboardCrawler.java:381 | ztsj |
| [5] | 同上 | 涨停原因 | String | TradingDashboardCrawler.java:382 | ztyy |
| [6] | 同上 | 封单（元） | Long | TradingDashboardCrawler.java:383 | fd |
| [7] | 同上 | 最大封单（元） | Long | TradingDashboardCrawler.java:384 | zdfd |
| [8] | 同上 | 主力净额（元） | Long | TradingDashboardCrawler.java:385 | zlje |
| [9] | 同上 | 主力买入（元） | Long | TradingDashboardCrawler.java:386 | zlmr |
| [10] | 同上 | 主力卖出（元） | Long | TradingDashboardCrawler.java:387 | zlmc |
| [11] | 同上 | 成交额（元） | Long | TradingDashboardCrawler.java:388 | cje |
| [12] | 同上 | 所属板块 | String | TradingDashboardCrawler.java:389 | ssbk |
| [13] | 同上 | 实际流通市值 | Double | TradingDashboardCrawler.java:390 | sjlt |
| [14] | 同上 | 实际换手率（%） | Double | TradingDashboardCrawler.java:391 | sjhs |
| [15-16] | 待确认 | 预留 | — | — | — |
| [17] | 同上 | 振幅（%） | Double | TradingDashboardCrawler.java:393 | zf |
| [18] | 同上 | 涨停状态 | String | TradingDashboardCrawler.java:395-408 | limit_up_status |
| [19] | 待确认 | 预留 | — | — | — |
| [20] | 同上 | 板块涨停数量 | Int | TradingDashboardCrawler.java:380 | bkztsl |

---

## 6. MySQL 表中文注释参照

### speculative_performance_data（投机表现数据）

| 字段 | 类型 | 中文注释 | 来源 |
|------|------|---------|------|
| id | VARCHAR | 主键 ID | SpeculativePerformanceData.java:22 |
| time | VARCHAR | 时间（Unix 时间戳） | SpeculativePerformanceData.java:27 |
| jrztpbl | DECIMAL | 今日涨停破板率（%） | SpeculativePerformanceData.java:32 |
| zrztjbx | DECIMAL | 昨日涨停今表现（%） | SpeculativePerformanceData.java:37 |
| zrlbjbx | DECIMAL | 昨日连板今表现（%） | SpeculativePerformanceData.java:42 |
| zrpbjbx | DECIMAL | 昨日破板今表现（%） | SpeculativePerformanceData.java:47 |
| dbcgl | DECIMAL | 打板成功率（%） | SpeculativePerformanceData.java:52 |
| dbyll | DECIMAL | 打板盈利率（%） | SpeculativePerformanceData.java:57 |
| date | DATE | 日期 | SpeculativePerformanceData.java:62 |

### stock_market_data（个股竞价委买/龙头异动）

| 字段 | 类型 | 中文注释 | 来源 |
|------|------|---------|------|
| id | VARCHAR | 主键 ID | StockMarketData.java:22 |
| code | VARCHAR | 个股代码 | StockMarketData.java:27 |
| name | VARCHAR | 个股名称 | StockMarketData.java:32 |
| ztwme | DOUBLE | 涨停委买额 | StockMarketData.java:37 |
| twenty_ztwme | DOUBLE | 20 分后涨停委买 | StockMarketData.java:42 |
| jjzf | DOUBLE | 竞价涨幅 | StockMarketData.java:47 |
| sszf | DOUBLE | 实时涨幅 | StockMarketData.java:52 |
| ssbk | VARCHAR | 所属板块 | StockMarketData.java:57 |
| jjje | DOUBLE | 竞价净额 | StockMarketData.java:62 |
| jjcje | DOUBLE | 竞价成交额 | StockMarketData.java:67 |
| jjhs | DOUBLE | 竞价换手 | StockMarketData.java:72 |
| sjlt | DOUBLE | 实际流通 | StockMarketData.java:77 |
| ztsj | VARCHAR | 涨停时间 | StockMarketData.java:82 |
| ztyy | VARCHAR | 涨停原因 | StockMarketData.java:87 |
| bkztsl | INT | 板块涨停数量 | StockMarketData.java:92 |
| fd | BIGINT | 封单 | StockMarketData.java:97 |
| zdfd | BIGINT | 最大封单 | StockMarketData.java:102 |
| zlje | BIGINT | 主力净额 | StockMarketData.java:107 |
| zlmr | BIGINT | 主力买入 | StockMarketData.java:112 |
| zlmc | BIGINT | 主力卖出 | StockMarketData.java:117 |
| cje | BIGINT | 成交额 | StockMarketData.java:122 |
| zf | DOUBLE | 振幅 | StockMarketData.java:127 |
| sjhs | DOUBLE | 实际换手 | StockMarketData.java:132 |
| date | DATE | 日期 | StockMarketData.java:137 |
| limit_up_status | VARCHAR | 涨停状态 | StockMarketData.java:142 |
| quotations_type | INT | 行情类型（1:竞价异动 2:龙头异动） | StockMarketData.java:147 |

### plate_movement（板块异动）

| 字段 | 类型 | 中文注释 | 来源 |
|------|------|---------|------|
| id | VARCHAR | 主键 ID | PlateMovement.java:22 |
| time | VARCHAR | 时间 | PlateMovement.java:27 |
| code | VARCHAR | 板块代码 | PlateMovement.java:32 |
| name | VARCHAR | 板块名称 | PlateMovement.java:37 |
| strong | BIGINT | 强度 | PlateMovement.java:42 |
| growth_rate | DOUBLE | 涨幅（接口原始数值） | PlateMovement.java:47 |
| large_force | BIGINT | 主力净额（元） | PlateMovement.java:52 |
| cje | BIGINT | 成交额（接口原始数值） | PlateMovement.java:57 |
| large_force_300 | BIGINT | 300 万大单净额（万元） | PlateMovement.java:62 |
| date | DATE | 日期 | PlateMovement.java:67 |

---

## 7. 待 T-R4 冻结事项

1. **DailyLimitResumption 精确列数**：Java 代码用 `item.get(20)` 取第 21 元素，但 `size() >= 2` 即解析——需实测确认完整列数与各列语义
2. **RealRankingInfo [3]/[7-11]/[13-17] 列语义**：Java 代码未解析这些位置，需抓包确认
3. **MorningBiddingList [2]/[10] 列语义**：同上
4. **涨停时间戳格式**：[2] 和 [4] 可能重复，需确认哪个是首封时间、哪个是最后封板时间
5. **涨停原因文本编码**：[5] 含中文+特殊字符，需确认编码格式（UTF-8/Unicode 转义）

---

*草稿版本: v0.1 | 创建: 2026-10-07 | 墨测*
*下一步: 铸码 T-R4 实测抓包后冻结最终版 → docs/field_dict_longhu.md*

---

## 2026-10-11 冻结附录

草稿里未实测的列仍标「待确认」，不进 DDL。`bidding_list` / `theme_heat` 不加扩展列。

`RealRankingInfo`（ZSType=7）当日涨跌幅在 `[3]`，`[18]` 与它相同。2026-10-09、10-12、10-13 银行 801027 的 `[3]` 与东财 BK1283 逐日一致（-1.06 / +1.99 / -1.01）。`[4]` 不是当日涨跌幅，多数落在 -0.5 到 2 之间。`[0]` 代码，`[1]` 名称，`[2]` 强度，`[5]` 成交额（元），`[6]` 主力净额（元）。

当晚冒烟（行数为解析后的 list 长度）：

| 端点 | 结果 |
|------|------|
| Radar | 15 |
| PopularityList / GetRQZ | 200 |
| PlateMovement / RealRankingInfo | 80（首页） |
| MarketWind / FengK | 1 |
| StrongestWind / FengKBest | 1 |
| WindVane / ZhiShuStockList_W8 | 1 |
| IndexTrend / GetZsTrend | 1 |
| Emotion | 空。响应只有空的 list，没有 ZY。不改用空 list 冒充序列 |
| DailyLimitResumption | 空 |
| DailyLimitPerformance | 响应不是 JSON |
| YouZi、GetStockPanKou_Narrow | 按任务保持不调用 |
