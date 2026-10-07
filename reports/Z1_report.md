# Z1 波施工报告 · 观势数据层基建

> 铸码 · 2026-10-07 18:55 CST

---

## 一、交付清单

| # | 交付项 | 状态 | 验证 |
|---|--------|------|------|
| 1 | 仓库脚手架 | ✅ | `/home/hello/application/dev/market-datalayer`，git init，目录结构完整，首个 commit `5d080fd` |
| 2 | docker-compose 四服务 | ✅ | market-tsdb (healthy) / market-sched (healthy) / market-worker (up) / market-api (up) |
| 3 | DB 初始化 + 四角色 | ✅ | duser_writer / duser_reader / duser_admin / duser_d12writer 密码随机生成 |
| 4 | V001 migration | ✅ | 31 张表 + hypertable + 压缩/保留策略 + 连续聚合视图 + D12 表 |
| 5 | Migration 幂等验证 | ✅ | 连续跑两遍输出一致，0 errors |
| 6 | 采集框架 (dworker/core) | ✅ | 降级链/令牌桶限速/3次退避重试/校验引擎/quarantine/raw归档/ingest_log |
| 7 | 5个源适配器骨架 | ✅ | tencent/eastmoney/mootdx/akshare/sina（longhu 留待 Z2） |
| 8 | dsched 调度服务 | ✅ | APScheduler + job_registry 种子数据 + 心跳 |
| 9 | 漏跑检测演示 | ✅ | 伪造 3 个 critical 作业无运行记录 → 服务启动检出并告警 |
| 10 | 单元测试 | ✅ | **24/24 passed** (降级链/quarantine/幂等/限速/漏跑检测) |
| 11 | pg_basebackup 首备 | ✅ | 4.7MB base + WAL → `/home/hello/backups/market_tsdb/basebackup_20261007/` |
| 12 | 凭证安全 | ✅ | secrets.yaml (chmod 600) + .env 均 .gitignore，git 零明文 |

---

## 二、Docker Compose 状态

```
NAME            STATUS                    PORTS
market-tsdb     Up (healthy)              127.0.0.1:15432->5432/tcp
market-sched    Up (healthy)              —
market-worker   Up (health: starting)     —
market-api      Up (health: starting)     127.0.0.1:8787->8787/tcp
```

- market-tsdb: TimescaleDB PG16, timezone=Asia/Shanghai, shared_buffers=2GB
- market-sched: 调度服务，已检出 3 个 critical 作业漏跑（首次启动预期行为）
- market-worker/api: Z2 波实装占位，本波 keepalive

---

## 三、数据库验证

### 3.1 表清单（31 张）

```
辅助: instrument_master, watchlist
D0:   trade_cal, session_def
D1:   index_daily [HT], index_minute [HT]
D2:   stock_daily [HT], stock_minute [HT], etf_daily [HT]
D3:   zt_pool, zb_pool, dt_pool, yzt_pool, sentiment_daily, bidding_list [HT]
D7:   global_daily, global_minute [HT]
管道: job_registry, ingest_log [HT], quarantine [HT], verify_source, verify_diff
D12:  cognition, prediction, base_rate
系统: schema_migrations
```

### 3.2 角色权限

| 角色 | 权限 | 验证 |
|------|------|------|
| duser_writer | SELECT/INSERT/UPDATE 全部表 | ✅ |
| duser_reader | SELECT only + statement_timeout=30s | ✅ |
| duser_admin | ALL PRIVILEGES | ✅ |
| duser_d12writer | cognition/prediction/base_rate INSERT/UPDATE | ✅ |

### 3.3 Hypertable + 压缩/保留

| 表 | chunk | 压缩 | 保留 |
|----|-------|------|------|
| index_daily / stock_daily / etf_daily / bidding_list | 1年 | 30d后 segmentby=code | 全留 |
| index_minute / stock_minute / global_minute | 7天 | 7d后 | 3年 |
| ingest_log / quarantine | 1月 | — | 3年 |

### 3.4 Migration 幂等验证

```
=== First run ===
INSERT 0 0  (V001 already applied)
0 errors

=== Second run ===
INSERT 0 0  (V001 already applied)
0 errors

✅ 连续两遍输出一致
```

---

## 四、漏跑检测演示

```
$ python3 -c "from dsched.main import detect_missed_runs; ..."

⚠️ MISSED: j_index_daily (critical, domain=D1) has no runs in last 24h
⚠️ MISSED: j_stock_daily (critical, domain=D2) has no runs in last 24h
⚠️ MISSED: j_global_overnight (critical, domain=D7) has no runs in last 24h

Detected 3 missed critical jobs:
  ⚠️  j_index_daily (domain=D1)
  ⚠️  j_stock_daily (domain=D2)
  ⚠️  j_global_overnight (domain=D7)
```

---

## 五、单元测试

```
24 passed in 0.62s

tests/test_degradation.py     6 passed  (降级链：主源成功/主败备成/全败MISS/空返回降级/缺adapter跳过/schema探针)
tests/test_quarantine.py      6 passed  (校验：有效行通过/OHLC自洽/量级/非空/软告警/批量)
tests/test_rate_limiter.py    6 passed  (令牌桶：基本/限速/burst/默认配置/已知源/未知源)
tests/test_missed_detection.py 3 passed (漏跑：检出漏跑/有运行不报/非critical忽略)
tests/test_idempotent.py      3 passed  (幂等：upsert/不同日期/quarantine replay)
```

---

## 六、备份

```
/home/hello/backups/market_tsdb/basebackup_20261007/
├── base.tar.gz       4.7MB
├── pg_wal.tar.gz     17KB
└── backup_manifest   235KB
```

WAL-G 下载受阻（GitHub release 二进制不匹配当前环境），降级使用 `pg_basebackup`。

---

## 七、系统状态

| 项 | 值 |
|----|-----|
| Docker | 29.1.4, systemd enabled + active |
| Compose | v5.0.1 |
| 磁盘 | 5.0T 可用 |
| 内存 | 125G (可用 99G) |
| TSDB 端口 | 127.0.0.1:15432 |
| API 端口 | 127.0.0.1:8787 |
| Git commit | `5d080fd` |

---

## 八、阻塞项

| # | 项 | 影响 | Z2 处理 |
|---|-----|------|---------|
| B1 | WAL-G 二进制下载失败 | 仅影响 PITR 高级备份；pg_basebackup 基准备份已就绪 | 尝试其他版本或编译 |
| B2 | BIOS 通电自启 | 无法软件配置 | 需梁总/机房侧核实 |
| B3 | longhu.py 适配器 | Z1 不建（凭证外置先行） | Z2 T-R1 实装 |
| B4 | 盘中作业 enabled=false | 开市后由梁总下令启用 | Z2 按需开启 |

---

## 九、Z2 就绪状态

| 项 | 就绪 |
|----|------|
| DB schema | ✅ 全量 DDL + hypertable + 压缩/保留 |
| 采集框架 | ✅ 降级链/限速/重试/校验/quarantine |
| 调度服务 | ✅ job_registry 种子 + 漏跑检测 |
| 源适配器 | ⏳ 5/5 非龙虎源骨架就绪；longhu 待 Z2 |
| data-api | ⏳ 占位定义就绪；FastAPI 实装待 Z2 |
| 测试框架 | ✅ pytest 全绿 |
| 备份 | ✅ pg_basebackup 基准完成 |

**Z2 波可直接开工。**

---

## 十、需梁总/机房侧核实项

1. **BIOS 通电自启**：docker restart=always + systemd 已配置，但 BIOS 通电自启需机房侧确认
2. **远端备份副本**：D4 决策项，建议加远端第二副本（对象存储约 ¥10/月）
3. **龙虎凭证外置**：Z2 T-R1 硬门禁，需梁总提供新 token + 旧 token 作废

---

*报告完。Z1 波交付完毕，等待 Z2 波指令。*
