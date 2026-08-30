"""Write explicit Patrol per-case App UAT execution receipts.

The producer is marker-driven.  A suite result, parent Patrol exit code, or
page screenshot never expands into sample/case authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    canonical_json_bytes,
    write_create_once_json,
)

from .constants import APP_UAT_CASE_EVIDENCE_PREFIX
APP_UAT_CASE_EVIDENCE_SCHEMA = "quwoquan_app.app_uat_case_evidence.v1"
APP_UAT_CASE_EXECUTION_SCHEMA = "quwoquan_ops.app_uat_case_execution.v1"
APP_UAT_CASE_EVIDENCE_MISSING = (
    "APP.UAT.CASE_EVIDENCE_MISSING: Patrol run emitted no explicit per-case evidence marker"
)
_RECEIPT_DIRECTORY = "app-uat-case-executions"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ENTRIES = frozenset({"feed", "search", "recommendation", "direct_or_object_route"})
_CARRIERS = frozenset({"homepage", "article", "image", "video"})
_STATUSES = frozenset({"passed", "failed", "blocked", "skipped"})


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _digest(value: object, *, field: str) -> str:
    result = _text(value, field=field)
    if _DIGEST_RE.fullmatch(result) is None:
        raise ValueError(f"{field} must be sha256:<64 lowercase hex>")
    return result


def _relative_ref(value: object, *, field: str) -> str:
    result = _text(value, field=field)
    ref = PurePosixPath(result)
    if (
        result.startswith("/")
        or "\\" in result
        or ref.as_posix() != result
        or any(part in {"", ".", ".."} for part in ref.parts)
    ):
        raise ValueError(f"{field} must be a contained relative reference")
    return result


def _read_regular(root: Path, ref: str, *, label: str) -> bytes:
    canonical_root = root.expanduser().resolve(strict=True)
    lexical_path = canonical_root / _relative_ref(ref, field=f"{label}.ref")
    try:
        path = lexical_path.resolve(strict=True)
        path.relative_to(canonical_root)
        before = path.lstat()
    except ValueError as exc:
        raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    except OSError as exc:
        raise ValueError(f"{label} is missing") from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError(f"{label} changed during exact-byte read")
    return b"".join(chunks)


def _marker_payloads(encoded: str, *, label: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in encoded.splitlines():
        offset = line.find(APP_UAT_CASE_EVIDENCE_PREFIX)
        if offset < 0:
            continue
        raw = line[offset + len(APP_UAT_CASE_EVIDENCE_PREFIX) :].strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} contains invalid App UAT case evidence JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{label} App UAT case evidence must be an object")
        values.append(value)
    return values


def _validate_authority(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("appUatAuthority must be an object")
    required = {
        "samplePlanRef", "samplePlanSha256", "targetUatBindingRef",
        "targetUatBindingSha256", "targetUatBindingDigest", "releaseId",
        "releaseDigest", "sourceIdentitySetDigest", "commitSha",
        "contractGraphSourceHash", "candidateManifestSha256", "provider",
    }
    if set(value) != required:
        raise ValueError("appUatAuthority fields are invalid")
    authority = dict(value)
    _relative_ref(authority["samplePlanRef"], field="appUatAuthority.samplePlanRef")
    _relative_ref(authority["targetUatBindingRef"], field="appUatAuthority.targetUatBindingRef")
    for field in (
        "samplePlanSha256", "targetUatBindingSha256", "targetUatBindingDigest",
        "releaseDigest", "sourceIdentitySetDigest",
    ):
        _digest(authority[field], field=f"appUatAuthority.{field}")
    _text(authority["releaseId"], field="appUatAuthority.releaseId")
    _text(authority["provider"], field="appUatAuthority.provider")
    if _COMMIT_RE.fullmatch(_text(authority["commitSha"], field="appUatAuthority.commitSha")) is None:
        raise ValueError("appUatAuthority.commitSha is invalid")
    for field in ("contractGraphSourceHash", "candidateManifestSha256"):
        if _SHA_RE.fullmatch(_text(authority[field], field=f"appUatAuthority.{field}")) is None:
            raise ValueError(f"appUatAuthority.{field} is invalid")
    return authority


def _receipt(
    marker: Mapping[str, Any],
    *,
    authority: Mapping[str, Any],
    patrol_exit_code: object,
    evidence_root: Path,
    page_evidence_resolver: Any | None = None,
) -> dict[str, Any]:
    required = {
        "schema", "sampleId", "entrySurface", "carrier", "objectId",
        "specRef", "runnerIdentity", "status", "startedAt", "completedAt",
        "target", "pageEvidence",
    }
    allowed = required | {"reasonCode"}
    if set(marker) != required and set(marker) != allowed:
        raise ValueError("App UAT case evidence marker fields are invalid")
    if marker.get("schema") != APP_UAT_CASE_EVIDENCE_SCHEMA:
        raise ValueError("App UAT case evidence marker schema is invalid")
    sample_id = _text(marker.get("sampleId"), field="case.sampleId")
    entry = _text(marker.get("entrySurface"), field="case.entrySurface")
    carrier = _text(marker.get("carrier"), field="case.carrier")
    status = _text(marker.get("status"), field="case.status")
    if entry not in _ENTRIES or carrier not in _CARRIERS or status not in _STATUSES:
        raise ValueError("App UAT case evidence marker identity/status is invalid")
    reason = marker.get("reasonCode")
    if status == "passed" and reason is not None:
        raise ValueError("passed App UAT case evidence cannot contain reasonCode")
    if status != "passed":
        _text(reason, field="case.reasonCode")
    target = marker.get("target")
    if not isinstance(target, Mapping) or set(target) != {"kind", "id"}:
        raise ValueError("App UAT case marker target is invalid")
    normalized_target = {
        "kind": _text(target.get("kind"), field="case.target.kind"),
        "id": _text(target.get("id"), field="case.target.id"),
    }
    page = marker.get("pageEvidence")
    if page_evidence_resolver is not None:
        page = page_evidence_resolver(marker)
    if not isinstance(page, Mapping):
        raise ValueError("App UAT case pageEvidence is invalid")
    if page.get("status") == "present":
        if set(page) != {"status", "ref", "sha256"}:
            raise ValueError("present App UAT pageEvidence fields are invalid")
        page_ref = _relative_ref(page.get("ref"), field="case.pageEvidence.ref")
        page_digest = _digest(page.get("sha256"), field="case.pageEvidence.sha256")
        if "sha256:" + hashlib.sha256(_read_regular(evidence_root, page_ref, label="case page evidence")).hexdigest() != page_digest:
            raise ValueError("App UAT case page evidence exact bytes drifted")
        normalized_page = {"status": "present", "ref": page_ref, "sha256": page_digest}
    elif page.get("status") == "missing" and set(page) == {"status"}:
        normalized_page = {"status": "missing"}
    else:
        raise ValueError("App UAT case pageEvidence status is invalid")
    if status == "passed" and (patrol_exit_code != 0 or normalized_page["status"] != "present"):
        raise ValueError("Patrol failure or missing page evidence cannot become a passed case receipt")
    if status == "failed" and (
        not isinstance(patrol_exit_code, int)
        or isinstance(patrol_exit_code, bool)
        or patrol_exit_code == 0
    ):
        raise ValueError("failed App UAT case receipt requires non-zero Patrol exit")
    if status == "skipped" and patrol_exit_code is not None:
        raise ValueError("skipped App UAT case receipt must remain not executed")
    receipt: dict[str, Any] = {
        "schema": APP_UAT_CASE_EXECUTION_SCHEMA,
        "sampleId": sample_id,
        "entrySurface": entry,
        "carrier": carrier,
        "objectId": _text(marker.get("objectId"), field="case.objectId"),
        "caseId": "app_uat_" + hashlib.sha256(
            f"{authority['targetUatBindingDigest']}\0{sample_id}\0{entry}\0{carrier}".encode()
        ).hexdigest(),
        "specRef": _text(marker.get("specRef"), field="case.specRef"),
        "runnerIdentity": _text(marker.get("runnerIdentity"), field="case.runnerIdentity"),
        "releaseId": authority["releaseId"],
        "releaseDigest": authority["releaseDigest"],
        "sourceIdentitySetDigest": authority["sourceIdentitySetDigest"],
        "targetUatBindingDigest": authority["targetUatBindingDigest"],
        "status": status,
        "target": normalized_target,
        "commitSha": authority["commitSha"],
        "contractGraphSourceHash": authority["contractGraphSourceHash"],
        "candidateManifestSha256": authority["candidateManifestSha256"],
        "provider": authority["provider"],
        "startedAt": _text(marker.get("startedAt"), field="case.startedAt"),
        "completedAt": _text(marker.get("completedAt"), field="case.completedAt"),
        "patrolExitCode": patrol_exit_code,
        "pageEvidence": normalized_page,
    }
    if status != "passed":
        receipt["reasonCode"] = reason
    return receipt


def settle_app_uat_case_execution_reports(
    report: dict[str, Any],
    *,
    report_path: Path,
    page_evidence_resolver: Any | None = None,
) -> None:
    """Project explicit markers into create-once receipts at report write time."""

    raw_authority = report.get("appUatAuthority")
    if raw_authority is None:
        report.pop("appUatAuthority", None)
        return
    try:
        authority = _validate_authority(raw_authority)
        root = Path(os.environ.get("QWQ_OUTPUT_ROOT", "")).expanduser()
        root = root.resolve() if str(root) not in {"", "."} else None
        if root is None or not report_path.resolve().is_relative_to(root):
            raise ValueError("Patrol report must remain within QWQ_OUTPUT_ROOT")
        report.pop("appUatAuthority", None)
        # Re-read authority inputs by exact reference; the report cannot merely claim them.
        for prefix in ("samplePlan", "targetUatBinding"):
            ref = authority[f"{prefix}Ref"]
            expected = authority[f"{prefix}Sha256"]
            observed = "sha256:" + hashlib.sha256(
                _read_regular(root, ref, label=prefix)
            ).hexdigest()
            if observed != expected:
                raise ValueError(f"{prefix} exact bytes drifted")
        markers: list[tuple[dict[str, Any], object]] = []
        for index, run in enumerate(report.get("runs") or []):
            if not isinstance(run, Mapping):
                raise ValueError(f"Patrol run {index} is invalid")
            evidence = run.get("evidence")
            if not isinstance(evidence, Mapping):
                continue
            ref = evidence.get("structuredEvidenceLogPath")
            if not isinstance(ref, str) or not ref:
                continue
            encoded = _read_regular(root, ref, label=f"Patrol run {index} evidence").decode("utf-8")
            patrol_exit = run.get("patrolExitCode", run.get("exitCode"))
            run_markers = _marker_payloads(
                encoded,
                label=f"Patrol run {index} evidence",
            )
            for marker in run_markers:
                marker_status = marker.get("status")
                case_exit = patrol_exit
                if marker_status == "passed" and case_exit == 0:
                    # A later blocked slot can fail the parent run, but that does not
                    # rewrite an already marker-bound passed slot. The inverse remains
                    # forbidden: a non-zero native Patrol exit never becomes passed.
                    case_exit = 0
                elif marker_status == "blocked":
                    # Blocked is an explicit observation, not a failed Patrol test.
                    case_exit = 0 if patrol_exit == 0 else patrol_exit
                markers.append((marker, case_exit))
        if not markers:
            raise ValueError(APP_UAT_CASE_EVIDENCE_MISSING)
        sources: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        pending: list[tuple[Path, dict[str, Any]]] = []
        binding = authority["targetUatBindingDigest"].removeprefix("sha256:")
        for marker, patrol_exit in markers:
            receipt = _receipt(
                marker,
                authority=authority,
                patrol_exit_code=patrol_exit,
                evidence_root=root,
                page_evidence_resolver=page_evidence_resolver,
            )
            key = (receipt["sampleId"], receipt["entrySurface"], receipt["carrier"])
            if key in seen:
                raise ValueError("duplicate App UAT per-case evidence marker")
            seen.add(key)
            slot = hashlib.sha256("\0".join(key).encode()).hexdigest()
            pending.append(
                (root / _RECEIPT_DIRECTORY / binding / f"{slot}.json", receipt)
            )
        for destination, receipt in pending:
            try:
                write_create_once_json(destination, receipt)
            except ReadinessCaseResultError as exc:
                raise ValueError(str(exc)) from exc
            encoded = canonical_json_bytes(receipt)
            sources.append(
                {
                    "receiptRef": destination.relative_to(root).as_posix(),
                    "receiptSha256": "sha256:"
                    + hashlib.sha256(encoded).hexdigest(),
                }
            )
        report["appUatCaseExecutionReports"] = sources
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        report.pop("appUatAuthority", None)
        report["appUatCaseExecutionReports"] = []
        report["status"] = "gate_block"
        report["failureReason"] = str(exc)


__all__ = [
    "APP_UAT_CASE_EVIDENCE_MISSING",
    "APP_UAT_CASE_EVIDENCE_PREFIX",
    "APP_UAT_CASE_EVIDENCE_SCHEMA",
    "settle_app_uat_case_execution_reports",
]
