# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-034
"""Global layout scan distinguishes current host task-init from managed legacy packages."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot  # noqa: E402
from verify import verify_content_execution_layout as layout  # noqa: E402


EXECUTION_ID = "20260831--travel-article-host-init--china--pilot-001"


def _target_set_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_current_task_init(tasks_root: Path) -> Path:
    execution_root = tasks_root / EXECUTION_ID
    plan_root = execution_root / "0.plan"
    plan_root.mkdir(parents=True)
    carrier_demand = {
        "ref": "data/local/workspace/carrier-demand.json",
        "digest": "sha256:" + "1" * 64,
        "workRequestRef": "data/local/workspace/work-request.json",
        "workRequestDigest": "sha256:" + "2" * 64,
    }
    candidate_binding = {
        "ref": "data/local/workspace/candidate-bindings.json",
        "digest": "sha256:" + "3" * 64,
    }
    request = {
        "schema": "quwoquan_data.task_init_request",
        "executionId": EXECUTION_ID,
        "familyRef": "content/travel/article/article",
        "carrier": "article",
        "quota": 1,
        "workUnitCount": 1,
        "carrierDemand": carrier_demand,
        "candidateBinding": candidate_binding,
        "retryOf": None,
    }
    target_set = {
        "executionId": EXECUTION_ID,
        "selectionPolicy": "frozen",
        "sourceRef": "data/local/workspace/source-pool.json",
        "candidateBinding": {**candidate_binding, "candidateCount": 1},
        "entityCatalogDigest": "sha256:" + "4" * 64,
        "targetCount": 1,
        "targetRefs": ["posts/article/攻略/西湖一日游/1"],
        "targets": [{
            "name": "西湖",
            "entityType": "地点/景区",
            "publishAngle": "攻略",
            "publishTitle": "西湖一日游",
            "publishSeq": 1,
        }],
    }
    manifest = {
        "executionId": EXECUTION_ID,
        "familyRef": {
            "ref": "content/travel/article/article",
            "sha256": "5" * 64,
        },
        "sourceDigest": SourceDefinitionSnapshot(digest="sha256:" + "6" * 64).to_document(),
        "executionBundle": ExecutionBundleIdentity(digest="sha256:" + "7" * 64).to_document(),
        "operationalFingerprint": "sha256:" + "8" * 64,
        "hostRuntime": "external_host_agent",
        "carrierDemand": carrier_demand,
        "requestRef": "0.plan/request.json",
        "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": _target_set_digest(target_set),
        "retryOf": None,
    }
    for target, value in (
        (execution_root / "execution_manifest.json", manifest),
        (plan_root / "request.json", request),
        (plan_root / "target_set.json", target_set),
    ):
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return execution_root


@pytest.fixture
def isolated_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tasks_root = tmp_path / "tasks"
    monkeypatch.setattr(layout, "DATA_EXECUTIONS_ROOT", tasks_root)
    monkeypatch.setattr(layout, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(layout.verify_task_init_contract.paths, "DATA_EXECUTIONS_ROOT", tasks_root)
    monkeypatch.setattr(layout, "load_terminal_execution_evidence", lambda _root: None)
    return tasks_root


def test_global_scan_accepts_current_host_task_init_without_execution_spec(
    isolated_layout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_current_task_init(isolated_layout)
    monkeypatch.setattr(
        layout,
        "load_spec",
        lambda _execution_id: pytest.fail("current host task-init must not load execution_spec.yaml"),
    )

    assert layout.content_execution_layout_issues() == []


def test_global_scan_defers_legacy_raw_byte_digest_generation(
    isolated_layout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_root = _write_current_task_init(isolated_layout)
    target_set_path = execution_root / "0.plan/target_set.json"
    manifest_path = execution_root / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["targetSetDigest"] = hashlib.sha256(target_set_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        layout.verify_task_init_contract,
        "issues",
        lambda _execution_id: pytest.fail("legacy raw-byte generation is not current"),
    )
    monkeypatch.setattr(
        layout,
        "_frozen_target_issues",
        lambda _root: pytest.fail("legacy host task-init is not a managed execution_spec package"),
    )

    assert layout.content_execution_layout_issues() == []


def test_global_scan_rejects_current_three_file_drift(
    isolated_layout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_root = _write_current_task_init(isolated_layout)
    manifest_path = execution_root / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["targetSetDigest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        layout,
        "load_spec",
        lambda _execution_id: pytest.fail("current drift must not fall back to the legacy spec"),
    )

    issues = layout.content_execution_layout_issues()

    assert any("task-init targetSetDigest drift" in issue for issue in issues)


def test_current_scan_keeps_root_identity_and_object_stage_checks(
    isolated_layout: Path,
) -> None:
    execution_root = _write_current_task_init(isolated_layout)
    (execution_root / "unexpected.txt").write_text("drift", encoding="utf-8")
    evidence = execution_root / "evidence/identity.json"
    evidence.parent.mkdir()
    evidence.write_text(json.dumps({"taskId": "retired"}), encoding="utf-8")
    partial_object = execution_root / "posts/article/攻略/西湖一日游/1"
    (partial_object / "2.quality").mkdir(parents=True)

    issues = layout.content_execution_layout_issues()

    assert any("not allowed in an execution work package" in issue for issue in issues)
    assert any("retired identity; use executionId" in issue for issue in issues)
    assert any("missing execution stages" in issue for issue in issues)


def test_external_host_managed_package_keeps_legacy_validator(
    isolated_layout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_root = isolated_layout / EXECUTION_ID
    plan_root = execution_root / "0.plan"
    plan_root.mkdir(parents=True)
    (execution_root / "execution_manifest.json").write_text(
        json.dumps({"executionId": EXECUTION_ID, "hostRuntime": "external_host_agent"}),
        encoding="utf-8",
    )
    (plan_root / "execution_spec.yaml").write_text("scope: {}\n", encoding="utf-8")
    observed: list[Path] = []

    def legacy_issues(root: Path) -> list[str]:
        observed.append(root)
        return ["legacy-drift"]

    monkeypatch.setattr(layout, "_frozen_target_issues", legacy_issues)
    monkeypatch.setattr(
        layout.verify_task_init_contract,
        "issues",
        lambda _execution_id: pytest.fail("managed package must retain legacy validation"),
    )

    assert layout.content_execution_layout_issues() == ["legacy-drift"]
    assert observed == [execution_root]
