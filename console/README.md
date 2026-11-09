# 观势台（console）

观势数据层的工作台。首页把指数、情绪、涨停、大盘直播、板块、竞价、外盘、北向、认知和表覆盖摊在一张桌上。

## 和 DSH「观势」看板的关系

- **观势台（本目录）**：多页工作台，适合回看、检索、题材库、笔记、交易体系。
- **DSH guanshi-board**：交易时段的盘面网格，读 `/api/public/v1/*`。

两边共用 `market-api`。开源时可以和 `dsh/` 一起打包。

## 主要页面

| 路径 | 内容 |
|------|------|
| `/home` | 观势台总览（`/api/console/desk`） |
| `/floor` | 涨停 / 炸板 / 跌停池 + 情绪 |
| `/market-trends/radar` | 开盘啦大盘直播 |
| `/market-trends/dynamic` | 财联社快讯 |
| `/capital-flow` | 主力净额 |
| `/interval-stats` | 区间统计 |
| `/catalyst` | 催化雷达 |
| `/topic-lib` | 题材库 |
| `/trading-notes` | 交易笔记 |
| `/trading-system` | 交易体系 |

## 本地开发

```bash
pnpm install
pnpm dev
```

接口默认同源。开发时把 `VITE_SERVICE_BASE_URL` 指到 `http://127.0.0.1:8787`，或走 nginx 反代。

## 生产

`Dockerfile` 打出静态 `dist`，由 nginx 把 `/api`、`/auth` 转到 `market-api:8787`。
