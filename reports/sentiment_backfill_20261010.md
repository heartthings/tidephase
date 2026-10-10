# sentiment_daily 全量回填(st=250) · 2026-10-10T21:38:45
端点: https://apphis.longhuvip.com/w1/api/index.php
参数: {"a": "GetMoneyDate", "st": "250", "c": "Emotion", "PhoneOSNew": "1", "DeviceID": "07ba97d5...", "VerSion": "5.18.0.2", "index": "0", "apiv": "w39"}
HTTP 200  resp_len=6058
响应键: ['ZY', 'ttag', 'errcode']  errcode=0
ZY 序列条数: 125
日期范围: 2026-04-03 ~ 2026-10-09
首条: {"CGL": "76.19", "YLL": "2.10", "Day": "2026-10-09"}  末条: {"CGL": "68.97", "YLL": "1.29", "Day": "2026-04-03"}
raw 归档: data/raw/D3/2026-10-10/j_sentiment_calc/20261010_213847_emotion_st250_backfill.json (6058 bytes, 经 market-worker 容器写入)
写库完成: 新增=95 更新=30
复核 sentiment_daily: rows=125 范围=2026-04-03~2026-10-09 dbcgl非空=125 dbyll非空=125
  2026-10-09 dbcgl=76.19 dbyll=2.1
  2026-10-08 dbcgl=60.78 dbyll=1.02
  2026-09-30 dbcgl=52.94 dbyll=1.21
  2026-09-29 dbcgl=60.61 dbyll=1.27
  2026-09-28 dbcgl=43.75 dbyll=0.04
  2026-09-24 dbcgl=50 dbyll=0.55
ingest_log 已留痕（trigger=backfill）
交叉验证: 源125条(ZY全量逐条比对) vs 库125行 → 不一致 0 处 ✅ 全一致

## 判定：sentiment_daily 全量回填(st=250) = PASS
