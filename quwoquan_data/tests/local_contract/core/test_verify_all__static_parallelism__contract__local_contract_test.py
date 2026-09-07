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


def test_verify_all_rehydrates_before_deduplicated_static_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def admit_carried_media() -> int:
        observed.append("rehydrate-media-holdings")
        return 0

    def controlled_gate(name: str, _argv: object = None) -> int:
        observed.append(name)
        return 0

    monkeypatch.setattr(
        verify_handler, "_admit_carried_media_holdings", admit_carried_media
    )
    monkeypatch.setattr(verify_handler, "_run", controlled_gate)

    verify_handler.handle_all()

    assert observed[0] == "rehydrate-media-holdings"
    observed_names = observed[1:]
    assert len(observed_names) == len(set(observed_names))
    assert "active-runtime-preflight" not in observed_names
    assert "publish-purity" not in observed_names
    assert observed_names.count("publish-closure") == 1


def test_verify_all_stops_when_carried_media_cannot_be_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verify_handler, "_admit_carried_media_holdings", lambda: 1)

    def unexpected_gate(_name: str, _argv: object = None) -> int:
        pytest.fail("static gates must not run with unresolved carried media")

    monkeypatch.setattr(verify_handler, "_run", unexpected_gate)

    with pytest.raises(SystemExit) as failure:
        verify_handler.handle_all()

    assert failure.value.code == 1
