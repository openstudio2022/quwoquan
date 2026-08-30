"""App content Patrol/page producer emits canonical per-slot raw results.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands.app_preflight_uat_page_evidence import (
    collect_app_uat_case_execution_reports,
    emit_app_uat_raw_results,
)
from quwoquan_ops.cli.commands.app_preflight_uat_raw_results import (
    AppUatRawResultError,
    CASE_EXECUTION_SCHEMA,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    target_uat_binding_digest,
    target_uat_binding_id,
)

SPEC_REF = (
    "specs/feature-tree/runtime/runtime-config/"
    "environment-topology-and-packaging/spec.md#gwt-004"
)
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
CARRIERS = ("homepage", "article", "image", "video")


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _write(root: Path, ref: str, value: object) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_bytes(value)
    path.write_bytes(encoded)
    return {"receiptRef": ref, "receiptSha256": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def _plan() -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-a",
        "releaseDigest": _digest("1"),
        "milestone": None,
        "selectionEvidence": {
            "poolDigest": _digest("2"),
            "sourceIdentitySetDigest": _digest("3"),
            "canonicalMerkle": _digest("4"),
        },
        "eligiblePopulationCounts": {carrier: 1 for carrier in CARRIERS},
        "exactCohortCounts": {carrier: 1 for carrier in CARRIERS},
        "entryCarrierCells": [
            {
                "entry": entry,
                "carrier": carrier,
                "applicability": "required",
                "specRef": SPEC_REF,
                "runnerClass": f"qwq_app.content_uat.{entry}.{carrier}.v1",
            }
            for entry in ENTRIES
            for carrier in CARRIERS
        ],
        "sampleStrategy": {
            "name": "baseline_per_required_carrier",
            "version": 1,
            "seedDigest": _digest("5"),
            "carrierOrder": list(CARRIERS),
            "sortKey": "identity",
            "direction": "ascending",
            "objectDigestAlgorithm": "sha256-path-blob-merkle",
            "sampleDistribution": {carrier: 1 for carrier in CARRIERS},
        },
        "sampleCount": 4,
        "samples": [
            {
                "sampleId": f"baseline-{carrier}-001",
                "carrier": carrier,
                "objectId": (
                    "/entity/homepage-object-001"
                    if carrier == "homepage"
                    else f"{carrier}-object-001"
                ),
                "objectRef": (
                    "objects/entities/homepage-object-001"
                    if carrier == "homepage"
                    else f"objects/posts/{carrier}/{carrier}-object-001"
                ),
                "objectDigest": _digest("e"),
            }
            for carrier in CARRIERS
        ],
    }


def _binding(plan: dict[str, object]) -> dict[str, object]:
    provider = {
        "identity": "first-party-https",
        "class": "first_party",
        "type": "https",
        "registered": False,
        "conformanceEvidence": {
            "ref": "env/alpha/provider/conformance.json",
            "digest": _digest("f"),
        },
    }
    runner = {
        "identity": "app-content-uat",
        "sourcePath": "quwoquan_ops/cli/commands/app_preflight_uat_page_evidence.py",
        "digest": _digest("6"),
        "registered": False,
    }
    return {
        "schema": "quwoquan_ops.target_uat_binding.v1",
        "bindingId": target_uat_binding_id(
            target="alpha-local",
            release_id="release-a",
            release_digest=_digest("1"),
            platform="android",
            provider=provider,
            device_identity="emulator-5554",
            profile="rehearsal",
            runner=runner,
        ),
        "releaseId": "release-a",
        "releaseDigest": _digest("1"),
        "releaseUatSamplePlanRef": "data/releases/release-a/uat/sample-plan.json",
        "releaseUatSamplePlanDigest": "sha256:" + hashlib.sha256(_canonical_bytes(plan)).hexdigest(),
        "environment": "alpha",
        "target": "alpha-local",
        "candidateDigest": _digest("7"),
        "packageDigest": _digest("8"),
        "configurationDigest": _digest("9"),
        "runtimeConfigDigest": _digest("a"),
        "environmentRuntimeDigest": _digest("b"),
        "activeCas": {"ref": "env/alpha/active-cas.json", "digest": _digest("c")},
        "readback": {"ref": "env/alpha/readback.json", "digest": _digest("d")},
        "artifact": {
            "class": "production_behavior",
            "digest": _digest("e"),
            "applicationId": "com.leadwise.quwoquan.debug",
            "buildMode": "debug",
            "buildProfile": "nonprod",
        },
        "platform": "android",
        "provider": provider,
        "device": {"identity": "emulator-5554", "class": "emulator", "registered": False},
        "runner": runner,
        "profile": "rehearsal",
        "nonPromotable": True,
        "createdAt": "2026-08-29T07:00:00Z",
    }


def _execution(
    root: Path,
    *,
    binding: dict[str, object],
    sample: dict[str, str],
    entry: str,
    status: str = "passed",
    suffix: str = "",
) -> dict[str, str]:
    carrier = sample["carrier"]
    page_ref = f"page/{sample['sampleId']}-{entry}{suffix}.json"
    page_path = root / page_ref
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_bytes = _canonical_bytes(
        {"sampleId": sample["sampleId"], "entrySurface": entry, "status": "observed"}
    )
    page_path.write_bytes(page_bytes)
    binding_digest = target_uat_binding_digest(binding)
    report: dict[str, object] = {
        "schema": CASE_EXECUTION_SCHEMA,
        "sampleId": sample["sampleId"],
        "entrySurface": entry,
        "carrier": carrier,
        "objectId": sample["objectId"],
        "caseId": f"app_uat_{sample['sampleId'].replace('-', '_')}_{entry}{suffix.replace('-', '_')}",
        "specRef": SPEC_REF,
        "runnerIdentity": f"qwq_app.content_uat.{entry}.{carrier}.v1",
        "releaseId": "release-a",
        "releaseDigest": _digest("1"),
        "sourceIdentitySetDigest": _digest("3"),
        "targetUatBindingDigest": binding_digest,
        "status": status,
        "target": {"kind": "object" if carrier == "homepage" else "page", "id": sample["objectId"]},
        "commitSha": "a" * 40,
        "contractGraphSourceHash": "b" * 64,
        "candidateManifestSha256": "c" * 64,
        "provider": "first-party-https",
        "startedAt": "2026-08-29T07:00:00Z",
        "completedAt": "2026-08-29T07:01:00Z",
        "patrolExitCode": 0,
        "pageEvidence": {
            "status": "present",
            "ref": page_ref,
            "sha256": "sha256:" + hashlib.sha256(page_bytes).hexdigest(),
        },
    }
    if status == "failed":
        report.update({"patrolExitCode": 1, "reasonCode": "APP.UAT.PATROL_FAILED"})
    elif status == "blocked":
        report.update(
            {
                "reasonCode": "APP.UAT.PAGE_EVIDENCE_MISSING",
                "pageEvidence": {"status": "missing"},
            }
        )
    elif status == "skipped":
        report.update(
            {
                "patrolExitCode": None,
                "reasonCode": "APP.UAT.NOT_EXECUTED",
                "pageEvidence": {"status": "missing"},
            }
        )
    ref = f"case/{sample['sampleId']}-{entry}{suffix}.json"
    return _write(root, ref, report)


def _executions(
    root: Path,
    binding: dict[str, object],
    *,
    overrides: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for raw_sample in _plan()["samples"]:  # type: ignore[index]
        sample = dict(raw_sample)  # type: ignore[arg-type]
        for entry in ENTRIES:
            status = (overrides or {}).get((sample["sampleId"], entry), "passed")
            values.append(
                _execution(
                    root,
                    binding=binding,
                    sample=sample,
                    entry=entry,
                    status=status,
                )
            )
    return values


def _load_results(root: Path, refs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [json.loads((root / str(item["ref"])).read_text()) for item in refs]


def test_producer_writes_one_raw_per_required_sample_case_and_preserves_statuses(
    tmp_path: Path,
) -> None:
    plan = _plan()
    binding = _binding(plan)
    sample_ids = [str(item["sampleId"]) for item in plan["samples"]]  # type: ignore[index]
    executions = _executions(
        tmp_path,
        binding,
        overrides={
            (sample_ids[0], "search"): "failed",
            (sample_ids[1], "recommendation"): "blocked",
            (sample_ids[2], "direct_or_object_route"): "skipped",
        },
    )

    refs = emit_app_uat_raw_results(
        evidence_root=tmp_path,
        target_binding=binding,
        sample_plan=plan,
        case_execution_reports=executions,
    )
    results = _load_results(tmp_path, refs)

    assert len(refs) == 16
    assert {result["status"] for result in results} == {
        "passed",
        "failed",
        "blocked",
        "skipped",
    }
    assert all(result["producer"] == "app" for result in results)
    assert all(result["layer"] == "user_acceptance" for result in results)
    assert all(result["releaseId"] == "release-a" for result in results)
    assert all(result["releaseDigest"] == _digest("1") for result in results)
    assert all(result["uatProfile"] == "rehearsal" for result in results)
    assert all(result["deviceClass"] == "emulator" for result in results)
    assert all(result["deviceRegistered"] is False for result in results)
    assert all(result["nonPromotable"] is True for result in results)
    assert all(result["targetUatBindingDigest"] == target_uat_binding_digest(binding) for result in results)
    assert {result["carrier"] for result in results} == set(CARRIERS)
    assert {result["entrySurface"] for result in results} == set(ENTRIES)
    assert all(result["receiptRef"] == ref["receiptRef"] for result, ref in zip(results, refs, strict=True))
    assert all(ref["receiptSha256"] == "sha256:" + result["artifactSha256"] for ref, result in zip(refs, results, strict=True))
    assert not any("results" in result for result in results)


def test_exact_replay_is_idempotent_and_conflicting_replay_fails(tmp_path: Path) -> None:
    plan = _plan()
    binding = _binding(plan)
    executions = _executions(tmp_path, binding)
    first = emit_app_uat_raw_results(
        evidence_root=tmp_path,
        target_binding=binding,
        sample_plan=plan,
        case_execution_reports=executions,
    )
    original = [(tmp_path / str(item["ref"])).read_bytes() for item in first]
    replay = emit_app_uat_raw_results(
        evidence_root=tmp_path,
        target_binding=binding,
        sample_plan=plan,
        case_execution_reports=executions,
    )
    assert all(item["created"] is False for item in replay)
    assert original == [(tmp_path / str(item["ref"])).read_bytes() for item in replay]

    changed = json.loads((tmp_path / executions[0]["receiptRef"]).read_text())
    changed["completedAt"] = "2026-08-29T07:02:00Z"
    executions[0] = _write(tmp_path, executions[0]["receiptRef"], changed)
    with pytest.raises(AppUatRawResultError, match="different bytes"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=plan,
            case_execution_reports=executions,
        )


def test_duplicate_slot_and_receipt_digest_drift_fail_closed(tmp_path: Path) -> None:
    plan = _plan()
    binding = _binding(plan)
    executions = _executions(tmp_path, binding)
    with pytest.raises(AppUatRawResultError, match="duplicate required slot"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=plan,
            case_execution_reports=[*executions, executions[0]],
        )

    drifted = deepcopy(executions)
    drifted[0]["receiptSha256"] = _digest("f")
    with pytest.raises(AppUatRawResultError, match="receipt digest drifted"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=plan,
            case_execution_reports=drifted,
        )


def test_retired_sample_identity_alias_fails_closed(tmp_path: Path) -> None:
    plan = _plan()
    retired = deepcopy(plan)
    sample = retired["samples"][0]  # type: ignore[index]
    sample["identity"] = sample.pop("objectId")  # type: ignore[union-attr]
    binding = _binding(retired)

    with pytest.raises(AppUatRawResultError, match="fields are invalid"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=retired,
            case_execution_reports=[],
        )




def test_duplicate_exact_sample_object_identity_fails_closed(tmp_path: Path) -> None:
    plan = _plan()
    duplicate = deepcopy(plan)
    first = duplicate["samples"][0]  # type: ignore[index]
    second = duplicate["samples"][1]  # type: ignore[index]
    second["objectRef"] = first["objectRef"]  # type: ignore[index]
    binding = _binding(duplicate)

    with pytest.raises(AppUatRawResultError, match="objectId and objectRef must each be unique"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=duplicate,
            case_execution_reports=[],
        )


def test_binding_release_and_case_release_or_source_mismatch_fail_closed(tmp_path: Path) -> None:
    plan = _plan()
    binding = _binding(plan)
    executions = _executions(tmp_path, binding)

    wrong_plan = deepcopy(plan)
    wrong_plan["releaseId"] = "release-b"
    with pytest.raises(AppUatRawResultError, match="sample plan releaseId"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=wrong_plan,
            case_execution_reports=executions,
        )

    for field, replacement in (
        ("releaseDigest", _digest("f")),
        ("sourceIdentitySetDigest", _digest("e")),
        ("targetUatBindingDigest", _digest("d")),
    ):
        changed = json.loads((tmp_path / executions[0]["receiptRef"]).read_text())
        changed[field] = replacement
        changed_source = _write(tmp_path, executions[0]["receiptRef"], changed)
        with pytest.raises(AppUatRawResultError, match="identity drifted"):
            emit_app_uat_raw_results(
                evidence_root=tmp_path,
                target_binding=binding,
                sample_plan=plan,
                case_execution_reports=[changed_source, *executions[1:]],
            )
        executions[0] = _execution(
            tmp_path,
            binding=binding,
            sample=dict(plan["samples"][0]),  # type: ignore[index,arg-type]
            entry="feed",
        )


def test_patrol_failure_or_missing_page_evidence_cannot_be_claimed_passed(
    tmp_path: Path,
) -> None:
    plan = _plan()
    binding = _binding(plan)
    executions = _executions(tmp_path, binding)
    report_path = tmp_path / executions[0]["receiptRef"]
    report = json.loads(report_path.read_text())
    report["patrolExitCode"] = 1
    executions[0] = _write(tmp_path, executions[0]["receiptRef"], report)
    with pytest.raises(AppUatRawResultError, match="cannot be rewritten as passed"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=plan,
            case_execution_reports=executions,
        )

    report["patrolExitCode"] = 0
    report["pageEvidence"] = {"status": "missing"}
    executions[0] = _write(tmp_path, executions[0]["receiptRef"], report)
    with pytest.raises(AppUatRawResultError, match="cannot be rewritten as passed"):
        emit_app_uat_raw_results(
            evidence_root=tmp_path,
            target_binding=binding,
            sample_plan=plan,
            case_execution_reports=executions,
        )


def test_page_boundary_collects_only_explicit_exact_case_receipts(tmp_path: Path) -> None:
    plan = _plan()
    binding = _binding(plan)
    source = _execution(
        tmp_path,
        binding=binding,
        sample=dict(plan["samples"][0]),  # type: ignore[index,arg-type]
        entry="feed",
    )
    report_ref = "patrol/report.json"
    report = {
        "appUatCaseExecutionReports": [source],
        "status": "passed",
    }
    _write(tmp_path, report_ref, report)

    collected = collect_app_uat_case_execution_reports(
        evidence_root=tmp_path,
        report_ref=report_ref,
        expected_target_uat_binding_digest=target_uat_binding_digest(binding),
    )

    assert collected == [source]


def test_page_boundary_required_report_missing_blocks(tmp_path: Path) -> None:
    report_ref = "patrol/report.json"
    _write(tmp_path, report_ref, {"status": "passed", "runs": [{"exitCode": 0}]})

    with pytest.raises(ValueError, match="lacks required .*case_execution"):
        collect_app_uat_case_execution_reports(
            evidence_root=tmp_path,
            report_ref=report_ref,
            expected_target_uat_binding_digest=_digest("1"),
        )
