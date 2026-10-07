"""
raw 归档层
原始响应落 data/raw/{域}/{日期}/{作业}/{HHMMSS}_{源}.json.gz
保留 1 年，可重灌。
"""
import gzip
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class RawArchiver:
    """Archive raw API responses to disk."""

    def __init__(self, base_dir: str = "data/raw"):
        self.base_dir = Path(base_dir)

    def archive(self, domain: str, job_name: str, source: str,
                payload: any, ts: datetime = None) -> str:
        """
        Save raw payload as gzipped JSON.
        Returns the file path.
        """
        ts = ts or datetime.now()
        date_str = ts.strftime("%Y-%m-%d")
        time_str = ts.strftime("%H%M%S")

        dir_path = self.base_dir / domain / date_str / job_name
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / f"{time_str}_{source}.json.gz"

        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            json.dump({
                "job": job_name,
                "source": source,
                "ts": ts.isoformat(),
                "payload": payload
            }, f, default=str, ensure_ascii=False)

        logger.debug(f"Archived raw: {file_path}")
        return str(file_path)
