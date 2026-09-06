#!/usr/bin/env python3
"""Validate one post-promotion MainSourceSeal and CAS main to dev1.0."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OCI_REF = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")
_ZERO = "0" * 40
_ADMISSION_FIELDS = frozenset(
    {
        "schema", "decision", "headRef", "baseRef", "headSha", "headTree",
        "baseSha", "syntheticMergeSha", "syntheticMergeTree", "qualification",
        "authority", "requiredEvidence", "changedPaths", "promotionReadyAt",
        "admissionId",
    }
)
_SEAL_REQUIRED_FIELDS = frozenset(
    {
        "schema", "sourceStatus", "releaseStatus", "mainRef", "mainSha",
        "mainTree", "promotionAdmission", "sourceHeadSha", "promotionReadyAt",
        "mainReadbackAt", "durationSeconds", "sealId",
    }
)
_SEAL_HOSTED_FIELDS = frozenset(
    {"promotionAdmissionOciRef", "hostedPromotionHandoff"}
)
_HOSTED_HANDOFF_FIELDS = frozenset({"ref", "digest"})
_HOSTED_HANDOFF_RECORD_FIELDS = frozenset(
    {
        "schema", "recordId", "checkRunId", "checkRunNodeId", "context",
        "app", "workflowActor", "createdAt", "repository",
        "pullRequestNumber", "headSha",
        "baseSha", "syntheticMergeSha", "syntheticMergeTree", "workflowRunId",
        "workflowRunAttempt", "workflowRepository", "workflowHeadSha",
        "promotionAdmissionRef", "admissionBytesDigest",
    }
)
_HOSTED_HANDOFF_IDENTITY_FIELDS = frozenset(
    {
        "schema", "repository", "pullRequestNumber", "headSha", "baseSha",
        "syntheticMergeSha", "syntheticMergeTree", "workflowRunId",
        "workflowRunAttempt", "workflowRepository", "workflowHeadSha",
        "workflowActor", "promotionAdmissionRef", "admissionBytesDigest",
        "createdAt",
    }
)


class SystemBacksyncError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str) -> SystemBacksyncError:
    return SystemBacksyncError(code, detail)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Mapping[str, Any] | bytes | Path) -> str:
    if isinstance(value, Path):
        raw = value.read_bytes()
    elif isinstance(value, bytes):
        raw = value
    else:
        raw = _canonical_bytes(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\x00\r\n")
    ):
        raise _fail("OPS.BRANCH.POLICY_INVALID", f"{field} is invalid")
    return value


def _sha(value: object, field: str) -> str:
    exact = _text(value, field)
    if _SHA.fullmatch(exact) is None or exact == _ZERO:
        raise _fail(
            "OPS.BRANCH.POLICY_INVALID",
            f"{field} must be a non-zero lowercase 40-character Git OID",
        )
    return exact


def _exact_digest(value: object, field: str) -> str:
    exact = _text(value, field)
    if _DIGEST.fullmatch(exact) is None:
        raise _fail("OPS.BRANCH.POLICY_INVALID", f"{field} must be sha256")
    return exact


def _timestamp(value: object, field: str) -> tuple[str, dt.datetime]:
    exact = _text(value, field)
    try:
        parsed = dt.datetime.fromisoformat(exact.replace("Z", "+00:00"))
    except ValueError as error:
        raise _fail("OPS.BRANCH.POLICY_INVALID", f"{field} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise _fail("OPS.BRANCH.POLICY_INVALID", f"{field} must include timezone")
    return exact, parsed


def _exact_local_ref(
    value: object, field: str, *, expected_ref: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            f"{field} must contain exact ref and digest",
        )
    ref = _text(value.get("ref"), f"{field}.ref")
    if expected_ref is not None and ref != expected_ref:
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            f"{field}.ref must equal {expected_ref}",
        )
    path = Path(ref)
    if (
        path.is_absolute()
        or path.as_posix() != ref
        or any(part in {"", ".", "..", "latest", "main"} for part in path.parts)
    ):
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            f"{field}.ref is mutable or unsafe",
        )
    return {"ref": ref, "digest": _exact_digest(value.get("digest"), f"{field}.digest")}


def _load_canonical_json(path_value: Path, field: str) -> tuple[Path, dict[str, Any]]:
    source = path_value.expanduser()
    if source.is_symlink() or not source.is_file():
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", f"{field} is not a regular file")
    source = source.resolve(strict=True)
    if not stat.S_ISREG(source.stat().st_mode):
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", f"{field} is not a regular file")
    try:
        raw = source.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", f"{field} is not canonical JSON") from error
    if not isinstance(payload, dict) or raw != _canonical_bytes(payload) + b"\n":
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", f"{field} bytes are not canonical")
    return source, payload


def _load_exact_oci_fact(
    *, path: Path, exact_ref: str, payload_digest: str,
    expected_repository: str, field: str,
) -> tuple[Path, dict[str, Any], dict[str, str]]:
    ref = _text(exact_ref, f"{field}.ref")
    if _OCI_REF.fullmatch(ref) is None or ref.rsplit("@", 1)[0] != expected_repository:
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            f"{field}.ref must be the canonical exact OCI @sha256 reference",
        )
    manifest_digest = _exact_digest(payload_digest, f"{field}.digest")
    if ref.rsplit("@", 1)[1] != manifest_digest:
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            f"{field}.digest must equal the OCI reference digest",
        )
    source, payload = _load_canonical_json(path, field)
    return source, payload, {
        "ref": ref,
        "digest": manifest_digest,
        "bytesDigest": _digest(source),
    }


def _validate_admission(
    payload: dict[str, Any], *, exact: Mapping[str, str], source_sha: str,
    main_tree: str,
) -> dict[str, Any]:
    if set(payload) != _ADMISSION_FIELDS:
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "PromotionAdmissionReceipt shape drifted")
    unsigned = {key: value for key, value in payload.items() if key != "admissionId"}
    head = _sha(payload.get("headSha"), "promotionAdmission.headSha")
    base = _sha(payload.get("baseSha"), "promotionAdmission.baseSha")
    _sha(payload.get("syntheticMergeSha"), "promotionAdmission.syntheticMergeSha")
    head_tree = _sha(payload.get("headTree"), "promotionAdmission.headTree")
    merge_tree = _sha(payload.get("syntheticMergeTree"), "promotionAdmission.syntheticMergeTree")
    if (
        payload.get("schema") != "quwoquan_ops.promotion_admission_receipt.v1"
        or payload.get("decision") != "admitted"
        or payload.get("headRef") != "refs/heads/dev1.0"
        or payload.get("baseRef") != "refs/heads/main"
        or payload.get("admissionId") != _digest(unsigned)
        or head != source_sha
        or merge_tree != main_tree
    ):
        raise _fail(
            "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
            "PromotionAdmissionReceipt does not bind the sealed promotion",
        )
    _timestamp(payload.get("promotionReadyAt"), "promotionAdmission.promotionReadyAt")
    _exact_local_ref(payload.get("qualification"), "promotionAdmission.qualification")
    authority = payload.get("authority")
    required = payload.get("requiredEvidence")
    changed = payload.get("changedPaths")
    if (
        not isinstance(authority, Mapping)
        or set(authority) != {"approval", "threads", "ruleset", "changedBoundary"}
        or any(
            not isinstance(value, Mapping) or set(value) != {"ref", "digest"}
            for value in authority.values()
        )
        or not isinstance(required, list)
        or not required
        or any(
            not isinstance(value, Mapping) or set(value) != {"ref", "digest"}
            for value in required
        )
        or required != sorted(required, key=lambda value: (value["ref"], value["digest"]))
        or len({(value["ref"], value["digest"]) for value in required}) != len(required)
        or not isinstance(changed, list)
        or not changed
        or changed != sorted(set(changed))
        or any(not isinstance(value, str) or not value for value in changed)
    ):
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            "PromotionAdmissionReceipt nested authority shape drifted",
        )
    for name, value in authority.items():
        _exact_local_ref(value, f"promotionAdmission.authority.{name}")
    for index, value in enumerate(required):
        _exact_local_ref(value, f"promotionAdmission.requiredEvidence[{index}]")
    return {
        "ref": exact["ref"],
        "digest": exact["digest"],
        "bytesDigest": exact["bytesDigest"],
        "admissionId": _exact_digest(payload.get("admissionId"), "promotionAdmission.admissionId"),
        "baseSha": base,
        "headSha": head,
        "headTree": head_tree,
        "syntheticMergeSha": payload["syntheticMergeSha"],
        "syntheticMergeTree": merge_tree,
    }


def _validate_main_source_seal(
    *, github_repository: str, seal_path: Path, seal_ref: str,
    seal_digest: str, admission_path: Path, hosted_handoff_path: Path | None,
    source_sha: str, expected_app_slug: str, expected_app_id: str,
) -> tuple[str, str, dict[str, Any]]:
    repository = _text(github_repository, "githubRepository")
    if _REPOSITORY.fullmatch(repository) is None:
        raise _fail("OPS.BRANCH.POLICY_INVALID", "githubRepository must be lowercase owner/name")
    source = _sha(source_sha, "sourceSha")
    path, seal, seal_exact = _load_exact_oci_fact(
        path=seal_path, exact_ref=seal_ref, payload_digest=seal_digest,
        expected_repository=f"ghcr.io/{repository}/main-source-seal",
        field="mainSourceSeal",
    )
    fields = set(seal)
    if fields not in {_SEAL_REQUIRED_FIELDS, _SEAL_REQUIRED_FIELDS | _SEAL_HOSTED_FIELDS}:
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "MainSourceSeal shape drifted")
    unsigned = {key: value for key, value in seal.items() if key != "sealId"}
    main_sha = _sha(seal.get("mainSha"), "mainSourceSeal.mainSha")
    main_tree = _sha(seal.get("mainTree"), "mainSourceSeal.mainTree")
    source_head = _sha(seal.get("sourceHeadSha"), "mainSourceSeal.sourceHeadSha")
    ready_text, ready = _timestamp(seal.get("promotionReadyAt"), "mainSourceSeal.promotionReadyAt")
    readback_text, readback = _timestamp(seal.get("mainReadbackAt"), "mainSourceSeal.mainReadbackAt")
    duration = seal.get("durationSeconds")
    if (
        seal.get("schema") != "quwoquan_ops.main_source_seal.v1"
        or seal.get("sourceStatus") != "source-admitted"
        or seal.get("releaseStatus") != "not_selected"
        or seal.get("mainRef") != "refs/heads/main"
        or seal.get("sealId") != _digest(unsigned)
        or source_head != source
        or readback < ready
        or not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration != int((readback - ready).total_seconds())
    ):
        raise _fail("OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE", "MainSourceSeal identity drifted")
    predecessor = _exact_local_ref(
        seal.get("promotionAdmission"),
        "mainSourceSeal.promotionAdmission",
        expected_ref="promotion-admission/fact.json",
    )
    predecessor_source, admission = _load_canonical_json(admission_path, "promotionAdmission")
    if _digest(predecessor_source) != predecessor["digest"]:
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            "PromotionAdmissionReceipt exact bytes differ from MainSourceSeal predecessor",
        )
    admission_exact = {
        "ref": predecessor["ref"],
        "digest": predecessor["digest"],
        "bytesDigest": _digest(predecessor_source),
    }
    admission_evidence = _validate_admission(
        admission, exact=admission_exact, source_sha=source, main_tree=main_tree,
    )
    if ready_text != admission.get("promotionReadyAt"):
        raise _fail(
            "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
            "MainSourceSeal promotion time differs from predecessor",
        )
    hosted_evidence: dict[str, str] | None = None
    if _SEAL_HOSTED_FIELDS <= fields:
        admission_oci = _text(
            seal.get("promotionAdmissionOciRef"),
            "mainSourceSeal.promotionAdmissionOciRef",
        )
        if (
            _OCI_REF.fullmatch(admission_oci) is None
            or admission_oci.rsplit("@", 1)[0]
            != f"ghcr.io/{repository}/promotion-admission"
        ):
            raise _fail(
                "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
                "MainSourceSeal hosted admission ref is not exact or canonical",
            )
        hosted = seal.get("hostedPromotionHandoff")
        if not isinstance(hosted, Mapping) or set(hosted) != _HOSTED_HANDOFF_FIELDS:
            raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "hosted promotion handoff shape drifted")
        hosted_ref = _text(hosted.get("ref"), "mainSourceSeal.hostedPromotionHandoff.ref")
        hosted_digest = _exact_digest(
            hosted.get("digest"), "mainSourceSeal.hostedPromotionHandoff.digest"
        )
        if hosted_ref != "promotion-handoff/record.json":
            raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "hosted promotion handoff ref drifted")
        if hosted_handoff_path is None:
            raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "hosted promotion handoff bytes are missing")
        hosted_path, hosted_record = _load_canonical_json(
            hosted_handoff_path, "hostedPromotionHandoff"
        )
        if _digest(hosted_path) != hosted_digest or set(hosted_record) != _HOSTED_HANDOFF_RECORD_FIELDS:
            raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "hosted promotion handoff bytes drifted")
        app = hosted_record.get("app")
        workflow_actor = hosted_record.get("workflowActor")
        trusted_app_slug = _text(expected_app_slug, "trustedPromotionRecorder.appSlug")
        if not expected_app_id.isdigit() or int(expected_app_id) <= 0:
            raise _fail(
                "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
                "trusted promotion recorder App id is unavailable",
            )
        trusted_app_id = int(expected_app_id)
        identity = {
            key: hosted_record[key] for key in _HOSTED_HANDOFF_IDENTITY_FIELDS
        }
        identity["handoffContext"] = hosted_record.get("context")
        positive_ids = (
            hosted_record.get("checkRunId"), hosted_record.get("pullRequestNumber"),
            hosted_record.get("workflowRunId"), hosted_record.get("workflowRunAttempt"),
        )
        if (
            hosted_record.get("schema")
            != "quwoquan_ops.promotion_admission_handoff.v1"
            or hosted_record.get("context")
            != "quwoquan/promotion-admission-handoff/v1"
            or hosted_record.get("recordId") != _digest(identity)
            or any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in positive_ids)
            or not isinstance(app, Mapping)
            or set(app) != {"slug", "id"}
            or not isinstance(app.get("slug"), str)
            or not app.get("slug")
            or not isinstance(app.get("id"), int)
            or isinstance(app.get("id"), bool)
            or app.get("id", 0) <= 0
            or (app.get("slug"), app.get("id"))
            != (trusted_app_slug, trusted_app_id)
            or not isinstance(workflow_actor, Mapping)
            or set(workflow_actor) != {"login", "id"}
            or not isinstance(workflow_actor.get("login"), str)
            or not workflow_actor.get("login")
            or not isinstance(workflow_actor.get("id"), int)
            or isinstance(workflow_actor.get("id"), bool)
            or workflow_actor.get("id", 0) <= 0
            or hosted_record.get("repository") != repository
            or hosted_record.get("workflowRepository") != repository
            or hosted_record.get("headSha") != source
            or hosted_record.get("workflowHeadSha") != source
            or hosted_record.get("baseSha") != admission_evidence["baseSha"]
            or hosted_record.get("syntheticMergeSha")
            != admission_evidence["syntheticMergeSha"]
            or hosted_record.get("syntheticMergeTree") != main_tree
            or hosted_record.get("promotionAdmissionRef") != admission_oci
            or hosted_record.get("admissionBytesDigest") != predecessor["digest"]
        ):
            raise _fail(
                "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
                "hosted promotion handoff does not bind the sealed promotion",
            )
        _text(hosted_record.get("checkRunNodeId"), "hostedPromotionHandoff.checkRunNodeId")
        _timestamp(hosted_record.get("createdAt"), "hostedPromotionHandoff.createdAt")
        hosted_evidence = {
            "ref": hosted_ref,
            "digest": hosted_digest,
            "recordId": _exact_digest(
                hosted_record.get("recordId"), "hostedPromotionHandoff.recordId"
            ),
        }
    return main_sha, main_tree, {
        "mainSourceSeal": seal_exact,
        "mainSourceSealBytesDigest": _digest(path),
        "sealId": _exact_digest(seal.get("sealId"), "mainSourceSeal.sealId"),
        "promotionAdmission": admission_evidence,
        "promotionAdmissionOciRef": seal.get("promotionAdmissionOciRef"),
        "hostedPromotionHandoff": hosted_evidence,
        "sourceGitSha": source,
        "mainGitSha": main_sha,
        "mainTree": main_tree,
        "promotionReadyAt": ready_text,
        "mainReadbackAt": readback_text,
    }


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repository, text=True, capture_output=True, check=False,
    )
    if check and result.returncode:
        detail = " ".join((result.stderr or result.stdout).split()) or "git query failed"
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", detail)
    return result


def _local_oid(repository: Path, ref: str, field: str) -> str:
    return _sha(_git(repository, "rev-parse", f"{ref}^{{commit}}").stdout.strip(), field)


def _remote_oid(repository: Path, remote: str, branch: str) -> str:
    fields = _git(repository, "ls-remote", "--refs", remote, f"refs/heads/{branch}").stdout.strip().split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}":
        raise _fail(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
            f"remote {branch} readback is missing or ambiguous",
        )
    return _sha(fields[0], f"remote.{branch}")


def _write_once(path_value: Path, payload: Mapping[str, Any]) -> Path:
    data = _canonical_bytes(payload) + b"\n"
    candidate = path_value.expanduser()
    if candidate.is_symlink():
        raise _fail("OPS.BRANCH.POLICY_INVALID", "evidence path is a symlink")
    path = candidate.resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as error:
        if path.is_symlink() or path.read_bytes() != data:
            raise _fail("OPS.BRANCH.BACKSYNC_CAS_CONFLICT", "create-once backsync fact conflict") from error
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _validate_managed_environment(
    environment: Mapping[str, str], *, github_repository: str, main_sha: str,
) -> None:
    caller_ref = environment.get("GITHUB_WORKFLOW_REF", "")
    workflow_ref = environment.get("QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF", "")
    expected_caller_suffix = "/.github/workflows/delivery-gate.yml@refs/heads/main"
    expected_workflow_prefix = (
        f"{github_repository}/.github/workflows/system-backsync.yml@"
    )
    workflow_revision = workflow_ref.rsplit("@", 1)[-1]
    if (
        environment.get("GITHUB_ACTIONS") != "true"
        or environment.get("GITHUB_EVENT_NAME") != "push"
        or environment.get("GITHUB_REF_TYPE") != "branch"
        or environment.get("GITHUB_REF_NAME") != "main"
        or environment.get("GITHUB_REF") != "refs/heads/main"
        or environment.get("GITHUB_REPOSITORY") != github_repository
        or environment.get("GITHUB_SHA") != main_sha
        or environment.get("GITHUB_EVENT_AFTER") != main_sha
        or environment.get("QWQ_MANAGED_SYSTEM_BACKSYNC") != "system-fast-forward-cas-v1"
        or not caller_ref.endswith(expected_caller_suffix)
        or not workflow_ref.startswith(expected_workflow_prefix)
        or workflow_revision not in {"refs/heads/main", main_sha}
    ):
        raise _fail(
            "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED",
            "system backsync requires the canonical main-pinned reusable workflow",
        )


def backsync_main_to_dev(
    *, repository: Path, remote: str, expected_dev_before: str,
    source_sha: str, github_repository: str, environment: Mapping[str, str],
    main_source_seal_path: Path, main_source_seal_ref: str,
    main_source_seal_digest: str, promotion_admission_path: Path,
    hosted_handoff_path: Path | None = None, evidence_path: Path, recorded_at: str,
) -> Path:
    """Validate source convergence authority, then expected-before FF-CAS dev1.0."""
    repository = repository.expanduser().resolve()
    if remote != "origin":
        raise _fail("OPS.BRANCH.POLICY_INVALID", "remote must be canonical origin")
    if not (repository / ".git").exists():
        raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", "repository is not a Git worktree")
    before = _sha(expected_dev_before, "expectedDevBefore")
    source = _sha(source_sha, "sourceSha")
    recorded_text, _ = _timestamp(recorded_at, "recordedAt")
    after, sealed_tree, source_evidence = _validate_main_source_seal(
        github_repository=github_repository,
        seal_path=main_source_seal_path,
        seal_ref=main_source_seal_ref,
        seal_digest=main_source_seal_digest,
        admission_path=promotion_admission_path,
        hosted_handoff_path=hosted_handoff_path, source_sha=source,
        expected_app_slug=environment.get("QWQ_PROMOTION_RECORDER_APP_SLUG", ""),
        expected_app_id=environment.get("QWQ_PROMOTION_RECORDER_APP_ID", ""),
    )
    _validate_managed_environment(
        environment, github_repository=github_repository, main_sha=after
    )
    if before != source:
        raise _fail(
            "OPS.BRANCH.BACKSYNC_CAS_CONFLICT",
            "expected dev before must equal the sealed promotion source",
        )
    if environment.get("GITHUB_EVENT_BEFORE") != source_evidence["promotionAdmission"]["baseSha"]:
        raise _fail(
            "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
            "push before SHA does not equal the admitted main base",
        )
    local_main = _local_oid(repository, "HEAD", "local.main")
    local_tree = _sha(
        _git(repository, "show", "-s", "--format=%T", local_main).stdout.strip(),
        "local.mainTree",
    )
    parents = _git(repository, "show", "-s", "--format=%P", local_main).stdout.strip().split()
    source_tree = _sha(
        _git(repository, "show", "-s", "--format=%T", source).stdout.strip(),
        "local.sourceTree",
    )
    if (
        local_main != after
        or local_tree != sealed_tree
        or source_tree != source_evidence["promotionAdmission"]["headTree"]
        or parents != [source_evidence["promotionAdmission"]["baseSha"], source]
    ):
        raise _fail(
            "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
            "local main commit, tree, or promotion parents differ from the seal",
        )
    observed_before = _remote_oid(repository, remote, "dev1.0")
    remote_main = _remote_oid(repository, remote, "main")
    if remote_main != after:
        raise _fail(
            "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
            "remote main does not equal the sealed merge",
        )
    if observed_before == after:
        terminal = "idempotent"
        mutation = "not_required"
        transport = 0
    else:
        if observed_before != before:
            raise _fail(
                "OPS.BRANCH.BACKSYNC_CAS_CONFLICT",
                "dev1.0 is neither expected source nor the sealed main merge",
            )
        ancestry = _git(repository, "merge-base", "--is-ancestor", before, after, check=False)
        if ancestry.returncode == 1:
            raise _fail(
                "OPS.BRANCH.BACKSYNC_NOT_FAST_FORWARD",
                "sealed main is not a descendant of expected dev1.0 source",
            )
        if ancestry.returncode != 0:
            detail = " ".join((ancestry.stderr or ancestry.stdout).split()) or "Git ancestry authority failed"
            raise _fail("OPS.BRANCH.AUTHORITY_UNAVAILABLE", detail)
        result = _git(
            repository,
            "push", "--porcelain",
            remote, "HEAD:refs/heads/dev1.0", check=False,
        )
        mutation = "attempted"
        transport = result.returncode
        terminal = "pending_readback"
    observed_after = _remote_oid(repository, remote, "dev1.0")
    if observed_after == after:
        terminal = "idempotent" if mutation == "not_required" else "success"
    elif observed_after == before:
        terminal = "retryable_before_unchanged" if transport else "unknown_before_unchanged"
    else:
        terminal = "blocked_other_readback"
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.system_backsync_fact.v1",
        "head": "main", "base": "dev1.0",
        "expectedBeforeOid": before, "sourceOid": source,
        "requestedAfterOid": after, "observedBeforeOid": observed_before,
        "observedAfterOid": observed_after, "mutation": mutation,
        "transportExitCode": transport, "terminal": terminal,
        "sourceEvidence": source_evidence, "recordedAt": recorded_text,
    }
    body["backsyncId"] = _digest(body)
    path = _write_once(evidence_path, body)
    if terminal not in {"success", "idempotent"}:
        code = (
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE"
            if terminal in {"unknown_before_unchanged", "retryable_before_unchanged"}
            else "OPS.BRANCH.BACKSYNC_CAS_CONFLICT"
        )
        raise _fail(code, f"terminal={terminal}; evidence={path}")
    return path


def _parser() -> Any:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--expected-dev-before", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--main-source-seal-path", required=True, type=Path)
    parser.add_argument("--main-source-seal-ref", required=True)
    parser.add_argument("--main-source-seal-digest", required=True)
    parser.add_argument("--promotion-admission-path", required=True, type=Path)
    parser.add_argument("--hosted-handoff-path", type=Path)
    parser.add_argument("--evidence-path", required=True, type=Path)
    parser.add_argument("--recorded-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        path = backsync_main_to_dev(
            repository=Path(__file__).resolve().parents[2], remote=args.remote,
            expected_dev_before=args.expected_dev_before, source_sha=args.source_sha,
            github_repository=args.github_repository, environment=os.environ,
            main_source_seal_path=args.main_source_seal_path,
            main_source_seal_ref=args.main_source_seal_ref,
            main_source_seal_digest=args.main_source_seal_digest,
            promotion_admission_path=args.promotion_admission_path,
            hosted_handoff_path=args.hosted_handoff_path,
            evidence_path=args.evidence_path, recorded_at=args.recorded_at,
        )
    except (OSError, SystemBacksyncError) as error:
        code = error.code if isinstance(error, SystemBacksyncError) else "OPS.BRANCH.AUTHORITY_UNAVAILABLE"
        print(json.dumps({"terminal": "GATE_BLOCK", "code": code, "detail": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"ref": str(path), "terminal": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
