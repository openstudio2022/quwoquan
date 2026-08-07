# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from content.execution.campaign.source_snapshot import (
    materialize_source_snapshot,
    source_snapshot_roots,
)
from core.source_digest import current_source_digest

ROOT = Path(__file__).resolve().parents[4]


def test_campaign_source_capsule_imports_canonical_release_without_ops_tree(
    tmp_path: Path,
) -> None:
    source_digest = current_source_digest(repo_root=ROOT).digest
    roots = source_snapshot_roots(ROOT, expected_digest=source_digest)
    capsule = tmp_path / "source-capsule"

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
