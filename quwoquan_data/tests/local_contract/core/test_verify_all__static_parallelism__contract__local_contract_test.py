"""The aggregate Data verifier is static and deduplicated."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify import handler as verify_handler  # noqa: E402


def test_verify_all_runs_only_deduplicated_static_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_names: list[str] = []

    def controlled_gate(name: str, _argv: object = None) -> int:
        observed_names.append(name)
        return 0

    monkeypatch.setattr(verify_handler, "_run", controlled_gate)

    verify_handler.handle_all()

    assert len(observed_names) == len(set(observed_names))
    assert "active-runtime-preflight" not in observed_names
    assert "publish-purity" in observed_names
    assert "publish-closure" in observed_names
