"""GWT-034 three independent four-carrier pre-delete proof contract."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator

DATA_ROOT = Path(__file__).resolve().parents[3]
ROOT = DATA_ROOT.parent
SCRIPTS = DATA_ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.execution import stable_production_proof as subject  # noqa: E402
from quwoquan_data.tests.support.stable_production_proof_fixture import (  # noqa: E402
    FINGERPRINT,
    build_proof_fixture,
)


@pytest.fixture
def proof_request(tmp_path: Path) -> dict[str, object]:
    return build_proof_fixture(tmp_path.resolve())


def _evaluate(root: Path, request: dict[str, object]) -> dict[str, object]:
    return subject.evaluate_stable_production_proof(
        artifact_root=root.resolve(),
        expected_fingerprint=str(request["fingerprint"]),
        proof_units=request["proofUnits"],  # type: ignore[arg-type]
    )


def _units(request: dict[str, object]) -> list[dict[str, Any]]:
    return request["proofUnits"]  # type: ignore[return-value]


def _carrier(request: dict[str, object], unit: int = 0, carrier: str = "homepage") -> dict[str, Any]:
    return _units(request)[unit]["carrierExecutions"][carrier]


def _rewrite(root: Path, binding: dict[str, str], mutate: Callable[[dict[str, Any]], None]) -> None:
    path = root / binding["ref"]
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    binding["exactByteDigest"] = subject.exact_byte_digest(path)


def _acceptance_binding(request: dict[str, object], unit: int = 0) -> dict[str, str]:
    return _units(request)[unit]["environmentAcceptanceFact"]


def _target_binding(root: Path, request: dict[str, object], unit: int = 0) -> tuple[dict[str, Any], dict[str, str]]:
    acceptance_ref = _acceptance_binding(request, unit)
    acceptance = json.loads((root / acceptance_ref["ref"]).read_text(encoding="utf-8"))
    item = acceptance["targetBindingRefs"][0]
    return acceptance, {"ref": item["ref"], "exactByteDigest": item["digest"]}


def _rewrite_target_binding(root: Path, request: dict[str, object], mutate: Callable[[dict[str, Any]], None], unit: int = 0) -> None:
    acceptance, binding = _target_binding(root, request, unit)
    _rewrite(root, binding, mutate)
    acceptance["targetBindingRefs"][0]["digest"] = binding["exactByteDigest"]
    acceptance_path = root / _acceptance_binding(request, unit)["ref"]
    acceptance_path.write_text(json.dumps(acceptance, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _acceptance_binding(request, unit)["exactByteDigest"] = subject.exact_byte_digest(acceptance_path)


def test_projects_three_independent_units_deterministically_without_writes(tmp_path: Path, proof_request: dict[str, object]) -> None:
    root = tmp_path.resolve()
    before = sorted((item.relative_to(root).as_posix(), item.read_bytes()) for item in root.rglob("*") if item.is_file())
    first = _evaluate(root, proof_request)
    second_request = deepcopy(proof_request)
    second_request["proofUnits"] = list(reversed(second_request["proofUnits"]))  # type: ignore[index]
    second = _evaluate(root, second_request)
    after = sorted((item.relative_to(root).as_posix(), item.read_bytes()) for item in root.rglob("*") if item.is_file())
    schema = json.loads((ROOT / "quwoquan_data/schema/execution/stable_production_proof_set.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(first)
    assert first == second
    assert first["proofUnitCount"] == 3
    assert first["executionCount"] == 12
    assert len(first["unitIds"]) == len(first["releaseIds"]) == 3
    assert len(first["executionIds"]) == 12
    assert first["carrierCountsPerUnit"] == subject.BASELINE_COUNTS
    assert len(first["retryRecoveryExecutionIds"]) == 1
    assert all(len(unit["environmentEvidence"]["appConsumerRawResults"]) == 16 for unit in first["proofUnits"])
    assert before == after


@pytest.mark.parametrize("count", [2, 4])
def test_rejects_wrong_unit_count(tmp_path: Path, proof_request: dict[str, object], count: int) -> None:
    units = _units(proof_request)
    proof_request["proofUnits"] = units[:count] if count == 2 else [*units, deepcopy(units[0])]
    with pytest.raises(subject.StableProductionProofError, match="exactly three proofUnits"):
        _evaluate(tmp_path, proof_request)


def test_rejects_missing_carrier(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _units(proof_request)[0]["carrierExecutions"].pop("image")
    with pytest.raises(subject.StableProductionProofError, match="exactly homepage/article/image/video"):
        _evaluate(tmp_path, proof_request)


def test_rejects_execution_carrier_identity_mismatch(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _carrier(proof_request, carrier="article")["executionId"] = _carrier(proof_request, carrier="homepage")["executionId"]
    with pytest.raises(subject.StableProductionProofError, match="carrier key article differs"):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize(
    ("binding_name", "field"),
    [("carrierDemand", "quota"), ("candidateBindings", "candidateCount"), ("taskInitRequest", "quota"), ("taskInitRequest", "workUnitCount"), ("targetSet", "targetCount")],
)
def test_rejects_task_init_counts_not_one(tmp_path: Path, proof_request: dict[str, object], binding_name: str, field: str) -> None:
    _rewrite(tmp_path, _carrier(proof_request)[binding_name], lambda value: value.update({field: 2}))
    with pytest.raises(subject.StableProductionProofError, match="quota/candidate/workUnit/target all equal 1"):
        _evaluate(tmp_path, proof_request)


def test_rejects_shared_execution(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _units(proof_request)[1]["carrierExecutions"]["homepage"] = deepcopy(_carrier(proof_request))
    with pytest.raises(subject.StableProductionProofError, match="twelve executionIds must be independent"):
        _evaluate(tmp_path, proof_request)


def test_rejects_shared_release(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _units(proof_request)[1]["release"] = deepcopy(_units(proof_request)[0]["release"])
    with pytest.raises(subject.StableProductionProofError, match="release must bind exactly"):
        _evaluate(tmp_path, proof_request)


def test_rejects_shared_acceptance(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _units(proof_request)[1]["environmentAcceptanceFact"] = deepcopy(_units(proof_request)[0]["environmentAcceptanceFact"])
    with pytest.raises(subject.StableProductionProofError, match="release/environment/fingerprint drifted"):
        _evaluate(tmp_path, proof_request)


def test_rejects_m100_impersonating_baseline(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _rewrite(tmp_path, _units(proof_request)[0]["release"]["header"], lambda value: value.update({"milestone": "M100", "milestoneTargets": subject.BASELINE_COUNTS, "selectionScope": "milestone"}))
    with pytest.raises(subject.StableProductionProofError, match="non-milestone Research|milestoneTargets"):
        _evaluate(tmp_path, proof_request)


def test_rejects_missing_raw_cell(tmp_path: Path, proof_request: dict[str, object]) -> None:
    acceptance_ref = _acceptance_binding(proof_request)
    _rewrite(tmp_path, acceptance_ref, lambda value: value["requiredRawResults"].pop())
    with pytest.raises(subject.StableProductionProofError, match="exactly 16 raw App UAT cells|canonical EnvironmentAcceptanceFact rejected"):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["device"].update({"class": "emulator"}),
        lambda value: value.update({"profile": "rehearsal", "nonPromotable": True}),
        lambda value: value["device"].update({"registered": False}),
    ],
)
def test_rejects_non_physical_non_promotable_or_unregistered_device(tmp_path: Path, proof_request: dict[str, object], mutation: Callable[[dict[str, Any]], None]) -> None:
    _rewrite_target_binding(tmp_path, proof_request, mutation)
    with pytest.raises(subject.StableProductionProofError, match="canonical EnvironmentAcceptanceFact rejected|registered physical-device promotable"):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize("carrier", ["homepage", "video"])
def test_rejects_append_or_replay_delta_drift(tmp_path: Path, proof_request: dict[str, object], carrier: str) -> None:
    execution = _carrier(proof_request, unit=2 if carrier == "video" else 0, carrier=carrier)
    _rewrite(tmp_path, execution["poolDeliveryResult"], lambda value: value.update({"poolDelta": 0 if value["appendedCount"] else 1}))
    with pytest.raises(subject.StableProductionProofError, match="appended=>delta1 or replayed=>delta0"):
        _evaluate(tmp_path, proof_request)


def test_rejects_missing_terminal_retry(tmp_path: Path, proof_request: dict[str, object]) -> None:
    execution = _carrier(proof_request, unit=2, carrier="video")
    _rewrite(tmp_path, execution["taskInitRequest"], lambda value: value.update({"retryOf": None}))
    _rewrite(tmp_path, execution["executionManifest"], lambda value: value.update({"retryOf": None}))
    execution["retryRecovery"] = None
    with pytest.raises(subject.StableProductionProofError, match="at least one valid terminal retryOf"):
        _evaluate(tmp_path, proof_request)


def test_rejects_fingerprint_drift(tmp_path: Path, proof_request: dict[str, object]) -> None:
    _units(proof_request)[1]["fingerprint"] = "sha256:" + "e" * 64
    with pytest.raises(subject.StableProductionProofError, match="current fingerprint"):
        _evaluate(tmp_path, proof_request)


def test_rejects_exact_byte_drift(tmp_path: Path, proof_request: dict[str, object]) -> None:
    publish = _carrier(proof_request)["canonicalPublish"]
    (tmp_path / publish["ref"]).write_bytes((tmp_path / publish["ref"]).read_bytes() + b" ")
    with pytest.raises(subject.StableProductionProofError, match="exact-byte digest drifted"):
        _evaluate(tmp_path, proof_request)
