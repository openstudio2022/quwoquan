"""The aggregate Data verifier is static, deduplicated, and parallel."""
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


def test_verify_all_runs_only_deduplicated_static_gates_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    observed_names: list[str] = []
    observed_threads: set[int] = set()
    call_count = 0

    def controlled_gate(name: str, _run: object) -> tuple[str, int]:
        nonlocal call_count
        with lock:
            call_count += 1
            should_wait = call_count <= barrier.parties
            observed_names.append(name)
            observed_threads.add(threading.get_ident())
        if should_wait:
            barrier.wait(timeout=5)
        return name, 0

    monkeypatch.setattr(verify_handler, "_run_static_gate", controlled_gate)

    verify_handler.handle_all()

    assert len(observed_names) == len(set(observed_names))
    assert "active-runtime-preflight" not in observed_names
    assert "publish-purity" not in observed_names
    assert "publish-closure" in observed_names
    assert len(observed_threads) >= 2
