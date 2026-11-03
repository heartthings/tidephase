# 观势看板

DeepSeek Harness panel for A-share pre-open, intraday, and after-close boards. The package id stays `guanshi-board`.

The canvas is three sessions. Intraday includes the index, breadth, minute, hourly volume, sector, leader, auction, news, and coverage boards. Boards sit on a fixed 12-column grid in reading order. Use the 面板 menu to show or hide a board. Sample data is shown until the public API responds.

Data comes from `http://127.0.0.1:8787/api/public/v1`. Set `localStorage.guanshi.api` to point elsewhere.

Install with `dsh/scripts/install.sh`. This package does not vendor Harness.
