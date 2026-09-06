"""Emit canonical raw App UAT results from explicit case execution receipts.

The producer consumes one already-created ``TargetUatBinding`` and one exact
Data-owned sample plan.  It never discovers a latest release, target, device,
or receipt.  Each required sample/case slot owns one create-once raw result.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.content_api_consumer_authority import (
    content_consumer_raw_slot_id,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    canonical_json_bytes,
    validate_readiness_case_result,
    write_create_once_json,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    target_uat_binding_digest,
    validate_target_uat_binding,
)

RAW_RESULT_DIRECTORY = "raw-readiness-case-results"
CASE_EXECUTION_SCHEMA = "quwoquan_ops.app_uat_case_execution.v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
_CARRIERS = ("homepage", "article", "image", "video")
_STATUSES = frozenset({"passed", "failed", "blocked", "skipped"})


class AppUatRawResultError(ValueError):
    """The explicit App UAT input cannot produce trustworthy raw results."""


def _fail(detail: str) -> None:
    raise AppUatRawResultError(f"OPS.APP_UAT_RAW_RESULT.invalid: {detail}")


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(f"{field} must be a non-empty canonical string")
    return value


def _digest(value: object, *, field: str) -> str:
    result = _text(value, field=field)
    if _DIGEST_RE.fullmatch(result) is None:
        _fail(f"{field} must be sha256:<64 lowercase hex>")
    return result


def _relative_ref(value: object, *, field: str) -> str:
    result = _text(value, field=field)
    reference = PurePosixPath(result)
    if (
        result.startswith("/")
        or "\\" in result
        or reference.as_posix() != result
        or any(part in {"", ".", ".."} for part in reference.parts)
    ):
        _fail(f"{field} must be a contained relative reference")
    return result


def _real_root(path: Path) -> Path:
    candidate = path.expanduser().absolute()
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise AppUatRawResultError(
            "OPS.APP_UAT_RAW_RESULT.path_invalid: evidence root is unavailable"
        ) from exc
    if (
        candidate.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or candidate.resolve(strict=True) != candidate
    ):
        _fail("evidence root must be a real non-symlink directory")
    return candidate


def _read_exact(root: Path, ref: str, *, label: str) -> bytes:
    reference = PurePosixPath(_relative_ref(ref, field=f"{label}.ref"))
    parent = root
    for part in reference.parts[:-1]:
        parent /= part
        try:
            metadata = parent.lstat()
        except OSError as exc:
            raise AppUatRawResultError(
                f"OPS.APP_UAT_RAW_RESULT.path_invalid: {label} parent is unavailable"
            ) from exc
        if parent.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            _fail(f"{label} path traverses a symlink or non-directory")
    path = parent / reference.name
    try:
        before = path.lstat()
    except OSError as exc:
        raise AppUatRawResultError(
            f"OPS.APP_UAT_RAW_RESULT.path_invalid: {label} is unavailable"
        ) from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        _fail(f"{label} must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AppUatRawResultError(
            f"OPS.APP_UAT_RAW_RESULT.path_invalid: {label} cannot be opened safely"
        ) from exc
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
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        _fail(f"{label} changed during exact-byte read")
    return b"".join(chunks)


def _decode_object(encoded: bytes, *, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        text = encoded.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=unique,
            parse_constant=lambda value: (_ for _ in ()).throw(
                AppUatRawResultError(
                    f"OPS.APP_UAT_RAW_RESULT.invalid: invalid JSON constant {value}"
                )
            ),
        )
        value, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppUatRawResultError(
            f"OPS.APP_UAT_RAW_RESULT.invalid: {label} is not UTF-8 JSON"
        ) from exc
    if text[end:].strip() or not isinstance(value, dict):
        _fail(f"{label} must contain exactly one JSON object")
    return value


def _canonical_plan_digest(plan: Mapping[str, Any]) -> str:
    encoded = (
        json.dumps(
            dict(plan),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _required_slots(plan: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if plan.get("schema") != "quwoquan_data.release_uat_sample_plan":
        _fail("sample plan schema is invalid")
    selection = plan.get("selectionEvidence")
    if not isinstance(selection, Mapping):
        _fail("sample plan selectionEvidence is missing")
    source_digest = _digest(
        selection.get("sourceIdentitySetDigest"),
        field="samplePlan.selectionEvidence.sourceIdentitySetDigest",
    )
    raw_samples = plan.get("samples")
    raw_cells = plan.get("entryCarrierCells")
    if not isinstance(raw_samples, list) or not raw_samples:
        _fail("sample plan samples must be non-empty")
    if not isinstance(raw_cells, list) or not raw_cells:
        _fail("sample plan entryCarrierCells must be non-empty")

    samples: dict[str, dict[str, str]] = {}
    for index, raw in enumerate(raw_samples):
        if not isinstance(raw, Mapping):
            _fail(f"samplePlan.samples[{index}] is invalid")
        if set(raw) != {
            "sampleId", "carrier", "objectId", "objectRef", "objectDigest",
        }:
            _fail(f"samplePlan.samples[{index}] fields are invalid")
        sample_id = _text(raw.get("sampleId"), field=f"samplePlan.samples[{index}].sampleId")
        carrier = _text(raw.get("carrier"), field=f"samplePlan.samples[{index}].carrier")
        object_id = _text(raw.get("objectId"), field=f"samplePlan.samples[{index}].objectId")
        object_ref = _relative_ref(
            raw.get("objectRef"), field=f"samplePlan.samples[{index}].objectRef"
        )
        object_digest = _digest(
            raw.get("objectDigest"), field=f"samplePlan.samples[{index}].objectDigest"
        )
        if carrier not in _CARRIERS or sample_id in samples:
            _fail("sample plan sample identity is duplicated or uses an unknown carrier")
        if any(
            sample["objectId"] == object_id
            or sample["objectRef"] == object_ref
            for sample in samples.values()
        ):
            _fail("sample plan objectId and objectRef must each be unique")
        expected_prefix = (
            "objects/entities/" if carrier == "homepage" else f"objects/posts/{carrier}/"
        )
        if not object_ref.startswith(expected_prefix):
            _fail(f"samplePlan.samples[{index}].objectRef is not carrier-bound")
        samples[sample_id] = {
            "sampleId": sample_id,
            "carrier": carrier,
            "objectId": object_id,
            "objectRef": object_ref,
            "objectDigest": object_digest,
        }
    if plan.get("sampleCount") != len(samples):
        _fail("sample plan sampleCount drifted")

    cells: dict[tuple[str, str], dict[str, str]] = {}
    for index, raw in enumerate(raw_cells):
        if not isinstance(raw, Mapping):
            _fail(f"samplePlan.entryCarrierCells[{index}] is invalid")
        entry = _text(raw.get("entry"), field=f"samplePlan.entryCarrierCells[{index}].entry")
        carrier = _text(raw.get("carrier"), field=f"samplePlan.entryCarrierCells[{index}].carrier")
        applicability = _text(
            raw.get("applicability"),
            field=f"samplePlan.entryCarrierCells[{index}].applicability",
        )
        key = (entry, carrier)
        if entry not in _ENTRIES or carrier not in _CARRIERS or key in cells:
            _fail("sample plan entry/carrier cell is duplicated or unknown")
        if applicability == "required":
            cells[key] = {
                "entrySurface": entry,
                "carrier": carrier,
                "specRef": _text(raw.get("specRef"), field="required cell.specRef"),
                "runnerIdentity": _text(
                    raw.get("runnerClass"), field="required cell.runnerClass"
                ),
            }
        elif applicability == "not_applicable":
            _text(raw.get("reasonCode"), field="not-applicable cell.reasonCode")
            cells[key] = {"entrySurface": entry, "carrier": carrier}
        else:
            _fail("sample plan cell applicability is unknown")
    if set(cells) != {(entry, carrier) for entry in _ENTRIES for carrier in _CARRIERS}:
        _fail("sample plan must declare the complete entry/carrier matrix")

    slots: list[dict[str, str]] = []
    for sample in samples.values():
        for entry in _ENTRIES:
            cell = cells[(entry, sample["carrier"])]
            if "specRef" not in cell:
                continue
            slots.append({**sample, **cell})
    if not slots:
        _fail("sample plan has no required sample/case slots")
    return source_digest, slots


def _slot_id(binding_digest: str, slot: Mapping[str, str]) -> str:
    return content_consumer_raw_slot_id(
        target_uat_binding_digest=binding_digest,
        sample_id=slot["sampleId"],
        entry_surface=slot["entrySurface"],
        carrier=slot["carrier"],
        spec_ref=slot["specRef"],
        runner_identity=slot["runnerIdentity"],
    )


def _case_source(source: Mapping[str, Any], *, index: int) -> tuple[str, str]:
    if not isinstance(source, Mapping) or set(source) != {"receiptRef", "receiptSha256"}:
        _fail(f"caseExecutionReports[{index}] must contain receiptRef and receiptSha256")
    return (
        _relative_ref(source.get("receiptRef"), field=f"caseExecutionReports[{index}].receiptRef"),
        _digest(source.get("receiptSha256"), field=f"caseExecutionReports[{index}].receiptSha256"),
    )


def _validate_case_execution(
    report: Mapping[str, Any],
    *,
    slot: Mapping[str, str],
    binding: Mapping[str, Any],
    binding_digest: str,
    source_identity_set_digest: str,
    evidence_root: Path,
) -> None:
    expected = {
        "schema": CASE_EXECUTION_SCHEMA,
        "sampleId": slot["sampleId"],
        "entrySurface": slot["entrySurface"],
        "carrier": slot["carrier"],
        "objectId": slot["objectId"],
        "specRef": slot["specRef"],
        "runnerIdentity": slot["runnerIdentity"],
        "releaseId": binding["releaseId"],
        "releaseDigest": binding["releaseDigest"],
        "sourceIdentitySetDigest": source_identity_set_digest,
        "targetUatBindingDigest": binding_digest,
    }
    drifted = [field for field, value in expected.items() if report.get(field) != value]
    if drifted:
        _fail("case execution identity drifted at " + ",".join(drifted))
    _text(report.get("caseId"), field="case execution caseId")
    status = _text(report.get("status"), field="case execution status")
    if status not in _STATUSES:
        _fail("case execution status is unknown")
    reason = report.get("reasonCode")
    if status == "passed" and reason is not None:
        _fail("passed case execution must not contain reasonCode")
    if status != "passed":
        _text(reason, field="case execution reasonCode")
    if _COMMIT_RE.fullmatch(_text(report.get("commitSha"), field="case execution commitSha")) is None:
        _fail("case execution commitSha is invalid")
    for field in ("contractGraphSourceHash", "candidateManifestSha256"):
        if _SHA_RE.fullmatch(_text(report.get(field), field=f"case execution {field}")) is None:
            _fail(f"case execution {field} is invalid")
    provider_identity = _text(
        report.get("provider"), field="case execution provider"
    )
    if provider_identity != binding["provider"]["identity"]:
        _fail("case execution provider differs from TargetUatBinding provider")
    _text(report.get("startedAt"), field="case execution startedAt")
    _text(report.get("completedAt"), field="case execution completedAt")
    target = report.get("target")
    if not isinstance(target, Mapping) or set(target) != {"kind", "id"}:
        _fail("case execution target is invalid")

    exit_code = report.get("patrolExitCode")
    page = report.get("pageEvidence")
    if not isinstance(page, Mapping):
        _fail("case execution pageEvidence is invalid")
    page_status = page.get("status")
    if page_status == "present":
        if set(page) != {"status", "ref", "sha256"}:
            _fail("present page evidence fields are invalid")
        page_ref = _relative_ref(page.get("ref"), field="case execution pageEvidence.ref")
        page_digest = _digest(page.get("sha256"), field="case execution pageEvidence.sha256")
        page_bytes = _read_exact(evidence_root, page_ref, label="case page evidence")
        if "sha256:" + hashlib.sha256(page_bytes).hexdigest() != page_digest:
            _fail("case page evidence exact bytes drifted")
    elif page_status == "missing":
        if set(page) != {"status"}:
            _fail("missing page evidence must not claim a reference")
    else:
        _fail("case execution pageEvidence.status is unknown")

    if status == "passed" and (exit_code != 0 or page_status != "present"):
        _fail("Patrol failure or missing page evidence cannot be rewritten as passed")
    if status == "failed" and (
        not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code == 0
    ):
        _fail("failed case execution must preserve a non-zero Patrol exit code")
    if status == "blocked" and exit_code == 0 and page_status == "present":
        _fail("blocked case execution lacks a blocking observation")
    if status == "skipped" and (exit_code is not None or page_status != "missing"):
        _fail("skipped case execution must remain not executed with missing page evidence")



def expected_app_uat_raw_coverage(sample_plan: Mapping[str, Any]) -> int:
    """Return the exact required sample/case slot count after strict validation."""

    _source_identity_set_digest, slots = _required_slots(sample_plan)
    return len(slots)

def emit_app_uat_raw_results(
    *,
    evidence_root: Path,
    target_binding: Mapping[str, Any],
    sample_plan: Mapping[str, Any],
    case_execution_reports: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Write one create-once raw result for every required sample/case slot.

    ``case_execution_reports`` contains explicit exact-byte receipt references;
    the receipt itself binds release, source identity, target binding, sample,
    case, spec, Patrol exit and page-evidence outcome.  Returned refs are direct
    raw result refs for diagnostic bundles and EnvironmentAcceptanceFact.
    """

    root = _real_root(evidence_root)
    try:
        binding = validate_target_uat_binding(target_binding)
        binding_digest = target_uat_binding_digest(binding)
    except TargetUatBindingError as exc:
        raise AppUatRawResultError(str(exc)) from exc
    if sample_plan.get("releaseId") != binding["releaseId"]:
        _fail("sample plan releaseId differs from TargetUatBinding")
    if sample_plan.get("releaseDigest") != binding["releaseDigest"]:
        _fail("sample plan releaseDigest differs from TargetUatBinding")
    source_identity_set_digest, slots = _required_slots(sample_plan)
    if _canonical_plan_digest(sample_plan) != binding["releaseUatSamplePlanDigest"]:
        _fail("sample plan exact canonical digest differs from TargetUatBinding")
    expected = {
        (slot["sampleId"], slot["entrySurface"], slot["carrier"]): slot
        for slot in slots
    }
    if len(expected) != len(slots):
        _fail("required sample/case slot identity is duplicated")

    reports: dict[tuple[str, str, str], tuple[str, str, dict[str, Any]]] = {}
    for index, source in enumerate(case_execution_reports):
        receipt_ref, receipt_digest = _case_source(source, index=index)
        encoded = _read_exact(root, receipt_ref, label=f"caseExecutionReports[{index}]")
        observed_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if observed_digest != receipt_digest:
            _fail(f"caseExecutionReports[{index}] receipt digest drifted")
        report = _decode_object(encoded, label=f"caseExecutionReports[{index}]")
        key = (
            _text(report.get("sampleId"), field="case execution sampleId"),
            _text(report.get("entrySurface"), field="case execution entrySurface"),
            _text(report.get("carrier"), field="case execution carrier"),
        )
        if key in reports:
            _fail("case execution reports contain a duplicate required slot")
        slot = expected.get(key)
        if slot is None:
            _fail("case execution report does not belong to a required sample/case slot")
        _validate_case_execution(
            report,
            slot=slot,
            binding=binding,
            binding_digest=binding_digest,
            source_identity_set_digest=source_identity_set_digest,
            evidence_root=root,
        )
        reports[key] = (receipt_ref, receipt_digest, report)
    missing = sorted(set(expected) - set(reports))
    if missing:
        _fail(f"required sample/case execution reports are missing: {missing}")

    prepared: list[tuple[str, Path, dict[str, Any], str, bool]] = []
    case_ids: set[str] = set()
    binding_directory = binding["bindingId"].removeprefix("sha256:")
    for key in sorted(expected):
        slot = expected[key]
        receipt_ref, receipt_digest, report = reports[key]
        case_id = str(report["caseId"])
        if case_id in case_ids:
            _fail("case execution caseId is duplicated across required slots")
        case_ids.add(case_id)
        status = str(report["status"])
        result: dict[str, Any] = {
            "objectId": slot["objectId"],
            "specRef": slot["specRef"],
            "caseId": case_id,
            "producer": "app",
            "layer": "user_acceptance",
            "status": status,
            "target": dict(report["target"]),
            "commitSha": report["commitSha"],
            "contractGraphSourceHash": report["contractGraphSourceHash"],
            "deploymentTarget": binding["target"],
            "baselineId": binding["candidateDigest"].removeprefix("sha256:"),
            "packageDigest": binding["packageDigest"],
            "configurationDigest": binding["configurationDigest"],
            "candidateManifestSha256": report["candidateManifestSha256"],
            "candidateDigest": binding["candidateDigest"],
            "releaseDigest": binding["releaseDigest"],
            "releaseId": binding["releaseId"],
            "targetUatBindingDigest": binding_digest,
            "entrySurface": slot["entrySurface"],
            "carrier": slot["carrier"],
            "environment": binding["environment"],
            "platform": binding["platform"],
            "deviceClass": binding["device"]["class"],
            "deviceIdentity": binding["device"]["identity"],
            "deviceRegistered": binding["device"]["registered"],
            "provider": binding["provider"]["identity"],
            "startedAt": report["startedAt"],
            "completedAt": report["completedAt"],
            "runnerIdentity": slot["runnerIdentity"],
            "artifactSha256": receipt_digest.removeprefix("sha256:"),
            "receiptRef": receipt_ref,
            "uatProfile": binding["profile"],
            "nonPromotable": binding["nonPromotable"],
            "artifactClass": binding["artifact"]["class"],
            "physicalDevice": binding["device"]["class"] == "physical",
        }
        if status != "passed":
            result["reasonCode"] = report["reasonCode"]
        try:
            validate_readiness_case_result(result, generated_at=str(report["completedAt"]))
        except ReadinessCaseResultError as exc:
            raise AppUatRawResultError(str(exc)) from exc
        slot_id = _slot_id(binding_digest, slot)
        reference = (
            f"{RAW_RESULT_DIRECTORY}/{binding_directory}/"
            f"{slot_id.removeprefix('sha256:')}.json"
        )
        destination = root / reference
        encoded = canonical_json_bytes(result)
        existed = destination.exists() or destination.is_symlink()
        if existed:
            if destination.is_symlink() or not destination.is_file():
                _fail("raw result create-once destination is unsafe")
            if destination.read_bytes() != encoded:
                _fail("raw result create-once destination contains different bytes")
        prepared.append((slot_id, destination, result, reference, existed))

    emitted: list[dict[str, Any]] = []
    for slot_id, destination, result, reference, existed in prepared:
        try:
            write_create_once_json(destination, result)
        except ReadinessCaseResultError as exc:
            raise AppUatRawResultError(str(exc)) from exc
        encoded = canonical_json_bytes(result)
        emitted.append(
            {
                "slotId": slot_id,
                "ref": reference,
                "digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
                "status": result["status"],
                "receiptRef": result["receiptRef"],
                "receiptSha256": "sha256:" + result["artifactSha256"],
                "created": not existed,
            }
        )
    return emitted


__all__ = [
    "AppUatRawResultError",
    "CASE_EXECUTION_SCHEMA",
    "RAW_RESULT_DIRECTORY",
    "emit_app_uat_raw_results",
    "expected_app_uat_raw_coverage",
]
