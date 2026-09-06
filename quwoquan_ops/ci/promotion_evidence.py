#!/usr/bin/env python3
"""Verify-only dev1.0 promotion admission and post-merge MainSourceSeal."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
ADMISSION_SCHEMA = "quwoquan_ops.promotion_admission_receipt.v1"
SEAL_SCHEMA = "quwoquan_ops.main_source_seal.v1"
HANDOFF_SCHEMA = "quwoquan_ops.promotion_admission_handoff.v1"
HANDOFF_CONTEXT = "quwoquan/promotion-admission-handoff/v1"
# handoff 有效窗口 = promotion ratchet 的 enforcement budget（1800s）；只此一处常量，不再另设 15 分钟第二阈值。
_MAX_HANDOFF_AGE_SECONDS = 1800
# 原生 GitHub Actions 就是 main ruleset 里 required check 信任的 integration；handoff check-run 由 GITHUB_TOKEN 创建。
GITHUB_ACTIONS_APP_SLUG = "github-actions"
GITHUB_ACTIONS_APP_ID = 15368
_HANDOFF_WORKFLOW_EVENTS = frozenset({"pull_request", "pull_request_review"})
_AUTHORITY_SCHEMAS = {
    "approval": "quwoquan_ops.promotion_approval_fact.v1",
    "threads": "quwoquan_ops.promotion_thread_fact.v1",
    "ruleset": "quwoquan_ops.promotion_ruleset_fact.v1",
    "changedBoundary": "quwoquan_ops.promotion_boundary_fact.v1",
}
_REQUIRED_EVIDENCE_SCHEMA = "quwoquan_ops.promotion_required_evidence_fact.v1"
_QUALIFICATION_SCHEMA = "quwoquan_ops.integration_qualification_fact.v1"
_QUALIFICATION_PAYLOAD_TYPE = (
    "application/vnd.quwoquan.integration-qualification-fact.v1+json"
)
_QUALIFICATION_KEYS = {
    "schema",
    "qualificationId",
    "decision",
    "devRef",
    "devHead",
    "devTree",
    "candidate",
    "publishResult",
    "publishAdmission",
    "environmentChain",
    "impactPlanDigest",
    "issuedAt",
    "expiresAt",
    "signer",
}


class PromotionEvidenceError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def digest(value: Mapping[str, Any] | bytes | Path) -> str:
    raw = (
        value.read_bytes()
        if isinstance(value, Path)
        else (value if isinstance(value, bytes) else canonical_bytes(value))
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\x00\r\n")
    ):
        raise PromotionEvidenceError("PROMOTION.INVALID", f"{field} is invalid")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA.fullmatch(text) is None:
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} is not an exact Git object id"
        )
    return text


def _timestamp(value: object, field: str) -> tuple[str, datetime]:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} is not RFC3339"
        ) from exc
    if parsed.tzinfo is None:
        raise PromotionEvidenceError("PROMOTION.INVALID", f"{field} lacks timezone")
    return text, parsed


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PromotionEvidenceError("PROMOTION.INVALID", f"{field} is invalid")
    return value



def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repository, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise PromotionEvidenceError(
            "PROMOTION.GIT_UNAVAILABLE", " ".join(completed.stderr.split())
        )
    return completed.stdout.strip()


def _exact(
    root: Path, value: object, field: str
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} must contain ref and digest"
        )
    ref = _text(value.get("ref"), f"{field}.ref")
    path_value = PurePosixPath(ref)
    if (
        path_value.is_absolute()
        or path_value.as_posix() != ref
        or any(part in {"", ".", ".."} for part in path_value.parts)
        or "\\" in ref
    ):
        raise PromotionEvidenceError("PROMOTION.INVALID", f"{field}.ref is invalid")
    expected = _text(value.get("digest"), f"{field}.digest")
    if _DIGEST.fullmatch(expected) is None:
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field}.digest is invalid"
        )
    path = root
    for part in path_value.parts:
        path = path / part
        if path.is_symlink():
            raise PromotionEvidenceError(
                "PROMOTION.INVALID", f"{field}.ref traverses a symlink"
            )
    if (
        not path.is_file()
        or not stat.S_ISREG(path.stat().st_mode)
        or digest(path) != expected
    ):
        raise PromotionEvidenceError(
            "PROMOTION.STALE", f"{field} exact bytes drifted"
        )
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} is not an object"
        )
    if raw != canonical_bytes(payload) + b"\n":
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} bytes are not canonical"
        )
    return payload, {"ref": ref, "digest": expected}


def _write_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise PromotionEvidenceError(
                "PROMOTION.CREATE_CONFLICT", path.name
            ) from exc
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _changed_paths(repository: Path, base: str, head: str) -> list[str]:
    raw = _git(repository, "diff", "--name-only", "-z", base, head)
    return sorted(item for item in raw.split("\0") if item)


def _valid_exact_identity(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        return False
    ref = value.get("ref")
    exact_digest = value.get("digest")
    if not isinstance(ref, str) or not ref or ref != ref.strip() or "\\" in ref:
        return False
    posix = PurePosixPath(ref)
    return (
        not posix.is_absolute()
        and posix.as_posix() == ref
        and all(part not in {"", ".", ".."} for part in posix.parts)
        and isinstance(exact_digest, str)
        and _DIGEST.fullmatch(exact_digest) is not None
    )


def _qualification(
    *,
    root: Path,
    exact: Mapping[str, str],
    head: str,
    head_tree: str,
    promotion_time: datetime,
) -> tuple[dict[str, Any], dict[str, str]]:
    fact, normalized = _exact(root, exact, "qualification")
    if set(fact) != _QUALIFICATION_KEYS:
        raise PromotionEvidenceError(
            "PROMOTION.QUALIFICATION_INVALID",
            "qualification shape or schema drifted",
        )

    signer = fact.get("signer")
    candidate = fact.get("candidate")
    chain = fact.get("environmentChain")
    if not isinstance(signer, Mapping) or set(signer) != {
        "identity",
        "payloadType",
        "payload",
        "signature",
    }:
        raise PromotionEvidenceError(
            "PROMOTION.QUALIFICATION_INVALID", "signer envelope drifted"
        )
    try:
        _, issued_at = _timestamp(fact.get("issuedAt"), "qualification.issuedAt")
        _, expires_at = _timestamp(fact.get("expiresAt"), "qualification.expiresAt")
        signer_identity = _text(
            signer.get("identity"), "qualification.signer.identity"
        )
        signer_payload = _text(
            signer.get("payload"), "qualification.signer.payload"
        )
        signer_signature = _text(
            signer.get("signature"), "qualification.signer.signature"
        )
        signed_payload = base64.b64decode(signer_payload, validate=True)
    except (PromotionEvidenceError, TypeError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, PromotionEvidenceError) else str(exc)
        raise PromotionEvidenceError(
            "PROMOTION.QUALIFICATION_INVALID", detail
        ) from exc

    unsigned = dict(fact)
    unsigned.pop("qualificationId")
    unsigned.pop("signer")
    identity = dict(fact)
    qualification_id = identity.pop("qualificationId")
    candidate_id = candidate.get("candidateId") if isinstance(candidate, Mapping) else None
    impact_digest = fact.get("impactPlanDigest")
    valid = (
        fact.get("schema") == _QUALIFICATION_SCHEMA
        and fact.get("decision") == "qualified"
        and fact.get("devRef") == "refs/heads/dev1.0"
        and fact.get("devHead") == head
        and fact.get("devTree") == head_tree
        and isinstance(candidate, Mapping)
        and set(candidate) == {"candidateId", "commit", "tree"}
        and isinstance(candidate_id, str)
        and _DIGEST.fullmatch(candidate_id) is not None
        and candidate.get("commit") == head
        and candidate.get("tree") == head_tree
        and _valid_exact_identity(fact.get("publishResult"))
        and _valid_exact_identity(fact.get("publishAdmission"))
        and isinstance(chain, Mapping)
        and set(chain) == {"alpha", "beta", "gamma"}
        and all(_valid_exact_identity(chain.get(name)) for name in chain)
        and isinstance(impact_digest, str)
        and _DIGEST.fullmatch(impact_digest) is not None
        and bool(signer_identity)
        and signer.get("payloadType") == _QUALIFICATION_PAYLOAD_TYPE
        and bool(signer_signature)
        and signed_payload == canonical_bytes(unsigned)
        and issued_at <= promotion_time < expires_at
        and isinstance(qualification_id, str)
        and _DIGEST.fullmatch(qualification_id) is not None
        and qualification_id == digest(identity)
    )
    if not valid:
        raise PromotionEvidenceError(
            "PROMOTION.QUALIFICATION_INVALID",
            "qualification does not bind the current unexpired dev identity",
        )
    return fact, normalized


def create_promotion_admission(
    *,
    repository: Path,
    evidence_root: Path,
    qualification_ref: Mapping[str, str],
    head_sha: str,
    base_sha: str,
    synthetic_merge_sha: str,
    approval_fact_ref: Mapping[str, str],
    thread_fact_ref: Mapping[str, str],
    ruleset_fact_ref: Mapping[str, str],
    boundary_fact_ref: Mapping[str, str],
    required_evidence: Sequence[Mapping[str, str]],
    promotion_ready_at: str,
) -> Path:
    repository, root = repository.resolve(), evidence_root.resolve()
    head = _sha(head_sha, "headSha")
    base = _sha(base_sha, "baseSha")
    merge = _sha(synthetic_merge_sha, "syntheticMergeSha")
    if merge in {head, base}:
        raise PromotionEvidenceError(
            "PROMOTION.MERGE_INVALID",
            "synthetic merge must be distinct from head and base",
        )
    ready_text, ready_time = _timestamp(promotion_ready_at, "promotionReadyAt")
    if _git(repository, "rev-parse", "refs/heads/dev1.0") != head:
        raise PromotionEvidenceError(
            "PROMOTION.HEAD_DRIFT", "head is not current dev1.0"
        )
    if _git(repository, "rev-parse", "refs/heads/main") != base:
        raise PromotionEvidenceError("PROMOTION.BASE_DRIFT", "base is not current main")
    head_tree = _sha(
        _git(repository, "show", "-s", "--format=%T", head), "headTree"
    )
    parents = _git(repository, "show", "-s", "--format=%P", merge).split()
    if parents != [base, head]:
        raise PromotionEvidenceError(
            "PROMOTION.MERGE_INVALID",
            "synthetic merge parents must be base then head",
        )
    merge_tree = _sha(
        _git(repository, "show", "-s", "--format=%T", merge), "mergeTree"
    )
    authority: dict[str, dict[str, str]] = {}
    for name, exact in (
        ("approval", approval_fact_ref),
        ("threads", thread_fact_ref),
        ("ruleset", ruleset_fact_ref),
        ("changedBoundary", boundary_fact_ref),
    ):
        fact, normalized = _exact(root, exact, name)
        semantics = {
            "approval": (
                fact.get("decision") == "approved"
                and fact.get("commitSha") == head
                and isinstance(fact.get("approvalCount"), int)
                and not isinstance(fact.get("approvalCount"), bool)
                and fact.get("approvalCount", 0) >= 1
            ),
            "threads": (
                fact.get("commitSha") == head
                and fact.get("unresolvedCount") == 0
            ),
            "ruleset": (
                fact.get("commitSha") == head
                and fact.get("requiredCheck") == "03. Delivery Gate"
                and fact.get("requiredCheckEnforced") is True
                and fact.get("bypassActors") == []
            ),
            "changedBoundary": (
                fact.get("verifiedHeadSha") == head
                and fact.get("verifiedBaseSha") == base
                and fact.get("secretStatus") == "passed"
                and fact.get("generatedBoundaryStatus") == "passed"
            ),
        }
        if (
            fact.get("schema") != _AUTHORITY_SCHEMAS[name]
            or fact.get("status") != "passed"
            or fact.get("headSha") != head
            or fact.get("baseSha") != base
            or not semantics[name]
        ):
            raise PromotionEvidenceError(
                "PROMOTION.AUTHORITY_INVALID",
                f"{name} does not bind promotion range",
            )
        authority[name] = normalized
    _, qualification_exact = _qualification(
        root=root,
        exact=qualification_ref,
        head=head,
        head_tree=head_tree,
        promotion_time=ready_time,
    )
    evidence: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, exact in enumerate(required_evidence):
        fact, normalized = _exact(root, exact, f"requiredEvidence[{index}]")
        identity = (normalized["ref"], normalized["digest"])
        if identity in seen:
            raise PromotionEvidenceError(
                "PROMOTION.EVIDENCE_INVALID", "required evidence contains duplicates"
            )
        seen.add(identity)
        if (
            fact.get("schema") != _REQUIRED_EVIDENCE_SCHEMA
            or fact.get("status") != "passed"
            or fact.get("headSha") != head
            or fact.get("baseSha") != base
        ):
            raise PromotionEvidenceError(
                "PROMOTION.EVIDENCE_INVALID",
                "required evidence is not passed for promotion range",
            )
        evidence.append(normalized)
    if not evidence:
        raise PromotionEvidenceError(
            "PROMOTION.EVIDENCE_INVALID", "required evidence cannot be empty"
        )
    body: dict[str, Any] = {
        "schema": ADMISSION_SCHEMA,
        "decision": "admitted",
        "headRef": "refs/heads/dev1.0",
        "baseRef": "refs/heads/main",
        "headSha": head,
        "headTree": head_tree,
        "baseSha": base,
        "syntheticMergeSha": merge,
        "syntheticMergeTree": merge_tree,
        "qualification": qualification_exact,
        "authority": authority,
        "requiredEvidence": sorted(
            evidence, key=lambda item: (item["ref"], item["digest"])
        ),
        "changedPaths": _changed_paths(repository, base, head),
        "promotionReadyAt": ready_text,
    }
    body["admissionId"] = digest(body)
    return _write_once(
        root / "promotion" / "admissions" / head / f"{body['admissionId']}.json",
        body,
    )


def create_main_source_seal(
    *,
    repository: Path,
    evidence_root: Path,
    admission_ref: Mapping[str, str],
    main_sha: str,
    main_readback_at: str,
    admission_oci_ref: str,
    hosted_handoff_ref: Mapping[str, str],
) -> Path:
    repository, root = repository.resolve(), evidence_root.resolve()
    admission, exact = _exact(root, admission_ref, "promotionAdmission")
    if (
        admission.get("schema") != ADMISSION_SCHEMA
        or admission.get("decision") != "admitted"
        or admission.get("admissionId")
        != digest({key: value for key, value in admission.items() if key != "admissionId"})
    ):
        raise PromotionEvidenceError("PROMOTION.INVALID", "admission is invalid")
    main = _sha(main_sha, "mainSha")
    if _git(repository, "rev-parse", "refs/heads/main") != main:
        raise PromotionEvidenceError(
            "PROMOTION.MAIN_DRIFT", "main ref readback drifted"
        )
    main_tree = _sha(
        _git(repository, "show", "-s", "--format=%T", main), "mainTree"
    )
    if main_tree != admission.get("syntheticMergeTree"):
        raise PromotionEvidenceError(
            "PROMOTION.MAIN_TREE_DRIFT",
            "main tree differs from admitted synthetic merge tree",
        )
    parents = _git(repository, "show", "-s", "--format=%P", main).split()
    if parents != [admission.get("baseSha"), admission.get("headSha")]:
        raise PromotionEvidenceError(
            "PROMOTION.MAIN_TREE_DRIFT",
            "main commit parents differ from admitted synthetic merge",
        )
    ready_text, ready = _timestamp(
        admission.get("promotionReadyAt"), "promotionReadyAt"
    )
    readback_text, readback = _timestamp(main_readback_at, "mainReadbackAt")
    if readback < ready:
        raise PromotionEvidenceError(
            "PROMOTION.TIMING_INVALID", "main readback precedes promotion readiness"
        )
    body: dict[str, Any] = {
        "schema": SEAL_SCHEMA,
        "sourceStatus": "source-admitted",
        "releaseStatus": "not_selected",
        "mainRef": "refs/heads/main",
        "mainSha": main,
        "mainTree": main_tree,
        "promotionAdmission": exact,
        "sourceHeadSha": admission["headSha"],
        "promotionReadyAt": ready_text,
        "mainReadbackAt": readback_text,
        "durationSeconds": int((readback - ready).total_seconds()),
    }
    exact_oci = _exact_oci_ref(admission_oci_ref, "promotionAdmissionOciRef")
    hosted_handoff, hosted_exact = _exact(
        root, hosted_handoff_ref, "hostedPromotionHandoff"
    )
    if (
        hosted_handoff.get("schema") != HANDOFF_SCHEMA
        or hosted_handoff.get("promotionAdmissionRef") != exact_oci
        or hosted_handoff.get("admissionBytesDigest") != exact["digest"]
        or hosted_handoff.get("headSha") != admission.get("headSha")
        or hosted_handoff.get("baseSha") != admission.get("baseSha")
        or hosted_handoff.get("syntheticMergeTree")
        != admission.get("syntheticMergeTree")
    ):
        raise PromotionEvidenceError(
            "PROMOTION.HANDOFF_INVALID",
            "hosted handoff does not bind exact materialized admission and merge",
        )
    body["promotionAdmissionOciRef"] = exact_oci
    body["hostedPromotionHandoff"] = hosted_exact
    body["sealId"] = digest(body)
    return _write_once(
        root / "promotion" / "main-source-seals" / main / f"{body['sealId']}.json",
        body,
    )

_EXACT_OCI = re.compile(
    r"^(?P<repository>ghcr\.io/[a-z0-9._/-]+)@(?P<digest>sha256:[0-9a-f]{64})$"
)
_OCI_REPOSITORY = re.compile(r"^ghcr\.io/[a-z0-9._/-]+$")


def _exact_oci_ref(value: object, field: str) -> str:
    text = _text(value, field)
    if _EXACT_OCI.fullmatch(text) is None:
        raise PromotionEvidenceError(
            "PROMOTION.HANDOFF_INVALID", f"{field} must be exact GHCR @sha256"
        )
    return text


def create_promotion_handoff(
    *,
    repository: str,
    pull_request_number: int,
    head_sha: str,
    base_sha: str,
    synthetic_merge_sha: str,
    synthetic_merge_tree: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    workflow_repository: str,
    workflow_head_sha: str,
    workflow_actor_login: str,
    workflow_actor_id: int,
    promotion_admission_ref: str,
    admission_bytes_digest: str,
    created_at: str,
) -> dict[str, Any]:
    repo = _text(repository, "repository")
    if repo.count("/") != 1 or repo.casefold() != repo:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "repository is invalid")
    body: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "repository": repo,
        "pullRequestNumber": _positive_int(pull_request_number, "pullRequestNumber"),
        "headSha": _sha(head_sha, "headSha"),
        "baseSha": _sha(base_sha, "baseSha"),
        "syntheticMergeSha": _sha(synthetic_merge_sha, "syntheticMergeSha"),
        "syntheticMergeTree": _sha(synthetic_merge_tree, "syntheticMergeTree"),
        "workflowRunId": _positive_int(workflow_run_id, "workflowRunId"),
        "workflowRunAttempt": _positive_int(workflow_run_attempt, "workflowRunAttempt"),
        "workflowRepository": _text(workflow_repository, "workflowRepository"),
        "workflowHeadSha": _sha(workflow_head_sha, "workflowHeadSha"),
        "workflowActor": {
            "login": _text(workflow_actor_login, "workflowActor.login"),
            "id": _positive_int(workflow_actor_id, "workflowActor.id"),
        },
        "handoffContext": HANDOFF_CONTEXT,
        "promotionAdmissionRef": _exact_oci_ref(
            promotion_admission_ref, "promotionAdmissionRef"
        ),
        "admissionBytesDigest": _text(
            admission_bytes_digest, "admissionBytesDigest"
        ),
        "createdAt": _timestamp(created_at, "createdAt")[0],
    }
    if body["workflowRepository"] != repo or body["workflowHeadSha"] != body["headSha"]:
        raise PromotionEvidenceError(
            "PROMOTION.HANDOFF_INVALID", "workflow identity differs from promotion head"
        )
    if _DIGEST.fullmatch(body["admissionBytesDigest"]) is None:
        raise PromotionEvidenceError(
            "PROMOTION.HANDOFF_INVALID", "admissionBytesDigest is invalid"
        )
    body["recordId"] = digest(body)
    return body


def validate_hosted_promotion_handoff(
    *,
    check_run: Mapping[str, Any], workflow_run: Mapping[str, Any], repository: str,
    pull_request_number: int, head_sha: str, base_sha: str,
    synthetic_merge_tree: str, expected_context: str,
    expected_app_slug: str, expected_app_id: int,
    expected_workflow_repository: str, verified_at: str,
    max_age_seconds: int = _MAX_HANDOFF_AGE_SECONDS,
) -> dict[str, Any]:
    if not isinstance(check_run, Mapping) or not isinstance(workflow_run, Mapping):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "hosted records are invalid")
    context = _text(expected_context, "expectedContext")
    app_slug = _text(expected_app_slug, "expectedAppSlug")
    app_id = _positive_int(expected_app_id, "expectedAppId")
    app, output = check_run.get("app"), check_run.get("output")
    if (
        context != HANDOFF_CONTEXT or check_run.get("name") != context
        or check_run.get("status") != "completed"
        or check_run.get("conclusion") != "success"
        or check_run.get("head_sha") != head_sha
    ):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "hosted check binding is invalid")
    if not isinstance(app, Mapping) or (app.get("id"), app.get("slug")) != (app_id, app_slug):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_AUTHORITY_INVALID", "check App is not trusted")
    if not isinstance(output, Mapping) or output.get("title") != HANDOFF_SCHEMA:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "check output is invalid")
    try:
        encoded = _text(output.get("summary"), "checkRun.output.summary")
        decoded = base64.b64decode(encoded, validate=True)
        record = json.loads(decoded)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "check record is invalid") from exc
    if not isinstance(record, dict) or decoded != canonical_bytes(record):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "check record is not canonical")
    repo_for_url = _text(repository, "repository")
    head_for_url = _sha(head_sha, "headSha")
    expected_statuses_url = (
        f"https://api.github.com/repos/{repo_for_url}/statuses/{head_for_url}"
    )
    if check_run.get("statuses_url") != expected_statuses_url:
        raise PromotionEvidenceError(
            "PROMOTION.HANDOFF_BINDING_INVALID", "check repository/statuses URL drifted"
        )
    identity = {key: value for key, value in record.items() if key != "recordId"}
    if (
        record.get("schema") != HANDOFF_SCHEMA
        or record.get("handoffContext") != context
        or record.get("recordId") != digest(identity)
        or check_run.get("external_id") != record.get("recordId")
    ):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "check identity drifted")
    expected = {
        "repository": _text(repository, "repository"),
        "pullRequestNumber": _positive_int(pull_request_number, "pullRequestNumber"),
        "headSha": _sha(head_sha, "headSha"), "baseSha": _sha(base_sha, "baseSha"),
        "syntheticMergeTree": _sha(synthetic_merge_tree, "syntheticMergeTree"),
        "workflowRepository": _text(expected_workflow_repository, "workflowRepository"),
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_BINDING_INVALID", "promotion binding drifted")
    started_text, started = _timestamp(check_run.get("started_at"), "checkRun.startedAt")
    completed_text, _ = _timestamp(check_run.get("completed_at"), "checkRun.completedAt")
    created_text, created = _timestamp(record.get("createdAt"), "record.createdAt")
    _, verified = _timestamp(verified_at, "verifiedAt")
    if started_text != completed_text or created_text != started_text:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_REPLACED", "check timing drifted")
    if not 0 <= int((verified - started).total_seconds()) <= max_age_seconds or created > verified:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_STALE", "check is outside promotion window")
    actor, actual_actor = record.get("workflowActor"), workflow_run.get("actor")
    workflow_repo, head_repo = workflow_run.get("repository"), workflow_run.get("head_repository")
    prs = workflow_run.get("pull_requests")
    matching_prs = [item for item in prs if isinstance(item, Mapping) and item.get("number") == expected["pullRequestNumber"]] if isinstance(prs, list) else []
    if (
        workflow_run.get("id") != record.get("workflowRunId")
        or workflow_run.get("run_attempt") != record.get("workflowRunAttempt")
        or workflow_run.get("event") not in _HANDOFF_WORKFLOW_EVENTS
        or workflow_run.get("path") != ".github/workflows/delivery-gate.yml"
        or workflow_run.get("head_sha") != expected["headSha"]
        or workflow_run.get("html_url")
        != f"https://github.com/{expected['repository']}/actions/runs/{record['workflowRunId']}"
        or record.get("workflowHeadSha") != expected["headSha"]
        or not isinstance(workflow_repo, Mapping) or workflow_repo.get("full_name") != expected["workflowRepository"]
        or not isinstance(head_repo, Mapping) or head_repo.get("full_name") != expected["repository"]
        or not isinstance(actor, Mapping) or not isinstance(actual_actor, Mapping)
        or (actor.get("login"), actor.get("id")) != (actual_actor.get("login"), actual_actor.get("id"))
        or len(matching_prs) != 1
    ):
        raise PromotionEvidenceError("PROMOTION.HANDOFF_ACTOR_INVALID", "workflow identity drifted")
    exact_ref = _exact_oci_ref(record.get("promotionAdmissionRef"), "promotionAdmissionRef")
    admission_digest = _text(record.get("admissionBytesDigest"), "admissionBytesDigest")
    if _DIGEST.fullmatch(admission_digest) is None:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_INVALID", "admission digest is invalid")
    expected_url = f"https://github.com/{expected['repository']}/actions/runs/{record['workflowRunId']}/attempts/{record['workflowRunAttempt']}"
    if check_run.get("details_url") != expected_url:
        raise PromotionEvidenceError("PROMOTION.HANDOFF_BINDING_INVALID", "workflow URL drifted")
    return {
        "schema": HANDOFF_SCHEMA, "recordId": record["recordId"],
        "checkRunId": _positive_int(check_run.get("id"), "checkRun.id"),
        "checkRunNodeId": _text(check_run.get("node_id"), "checkRun.nodeId"),
        "context": context, "app": {"slug": app_slug, "id": app_id},
        "workflowActor": {"login": _text(actual_actor.get("login"), "actor.login"), "id": _positive_int(actual_actor.get("id"), "actor.id")},
        "createdAt": started_text, **expected,
        "syntheticMergeSha": _sha(record.get("syntheticMergeSha"), "syntheticMergeSha"),
        "workflowRunId": _positive_int(record.get("workflowRunId"), "workflowRunId"),
        "workflowRunAttempt": _positive_int(record.get("workflowRunAttempt"), "workflowRunAttempt"),
        "workflowHeadSha": expected["headSha"],
        "promotionAdmissionRef": exact_ref, "admissionBytesDigest": admission_digest,
    }


def materialize_oci_fact(*, exact_ref: str, output_file: Path) -> Path:
    """Pull one exact generic OCI artifact containing only ``fact.json``."""
    if _EXACT_OCI.fullmatch(_text(exact_ref, "exactRef")) is None:
        raise PromotionEvidenceError(
            "PROMOTION.OCI_INVALID", "evidence ref must be exact GHCR @sha256"
        )
    output = output_file.expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise PromotionEvidenceError(
            "PROMOTION.CREATE_CONFLICT", "materialized fact destination already exists"
        )
    with tempfile.TemporaryDirectory(prefix="qwq-promotion-fact-") as directory:
        stage = Path(directory)
        completed = subprocess.run(
            ["oras", "pull", "--output", str(stage), exact_ref],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise PromotionEvidenceError(
                "PROMOTION.OCI_UNAVAILABLE",
                " ".join((completed.stderr or completed.stdout).split()),
            )
        entries = sorted(stage.rglob("*"))
        files = [entry for entry in entries if entry.is_file() and not entry.is_symlink()]
        if files != [stage / "fact.json"] or any(entry.is_symlink() for entry in entries):
            raise PromotionEvidenceError(
                "PROMOTION.OCI_INVALID", "evidence artifact must contain only fact.json"
            )
        try:
            value = json.loads(files[0].read_bytes())
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PromotionEvidenceError(
                "PROMOTION.OCI_INVALID", "fact.json is not readable JSON"
            ) from exc
        if not isinstance(value, dict) or files[0].read_bytes() != canonical_bytes(value) + b"\n":
            raise PromotionEvidenceError(
                "PROMOTION.OCI_INVALID", "fact.json bytes are not canonical"
            )
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(files[0], output)
    return output


def publish_oci_fact(*, fact_file: Path, repository: str, transport_tag: str) -> str:
    """Publish canonical fact bytes and return the registry-provided exact OCI ref."""
    source = fact_file.expanduser().resolve()
    if _OCI_REPOSITORY.fullmatch(_text(repository, "repository")) is None:
        raise PromotionEvidenceError(
            "PROMOTION.OCI_INVALID", "repository must be canonical GHCR"
        )
    tag = _text(transport_tag, "transportTag")
    if any(character.isspace() for character in tag) or ":" in tag or "/" in tag:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "transport tag is invalid")
    if source.is_symlink() or not source.is_file():
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "fact file is missing")
    try:
        value = json.loads(source.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "fact file is invalid JSON") from exc
    if not isinstance(value, dict) or source.read_bytes() != canonical_bytes(value) + b"\n":
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "fact file is not canonical")
    with tempfile.TemporaryDirectory(prefix="qwq-promotion-publish-") as directory:
        stage = Path(directory)
        shutil.copyfile(source, stage / "fact.json")
        completed = subprocess.run(
            [
                "oras", "push", "--no-tty", "--format", "json",
                "--artifact-type", "application/vnd.quwoquan.promotion-fact.v1",
                f"{repository}:{tag}",
                "fact.json:application/vnd.quwoquan.promotion-fact.v1+json",
            ],
            cwd=stage,
            text=True,
            capture_output=True,
            check=False,
        )
    if completed.returncode:
        raise PromotionEvidenceError(
            "PROMOTION.OCI_UNAVAILABLE", " ".join(completed.stderr.split())
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PromotionEvidenceError(
            "PROMOTION.OCI_INVALID", "ORAS did not return JSON"
        ) from exc
    exact_ref = str(payload.get("reference") or "") if isinstance(payload, dict) else ""
    match = _EXACT_OCI.fullmatch(exact_ref)
    if match is None or match.group("repository") != repository:
        raise PromotionEvidenceError(
            "PROMOTION.OCI_INVALID", "ORAS did not return the expected exact reference"
        )
    return exact_ref


def _split_exact(value: str, field: str) -> dict[str, str]:
    try:
        ref, exact_digest = value.split("=", 1)
    except ValueError as exc:
        raise PromotionEvidenceError(
            "PROMOTION.INVALID", f"{field} must be ref=digest"
        ) from exc
    return {"ref": ref, "digest": exact_digest}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    materialize = subparsers.add_parser("materialize-oci")
    materialize.add_argument("--ref", required=True)
    materialize.add_argument("--output-file", required=True, type=Path)
    publish = subparsers.add_parser("publish-oci")
    publish.add_argument("--fact-file", required=True, type=Path)
    publish.add_argument("--repository", required=True)
    publish.add_argument("--transport-tag", required=True)
    handoff = subparsers.add_parser("create-handoff")
    for name in (
        "repository", "head-sha", "base-sha", "synthetic-merge-sha",
        "synthetic-merge-tree", "workflow-repository", "workflow-head-sha",
        "promotion-admission-ref", "admission-bytes-digest", "created-at",
    ):
        handoff.add_argument(f"--{name}", required=True)
    handoff.add_argument("--pull-request-number", required=True, type=int)
    handoff.add_argument("--workflow-run-id", required=True, type=int)
    handoff.add_argument("--workflow-run-attempt", required=True, type=int)
    handoff.add_argument("--workflow-actor-login", required=True)
    handoff.add_argument("--workflow-actor-id", required=True, type=int)
    handoff.add_argument("--output-file", required=True, type=Path)
    hosted = subparsers.add_parser("validate-hosted-handoff")
    hosted.add_argument("--check-run-file", required=True, type=Path)
    hosted.add_argument("--workflow-run-file", required=True, type=Path)
    hosted.add_argument("--repository", required=True)
    hosted.add_argument("--pull-request-number", required=True, type=int)
    hosted.add_argument("--head-sha", required=True)
    hosted.add_argument("--base-sha", required=True)
    hosted.add_argument("--synthetic-merge-tree", required=True)
    hosted.add_argument("--expected-context", required=True)
    hosted.add_argument("--expected-app-slug", required=True)
    hosted.add_argument("--expected-app-id", required=True, type=int)
    hosted.add_argument("--expected-workflow-repository", required=True)
    hosted.add_argument("--verified-at", required=True)
    hosted.add_argument("--output-file", required=True, type=Path)
    seal = subparsers.add_parser("main-seal")
    seal.add_argument("--repository", required=True, type=Path)
    seal.add_argument("--evidence-root", required=True, type=Path)
    seal.add_argument("--admission", required=True)
    seal.add_argument("--admission-oci-ref", required=True)
    seal.add_argument("--hosted-handoff", required=True)
    seal.add_argument("--main-sha", required=True)
    seal.add_argument("--main-readback-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "materialize-oci":
            result: object = {"path": str(materialize_oci_fact(exact_ref=args.ref, output_file=args.output_file))}
        elif args.command == "publish-oci":
            result = {
                "exactRef": publish_oci_fact(
                    fact_file=args.fact_file,
                    repository=args.repository,
                    transport_tag=args.transport_tag,
                )
            }
        elif args.command == "create-handoff":
            record = create_promotion_handoff(
                repository=args.repository,
                pull_request_number=args.pull_request_number,
                head_sha=args.head_sha,
                base_sha=args.base_sha,
                synthetic_merge_tree=args.synthetic_merge_tree,
                workflow_run_id=args.workflow_run_id,
                workflow_run_attempt=args.workflow_run_attempt,
                workflow_repository=args.workflow_repository,
                workflow_head_sha=args.workflow_head_sha,
                workflow_actor_login=args.workflow_actor_login,
                workflow_actor_id=args.workflow_actor_id,
                promotion_admission_ref=args.promotion_admission_ref,
                admission_bytes_digest=args.admission_bytes_digest,
                created_at=args.created_at,
            )
            output = args.output_file.expanduser().resolve()
            _write_once(output, record)
            result = {"path": str(output), "recordId": record["recordId"]}
        elif args.command == "validate-hosted-handoff":
            try:
                check_run = json.loads(args.check_run_file.read_bytes())
                workflow_run = json.loads(args.workflow_run_file.read_bytes())
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise PromotionEvidenceError(
                    "PROMOTION.HANDOFF_INVALID", "hosted API file is invalid JSON"
                ) from exc
            hosted = validate_hosted_promotion_handoff(
                check_run=check_run,
                workflow_run=workflow_run,
                repository=args.repository,
                pull_request_number=args.pull_request_number,
                head_sha=args.head_sha,
                base_sha=args.base_sha,
                synthetic_merge_tree=args.synthetic_merge_tree,
                expected_context=args.expected_context,
                expected_app_slug=args.expected_app_slug,
                expected_app_id=args.expected_app_id,
                expected_workflow_repository=args.expected_workflow_repository,
                verified_at=args.verified_at,
            )
            output = args.output_file.expanduser().resolve()
            _write_once(output, hosted)
            result = {
                "path": str(output),
                "exactRef": hosted["promotionAdmissionRef"],
                "admissionBytesDigest": hosted["admissionBytesDigest"],
            }
        else:
            admission = _split_exact(args.admission, "admission")
            hosted = _split_exact(args.hosted_handoff, "hostedHandoff")
            path = create_main_source_seal(
                repository=args.repository,
                evidence_root=args.evidence_root,
                admission_ref=admission,
                main_sha=args.main_sha,
                main_readback_at=args.main_readback_at,
                admission_oci_ref=args.admission_oci_ref,
                hosted_handoff_ref=hosted,
            )
            result = {
                "ref": path.relative_to(args.evidence_root.resolve()).as_posix(),
                "digest": digest(path),
            }
    except (OSError, PromotionEvidenceError) as error:
        code = error.code if isinstance(error, PromotionEvidenceError) else "PROMOTION.IO_ERROR"
        print(json.dumps({"terminal": "GATE_BLOCK", "code": code, "detail": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
