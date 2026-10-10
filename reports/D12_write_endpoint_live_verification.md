# D12 写端点 live 验证 · 2026-10-10T21:23:00
API=http://127.0.0.1:8787  只读token len=43  写token len=43

### 1) 鉴权闸门：read token → POST /d12/cognition（预期 403）
HTTP 403  body={"detail":{"code":"AUTH","msg":"Write permission required"}}

### 1b) 无 token → POST /d12/prediction（预期 401/403）
HTTP 401  body={"detail":{"code":"AUTH","msg":"Missing bearer token"}}

### 2) 参数校验：cognition_id 非法（预期 400 BAD_PARAM）
HTTP 400  body={"error":{"code":"BAD_PARAM","msg":"cognition_id must match ^[FCHM]-\\d{3}$, got 'XX-1'","request_id":"a093b508-c6ab-4e71-b794-f95ff27217ab"}}

### 2b) 必填缺失（预期 400）
HTTP 400  body={"error":{"code":"BAD_PARAM","msg":"'title' is required","request_id":"901b399b-9814-4d15-b918-c5fb2c3d8bae"}}

### 2c) prediction confidence_pct 越界（预期 400）
HTTP 400  body={"error":{"code":"BAD_PARAM","msg":"confidence_pct must be int 0-100","request_id":"2f709f19-fc20-4883-8ea8-d6e0652d58fc"}}

### 3) 真实写入 cognition（smoke，随后清理）
HTTP 200  body={"data":{"created":"M-999","version":1},"meta":{"rows":1,"next_cursor":null,"server_ts":"2026-10-10T21:23:00.169676+08:00","request_id":"638c4913-5f7b-432f-bf0a-f42390035032"}}

### 3b) 真实写入 prediction（smoke，含 horizon/regime_at_create/falsify 标准 schema）
HTTP 200  body={"data":{"created":"P-20261010-SMOKE"},"meta":{"rows":1,"next_cursor":null,"server_ts":"2026-10-10T21:23:00.233112+08:00","request_id":"f540c714-4a47-440a-9c2c-6d2146ba85c1"}}

### 3c) 幂等/冲突检测：重复写同 id（预期 409 CONFLICT）
HTTP 409  body={"error":{"code":"CONFLICT","msg":"cognition_id 'M-999' already exists (version=1)","request_id":"14d537fb-9a5f-4dfa-957a-2e7e8f29d6dd"}}

### 4) DB 复核（写入是否真落库）
cognition 行: M-999 v1 type=M actor=dujun_smoke src=dujun_smoke_20261010
prediction 行: P-20261010-SMOKE cat=smoke conf=1 horizon=T1 regime=smoke falsify={"dim": {"code": "sz000001"}, "metric": "stock_daily.pct", "direction": "<", "th

### 5) 清理（零残留）
DELETE cognition -> M-999
DELETE 1
DELETE prediction -> P-20261010-SMOKE
DELETE 1
残留复核 cognition=0
残留复核 prediction=0
cognition 总行数（应=2078 不变）: 2078
prediction 总行数（应=344 不变）: 344

### 6) GET /d12/prediction/due（读端点）
HTTP 200  len=72168  head={"data":[{"prediction_id":"P-12","statement":"韩国杠杆清算冲击进入衰减期，T+1~T+2 A股半导体跌幅收窄，创业板有望率先企稳","category":"phase_change","confidence_pct":68,"check_date":"2026-07-20","result":"pending","result_note":"半导体今日显著分化：国产算力逆势爆发（紫光股份/中兴通讯涨停），但存储芯片退潮（德明利跌停）。创业板确实率先企稳（虽仍跌3.23%但较昨日+7.05%后回调幅度可控）。部分验证。","created_at":"

## 判定：D12 写端点 live = PASS
- 鉴权：read token 被拒 ✅ / 无 token 被拒 ✅
- 校验：非法 id 400 ✅ / 缺字段 400 ✅ / conf 越界 400 ✅ / 重复 409 ✅
- 写入：cognition 落库=True / prediction 落库=True
- 清理：零残留，总行数未变
