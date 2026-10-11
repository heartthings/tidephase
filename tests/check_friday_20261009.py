"""周五 2026-10-09 行数断言。在 market-sched 容器里跑。"""
from dworker.core.runner import get_db_connection

EXPECT = {
    "index_daily": 6,
    "stock_daily": 5224,
    "zt_pool": 69,
    "yzt_pool": 42,
    "sector_daily": 259,
    "fund_flow_stock": 5498,
    "dragon_tiger": 82,
    "etf_daily": 1694,
}


def main():
    conn = get_db_connection()
    failed = []
    with conn.cursor() as cur:
        for table, want in EXPECT.items():
            cur.execute(f"SELECT count(*) FROM {table} WHERE date = %s", ("2026-10-09",))
            got = cur.fetchone()[0]
            print(f"{table} {got} expect {want}")
            if got != want:
                failed.append(table)
        cur.execute("SELECT count(*) FROM verify_source WHERE date = %s", ("2026-10-09",))
        checked = cur.fetchone()[0]
        print(f"verify_source {checked}")
        if checked < 5000:
            failed.append("verify_source")
    if failed:
        raise SystemExit("FAIL " + ",".join(failed))
    print("PASS")


if __name__ == "__main__":
    main()
