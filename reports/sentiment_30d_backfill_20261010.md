# sentiment_daily 30日回填 · 2026-10-10T21:35:47
端点: https://apphis.longhuvip.com/w1/api/index.php
参数: {"a": "GetMoneyDate", "st": "30", "c": "Emotion", "PhoneOSNew": "1", "DeviceID": "07ba97d5...", "VerSion": "5.18.0.2", "index": "0", "apiv": "w39"}
HTTP 200  resp_len=1493
响应键: ['ZY', 'ttag', 'errcode']  errcode=0
ZY 序列条数: 30
日期范围: 2026-08-21 ~ 2026-10-09
首条: {"CGL": "76.19", "YLL": "2.10", "Day": "2026-10-09"}  末条: {"CGL": "55.56", "YLL": "-0.07", "Day": "2026-08-21"}
raw 归档: data/raw/D3/2026-10-10/j_sentiment_calc/20261010_213550_emotion_30d_backfill.json (1493 bytes, 经 market-worker 容器写入)
写库完成: 新增=30 更新=0
复核 sentiment_daily: rows=30 范围=2026-08-21~2026-10-09 dbcgl非空=30 dbyll非空=30
  2026-10-09 dbcgl=76.19 dbyll=2.1
  2026-10-08 dbcgl=60.78 dbyll=1.02
  2026-09-30 dbcgl=52.94 dbyll=1.21
  2026-09-29 dbcgl=60.61 dbyll=1.27
  2026-09-28 dbcgl=43.75 dbyll=0.04
  2026-09-24 dbcgl=50 dbyll=0.55
ingest_log 已留痕（trigger=backfill）
交叉验证: 源30条 vs 库30行 → 不一致 0 处 ✅ 全一致

## 判定：sentiment_daily 30日回填 = PASS
