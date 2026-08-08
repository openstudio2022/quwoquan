# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from content.execution.campaign.source_snapshot import (
    materialize_source_snapshot,
    source_snapshot_roots,
)
from core.source_digest import current_source_digest
from support import remove_readonly_test_tree

ROOT = Path(__file__).resolve().parents[4]


def test_campaign_source_capsule_imports_canonical_release_without_ops_tree(
    tmp_path: Path,
) -> None:
    source_digest = current_source_digest(repo_root=ROOT).digest
    roots = source_snapshot_roots(ROOT, expected_digest=source_digest)
    capsule = tmp_path / "source-capsule"

    try:
        materialize_source_snapshot(
            ROOT,
            capsule,
            roots=roots,
            expected_digest=source_digest,
        )

        assert not (capsule / "quwoquan_ops").exists()
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(capsule / "quwoquan_data" / "scripts")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "from core.intersection_signal import contract_field_names; "
                    "from content.release.canonical.aggregate_release "
                    "import build_aggregate_release; "
                    "assert callable(build_aggregate_release); "
                    "assert {'dimension', 'source', 'tagRefs', 'actionType', "
                    "'actionTargetId'} <= contract_field_names()"
                ),
            ],
            cwd=capsule,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
    finally:
        remove_readonly_test_tree(capsule, test_temp_root=tmp_path)


def test_readonly_capsule_cleanup_is_confined_to_explicit_test_root(
    tmp_path: Path,
) -> None:
    owned_root = tmp_path / "owned"
    capsule = owned_root / "source-capsule"
    nested = capsule / "nested"
    nested.mkdir(parents=True)
    source_file = nested / "source.py"
    source_file.write_text("source = True\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.txt").write_text("keep\n", encoding="utf-8")
    (capsule / "outside-link").symlink_to(outside, target_is_directory=True)

    for path in sorted(capsule.rglob("*"), reverse=True):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o222)
    capsule.chmod(capsule.stat().st_mode & ~0o222)
    if hasattr(os, "chflags") and hasattr(stat, "UF_IMMUTABLE"):
        os.chflags(source_file, stat.UF_IMMUTABLE, follow_symlinks=False)

    remove_readonly_test_tree(capsule, test_temp_root=owned_root)

    assert not capsule.exists()
    assert (outside / "evidence.txt").read_text(encoding="utf-8") == "keep\n"
    with pytest.raises(ValueError, match="temporary boundary"):
        remove_readonly_test_tree(outside, test_temp_root=owned_root)
    with pytest.raises(ValueError, match="must not remove"):
        remove_readonly_test_tree(owned_root, test_temp_root=owned_root)
