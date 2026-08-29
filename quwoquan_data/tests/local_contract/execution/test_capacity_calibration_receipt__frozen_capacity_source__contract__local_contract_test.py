"""GWT-009 / GWT-010：容量数值与批次绝对截止只能从 calibration receipt 冻结。

绑定 `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/`
`multi-carrier-release/spec.md` 的 `GWT-009.t4`、`GWT-010.t4`、`GWT-011.t2`
与 L2 `design.md` 的 `DEC-003`、`DEC-006`。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-009
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from core.paths import SCHEMA_ROOT  # noqa: E402
from core.schema import assert_valid, load_schema, validate_strict  # noqa: E402

RECEIPT_SCHEMA = "governed_capacity_calibration_receipt"
RECEIPT_PATH = SCHEMA_ROOT / "execution" / f"{RECEIPT_SCHEMA}.schema.json"

FROZEN_CAPACITY_FIELDS = (
    "autoResearchMaxConcurrentWorkers",
    "fleetMaxConcurrentWorkers",
    "objectWallClockSeconds",
    "completionGraceSeconds",
)
FROZEN_LIVENESS_FIELDS = (
    "sourceDiscoveryHeartbeatIntervalSeconds",
    "sourceDiscoveryHeartbeatStaleAfterSeconds",
)
RECEIPT_BINDING_FIELDS = (
    "calibrationId",
    "calibrationReceiptRef",
    "calibrationReceiptDigest",
    "applicability",
)


def _frozen_capacity() -> dict[str, int]:
    """标定数值属于 OPEN-003，本层只证明契约形状而不冻结生产取值。"""
    return {
        "autoResearchMaxConcurrentWorkers": 8,
        "fleetMaxConcurrentWorkers": 8,
        "objectWallClockSeconds": 900,
        "completionGraceSeconds": 300,
    }


def _frozen_liveness() -> dict[str, int]:
    """阶段存活阈值与容量数值同源冻结，但各有自己的取值，不互相挪用。"""
    return {
        "sourceDiscoveryHeartbeatIntervalSeconds": 30,
        "sourceDiscoveryHeartbeatStaleAfterSeconds": 90,
    }


def _applicability() -> dict[str, str]:
    return {"hostClass": "local-apple-silicon", "providerTier": "cursor-grok-standard"}


def _receipt(**overrides: Any) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": "quwoquan_data.governed_capacity_calibration_receipt",
        "calibrationId": "m100-wave-soak-001",
        "supersedesCalibrationId": None,
        "soakEvidenceRef": "evidence/soak/m100-wave-soak-001/evidence.json",
        "soakEvidenceDigest": "sha256:" + "d" * 64,
        "applicability": _applicability(),
        "frozenCapacity": _frozen_capacity(),
        "frozenLiveness": _frozen_liveness(),
        "calibratedAt": "2026-08-16T00:00:00Z",
        "receiptDigest": "sha256:" + "e" * 64,
    }
    receipt.update(overrides)
    return receipt


def _binding_definition() -> dict[str, Any]:
    """按 execution spec 内联后的形态取出 executionPolicy 绑定值对象。"""
    return load_schema("execution", RECEIPT_SCHEMA)["$defs"]["executionPolicyBinding"]


def _binding(**overrides: Any) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "calibrationId": "m100-wave-soak-001",
        "calibrationReceiptRef": (
            "evidence/calibration/m100-wave-soak-001/receipt.json"
        ),
        "calibrationReceiptDigest": "sha256:" + "e" * 64,
        "applicability": _applicability(),
        "frozenCapacity": _frozen_capacity(),
        "frozenLiveness": _frozen_liveness(),
        "frozenAtEpochSeconds": 1_786_000_000,
        "waveCount": 23,
        "fleetBatchDeadlineEpochSeconds": 1_786_021_000,
    }
    binding.update(overrides)
    return binding


def _binding_issues(binding: dict[str, Any]) -> list[str]:
    return validate_strict(binding, _binding_definition())


def test_receipt_with_full_governed_provenance_is_valid() -> None:
    assert_valid(_receipt(), "execution", RECEIPT_SCHEMA)


def test_execution_policy_binding_is_valid() -> None:
    assert _binding_issues(_binding()) == []


@pytest.mark.parametrize("field", FROZEN_CAPACITY_FIELDS)
def test_receipt_without_any_frozen_value_fails_closed(field: str) -> None:
    """GWT-009.t4：任一项缺失即 fail closed，不得由另一项默认补齐。"""
    receipt = _receipt()
    del receipt["frozenCapacity"][field]

    with pytest.raises(ValueError, match=field):
        assert_valid(receipt, "execution", RECEIPT_SCHEMA)


@pytest.mark.parametrize("field", FROZEN_CAPACITY_FIELDS)
def test_binding_without_any_frozen_value_fails_closed(field: str) -> None:
    binding = _binding()
    del binding["frozenCapacity"][field]

    assert _binding_issues(binding) != []


@pytest.mark.parametrize("field", FROZEN_CAPACITY_FIELDS)
def test_frozen_values_declare_no_default_constant(field: str) -> None:
    """DEC-006：缺 receipt 时不落默认常量，契约本身不得提供取值。"""
    schema = load_schema("execution", RECEIPT_SCHEMA)
    declaration = schema["properties"]["frozenCapacity"]["properties"][field]

    assert "default" not in declaration
    assert "const" not in declaration
    assert declaration["minimum"] >= 1


@pytest.mark.parametrize("field", FROZEN_LIVENESS_FIELDS)
def test_receipt_without_any_frozen_liveness_value_fails_closed(field: str) -> None:
    """存活阈值缺任一项即 fail closed，不得由容量数值或默认常量补齐。"""
    receipt = _receipt()
    del receipt["frozenLiveness"][field]

    with pytest.raises(ValueError, match=field):
        assert_valid(receipt, "execution", RECEIPT_SCHEMA)


@pytest.mark.parametrize("field", FROZEN_LIVENESS_FIELDS)
def test_frozen_liveness_values_declare_no_default_constant(field: str) -> None:
    """契约本身不提供存活阈值取值：缺 receipt 时没有可落的默认常量。"""
    schema = load_schema("execution", RECEIPT_SCHEMA)
    declaration = schema["properties"]["frozenLiveness"]["properties"][field]

    assert "default" not in declaration
    assert "const" not in declaration
    assert declaration["minimum"] >= 1


def test_frozen_liveness_is_a_separate_value_object_from_frozen_capacity() -> None:
    """存活阈值与容量数值是两组取值：字段集不重叠，也不互相引用。"""
    schema = load_schema("execution", RECEIPT_SCHEMA)
    capacity_fields = set(schema["properties"]["frozenCapacity"]["properties"])
    liveness_fields = set(schema["properties"]["frozenLiveness"]["properties"])

    assert capacity_fields.isdisjoint(liveness_fields)
    assert liveness_fields == set(FROZEN_LIVENESS_FIELDS)


def test_binding_frozen_values_are_the_same_definition_as_the_receipt() -> None:
    """DEC-006：冻结后的执行策略数值与 receipt 内容逐字段相等。

    两处引用同一共享值对象，字段集与约束不可能分别漂移。
    """
    schema = load_schema("execution", RECEIPT_SCHEMA)

    assert (
        schema["$defs"]["executionPolicyBinding"]["properties"]["frozenCapacity"]
        == schema["properties"]["frozenCapacity"]
    )
    assert (
        schema["$defs"]["executionPolicyBinding"]["properties"]["frozenLiveness"]
        == schema["properties"]["frozenLiveness"]
    )
    assert (
        schema["$defs"]["executionPolicyBinding"]["properties"]["applicability"]
        == schema["properties"]["applicability"]
    )


@pytest.mark.parametrize("field", RECEIPT_BINDING_FIELDS)
def test_binding_must_name_the_receipt_it_froze_from(field: str) -> None:
    """DEC-006：缺 receipt、摘要漂移与超范围复用都必须可判定。"""
    binding = _binding()
    del binding[field]

    assert _binding_issues(binding) != []


def test_binding_rejects_a_digest_that_is_not_a_sha256_binding() -> None:
    assert _binding_issues(_binding(calibrationReceiptDigest="unverified")) != []


def test_binding_carries_the_absolute_batch_deadline() -> None:
    """GWT-010.t4 / DEC-003：绝对截止在冻结时定值并随 execution 持久化。"""
    binding = _binding()
    del binding["fleetBatchDeadlineEpochSeconds"]

    assert _binding_issues(binding) != []
    assert _binding_issues(_binding(fleetBatchDeadlineEpochSeconds=0)) != []


def test_binding_carries_the_freeze_instant_and_wave_count() -> None:
    """DEC-003：截止取值由冻结时刻、wave 数与单对象上限决定，三项都要可复核。"""
    for field in ("frozenAtEpochSeconds", "waveCount"):
        binding = _binding()
        del binding[field]
        assert _binding_issues(binding) != []

    assert _binding_issues(_binding(waveCount=0)) != []


def test_receipt_itself_carries_no_batch_deadline() -> None:
    """DEC-006：运行期不得按路径实时重读 receipt 改变在跑批次的截止。

    截止只存在于已冻结的 execution 绑定里，receipt 侧没有可被替换的截止字段。
    """
    schema = load_schema("execution", RECEIPT_SCHEMA)

    assert "fleetBatchDeadlineEpochSeconds" not in schema["properties"]
    assert "fleetBatchDeadlineEpochSeconds" not in schema["properties"][
        "frozenCapacity"
    ]["properties"]


def test_receipt_records_its_supersession_lineage() -> None:
    """DEC-006：改数值只能产出新 receipt，回滚是重新绑定上一份仍有效的 receipt。"""
    assert_valid(
        _receipt(supersedesCalibrationId="m100-wave-soak-000"),
        "execution",
        RECEIPT_SCHEMA,
    )

    receipt = _receipt()
    del receipt["supersedesCalibrationId"]
    with pytest.raises(ValueError, match="supersedesCalibrationId"):
        assert_valid(receipt, "execution", RECEIPT_SCHEMA)


def test_receipt_declares_its_applicability_scope() -> None:
    """DEC-006：超出运行主机类别与 Provider 档位的 execution 不得复用其数值。"""
    receipt = _receipt()
    del receipt["applicability"]

    with pytest.raises(ValueError, match="applicability"):
        assert_valid(receipt, "execution", RECEIPT_SCHEMA)


def test_binding_definition_is_inlinable_by_the_execution_spec() -> None:
    """外部引用的 $defs 不得含内部 $ref，否则被内联进 execution spec 后无法解析。"""
    raw = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    resolved = _binding_definition()

    assert _internal_refs(raw["$defs"]["executionPolicyBinding"]) == []
    assert _internal_refs(resolved) == []


def _internal_refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        found = [
            value
            for key, value in node.items()
            if key == "$ref" and isinstance(value, str) and value.startswith("#/")
        ]
        for value in node.values():
            found.extend(_internal_refs(value))
        return found
    if isinstance(node, list):
        return [ref for item in node for ref in _internal_refs(item)]
    return []
