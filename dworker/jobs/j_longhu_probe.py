"""龙虎三个端点的行数回报。不把空响应写成行情。"""
import logging

from dworker.adapters.longhu import LonghuAdapter
from dworker.core.degradation import JobContext, SourceError

logger = logging.getLogger(__name__)
ENDPOINTS = ("Emotion", "DailyLimitResumption", "Radar")


def run(job_ctx, deg_chain, source_chain, conn, ingest_logger, raw_archiver, trigger="scheduled"):
    adapter = LonghuAdapter()
    ctx = JobContext("j_longhu_probe", "D3", [], {})
    counts = []
    for name in ENDPOINTS:
        try:
            result = adapter.fetch(ctx, {"endpoint": name, "extra_params": {}})
            counts.append(f"{name}={len(result.rows or [])}")
        except SourceError as e:
            counts.append(f"{name}=0 ({e.kind})")
        except Exception as e:
            logger.warning(f"[j_longhu_probe] {name}: {e}")
            counts.append(f"{name}=ERR")
    note = " ".join(counts) + "; YouZi and L2 pan kou stay off"
    empty = any(part.startswith("Emotion=0") or part.startswith("DailyLimitResumption=0") for part in counts)
    try:
        ingest_logger.log_run(
            "j_longhu_probe", "D3", "radar_event", "longhu",
            "MISS" if empty else "OK", note=note, trigger=trigger,
        )
    except Exception:
        pass
    return {"success": True, "already_logged": True, "source_used": "longhu",
            "rows_in": 0, "rows_written": 0, "rows_quarantined": 0, "note": note}
