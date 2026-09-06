"""Exact-byte authorities and evidence I/O for the content API consumer.

This private helper owns authority validation, sample-to-runtime resolution,
runtime identity validation, and create-once evidence persistence.  The stable
consumer API remains in ``content_api_consumer``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

ROOT = Path(__file__).resolve().parents[3]
ENTRY_SURFACES = ("feed", "search", "recommendation", "direct_or_object_route")
CARRIERS = ("homepage", "article", "image", "video")
SPEC_REF = (
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/"
    "multi-carrier-release/spec.md#gwt-034"
)
SOURCE_FINGERPRINT_SCHEMA = "qwq.m1_api_consumer.source_fingerprint"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_RUNNER_RE = re.compile(
    r"^qwq\.content_consumer\."
    r"(feed|search|recommendation|direct_or_object_route)\."
    r"(homepage|article|image|video)\.v1$"
)
_REQUIRED_HEALTH_LAYERS = (
    "build_ready",
    "runtime_full_ready",
    "release_active",
    "content_exact_queries_ready",
)


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


def _consumer_error(message: str) -> ValueError:
    # Imported lazily so this private helper is independently importable while
    # the stable exception type continues to live in content_api_consumer.
    from quwoquan_ops.cli.lib.content_api_consumer import ContentApiConsumerError

    return ContentApiConsumerError(message)


def _content_text(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in ("\x00", "\n", "\r"))
    ):
        raise _consumer_error(f"{field} must be non-empty canonical text")
    return value


def _content_digest(value: object, *, field: str) -> str:
    text = _content_text(value, field=field)
    if _DIGEST_RE.fullmatch(text) is None:
        raise _consumer_error(f"{field} must be sha256:<64 lowercase hex>")
    return text


def _content_identity(value: object, *, field: str) -> str:
    text = _content_text(value, field=field)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", text) is None:
        raise _consumer_error(f"{field} has invalid identity format")
    return text


def _content_relative_ref(value: object, *, field: str) -> str:
    text = _content_text(value, field=field)
    ref = PurePosixPath(text)
    if (
        ref.is_absolute()
        or ref.as_posix() != text
        or any(part in {"", ".", ".."} for part in ref.parts)
        or "\\" in text
        or text.endswith("/latest")
        or "/latest/" in text
        or ref.name.startswith("latest.")
    ):
        raise _consumer_error(f"{field} must be an immutable contained relative ref")
    return text


def _content_canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _consumer_error("content authority is not canonical JSON") from exc


def content_consumer_raw_slot_id(
    *,
    target_uat_binding_digest: str | None = None,
    sample_id: str,
    entry_surface: str,
    carrier: str,
    spec_ref: str,
    runner_identity: str,
) -> str:
    """Derive one deterministic content sample/case raw-result slot ID."""

    material = {
        "sampleId": _content_identity(sample_id, field="sampleId"),
        "entrySurface": _content_text(entry_surface, field="entrySurface"),
        "carrier": _content_text(carrier, field="carrier"),
        "specRef": _content_text(spec_ref, field="specRef"),
        "runnerIdentity": _content_identity(
            runner_identity, field="runnerIdentity"
        ),
    }
    if target_uat_binding_digest is not None:
        material["targetUatBindingDigest"] = _content_digest(
            target_uat_binding_digest, field="targetUatBindingDigest"
        )
    return _digest_bytes(_content_canonical_bytes(material))


def _content_exact_ref(value: object, *, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise _consumer_error(f"{field} must contain exactly ref and digest")
    return {
        "ref": _content_relative_ref(value.get("ref"), field=f"{field}.ref"),
        "digest": _content_digest(value.get("digest"), field=f"{field}.digest"),
    }


def derive_content_consumer_source_fingerprint(
    *,
    schema: str,
    environment: str,
    target: str,
    release_id: str,
    release_digest: str,
    manifest_digest: str,
    import_run_id: str,
    verify_run_id: str,
    sample_plan: Mapping[str, Any],
    data_readiness: Mapping[str, Any],
    consumer_health: Mapping[str, Any],
    required_raw_results: Sequence[Mapping[str, Any]],
) -> str:
    """Derive the content consumer authority fingerprint from exact evidence."""

    source_schema = _content_text(schema, field="sourceFingerprint.schema")
    if source_schema != SOURCE_FINGERPRINT_SCHEMA:
        raise _consumer_error(
            "sourceFingerprint.schema must equal " + SOURCE_FINGERPRINT_SCHEMA
        )
    plan = _content_exact_ref(
        sample_plan, field="sourceFingerprint.samplePlan"
    )
    data = _content_exact_ref(
        data_readiness, field="sourceFingerprint.dataReadiness"
    )
    health = _content_exact_ref(
        consumer_health, field="sourceFingerprint.consumerHealth"
    )
    if isinstance(required_raw_results, (str, bytes)) or not required_raw_results:
        raise _consumer_error("sourceFingerprint.requiredRawResults must be non-empty")
    raw_results: list[dict[str, str]] = []
    for index, item in enumerate(required_raw_results):
        field = f"sourceFingerprint.requiredRawResults[{index}]"
        if (
            not isinstance(item, Mapping)
            or set(item) != {"ref", "digest", "slotId", "status"}
        ):
            raise _consumer_error(f"{field} fields are invalid")
        exact = _content_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")}, field=field
        )
        raw_results.append(
            {
                **exact,
                "slotId": _content_digest(
                    item.get("slotId"), field=f"{field}.slotId"
                ),
                "status": _content_text(
                    item.get("status"), field=f"{field}.status"
                ),
            }
        )
    material = {
        "schema": source_schema,
        "environment": _content_text(
            environment, field="sourceFingerprint.environment"
        ),
        "target": _content_identity(target, field="sourceFingerprint.target"),
        "releaseId": _content_identity(
            release_id, field="sourceFingerprint.releaseId"
        ),
        "releaseDigest": _content_digest(
            release_digest, field="sourceFingerprint.releaseDigest"
        ),
        "manifestDigest": _content_digest(
            manifest_digest, field="sourceFingerprint.manifestDigest"
        ),
        "importRunId": _content_identity(
            import_run_id, field="sourceFingerprint.importRunId"
        ),
        "verifyRunId": _content_identity(
            verify_run_id, field="sourceFingerprint.verifyRunId"
        ),
        "samplePlan": plan,
        "dataReadiness": data,
        "consumerHealth": health,
        "requiredRawResults": sorted(
            raw_results,
            key=lambda item: (
                item["slotId"], item["digest"], item["ref"], item["status"]
            ),
        ),
    }
    return _digest_bytes(_content_canonical_bytes(material))


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
        raise _consumer_error(
            f"{label} must use canonical sha256:<64 lowercase hex>"
        )
    return digest


def _required_identity(value: object, *, label: str) -> str:
    identity = str(value or "").strip()
    if _IDENTITY_RE.fullmatch(identity) is None:
        raise _consumer_error(f"{label} is not a canonical identity")
    return identity


def _regular_bytes(path: Path, *, label: str) -> bytes:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise _consumer_error(f"{label} must not be a symlink")
    try:
        before = candidate.stat()
    except OSError as exc:
        raise _consumer_error(f"{label} is unavailable: {candidate}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise _consumer_error(f"{label} must be a regular file")
    try:
        raw = candidate.read_bytes()
        after = candidate.stat()
    except OSError as exc:
        raise _consumer_error(f"{label} is unreadable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(raw) != after.st_size
    ):
        raise _consumer_error(f"{label} changed during read")
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
        raise _consumer_error(f"{label} ref must be repo/output-root relative")
    expected_digest = _required_digest(digest, label=f"{label} digest")
    resolved_root = root.expanduser().resolve(strict=True)
    candidate = resolved_root / relative
    try:
        resolved = candidate.resolve(strict=True)
        observed_ref = resolved.relative_to(resolved_root).as_posix()
    except (OSError, ValueError) as exc:
        raise _consumer_error(
            f"{label} ref escapes its authority root"
        ) from exc
    if observed_ref != relative.as_posix():
        raise _consumer_error(f"{label} ref is not canonical")
    raw = _regular_bytes(resolved, label=label)
    observed_digest = _digest_bytes(raw)
    if observed_digest != expected_digest:
        raise _consumer_error(
            f"{label} exact-byte digest drifted: expected {expected_digest}, "
            f"got {observed_digest}"
        )
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _consumer_error(f"{label} is not JSON") from exc
    if not isinstance(value, dict):
        raise _consumer_error(f"{label} must be a JSON object")
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
        raise _consumer_error("sample plan release identity drifted")
    release_digest = _required_digest(
        plan.get("releaseDigest"), label="sample plan releaseDigest"
    )
    raw_samples = plan.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise _consumer_error("sample plan samples are missing")
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
            raise _consumer_error(
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
            raise _consumer_error(
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
        raise _consumer_error(
            "content API consumer requires a baseline 1/1/1/1 sample plan"
        )

    raw_cells = plan.get("entryCarrierCells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 16:
        raise _consumer_error("sample plan must contain exactly 16 cells")
    cells: dict[str, dict[str, str]] = {}
    expected_pairs = [
        (entry, carrier) for entry in ENTRY_SURFACES for carrier in CARRIERS
    ]
    observed_pairs: list[tuple[str, str]] = []
    for index, row in enumerate(raw_cells):
        if not isinstance(row, Mapping):
            raise _consumer_error(f"sample plan cell {index} is invalid")
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
            or runner != f"qwq.content_consumer.{entry}.{carrier}.v1"
            or "reasonCode" in row
        ):
            raise _consumer_error(
                f"sample plan cell {entry or index}/{carrier or index} is not a "
                "required neutral content consumer cell"
            )
        key = f"{entry}:{carrier}"
        if key in cells:
            raise _consumer_error("sample plan contains duplicate matrix cells")
        cells[key] = {
            "entry": entry,
            "carrier": carrier,
            "specRef": str(row["specRef"]),
            "runnerClass": runner,
        }
        observed_pairs.append(pair)
    if observed_pairs != expected_pairs:
        raise _consumer_error("sample plan cell order or coverage drifted")
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
        raise _consumer_error(
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
        raise _consumer_error(
            "Data readiness identity/status drifted at " + ",".join(drift)
        )
    if (
        readiness.get("releaseKind") != "content"
        or readiness.get("sourceOwner") != "qwq_data"
    ):
        raise _consumer_error("Data readiness ownership drifted")
    entity_refs = readiness.get("entityRefs")
    post_ids = readiness.get("postIds")
    if (
        not isinstance(entity_refs, list)
        or not entity_refs
        or not isinstance(post_ids, list)
        or not post_ids
    ):
        raise _consumer_error("Data readiness object closure is incomplete")
    for field in (
        "contentImportReportRef",
        "homepageApiVerificationRef",
        "postApiVerificationRef",
    ):
        if not str(readiness.get(field) or "").strip():
            raise _consumer_error(f"Data readiness {field} is missing")
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
        raise _consumer_error(
            "content-consumer health identity drifted at " + ",".join(drift)
        )
    if health.get("findings") != [] or health.get("generationIssues") not in (None, []):
        raise _consumer_error("content-consumer health contains findings")
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
        raise _consumer_error(
            "content-consumer health checks are not all healthy"
        )
    layers = health.get("userAvailability")
    if not isinstance(layers, list):
        raise _consumer_error("content-consumer health availability is missing")
    by_name = {
        str(row.get("name") or ""): row for row in layers if isinstance(row, Mapping)
    }
    if any(
        by_name.get(name, {}).get("status") != "ready"
        for name in _REQUIRED_HEALTH_LAYERS
    ):
        raise _consumer_error(
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
        raise _consumer_error(
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
            raise _consumer_error(
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
        raise _consumer_error(f"{label} must equal {expected}")
    resolved_root = root.resolve(strict=True)
    path = (resolved_root / observed).resolve(strict=True)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise _consumer_error(f"{label} escapes the authority root") from exc
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
        raise _consumer_error(
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
        raise _consumer_error("import mapping authority is not JSON") from exc
    if not all(
        isinstance(value, dict)
        for value in (cases, homepage_verification, import_report)
    ):
        raise _consumer_error("import mapping authority must contain objects")
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
        raise _consumer_error(
            "import mapping authority identity/status drifted"
        )

    homepage_cases: dict[str, tuple[str, str]] = {}
    for row in cases.get("cases") or []:
        if not isinstance(row, Mapping):
            raise _consumer_error("homepage case row is invalid")
        entity_ref = str(row.get("entityRef") or "").strip()
        homepage_id = str(row.get("homepageId") or "").strip()
        title = str(row.get("title") or "").strip()
        if (
            not entity_ref
            or not homepage_id
            or not title
            or entity_ref in homepage_cases
        ):
            raise _consumer_error(
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
        raise _consumer_error("homepage case/import readback mapping drifted")

    bindings: dict[tuple[str, str, str], str] = {}
    post_types: dict[str, str] = {}
    for row in import_report.get("postBindings") or []:
        if not isinstance(row, Mapping):
            raise _consumer_error("content import binding is invalid")
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
            raise _consumer_error("content import binding identity drifted")
        bindings[key] = post_id
        post_types[post_id] = content_type
    if set(post_types) != {str(value) for value in readiness.get("postIds") or []}:
        raise _consumer_error("content import postIds drift from readiness")
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
                raise _consumer_error(
                    f"sample plan homepage {source_id} does not map exactly once"
                )
            runtime_id, query = matches[0]
        else:
            prefix = f"objects/posts/{carrier}/"
            if not object_ref.startswith(prefix):
                raise _consumer_error(
                    f"sample plan {carrier} objectRef is not canonical"
                )
            post_ref = object_ref.removeprefix("objects/posts/")
            runtime_id = post_bindings.get((source_id, post_ref, carrier), "")
            query = post_ref.rsplit("/", 1)[-1]
            if not runtime_id:
                raise _consumer_error(
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
        raise _consumer_error("target must be alpha-local")
    topology = load_environment_topology()
    target_payload = get_target(topology, target)
    if target_payload.get("env") != "alpha":
        raise _consumer_error("alpha-local topology environment drifted")
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
        raise _consumer_error(
            "environment topology target.publicBases.api must be canonical HTTPS"
        )
    return api_base


def _tls_ca_file(target: str) -> Path:
    try:
        path = root_certificate_path(target)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _consumer_error(
            f"public_domain_tls CA is unavailable: {exc}"
        ) from exc
    if path.is_symlink() or not path.is_file():
        raise _consumer_error("public_domain_tls CA must be a regular file")
    return path


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
            raise _consumer_error(
                "active candidate manifest is not JSON"
            ) from exc
        if not isinstance(manifest, Mapping):
            raise _consumer_error("active candidate manifest must be an object")
        if (
            manifest.get("target") != target
            or manifest.get("baselineId") != baseline_id
            or manifest.get("packageDigest") != package_digest
            or manifest.get("sourceRevision") != source_revision
        ):
            raise _consumer_error("active candidate manifest identity drifted")
        configuration_digest = str(
            configuration_digest or manifest.get("configurationDigest") or ""
        )
        contract_graph_digest = str(manifest.get("contractGraphDigest") or "")
        candidate_manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    if not baseline_id:
        raise _consumer_error(
            "content-consumer health lacks candidate baselineId"
        )
    if baseline_id.startswith("sha256:"):
        baseline_id = baseline_id.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", baseline_id) is None:
        raise _consumer_error("content-consumer health baselineId is invalid")
    _required_digest(package_digest, label="content-consumer health packageDigest")
    _required_digest(
        configuration_digest, label="content-consumer health configurationDigest"
    )
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_revision) is None:
        raise _consumer_error(
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
        raise _consumer_error(f"report output already exists: {path}")
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
