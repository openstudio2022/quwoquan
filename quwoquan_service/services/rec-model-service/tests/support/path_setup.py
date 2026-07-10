"""Path setup for rec-model service tests."""
from __future__ import annotations

import sys
from pathlib import Path


def ensure_rec_model_paths() -> None:
    service_root = Path(__file__).resolve().parents[2]
    script_root = service_root / "scripts"
    for path in (service_root, script_root):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
