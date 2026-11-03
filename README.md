# Tidephase

Chinese name: 观势. A-share market data, and a DeepSeek Harness plugin that draws it as boards.

**A-shares only.** Read [DISCLAIMER.md](DISCLAIMER.md) before using the numbers. 中文说明见 [README.zh-CN.md](README.zh-CN.md).

The open-source entry is the **观势** panel inside Harness. This repo ships two plugins:

- `guanshi-board` — three canvases
- `guanshi-theme` — a soft light theme and a soft dark theme

Harness is pinned to official `@deepseek-ai/dsh@0.2.0-rc.2`.

## Start from zero

You need Docker and Docker Compose. From the repo root:

```bash
cp ops/.env.example ops/.env
cp configs/secrets.yaml.example configs/secrets.yaml
```

Change the five database passwords in `ops/.env`. The four role passwords under `database` in `configs/secrets.yaml` must match. The superuser password stays only in `.env`. Do not commit either file.

One command brings up the database, schema, collectors, read API, and Harness:

```bash
cd ops
docker compose up -d --build
```

The first run creates the database, applies migrations, and installs the plugins. Then:

```bash
docker compose logs market-dsh | grep 'dsh web:'
```

Open the logged URL in a browser, with the host set to `127.0.0.1`, for example `http://127.0.0.1:3080/?token=...`. The session sticks after the first open. Choose **观势** in the sidebar.

The API is `http://127.0.0.1:8787`. Board reads do not ask for a login. If the browser is not on the same machine as the API, run this in the board page console and reload:

```js
localStorage.setItem("guanshi.api", "http://your-data-api")
```

Put your own model key in Harness settings. This repo does not ship one.

## What you see

Three sessions. Right-click empty canvas to add a board for the current session. Drag a title to move a board. Drag an edge to resize it.

- **Pre-open:** messages grouped by hour and theme. Overnight global quotes are in the menu.
- **Intraday:** index moves, advance/decline buckets, money effect, overnight quotes, index minutes, hourly index volume, sector moves and flow, leaders, auction, radar, tape, headlines, wires and catalysts, predictions, and data coverage. The intraday canvas refreshes about every two minutes. Sample figures stay on screen until the API has rows.
- **After close:** sentiment, theme stage, reason check, money flow, limit-up and limit-down cards, next-day candidates, fulfillment, and a one-line plan.

Switch light and dark from the board header.

Stages follow the stored rules: under 3 boards is still gathering, 3 is ignition, 4–5 is fermentation, 6 or more is climax. A sharp drop in limit-ups, or a cluster of broken boards, is divergence. A collapse after that height is ebb.

## Collection

After `docker compose up -d`, the scheduler collects on the trading-day timetable. Calendar, overnight markets, indexes, daily stocks, limit-up pools, auction, radar, headlines, and sectors are on by default. The coverage board shows the latest day in each table and whether the last day's jobs succeeded.

To collect one day now, from `ops` (use a real trade date):

```bash
docker compose exec market-sched python -c "
from dworker.core.runner import execute_job
print(execute_job('j_index_daily', trigger='manual', extra_params={'date':'2026-11-03'}))
"
```

Useful job names: `j_trade_cal`, `j_global_overnight`, `j_index_daily`, `j_index_minute`, `j_stock_daily`, `j_zt_pools`, `j_bidding_list`, `j_radar`, `j_market_messages_hot`.

Closed days are skipped. A missing source is recorded as a gap, not filled from another day.

Longhu jobs need your own account. Put the user id, token, and device id in `longhu.longhu_primary` and `longhu.longhu_secondary` inside `configs/secrets.yaml`, then `docker compose restart market-sched`. The other jobs still run without that account.

After editing `db/seed_jobs.yaml` or `dworker/`, run `docker compose restart market-sched`. After editing `data_api/`, run `docker compose restart market-api`.

## Layout

```
data_api/     read API, including /api/public/v1
dworker/      collectors
dsched/       timetable
dsh/          plugins and installer
db/           schema migrations
ops/          Docker Compose
```

## License

[MIT](LICENSE). Market data from upstream vendors stays under those vendors' terms.
