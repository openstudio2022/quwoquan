"""Canonical reset is allowed only after a matching empty-baseline receipt."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical import reset  # noqa: E402


BASELINE_ID = "20260725--travel-content--empty--test-001"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _baseline(release_root: Path) -> None:
    _write_json(
        release_root / BASELINE_ID / "payload/release.json",
        {"releaseKind": "empty_baseline"},
    )
    _write_json(
        release_root / BASELINE_ID / "payload/desired_state.json",
        {"desiredRefs": {"creators": [], "entities": [], "posts": [], "tags": []}},
    )


def _receipt(output_root: Path, environment: str) -> None:
    _write_json(
        output_root
        / "env"
        / environment
        / "runs/data-release"
        / BASELINE_ID
        / "apply-test"
        / "applied_ref.json",
        {"releaseId": BASELINE_ID},
    )


def test_release_reset_canonical__clears_only_canonical_output_after_baseline_receipts__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    output_root = tmp_path
    publish_root = tmp_path / "publish"
    _baseline(release_root)
    _receipt(output_root, "alpha")
    _receipt(output_root, "beta")
    (publish_root / "entities/example").mkdir(parents=True)
    (publish_root / "media/objects").mkdir(parents=True)
    (publish_root / "tags/Topic").mkdir(parents=True)
    monkeypatch.setattr(reset, "active_runtime_processes", lambda: [])

    removed = reset.reset_canonical_publish(
        empty_baseline_release=BASELINE_ID,
        environments=("alpha", "beta"),
        publish_root=publish_root,
        release_root=release_root,
        output_root=output_root,
    )

    assert removed == ("entities", "media", "tags")
    assert list(publish_root.iterdir()) == []


def test_release_reset_canonical__blocks_without_every_baseline_receipt__functional__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "data/releases"
    _baseline(release_root)
    _receipt(tmp_path, "alpha")
    monkeypatch.setattr(reset, "active_runtime_processes", lambda: [])

    with pytest.raises(RuntimeError, match="empty baseline is not applied"):
        reset.reset_canonical_publish(
            empty_baseline_release=BASELINE_ID,
            environments=("alpha", "beta"),
            publish_root=tmp_path / "publish",
            release_root=release_root,
            output_root=tmp_path,
        )
