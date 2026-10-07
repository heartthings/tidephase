# 观势数据层验收测试套件

> 墨测（MoTest）编写。配合技术方案附录 B 验收标准对齐表。

## 执行顺序

| 序号 | 脚本 | 验收标准 | 前置条件 | 预计耗时 |
|------|------|---------|---------|---------|
| 1 | `test_completeness.py` | ① 完整性 | PG + trade_cal + instrument_master 已初始化 | 1-5 min |
| 2 | `test_accuracy.py` | ② 准确性 | PG + stock_daily 有数据 + 网络可访问 akshare | 5-15 min（含限速等待） |
| 3 | `test_timeliness.py` | ③ 时效 | PG + ingest_log 有记录（至少运行 1 天后） | <1 min |
| 4 | `test_audit.py` | ⑤ 审计 | PG + raw 归档目录存在 | 1-3 min |
| 5 | `docs/replay_witness_template.md` | ④ 回放见证 | 六案例数据面全部就绪（M3） | 人工见证 |

## 环境变量

```bash
# PG 直连（只读账号）
export PG_HOST=127.0.0.1
export PG_PORT=15432
export PG_DB=market_tsdb
export PG_USER=duser_reader
export PG_PASS="从 configs/secrets.yaml 获取"

# data-api（备用通道）
export DATA_API_BASE=http://127.0.0.1:8787
export DATA_API_TOKEN="从督军获取"

# raw 归档目录（审计追溯用）
export RAW_ARCHIVE_ROOT=/home/hello/application/dev/market-datalayer/data/raw
```

## 依赖

```bash
pip install psycopg2-binary  # PG 直连
pip install akshare          # 准确性抽检外部源（可选，无则用腾讯 qt）
# 标准库：json, gzip, urllib, argparse, random, datetime, pathlib
```

## 快速开始

```bash
# 所有脚本支持 --help
python tests/acceptance/test_completeness.py --help

# 干跑（空库/无 API 时优雅报错）
python tests/acceptance/test_completeness.py --start 2026-07-01 --end 2026-10-07
python tests/acceptance/test_accuracy.py --start 2026-09-01 --end 2026-10-07
python tests/acceptance/test_timeliness.py --days 20
python tests/acceptance/test_audit.py --sample 20

# JSON 输出（便于程序化处理）
python tests/acceptance/test_completeness.py --start 2026-07-01 --end 2026-10-07 --json
```

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | PASS 或 BLOCKED（等待构建完成，非错误） |
| 1 | FAIL（验收未达标） |

## 红线

- 所有脚本**只读**，永不写库
- 外部接口低频调用（≤1 rps）
- 不调用龙虎 longhuvip 任何端点
- lovetrade-service 与观势工作区只读

## 阻塞处理

当 PG/API 未就绪时，脚本输出 `[BLOCKED]` 状态和明确原因，不崩溃。
阻塞项记入最终报告。

---

*创建: 2026-10-07 | 墨测*
