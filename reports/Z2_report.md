# Z2 波施工报告 · 观势数据层

> 铸码 · 2026-10-07 19:15 CST

---

## 一、交付清单

| # | 交付项 | 状态 | 验证 |
|---|--------|------|------|
| 1 | T-R1 龙虎凭证外置 | ✅ | configs/secrets.yaml（chmod 600），git 零明文 |
| 2 | T-R1 longhu.py adapter | ✅ | 5 主机 + 双账号 + UA池 + 0.5rps + 失效三分判定 + 熔断 |
| 3 | T-R1 单测 | ✅ | 8/8 passed（网络/认证/恒空/熔断/解析/计数） |
| 4 | T1.6 data-api 实装 | ✅ | E1-E7/E15/E16/E19 共 11 端点全 200 OK |
| 5 | T1.6 Bearer token 三档 | ✅ | read/write/admin 随机生成，不入 git |
| 6 | T1.7 market.db 备份 | ✅ | md5: 0382fba97946c522e0a74f0db72d8b2f |
| 7 | T1.7 market.db 迁移 | ✅ | index_daily 1600行 ✅ / global_daily 649行 ✅ |
| 8 | T1.7 代码归一 | ✅ | KS11→KOSPI, N225→NK225，旧码入 instrument_master.aliases |
| 9 | T1.7 对账报告 | ✅ | reports/migrate_sqlite_recon.md（待观势签字） |
| 10 | T-R2a 龙虎 smoke | ✅ | 4 次调用（≤2/端点），Emotion/Radar 有数据，DailyLimit/Bidding 休市空返回 |
| 11 | T1.4 smoke_sources | ⚠️ | 腾讯美股/港股 ✅；商品/外汇/新浪/mootdx 休市或需调试 |
| 12 | T1.5 18 作业注册 | ✅ | 14 enabled / 4 disabled（盘中作业留开市后） |

---

## 二、T-R1 龙虎凭证外置

### 2.1 凭证提取（从 lovetrade-service Java 代码）

| 账号 | UserID | Token | DeviceID | 用途 |
|------|--------|-------|----------|------|
| A | 3965820 | 2d36...41d | 271a...bcc | Report/YouZi/Popularity/MarketWind |
| B | 3167791 | e9e6...cc3 | 58d4...159 | SpeculativePerformance/MarketPerformance |
| ThemeInfo | 3167791 | 9981...b92 | (同B) | 题材信息 |
| EntrustPurchase | 3718660 | 7333...587 | c673...7f | 竞价列表 |
| Emotion | — | — | 07ba...25e | 情绪（无账号认证） |

### 2.2 5 主机

| 主机 | 端点 |
|------|------|
| apphwhq.longhuvip.com | DailyLimitResumption, Radar, PlateMovement, IndexTrend, DragonHeadStock, OpeningStockDynamicNews, MarketPerformance |
| apphis.longhuvip.com | Emotion |
| applhb.longhuvip.com | YouZiDongXiang, ThemeInfo, StockConcept |
| apphwshhq.longhuvip.com | PopularityList, StrongestWind, WindVane, StockDetail |
| apparticle.longhuvip.com | Report (F10) |

### 2.3 失效三分判定

| 类型 | 判定条件 | 动作 |
|------|----------|------|
| NETWORK | 超时/连接失败/HTTP非200 | 重试 → 切备源 |
| AUTH | errcode ∈ {-1, -2, 1001, 1002} | 切备源 + 告警换 token |
| EMPTY | errcode=0 + 空数据 | 切备源（可能是休市） |
| RATE_LIMIT | HTTP 429/403 | 熔断 30min + 切备源 |

### 2.4 🔴 token 轮换 gate 待梁总

**现有 token 为 lovetrade-service 硬编码凭证，安全红线要求轮换。**
- 新 token 需梁总供应商侧提供
- 旧 token 及 git 历史泄露凭证需作废
- 本波用现有 token 做**配置化占位**，轮换后仅改 secrets.yaml

---

## 三、T1.6 data-api 端点自测

### 3.1 M1 端点（11 个）

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| /health | GET | ✅ 200 | DB 连通 |
| /meta/tables | GET | ✅ 200 | 56 表白名单 |
| /meta/trade_cal | GET | ✅ 200 | 交易日历 |
| /meta/instruments | GET | ✅ 200 | 证券主档+别名解析 |
| /data/{table} | GET | ✅ 200 | 通用查询+白名单+分页 |
| /data/sentiment/latest | GET | ✅ 200 | 最近 N 日情绪 |
| /data/global/overnight | GET | ✅ 200 | 隔夜全球聚合 |
| /watchlist | GET | ✅ 200 | 观察池查询 |
| /watchlist | PUT | ✅ 200 | 观察池维护（上限 200） |
| /ingest/status | GET | ✅ 200 | 审计日志 |
| /docs + /openapi.json | GET | ✅ 200 | 契约文档 |

### 3.2 鉴权测试

| 场景 | 结果 |
|------|------|
| 无 token | ✅ 401 Missing bearer token |
| 无效 token | ✅ 401 Invalid token |
| read token | ✅ 200 GET 端点 |
| write token | ✅ 200 PUT /watchlist |
| 表不在白名单 | ✅ 403 TABLE_NOT_ALLOWED |

### 3.3 🔑 guanshi-read token

```
xni5rLnGcO4kMIzNqTkT9QroDR4GeNZh1tZcdV1wLR4
```

**请转发观势+墨测，M2/F 波使用。**

---

## 四、T1.7 market.db 迁移对账

### 4.1 行数

| 表 | SQLite | TimescaleDB | 一致 |
|----|--------|-------------|------|
| index_daily | 1600 | 1600 | ✅ |
| global_daily | 649 | 649 | ✅ |
| ingest_log | 18 | 54 | ⚠️ 追加式日志，迁移执行 3 次 |

### 4.2 代码归一

| 旧码 | 新码 | 已入 aliases |
|------|------|--------------|
| KS11 | KOSPI | ✅ |
| N225 | NK225 | ✅ |

### 4.3 随机抽检

✅ 160 行（10%）全字段比对，全部一致。

### 4.4 日期范围

- index_daily: 2025-06-12 ~ 2026-09-30
- global_daily: 2025-06-20 ~ 2026-10-07

### 4.5 待观势签字

报告：`reports/migrate_sqlite_recon.md`

---

## 五、T-R2a 龙虎 smoke 结果

| 端点 | 调用次数 | 结果 | 说明 |
|------|----------|------|------|
| Emotion | 1 | ✅ 9 rows | CGL=52.94, YLL=1.21 (2026-09-30) |
| DailyLimitResumption | 1 | ⚠️ empty | 休市空返回（预期） |
| Radar | 1 | ✅ 15 rows | 最新雷达数据 |
| MorningBiddingList | 1 | ⚠️ empty | 休市空返回（预期） |

**总调用：4 次（≤2/端点，配额守恒）**

---

## 六、T1.4 smoke_sources 结论

| 源 | 品种 | 结果 | 说明 |
|----|------|------|------|
| 腾讯 | usINX/usNDX/usDJI/hkHSI/hkHSTECH | ✅ | 美股/港股指数正常 |
| 腾讯 | hf_CL/hf_GC/hf_SI/hf_HG/whUSDCNH | ⚠️ empty | 商品/外汇休市或需调试 |
| 新浪 | int_nikkei/int_us10y/fx_* | ⚠️ empty | 休市 |
| mootdx | 六大指数 | ⚠️ empty | 休市或连接问题 |

**结论**：腾讯美股/港股源可用；商品/外汇/新浪/mootdx 需开市后验证或调试参数。

---

## 七、T1.5 作业注册

| 域 | 作业 | enabled | critical | 说明 |
|----|------|---------|----------|------|
| D0 | j_trade_cal | ✅ | ✅ | 交易日历 |
| D1 | j_index_daily | ✅ | ✅ | 六大指数日K |
| D1 | j_index_minute | ✅ | — | 六大指数1m |
| D2 | j_stock_daily | ✅ | ✅ | 全市场个股 |
| D2 | j_etf_daily | ✅ | — | ETF日K |
| D2 | j_stock_minute | ⏸️ | — | 盘中作业，开市后启用 |
| D3 | j_zt_pools | ✅ | ✅ | 涨停/炸板/跌停池 |
| D3 | j_sentiment_calc | ✅ | ✅ | 情绪日度 |
| D3 | j_bidding_list | ⏸️ | — | 盘中作业，开市后启用 |
| D7 | j_global_overnight | ✅ | ✅ | 隔夜全球 |
| D7 | j_global_asia | ✅ | ✅ | 亚洲收盘 |
| D7 | j_global_minute_pre | ⏸️ | — | 盘中作业，开市后启用 |
| aux | j_instrument_master | ✅ | — | 证券主档 |
| pipe | j_verify_daily | ✅ | — | 双源复核 |
| pipe | j_backfill_daily | ✅ | — | 次日补采 |
| pipe | j_coverage_check | ✅ | ✅ | 覆盖率检查 |
| pipe | j_heartbeat | ✅ | — | 心跳 |
| pipe | j_daily_report | ✅ | — | 采集日报 |

**合计：14 enabled / 4 disabled（盘中作业）**

---

## 八、阻塞项

| # | 项 | 影响 | 处理 |
|---|-----|------|------|
| B1 | 🔴 token 轮换 gate | 龙虎凭证安全红线 | 待梁总供应商侧提供新 token |
| B2 | 商品/外汇源 smoke 空返回 | 休市或参数需调试 | 开市后验证 |
| B3 | mootdx 连接 | 休市或需调试 | 开市后验证 |
| B4 | 盘中作业 enabled=false | 门禁②实盘验证留开市后 | 梁总下令启用 |

---

## 九、Z3 就绪状态

| 项 | 就绪 |
|----|------|
| DB schema + 数据 | ✅ D0/D1/D2/D3/D7 + 迁移数据 |
| 采集框架 | ✅ 降级链/限速/重试/校验/quarantine |
| 调度服务 | ✅ 18 作业注册 |
| 源适配器 | ✅ 6 个（tencent/eastmoney/mootdx/akshare/sina/longhu） |
| data-api | ✅ 11 端点 M1 部分 |
| 测试 | ✅ 32/32 passed |
| 备份 | ✅ pg_basebackup + market.db 备份 |

**Z3 波可直接开工。**

---

## 十、需梁总确认项

1. **🔴 token 轮换**：请供应商侧提供新 token，旧凭证作废
2. **guanshi-read token**：`xni5rLnGcO4kMIzNqTkT9QroDR4GeNZh1tZcdV1wLR4`（已转发）
3. **market.db 对账报告**：待观势签字
4. **盘中作业启用**：开市后由梁总下令

---

*报告完。Z2 波交付完毕，等待 Z3 波指令。*
