from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import error, request

from .deployment_candidate_manifest import load_candidate_manifest
from .local_environment_auth import (
    LocalAcceptanceSession,
    mint_local_product_ops_operator_token,
)
from .output_paths import active_deployment_candidate, env_runs_root, output_root
from .app_content_uat_plan import build_app_content_uat_plan, load_release_uat_sample_plan
from .test_live_content_binding import load_test_live_content_binding


COLLECTION_PATH = "/control-plane/product/recommendation/premium-pool"
PREMIUM_FEED_PATH = "/content/feed?sort=recommend&channelId=premium_stream&limit=20"


class PremiumPoolReleaseError(RuntimeError):
    pass


def _require_sha256_digest(value: object, *, label: str) -> str:
    digest = str(value or "").strip()
    if (
        len(digest) != 71
        or not digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in digest[7:])
    ):
        raise PremiumPoolReleaseError(
            f"{label} must be sha256:<64 lowercase hex>"
        )
    return digest


def _load_release_sample_plan_documents_from_attestation(
    *,
    release_id: str,
    manifest_digest: str,
    attestation_ref: object,
    attestation_digest: object,
) -> dict[str, Any]:
    ref = str(attestation_ref or "").strip()
    digest = _require_sha256_digest(
        attestation_digest, label="release attestation digest"
    )
    source = Path(ref).expanduser()
    if not ref or source.is_symlink():
        raise PremiumPoolReleaseError("release attestation reference is unsafe")
    try:
        path = source.resolve(strict=True)
        raw = path.read_bytes()
        attestation = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PremiumPoolReleaseError("release attestation is unreadable") from exc
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise PremiumPoolReleaseError("release attestation digest drifted")
    if (
        not isinstance(attestation, Mapping)
        or attestation.get("schema") != "quwoquan_data.release_attestation"
        or attestation.get("sourceOwner") != "qwq_data"
        or attestation.get("releaseKind") != "content"
        or attestation.get("releaseId") != release_id
        or attestation.get("payloadSha256") != manifest_digest
        or path.name != "release.json"
        or path.parent.name != "attestations"
    ):
        raise PremiumPoolReleaseError("release attestation identity drifted")
    release_root = path.parents[1]
    header_path = release_root / "payload/release.json"
    if header_path.is_symlink():
        raise PremiumPoolReleaseError("release header is unsafe")
    try:
        header = json.loads(header_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PremiumPoolReleaseError("release header is unreadable") from exc
    if not isinstance(header, Mapping):
        raise PremiumPoolReleaseError("release header must be a JSON object")
    try:
        sample_plan, _, sample_plan_digest = load_release_uat_sample_plan(
            release_root=header_path.parent, release_header=header
        )
        if (
            sample_plan.get("schema") != "quwoquan_data.release_uat_sample_plan"
            or sample_plan.get("releaseId") != release_id
        ):
            raise ValueError("ReleaseUatSamplePlan identity drifted")
        return dict(header), sample_plan, sample_plan_digest
    except (OSError, ValueError) as exc:
        raise PremiumPoolReleaseError(
            "release UAT sample plan binding is invalid"
        ) from exc


def _load_release_sample_plan_from_attestation(
    *,
    release_id: str,
    manifest_digest: str,
    readiness: Mapping[str, Any],
    attestation_ref: object,
    attestation_digest: object,
) -> dict[str, Any]:
    header, sample_plan, sample_plan_digest = (
        _load_release_sample_plan_documents_from_attestation(
            release_id=release_id,
            manifest_digest=manifest_digest,
            attestation_ref=attestation_ref,
            attestation_digest=attestation_digest,
        )
    )
    try:
        return build_app_content_uat_plan(
            readiness,
            release_header=header,
            release_uat_sample_plan=sample_plan,
            release_uat_sample_plan_digest=sample_plan_digest,
            release_payload_sha256=manifest_digest,
        )
    except ValueError as exc:
        raise PremiumPoolReleaseError(
            "release UAT sample plan binding is invalid"
        ) from exc


def _required_video_sample(app_uat_plan: object) -> str:
    if not isinstance(app_uat_plan, Mapping):
        raise PremiumPoolReleaseError("ReleaseUatSamplePlan derived App UAT plan is missing")
    samples = app_uat_plan.get("orderedSamples")
    if not isinstance(samples, list):
        raise PremiumPoolReleaseError("ReleaseUatSamplePlan ordered samples are missing")
    video_ids = [
        str(sample.get("objectId") or "").strip()
        for sample in samples
        if isinstance(sample, Mapping) and sample.get("carrier") == "video"
    ]
    if not video_ids or not video_ids[0]:
        raise PremiumPoolReleaseError(
            "ReleaseUatSamplePlan has no required video sample"
        )
    return video_ids[0]


def _required_raw_video_sample(sample_plan: Mapping[str, Any]) -> str:
    samples = sample_plan.get("samples")
    if not isinstance(samples, list):
        raise PremiumPoolReleaseError("ReleaseUatSamplePlan samples are missing")
    for sample in samples:
        if isinstance(sample, Mapping) and sample.get("carrier") == "video":
            video_id = str(sample.get("objectId") or "").strip()
            if video_id:
                return video_id
    raise PremiumPoolReleaseError("ReleaseUatSamplePlan has no required video sample")


@dataclass(frozen=True)
class PremiumPoolCandidateBinding:
    environment: str
    target: str
    baseline_id: str
    package_digest: str
    source_revision: str
    release_id: str
    manifest_digest: str
    import_run_id: str
    verify_run_id: str
    content_id: str
    readiness_receipt_ref: str


@dataclass(frozen=True)
class PremiumPoolTestLiveBinding:
    environment: str
    target: str
    release_id: str
    manifest_digest: str
    import_run_id: str
    verify_run_id: str
    content_id: str
    readiness_phase: str
    readiness_receipt_ref: str
    readiness_receipt_digest: str
    startup_attempt_id: str
    runtime_identity: Mapping[str, str]


@dataclass(frozen=True)
class PremiumPoolBootstrapBinding:
    """首次激活绑定：只以 `apply` 的导入证据为输入。

    与 candidate 绑定的本质区别是没有 `verify_run_id`——这条路径存在的前提正是
    consumer 档校验尚未、也无法通过。
    """

    environment: str
    target: str
    baseline_id: str
    package_digest: str
    source_revision: str
    release_id: str
    manifest_digest: str
    import_run_id: str
    content_id: str
    import_report_ref: str


PremiumPoolBinding = (
    PremiumPoolCandidateBinding
    | PremiumPoolTestLiveBinding
    | PremiumPoolBootstrapBinding
)


def load_premium_pool_candidate_binding(
    *,
    environment: str,
    target: str,
    readiness_receipt: str | Path,
    content_id: str,
) -> PremiumPoolCandidateBinding:
    active = active_deployment_candidate(target)
    if not isinstance(active, dict):
        raise PremiumPoolReleaseError(
            "GATE_BLOCK: active immutable candidate is required"
        )
    baseline_id = str(active.get("baselineId") or "").strip()
    manifest = load_candidate_manifest(
        environment,
        target,
        baseline_id,
        require_full=True,
    )
    receipt_path = Path(readiness_receipt).expanduser().resolve()
    receipt_root = env_runs_root(environment).resolve()
    try:
        receipt_ref = str(receipt_path.relative_to(receipt_root))
    except ValueError as exc:
        raise PremiumPoolReleaseError(
            "readiness receipt must belong to the selected environment"
        ) from exc
    try:
        readiness = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PremiumPoolReleaseError("readiness receipt is unreadable") from exc
    if (
        not isinstance(readiness, dict)
        or readiness.get("schema") != "quwoquan_data.environment_release_readiness"
        or readiness.get("environment") != environment
        or readiness.get("passed") is not True
        or readiness.get("readinessPhase") not in {"consumer", "commercial"}
    ):
        raise PremiumPoolReleaseError(
            "readiness receipt is not a passed canonical consumer receipt"
        )
    release_binding = manifest.get("release")
    candidate_release = (
        release_binding.get("candidate") if isinstance(release_binding, dict) else None
    )
    if not isinstance(candidate_release, dict):
        raise PremiumPoolReleaseError("active candidate has no release binding")
    release_id = str(readiness.get("releaseId") or "").strip()
    manifest_digest = str(readiness.get("manifestDigest") or "").strip()
    if (
        release_id != candidate_release.get("releaseId")
        or manifest_digest != candidate_release.get("releaseDigest")
    ):
        raise PremiumPoolReleaseError(
            "readiness receipt does not match the active candidate release"
        )
    app_uat_plan = _load_release_sample_plan_from_attestation(
        release_id=release_id,
        manifest_digest=manifest_digest,
        readiness=readiness,
        attestation_ref=candidate_release.get("attestationRef"),
        attestation_digest=candidate_release.get("attestationDigest"),
    )
    video_work_id = _required_video_sample(app_uat_plan)
    canonical_content_id = str(content_id or "").strip()
    if not canonical_content_id or canonical_content_id != video_work_id:
        raise PremiumPoolReleaseError(
            "contentId must be the exact ReleaseUatSamplePlan video sample"
        )
    import_run_id = str(readiness.get("importRunId") or "").strip()
    verify_run_id = str(readiness.get("verifyRunId") or "").strip()
    if not import_run_id or not verify_run_id:
        raise PremiumPoolReleaseError(
            "readiness receipt lacks importRunId or verifyRunId"
        )
    return PremiumPoolCandidateBinding(
        environment=environment,
        target=target,
        baseline_id=baseline_id,
        package_digest=str(manifest.get("packageDigest") or "").strip(),
        source_revision=str(manifest.get("sourceRevision") or "").strip(),
        release_id=release_id,
        manifest_digest=manifest_digest,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        content_id=canonical_content_id,
        readiness_receipt_ref=receipt_ref,
    )


def load_premium_pool_bootstrap_binding(
    *,
    environment: str,
    target: str,
    import_report: str | Path,
    content_id: str,
    pool_is_empty: bool,
) -> PremiumPoolBootstrapBinding:
    """Bind the first PremiumPoolEntry of an environment to its import evidence.

    `immutable-candidate` 要求一份已通过的 consumer 档收据，而该档校验把
    「`premium_stream` 非空」当作通过条件，因此空池环境无法自举。这条路径只在
    池确实为空时开放，且不放宽 release 绑定：内容必须是本次导入落库的视频。
    """

    if not pool_is_empty:
        raise PremiumPoolReleaseError(
            "environment already has premium pool entries; "
            "use the consumer readiness receipt instead"
        )
    active = active_deployment_candidate(target)
    if not isinstance(active, dict):
        raise PremiumPoolReleaseError(
            "GATE_BLOCK: active immutable candidate is required"
        )
    baseline_id = str(active.get("baselineId") or "").strip()
    manifest = load_candidate_manifest(
        environment,
        target,
        baseline_id,
        require_full=True,
    )
    report_path = Path(import_report).expanduser().resolve()
    report_root = env_runs_root(environment).resolve()
    try:
        report_ref = str(report_path.relative_to(report_root))
    except ValueError as exc:
        raise PremiumPoolReleaseError(
            "import report must belong to the selected environment"
        ) from exc
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PremiumPoolReleaseError("import report is unreadable") from exc
    if (
        not isinstance(report, dict)
        or report.get("schema") != "quwoquan.content_import_report"
        or report.get("environment") != environment
        or report.get("status") != "imported"
    ):
        raise PremiumPoolReleaseError(
            "import report is not a passed canonical content import report"
        )
    release_binding = manifest.get("release")
    candidate_release = (
        release_binding.get("candidate") if isinstance(release_binding, dict) else None
    )
    if not isinstance(candidate_release, dict):
        raise PremiumPoolReleaseError("active candidate has no release binding")
    release_id = str(report.get("releaseId") or "").strip()
    manifest_digest = str(report.get("manifestDigest") or "").strip()
    if (
        release_id != candidate_release.get("releaseId")
        or manifest_digest != candidate_release.get("releaseDigest")
    ):
        raise PremiumPoolReleaseError(
            "import report does not match the active candidate release"
        )
    _header, sample_plan, _sample_plan_digest = (
        _load_release_sample_plan_documents_from_attestation(
            release_id=release_id,
            manifest_digest=manifest_digest,
            attestation_ref=candidate_release.get("attestationRef"),
            attestation_digest=candidate_release.get("attestationDigest"),
        )
    )
    video_work_id = _required_raw_video_sample(sample_plan)
    canonical_content_id = str(content_id or "").strip()
    if not canonical_content_id or canonical_content_id != video_work_id:
        raise PremiumPoolReleaseError(
            "contentId must be the exact ReleaseUatSamplePlan video sample"
        )
    imported_video_ids = {
        str(row.get("postId") or "").strip()
        for row in report.get("postBindings") or []
        if isinstance(row, dict)
        and row.get("contentType") == "video"
        and str(row.get("postId") or "").strip()
    }
    if canonical_content_id not in imported_video_ids:
        raise PremiumPoolReleaseError(
            "ReleaseUatSamplePlan video sample is absent from the import report"
        )
    return PremiumPoolBootstrapBinding(
        environment=environment,
        target=target,
        baseline_id=baseline_id,
        package_digest=str(manifest.get("packageDigest") or "").strip(),
        source_revision=str(manifest.get("sourceRevision") or "").strip(),
        release_id=release_id,
        manifest_digest=manifest_digest,
        import_run_id=report_path.parent.name,
        content_id=canonical_content_id,
        import_report_ref=report_ref,
    )


def premium_pool_is_empty(*, api_base_url: str, ssl_cafile: str) -> bool:
    """Read the premium projection to decide whether a first activation is due.

    判定只读内容面，因此不需要运维凭据——这与 readback 的取证口径一致。
    """

    payload = _request_json(
        api_base_url.rstrip("/") + PREMIUM_FEED_PATH,
        method="GET",
        token="",
        body=None,
        headers={"X-Client-Session-Id": "premium-bootstrap-probe"},
        ssl_cafile=ssl_cafile,
        timeout_seconds=5.0,
    )
    return not [
        item
        for item in payload.get("items") or []
        if isinstance(item, dict)
        and str(item.get("id") or item.get("postId") or "").strip()
    ]


def load_premium_pool_test_live_binding(
    *,
    environment: str,
    target: str,
    readiness_receipt: str | Path,
    content_id: str,
) -> PremiumPoolTestLiveBinding:
    """Bind PremiumPoolEntry to the exact current mutable content evidence."""

    if environment not in {"alpha", "beta", "gamma"} or target != f"{environment}-local":
        raise PremiumPoolReleaseError(
            "test-live premium pool binding requires an exact Alpha/Beta/Gamma local target"
        )
    try:
        content_binding = load_test_live_content_binding(target)
    except (OSError, ValueError) as exc:
        raise PremiumPoolReleaseError(
            "current test-live content binding is invalid"
        ) from exc
    if not isinstance(content_binding, dict):
        raise PremiumPoolReleaseError(
            "current test-live content binding is required"
        )
    if (
        content_binding.get("launchPolicy") != "test_live"
        or content_binding.get("nonPromotable") is not True
        or content_binding.get("contentBindingState") != "bound"
        or content_binding.get("retentionClass") != "run_bound"
        or content_binding.get("environment") != environment
        or content_binding.get("target") != target
    ):
        raise PremiumPoolReleaseError(
            "current test-live content binding identity mismatch"
        )

    attempt_id = str(content_binding.get("startupAttemptId") or "").strip()
    runtime_identity = content_binding.get("startupIdentity")
    if not attempt_id or not isinstance(runtime_identity, Mapping):
        raise PremiumPoolReleaseError(
            "current test-live content binding is partial"
        )
    canonical_runtime_identity = {
        str(key): str(value or "").strip()
        for key, value in runtime_identity.items()
    }
    for field in (
        "mutableStateDigest",
        "configurationDigest",
        "providerRuntimeDigest",
    ):
        _require_sha256_digest(
            canonical_runtime_identity.get(field),
            label=f"test-live runtime {field}",
        )

    receipt_ref = str(content_binding.get("readinessReceiptRef") or "").strip()
    receipt_digest = _require_sha256_digest(
        content_binding.get("readinessReceiptDigest"),
        label="test-live readiness receipt",
    )
    relative_receipt_path = Path(receipt_ref)
    if (
        not receipt_ref
        or relative_receipt_path.is_absolute()
        or ".." in relative_receipt_path.parts
    ):
        raise PremiumPoolReleaseError(
            "test-live readiness receipt reference is not canonical"
        )
    expected_receipt_path = Path(
        os.path.abspath(output_root() / receipt_ref)
    )
    supplied_receipt_path = Path(
        os.path.abspath(Path(readiness_receipt).expanduser())
    )
    if supplied_receipt_path != expected_receipt_path:
        raise PremiumPoolReleaseError(
            "readiness receipt does not match the current test-live content binding"
        )
    if supplied_receipt_path.is_symlink():
        raise PremiumPoolReleaseError(
            "readiness receipt must be a regular non-symlink file"
        )
    try:
        encoded = supplied_receipt_path.read_bytes()
        readiness = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PremiumPoolReleaseError("readiness receipt is unreadable") from exc
    if not isinstance(readiness, dict):
        raise PremiumPoolReleaseError("readiness receipt must be a JSON object")
    observed_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if observed_digest != receipt_digest:
        raise PremiumPoolReleaseError(
            "readiness receipt digest drifted from the current test-live content binding"
        )

    readiness_phase = str(readiness.get("readinessPhase") or "").strip()
    expected_readiness = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": content_binding.get("releaseId"),
        "verifyRunId": content_binding.get("verifyRunId"),
        "manifestDigest": content_binding.get("manifestDigest"),
        "passed": True,
    }
    if (
        readiness_phase not in {"consumer", "commercial"}
        or any(readiness.get(field) != value for field, value in expected_readiness.items())
    ):
        raise PremiumPoolReleaseError(
            "readiness receipt does not match the current test-live content evidence"
        )
    import_run_id = str(readiness.get("importRunId") or "").strip()
    if not import_run_id:
        raise PremiumPoolReleaseError("readiness receipt lacks importRunId")
    _require_sha256_digest(
        content_binding.get("releaseUatSamplePlanDigest"),
        label="test-live ReleaseUatSamplePlan digest",
    )
    if not str(content_binding.get("releaseUatSamplePlanRef") or "").strip():
        raise PremiumPoolReleaseError(
            "test-live content binding lacks ReleaseUatSamplePlan identity"
        )
    video_work_id = _required_video_sample(content_binding.get("appUatPlan"))
    canonical_content_id = str(content_id or "").strip()
    if not canonical_content_id or canonical_content_id != video_work_id:
        raise PremiumPoolReleaseError(
            "contentId must be the exact ReleaseUatSamplePlan video sample"
        )
    return PremiumPoolTestLiveBinding(
        environment=environment,
        target=target,
        release_id=str(readiness["releaseId"]),
        manifest_digest=str(readiness["manifestDigest"]),
        import_run_id=import_run_id,
        verify_run_id=str(readiness["verifyRunId"]),
        content_id=canonical_content_id,
        readiness_phase=readiness_phase,
        readiness_receipt_ref=receipt_ref,
        readiness_receipt_digest=receipt_digest,
        startup_attempt_id=attempt_id,
        runtime_identity=canonical_runtime_identity,
    )


def open_premium_pool_operator_session(
    *,
    environment: str,
    target: str,
) -> tuple[LocalAcceptanceSession, str]:
    if environment in {"alpha", "beta", "gamma"}:
        token = mint_local_product_ops_operator_token(environment, target)
        return (
            LocalAcceptanceSession(
                owner_id=f"operator:content-commercial:{environment}",
                persona_id="",
                access_token=token,
            ),
            "managed_local_hs256_operator",
        )
    raise PremiumPoolReleaseError(
        "premium pool environment command only supports Alpha/Beta/Gamma local targets"
    )


def execute_premium_pool_upsert(
    *,
    binding: PremiumPoolBinding,
    product_ops_base_url: str,
    api_base_url: str,
    session: LocalAcceptanceSession,
    operator_kind: str,
    quality_score: float,
    expires_at: str,
    ssl_cafile: str,
    projection_deadline_seconds: float = 30.0,
) -> dict[str, Any]:
    if quality_score < 0.75 or quality_score > 1.0:
        raise PremiumPoolReleaseError("qualityScore must be between 0.75 and 1.0")
    canonical_expiry = _future_rfc3339(expires_at)
    supply_source = "canonical_data_release:" + binding.release_id
    audit_id = _premium_audit_id(binding)
    rollback_token = _premium_rollback_token(binding)
    body = {
        "contentId": binding.content_id,
        "scope": "global",
        "qualityScore": quality_score,
        "qualityAdmission": "approved",
        "supplySource": supply_source,
        "sourceTaskId": binding.import_run_id,
        "auditId": audit_id,
        "rollbackToken": rollback_token,
        "expiresAt": canonical_expiry,
    }
    canonical_body = json.dumps(
        body,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    idempotency_key = hashlib.sha256(
        _premium_idempotency_identity(binding) + b"\x00" + canonical_body
    ).hexdigest()
    request_id = "premium-" + idempotency_key[:24]
    response = _request_json(
        product_ops_base_url.rstrip("/") + COLLECTION_PATH,
        method="POST",
        token=session.access_token,
        body=canonical_body,
        headers={
            "Idempotency-Key": idempotency_key,
            "X-Request-Id": request_id,
            "X-Trace-Id": request_id,
        },
        ssl_cafile=ssl_cafile,
        timeout_seconds=12.0,
    )
    _require_matching_entry(
        response,
        binding=binding,
        supply_source=supply_source,
        expires_at=canonical_expiry,
    )
    listing = _request_json(
        product_ops_base_url.rstrip("/") + COLLECTION_PATH + "?activeOnly=true",
        method="GET",
        token=session.access_token,
        body=None,
        headers={},
        ssl_cafile=ssl_cafile,
        timeout_seconds=12.0,
    )
    listed_entry = next(
        (
            row
            for row in listing.get("items") or []
            if isinstance(row, dict) and row.get("contentId") == binding.content_id
        ),
        None,
    )
    if not isinstance(listed_entry, dict):
        raise PremiumPoolReleaseError(
            "Product Ops active readback omitted the committed contentId"
        )
    _require_matching_entry(
        listed_entry,
        binding=binding,
        supply_source=supply_source,
        expires_at=canonical_expiry,
    )
    matched_ids = _wait_for_premium_projection(
        api_base_url=api_base_url,
        content_id=binding.content_id,
        client_session_id=_premium_readback_session_id(binding),
        ssl_cafile=ssl_cafile,
        deadline_seconds=projection_deadline_seconds,
    )
    return {
        "schema": "qwq.premium_pool_environment_receipt",
        "status": "passed",
        "environment": binding.environment,
        "target": binding.target,
        **_premium_receipt_binding(binding),
        "operator": {
            "kind": operator_kind,
            "credentialPersisted": False,
        },
        "command": {
            "operation": "UpsertPremiumPoolEntry",
            "contentId": binding.content_id,
            "idempotencyKey": idempotency_key,
            "requestId": request_id,
            "status": str(response.get("status") or ""),
            "revision": response.get("revision"),
            "qualityScore": response.get("qualityScore"),
            "expiresAt": canonical_expiry,
        },
        "productOpsReadback": {
            "contentId": binding.content_id,
            "status": str(listed_entry.get("status") or ""),
            "revision": listed_entry.get("revision"),
        },
        "recommendationReadback": {
            "path": "/content/feed",
            "query": "sort=recommend&channelId=premium_stream&limit=20",
            "matchedPostIds": matched_ids,
        },
    }


def execute_premium_pool_readback(
    *,
    binding: PremiumPoolBinding,
    api_base_url: str,
    ssl_cafile: str,
    projection_deadline_seconds: float = 30.0,
) -> dict[str, Any]:
    """Verify the exact release-bound premium projection from content only."""
    matched_ids = _wait_for_premium_projection(
        api_base_url=api_base_url,
        content_id=binding.content_id,
        client_session_id=_premium_readback_session_id(binding),
        ssl_cafile=ssl_cafile,
        deadline_seconds=projection_deadline_seconds,
    )
    return {
        "schema": "qwq.premium_pool_readback_receipt",
        "status": "passed",
        "environment": binding.environment,
        "target": binding.target,
        **_premium_receipt_binding(binding),
        "recommendationReadback": {
            "path": "/content/feed",
            "query": "sort=recommend&channelId=premium_stream&limit=20",
            "contentId": binding.content_id,
            "matchedPostIds": matched_ids,
        },
    }


def _wait_for_premium_projection(
    *,
    api_base_url: str,
    content_id: str,
    client_session_id: str,
    ssl_cafile: str,
    deadline_seconds: float,
) -> list[str]:
    deadline = time.monotonic() + max(1.0, deadline_seconds)
    last_ids: list[str] = []
    while True:
        payload = _request_json(
            api_base_url.rstrip("/") + PREMIUM_FEED_PATH,
            method="GET",
            token="",
            body=None,
            headers={"X-Client-Session-Id": client_session_id},
            ssl_cafile=ssl_cafile,
            timeout_seconds=min(5.0, max(1.0, deadline - time.monotonic())),
        )
        last_ids = sorted(
            {
                str(item.get("id") or item.get("postId") or "").strip()
                for item in payload.get("items") or []
                if isinstance(item, dict)
                and str(item.get("id") or item.get("postId") or "").strip()
            }
        )
        if content_id in last_ids:
            return last_ids
        if time.monotonic() >= deadline:
            raise PremiumPoolReleaseError(
                "premium_stream did not expose the committed release video before deadline"
            )
        time.sleep(0.5)


def _premium_audit_id(binding: PremiumPoolBinding) -> str:
    """审计标识必须指向真正支撑这次写入的证据。

    首次激活尚无 verify 运行，其唯一凭据是导入报告；把它记成 commercial 审核会让
    收据谎称经过了并不存在的校验。
    """

    if isinstance(binding, PremiumPoolBootstrapBinding):
        return "content-release-import:" + binding.import_run_id
    return "content-commercial:" + binding.verify_run_id


def _premium_readback_session_id(binding: PremiumPoolBinding) -> str:
    if isinstance(binding, PremiumPoolTestLiveBinding):
        identity = (
            binding.target,
            binding.startup_attempt_id,
            binding.runtime_identity["mutableStateDigest"],
            binding.content_id,
        )
    else:
        identity = (binding.target, binding.baseline_id, binding.content_id)
    digest = hashlib.sha256("\x1f".join(identity).encode("utf-8")).hexdigest()[:24]
    return "premium-readback-" + digest


def _premium_idempotency_identity(binding: PremiumPoolBinding) -> bytes:
    if isinstance(
        binding, (PremiumPoolCandidateBinding, PremiumPoolBootstrapBinding)
    ):
        return binding.package_digest.encode("utf-8")
    return json.dumps(
        {
            "target": binding.target,
            "startupAttemptId": binding.startup_attempt_id,
            "mutableStateDigest": binding.runtime_identity["mutableStateDigest"],
            "configurationDigest": binding.runtime_identity["configurationDigest"],
            "providerRuntimeDigest": binding.runtime_identity["providerRuntimeDigest"],
            "readinessReceiptDigest": binding.readiness_receipt_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _premium_rollback_token(binding: PremiumPoolBinding) -> str:
    if isinstance(binding, PremiumPoolTestLiveBinding):
        identity = (
            binding.target,
            binding.startup_attempt_id,
            binding.runtime_identity["mutableStateDigest"],
            binding.content_id,
        )
    else:
        identity = (binding.target, binding.baseline_id, binding.content_id)
    return "rbk-premium-" + hashlib.sha256(
        "\x1f".join(identity).encode("utf-8")
    ).hexdigest()[:32]


def _premium_receipt_binding(binding: PremiumPoolBinding) -> dict[str, Any]:
    if isinstance(binding, PremiumPoolBootstrapBinding):
        return {
            "releaseImportBinding": {
                "launchPolicy": "release_import",
                "baselineId": binding.baseline_id,
                "packageDigest": binding.package_digest,
                "sourceRevision": binding.source_revision,
                "releaseId": binding.release_id,
                "manifestDigest": binding.manifest_digest,
                "importRunId": binding.import_run_id,
                "importReportRef": binding.import_report_ref,
                "videoWorkId": binding.content_id,
            }
        }
    if isinstance(binding, PremiumPoolCandidateBinding):
        return {
            "candidate": {
                "baselineId": binding.baseline_id,
                "packageDigest": binding.package_digest,
                "sourceRevision": binding.source_revision,
                "releaseId": binding.release_id,
                "manifestDigest": binding.manifest_digest,
                "importRunId": binding.import_run_id,
                "verifyRunId": binding.verify_run_id,
                "readinessReceiptRef": binding.readiness_receipt_ref,
            }
        }
    return {
        "testLiveBinding": {
            "launchPolicy": "test_live",
            "nonPromotable": True,
            "startupAttemptId": binding.startup_attempt_id,
            "mutableStateDigest": binding.runtime_identity["mutableStateDigest"],
            "configurationDigest": binding.runtime_identity["configurationDigest"],
            "providerRuntimeDigest": binding.runtime_identity["providerRuntimeDigest"],
            "runtimeIdentity": dict(binding.runtime_identity),
            "releaseId": binding.release_id,
            "manifestDigest": binding.manifest_digest,
            "importRunId": binding.import_run_id,
            "verifyRunId": binding.verify_run_id,
            "readinessPhase": binding.readiness_phase,
            "readinessReceiptRef": binding.readiness_receipt_ref,
            "readinessReceiptDigest": binding.readiness_receipt_digest,
            "videoWorkId": binding.content_id,
        }
    }


def _require_matching_entry(
    entry: dict[str, Any],
    *,
    binding: PremiumPoolBinding,
    supply_source: str,
    expires_at: str,
) -> None:
    if (
        entry.get("contentId") != binding.content_id
        or entry.get("status") != "active"
        or entry.get("scope") != "global"
        or entry.get("qualityAdmission") != "approved"
        or entry.get("supplySource") != supply_source
        or entry.get("sourceTaskId") != binding.import_run_id
        or entry.get("expiresAt") != expires_at
        or not isinstance(entry.get("revision"), int)
        or int(entry["revision"]) <= 0
    ):
        raise PremiumPoolReleaseError(
            "PremiumPoolEntry readback does not match the content-bound command"
        )


def _future_rfc3339(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PremiumPoolReleaseError("expiresAt must be RFC3339") from exc
    if parsed.tzinfo is None or parsed <= datetime.now(timezone.utc):
        raise PremiumPoolReleaseError("expiresAt must be in the future")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_json(
    url: str,
    *,
    method: str,
    token: str,
    body: bytes | None,
    headers: dict[str, str],
    ssl_cafile: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **headers}
    if token:
        request_headers["Authorization"] = "Bearer " + token
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    context = ssl.create_default_context(
        cafile=str(ssl_cafile).strip() or None,
    )
    opener = request.build_opener(
        request.ProxyHandler({}),
        request.HTTPSHandler(context=context),
    )
    req = request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with opener.open(req, timeout=max(1.0, timeout_seconds)) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except Exception as exc:  # noqa: BLE001
        raise PremiumPoolReleaseError(
            f"premium pool request transport failed: {type(exc).__name__}"
        ) from exc
    if status < 200 or status >= 300:
        raise PremiumPoolReleaseError(
            f"premium pool request {method} failed with HTTP {status}"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PremiumPoolReleaseError(
            f"premium pool request {method} returned non-JSON HTTP {status}"
        ) from exc
    if not isinstance(payload, dict):
        raise PremiumPoolReleaseError(
            f"premium pool request {method} returned non-object JSON"
        )
    return payload
