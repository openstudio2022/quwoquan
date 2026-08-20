# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-015.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-015.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-015.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-015.t2
from __future__ import annotations

from pathlib import Path

import pytest
import content.execution.campaign.request_envelope as _request_envelope_owner  # noqa: F401
from content.execution.campaign import request_envelope_build, request_envelope_writer
from content.execution.planning import work_request_contract
from content.execution.planning.work_request import (
    WorkRequestCommandWriter,
    WorkRequestCompilationQuery,
)
from content.execution.planning.work_request_contract import WorkRequestPreviewQuery
from core.io import read_json, write_json
from support.campaign_request_envelope_fixture import _patch_envelope_deps

DIGEST = "sha256:" + "a" * 64


def _test_ref(path: Path) -> str:
    text = path.as_posix()
    marker = "data/local/tests/capacity/local-contract-capacity.json"
    return marker if text.endswith(marker) else text


def _intent(
    tmp_path: Path,
    *,
    workloads: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "regionRef": "china",
        "lifecycle": "research",
        "mode": "fresh",
        "workloads": workloads or {"homepage": 1},
        "capacityCalibrationReceiptRef": (
            "data/local/tests/capacity/local-contract-capacity.json"
        ),
        "preAcquisitionHandoffRef": str(tmp_path / "handoff.json"),
        "scaleSourcePoolPlanRef": str(tmp_path / "pool.json"),
        "sourcePoolEvidenceRootRef": str(tmp_path / "evidence"),
    }


def _dependencies(
    intent: object,
    *,
    scale: str,
    workload_mode: str,
    workloads: object,
    **_kwargs: object,
) -> dict[str, object]:
    workload_map = dict(workloads)
    dependency_rows = {
        "sourcePool": {"ref": "pool.json", "digest": DIGEST}
    }
    if isinstance(intent, dict) and intent.get(
        "predecessorReconciliationReceiptRef"
    ):
        dependency_rows["predecessorReconciliationReceiptRef"] = {
            "ref": "reconciliation.json",
            "digest": "sha256:" + "8" * 64,
        }
    return {
        "source": {
            "algorithm": "sha256",
            "digest": "sha256:" + "a" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "c" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": "sha256:" + "b" * 64,
        "sourcePool": {
            "poolId": "pool-work-request",
            "targetScale": "WORKLOAD",
            "workloadMode": workload_mode,
            "activeCarriers": list(workload_map),
            "workloadTargets": workload_map,
            "sourceRevision": "sha256:" + "0" * 64,
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "b" * 64,
            "planDigest": "sha256:" + "4" * 64,
        },
        "dependencies": dependency_rows,
        "dependencySetDigest": work_request_contract._digest(dependency_rows),
    }


def _prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], str, list[int]]:
    _patch_envelope_deps(monkeypatch)
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "_canonical_ref", _test_ref
    )
    selected_counts: list[int] = []
    original_bind = request_envelope_build.bind_scale_source_pool

    def bind(*args: object, **kwargs: object):
        selected_counts.append(int(kwargs["count"]))
        return original_bind(*args, **kwargs)

    monkeypatch.setattr(request_envelope_build, "bind_scale_source_pool", bind)
    intent = _intent(tmp_path)
    preview = WorkRequestPreviewQuery().preview(intent)
    assert preview["outcome"] == "preview"
    return intent, str(preview["requestDigest"]), selected_counts


def test_confirm_publishes_one_atomic_package_and_replays_same_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest, selected_counts = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "output"
    writer = WorkRequestCommandWriter(output_root=output_root)

    first = writer.confirm(intent, preview_digest=preview_digest)
    replay = writer.confirm(intent, preview_digest=preview_digest)
    assert first["outcome"] == "confirmed", first
    queried = WorkRequestCompilationQuery(output_root=output_root).get(
        str(first["workRequestDigest"])
    )

    assert first["replayed"] is False
    assert replay["outcome"] == "confirmed" and replay["replayed"] is True
    assert queried["compileReceiptDigest"] == first["compileReceiptDigest"]
    assert selected_counts == [1]
    work_request_path = output_root / first["workRequestRef"]
    batch_root = work_request_path.parent
    assert {path.name for path in batch_root.iterdir()} == {
        "homepage.json",
        "work-request.json",
        "compile-receipt.json",
    }
    work_request = read_json(work_request_path)
    compile_receipt = read_json(batch_root / "compile-receipt.json")
    assert work_request["workloads"] == {"homepage": 1}
    assert work_request["sourcePool"]["targetScale"] == "WORKLOAD"
    assert work_request["dependencies"] == {
        "sourcePool": {"ref": "pool.json", "digest": DIGEST}
    }
    assert work_request["workRequestDigest"] != work_request["requestDigest"]
    assert compile_receipt["correlationId"] == work_request["workRequestDigest"]
    assert compile_receipt["workRequestDigest"] == work_request["workRequestDigest"]
    assert "intentText" not in work_request["intent"]


def test_staging_write_failure_leaves_zero_visible_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest, _counts = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "failed-output"
    original_write = request_envelope_writer.write_json
    calls = 0

    def fail_second(path: Path, document: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        original_write(path, document)

    monkeypatch.setattr(request_envelope_writer, "write_json", fail_second)
    result = WorkRequestCommandWriter(output_root=output_root).confirm(
        intent,
        preview_digest=preview_digest,
    )

    assert result["outcome"] == "blocked"
    assert result["error"]["code"] == "DATA.WORK_REQUEST.COMPILE_BLOCKED"
    root = output_root / "workspace/content-campaign-envelopes"
    assert not tuple(root.rglob("sequence-*"))
    assert not tuple(root.rglob(".*.tmp"))


def test_four_carrier_build_failure_leaves_zero_visible_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_envelope_deps(monkeypatch)
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
    monkeypatch.setattr(work_request_contract, "_canonical_ref", _test_ref)
    original_build = request_envelope_writer.build_envelope

    def fail_image(*args: object, **kwargs: object):
        if kwargs["carrier"] == "image":
            raise RuntimeError("injected image carrier build failure")
        return original_build(*args, **kwargs)

    monkeypatch.setattr(request_envelope_writer, "build_envelope", fail_image)
    intent = _intent(
        tmp_path,
        workloads={"homepage": 1, "article": 2, "image": 3, "video": 4},
    )
    preview = WorkRequestPreviewQuery().preview(intent)
    output_root = tmp_path / "four-carrier-failed-output"

    result = WorkRequestCommandWriter(output_root=output_root).confirm(
        intent,
        preview_digest=str(preview["requestDigest"]),
    )

    assert result["outcome"] == "blocked"
    assert result["error"]["code"] == "DATA.WORK_REQUEST.COMPILE_BLOCKED"
    root = output_root / "workspace/content-campaign-envelopes"
    assert not tuple(root.rglob("sequence-*"))
    assert not tuple(root.rglob(".*.tmp"))


def test_confirm_rechecks_preview_dependency_digest_before_allocating_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_envelope_deps(monkeypatch)
    generation = {"digest": "sha256:" + "1" * 64}

    def dependencies(*args: object, **kwargs: object) -> dict[str, object]:
        document = _dependencies(*args, **kwargs)
        rows = document["dependencies"]
        assert isinstance(rows, dict)
        rows["sourcePool"]["digest"] = generation["digest"]
        document["dependencySetDigest"] = work_request_contract._digest(rows)
        return document

    monkeypatch.setattr(work_request_contract, "_dependency_bindings", dependencies)
    monkeypatch.setattr(work_request_contract, "_canonical_ref", _test_ref)
    intent = _intent(tmp_path)
    preview = WorkRequestPreviewQuery().preview(intent)
    assert preview["outcome"] == "preview"
    generation["digest"] = "sha256:" + "2" * 64

    result = WorkRequestCommandWriter(output_root=tmp_path / "drift").confirm(
        intent,
        preview_digest=str(preview["requestDigest"]),
    )

    assert result["outcome"] == "blocked"
    assert result["error"]["code"] == "DATA.WORK_REQUEST.PREVIEW_DRIFT"
    root = tmp_path / "drift/workspace/content-campaign-envelopes"
    assert not tuple(root.rglob("sequence-*"))


def test_retry_work_request_confirms_exact_predecessor_and_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest, _counts = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "retry-output"
    writer = WorkRequestCommandWriter(output_root=output_root)
    first = writer.confirm(intent, preview_digest=preview_digest)
    assert first["outcome"] == "confirmed", first
    predecessor = str(first["carrierEnvelopes"][0]["executionId"])
    predecessor_root = read_json(
        output_root / first["carrierEnvelopes"][0]["envelopeRef"]
    )["rootExecutionId"]

    def reconciliation(
        _receipt_path: Path,
        *,
        retry_predecessors: dict[str, str],
        target_names: object,
        **_kwargs: object,
    ):
        return (
            dict(retry_predecessors),
            tuple(target_names),
            {
                "predecessorRootExecutionId": predecessor_root,
                "receiptRef": "data/local/reconciliation.json",
                "receiptDigest": "sha256:" + "8" * 64,
            },
            {"reason": "retry"},
        )

    monkeypatch.setattr(
        request_envelope_writer, "_reconciliation_inputs", reconciliation
    )
    retry_intent = _intent(tmp_path)
    retry_intent.update(
        {
            "mode": "retry",
            "predecessorExecutionIdsByCarrier": {"homepage": predecessor},
            "predecessorReconciliationReceiptRef": str(
                tmp_path / "reconciliation.json"
            ),
        }
    )
    retry_preview = WorkRequestPreviewQuery().preview(retry_intent)
    assert retry_preview["outcome"] == "preview", retry_preview

    retry = writer.confirm(
        retry_intent,
        preview_digest=str(retry_preview["requestDigest"]),
    )

    assert retry["outcome"] == "confirmed", retry
    retry_request = read_json(output_root / retry["workRequestRef"])
    retry_envelope = read_json(
        output_root / retry["carrierEnvelopes"][0]["envelopeRef"]
    )
    assert retry_request["executionMode"] == "retry"
    assert retry_envelope["retryOf"] == predecessor
    assert retry_envelope["predecessorReconciliation"]["receiptDigest"] == (
        "sha256:" + "8" * 64
    )


def test_replay_rejects_existing_compile_package_digest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest, _counts = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "drift-output"
    writer = WorkRequestCommandWriter(output_root=output_root)
    first = writer.confirm(intent, preview_digest=preview_digest)
    assert first["outcome"] == "confirmed", first
    receipt_path = output_root / first["compileReceiptRef"]
    receipt = read_json(receipt_path)
    receipt["durationMs"] += 1
    write_json(receipt_path, receipt)

    replay = writer.confirm(intent, preview_digest=preview_digest)
    queried = WorkRequestCompilationQuery(output_root=output_root).get(
        str(first["workRequestDigest"])
    )

    assert replay["outcome"] == "blocked"
    assert replay["error"]["code"] == "DATA.WORK_REQUEST.COMPILE_BLOCKED"
    assert queried["outcome"] == "blocked"
    assert queried["error"]["code"] == (
        "DATA.WORK_REQUEST.COMPILATION_QUERY_BLOCKED"
    )
    root = output_root / "workspace/content-campaign-envelopes"
    assert len(tuple(root.rglob("sequence-*"))) == 1


def test_replay_does_not_bypass_tampered_request_digest_with_new_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest, _counts = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "request-drift-output"
    writer = WorkRequestCommandWriter(output_root=output_root)
    first = writer.confirm(intent, preview_digest=preview_digest)
    assert first["outcome"] == "confirmed", first
    work_request_path = output_root / first["workRequestRef"]
    work_request = read_json(work_request_path)
    work_request["requestDigest"] = "sha256:" + "9" * 64
    write_json(work_request_path, work_request)

    replay = writer.confirm(intent, preview_digest=preview_digest)

    assert replay["outcome"] == "blocked"
    assert replay["error"]["code"] == "DATA.WORK_REQUEST.COMPILE_BLOCKED"
    root = output_root / "workspace/content-campaign-envelopes"
    assert len(tuple(root.rglob("sequence-*"))) == 1


def test_replay_rejects_envelope_bytes_changed_under_same_request_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest, _counts = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "envelope-drift-output"
    writer = WorkRequestCommandWriter(output_root=output_root)
    first = writer.confirm(intent, preview_digest=preview_digest)
    assert first["outcome"] == "confirmed", first
    envelope_path = output_root / first["carrierEnvelopes"][0]["envelopeRef"]
    envelope = read_json(envelope_path)
    frozen_digest = envelope["requestDigest"]
    envelope["frozenAt"] = "2099-01-01T00:00:00+00:00"
    write_json(envelope_path, envelope)

    replay = writer.confirm(intent, preview_digest=preview_digest)

    assert envelope["requestDigest"] == frozen_digest
    assert replay["outcome"] == "blocked"
    assert replay["error"]["code"] == "DATA.WORK_REQUEST.COMPILE_BLOCKED"
    root = output_root / "workspace/content-campaign-envelopes"
    assert len(tuple(root.rglob("sequence-*"))) == 1


def test_direct_batch_writer_recomputes_existing_envelope_digest_on_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_envelope_deps(monkeypatch)
    output_root = tmp_path / "direct-writer-output"
    arguments = {
        "scale": "M1",
        "region_ref": "china",
        "carriers": ("homepage",),
        "workloads": {"homepage": 1},
        "output_root": output_root,
        "day": "20260820",
        "sequence": 1,
        "capacity_calibration_receipt": Path(
            "data/local/tests/capacity/local-contract-capacity.json"
        ),
        "pre_acquisition_handoff": tmp_path / "handoff.json",
        "scale_source_pool": tmp_path / "pool.json",
        "source_pool_evidence_root": tmp_path / "evidence",
    }
    first = request_envelope_writer.write_scale_envelopes(**arguments)
    replay = request_envelope_writer.write_scale_envelopes(**arguments)
    assert replay == first
    envelope = read_json(first["homepage"])
    frozen_digest = envelope["requestDigest"]
    envelope["frozenAt"] = "2099-01-01T00:00:00+00:00"
    write_json(first["homepage"], envelope)

    with pytest.raises(ValueError, match="different digest"):
        request_envelope_writer.write_scale_envelopes(**arguments)

    assert read_json(first["homepage"])["requestDigest"] == frozen_digest


def test_four_carrier_confirm_preserves_each_heterogeneous_exact_quantity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_envelope_deps(monkeypatch)
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "_canonical_ref", _test_ref
    )
    intent = _intent(
        tmp_path,
        workloads={
            "homepage": 1,
            "article": 2,
            "image": 3,
            "video": 4,
        },
    )
    preview = WorkRequestPreviewQuery().preview(intent)
    result = WorkRequestCommandWriter(output_root=tmp_path / "four-output").confirm(
        intent,
        preview_digest=str(preview["requestDigest"]),
    )

    assert result["outcome"] == "confirmed", result
    assert [row["carrier"] for row in result["carrierEnvelopes"]] == [
        "homepage",
        "article",
        "image",
        "video",
    ]
    batch_root = (tmp_path / "four-output" / result["workRequestRef"]).parent
    assert len(tuple(batch_root.glob("*.json"))) == 6
    work_request = read_json(batch_root / "work-request.json")
    assert work_request["workloads"] == {
        "homepage": 1,
        "article": 2,
        "image": 3,
        "video": 4,
    }
    for carrier, quantity in work_request["workloads"].items():
        envelope = read_json(batch_root / f"{carrier}.json")
        assert envelope["quota"] == quantity
        assert envelope["sourcePoolSelection"]["candidateCount"] == quantity
