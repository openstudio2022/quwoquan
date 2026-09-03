"""Strict read-only 4×4 content API consumer for Alpha Research releases.

The runner consumes only explicit, exact-byte authorities.  It never selects a
latest release, accepts a caller-supplied URL/token, mutates runtime state, or
writes an acceptance fact.  Every matrix cell retains one observation and one
canonical create-once ``ReadinessCaseResult``, including blocked/failed cells.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import stat
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    derive_m1_source_fingerprint,
    required_raw_slot_id,
)
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path
from quwoquan_ops.cli.lib.readiness_case_result import (
    canonical_json_bytes,
    write_readiness_case_result,
)
from quwoquan_ops.cli.lib.research_consumer_credential import (
    issue_research_consumer_credential,
)

ROOT = Path(__file__).resolve().parents[3]
ENTRY_SURFACES = ("feed", "search", "recommendation", "direct_or_object_route")
CARRIERS = ("homepage", "article", "image", "video")
SPEC_REF = (
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/"
    "multi-carrier-release/spec.md#gwt-034"
)
CONTENT_API_CONSUMER_HEALTH_SCHEMA = "qwq.content_api_consumer.health_binding"
CONTENT_API_CONSUMER_OBSERVATION_SCHEMA = "qwq.content_api_consumer.observation"
CONTENT_API_CONSUMER_REPORT_SCHEMA = "qwq.content_api_consumer.report"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_RUNNER_RE = re.compile(
    r"^qwq\.content_consumer\."
    r"(feed|search|recommendation|direct_or_object_route)\."
    r"(homepage|article|image|video)$"
)
_REQUIRED_HEALTH_LAYERS = (
    "build_ready",
    "runtime_full_ready",
    "release_active",
    "content_exact_queries_ready",
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
class _AuthorityFile:
    path: Path
    ref: str
    digest: str
    value: dict[str, Any]


@dataclass(frozen=True)
class _Sample:
    sample_id: str
    carrier: str
    object_id: str
    object_ref: str
    object_digest: str
    runtime_object_id: str
    query: str


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


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _required_digest(value: object, *, label: str) -> str:
    digest = str(value or "").strip()
    if _DIGEST_RE.fullmatch(digest) is None:
        raise ContentApiConsumerError(
            f"{label} must use canonical sha256:<64 lowercase hex>"
        )
    return digest


def _required_identity(value: object, *, label: str) -> str:
    identity = str(value or "").strip()
    if _IDENTITY_RE.fullmatch(identity) is None:
        raise ContentApiConsumerError(f"{label} is not a canonical identity")
    return identity


def _regular_bytes(path: Path, *, label: str) -> bytes:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ContentApiConsumerError(f"{label} must not be a symlink")
    try:
        before = candidate.stat()
    except OSError as exc:
        raise ContentApiConsumerError(f"{label} is unavailable: {candidate}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ContentApiConsumerError(f"{label} must be a regular file")
    try:
        raw = candidate.read_bytes()
        after = candidate.stat()
    except OSError as exc:
        raise ContentApiConsumerError(f"{label} is unreadable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise ContentApiConsumerError(f"{label} changed during read")
    return raw


def _load_authority(
    ref: str,
    digest: str,
    *,
    label: str,
    root: Path,
) -> _AuthorityFile:
    normalized_ref = str(ref or "").strip()
    relative = Path(normalized_ref)
    if (
        not normalized_ref
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in normalized_ref
        or "//" in normalized_ref
    ):
        raise ContentApiConsumerError(f"{label} ref must be repo/output-root relative")
    expected_digest = _required_digest(digest, label=f"{label} digest")
    resolved_root = root.expanduser().resolve(strict=True)
    candidate = resolved_root / relative
    try:
        resolved = candidate.resolve(strict=True)
        observed_ref = resolved.relative_to(resolved_root).as_posix()
    except (OSError, ValueError) as exc:
        raise ContentApiConsumerError(
            f"{label} ref escapes its authority root"
        ) from exc
    if observed_ref != relative.as_posix():
        raise ContentApiConsumerError(f"{label} ref is not canonical")
    raw = _regular_bytes(resolved, label=label)
    observed_digest = _digest_bytes(raw)
    if observed_digest != expected_digest:
        raise ContentApiConsumerError(
            f"{label} exact-byte digest drifted: expected {expected_digest}, "
            f"got {observed_digest}"
        )
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContentApiConsumerError(f"{label} is not JSON") from exc
    if not isinstance(value, dict):
        raise ContentApiConsumerError(f"{label} must be a JSON object")
    return _AuthorityFile(resolved, observed_ref, expected_digest, value)


def _validate_sample_plan(
    authority: _AuthorityFile,
    *,
    release_id: str,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], str]:
    plan = authority.value
    if (
        plan.get("schema") != "quwoquan_data.release_uat_sample_plan"
        or plan.get("releaseId") != release_id
    ):
        raise ContentApiConsumerError("sample plan release identity drifted")
    release_digest = _required_digest(
        plan.get("releaseDigest"), label="sample plan releaseDigest"
    )
    raw_samples = plan.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ContentApiConsumerError("sample plan samples are missing")
    samples: dict[str, dict[str, str]] = {}
    sample_ids: set[str] = set()
    object_ids: set[str] = set()
    object_refs: set[str] = set()
    for index, row in enumerate(raw_samples):
        if not isinstance(row, Mapping) or set(row) != {
            "sampleId",
            "carrier",
            "objectId",
            "objectRef",
            "objectDigest",
        }:
            raise ContentApiConsumerError(
                f"sample plan samples[{index}] fields drifted"
            )
        carrier = str(row.get("carrier") or "")
        sample_id = _required_identity(
            row.get("sampleId"), label=f"sample plan samples[{index}].sampleId"
        )
        object_id = str(row.get("objectId") or "").strip()
        object_ref = str(row.get("objectRef") or "").strip()
        object_digest = _required_digest(
            row.get("objectDigest"),
            label=f"sample plan samples[{index}].objectDigest",
        )
        expected_prefix = (
            "objects/entities/"
            if carrier == "homepage"
            else f"objects/posts/{carrier}/"
        )
        if (
            carrier not in CARRIERS
            or carrier in samples
            or not object_id
            or not object_ref.startswith(expected_prefix)
            or sample_id in sample_ids
            or object_id in object_ids
            or object_ref in object_refs
        ):
            raise ContentApiConsumerError(
                "content API consumer requires exactly one unique sample per carrier"
            )
        samples[carrier] = {
            "sampleId": sample_id,
            "carrier": carrier,
            "objectId": object_id,
            "objectRef": object_ref,
            "objectDigest": object_digest,
        }
        sample_ids.add(sample_id)
        object_ids.add(object_id)
        object_refs.add(object_ref)
    if set(samples) != set(CARRIERS) or len(raw_samples) != len(CARRIERS):
        raise ContentApiConsumerError(
            "content API consumer requires a baseline 1/1/1/1 sample plan"
        )

    raw_cells = plan.get("entryCarrierCells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 16:
        raise ContentApiConsumerError("sample plan must contain exactly 16 cells")
    cells: dict[str, dict[str, str]] = {}
    expected_pairs = [
        (entry, carrier) for entry in ENTRY_SURFACES for carrier in CARRIERS
    ]
    observed_pairs: list[tuple[str, str]] = []
    for index, row in enumerate(raw_cells):
        if not isinstance(row, Mapping):
            raise ContentApiConsumerError(f"sample plan cell {index} is invalid")
        entry = str(row.get("entry") or "")
        carrier = str(row.get("carrier") or "")
        pair = (entry, carrier)
        runner = str(row.get("runnerClass") or "").strip()
        if (
            pair not in expected_pairs
            or row.get("applicability") != "required"
            or not str(row.get("specRef") or "").startswith("specs/feature-tree/")
            or ".md#" not in str(row.get("specRef") or "")
            or _RUNNER_RE.fullmatch(runner) is None
            or runner != f"qwq.content_consumer.{entry}.{carrier}"
            or "reasonCode" in row
        ):
            raise ContentApiConsumerError(
                f"sample plan cell {entry or index}/{carrier or index} is not a "
                "required neutral content consumer cell"
            )
        key = f"{entry}:{carrier}"
        if key in cells:
            raise ContentApiConsumerError("sample plan contains duplicate matrix cells")
        cells[key] = {
            "entry": entry,
            "carrier": carrier,
            "specRef": str(row["specRef"]),
            "runnerClass": runner,
        }
        observed_pairs.append(pair)
    if observed_pairs != expected_pairs:
        raise ContentApiConsumerError("sample plan cell order or coverage drifted")
    return samples, cells, release_digest


def _validate_data_readiness(
    authority: _AuthorityFile,
    *,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    release_digest: str,
    manifest_digest: str,
) -> dict[str, Any]:
    readiness = authority.value
    observed_manifest_digest = _required_digest(
        readiness.get("manifestDigest"), label="Data readiness manifestDigest"
    )
    if observed_manifest_digest != manifest_digest:
        raise ContentApiConsumerError(
            "Data readiness manifestDigest drifted from explicit authority"
        )
    expected = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": "alpha",
        "releaseId": release_id,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "passed": True,
    }
    drift = [
        field for field, value in expected.items() if readiness.get(field) != value
    ]
    if drift:
        raise ContentApiConsumerError(
            "Data readiness identity/status drifted at " + ",".join(drift)
        )
    if (
        readiness.get("releaseKind") != "content"
        or readiness.get("sourceOwner") != "qwq_data"
    ):
        raise ContentApiConsumerError("Data readiness ownership drifted")
    entity_refs = readiness.get("entityRefs")
    post_ids = readiness.get("postIds")
    if (
        not isinstance(entity_refs, list)
        or not entity_refs
        or not isinstance(post_ids, list)
        or not post_ids
    ):
        raise ContentApiConsumerError("Data readiness object closure is incomplete")
    for field in (
        "contentImportReportRef",
        "homepageApiVerificationRef",
        "postApiVerificationRef",
    ):
        if not str(readiness.get(field) or "").strip():
            raise ContentApiConsumerError(f"Data readiness {field} is missing")
    return {
        **readiness,
        "_releaseDigest": release_digest,
        "_manifestDigest": observed_manifest_digest,
    }


def _validate_health(
    authority: _AuthorityFile,
    *,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    release_digest: str,
    manifest_digest: str,
    data_readiness_ref: str,
    data_readiness_digest: str,
) -> dict[str, Any]:
    health = authority.value
    expected = {
        "command": "health",
        "target": "alpha-local",
        "scope": "content-consumer",
    }
    drift = [field for field, value in expected.items() if health.get(field) != value]
    if drift:
        raise ContentApiConsumerError(
            "content-consumer health identity drifted at " + ",".join(drift)
        )
    if health.get("findings") != [] or health.get("generationIssues") not in (None, []):
        raise ContentApiConsumerError("content-consumer health contains findings")
    checks = health.get("checks")
    executed_checks = (
        [
            row
            for row in checks
            if isinstance(row, Mapping) and not bool(row.get("skipped"))
        ]
        if isinstance(checks, list)
        else []
    )
    if not executed_checks or any(row.get("ok") is not True for row in executed_checks):
        raise ContentApiConsumerError(
            "content-consumer health checks are not all healthy"
        )
    layers = health.get("userAvailability")
    if not isinstance(layers, list):
        raise ContentApiConsumerError("content-consumer health availability is missing")
    by_name = {
        str(row.get("name") or ""): row for row in layers if isinstance(row, Mapping)
    }
    if any(
        by_name.get(name, {}).get("status") != "ready"
        for name in _REQUIRED_HEALTH_LAYERS
    ):
        raise ContentApiConsumerError(
            "content-consumer health required layers are blocked"
        )
    content = health.get("userAvailabilityReport")
    content_evidence = (
        ((content.get("evidence") or {}).get("content") or {})
        if isinstance(content, Mapping)
        else {}
    )
    expected_content = {
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
    }
    if (
        not content_evidence
        or content_evidence.get("releaseId") != expected_content["releaseId"]
        or content_evidence.get("manifestDigest") != expected_content["manifestDigest"]
        or content_evidence.get("readinessReceiptRef") != data_readiness_ref
        or content_evidence.get("readinessReceiptDigest") != data_readiness_digest
        or content_evidence.get("releaseActive") is not True
        or content_evidence.get("exactQueriesReady") is not True
        or content_evidence.get("generationMatch") is not True
    ):
        raise ContentApiConsumerError(
            "content-consumer health release/readback identity drifted"
        )
    # If a newer health contract additionally projects direct identity, it must
    # agree; the canonical nested exact readiness binding remains sufficient for
    # existing receipts and proves import/verify identity transitively.
    optional_identity = {
        "environment": "alpha",
        "deploymentTarget": "alpha-local",
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "manifestDigest": manifest_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
    }
    for field, value in optional_identity.items():
        if field in health and health.get(field) != value:
            raise ContentApiConsumerError(
                f"content-consumer health direct identity drifted at {field}"
            )
    return health


def _ref_authority(
    ref: object,
    *,
    expected: str,
    label: str,
    root: Path,
) -> Path:
    observed = str(ref or "").strip()
    if observed != expected:
        raise ContentApiConsumerError(f"{label} must equal {expected}")
    resolved_root = root.resolve(strict=True)
    path = (resolved_root / observed).resolve(strict=True)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise ContentApiConsumerError(f"{label} escapes the authority root") from exc
    return path


def _load_import_mappings(
    readiness: Mapping[str, Any],
    *,
    output_root: Path,
    release_id: str,
    import_run_id: str,
    manifest_digest: str,
) -> tuple[dict[str, tuple[str, str]], dict[tuple[str, str, str], str], dict[str, str]]:
    expected_run_prefix = (
        Path("env/alpha/runs/data-release") / release_id / import_run_id
    ).as_posix()
    homepage_cases_path = _ref_authority(
        (Path(expected_run_prefix) / "homepage_verification_cases.json").as_posix(),
        expected=(
            Path(expected_run_prefix) / "homepage_verification_cases.json"
        ).as_posix(),
        label="homepage verification cases",
        root=output_root,
    )
    homepage_ref = str(readiness.get("homepageApiVerificationRef") or "")
    expected_homepage_ref = (
        Path("env/alpha/runs/data-release")
        / release_id
        / str(readiness.get("verifyRunId") or "")
        / "homepage-api-verification.json"
    ).as_posix()
    if homepage_ref != expected_homepage_ref:
        raise ContentApiConsumerError(
            "homepage API verification ref is not verify-run bound"
        )
    homepage_verification_path = _ref_authority(
        homepage_ref,
        expected=expected_homepage_ref,
        label="homepage API verification",
        root=output_root,
    )
    import_ref = str(readiness.get("contentImportReportRef") or "")
    expected_import_ref = (Path(expected_run_prefix) / "import.json").as_posix()
    import_path = _ref_authority(
        import_ref,
        expected=expected_import_ref,
        label="content import report",
        root=output_root,
    )

    try:
        cases = json.loads(_regular_bytes(homepage_cases_path, label="homepage cases"))
        homepage_verification = json.loads(
            _regular_bytes(
                homepage_verification_path, label="homepage API verification"
            )
        )
        import_report = json.loads(
            _regular_bytes(import_path, label="content import report")
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContentApiConsumerError("import mapping authority is not JSON") from exc
    if not all(
        isinstance(value, dict)
        for value in (cases, homepage_verification, import_report)
    ):
        raise ContentApiConsumerError("import mapping authority must contain objects")
    if (
        cases.get("schema") != "quwoquan_data.homepage_verification_case_manifest"
        or cases.get("environment") != "alpha"
        or cases.get("releaseId") != release_id
        or cases.get("runId") != import_run_id
        or homepage_verification.get("schema")
        != "quwoquan_data.homepage_api_verification"
        or homepage_verification.get("environment") != "alpha"
        or homepage_verification.get("releaseId") != release_id
        or homepage_verification.get("runId") != readiness.get("verifyRunId")
        or homepage_verification.get("passed") is not True
        or homepage_verification.get("issues") != []
        or import_report.get("schema") != "quwoquan.content_import_report"
        or import_report.get("environment") != "alpha"
        or import_report.get("releaseId") != release_id
        or import_report.get("status") != "imported"
        or import_report.get("manifestDigest") != manifest_digest
    ):
        raise ContentApiConsumerError(
            "import mapping authority identity/status drifted"
        )

    homepage_cases: dict[str, tuple[str, str]] = {}
    for row in cases.get("cases") or []:
        if not isinstance(row, Mapping):
            raise ContentApiConsumerError("homepage case row is invalid")
        entity_ref = str(row.get("entityRef") or "").strip()
        homepage_id = str(row.get("homepageId") or "").strip()
        title = str(row.get("title") or "").strip()
        if (
            not entity_ref
            or not homepage_id
            or not title
            or entity_ref in homepage_cases
        ):
            raise ContentApiConsumerError(
                "homepage case identity is invalid or duplicated"
            )
        homepage_cases[entity_ref] = (homepage_id, title)
    verified_homepages = {
        str(row.get("entityRef") or "").strip(): str(
            row.get("homepageId") or ""
        ).strip()
        for row in homepage_verification.get("entities") or []
        if isinstance(row, Mapping)
        and row.get("detailStatus") == 200
        and row.get("introductionStatus") == 200
    }
    if {key: value[0] for key, value in homepage_cases.items()} != verified_homepages:
        raise ContentApiConsumerError("homepage case/import readback mapping drifted")

    bindings: dict[tuple[str, str, str], str] = {}
    post_types: dict[str, str] = {}
    for row in import_report.get("postBindings") or []:
        if not isinstance(row, Mapping):
            raise ContentApiConsumerError("content import binding is invalid")
        content_id = str(row.get("contentId") or "").strip()
        post_ref = str(row.get("postRef") or "").strip()
        content_type = str(row.get("contentType") or "").strip()
        post_id = str(row.get("postId") or "").strip()
        key = (content_id, post_ref, content_type)
        if (
            not all(key)
            or not post_id
            or content_type not in {"article", "image", "video"}
            or key in bindings
            or post_id in post_types
        ):
            raise ContentApiConsumerError("content import binding identity drifted")
        bindings[key] = post_id
        post_types[post_id] = content_type
    if set(post_types) != {str(value) for value in readiness.get("postIds") or []}:
        raise ContentApiConsumerError("content import postIds drift from readiness")
    return homepage_cases, bindings, post_types


def _resolve_samples(
    samples: Mapping[str, Mapping[str, str]],
    *,
    readiness: Mapping[str, Any],
    output_root: Path,
    release_id: str,
    import_run_id: str,
    manifest_digest: str,
) -> dict[str, _Sample]:
    homepage_cases, post_bindings, _post_types = _load_import_mappings(
        readiness,
        output_root=output_root,
        release_id=release_id,
        import_run_id=import_run_id,
        manifest_digest=manifest_digest,
    )
    resolved: dict[str, _Sample] = {}
    for carrier in CARRIERS:
        sample = samples[carrier]
        source_id = sample["objectId"]
        object_ref = sample["objectRef"]
        if carrier == "homepage":
            normalized = source_id.strip("/")
            if normalized.startswith("entity/"):
                normalized = normalized.removeprefix("entity/")
            candidates = {
                source_id,
                "/entity/" + normalized,
                "entity/" + normalized,
            }
            matches = [
                homepage_cases[key] for key in candidates if key in homepage_cases
            ]
            if len(set(matches)) != 1:
                raise ContentApiConsumerError(
                    f"sample plan homepage {source_id} does not map exactly once"
                )
            runtime_id, query = matches[0]
        else:
            prefix = f"objects/posts/{carrier}/"
            if not object_ref.startswith(prefix):
                raise ContentApiConsumerError(
                    f"sample plan {carrier} objectRef is not canonical"
                )
            post_ref = object_ref.removeprefix("objects/posts/")
            runtime_id = post_bindings.get((source_id, post_ref, carrier), "")
            query = post_ref.rsplit("/", 1)[-1]
            if not runtime_id:
                raise ContentApiConsumerError(
                    f"sample plan {carrier} source identity lacks an exact "
                    "import mapping"
                )
        resolved[carrier] = _Sample(
            sample_id=sample["sampleId"],
            carrier=carrier,
            object_id=source_id,
            object_ref=object_ref,
            object_digest=sample["objectDigest"],
            runtime_object_id=runtime_id,
            query=query,
        )
    return resolved


def _topology_api_base(target: str) -> str:
    if target != "alpha-local":
        raise ContentApiConsumerError("target must be alpha-local")
    topology = load_environment_topology()
    target_payload = get_target(topology, target)
    if target_payload.get("env") != "alpha":
        raise ContentApiConsumerError("alpha-local topology environment drifted")
    public_bases = target_payload.get("publicBases")
    api_base = (
        str(public_bases.get("api") or "").strip().rstrip("/")
        if isinstance(public_bases, Mapping)
        else ""
    )
    parsed = urlsplit(api_base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ContentApiConsumerError(
            "environment topology target.publicBases.api must be canonical HTTPS"
        )
    return api_base


def _tls_ca_file(target: str) -> Path:
    try:
        path = root_certificate_path(target)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContentApiConsumerError(
            f"public_domain_tls CA is unavailable: {exc}"
        ) from exc
    if path.is_symlink() or not path.is_file():
        raise ContentApiConsumerError("public_domain_tls CA must be a regular file")
    return path


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


def _report_ref(path: Path, *, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return path.resolve().as_posix()


def _runtime_authority(health: Mapping[str, Any], *, target: str) -> dict[str, str]:
    candidate: Mapping[str, Any] = {}
    startup: Mapping[str, Any] = {}
    report = health.get("userAvailabilityReport")
    if isinstance(report, Mapping):
        evidence = report.get("evidence")
        if isinstance(evidence, Mapping):
            raw_candidate = evidence.get("candidate")
            if isinstance(raw_candidate, Mapping):
                candidate = raw_candidate
            runtime = evidence.get("runtime")
            if isinstance(runtime, Mapping) and isinstance(
                runtime.get("startupReceipt"), Mapping
            ):
                startup = runtime["startupReceipt"]
    baseline_id = str(candidate.get("baselineId") or "").strip()
    package_digest = str(candidate.get("packageDigest") or "").strip()
    source_revision = str(candidate.get("sourceRevision") or "").strip()
    configuration_digest = str(startup.get("configurationDigest") or "").strip()
    contract_graph_digest = ""
    candidate_manifest_sha = ""
    candidate_dir = str(candidate.get("candidateDir") or "").strip()
    if candidate_dir:
        manifest_path = Path(candidate_dir) / "manifest.json"
        try:
            manifest_raw = _regular_bytes(
                manifest_path, label="active candidate manifest"
            )
            manifest = json.loads(manifest_raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ContentApiConsumerError(
                "active candidate manifest is not JSON"
            ) from exc
        if not isinstance(manifest, Mapping):
            raise ContentApiConsumerError("active candidate manifest must be an object")
        if (
            manifest.get("target") != target
            or manifest.get("baselineId") != baseline_id
            or manifest.get("packageDigest") != package_digest
            or manifest.get("sourceRevision") != source_revision
        ):
            raise ContentApiConsumerError("active candidate manifest identity drifted")
        configuration_digest = str(
            configuration_digest or manifest.get("configurationDigest") or ""
        )
        contract_graph_digest = str(manifest.get("contractGraphDigest") or "")
        candidate_manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    if not baseline_id:
        raise ContentApiConsumerError(
            "content-consumer health lacks candidate baselineId"
        )
    if baseline_id.startswith("sha256:"):
        baseline_id = baseline_id.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", baseline_id) is None:
        raise ContentApiConsumerError("content-consumer health baselineId is invalid")
    _required_digest(package_digest, label="content-consumer health packageDigest")
    _required_digest(
        configuration_digest, label="content-consumer health configurationDigest"
    )
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_revision) is None:
        raise ContentApiConsumerError(
            "content-consumer health sourceRevision is invalid"
        )
    if not contract_graph_digest:
        graph = ROOT / "quwoquan_service/generated/contract_graph.json"
        contract_graph_digest = _digest_bytes(
            _regular_bytes(graph, label="canonical contract graph")
        )
    contract_graph_digest = _required_digest(
        contract_graph_digest, label="contract graph digest"
    )
    if not candidate_manifest_sha:
        candidate_manifest_sha = contract_graph_digest.removeprefix("sha256:")
    return {
        "baselineId": baseline_id,
        "packageDigest": package_digest,
        "configurationDigest": configuration_digest,
        "commitSha": source_revision,
        "contractGraphSourceHash": contract_graph_digest.removeprefix("sha256:"),
        "candidateManifestSha256": candidate_manifest_sha,
    }


def _write_regular_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ContentApiConsumerError(f"report output already exists: {path}")
    encoded = (
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


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
        "schema": CONTENT_API_CONSUMER_HEALTH_SCHEMA,
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
                "schema": CONTENT_API_CONSUMER_OBSERVATION_SCHEMA,
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
                    "slotId": required_raw_slot_id(
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
    source_fingerprint = derive_m1_source_fingerprint(
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
        "schema": CONTENT_API_CONSUMER_REPORT_SCHEMA,
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
