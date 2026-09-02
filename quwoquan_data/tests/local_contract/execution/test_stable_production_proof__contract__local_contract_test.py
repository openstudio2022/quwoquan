"""GWT-034 one four-carrier M1 pre-delete proof contract."""
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
from quwoquan_ops.cli.lib import environment_acceptance_fact as eaf_subject  # noqa: E402
from quwoquan_data.tests.support.stable_production_proof_fixture import (  # noqa: E402
    build_proof_fixture,
)


@pytest.fixture
def proof_request(tmp_path: Path) -> dict[str, object]:
    return build_proof_fixture(tmp_path.resolve())


def _evaluate(root: Path, request: dict[str, object]) -> dict[str, object]:
    return subject.evaluate_stable_production_proof(
        artifact_root=root.resolve(),
        expected_fingerprint=str(request["fingerprint"]),
        verify_all_receipt=request["verifyAllReceipt"],  # type: ignore[arg-type]
        public_cli_live_import_zero_receipt=request["publicCliLiveImportZeroReceipt"],  # type: ignore[arg-type]
        proof_units=request["proofUnits"],  # type: ignore[arg-type]
        allow_test_evidence=True,
    )


def _unit(request: dict[str, object]) -> dict[str, Any]:
    return request["proofUnits"][0]  # type: ignore[index,return-value]


def _carrier(request: dict[str, object], carrier: str = "homepage") -> dict[str, Any]:
    return _unit(request)["carrierExecutions"][carrier]


def _rewrite(
    root: Path,
    binding: dict[str, str],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    path = root / binding["ref"]
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    binding["exactByteDigest"] = subject.exact_byte_digest(path)


def _acceptance(request: dict[str, object], root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    binding = _unit(request)["environmentAcceptanceFact"]
    return binding, json.loads((root / binding["ref"]).read_text(encoding="utf-8"))


def _write_acceptance(
    request: dict[str, object], root: Path, document: dict[str, Any]
) -> None:
    binding = _unit(request)["environmentAcceptanceFact"]
    document["factId"] = eaf_subject.derive_fact_id(document)
    path = root / binding["ref"]
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    binding["exactByteDigest"] = subject.exact_byte_digest(path)


def _raw_result(
    request: dict[str, object], root: Path, *, index: int = 0
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    _binding, acceptance = _acceptance(request, root)
    raw_binding = acceptance["requiredRawResults"][index]
    raw_path = root / raw_binding["ref"]
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    return acceptance, raw, raw_binding


def _write_raw_and_acceptance(
    request: dict[str, object], root: Path, acceptance: dict[str, Any],
    raw: dict[str, Any], raw_binding: dict[str, str],
) -> None:
    raw_path = root / raw_binding["ref"]
    raw_path.write_text(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    raw_binding["digest"] = subject.exact_byte_digest(raw_path)
    _write_acceptance(request, root, acceptance)


def test_projects_one_unit_four_executions_and_api_matrix_without_writes(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    root = tmp_path.resolve()
    before = sorted(
        (item.relative_to(root).as_posix(), item.read_bytes())
        for item in root.rglob("*") if item.is_file()
    )
    first = _evaluate(root, proof_request)
    second = _evaluate(root, deepcopy(proof_request))
    after = sorted(
        (item.relative_to(root).as_posix(), item.read_bytes())
        for item in root.rglob("*") if item.is_file()
    )
    schema = json.loads(
        (ROOT / "quwoquan_data/schema/execution/stable_production_proof_set.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(first)
    assert first == second
    assert first["proofUnitCount"] == 1
    assert first["executionCount"] == 4
    assert len(first["unitIds"]) == len(first["releaseIds"]) == 1
    assert len(first["executionIds"]) == 4
    assert first["carrierCountsPerUnit"] == subject.BASELINE_COUNTS
    assert len(first["proofUnits"][0]["environmentEvidence"]["apiConsumerRawResults"]) == 16
    assert first["proofUnits"][0]["environment"] == "alpha"
    assert before == after


def test_rejects_second_proof_unit(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    proof_request["proofUnits"].append(deepcopy(_unit(proof_request)))  # type: ignore[union-attr]
    with pytest.raises(subject.StableProductionProofError, match="exactly one proofUnit"):
        _evaluate(tmp_path, proof_request)


def test_rejects_missing_carrier(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _unit(proof_request)["carrierExecutions"].pop("image")
    with pytest.raises(subject.StableProductionProofError, match="exactly homepage/article/image/video"):
        _evaluate(tmp_path, proof_request)


def test_rejects_execution_carrier_identity_mismatch(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _carrier(proof_request, "article")["executionId"] = _carrier(proof_request)["executionId"]
    with pytest.raises(subject.StableProductionProofError, match="carrier key article differs"):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize(
    ("binding_name", "field"),
    [
        ("carrierDemand", "quota"),
        ("candidateBindings", "candidateCount"),
        ("taskInitRequest", "quota"),
        ("taskInitRequest", "workUnitCount"),
        ("targetSet", "targetCount"),
    ],
)
def test_rejects_task_init_counts_not_one(
    tmp_path: Path, proof_request: dict[str, object], binding_name: str, field: str
) -> None:
    _rewrite(tmp_path, _carrier(proof_request)[binding_name], lambda value: value.update({field: 2}))
    with pytest.raises(subject.StableProductionProofError, match="quota/candidate/workUnit/target all equal 1"):
        _evaluate(tmp_path, proof_request)


def test_rejects_shared_execution_inside_unit(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _unit(proof_request)["carrierExecutions"]["article"] = deepcopy(_carrier(proof_request))
    with pytest.raises(subject.StableProductionProofError, match="carrier key article differs|executionIds must be independent"):
        _evaluate(tmp_path, proof_request)


def test_rejects_m100_impersonating_m1(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _rewrite(
        tmp_path,
        _unit(proof_request)["release"]["header"],
        lambda value: value.update({
            "milestone": "M100",
            "milestoneTargets": subject.BASELINE_COUNTS,
            "selectionScope": "milestone",
        }),
    )
    with pytest.raises(subject.StableProductionProofError, match="non-milestone Research|milestoneTargets|digest drift"):
        _evaluate(tmp_path, proof_request)


def test_rejects_missing_api_raw_cell(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _binding, acceptance = _acceptance(proof_request, tmp_path)
    acceptance["requiredRawResults"].pop()
    _write_acceptance(proof_request, tmp_path, acceptance)
    with pytest.raises(subject.StableProductionProofError, match="canonical EnvironmentAcceptanceFact rejected|exactly 16 raw Service API cells|exact binding digest drift"):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize(
    ("request_key", "mutation", "message"),
    [
        ("verifyAllReceipt", lambda value: value.update({"verdict": "failed", "exitCode": 1}), "canonical schema invalid|passing canonical receipt"),
        ("publicCliLiveImportZeroReceipt", lambda value: value.update({"verdict": "failed", "exitCode": 1}), "canonical schema invalid|passing canonical receipt"),
    ],
)
def test_rejects_failed_operational_receipts(
    tmp_path: Path, proof_request: dict[str, object], request_key: str,
    mutation: Callable[[dict[str, Any]], None], message: str,
) -> None:
    _rewrite(tmp_path, proof_request[request_key], mutation)  # type: ignore[arg-type]
    with pytest.raises(subject.StableProductionProofError, match=message):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize("request_key", ["verifyAllReceipt", "publicCliLiveImportZeroReceipt"])
def test_rejects_missing_operational_receipt(
    tmp_path: Path, proof_request: dict[str, object], request_key: str
) -> None:
    proof_request[request_key] = {}
    with pytest.raises(subject.StableProductionProofError, match="ref and exactByteDigest"):
        _evaluate(tmp_path, proof_request)


def test_rejects_public_cli_receipt_identity_digest_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _rewrite(
        tmp_path,
        proof_request["publicCliLiveImportZeroReceipt"],  # type: ignore[arg-type]
        lambda value: value.update({"receiptId": "sha256:" + "0" * 64}),
    )
    with pytest.raises(subject.StableProductionProofError, match="identity digest drifted"):
        _evaluate(tmp_path, proof_request)


def test_rejects_api_authority_runner_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    acceptance, raw, raw_binding = _raw_result(proof_request, tmp_path)
    raw["runnerIdentity"] = "qwq_service.content_api.drifted.v1"
    _write_raw_and_acceptance(proof_request, tmp_path, acceptance, raw, raw_binding)
    with pytest.raises(subject.StableProductionProofError, match="required sample-plan cell|authority|exact binding digest drift"):
        _evaluate(tmp_path, proof_request)


def test_rejects_api_authority_import_run_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    acceptance, raw, raw_binding = _raw_result(proof_request, tmp_path)
    raw["importRunId"] = "other-import-run"
    _write_raw_and_acceptance(proof_request, tmp_path, acceptance, raw, raw_binding)
    with pytest.raises(subject.StableProductionProofError, match="identity drifted at importRunId|exact binding digest drift"):
        _evaluate(tmp_path, proof_request)


def test_rejects_promotion_profile_impersonation(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _binding, acceptance = _acceptance(proof_request, tmp_path)
    acceptance["acceptanceProfile"] = "environment_promotion"
    _write_acceptance(proof_request, tmp_path, acceptance)
    with pytest.raises(subject.StableProductionProofError, match="canonical EnvironmentAcceptanceFact rejected|m1_api_consumer|exact binding digest drift"):
        _evaluate(tmp_path, proof_request)


def test_rejects_app_or_device_authority_in_api_profile(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    acceptance, raw, raw_binding = _raw_result(proof_request, tmp_path)
    raw.update({"producer": "app", "layer": "user_acceptance", "deviceId": "physical-1"})
    _write_raw_and_acceptance(proof_request, tmp_path, acceptance, raw, raw_binding)
    with pytest.raises(subject.StableProductionProofError, match="Service API integration|App/device authority|exact binding digest drift"):
        _evaluate(tmp_path, proof_request)


@pytest.mark.parametrize("carrier", ["homepage", "video"])
def test_rejects_append_or_replay_delta_drift(
    tmp_path: Path, proof_request: dict[str, object], carrier: str
) -> None:
    execution = _carrier(proof_request, carrier)
    _rewrite(
        tmp_path,
        execution["poolDeliveryResult"],
        lambda value: value.update({"poolDelta": 0 if value["appendedCount"] else 1}),
    )
    with pytest.raises(subject.StableProductionProofError, match="appended=>delta1 or replayed=>delta0"):
        _evaluate(tmp_path, proof_request)


def test_retry_of_is_not_required(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    assert all(
        _carrier(proof_request, carrier)["executionId"].endswith("-001")
        for carrier in subject.CARRIERS
    )
    assert _evaluate(tmp_path, proof_request)["verdict"] == "pass"


def test_rejects_fingerprint_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _unit(proof_request)["fingerprint"] = "sha256:" + "e" * 64
    with pytest.raises(subject.StableProductionProofError, match="current fingerprint"):
        _evaluate(tmp_path, proof_request)


def test_rejects_exact_byte_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    publish = _carrier(proof_request)["canonicalPublish"]
    (tmp_path / publish["ref"]).write_bytes((tmp_path / publish["ref"]).read_bytes() + b" ")
    with pytest.raises(subject.StableProductionProofError, match="exact-byte digest drifted|exact binding digest drift"):
        _evaluate(tmp_path, proof_request)


def test_production_evaluator_rejects_test_only_fixture(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    with pytest.raises(subject.StableProductionProofError, match="test_only evidence"):
        subject.evaluate_stable_production_proof(
            artifact_root=tmp_path.resolve(),
            expected_fingerprint=str(proof_request["fingerprint"]),
            verify_all_receipt=proof_request["verifyAllReceipt"],  # type: ignore[arg-type]
            public_cli_live_import_zero_receipt=proof_request["publicCliLiveImportZeroReceipt"],  # type: ignore[arg-type]
            proof_units=proof_request["proofUnits"],  # type: ignore[arg-type]
        )


def test_rejects_canonical_object_bytes_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    delivery_ref = _carrier(proof_request)["poolDeliveryResult"]
    delivery = json.loads((tmp_path / delivery_ref["ref"]).read_text(encoding="utf-8"))
    canonical_ref = delivery["canonicalObjects"][0]["canonicalObjectRef"]
    (tmp_path / "canonical-publish" / canonical_ref / "content.json").write_text(
        '{"drifted":true}\n', encoding="utf-8"
    )
    with pytest.raises(subject.StableProductionProofError, match="canonical object bytes drifted"):
        _evaluate(tmp_path, proof_request)


def test_rejects_apply_report_identity_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    _rewrite(
        tmp_path, _carrier(proof_request)["applyReport"],
        lambda value: value.update({"transactionId": "drifted-transaction"}),
    )
    with pytest.raises(subject.StableProductionProofError, match="apply report identity drifted"):
        _evaluate(tmp_path, proof_request)


def test_rejects_pool_record_exact_bytes_drift(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    execution = _carrier(proof_request)
    binding = execution["poolRecord"]
    (tmp_path / binding["ref"]).write_bytes((tmp_path / binding["ref"]).read_bytes() + b" ")
    delivery_binding = execution["poolDeliveryResult"]
    delivery_path = tmp_path / delivery_binding["ref"]
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    canonical_ref = delivery["canonicalObjects"][0]["canonicalObjectRef"]
    canonical_digest = subject.tree_integrity_stats(
        tmp_path / "canonical-publish" / canonical_ref
    )["merkleRoot"]
    delivery["canonicalObjects"][0]["canonicalObjectSha256"] = canonical_digest
    delivery["objectResults"][0]["canonicalObject"]["canonicalObjectSha256"] = canonical_digest
    delivery_path.write_text(
        json.dumps(delivery, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    delivery_binding["exactByteDigest"] = subject.exact_byte_digest(delivery_path)
    with pytest.raises(subject.StableProductionProofError, match="exact-byte digest drifted"):
        _evaluate(tmp_path, proof_request)


def test_rejects_pool_record_ref_escape(
    tmp_path: Path, proof_request: dict[str, object]
) -> None:
    execution = _carrier(proof_request)
    delivery_binding = execution["poolDeliveryResult"]
    escaped = "canonical-publish/posts/other/_pool/versions/1.json"
    escaped_path = tmp_path / escaped
    escaped_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_path.write_bytes((tmp_path / execution["poolRecord"]["ref"]).read_bytes())
    execution["poolRecord"] = {"ref": escaped, "exactByteDigest": subject.exact_byte_digest(escaped_path)}
    with pytest.raises(subject.StableProductionProofError, match="pool record ref escapes"):
        _evaluate(tmp_path, proof_request)
