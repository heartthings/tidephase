# 运维手册

2026-10-11。恢复不走 WAL-G。梁总 D4：不做备份，恢复 = `data/raw` 归档加源端重采。

## 启停

```bash
cd /home/hello/application/dev/market-datalayer/ops
docker compose up -d
docker restart market-api      # 改 data_api 之后
docker restart market-sched    # 改 dsched 或 seed_jobs.yaml 之后
```

采集代码在 `dworker/`，挂进调度容器，改完不用重建镜像。新作业要写进 `db/seed_jobs.yaml`，重启 `market-sched` 才会注册。

## 补数

对已有 handler 的作业：

```bash
docker exec market-sched python -c "
from dworker.core.runner import execute_job
print(execute_job('j_zt_pools', trigger='manual', extra_params={'date':'2026-10-09'}))
"
```

非交易日写 SKIP，不落业务表。源没有数就记 MISS，不拿别的日子顶上。

## 限速和封禁

龙虎适配器在 HTTP 429 或 403 时熔断 30 分钟，然后走备源。东财请求按页间隔，不并发打满。熔断代码在 `dworker/adapters/longhu.py` 的 `_trigger_circuit_breaker`。

## 告警演练（2026-10-11）

- 磁盘 `/`：5.5T 里用了 169G，4%。
- `GET /health` 为 200。
- 连续 MISS 看 `ingest_log` 里 `status='MISS'`。北向从 2024-08-16 起就是这种，不是作业挂了。

## 新增作业

1. `dworker/jobs/j_名称.py` 里写 `run(...)`。
2. 在 `db/seed_jobs.yaml` 加一条。
3. `docker restart market-sched`。
4. 用上面的 `execute_job` 打一个交易日，确认 ingest OK、表有行、`data/raw` 有归档。
