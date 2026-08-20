"""DEC-006 / DEC-003：calibration receipt 的读取侧与冻结投影。

已有的 `test_capacity_calibration_receipt__frozen_capacity_source__*` 只锁契约
形状；本文件锁生产加载器的行为——三种 fail closed（缺 receipt、摘要漂移、超适用
范围）、冻结后数值与 receipt 逐字段相等，以及 `DEC-003` 的绝对截止推导与 lease
截止取更小者。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-009
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-009.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-009.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-010
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-010.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-010.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-010.t4
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.execution.planning.capacity_calibration import (  # noqa: E402
    CapacityCalibrationError,
    calibration_wave_count,
    freeze_capacity_calibration_binding,
    lease_deadline_epoch_seconds,
    load_capacity_calibration_receipt,
    remaining_batch_seconds,
)

_HOST_CLASS = "local-apple-silicon"
_PROVIDER_TIER = "cursor-grok-standard"
_FROZEN_AT = 1_786_000_000


def _frozen_capacity() -> dict[str, int]:
    """Synthetic 数值只证明加载与投影，不代表生产容量结论。"""
    return {
        "autoResearchMaxConcurrentWorkers": 4,
        "fleetMaxConcurrentWorkers": 8,
        "objectWallClockSeconds": 900,
        "completionGraceSeconds": 300,
    }


def _receipt(**overrides: Any) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": "quwoquan_data.governed_capacity_calibration_receipt",
        "calibrationId": "m100-wave-soak-001",
        "supersedesCalibrationId": None,
        "soakEvidenceRef": "evidence/soak/m100-wave-soak-001/evidence.json",
        "soakEvidenceDigest": "sha256:" + "d" * 64,
        "applicability": {
            "hostClass": _HOST_CLASS,
            "providerTier": _PROVIDER_TIER,
        },
        "frozenCapacity": _frozen_capacity(),
        "calibratedAt": "2026-08-16T00:00:00Z",
    }
    receipt.update(overrides)
    receipt["receiptDigest"] = _self_digest(receipt)
    return receipt


def _self_digest(receipt: dict[str, Any]) -> str:
    document = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_repository_capacity_calibration_receipt_is_self_contained() -> None:
    path = (
        DATA_ROOT
        / "control_plane/_shared/capacity_calibration/"
        / "m100-wave-soak-20260818-v4/receipt.json"
    )
    # OPEN-006 要求缺 receipt 时在干净检出上 GATE_BLOCK。动态 skip 会把这个
    # P0 证据缺口变成静默通过，因此这里断言 receipt 在场：它只能由真实 M100
    # soak 经 capacity_calibration_cli 产出并入库，用规格复述的数值反向合成
    # receipt 恰好会伪造本用例要证的自包含闭包。
    assert path.is_file(), (
        f"governed capacity calibration receipt is missing: {path}. "
        "multi-carrier-release OPEN-006 blocks until a real M100 soak produces it"
    )
    receipt = load_capacity_calibration_receipt(path)
    assert receipt["frozenCapacity"] == {
        "autoResearchMaxConcurrentWorkers": 8,
        "fleetMaxConcurrentWorkers": 3,
        "objectWallClockSeconds": 660,
        "completionGraceSeconds": 60,
    }
    assert receipt["supersedesCalibrationId"] is None
    assert receipt["receiptDigest"] == (
        "sha256:653180ed007d37bd01644f5d19e27b406532cf026a701086a0e06b2beda744f0"
    )


class CapacityCalibrationLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = _receipt()

    def _binding(self, **overrides: Any) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "receipt": self.receipt,
            "receipt_ref": "evidence/calibration/m100-wave-soak-001/receipt.json",
            "host_class": _HOST_CLASS,
            "provider_tier": _PROVIDER_TIER,
            "work_unit_count": 100,
            "frozen_at_epoch_seconds": _FROZEN_AT,
        }
        arguments.update(overrides)
        return freeze_capacity_calibration_binding(**arguments)

    def test_absent_receipt_fails_closed(self) -> None:
        """DEC-006：冻结时没有 receipt 即 GATE_BLOCK，不落默认常量。"""
        with self.assertRaises(CapacityCalibrationError) as caught:
            load_capacity_calibration_receipt(
                Path("/nonexistent/calibration/receipt.json")
            )

        self.assertIn("missing", str(caught.exception))

    def test_receipt_digest_drift_fails_closed(self) -> None:
        """DEC-006：receipt 字节与所绑摘要不一致时拒绝，不接受其数值。"""
        import tempfile

        drifted = _receipt()
        drifted["frozenCapacity"]["fleetMaxConcurrentWorkers"] = 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(
                json.dumps(
                    {**drifted, "receiptDigest": "sha256:" + "0" * 64},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CapacityCalibrationError) as caught:
                load_capacity_calibration_receipt(path)

        self.assertIn("drift", str(caught.exception))

    def test_verified_receipt_document_round_trips_without_evidence_resolution(
        self,
    ) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(
                json.dumps(self.receipt, ensure_ascii=False),
                encoding="utf-8",
            )

            loaded = load_capacity_calibration_receipt(
                path,
                verify_evidence=False,
            )

        self.assertEqual(loaded["frozenCapacity"], _frozen_capacity())
        self.assertEqual(loaded["calibrationId"], "m100-wave-soak-001")

    def test_out_of_scope_reuse_fails_closed(self) -> None:
        """DEC-006：超出主机类别或 Provider 档位的 execution 不得复用其数值。"""
        for override in (
            {"host_class": "ci-linux-x86"},
            {"provider_tier": "cursor-grok-premium"},
        ):
            with self.subTest(**override):
                with self.assertRaises(CapacityCalibrationError) as caught:
                    self._binding(**override)

                self.assertIn("does not apply", str(caught.exception))

    def test_binding_values_equal_the_receipt_field_by_field(self) -> None:
        """DEC-006 可观察面：冻结后的执行策略数值与 receipt 内容逐字段相等。"""
        binding = self._binding()

        self.assertEqual(binding["frozenCapacity"], self.receipt["frozenCapacity"])
        self.assertEqual(binding["applicability"], self.receipt["applicability"])
        self.assertEqual(binding["calibrationId"], self.receipt["calibrationId"])
        self.assertEqual(
            binding["calibrationReceiptDigest"],
            self.receipt["receiptDigest"],
        )

    def test_wave_count_only_grows_with_job_count(self) -> None:
        """规模只改变 wave 数：并行上限不随 job 数或 quota 变化。"""
        self.assertEqual(
            calibration_wave_count(
                work_unit_count=8,
                fleet_max_concurrent_workers=8,
            ),
            1,
        )
        self.assertEqual(
            calibration_wave_count(
                work_unit_count=9,
                fleet_max_concurrent_workers=8,
            ),
            2,
        )
        self.assertEqual(self._binding(work_unit_count=100)["waveCount"], 13)
        self.assertEqual(self._binding(work_unit_count=1000)["waveCount"], 125)

    def test_absolute_deadline_is_derived_from_calibration_only(self) -> None:
        """DEC-003：截止 = 冻结时刻 + wave 数 × 单对象上限 + 完成宽限。"""
        binding = self._binding(work_unit_count=100)

        self.assertEqual(
            binding["fleetBatchDeadlineEpochSeconds"],
            _FROZEN_AT + 13 * 900 + 300,
        )

    def test_remaining_time_clamps_at_zero(self) -> None:
        """DEC-003：剩余时间由单点投影给出，过期后为 0 而不是负值。"""
        binding = self._binding()
        deadline = binding["fleetBatchDeadlineEpochSeconds"]

        self.assertEqual(
            remaining_batch_seconds(binding, now_epoch_seconds=deadline - 60),
            60,
        )
        self.assertEqual(
            remaining_batch_seconds(binding, now_epoch_seconds=deadline + 3_600),
            0,
        )

    def test_lease_deadline_takes_the_smaller_of_two_windows(self) -> None:
        """DEC-003：lease 截止取单对象窗口与绝对截止的更小者。"""
        binding = self._binding()
        deadline = binding["fleetBatchDeadlineEpochSeconds"]

        early = deadline - 10_000
        self.assertEqual(
            lease_deadline_epoch_seconds(binding, now_epoch_seconds=early),
            early + 900,
        )

        late = deadline - 100
        self.assertEqual(
            lease_deadline_epoch_seconds(binding, now_epoch_seconds=late),
            deadline,
        )

    def test_receipt_ref_must_stay_inside_the_evidence_tree(self) -> None:
        for ref in ("/etc/passwd", "../../escape.json", ""):
            with self.subTest(ref=ref):
                with self.assertRaises(CapacityCalibrationError):
                    self._binding(receipt_ref=ref)

    def test_freeze_instant_must_be_a_positive_epoch_second(self) -> None:
        for instant in (0, -1):
            with self.subTest(instant=instant):
                with self.assertRaises(CapacityCalibrationError):
                    self._binding(frozen_at_epoch_seconds=instant)


if __name__ == "__main__":
    unittest.main()
