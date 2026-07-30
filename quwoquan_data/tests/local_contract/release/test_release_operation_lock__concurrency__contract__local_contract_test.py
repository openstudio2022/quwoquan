# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""Release cleanup and writers must coordinate through OS-backed locks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.release_operation_lock import (  # noqa: E402
    release_operation_guard,
)


_CHILD = """
from pathlib import Path
import sys
from content.release.canonical.release_operation_lock import ReleaseOperationConflict, release_operation_guard
environment = sys.argv[3] if len(sys.argv) > 3 else ""
try:
    with release_operation_guard(
        lock_root=Path(sys.argv[1]),
        release_ids=(sys.argv[2],),
        exclusive_releases=True,
        environments=(environment,) if environment else (),
        exclusive_environments=True,
    ):
        pass
except ReleaseOperationConflict as exc:
    print(exc)
    raise SystemExit(3)
"""


def _child(
    lock_root: Path,
    release_id: str,
    environment: str = "",
) -> subprocess.CompletedProcess[str]:
    process_environment = dict(os.environ)
    process_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process_environment["PYTHONPATH"] = str(SCRIPTS)
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            _CHILD,
            str(lock_root),
            release_id,
            environment,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=process_environment,
    )


def test_release_operation_lock__active_ship_blocks_discard__local_contract(
    tmp_path: Path,
) -> None:
    lock_root = tmp_path / "release-operations"
    release_id = "release-a"

    with release_operation_guard(
        lock_root=lock_root,
        release_ids=(release_id,),
    ):
        result = _child(lock_root, release_id)

    assert result.returncode == 3
    assert "GATE_BLOCK" in result.stdout
    assert f"releaseId={release_id}" in result.stdout


def test_release_operation_lock__canonical_reset_blocks_new_release_writer__local_contract(
    tmp_path: Path,
) -> None:
    lock_root = tmp_path / "release-operations"

    with release_operation_guard(lock_root=lock_root, global_exclusive=True):
        result = _child(lock_root, "release-b")

    assert result.returncode == 3
    assert "canonical release operations" in result.stdout


def test_release_operation_lock__same_environment_serializes_different_releases__local_contract(
    tmp_path: Path,
) -> None:
    lock_root = tmp_path / "release-operations"

    with release_operation_guard(
        lock_root=lock_root,
        release_ids=("release-a",),
        exclusive_releases=True,
        environments=("gamma",),
        exclusive_environments=True,
    ):
        same_environment = _child(lock_root, "release-b", "gamma")
        other_environment = _child(lock_root, "release-b", "beta")

    assert same_environment.returncode == 3
    assert "environment=gamma" in same_environment.stdout
    assert other_environment.returncode == 0
