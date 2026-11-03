---
name: board-edit
description: Add, remove, or resize Tidephase (观势) boards on the pre-open, intraday, or after-close canvas. Use when the user wants a different dashboard layout.
---

# Board edit

The canvas is one JSON document, version 1, with sessions `preopen`, `intraday`, and `afterclose`. Each board has `id`, `type`, `x`, `y`, `w`, `h`. The screen lays boards on a fixed 12-column grid in reading order. `x`, `y`, `w`, and `h` are still stored and validated. The page does not use freeform dragging. Users show or hide a board from the 面板 menu.

Allowed types are the ones in `dsh/spec/catalog.json` for that session.

Read the current spec:

`GET http://127.0.0.1:8787/api/public/v1/boards/spec`

Write it back from loopback only:

`PUT http://127.0.0.1:8787/api/public/v1/boards/spec`

Keep every session key. Width stays between 220 and 2400. Height stays between 120 and 1600. Do not invent a board type, and do not embed HTML.
