"""Strict read-only 4×4 content API consumer for Alpha Research releases.

The runner consumes only explicit, exact-byte authorities.  It never selects a
latest release, accepts a caller-supplied URL/token, mutates runtime state, or
writes an acceptance fact.  Every matrix cell retains one observation and one
canonical create-once ``ReadinessCaseResult``, including blocked/failed cells.
"""

from __future__ import annotations

import hashlib
import json
import ssl
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from quwoquan_ops.cli.lib.content_api_consumer_authority import (
    CARRIERS,
    ENTRY_SURFACES,
    ROOT,
    SOURCE_FINGERPRINT_SCHEMA,
    SPEC_REF,
    _AuthorityFile,
    _DIGEST_RE,
    _IDENTITY_RE,
    _REQUIRED_HEALTH_LAYERS,
    _RUNNER_RE,
    _Sample,
    _digest_bytes,
    _load_authority,
    _load_import_mappings,
    _ref_authority,
    _regular_bytes,
    _report_ref,
    _required_digest,
    _required_identity,
    _resolve_samples,
    _runtime_authority,
    _tls_ca_file,
    _topology_api_base,
    _utc_now,
    _validate_data_readiness,
    _validate_health,
    _validate_sample_plan,
    _write_regular_json,
    content_consumer_raw_slot_id,
    derive_content_consumer_source_fingerprint,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    canonical_json_bytes,
    write_readiness_case_result,
)
from quwoquan_ops.cli.lib.research_consumer_credential import (
    issue_research_consumer_credential,
)


class ContentApiConsumerError(ValueError):
    """An explicit authority is invalid or the runner cannot retain evidence."""


class ContentApiConsumerTransportError(ContentApiConsumerError):
    """A read-only HTTP operation could not reach a JSON terminal response."""


class ContentApiConsumerAssertionError(ContentApiConsumerError):
    """A terminal HTTP response failed an exact cell assertion."""

    def __init__(self, message: str, *, observation: HttpObservation):
        super().__init__(message)
        self.observation = observation

@dataclass(frozen=True)
class HttpObservation:
    method: str
    path: str
    status: int
    payload: Mapping[str, Any]
    request_id: str
    trace_id: str
    started_at: str
    completed_at: str
    duration_ms: int


HttpRequest = Callable[..., HttpObservation]
CredentialIssuer = Callable[..., dict[str, Any]]


def _default_http_request(
    *,
    api_base: str,
    ca_file: Path,
    bearer_token: str,
    attestation_token: str,
    method: str,
    path: str,
    page_id: str,
    query: Mapping[str, str] | None = None,
    body: Mapping[str, Any] | None = None,
    timeout_seconds: float = 12.0,
    release_id: str = "",
    release_digest: str = "",
    manifest_digest: str = "",
) -> HttpObservation:
    request_id = "OPS.content-api-consumer." + uuid.uuid4().hex
    trace_id = "OPS.content-api-consumer." + uuid.uuid4().hex
    normalized_path = "/" + path.lstrip("/")
    url = api_base.rstrip("/") + normalized_path
    if query:
        url += "?" + urlencode(dict(query))
    encoded = (
        json.dumps(dict(body), sort_keys=True, separators=(",", ":")).encode()
        if body is not None
        else None
    )
    started_at = _utc_now()
    started = time.monotonic_ns()
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}",
        "X-Research-Identity-Attestation": attestation_token,
        "X-Client-Page-Id": page_id,
        "X-Client-Session-Id": "content-api-consumer",
        "X-Client-Sent-At": started_at,
        "X-Client-Device-Platform": "ops",
        "X-Client-App-Version": "content-api-consumer-v1",
        "X-Request-Id": request_id,
        "X-Trace-Id": trace_id,
    }
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded, headers=headers, method=method)
    context = ssl.create_default_context(cafile=str(ca_file))
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read(2 * 1024 * 1024 + 1)
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read(2 * 1024 * 1024 + 1)
    except (OSError, URLError, ssl.SSLError) as exc:
        raise ContentApiConsumerTransportError(
            f"HTTP transport failed for {method} {normalized_path}: "
            f"{type(exc).__name__}"
        ) from exc
    if len(raw) > 2 * 1024 * 1024:
        raise ContentApiConsumerError(
            f"HTTP response exceeded byte budget for {method} {normalized_path}"
        )
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContentApiConsumerError(
            f"HTTP response is not JSON for {method} {normalized_path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ContentApiConsumerError(
            f"HTTP response is not an object for {method} {normalized_path}"
        )
    completed_at = _utc_now()
    duration_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
    return HttpObservation(
        method=method,
        path=normalized_path,
        status=status,
        payload=payload,
        request_id=request_id,
        trace_id=trace_id,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=int(duration_ms),
    )


def _items(
    payload: Mapping[str, Any], field: str, *, label: str
) -> list[Mapping[str, Any]]:
    raw = payload.get(field)
    if not isinstance(raw, list):
        raise ContentApiConsumerError(f"{label} lacks {field} array")
    if any(not isinstance(row, Mapping) for row in raw):
        raise ContentApiConsumerError(f"{label} {field} contains non-object rows")
    return list(raw)


def _assert_activation(
    observation: HttpObservation,
    *,
    release_id: str,
    manifest_digest: str,
    label: str,
) -> None:
    if observation.status != 200:
        raise ContentApiConsumerError(f"{label} returned HTTP {observation.status}")
    if (
        observation.payload.get("releaseId") != release_id
        or observation.payload.get("manifestDigest") != manifest_digest
    ):
        raise ContentApiConsumerError(f"{label} active release identity drifted")


def _post_item(
    rows: list[Mapping[str, Any]], sample: _Sample, *, label: str
) -> Mapping[str, Any]:
    matches = [
        row
        for row in rows
        if str(row.get("postId") or row.get("objectId") or "").strip()
        == sample.runtime_object_id
    ]
    if len(matches) != 1:
        raise ContentApiConsumerError(
            f"{label} did not expose exactly one imported {sample.carrier} post"
        )
    item = matches[0]
    observed_type = str(
        item.get("contentType")
        or (
            (item.get("content") or {}).get("contentType")
            if isinstance(item.get("content"), Mapping)
            else ""
        )
        or ""
    ).strip()
    if observed_type != sample.carrier:
        raise ContentApiConsumerError(f"{label} contentType drifted")
    return item


def _homepage_item(
    rows: list[Mapping[str, Any]], sample: _Sample, *, label: str
) -> Mapping[str, Any]:
    matches = [
        row
        for row in rows
        if str(row.get("homepageId") or row.get("objectId") or "").strip()
        == sample.runtime_object_id
    ]
    if len(matches) != 1:
        raise ContentApiConsumerError(
            f"{label} did not expose exactly one imported homepage"
        )
    return matches[0]


def _feed_probe(
    sample: _Sample,
    *,
    request: HttpRequest,
    common: Mapping[str, Any],
) -> tuple[HttpObservation, dict[str, Any]]:
    query = (
        {"sort": "recommend", "channelId": "recommend", "limit": "50"}
        if sample.carrier == "homepage"
        else {"identity": "work", "type": sample.carrier, "limit": "50"}
    )
    observation = request(
        **common,
        method="GET",
        path="content/feed",
        page_id="content.feed.list",
        query=query,
    )
    try:
        _assert_activation(
            observation,
            release_id=str(common["release_id"]),
            manifest_digest=str(common["manifest_digest"]),
            label=f"feed/{sample.carrier}",
        )
        if sample.carrier == "homepage":
            item = _homepage_item(
                _items(observation.payload, "objectCards", label="feed/homepage"),
                sample,
                label="feed/homepage",
            )
        else:
            item = _post_item(
                _items(observation.payload, "items", label=f"feed/{sample.carrier}"),
                sample,
                label=f"feed/{sample.carrier}",
            )
        return observation, {
            "matchedRuntimeObjectId": sample.runtime_object_id,
            "wireKind": "feed",
            "fieldSet": sorted(item),
        }

    except ContentApiConsumerError as exc:
        raise ContentApiConsumerAssertionError(
            str(exc), observation=observation
        ) from exc


def _search_probe(
    sample: _Sample,
    *,
    request: HttpRequest,
    common: Mapping[str, Any],
) -> tuple[HttpObservation, dict[str, Any]]:
    object_type = "entity.homepage" if sample.carrier == "homepage" else "content.post"
    body: dict[str, Any] = {
        "query": sample.query,
        "mode": "result",
        "objectTypes": [object_type],
        "ids": [sample.runtime_object_id],
        "limit": 50,
    }
    if sample.carrier != "homepage":
        body["contentTypes"] = [sample.carrier]
    observation = request(
        **common,
        method="POST",
        path="search",
        page_id="search.global",
        body=body,
    )
    try:
        if observation.status != 200:
            raise ContentApiConsumerError(
                f"search/{sample.carrier} returned HTTP {observation.status}"
            )
        rows = _items(observation.payload, "hits", label=f"search/{sample.carrier}")
        if sample.carrier == "homepage":
            item = _homepage_item(rows, sample, label="search/homepage")
            if item.get("objectType") != "entity.homepage":
                raise ContentApiConsumerError("search/homepage objectType drifted")
        else:
            item = _post_item(rows, sample, label=f"search/{sample.carrier}")
            if item.get("objectType") != "content.post":
                raise ContentApiConsumerError(
                    f"search/{sample.carrier} objectType drifted"
                )
        return observation, {
            "matchedRuntimeObjectId": sample.runtime_object_id,
            "wireKind": "search",
            "fieldSet": sorted(item),
        }

    except ContentApiConsumerError as exc:
        raise ContentApiConsumerAssertionError(
            str(exc), observation=observation
        ) from exc


def _recommendation_probe(
    sample: _Sample,
    *,
    request: HttpRequest,
    common: Mapping[str, Any],
) -> tuple[HttpObservation, dict[str, Any]]:
    observation = request(
        **common,
        method="GET",
        path="content/feed",
        page_id="content.feed.list",
        query={"sort": "recommend", "channelId": "recommend", "limit": "50"},
    )
    try:
        _assert_activation(
            observation,
            release_id=str(common["release_id"]),
            manifest_digest=str(common["manifest_digest"]),
            label=f"recommendation/{sample.carrier}",
        )
        rows = _items(
            observation.payload, "items", label=f"recommendation/{sample.carrier}"
        )
        if sample.carrier == "homepage":
            matches = [
                row
                for row in rows
                if str(row.get("primaryHomepageId") or "").strip()
                == sample.runtime_object_id
            ]
            if not matches:
                raise ContentApiConsumerError(
                    "recommendation/homepage lacks an item whose primaryHomepageId "
                    "equals the imported homepageId"
                )
            item = matches[0]
        else:
            item = _post_item(rows, sample, label=f"recommendation/{sample.carrier}")
        return observation, {
            "matchedRuntimeObjectId": sample.runtime_object_id,
            "wireKind": "recommendation",
            "fieldSet": sorted(item),
        }

    except ContentApiConsumerError as exc:
        raise ContentApiConsumerAssertionError(
            str(exc), observation=observation
        ) from exc


def _direct_probe(
    sample: _Sample,
    *,
    request: HttpRequest,
    common: Mapping[str, Any],
) -> tuple[HttpObservation, dict[str, Any]]:
    if sample.carrier == "homepage":
        path = "homepages/" + quote(sample.runtime_object_id, safe="")
        page_id = "entity.homepage.detail"
    else:
        path = "content/posts/" + quote(sample.runtime_object_id, safe="")
        page_id = "content.post.get"
    observation = request(
        **common,
        method="GET",
        path=path,
        page_id=page_id,
    )
    try:
        if observation.status != 200:
            raise ContentApiConsumerError(
                f"direct/{sample.carrier} returned HTTP {observation.status}"
            )
        if sample.carrier == "homepage":
            if observation.payload.get("homepageId") != sample.runtime_object_id:
                raise ContentApiConsumerError("direct/homepage homepageId drifted")
        else:
            if (
                observation.payload.get("postId") != sample.runtime_object_id
                or observation.payload.get("contentType") != sample.carrier
                or observation.payload.get("contentIdentity") != "work"
            ):
                raise ContentApiConsumerError(
                    f"direct/{sample.carrier} imported post identity drifted"
                )
        return observation, {
            "matchedRuntimeObjectId": sample.runtime_object_id,
            "wireKind": "direct",
            "fieldSet": sorted(observation.payload),
        }

    except ContentApiConsumerError as exc:
        raise ContentApiConsumerAssertionError(
            str(exc), observation=observation
        ) from exc


_PROBES = {
    "feed": _feed_probe,
    "search": _search_probe,
    "recommendation": _recommendation_probe,
    "direct_or_object_route": _direct_probe,
}

def run_content_api_consumer(
    *,
    target: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    sample_plan_ref: str,
    sample_plan_digest: str,
    data_readiness_ref: str,
    data_readiness_digest: str,
    consumer_health_ref: str,
    consumer_health_digest: str,
    manifest_digest: str,
    report_dir: Path,
    output_root: Path,
    http_request: HttpRequest = _default_http_request,
    credential_issuer: CredentialIssuer = issue_research_consumer_credential,
) -> dict[str, Any]:
    """Execute and retain exactly sixteen read-only API observations/results."""

    target = str(target or "").strip()
    release_id = _required_identity(release_id, label="release-id")
    manifest_digest = _required_digest(manifest_digest, label="manifest-digest")
    import_run_id = _required_identity(import_run_id, label="import-run-id")
    verify_run_id = _required_identity(verify_run_id, label="verify-run-id")
    if import_run_id == verify_run_id:
        raise ContentApiConsumerError(
            "import-run-id and verify-run-id must be distinct"
        )
    api_base = _topology_api_base(target)
    ca_file = _tls_ca_file(target)
    authority_root = output_root.expanduser().resolve(strict=True)
    report_dir = report_dir.expanduser()
    if report_dir.exists() or report_dir.is_symlink():
        raise ContentApiConsumerError(
            "report-dir must be a fresh create-once directory"
        )
    try:
        report_dir.parent.resolve(strict=True).relative_to(authority_root)
    except (OSError, ValueError) as exc:
        raise ContentApiConsumerError(
            "report-dir must stay below QWQ_OUTPUT_ROOT"
        ) from exc

    started_at = _utc_now()
    sample_plan = _load_authority(
        sample_plan_ref,
        sample_plan_digest,
        label="sample plan",
        root=authority_root,
    )
    readiness_authority = _load_authority(
        data_readiness_ref,
        data_readiness_digest,
        label="Data readiness",
        root=authority_root,
    )
    health_authority = _load_authority(
        consumer_health_ref,
        consumer_health_digest,
        label="content-consumer health",
        root=authority_root,
    )
    samples, cells, release_digest = _validate_sample_plan(
        sample_plan, release_id=release_id
    )
    readiness = _validate_data_readiness(
        readiness_authority,
        release_id=release_id,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        release_digest=release_digest,
        manifest_digest=manifest_digest,
    )
    health = _validate_health(
        health_authority,
        release_id=release_id,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        release_digest=release_digest,
        manifest_digest=manifest_digest,
        data_readiness_ref=readiness_authority.ref,
        data_readiness_digest=readiness_authority.digest,
    )
    resolved_samples = _resolve_samples(
        samples,
        readiness=readiness,
        output_root=authority_root,
        release_id=release_id,
        import_run_id=import_run_id,
        manifest_digest=manifest_digest,
    )
    runtime = _runtime_authority(health, target=target)

    # Evidence begins only after all owner refs/digests and runtime identity pass.
    report_dir.mkdir()
    consumer_health_binding = {
        "schema": "qwq.content_api_consumer.health_binding.v1",
        "status": "passed",
        "environment": "alpha",
        "deploymentTarget": target,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "manifestDigest": manifest_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "sourceHealth": {
            "ref": health_authority.ref,
            "digest": health_authority.digest,
        },
        "requiredLayers": list(_REQUIRED_HEALTH_LAYERS),
    }
    consumer_health_binding_path = report_dir / "consumer-health.json"
    _write_regular_json(consumer_health_binding_path, consumer_health_binding)
    consumer_health_binding_raw = _regular_bytes(
        consumer_health_binding_path, label="consumer health binding"
    )
    consumer_health_binding_exact = {
        "ref": _report_ref(consumer_health_binding_path, output_root=authority_root),
        "digest": _digest_bytes(consumer_health_binding_raw),
    }
    credential_error = ""
    try:
        credential = credential_issuer(
            environment="alpha",
            release_id=release_id,
            verify_run_id=verify_run_id,
        )
        bearer_token = str(credential.get("bearerToken") or "").strip()
        attestation_token = str(credential.get("attestationToken") or "").strip()
        credential_base = str(credential.get("apiBaseUrl") or "").strip().rstrip("/")
        credential_ca = Path(str(credential.get("sslCaFile") or "")).expanduser()
        if (
            not bearer_token
            or not attestation_token
            or credential_base != api_base
            or credential_ca.resolve() != ca_file.resolve()
        ):
            raise ContentApiConsumerError(
                "research_consumer_credential topology/TLS identity drifted"
            )
    except (OSError, RuntimeError, TypeError, ValueError):
        # The terminal is retained for every required cell; credential exception
        # text is intentionally excluded because an upstream client might echo a
        # secret while failing.
        bearer_token = ""
        attestation_token = ""
        credential_error = "research_consumer_credential is unavailable"

    observations: list[dict[str, Any]] = []
    raw_results: list[dict[str, str]] = []
    statuses: list[str] = []
    common = {
        "api_base": api_base,
        "ca_file": ca_file,
        "bearer_token": bearer_token,
        "attestation_token": attestation_token,
        "release_id": release_id,
        "release_digest": release_digest,
        "manifest_digest": manifest_digest,
    }
    for entry in ENTRY_SURFACES:
        for carrier in CARRIERS:
            cell = cells[f"{entry}:{carrier}"]
            sample = resolved_samples[carrier]
            cell_started_at = _utc_now()
            observation: HttpObservation | None = None
            compact: dict[str, Any] = {}
            status = "passed"
            reason_code = ""
            try:
                if credential_error:
                    raise ContentApiConsumerTransportError(credential_error)
                observation, compact = _PROBES[entry](
                    sample,
                    request=http_request,
                    common=common,
                )
            except ContentApiConsumerTransportError as exc:
                status = "blocked"
                reason_code = "SERVICE.CONTENT_API_CONSUMER.blocked"
                compact = {
                    "errorClass": type(exc).__name__,
                    "error": str(exc)[:500],
                }
            except ContentApiConsumerAssertionError as exc:
                observation = exc.observation
                status = "failed"
                reason_code = "SERVICE.CONTENT_API_CONSUMER.failed"
                compact = {
                    "errorClass": type(exc).__name__,
                    "error": str(exc)[:500],
                }
            except ContentApiConsumerError as exc:
                status = "failed"
                reason_code = "SERVICE.CONTENT_API_CONSUMER.failed"
                compact = {
                    "errorClass": type(exc).__name__,
                    "error": str(exc)[:500],
                }
            cell_completed_at = observation.completed_at if observation else _utc_now()
            observation_payload: dict[str, Any] = {
                "schema": "qwq.content_api_consumer.observation.v1",
                "sampleId": sample.sample_id,
                "entrySurface": entry,
                "carrier": carrier,
                "objectId": sample.object_id,
                "runtimeObjectId": sample.runtime_object_id,
                "releaseId": release_id,
                "releaseDigest": release_digest,
                "manifestDigest": manifest_digest,
                "importRunId": import_run_id,
                "verifyRunId": verify_run_id,
                "status": status,
                "startedAt": (
                    observation.started_at if observation else cell_started_at
                ),
                "completedAt": cell_completed_at,
                "http": (
                    {
                        "method": observation.method,
                        "path": observation.path,
                        "status": observation.status,
                        "requestId": observation.request_id,
                        "traceId": observation.trace_id,
                        "durationMs": observation.duration_ms,
                        "responseSha256": _digest_bytes(
                            canonical_json_bytes(observation.payload)
                        ),
                    }
                    if observation is not None
                    else None
                ),
                "assertion": compact,
            }
            observation_path = report_dir / "observations" / entry / f"{carrier}.json"
            _write_regular_json(observation_path, observation_payload)
            observation_raw = _regular_bytes(
                observation_path, label=f"{entry}/{carrier} observation"
            )
            result: dict[str, Any] = {
                "objectId": sample.object_id,
                "objectRef": sample.object_ref,
                "objectDigest": sample.object_digest,
                "specRef": cell["specRef"],
                "caseId": (
                    "content_api_consumer_"
                    + hashlib.sha256(
                        (
                            f"{release_id}\0{import_run_id}\0{verify_run_id}\0"
                            f"{sample.sample_id}\0{entry}\0{carrier}"
                        ).encode()
                    ).hexdigest()
                ),
                "producer": "service",
                "layer": "api_integration",
                "status": status,
                "target": {"kind": "operation", "id": entry},
                "commitSha": runtime["commitSha"],
                "contractGraphSourceHash": runtime["contractGraphSourceHash"],
                "deploymentTarget": target,
                "baselineId": runtime["baselineId"],
                "packageDigest": runtime["packageDigest"],
                "configurationDigest": runtime["configurationDigest"],
                "candidateManifestSha256": runtime["candidateManifestSha256"],
                "releaseId": release_id,
                "releaseDigest": release_digest,
                "importRunId": import_run_id,
                "verifyRunId": verify_run_id,
                "entrySurface": entry,
                "carrier": carrier,
                "environment": "alpha",
                "provider": "first-party-https",
                "startedAt": observation_payload["startedAt"],
                "completedAt": cell_completed_at,
                "runnerIdentity": cell["runnerClass"],
                "artifactSha256": hashlib.sha256(observation_raw).hexdigest(),
                "artifactPath": _report_ref(
                    observation_path, output_root=authority_root
                ),
            }
            if reason_code:
                result["reasonCode"] = reason_code
            raw_path = report_dir / "raw" / entry / f"{carrier}.json"
            write_readiness_case_result(
                raw_path,
                result,
                generated_at=cell_completed_at,
            )
            raw = _regular_bytes(raw_path, label=f"{entry}/{carrier} raw result")
            raw_ref = _report_ref(raw_path, output_root=authority_root)
            raw_results.append(
                {
                    "ref": raw_ref,
                    "digest": _digest_bytes(raw),
                    "slotId": content_consumer_raw_slot_id(
                        sample_id=sample.sample_id,
                        entry_surface=entry,
                        carrier=carrier,
                        spec_ref=cell["specRef"],
                        runner_identity=cell["runnerClass"],
                    ),
                    "status": status,
                }
            )
            observations.append(
                {
                    "ref": _report_ref(observation_path, output_root=authority_root),
                    "digest": _digest_bytes(observation_raw),
                    "status": status,
                }
            )
            statuses.append(status)

    completed_at = _utc_now()
    source_fingerprint = derive_content_consumer_source_fingerprint(
        schema=SOURCE_FINGERPRINT_SCHEMA,
        environment="alpha",
        target=target,
        release_id=release_id,
        release_digest=release_digest,
        manifest_digest=manifest_digest,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        sample_plan={"ref": sample_plan.ref, "digest": sample_plan.digest},
        data_readiness={
            "ref": readiness_authority.ref,
            "digest": readiness_authority.digest,
        },
        consumer_health=consumer_health_binding_exact,
        required_raw_results=raw_results,
    )
    report = {
        "schema": "qwq.content_api_consumer.report.v1",
        "command": "content-api-consumer",
        "target": target,
        "environment": "alpha",
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "manifestDigest": manifest_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "samplePlan": {"ref": sample_plan.ref, "digest": sample_plan.digest},
        "dataReadiness": {
            "ref": readiness_authority.ref,
            "digest": readiness_authority.digest,
        },
        "consumerHealth": consumer_health_binding_exact,
        "sourceHealth": {
            "ref": health_authority.ref,
            "digest": health_authority.digest,
        },
        "sourceFingerprint": source_fingerprint,
        "observations": observations,
        "requiredRawResults": raw_results,
        "startedAt": started_at,
        "completedAt": completed_at,
    }
    # Intentionally no aggregate status/verdict: canonical raw results own outcomes.
    _write_regular_json(report_dir / "report.json", report)
    failed = sum(status == "failed" for status in statuses)
    blocked = sum(status == "blocked" for status in statuses)
    return {
        "exitCode": 1 if failed else 2 if blocked else 0,
        "summary": (
            "content API consumer completed 16/16 cells"
            if not failed and not blocked
            else (
                "content API consumer retained 16 cells: "
                f"failed={failed}, blocked={blocked}"
            )
        ),
        "details": [
            f"passed={statuses.count('passed')}",
            f"failed={failed}",
            f"blocked={blocked}",
        ],
        "reportDir": _report_ref(report_dir, output_root=authority_root),
        "releaseDigest": release_digest,
        "manifestDigest": manifest_digest,
        "consumerHealth": consumer_health_binding_exact,
        "sourceFingerprint": source_fingerprint,
        "requiredRawResults": raw_results,
    }


__all__ = [
    "CARRIERS",
    "ENTRY_SURFACES",
    "ContentApiConsumerAssertionError",
    "ContentApiConsumerError",
    "ContentApiConsumerTransportError",
    "HttpObservation",
    "run_content_api_consumer",
]
