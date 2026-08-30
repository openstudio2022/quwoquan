"""Build the App content UAT authority projection receipt."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    canonical_json_bytes,
    validate_readiness_case_result,
)


def project_app_content_uat_raw_authority(
    *,
    evidence_root: Path,
    targets: Sequence[str],
    raw_results: Mapping[str, Sequence[Mapping[str, Any]]],
    expected_raw_coverage: Mapping[str, int],
    dry_run: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Re-read exact raw bytes and build a verdict-free parent projection."""

    root = evidence_root.expanduser().resolve(strict=True)
    refs: dict[str, list[dict[str, str]]] = {}
    digests: dict[str, list[dict[str, str]]] = {}
    coverage: dict[str, dict[str, int]] = {}
    gaps: dict[str, list[str]] = {}
    integrity_issues: list[str] = []
    for target in targets:
        expected = int(expected_raw_coverage.get(target) or 0)
        target_refs: list[dict[str, str]] = []
        target_digests: list[dict[str, str]] = []
        target_gaps: list[str] = []
        seen_slots: set[str] = set()
        if expected <= 0:
            target_gaps.append("expected raw coverage is empty")
        if not dry_run:
            for index, item in enumerate(raw_results.get(target) or ()):
                slot_id = str(item.get("slotId") or "")
                ref = str(item.get("ref") or "")
                digest = str(item.get("digest") or "")
                if not slot_id or not ref or not digest:
                    target_gaps.append(f"raw[{index}] identity is incomplete")
                    continue
                if slot_id in seen_slots:
                    target_gaps.append(f"raw[{index}] duplicates slot {slot_id}")
                    continue
                seen_slots.add(slot_id)
                raw_candidate = root / ref
                try:
                    candidate = raw_candidate.resolve(strict=True)
                    candidate.relative_to(root)
                    before = raw_candidate.lstat()
                    if raw_candidate.is_symlink() or not stat.S_ISREG(before.st_mode):
                        raise ValueError("raw authority path is unsafe")
                    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(
                        os, "O_CLOEXEC", 0
                    )
                    descriptor = os.open(raw_candidate, flags)
                    try:
                        opened = os.fstat(descriptor)
                        chunks: list[bytes] = []
                        while True:
                            chunk = os.read(descriptor, 1024 * 1024)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        after = os.fstat(descriptor)
                    finally:
                        os.close(descriptor)
                    identity = (
                        before.st_dev,
                        before.st_ino,
                        before.st_size,
                        before.st_mtime_ns,
                    )
                    if (
                        identity
                        != (
                            opened.st_dev,
                            opened.st_ino,
                            opened.st_size,
                            opened.st_mtime_ns,
                        )
                        or identity
                        != (
                            after.st_dev,
                            after.st_ino,
                            after.st_size,
                            after.st_mtime_ns,
                        )
                    ):
                        raise ValueError("raw authority bytes changed during read")
                    encoded = b"".join(chunks)
                    payload = json.loads(encoded)
                except (OSError, ValueError, json.JSONDecodeError):
                    target_gaps.append(f"{slot_id} raw authority bytes are unavailable")
                    continue
                observed = "sha256:" + hashlib.sha256(encoded).hexdigest()
                if observed != digest:
                    target_gaps.append(f"{slot_id} raw authority digest drifted")
                    continue
                if not isinstance(payload, Mapping):
                    target_gaps.append(f"{slot_id} raw authority payload is invalid")
                    continue
                try:
                    canonical_payload = validate_readiness_case_result(
                        payload,
                        generated_at=str(payload.get("completedAt") or ""),
                    )
                except ReadinessCaseResultError:
                    target_gaps.append(
                        f"{slot_id} raw authority is not a canonical ReadinessCaseResult"
                    )
                    continue
                if encoded != canonical_json_bytes(canonical_payload):
                    target_gaps.append(
                        f"{slot_id} raw authority bytes are not canonical"
                    )
                    continue
                target_refs.append({"slotId": slot_id, "ref": ref})
                target_digests.append({"slotId": slot_id, "digest": digest})
                # The raw document owns the outcome. The parent observes only
                # whether that authority is green enough for this integrity gate;
                # it never copies the outcome enum into its own payload.
                if payload.get("status") != "passed":
                    target_gaps.append(
                        f"{slot_id} raw authority is not green; inspect its exact ref"
                    )
        present = len(target_refs)
        missing = max(0, expected - present)
        if not dry_run and missing:
            target_gaps.append(f"required raw coverage is missing {missing} slot(s)")
        if not dry_run and present > expected:
            target_gaps.append(
                f"raw coverage contains {present - expected} unexpected slot(s)"
            )
        refs[target] = target_refs
        digests[target] = target_digests
        coverage[target] = {
            "expected": expected,
            "present": 0 if dry_run else present,
            "missing": expected if dry_run else missing,
        }
        gaps[target] = [] if dry_run and expected > 0 else target_gaps
        integrity_issues.extend(f"{target}: {gap}" for gap in gaps[target])
    return (
        {
            "rawResultRefs": refs,
            "rawResultDigests": digests,
            "rawCoverage": coverage,
            "rawGaps": gaps,
        },
        integrity_issues,
    )


def build_app_content_uat_receipt(
    *,
    status: str,
    targets: list[str],
    platform: str,
    device_id: str,
    uat_profile: Mapping[str, Any],
    runtime_bindings: list[dict[str, Any]],
    launch_bindings: dict[str, dict[str, Any]],
    target_uat_binding_refs: Mapping[str, Mapping[str, str]],
    raw_authority_projection: Mapping[str, Any],
    preflights: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    experience_screenshot_digests: Mapping[str, Mapping[str, str]],
    issues: list[str],
    dry_run: bool,
    canonical_checksum: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    if status not in {"planned", "gate_block", "complete"}:
        raise ValueError("App content UAT projection status is invalid")
    first = preflights[0] if preflights else {}
    first_plan = (
        first.get("appUatPlan")
        if isinstance(first.get("appUatPlan"), Mapping)
        else {}
    )
    required_projection_fields = {
        "rawResultRefs",
        "rawResultDigests",
        "rawCoverage",
        "rawGaps",
    }
    if set(raw_authority_projection) != required_projection_fields:
        raise ValueError("App content UAT raw authority projection is invalid")
    if status == "complete" and issues:
        raise ValueError("complete UAT projection cannot contain integrity gaps")
    projection_details = (
        ["dry-run planned expected raw authority coverage; no raw result was written"]
        if dry_run and not issues
        else ["raw authority projection complete"]
        if status == "complete"
        else list(issues)
    )
    return {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": status,
        "targets": targets,
        "platform": platform,
        "deviceId": device_id,
        "launchPolicy": "immutable_candidate",
        "uatProfile": str(uat_profile.get("profile") or ""),
        "deviceClass": str(uat_profile.get("deviceClass") or ""),
        "deviceRegistered": uat_profile.get("deviceRegistered"),
        "nonPromotable": uat_profile.get("nonPromotable"),
        "packageBaselines": {
            str(item.get("target") or ""): str(item.get("candidateDigest") or "")
            for item in runtime_bindings
            if str(item.get("target") or "")
        },
        "releaseTrainId": (
            str(runtime_bindings[0].get("releaseTrainId") or "")
            if runtime_bindings
            and len(
                {str(item.get("releaseTrainId") or "") for item in runtime_bindings}
            )
            == 1
            else ""
        ),
        "runtimeBindings": {
            str(item["target"]): item for item in runtime_bindings
        },
        "runtimeBindingDigests": {
            str(item["target"]): "sha256:"
            + hashlib.sha256(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for item in runtime_bindings
        },
        "launchBindings": launch_bindings,
        "contractGraphDigests": {
            target: binding.get("contractGraphDigest", "")
            for target, binding in launch_bindings.items()
        },
        "firstBlocker": "",
        "launchBindingDigests": {
            target: canonical_checksum(binding)
            for target, binding in launch_bindings.items()
        },
        "targetUatBindingRefs": {
            target: dict(source)
            for target, source in target_uat_binding_refs.items()
        },
        **{field: raw_authority_projection[field] for field in required_projection_fields},
        "releaseId": str(first.get("releaseId") or ""),
        "manifestDigest": str(first.get("manifestDigest") or ""),
        "releaseUatSamplePlanRef": str(
            first.get("releaseUatSamplePlanRef") or ""
        ),
        "releaseUatSamplePlanDigest": str(
            first.get("releaseUatSamplePlanDigest") or ""
        ),
        "releaseIdentity": dict(first_plan.get("releaseIdentity") or {}),
        "sampleCasePlan": (
            {
                "orderedSamples": list(first_plan.get("orderedSamples") or []),
                "requiredCasePlan": list(
                    first_plan.get("requiredCasePlan") or []
                ),
            }
            if first_plan
            else {}
        ),
        "appUatPlan": dict(first_plan),
        "appUatPlanDigest": (
            canonical_checksum(dict(first_plan)) if first_plan else ""
        ),
        "configurationDigests": sorted(
            {
                str(item.get("configurationDigest") or "")
                for item in preflights
                if str(item.get("configurationDigest") or "")
            }
        ),
        "readinessReceiptDigests": sorted(
            {
                str(item.get("readinessReceiptDigest") or "")
                for item in preflights
                if str(item.get("readinessReceiptDigest") or "")
            }
        ),
        "consumerLeaseIds": sorted(
            {
                str(item.get("consumerLeaseId") or "")
                for item in runs
                if str(item.get("consumerLeaseId") or "")
            }
        ),
        "screenshotDigests": sorted(
            {
                str((item.get("evidence") or {}).get("screenshotDigest") or "")
                for item in runs
                if isinstance(item.get("evidence"), dict)
                and str((item.get("evidence") or {}).get("screenshotDigest") or "")
            }
        ),
        "experienceScreenshotDigests": {
            target: dict(digests)
            for target, digests in experience_screenshot_digests.items()
        },
        "visibleCardCounts": {
            str(item.get("target") or ""): int(
                ((item.get("evidence") or {}).get("feedContent") or {}).get(
                    "visibleCardCount", 0
                )
            )
            for item in runs
            if item.get("suite") == "homepage-feed"
            and isinstance(item.get("evidence"), dict)
        },
        "controlledEdgeRecoveries": {
            str(item.get("target") or ""): {
                "evidence": (item.get("evidence") or {}).get(
                    "controlledEdgeFault"
                )
                or {},
                "receipt": (item.get("evidence") or {}).get(
                    "controlledEdgeFaultReceipt"
                )
                or {},
            }
            for item in runs
            if item.get("suite") == "controlled-edge-recovery"
            and isinstance(item.get("evidence"), dict)
        },
        "preflights": preflights,
        "runs": runs,
        "executed": 0 if dry_run else len(runs),
        "details": projection_details,
    }


__all__ = [
    "build_app_content_uat_receipt",
    "project_app_content_uat_raw_authority",
]
