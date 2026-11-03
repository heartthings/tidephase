---
name: board-edit
description: Add, remove, or resize Tidephase (观势) boards on the pre-open, intraday, or after-close canvas. Use when the user wants a different dashboard layout.
---

# Board edit

The canvas is one JSON document, version 1, with sessions `preopen`, `intraday`, and `afterclose`. Each board has `id`, `type`, `x`, `y`, `w`, `h`.

Allowed types:

- preopen: `preopen-messages`, `overnight`
- intraday: `market-radar`, `market-dynamics`
- afterclose: `sentiment-dial`, `theme-stage`, `reason-check`, `money-flow`, `limit-cards`, `next-candidates`, `fulfillment`, `tomorrow-line`

Read the current spec:

`GET http://127.0.0.1:8787/api/public/v1/boards/spec`

Write it back from loopback only:

`PUT http://127.0.0.1:8787/api/public/v1/boards/spec`

Keep every session key. Width stays between 220 and 2400. Height stays between 120 and 1600. Do not invent a board type, and do not embed HTML.
