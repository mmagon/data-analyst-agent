"""Shared configuration for the Prudentia monitor scripts (Commit A hardening).

Fixes: B8 (BASE_DIR fail-fast instead of silent ~/prudentia_monitor default),
B5 (UTC everywhere via utcnow()), B9 (durable run-log path).
"""

import hashlib
import os
import sys
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now. All timestamps in the monitor must come from here."""
    return datetime.now(timezone.utc)


def _base_dir() -> str:
    env = os.environ.get("PRUDENTIA_MONITOR_DIR")
    if env:
        return env
    if os.environ.get("PRUDENTIA_MONITOR_ALLOW_DEFAULT") == "1":
        return os.path.expanduser("~/prudentia_monitor")
    print(
        "FATAL: PRUDENTIA_MONITOR_DIR is not set; refusing to default silently to "
        "~/prudentia_monitor (issue B8). Set the env var, or set "
        "PRUDENTIA_MONITOR_ALLOW_DEFAULT=1 for interactive use.",
        file=sys.stderr,
    )
    raise SystemExit(3)


BASE_DIR = _base_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
RUN_LOG = os.path.join(BASE_DIR, "run_log.jsonl")


def script_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
