#!/usr/bin/env python3
"""周一开市前能核对的事项。交易时段里的事留给周一，不在这里标完成。"""
import subprocess


def sh(cmd: str) -> str:
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return (out.stdout or out.stderr).strip()


def main() -> None:
    names = sh("docker ps -a --format '{{.Names}} {{.Status}}'")
    print("containers:")
    print(names or "(none)")
    print("lovetrade container present:", any(line.split()[0] == "lovetrade" for line in names.splitlines() if line.split()))
    pred = sh(
        "docker exec market-tsdb psql -U postgres -d market_tsdb -tAc "
        "\"SELECT enabled FROM job_registry WHERE job_name='j_prediction_sync'\""
    )
    print("j_prediction_sync enabled:", pred.strip())
    print("monday still to watch:")
    for line in (
        "07:30 j_global_overnight",
        "09:15/09:20/09:25 bidding snaps",
        "15:20 hot list including concept plates",
        "15:40 option job should log MISS if contracts are still unpublished",
        "16:10 dragon seats",
        "16:30 longhu probe counts",
        "17:30 观势 POST /d12/regime_daily",
        "three trading days and 梁总 web check before W5 can close",
    ):
        print(" -", line)


if __name__ == "__main__":
    main()
