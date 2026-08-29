"""Canonical contract binding for the page-UAT AppArtifact blocker."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
)

APP_LAUNCH_MANIFEST = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "app_launch_manifest.yaml"
)
OWNER_SPEC = (
    ROOT
    / "specs"
    / "feature-tree"
    / "runtime"
    / "runtime-config"
    / "environment-topology-and-packaging"
    / "spec.md"
)


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
def test_page_artifact_binding_blocker_comes_from_canonical_launch_contract() -> None:
    manifest = yaml.safe_load(APP_LAUNCH_MANIFEST.read_text(encoding="utf-8"))
    launch_blockers = manifest["launch_blockers"]

    assert APP_PAGE_ARTIFACT_BINDING_BLOCKER == (
        "APP.UAT.page_artifact_binding_missing"
    )
    assert APP_PAGE_ARTIFACT_BINDING_BLOCKER in launch_blockers
    assert str(launch_blockers[APP_PAGE_ARTIFACT_BINDING_BLOCKER]).strip()
    assert APP_PAGE_ARTIFACT_BINDING_BLOCKER in OWNER_SPEC.read_text(encoding="utf-8")
