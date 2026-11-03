# 采集与补数

日常启动见仓库根目录 [README.zh-CN.md](../README.zh-CN.md)。这里只写补跑和重启。

## 立刻跑一条作业

在 `ops` 目录，日期用交易日：

```bash
docker compose exec market-sched python -c "
from dworker.core.runner import execute_job
print(execute_job('j_zt_pools', trigger='manual', extra_params={'date':'2026-11-03'}))
"
```

非交易日会跳过。源没有数就记缺数，不用别的日子填。

## 改完代码

```bash
docker compose restart market-api      # 改了 data_api
docker compose restart market-sched    # 改了 dworker、dsched 或 db/seed_jobs.yaml
```

新作业要写进 `db/seed_jobs.yaml`，重启调度后才会注册。

## 看是否活着

```bash
curl -s http://127.0.0.1:8787/health
docker compose ps
```

最近一天的作业成败在盘中的「数据覆盖」看板，也可以查 `ingest_log`。
