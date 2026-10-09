"""
mootdx 竞价字段集成方案（PATCH - 待验证后应用）
状态：READY_FOR_TEST（09:26 后用真实数据验证）
验证计划：09:26 运行 smoke → 确认字段 → 应用到 j_bidding_list.py → 重跑 manual_test

变更摘要：
1. j_bidding_list.py: source_chain 首位插入 mootdx，eastmoney 保留降级位
2. 新增 _fetch_mootdx_bidding() 函数
3. 字段映射：
   - jjzf = (price - last_close) / last_close * 100
   - jjje = amount（竞价成交额）
   - jjhs = vol / total_shares（需 instrument_master 补充，暂填 0）
   - ztwme = 需额外计算，暂填 0
   - twenty_ztwme = 暂填 0
   - fd = b_vol + s_vol（内外盘之和，近似放量）
"""

def _fetch_mootdx_bidding(today: str, quotations_type: int) -> list:
    """
    从 mootdx 获取竞价数据。
    注意：仅在 09:15-09:25 有效，其他时段返回空。
    """
    from mootdx.quotes import Quotes
    import time
    
    rows = []
    try:
        api = Quotes.factory(market='std')
        
        # 获取全市场股票列表（优化：可缓存到 instrument_master）
        # 这里先用观察池或固定列表，避免全市场扫描超时
        # TODO: 从 watchlist 或 instrument_master 读取活跃股票列表
        test_stocks = [
            (0, '000001'), (0, '000002'), (0, '000063'),
            (0, '300750'), (0, '300059'),
            (1, '600519'), (1, '601318'), (1, '600036'),
        ]
        
        # 分批查询（mootdx 并发≤4）
        batch_size = 50
        all_quotes = []
        
        for i in range(0, len(test_stocks), batch_size):
            batch = test_stocks[i:i+batch_size]
            try:
                result = api.client.get_security_quotes(batch)
                if result:
                    all_quotes.extend(result)
                time.sleep(0.1)  # 限速
            except Exception as e:
                logger.warning(f"mootdx batch {i} failed: {e}")
                continue
        
        # 转换为 bidding_list 格式
        for quote in all_quotes:
            code_raw = quote.get('code', '')
            market = quote.get('market', 0)
            
            # 标准化代码
            if market == 0:
                code = f"sz{code_raw}"
            elif market == 1:
                code = f"sh{code_raw}"
            else:
                continue
            
            price = float(quote.get('price', 0))
            last_close = float(quote.get('last_close', 0))
            
            if price <= 0 or last_close <= 0:
                continue
            
            # 计算竞价涨幅
            jjzf = (price - last_close) / last_close * 100
            
            rows.append({
                "date": today,
                "code": code,
                "name": "",  # mootdx 不返回名称，需 instrument_master 补充
                "jjzf": round(jjzf, 2),
                "jjje": int(float(quote.get('amount', 0))),
                "jjcje": 0,  # 需额外计算
                "jjhs": 0,  # 需 total_shares
                "ztwme": 0,  # 需额外计算
                "twenty_ztwme": 0,
                "fd": int(float(quote.get('b_vol', 0)) + float(quote.get('s_vol', 0))),
                "zdfd": 0,
                "sjlt": 0,
                "ssbk": "",
                "ztsj": "",
                "ztyy": "",
                "bkztsl": 0,
                "limit_up_status": "",
                "quotations_type": quotations_type,
            })
        
        logger.info(f"mootdx bidding: got {len(rows)} rows")
        
    except Exception as e:
        logger.warning(f"mootdx bidding fetch failed: {e}")
    
    return rows


# === 应用到 j_bidding_list.py 的变更 ===

CHANGE_SUMMARY = """
1. 在 _fetch_from_source() 中增加 mootdx 分支：

def _fetch_from_source(source_name: str, today: str, quotations_type: int) -> list:
    if source_name == "mootdx":
        return _fetch_mootdx_bidding(today, quotations_type)
    elif source_name == "eastmoney":
        return _fetch_eastmoney_bidding(today)
    return []

2. 在 seed_jobs.yaml 中修改 source_chain：

# 原：
source_chain: ["eastmoney"]
# 改为：
source_chain: ["mootdx", "eastmoney"]

3. 备份原文件：
cp j_bidding_list.py j_bidding_list.py.bak_20261009

4. 验证步骤（09:26 后执行）：
a. python3 tools/smoke_mootdx_bidding.py  # 确认有真实数据
b. 应用上述变更
c. python3 tools/manual_test.py --job j_bidding_list  # 重跑 smoke
d. 对比 bidding_list 表中 source='mootdx' vs source='eastmoney' 的行数和质量
e. 检查 ingest_log 中 run_id 对应的 duration_ms 和 rows_written
"""

VERIFICATION_CHECKLIST = """
09:26 验证清单：
□ smoke_mootdx_bidding.py 返回非空数据（4只测试股票）
□ 字段完整性：price/open/vol/amount 均 > 0
□ 代码映射正确：sz000001/sh600519 等
□ 性能：50只股票批量查询 < 5s
□ 与 eastmoney 数据对比：价格偏差 < 1%
□ 写入 bidding_list 后 SELECT 验证
"""
