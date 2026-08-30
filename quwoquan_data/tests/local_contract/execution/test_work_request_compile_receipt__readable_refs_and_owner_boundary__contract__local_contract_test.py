# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t8
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t10
"""GWT-001：编译结果自解释，编译器 owner 边界之外零写入，修复输入回到 preview。"""
from __future__ import annotations

from pathlib import Path

import pytest
import content.execution.campaign.request_envelope as _request_envelope_owner  # noqa: F401
from content.execution.campaign import request_envelope_build
from content.execution.controller.execute import (
    pre_acquisition_handoff as handoff_api,
)
from content.execution.planning import (
    work_request_contract,
    work_request_dependencies,
)
from content.execution.planning.work_request import (
    WorkRequestCommandWriter,
    WorkRequestCompilationQuery,
)
from content.execution.planning.work_request_contract import WorkRequestPreviewQuery
from core.io import read_json
from support.campaign_request_envelope_fixture import _patch_envelope_deps

DIGEST = "sha256:" + "a" * 64
RECEIPT_REF_FIELDS = (
    "workRequestRef",
    "carrierPolicyRef",
    "sourcePoolPlanRef",
)
RECEIPT_DIGEST_FIELDS = (
    "workRequestDigest",
    "requestDigest",
    "carrierPolicyDigest",
    "entityCatalogDigest",
    "dependencySetDigest",
    "sourcePoolPlanDigest",
    "sourceDigest",
)
# 编译器 owner 之外的 artifact 家族：出现任一即证明编译面越权写入。
FORBIDDEN_ARTIFACT_MARKERS = (
    "execution-spec",
    "campaign-plan",
    "campaign-report",
    "reconciliation",
    "scale-source-pool",
    "submission",
)


def _install_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    document = {
        "vertical": "travel",
        "regionRef": "china",
        "lifecycle": "research",
        "scopeType": "region",
        "scope": "china",
        "primaryTopicRef": None,
        "relatedTopicRefs": [],
        "scale": "M1",
        "workloadTargets": {"homepage": 1},
        "sourceSelection": {
            "homepage": {"mode": "site_primary", "providers": ["wikipedia"]}
        },
    }
    monkeypatch.setattr(
        handoff_api, "load_pre_acquisition_handoff", lambda _path: dict(document)
    )


def _dependencies(
    intent: object,
    *,
    workload_mode: str,
    workloads: object,
    **_kwargs: object,
) -> dict[str, object]:
    workload_map = dict(workloads)
    dependency_rows = {"sourcePool": {"ref": "pool.json", "digest": DIGEST}}
    return {
        "source": {
            "algorithm": "sha256",
            "digest": DIGEST,
            "inputs": ["quwoquan_data/scripts"],
        },
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "c" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": "sha256:" + "b" * 64,
        "sourcePool": {
            "poolId": "pool-compile-receipt",
            "targetScale": "WORKLOAD",
            "workloadMode": workload_mode,
            "activeCarriers": list(workload_map),
            "workloadTargets": workload_map,
            "sourceRevision": "sha256:" + "0" * 64,
            "sourceDigest": DIGEST,
            "entityCatalogDigest": "sha256:" + "b" * 64,
            "planDigest": "sha256:" + "4" * 64,
        },
        "dependencies": dependency_rows,
        "dependencySetDigest": work_request_dependencies.canonical_digest(dependency_rows),
    }


def _intent(tmp_path: Path) -> dict[str, object]:
    return {
        "mode": "fresh",
        "preAcquisitionHandoffRef": str(tmp_path / "handoff.json"),
        "scaleSourcePoolPlanRef": str(tmp_path / "pool.json"),
        "sourcePoolEvidenceRootRef": str(tmp_path / "evidence"),
    }


def _prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], str]:
    _patch_envelope_deps(monkeypatch)
    _install_handoff(monkeypatch)
    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "canonical_dependency_ref", lambda path: Path(path).as_posix()
    )
    intent = _intent(tmp_path)
    preview = WorkRequestPreviewQuery().preview(intent)
    assert preview["outcome"] == "preview", preview
    return intent, str(preview["requestDigest"])


# t7 编译结果可读出 WorkRequest、policy/catalog、全部 dependency 与 envelope 的 ref/digest。
def test_compile_receipt_reads_out_every_ref_and_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "output"
    confirmed = WorkRequestCommandWriter(output_root=output_root).confirm(
        intent, preview_digest=preview_digest
    )
    assert confirmed["outcome"] == "confirmed", confirmed

    receipt = read_json(output_root / str(confirmed["compileReceiptRef"]))
    work_request = read_json(output_root / str(confirmed["workRequestRef"]))

    for field in RECEIPT_REF_FIELDS:
        assert receipt[field], field
    for field in RECEIPT_DIGEST_FIELDS:
        assert str(receipt[field]).startswith("sha256:"), field

    # 每个 dependency 都自带 ref+digest，dependencySetDigest 覆盖全集。
    assert work_request["dependencies"]
    for name, row in work_request["dependencies"].items():
        assert row["ref"], name
        assert str(row["digest"]).startswith("sha256:"), name
    assert receipt["dependencySetDigest"] == work_request_dependencies.canonical_digest(
        work_request["dependencies"]
    )

    # 每个 envelope 都能从 receipt 定位到落盘字节。
    assert [row["carrier"] for row in receipt["carrierEnvelopes"]] == ["homepage"]
    for row in receipt["carrierEnvelopes"]:
        envelope = read_json(output_root / str(row["envelopeRef"]))
        assert envelope["requestDigest"] == row["requestDigest"]
        assert envelope["executionId"] == row["executionId"]

    # 同一份回执经查询面复读得到同一身份，不依赖调用方记忆。
    queried = WorkRequestCompilationQuery(output_root=output_root).get(
        str(confirmed["workRequestDigest"])
    )
    assert queried["compileReceiptDigest"] == confirmed["compileReceiptDigest"]
    assert queried["carrierEnvelopes"] == confirmed["carrierEnvelopes"]


# t8 ExecutionSpec、Campaign plan/report、reconciliation receipt 与 SourcePool 均非编译器所写。
def test_compiler_writes_nothing_outside_the_compile_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest = _prepare(tmp_path, monkeypatch)
    output_root = tmp_path / "output"
    confirmed = WorkRequestCommandWriter(output_root=output_root).confirm(
        intent, preview_digest=preview_digest
    )
    assert confirmed["outcome"] == "confirmed", confirmed

    # compile lock 是并发互斥载体而非 artifact，不参与 owner 边界判定。
    written = sorted(
        path.relative_to(output_root).as_posix()
        for path in output_root.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    assert {Path(name).name for name in written} == {
        "homepage.json",
        "work-request.json",
        "compile-receipt.json",
    }, written
    for name in written:
        for marker in FORBIDDEN_ARTIFACT_MARKERS:
            assert marker not in name, (marker, name)


# t10 修复输入后回到 preview，缺口不残留在编译面。
def test_fixed_input_returns_to_preview_after_needs_input_and_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent, preview_digest = _prepare(tmp_path, monkeypatch)
    writer = WorkRequestCommandWriter(output_root=tmp_path / "output")

    unknown_mode = {**intent, "mode": "__unknown_mode__"}
    needs_input = WorkRequestPreviewQuery().preview(unknown_mode)
    assert needs_input["outcome"] == "needs_input", needs_input

    # 依赖漂移把同一份意图判为 blocked，且不产生 envelope。
    def drifted(*args: object, **kwargs: object) -> dict[str, object]:
        raise ValueError("injected dependency drift")

    monkeypatch.setattr(request_envelope_build, "bind_scale_source_pool", drifted)
    blocked = writer.confirm(intent, preview_digest=preview_digest)
    assert blocked["outcome"] == "blocked", blocked
    assert not list((tmp_path / "output").rglob("*.json"))

    # 修复输入面后回到 preview，requestDigest 与修复前一致。
    monkeypatch.undo()
    intent, restored_digest = _prepare(tmp_path, monkeypatch)
    reopened = WorkRequestPreviewQuery().preview(intent)
    assert reopened["outcome"] == "preview", reopened
    assert reopened["requestDigest"] == restored_digest
