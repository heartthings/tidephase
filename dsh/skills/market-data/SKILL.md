---
name: market-data
description: Read Tidephase (观势) A-share boards through the local read-only API. Use for pre-open messages, overnight markets, intraday radar, intraday tape, and the after-close review.
---

# Market data

Only A-shares. Never invent a print when the API reports a gap.

Base URL defaults to `http://127.0.0.1:8787`. Override with `GUANSHI_API_BASE`.

- `GET /api/public/v1/preopen/messages?date=YYYY-MM-DD`
- `GET /api/public/v1/preopen/overnight?date=YYYY-MM-DD`
- `GET /api/public/v1/intraday/radar?date=YYYY-MM-DD`
- `GET /api/public/v1/intraday/dynamics?date=YYYY-MM-DD`
- `GET /api/public/v1/intraday/tape?date=YYYY-MM-DD` — indexes, breadth, minutes, hourly volume, sectors, leaders, auction, headlines, coverage
- `GET /api/public/v1/afterclose/review?date=YYYY-MM-DD`

Say what the payload shows: counts, stage names, one-line reasons, probabilities. Do not expand those into a long essay, and do not add prices to buy or sell.
