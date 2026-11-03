# 观势

英文名 Tidephase。A 股行情数据层，以及一个 DeepSeek Harness 插件。插件把盘前、盘中、盘后画成可以拖动的看板。

只适配 **A 股**。使用前先读 [DISCLAIMER.zh-CN.md](DISCLAIMER.zh-CN.md)。English: [README.md](README.md).

开源入口是 Harness 里的 **观势**。本仓库带两个插件：

- `guanshi-board`：三块画布
- `guanshi-theme`：柔和浅色和深色

Harness 版本钉在官方 `@deepseek-ai/dsh@0.2.0-rc.2`。

## 从零启动

需要 Docker 和 Docker Compose。在仓库根目录：

```bash
cp ops/.env.example ops/.env
cp configs/secrets.yaml.example configs/secrets.yaml
```

把 `ops/.env` 里的五个数据库密码改成你自己的。`configs/secrets.yaml` 里的 `database` 四条密码要和 `.env` 里的角色密码一致（超级用户密码只放在 `.env`）。这两份文件不要提交。

然后一条命令拉起数据库、表结构、采集、读接口和 Harness：

```bash
cd ops
docker compose up -d --build
```

第一次会建库、跑迁移、安装插件，需要几分钟。完成之后：

```bash
docker compose logs market-dsh | grep 'dsh web:'
```

日志里有一行带 `?token=` 的地址。把主机改成 `127.0.0.1`，用浏览器打开，例如 `http://127.0.0.1:3080/?token=...`。打开一次之后会话会留下来。侧栏点 **观势**。

接口在 `http://127.0.0.1:8787`。看板读数不需要登录。浏览器和 Harness 不在同一台机器时，在看板页面控制台执行：

```js
localStorage.setItem("guanshi.api", "http://你的数据接口")
```

然后刷新。

在 Harness 的设置里填上你自己的模型密钥。这个仓库不带密钥。

## 画面

三个时段。在画布空白处右键，添加当前时段的看板。拖标题栏移动，拖边缘改大小。布局记在本机。

- **盘前**：盘前消息按小时和题材摊开。右键可以加隔夜外盘。
- **盘中**：指数涨跌、涨跌分布、赚钱效应、隔夜外盘、指数分钟、指数小时成交、板块涨跌与资金、领涨领跌、竞价强弱、市场雷达、市场动态、快讯、电报与催化、预测与反思、数据覆盖。交易时段大约每两分钟刷新。接口还没有数时，先显示示例数据。
- **盘后**：情绪刻度、题材舞台、原因核对、资金去向、涨停与跌停、次日候选、预测兑现、明日一句。

浅色和深色在看板顶栏切换。

阶段沿用库里的规则：不到 3 板是聚集未完成，破 3 板是启动，4 到 5 板是发酵，破 6 板是高潮。涨停明显减少或炸板挤在一起是分歧。高位之后急降是退潮。

## 采集

`docker compose up -d` 之后，调度容器会按交易日时刻表自己采。日历、隔夜外盘、指数、个股日线、涨停池、竞价、雷达、快讯、板块，都在默认开启的作业里。等到对应时刻，表里就会有数。数据覆盖看板上能看到每张表最新到哪一天，以及最近一天作业是成功还是缺数。

想立刻采一天，而不是等到时刻表，在仓库的 `ops` 目录执行（把日期换成交易日）：

```bash
docker compose exec market-sched python -c "
from dworker.core.runner import execute_job
print(execute_job('j_index_daily', trigger='manual', extra_params={'date':'2026-11-03'}))
"
```

常用作业名：`j_trade_cal`、`j_global_overnight`、`j_index_daily`、`j_index_minute`、`j_stock_daily`、`j_zt_pools`、`j_bidding_list`、`j_radar`、`j_market_messages_hot`。

非交易日会跳过，不拿别的日子顶上。源没有数就记成缺数。

龙虎相关的作业需要你自己的账号。把用户号、token、设备号填进 `configs/secrets.yaml` 的 `longhu.longhu_primary` 和 `longhu.longhu_secondary`，然后 `docker compose restart market-sched`。没有这组账号时，其余公开源的作业仍然会跑。

改了 `db/seed_jobs.yaml` 或 `dworker/` 之后，执行 `docker compose restart market-sched`。改了 `data_api/` 之后，执行 `docker compose restart market-api`。

## 目录

```
data_api/     读接口，含 /api/public/v1
dworker/      采集作业
dsched/       时刻表
dsh/          插件、安装脚本
db/           表结构迁移
ops/          Docker Compose
```

## 许可

[MIT](LICENSE)。上游行情数据的条款仍归各数据源所有。
