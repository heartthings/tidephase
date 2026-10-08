# M2 Phase2 lovetrade 迁移独立抽检报告

> 执行时间: 2026-10-08 08:56:38

> 执行人: 墨测（MoTest）

> 方法: 独立连接远程 MySQL vs TimescaleDB，不依赖铸码报告

---

## 对账汇总

| MySQL 表 | PG 表 | 里程碑 | MySQL 行数 | PG 迁移行数 | COUNT 匹配 | 状态 |
|---------|-------|--------|-----------|------------|-----------|------|
| index_trend | index_minute | M1 | 52,196 | 39,182 | False | ❌ |
| market_message | news_telegraph | M2 | 69,120 | 9,738 | False | ❌ |
| opening_stock_dynamic_news | news_telegraph | M2 | 9,738 | 9,738 | True | ✅ |
| market_radar | theme_heat | M2 | 296,749 | 0 | False | ❌ |
| plate_movement | sector_daily | M2 | 11,318 | 11,318 | True | ✅ |
| trading_calendar | trade_cal | M1 | 365 | 0 | False | ❌ |
| catalyst_impacts | prediction | M2 | 1,234 | 328 | False | ❌ |
| topic_stock | stock_sector_map | M2 | 15,241 | 15,241 | True | ✅ |

## quarantine 检查

- lovetrade-mysql 隔离行数: 13014


## 判定

**状态**: FAIL ❌

- COUNT 不一致的表需进一步排查

- 13014 行被隔离


---

*报告生成: 2026-10-08 08:56:38 | 墨测*
