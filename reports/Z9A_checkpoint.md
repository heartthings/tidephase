# Z9-A 今夜清板 Checkpoint

> 开始时间：2026-10-10 21:30
> 指令：梁总直接指令，不规划不配速，干完为止
> 最终更新：2026-10-10 23:xx

---

## P0-1 T3.1 base_rate 聚合作业实装 ✅ commit e643b33

### 交付清单
| 项 | 状态 | 详情 |
|---|---|---|
| j_base_rate.py handler | ✅ | spec v1.0 口径，regime空→unclassified，horizon NULL→_unknown |
| seed_jobs.yaml 注册 | ✅ | 每周五18:00 |
| V003 补登记 schema_migrations | ✅ | |
| base_rate PK 修复 | ✅ | 加入 window_type |
| 手动实跑 | ✅ | 16行（8组×2窗口） |
| GET /data/base_rate | ✅ | 返回16行真实JSON |
| GET /calibration | ✅ | 返回月度分桶数据 |

### 数据实况
- prediction 344行 → 72hit/0miss → base_rate 16行
- regime 全为 unclassified（lovetrade迁移数据无regime_at_create）
- Wilson CI / reliability 均正确计算

---

## P0-2 Z9 lovetrade-web 接口改指 data-api ✅ commit f209d19

### 交付清单
| 项 | 状态 | 详情 |
|---|---|---|
| 盘点 web 端点 | ✅ | 55个URL映射完成 |
| lovetrade_routes 改造 | ✅ | /api/前缀 + code:0兼容 + Authorize header |
| .env baseURL 改指 | ✅ | http://127.0.0.1:8787 |
| 缺失端点补齐 | ✅ | note/trading-system/systemManage/public-catalyst/route |
| web build | ✅ | dist/ 已生成（1m12s） |
| import 校验 | ✅ | main.app 加载无误 |

### 部署阻塞项
- **market-api 需重启**（加载新 lovetrade_routes.py）→ 督军做
- **web 静态部署**：dist/ 需挂到 nginx 或起容器
- **systemManage 路由**：桩实现，返回空数据（web管理页面会显示空但不报错）

### 缺口清单
| Web URL | data-api 状态 | 说明 |
|---------|-------------|------|
| /api/catalyst/* | ✅ 已实现 | 映射到 cognition/prediction 表 |
| /api/market/* | ✅ 已实现 | radars/messages/dynamic-news/plate-movements |
| /api/note/* | ✅ 已实现 | CRUD + count/month + top |
| /api/home/summary | ✅ 已实现 | |
| /api/trading-system/* | ✅ 已实现 | 树形CRUD |
| /api/user/login | ✅ 已实现 | username+password → bearer token |
| /api/user/personal | ✅ 桩 | 返回默认admin |
| /api/auth/refreshToken | ✅ 桩 | 返回read token |
| /api/route/* | ✅ 桩 | 返回空路由（web用static路由模式） |
| /api/systemManage/* | ✅ 桩 | 返回空/默认数据 |
| /api/public/catalyst/* | ✅ 已实现 | 免鉴权 |

---

## P0-3 handler 补齐 ✅ commit f209d19

| Handler | 状态 | 详情 |
|---------|------|------|
| j_sentiment_calc | ⚠️ SKIP | 龙虎Emotion端点返回空（token可能过期），如实记录MISS |
| j_instrument_master | ✅ | akshare首跑5573只入库，total_active=5574 |
| session_def | ✅ | 10行静态配置已回填（SSE/SZSE交易时段） |
| j_news_feed | ⚠️ SKIP | eastmoney/cls源均不可用，保持enabled=false |
| j_zt_pools | ⚠️ SKIP | 需周一开盘（今日周六无数据） |

### 数据变化
| 表 | 之前 | 之后 |
|---|---|---|
| instrument_master | 1 | 5574 |
| session_def | 0 | 10 |
| sentiment_daily | 0 | 0（源不可用） |

---

## P0-4 竞价九字段确认 ✅ 无需改代码

### 现状
| 字段 | NOT NULL行数 | 总行数 | 说明 |
|------|------------|--------|------|
| twenty_ztwme | 100 | 5672 | 仅09:25终版(quotations_type=2)有值 |
| fd | 100 | 5672 | 同上 |
| zdfd | 100 | 5672 | 同上 |
| ztwme | 5672 | 5672 | 全部有值 |

### 周一重验就绪度
- 09:15 snap1: ✅ handler就绪（j_bidding_snap1）
- 09:20 snap2: ✅ handler就绪（j_bidding_snap2）
- 09:25 snap3: ✅ handler就绪（j_bidding_snap3 + j_bidding_list终版）
- 三时点 twenty_ztwme/fd/zdfd 预期从NULL变NOT NULL

---

## 待督军操作

1. **重启 market-api**（加载新 lovetrade_routes.py，55路由生效）
2. **重启 market-sched**（加载新 seed_jobs.yaml，j_base_rate/j_instrument_master 入库）
3. **部署 lovetrade-web dist/**（挂到nginx或起容器）
4. **确认龙虎Emotion token**（j_sentiment_calc 源不可用）

---

## Commit 记录
- `e643b33` [Z9A-P0-1] T3.1 base_rate聚合作业实装+首跑
- `f209d19` [Z9A-P0-3] handler补齐+lovetrade_routes改造+web build
