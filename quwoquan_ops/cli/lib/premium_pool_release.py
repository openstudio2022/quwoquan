from __future__ import annotations

import hashlib
import json
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from .deployment_candidate_manifest import load_candidate_manifest
from .local_environment_auth import (
    LocalAcceptanceSession,
    mint_local_product_ops_operator_token,
)
from .output_paths import active_deployment_candidate, env_runs_root


COLLECTION_PATH = "/control-plane/product/recommendation/premium-pool"
PREMIUM_FEED_PATH = "/content/feed?sort=recommend&channelId=premium_stream&limit=20"


class PremiumPoolReleaseError(RuntimeError):
    pass


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
    canonical_content_id = str(content_id or "").strip()
    if not canonical_content_id:
        raise PremiumPoolReleaseError("contentId is required")
    typed_video_ids: set[str] = set()
    for row in readiness.get("feedQueries") or []:
        if isinstance(row, dict) and row.get("name") == "typed_video":
            typed_video_ids.update(
                str(item).strip()
                for item in row.get("matchedPostIds") or []
                if str(item).strip()
            )
    if canonical_content_id not in typed_video_ids:
        raise PremiumPoolReleaseError(
            "contentId is not a release-bound video in the readiness receipt"
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
    binding: PremiumPoolCandidateBinding,
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
    audit_id = "content-commercial:" + binding.verify_run_id
    rollback_token = "rbk-premium-" + hashlib.sha256(
        "\x1f".join(
            (binding.target, binding.baseline_id, binding.content_id)
        ).encode("utf-8")
    ).hexdigest()[:32]
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
        binding.package_digest.encode("utf-8") + b"\x00" + canonical_body
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
        "candidate": {
            "baselineId": binding.baseline_id,
            "packageDigest": binding.package_digest,
            "sourceRevision": binding.source_revision,
            "releaseId": binding.release_id,
            "manifestDigest": binding.manifest_digest,
            "importRunId": binding.import_run_id,
            "verifyRunId": binding.verify_run_id,
            "readinessReceiptRef": binding.readiness_receipt_ref,
        },
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
    binding: PremiumPoolCandidateBinding,
    api_base_url: str,
    ssl_cafile: str,
    projection_deadline_seconds: float = 30.0,
) -> dict[str, Any]:
    """Verify the candidate-bound premium projection from content-release only."""
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
        "candidate": {
            "baselineId": binding.baseline_id,
            "packageDigest": binding.package_digest,
            "sourceRevision": binding.source_revision,
            "releaseId": binding.release_id,
            "manifestDigest": binding.manifest_digest,
            "importRunId": binding.import_run_id,
            "verifyRunId": binding.verify_run_id,
            "readinessReceiptRef": binding.readiness_receipt_ref,
        },
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


def _premium_readback_session_id(binding: PremiumPoolCandidateBinding) -> str:
    digest = hashlib.sha256(
        "\x1f".join(
            (binding.target, binding.baseline_id, binding.content_id)
        ).encode("utf-8")
    ).hexdigest()[:24]
    return "premium-readback-" + digest


def _require_matching_entry(
    entry: dict[str, Any],
    *,
    binding: PremiumPoolCandidateBinding,
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
            "PremiumPoolEntry readback does not match the candidate-bound command"
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
