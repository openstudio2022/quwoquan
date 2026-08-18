# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-001
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for import_path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from content.execution.planning.recipe import model as recipe  # noqa: E402
from support.capacity_calibration_fixture import (  # noqa: E402
    SYNTHETIC_FROZEN_AT_EPOCH_SECONDS,
    synthetic_capacity_source_binding,
    write_synthetic_capacity_receipt,
)

EXECUTION_ID = "20260722--travel-homepage-coverage--test-region-a--pilot-001"


@pytest.fixture(autouse=True)
def _default_capacity_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import paths as core_paths

    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", tmp_path)
    receipt_ref = "data/local/tests/capacity/capacity.json"
    write_synthetic_capacity_receipt(tmp_path / receipt_ref)
    original = recipe.RuntimeExecutionRequest.from_args

    def from_args(args: argparse.Namespace):
        if (
            not getattr(args, "disable_capacity_fixture", False)
            and not getattr(args, "capacity_calibration_receipt", None)
        ):
            args.capacity_calibration_receipt = receipt_ref
        if not getattr(args, "semantic_selection_id", None):
            args.semantic_selection_id = "default"
        return original(args)

    monkeypatch.setattr(recipe.RuntimeExecutionRequest, "from_args", from_args)


def test_capacity_source_is_bound_before_exact_workload_derivation(
    tmp_path: Path,
) -> None:
    from content.execution.planning.capacity_policy import (
        derive_workload_capacity_fields,
        workload_plan_digest,
        workload_plan_document,
    )

    receipt_ref = "data/local/tests/capacity/capacity.json"
    write_synthetic_capacity_receipt(tmp_path / receipt_ref)
    args = argparse.Namespace(
        execution_id="20260722--travel-article-supply--test-region-b--pilot-001",
        family="content/travel/article/article",
        region_ref="test-region-b",
        selector="priority",
        count=7,
        quota=7,
        capacity_calibration_receipt=receipt_ref,
        semantic_selection_id="default",
        topic=None,
        source_providers=(),
        target_names=(),
    )
    request = recipe.RuntimeExecutionRequest.from_args(args)
    assert request.capacity_calibration["frozenCapacity"][
        "fleetMaxConcurrentWorkers"
    ] == 2

    derived = derive_workload_capacity_fields(
        target_scale="pilot",
        carrier="article",
        work_unit_count=7,
        capacity_calibration=request.capacity_calibration,
        frozen_at_epoch_seconds=SYNTHETIC_FROZEN_AT_EPOCH_SECONDS,
    )
    assert derived["capacityPlanDigest"] == workload_plan_digest(
        workload_plan_document(
            target_scale="pilot",
            carrier="article",
            work_unit_count=7,
            capacity_calibration=request.capacity_calibration,
        )
    )
    assert derived["partitionCount"] == 16
    assert derived["capacityCalibration"]["waveCount"] == 4
    assert "requiredWorkers" not in derived


def test_capacity_receipt_absence_stays_fail_closed() -> None:
    args = argparse.Namespace(
        execution_id="20260722--travel-article-supply--test-region-b--pilot-001",
        family="content/travel/article/article",
        region_ref="test-region-b",
        selector="priority",
        count=1,
        quota=1,
        capacity_calibration_receipt=None,
        disable_capacity_fixture=True,
        semantic_selection_id="default",
        topic=None,
        source_providers=(),
        target_names=(),
    )
    with pytest.raises(SystemExit, match="capacity-calibration-receipt"):
        recipe.RuntimeExecutionRequest.from_args(args)


def test_frozen_runtime_request_rejects_unknown_or_unordered_fields() -> None:
    request = {
        "familyRef": "content/travel/homepage/homepage",
        "regionRef": "test-region-a",
        "selector": "all",
        "count": 1,
        "quota": 1,
        "capacityCalibration": synthetic_capacity_source_binding(),
        "workerHostSetBinding": None,
        "topic": None,
        "sourceProviders": ["provider-b", "provider-a"],
        "targetNames": [],
    }
    with pytest.raises(SystemExit, match="deduplicated and sorted"):
        recipe.RuntimeExecutionRequest.from_document(request)
    request["sourceProviders"] = []
    request["unexpected"] = "value"
    with pytest.raises(SystemExit, match="keys must be exactly"):
        recipe.RuntimeExecutionRequest.from_document(request)


def test_execute_rejects_a_provider_outside_the_vertical_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RejectingProviderPolicy:
        def require_declared(self, provider_ids: tuple[str, ...]) -> None:
            raise ValueError(f"undeclared provider IDs: {provider_ids}")

    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        recipe,
        "load_provider_policy",
        lambda _vertical: RejectingProviderPolicy(),
    )
    args = argparse.Namespace(
        execution_id=EXECUTION_ID,
        retry_of=None,
        family="content/travel/homepage/homepage",
        region_ref="test-region-a",
        selector="source-ready-priority",
        count=1,
        quota=1,
        topic=None,
        source_providers=["provider-a"],
        stage="plan-only",
        recover_stage=None,
        recovery_reason=None,
    )
    with pytest.raises(SystemExit, match="undeclared provider IDs"):
        recipe.handle_execute(args)


def test_execute_cli_accepts_only_explicit_generic_request_parameters() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / "cli.py"), "task", "execute", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for option in (
        "--family",
        "--region-ref",
        "--selector",
        "--count",
        "--target",
        "--campaign-envelope",
        "--image-scale-promotion",
        "--video-scale-promotion",
    ):
        assert option in result.stdout
    assert "promote-scale" in result.stdout
    for retired in ("--rollout", "--province", "--mandatory", "--max-workers"):
        assert retired not in result.stdout
