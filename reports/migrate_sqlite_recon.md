# market.db → market_tsdb 迁移对账报告

> 迁移时间：2026-10-07T19:09:34.984672
> 源文件：/home/hello/.qwenpaw/workspaces/guanshi/data/market.db
> 备份：/home/hello/backups/market_db_20261007/market.db

## 一、行数对账

| 表 | SQLite 行数 | TimescaleDB 行数 | 一致 |
|---|---|---|---|
| index_daily | 1600 | 1600 | ✅ |
| global_daily | 649 | 649 | ✅ |
| ingest_log | 18 | 54 | ❌ |

**结论**：❌ 存在差异，需排查

## 二、代码归一

| 旧码 | 新码 | 说明 |
|---|---|---|
| KS11 | KOSPI | 韩国综合指数 |
| N225 | NK225 | 日经225 |

旧码已写入 instrument_master.aliases。

## 三、随机抽检（10%）

✅ 随机抽检 160 行，全部一致。

## 四、边界日期抽查

- index_daily 日期范围：2025-06-12 ~ 2026-09-30
- global_daily 日期范围：2025-06-20 ~ 2026-10-07

## 五、待观势签字

本报告待观势确认后签字归档。

---
*迁移工具：tools/migrate_sqlite.py*