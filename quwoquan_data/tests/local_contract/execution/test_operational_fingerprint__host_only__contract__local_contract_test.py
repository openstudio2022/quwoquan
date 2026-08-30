from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from content.execution.operational_fingerprint import POLICY_PATH, operational_fingerprint

ROOT = Path(__file__).resolve().parents[4]
LIVE_REFS = (
    "quwoquan_data/scripts/content/execution/closure/publish_ref.py",
    "quwoquan_data/scripts/content/release/canonical/release_header.py",
    "quwoquan_data/scripts/content/release/environment/importers.py",
    "quwoquan_ops/cli/lib/target_uat_binding.py",
    "quwoquan_ops/cli/lib/environment_acceptance_fact.py",
    "quwoquan_ops/cli/lib/readiness_case_result.py",
)
RETIREMENT_INVENTORY = "quwoquan_data/control_plane/execution/legacy_orchestration_retirement.json"


def _copy_policy_inputs(destination: Path) -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy_path = destination / POLICY_PATH.relative_to(ROOT)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_bytes(POLICY_PATH.read_bytes())
    for ref in policy["inputs"]:
        source = ROOT / ref
        target = destination / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


@pytest.mark.parametrize("ref", LIVE_REFS)
def test_fingerprint_changes_when_live_publish_release_or_uat_bytes_change(tmp_path: Path, ref: str) -> None:
    _copy_policy_inputs(tmp_path)
    before = operational_fingerprint(repo_root=tmp_path)
    live = tmp_path / ref
    live.write_bytes(live.read_bytes() + b"\n# operational-fingerprint-drift\n")
    assert operational_fingerprint(repo_root=tmp_path) != before


def test_fingerprint_ignores_unreachable_legacy_family_bytes(tmp_path: Path) -> None:
    _copy_policy_inputs(tmp_path)
    before = operational_fingerprint(repo_root=tmp_path)
    dead = tmp_path / "quwoquan_data/scripts/content/execution/controller/dead.py"
    dead.parent.mkdir(parents=True)
    dead.write_text("raise RuntimeError('unreachable')\n", encoding="utf-8")
    assert operational_fingerprint(repo_root=tmp_path) == before


def test_fingerprint_ignores_retirement_inventory_governance_state(tmp_path: Path) -> None:
    _copy_policy_inputs(tmp_path)
    before = operational_fingerprint(repo_root=tmp_path)
    inventory = tmp_path / RETIREMENT_INVENTORY
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text('{"state":"operationally_retired"}\n', encoding="utf-8")
    assert operational_fingerprint(repo_root=tmp_path) == before
    inventory.write_text('{"state":"retired"}\n', encoding="utf-8")
    assert operational_fingerprint(repo_root=tmp_path) == before


def test_policy_does_not_bind_retirement_inventory() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert RETIREMENT_INVENTORY not in policy["inputs"]
