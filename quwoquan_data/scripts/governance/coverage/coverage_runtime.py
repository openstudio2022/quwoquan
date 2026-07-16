"""Runtime paths and timestamps for coverage discovery evidence."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from core import paths as _paths


def coverage_workspace_root() -> Path:
    output_root = Path(os.environ.get("QWQ_OUTPUT_ROOT", _paths.OUTPUT_ROOT))
    return output_root / "data" / "local" / "workspace" / "coverage"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
