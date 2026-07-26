"""Release discard removes only inactive, disposable release output."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical import discard  # noqa: E402


RELEASE_ID = "20260725--travel-homepage-coverage--test-region--pilot-001"


def test_release_discard__removes_release_and_matching_environment_evidence__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    output_root = tmp_path
    evidence = output_root / "env/alpha/runs/data-release" / RELEASE_ID
    evidence.mkdir(parents=True)
    unrelated = output_root / "env/alpha/runs/data-release/unrelated-release"
    unrelated.mkdir(parents=True)
    monkeypatch.setattr(discard, "_active_release_processes", lambda _release_id: ())

    discard.discard_release(
        RELEASE_ID,
        release_root=release_root,
        output_root=output_root,
    )

    assert not release.exists()
    assert not evidence.exists()
    assert unrelated.is_dir()


def test_release_discard__rejects_active_release_writer__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    release = release_root / RELEASE_ID
    release.mkdir(parents=True)
    monkeypatch.setattr(
        discard,
        "_active_release_processes",
        lambda _release_id: ("123 python cli.py ship apply --release-id ...",),
    )

    with pytest.raises(RuntimeError, match="active release command"):
        discard.discard_release(RELEASE_ID, release_root=release_root, output_root=tmp_path)

    assert release.is_dir()
