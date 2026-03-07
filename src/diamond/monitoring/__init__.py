"""Monitoring: risk, alerts, and structured metrics."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_metrics_logging(log_dir: Path | None = None) -> None:
    """Configure the diamond.metrics logger to write JSON events to a file.

    Call once at startup (e.g. from CLI entrypoint). Safe to call multiple times.
    """
    metrics_logger = logging.getLogger("diamond.metrics")

    # Avoid duplicate handlers
    if metrics_logger.handlers:
        return

    if log_dir is None:
        from diamond.config import get_config

        log_dir = get_config().data_dir / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "metrics.jsonl", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    metrics_logger.addHandler(handler)
    metrics_logger.setLevel(logging.INFO)
    metrics_logger.propagate = False
