#!/usr/bin/env python3
"""Render one fail-closed release-bound environment identity projection."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    canonical_candidate_digest,
    canonical_manifest_digest,
    validate_application_package_evidence,
    validate_manifest,
    validate_manifest_files,
)
from quwoquan_ops.ci.release_bound_data_evidence import (
    DataEvidenceError,
    validate_data_evidence,
)


SCHEMA = "qwq.release-bound-environment-identity"
ENVIRONMENT_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
EXPECTED_DEVICE_PROFILES = {
    "alpha": {"android-simulator", "android-physical", "ios-simulator"},
    "beta": {"android-simulator", "android-physical", "ios-simulator"},
    "gamma": {"android-simulator", "android-physical", "ios-simulator"},
    "prod": {"android-physical", "ios-physical"},
}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
TREE_DIGEST = re.compile(r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
SYNTHETIC_MARKERS = (
    "local",
    "localhost",
    "127.0.0.1",
    "mock",
    "memory",
    "fixture",
    "noop",
    "synthetic",
    ".invalid",
)
SPEC_REFS = (
    "specs/feature-tree/spec.md#uat-003",
    "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
    (
        "specs/feature-tree/runtime/runtime-client-foundation/"
        "cold-start-performance/spec.md#gwt-004"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-001"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-002"
    ),
)
READINESS_COUNTS = {
    "entities",
    "posts",
    "creators",
    "avatarAssets",
    "imageAssets",
    "tags",
    "mediaAssets",
    "discoveryPosts",
    "premiumPlayableVideos",
}
FEED_QUERY_NAMES = {
    "discovery_work",
    "typed_article",
    "typed_image",
    "typed_video",
    "homepage_recommend",
    "premium_stream",
}
RUN_RECEIPT_FIELDS = {
    "schema",
    "environment",
    "releaseId",
    "runId",
    "status",
    "homepageVerificationCasesRef",
    "tagImportReportRef",
    "creatorImportReportRef",
    "contentImportReportRef",
    "homepageImportReportRef",
    "verificationChecksum",
}
ROLLBACK_FIELDS = {
    "schema",
    "environment",
    "sourceOwner",
    "exitRunId",
    "originalReleaseId",
    "originalManifestDigest",
    "originalImportRunId",
    "originalVerifyRunId",
    "originalImportResultRef",
    "originalVerifyResultRef",
    "rollbackToReleaseId",
    "rollbackToManifestDigest",
    "rollbackRunId",
    "rollbackVerifyRunId",
    "rollbackResultRef",
    "rollbackVerifyResultRef",
    "replayImportRunId",
    "replayVerifyRunId",
    "replayManifestDigest",
    "replayImportResultRef",
    "replayVerifyResultRef",
    "recordedAt",
    "verificationChecksum",
    "passed",
}


class IdentityEvidenceError(ValueError):
    """Evidence cannot support a release-bound environment identity."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--environment", required=True, choices=tuple(ENVIRONMENT_TARGETS))
    parser.add_argument("--target", required=True, choices=tuple(ENVIRONMENT_TARGETS.values()))
    parser.add_argument("--release-evidence-manifest", required=True, type=Path)
    parser.add_argument("--data-output-root", required=True, type=Path)
    parser.add_argument("--release-readiness", required=True, type=Path)
    parser.add_argument("--import-receipt", required=True, type=Path)
    parser.add_argument("--replay-receipt", required=True, type=Path)
    parser.add_argument("--effective-launch-manifest", required=True, type=Path)
    parser.add_argument(
        "--app-artifact-receipt", required=True, action="append", type=Path
    )
    parser.add_argument("--startup-device-case-result", required=True, type=Path)
    parser.add_argument("--telemetry-readback", required=True, type=Path)
    parser.add_argument("--rollback-receipt", required=True, type=Path)
    parser.add_argument("--release-video-delivery", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _read(path: Path, label: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_file():
        raise IdentityEvidenceError(f"{label} is missing or is not a regular file: {path}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityEvidenceError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise IdentityEvidenceError(f"{label} must contain a JSON object")
    return payload


def _sha256(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_file():
        raise IdentityEvidenceError(f"evidence is missing or unsafe: {path}")
    digest = hashlib.sha256()
    with resolved.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _evidence_ref(path: Path, *, digest: str | None = None) -> dict[str, str]:
    return {
        "ref": path.expanduser().resolve().as_posix(),
        "sha256": digest or _sha256(path),
    }


def _required_text(payload: dict[str, Any], field: str, label: str) -> str:
    value = str(payload.get(field) or "").strip()
    if value in {"", "unknown"}:
        raise IdentityEvidenceError(f"{label}.{field} is missing or unknown")
    return value


def _require_digest(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if DIGEST.fullmatch(normalized) is None:
        raise IdentityEvidenceError(f"{label} is not a sha256 identity")
    return normalized


def _require_counts(payload: dict[str, Any], label: str) -> None:
    required = payload.get("required")
    executed = payload.get("executed")
    if not isinstance(required, int) or required <= 0:
        raise IdentityEvidenceError(f"{label}.required must be greater than zero")
    if not isinstance(executed, int) or executed <= 0:
        raise IdentityEvidenceError(f"{label}.executed must be greater than zero")
    if executed != required:
        raise IdentityEvidenceError(f"{label}.executed must equal required")
    if payload.get("skipped") != 0 or payload.get("failed") != 0:
        raise IdentityEvidenceError(f"{label} contains skipped or failed cases")


def _require_spec_refs(payload: dict[str, Any], label: str) -> None:
    refs = payload.get("specRefs")
    if not isinstance(refs, list) or set(refs) != set(SPEC_REFS):
        raise IdentityEvidenceError(f"{label}.specRefs are incomplete or non-canonical")


def _require_public_https(value: Any, label: str, *, origin: bool) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    hostname = str(parsed.hostname or "").lower()
    if (
        not normalized
        or parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (origin and (parsed.path not in {"", "/"} or parsed.params))
        or (not origin and parsed.params)
        or hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith((".local", ".invalid", ".test", ".example"))
    ):
        raise IdentityEvidenceError(f"{label} is not a canonical public HTTPS URL")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise IdentityEvidenceError(f"{label} resolves to a non-public address literal")
    return normalized


def _verify_checksum(payload: dict[str, Any], label: str) -> None:
    declared = payload.get("verificationChecksum")
    if declared is None:
        raise IdentityEvidenceError(f"{label}.verificationChecksum is missing")
    unsigned = dict(payload)
    unsigned.pop("verificationChecksum", None)
    if declared != _canonical_digest(unsigned):
        raise IdentityEvidenceError(f"{label}.verificationChecksum drift")


def _validate_release_manifest(
    payload: dict[str, Any], *, environment: str
) -> tuple[str, str, str]:
    allowed_statuses = {"candidate-ready", "deployable", "released"}
    try:
        validate_manifest(payload, allowed_statuses=allowed_statuses)
    except ValueError as exc:
        raise IdentityEvidenceError(
            f"ReleaseEvidenceManifest is not canonical: {exc}"
        ) from exc
    if environment == "prod" and payload.get("status") == "candidate-ready":
        raise IdentityEvidenceError("Prod requires a deployable or released manifest")
    candidate_id = _require_digest(payload.get("candidateId"), "candidateId")
    artifact_digest = _require_digest(payload.get("artifactDigest"), "artifactDigest")
    try:
        expected_candidate = canonical_candidate_digest(payload)
        expected_artifact = canonical_manifest_digest(payload)
    except ValueError as exc:
        raise IdentityEvidenceError(f"ReleaseEvidenceManifest is incomplete: {exc}") from exc
    if candidate_id != expected_candidate or artifact_digest != expected_artifact:
        raise IdentityEvidenceError("ReleaseEvidenceManifest seal drift")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise IdentityEvidenceError("ReleaseEvidenceManifest.source is missing")
    git_sha = str(source.get("gitSha") or "")
    tree_digest = str(source.get("treeDigest") or "")
    if GIT_SHA.fullmatch(git_sha) is None or TREE_DIGEST.fullmatch(tree_digest) is None:
        raise IdentityEvidenceError("ReleaseEvidenceManifest source revision is invalid")
    packages = payload.get("applicationPackages")
    if not isinstance(packages, dict) or not isinstance(packages.get(environment), dict):
        raise IdentityEvidenceError("ReleaseEvidenceManifest App packages are missing")
    return candidate_id, git_sha, tree_digest


def _validate_readiness(
    payload: dict[str, Any], *, environment: str
) -> dict[str, Any]:
    if (
        payload.get("schema") != "quwoquan_data.environment_release_readiness"
        or payload.get("passed") is not True
        or payload.get("environment") != environment
        or payload.get("releaseKind") != "content"
        or payload.get("sourceOwner") != "qwq_data"
    ):
        raise IdentityEvidenceError("release-readiness is not a passed Data receipt")
    _verify_checksum(payload, "release-readiness")
    counts = payload.get("counts")
    if (
        not isinstance(counts, dict)
        or set(counts) != READINESS_COUNTS
        or any(not isinstance(value, int) or value <= 0 for value in counts.values())
    ):
        raise IdentityEvidenceError("release-readiness counts are incomplete")
    object_fields = {
        "entityRefs": "entities",
        "postIds": "posts",
        "creatorIds": "creators",
        "tagRefs": "tags",
        "mediaAssetIds": "mediaAssets",
    }
    objects: dict[str, list[str]] = {}
    for field, count_field in object_fields.items():
        values = payload.get(field)
        if (
            not isinstance(values, list)
            or len(values) != counts[count_field]
            or len(values) != len(set(values))
            or any(not isinstance(value, str) or not value.strip() for value in values)
        ):
            raise IdentityEvidenceError(f"release-readiness.{field} is incomplete")
        objects[field] = list(values)
    if (
        counts["avatarAssets"] != counts["creators"]
        or counts["discoveryPosts"] > counts["posts"]
        or counts["premiumPlayableVideos"] > counts["posts"]
    ):
        raise IdentityEvidenceError("release-readiness discovery/media counts exceed posts")
    queries = payload.get("feedQueries")
    if not isinstance(queries, list) or len(queries) != len(FEED_QUERY_NAMES):
        raise IdentityEvidenceError("release-readiness feedQueries are incomplete")
    normalized_queries: list[dict[str, Any]] = []
    for query in queries:
        if not isinstance(query, dict) or not {
            "name",
            "path",
            "query",
            "status",
            "releaseBound",
            "matchedPostIds",
        }.issubset(query):
            raise IdentityEvidenceError("release-readiness feed query is not canonical")
        matched = query.get("matchedPostIds")
        if (
            query.get("name") not in FEED_QUERY_NAMES
            or query.get("path") != "/content/feed"
            or not str(query.get("query") or "").strip()
            or query.get("status") != 200
            or query.get("releaseBound") is not True
            or not isinstance(matched, list)
            or not matched
            or len(matched) != len(set(matched))
            or not set(matched).issubset(objects["postIds"])
        ):
            raise IdentityEvidenceError("release-readiness feed query did not prove exact readback")
        normalized_queries.append(
            {"name": query["name"], "query": query["query"], "matchedPostIds": matched}
        )
    if {query["name"] for query in normalized_queries} != FEED_QUERY_NAMES:
        raise IdentityEvidenceError("release-readiness feed query names are incomplete")
    prefix = f"env/{environment}/runs/data-release/"
    for field in (
        "contentImportReportRef",
        "creatorAttributionRef",
        "tagAttributionRef",
        "homepageApiVerificationRef",
        "postApiVerificationRef",
    ):
        if not _required_text(payload, field, "release-readiness").startswith(prefix):
            raise IdentityEvidenceError(f"release-readiness.{field} is not environment-owned")
    media_manifest_ref = _required_text(payload, "mediaManifestRef", "release-readiness")
    if not re.fullmatch(r"data/releases/.+/payload/media_manifest\.json", media_manifest_ref):
        raise IdentityEvidenceError("release-readiness.mediaManifestRef is not canonical")
    _required_text(payload, "verifiedAt", "release-readiness")
    return {
        "releaseId": _required_text(payload, "releaseId", "release-readiness"),
        "releaseDigest": _require_digest(
            payload.get("manifestDigest"), "release-readiness.manifestDigest"
        ),
        "importRunId": _required_text(payload, "importRunId", "release-readiness"),
        "verifyRunId": _required_text(payload, "verifyRunId", "release-readiness"),
        "counts": dict(counts),
        "objects": objects,
        "feedQueries": sorted(normalized_queries, key=lambda item: item["name"]),
        "mediaProbe": {
            "mediaManifestDigest": _require_digest(
                payload.get("mediaManifestDigest"),
                "release-readiness.mediaManifestDigest",
            ),
            "mediaManifestRef": media_manifest_ref,
            "mediaAssetIds": objects["mediaAssetIds"],
            "avatarAssets": counts["avatarAssets"],
            "imageAssets": counts["imageAssets"],
            "premiumPlayableVideos": counts["premiumPlayableVideos"],
        },
    }


def _validate_run_receipt(
    payload: dict[str, Any], *, label: str, environment: str, release_id: str
) -> str:
    if (
        payload.get("schema") != "quwoquan_data.environment_release_result"
        or payload.get("environment") != environment
        or payload.get("releaseId") != release_id
        or payload.get("status") != "completed"
    ):
        raise IdentityEvidenceError(f"{label} is not a completed environment release result")
    if set(payload) != RUN_RECEIPT_FIELDS:
        raise IdentityEvidenceError(f"{label} fields are not canonical")
    _verify_checksum(payload, label)
    prefix = f"env/{environment}/runs/data-release/{release_id}/"
    for field in (
        "homepageVerificationCasesRef",
        "tagImportReportRef",
        "creatorImportReportRef",
        "contentImportReportRef",
        "homepageImportReportRef",
    ):
        if not _required_text(payload, field, label).startswith(prefix):
            raise IdentityEvidenceError(f"{label}.{field} is not release-owned")
    return _required_text(payload, "runId", label)


def _validate_rollback(
    payload: dict[str, Any],
    *,
    environment: str,
    release_id: str,
    release_digest: str,
    import_run_id: str,
    verify_run_id: str,
    replay_run_id: str,
) -> dict[str, str]:
    if (
        payload.get("schema") != "quwoquan_data.environment_release_lifecycle_exit"
        or payload.get("passed") is not True
        or payload.get("environment") != environment
        or payload.get("sourceOwner") != "qwq_data"
    ):
        raise IdentityEvidenceError("rollback receipt is not a passed lifecycle Exit receipt")
    if set(payload) != ROLLBACK_FIELDS:
        raise IdentityEvidenceError("rollback receipt fields are not canonical")
    _verify_checksum(payload, "rollback-receipt")
    exact = {
        "originalReleaseId": release_id,
        "originalManifestDigest": release_digest,
        "originalImportRunId": import_run_id,
        "originalVerifyRunId": verify_run_id,
        "replayImportRunId": replay_run_id,
        "replayManifestDigest": release_digest,
    }
    for field, expected in exact.items():
        if payload.get(field) != expected:
            raise IdentityEvidenceError(f"rollback-receipt.{field} drift")
    rollback_release = _required_text(payload, "rollbackToReleaseId", "rollback-receipt")
    if rollback_release == release_id:
        raise IdentityEvidenceError("rollback target must be a distinct release")
    for field in (
        "exitRunId",
        "rollbackRunId",
        "rollbackVerifyRunId",
        "replayVerifyRunId",
        "originalImportResultRef",
        "originalVerifyResultRef",
        "rollbackResultRef",
        "rollbackVerifyResultRef",
        "replayImportResultRef",
        "replayVerifyResultRef",
    ):
        _required_text(payload, field, "rollback-receipt")
    rollback_digest = _require_digest(
        payload.get("rollbackToManifestDigest"),
        "rollback-receipt.rollbackToManifestDigest",
    )
    return {
        "exitRunId": str(payload["exitRunId"]),
        "rollbackReleaseId": rollback_release,
        "rollbackReleaseDigest": rollback_digest,
        "rollbackRunId": str(payload["rollbackRunId"]),
        "replayRunId": replay_run_id,
    }


def _validate_launch_manifest(
    payload: dict[str, Any], *, environment: str, target: str
) -> tuple[str, str]:
    expected_fields = {
        "schema",
        "environment",
        "target",
        "entrypoint",
        "launchMode",
        "dartDefinesDigest",
        "runtimeConfigDigest",
        "recoveryBaseUrl",
        "publicWebBaseUrl",
        "appDownloadBaseUrl",
        "requiresLocalTransport",
        "transport",
    }
    if set(payload) != expected_fields:
        raise IdentityEvidenceError("effective launch manifest fields are not canonical")
    if (
        payload.get("schema") != "app-effective-launch-manifest"
        or payload.get("environment") != environment
        or payload.get("target") != target
        or payload.get("entrypoint") != "lib/main_prod.dart"
    ):
        raise IdentityEvidenceError("effective launch manifest identity drift")
    launch_mode = _required_text(payload, "launchMode", "effective launch manifest")
    _require_digest(payload.get("dartDefinesDigest"), "dartDefinesDigest")
    _require_digest(payload.get("runtimeConfigDigest"), "runtimeConfigDigest")
    _require_public_https(
        payload.get("recoveryBaseUrl"),
        "effective launch manifest.recoveryBaseUrl",
        origin=True,
    )
    _require_public_https(
        payload.get("publicWebBaseUrl"),
        "effective launch manifest.publicWebBaseUrl",
        origin=True,
    )
    _require_public_https(
        payload.get("appDownloadBaseUrl"),
        "effective launch manifest.appDownloadBaseUrl",
        origin=False,
    )
    transport = payload.get("transport")
    if not isinstance(transport, dict) or set(transport) != {
        "required",
        "reverseExpectedPorts",
        "reverseActualPorts",
        "reverseReceiptDigest",
        "consumerLeaseId",
    }:
        raise IdentityEvidenceError("effective launch transport is not canonical")
    if environment == "prod":
        if payload.get("requiresLocalTransport") is not False or any(
            value for key, value in transport.items() if key != "required"
        ) or transport.get("required") is not False:
            raise IdentityEvidenceError("Prod launch manifest contains local transport")
    else:
        if payload.get("requiresLocalTransport") is not True or transport.get("required") is not True:
            raise IdentityEvidenceError("local environment runtime transport receipt is missing")
        if transport.get("reverseExpectedPorts") != transport.get("reverseActualPorts"):
            raise IdentityEvidenceError("local environment reverse port receipt drift")
        _require_digest(transport.get("reverseReceiptDigest"), "reverseReceiptDigest")
        _require_digest(transport.get("consumerLeaseId"), "consumerLeaseId")
    return _canonical_digest(payload), launch_mode


def _validate_app_receipts(
    paths: list[Path],
    payloads: list[dict[str, Any]],
    *,
    manifest: dict[str, Any],
    environment: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    artifacts: dict[str, str] = {}
    evidence: list[dict[str, str]] = []
    descriptors = manifest["applicationPackages"][environment]
    for path, payload in zip(paths, payloads, strict=True):
        surface = (
            "android"
            if environment == "prod"
            and payload.get("schema") == "qwq.android.official-release"
            else _required_text(payload, "surface", "app-artifact-receipt")
        )
        if surface not in {"android", "ios"} or surface in artifacts:
            raise IdentityEvidenceError("App artifact receipt surface is unsupported or duplicated")
        try:
            package_digest = validate_application_package_evidence(
                payload,
                manifest=manifest,
                environment=environment,
                surface=surface,
            )
        except ValueError as exc:
            raise IdentityEvidenceError(
                f"App artifact receipt is not canonical for {environment}/{surface}: {exc}"
            ) from exc
        descriptor = descriptors.get(surface)
        if not isinstance(descriptor, dict):
            raise IdentityEvidenceError(f"ReleaseEvidenceManifest lacks {surface} App package")
        receipt_digest = _sha256(path)
        if (
            descriptor.get("packageDigest") != package_digest
            or descriptor.get("digest") != receipt_digest
        ):
            raise IdentityEvidenceError(f"{surface} App artifact differs from sealed manifest")
        artifacts[surface] = package_digest
        evidence.append(
            {
                "surface": surface,
                "ref": path.expanduser().resolve().as_posix(),
                "sha256": receipt_digest,
            }
        )
    if set(artifacts) != {"android", "ios"}:
        raise IdentityEvidenceError("Android and iOS App artifact receipts are both required")
    return artifacts, sorted(evidence, key=lambda item: item["surface"])


def _validate_case_result(
    payload: dict[str, Any],
    *,
    baseline_id: str,
    release_id: str,
    release_digest: str,
    source_git_sha: str,
    source_tree_digest: str,
    environment: str,
    target: str,
    launch_digest: str,
    launch_mode: str,
    app_artifacts: dict[str, str],
) -> tuple[list[str], list[dict[str, str]]]:
    if payload.get("schema") != "qwq.startup-environment-case-result" or payload.get("status") != "passed":
        raise IdentityEvidenceError("startup/device CaseResult is not passed")
    _require_counts(payload, "startup/device CaseResult")
    _require_spec_refs(payload, "startup/device CaseResult")
    exact = {
        "baselineId": baseline_id,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
    }
    for field, expected in exact.items():
        if payload.get(field) != expected:
            raise IdentityEvidenceError(f"startup/device CaseResult {field} drift")
    if payload.get("applicationArtifacts") != app_artifacts:
        raise IdentityEvidenceError("startup/device CaseResult App artifact drift")
    packages = payload.get("packages")
    package = packages.get(environment) if isinstance(packages, dict) else None
    if not isinstance(package, dict) or (
        package.get("status") != "component_ready"
        or package.get("runtimeTarget") != target
        or package.get("effectiveLaunchManifestDigest") != launch_digest
    ):
        raise IdentityEvidenceError("startup/device CaseResult package identity drift")
    runtime_evidence = payload.get("runtimeEvidence")
    readback_evidence = payload.get("readbackEvidence")
    if not isinstance(runtime_evidence, dict) or not isinstance(readback_evidence, dict):
        raise IdentityEvidenceError("startup/device runtime or readback evidence is missing")
    profiles = EXPECTED_DEVICE_PROFILES[environment]
    attempts: list[str] = []
    devices: list[dict[str, str]] = []
    for profile in sorted(profiles):
        key = f"{target}/{profile}"
        wrapper = runtime_evidence.get(key)
        readback_wrapper = readback_evidence.get(key)
        runtime = wrapper.get("evidence") if isinstance(wrapper, dict) else None
        readback = (
            readback_wrapper.get("evidence")
            if isinstance(readback_wrapper, dict)
            else None
        )
        if (
            not isinstance(wrapper, dict)
            or wrapper.get("status") != "passed"
            or not isinstance(runtime, dict)
            or runtime.get("schema") != "qwq.startup-runtime-evidence"
            or runtime.get("passed") is not True
        ):
            raise IdentityEvidenceError(f"startup runtime evidence is not passed: {profile}")
        _require_spec_refs(runtime, f"startup runtime {profile}")
        for field, expected in (
            ("baselineId", baseline_id),
            ("releaseId", release_id),
            ("releaseDigest", release_digest),
            ("runtimeEnv", environment),
            ("runtimeTarget", target),
        ):
            if runtime.get(field) != expected:
                raise IdentityEvidenceError(f"startup runtime {profile} {field} drift")
        platform = profile.split("-", 1)[0]
        expected_device_kind = (
            "simulator"
            if profile.endswith("-simulator")
            else ("physical" if profile == "ios-physical" else "true_device")
        )
        if runtime.get("platform") != platform:
            raise IdentityEvidenceError(f"startup runtime {profile} platform drift")
        samples = runtime.get("samples")
        if not isinstance(samples, list) or not samples or runtime.get("runs") != len(samples):
            raise IdentityEvidenceError(f"startup runtime {profile} has no real samples")
        expected_runs = 20 if environment == "prod" else None
        if expected_runs is not None and len(samples) != expected_runs:
            raise IdentityEvidenceError(
                f"startup runtime {profile} must contain exactly {expected_runs} cold starts"
            )
        profile_device_ids: set[str] = set()
        for sample in samples:
            if not isinstance(sample, dict) or sample.get("passed") is not True:
                raise IdentityEvidenceError(f"startup runtime {profile} sample did not pass")
            attempt = _required_text(sample, "attemptId", f"startup runtime {profile}")
            device_id = _required_text(sample, "deviceId", f"startup runtime {profile}")
            for field, expected in (
                ("runtimeEnv", environment),
                ("runtimeTarget", target),
                ("platform", platform),
                ("deviceKind", expected_device_kind),
                ("effectiveLaunchManifestDigest", launch_digest),
                ("launchMode", launch_mode),
                ("runtimeConfigurationState", "complete"),
                ("canonicalTerminal", "routerShell"),
            ):
                if sample.get(field) != expected:
                    raise IdentityEvidenceError(
                        f"startup runtime {profile} sample {field} drift"
                    )
            _required_text(sample, "sourceReport", f"startup runtime {profile}")
            _required_text(sample, "launchMode", f"startup runtime {profile}")
            if (
                sample.get("missingDefineKeys") not in (None, [])
                or not isinstance(sample.get("failureCode"), str)
                or sample.get("hotRestart") is not False
                or sample.get("watchdogOutcome") == "native_recovery"
                or sample.get("startupSequenceMotionCurrent") is not True
                or sample.get("telemetryAcknowledged") is not True
            ):
                raise IdentityEvidenceError(
                    f"startup runtime {profile} sample terminal/motion/telemetry is invalid"
                )
            for field in (
                "rendererFirstFrameMs",
                "safeTerminalMs",
                "reportedSafeTerminalMs",
                "nativeReceivedSafeTerminalMs",
            ):
                value = sample.get(field)
                if not isinstance(value, (int, float)) or value > 6000:
                    raise IdentityEvidenceError(
                        f"startup runtime {profile} sample {field} is invalid"
                    )
            if platform == "android":
                resolution = sample.get("launcherResolution")
                task_snapshot = sample.get("taskSnapshot")
                visual = sample.get("launchVisual")
                if (
                    sample.get("launcherIntentUsed") is not True
                    or sample.get("launcherStarted") is not True
                    or not isinstance(resolution, dict)
                    or resolution.get("matchesExpectedGate") is not True
                    or sample.get("gateMainOrderObserved") is not True
                    or not isinstance(task_snapshot, dict)
                    or task_snapshot.get("singleMainTask") is not True
                    or task_snapshot.get("mainActivityInstances") != 1
                    or not isinstance(visual, dict)
                    or visual.get("contractVerified") is not True
                    or re.fullmatch(r"[0-9a-f]{64}", str(visual.get("sourceDigest") or "")) is None
                ):
                    raise IdentityEvidenceError(
                        f"startup runtime {profile} Android launcher provenance is invalid"
                    )
            elif (
                sample.get("sceneLaunchUsed") is not True
                or sample.get("sceneStarted") is not True
                or sample.get("sceneLauncher")
                != (
                    "xcrun_simctl"
                    if profile == "ios-simulator"
                    else "xcrun_devicectl"
                )
            ):
                raise IdentityEvidenceError(
                    f"startup runtime {profile} iOS scene provenance is invalid"
                )
            attempts.append(attempt)
            profile_device_ids.add(device_id)
        if len(profile_device_ids) != 1:
            raise IdentityEvidenceError(
                f"startup runtime {profile} cold-start series changes device identity"
            )
        profile_device_id = next(iter(profile_device_ids))
        devices.append(
            {
                "profile": profile,
                "platform": platform,
                "deviceId": profile_device_id,
            }
        )
        if (
            not isinstance(readback_wrapper, dict)
            or readback_wrapper.get("status") != "passed"
            or not isinstance(readback, dict)
            or readback.get("schema") != "qwq.app-core-readback-evidence"
            or readback.get("status") != "passed"
        ):
            raise IdentityEvidenceError(f"App readback evidence is not passed: {profile}")
        _require_counts(readback, f"App readback {profile}")
        _require_spec_refs(readback, f"App readback {profile}")
        for field, expected in (
            ("baselineId", baseline_id),
            ("releaseId", release_id),
            ("releaseDigest", release_digest),
            ("environment", environment),
            ("target", target),
            ("platform", platform),
            ("effectiveLaunchManifestDigest", launch_digest),
        ):
            if readback.get(field) != expected:
                raise IdentityEvidenceError(f"App readback {profile} {field} drift")
        if (
            readback.get("deviceKind") != expected_device_kind
            or _required_text(readback, "deviceId", f"App readback {profile}")
            != profile_device_id
        ):
            raise IdentityEvidenceError(f"App readback {profile} device identity drift")
        _required_text(readback, "sourceReport", f"App readback {profile}")
        if str(readback.get("failureReason") or "").strip():
            raise IdentityEvidenceError(f"App readback {profile} contains a failure reason")
        case_results = readback.get("caseResults")
        if (
            not isinstance(case_results, list)
            or len(case_results) != readback["required"]
            or any(
                not isinstance(case, dict)
                or case.get("status") != "passed"
                or not str(case.get("caseId") or "").strip()
                or case.get("deviceId") != profile_device_id
                or not isinstance(case.get("testExecution"), dict)
                or not isinstance(case["testExecution"].get("executed"), int)
                or case["testExecution"]["executed"] <= 0
                or case["testExecution"].get("failed") != 0
                or not isinstance(case.get("evidence"), dict)
                or not str(case["evidence"].get("commandPath") or "").strip()
                or not str(case["evidence"].get("patrolLogPath") or "").strip()
                or not isinstance(case["evidence"].get("remoteApi"), dict)
                or not case["evidence"]["remoteApi"]
                for case in case_results
            )
            or len({case["caseId"] for case in case_results}) != len(case_results)
        ):
            raise IdentityEvidenceError(f"App readback {profile} CaseResults are incomplete")
    if len(attempts) != len(set(attempts)):
        raise IdentityEvidenceError("startup/device CaseResult reuses an attemptId")
    _validate_app_readback_receipts(payload)
    return attempts, devices


def _validate_app_readback_receipts(payload: dict[str, Any]) -> None:
    """Fail closed until App readback references are replayably verified.

    The current CaseResult embeds non-empty report, command, log and Remote API
    references, but the formal producer does not yet bind their bytes and
    release-object identities in a typed receipt.  Shape-only validation must
    not qualify a commercial candidate.
    """

    del payload
    raise IdentityEvidenceError(
        "canonical App readback report/log/Remote API references are not "
        "replayably bound"
    )


def _validate_telemetry(
    payload: dict[str, Any],
    *,
    baseline_id: str,
    release_id: str,
    release_digest: str,
    environment: str,
    target: str,
    launch_digest: str,
    attempts: list[str],
    devices: list[dict[str, str]],
) -> None:
    if payload.get("schema") != "qwq.startup-observability-readback" or payload.get("status") != "passed":
        raise IdentityEvidenceError("telemetry backend readback is not passed")
    _require_counts(payload, "telemetry backend readback")
    _require_spec_refs(payload, "telemetry backend readback")
    for field, expected in (
        ("baselineId", baseline_id),
        ("releaseId", release_id),
        ("releaseDigest", release_digest),
        ("environment", environment),
        ("target", target),
        ("effectiveLaunchManifestDigest", launch_digest),
    ):
        if payload.get(field) != expected:
            raise IdentityEvidenceError(f"telemetry backend readback {field} drift")
    backend = _required_text(payload, "telemetryBackend", "telemetry backend readback")
    receipt = _required_text(payload, "backendReceiptRef", "telemetry backend readback")
    if any(marker in backend.lower() or marker in receipt.lower() for marker in SYNTHETIC_MARKERS):
        raise IdentityEvidenceError("telemetry backend receipt is local, mock, or synthetic")
    observed_attempts = payload.get("attemptIds")
    observed_devices = payload.get("deviceIds")
    expected_device_ids = [item["deviceId"] for item in devices]
    if (
        not isinstance(observed_attempts, list)
        or len(observed_attempts) != len(set(observed_attempts))
        or set(observed_attempts) != set(attempts)
    ):
        raise IdentityEvidenceError("telemetry attemptIds do not match startup evidence")
    if (
        not isinstance(observed_devices, list)
        or len(observed_devices) != len(set(observed_devices))
        or any(str(value or "").strip() in {"", "unknown"} for value in observed_devices)
        or set(observed_devices) != set(expected_device_ids)
    ):
        raise IdentityEvidenceError("telemetry deviceIds do not match startup evidence")
    if payload.get("required") != len(attempts) or payload.get("executed") != len(attempts):
        raise IdentityEvidenceError("telemetry counts do not match startup attempts")
    _validate_telemetry_backend_receipt(payload)


def _validate_telemetry_backend_receipt(payload: dict[str, Any]) -> None:
    """Fail closed until Product Ops exposes canonical startup-store readback.

    The current startup ACK and observability envelope only assert that a batch
    was accepted.  Neither one can query the dedicated startup diagnostic store
    by attemptId/batchKey, so a non-empty backendReceiptRef is not commercial
    evidence and must never produce a passed environment identity.
    """

    del payload
    raise IdentityEvidenceError(
        "canonical Product Ops startup telemetry backend readback and typed "
        "stackctl receipt are not implemented"
    )


def render(args: argparse.Namespace) -> dict[str, Any]:
    baseline_id = args.baseline_id.strip()
    if baseline_id in {"", "unknown"}:
        raise IdentityEvidenceError("baselineId is missing or unknown")
    environment = args.environment
    target = args.target
    if ENVIRONMENT_TARGETS[environment] != target:
        raise IdentityEvidenceError("environment/target mismatch")
    all_paths = [
        args.release_evidence_manifest,
        args.release_readiness,
        args.import_receipt,
        args.replay_receipt,
        args.effective_launch_manifest,
        *args.app_artifact_receipt,
        args.startup_device_case_result,
        args.telemetry_readback,
        args.rollback_receipt,
        args.release_video_delivery,
    ]
    resolved = [path.expanduser().resolve() for path in all_paths]
    if len(resolved) != len(set(resolved)):
        raise IdentityEvidenceError("one evidence file cannot satisfy multiple required inputs")

    manifest = _read(args.release_evidence_manifest, "ReleaseEvidenceManifest")
    readiness = _read(args.release_readiness, "release-readiness")
    import_receipt = _read(args.import_receipt, "import-receipt")
    replay_receipt = _read(args.replay_receipt, "replay-receipt")
    launch = _read(args.effective_launch_manifest, "effective-launch-manifest")
    app_receipts = [
        _read(path, "app-artifact-receipt") for path in args.app_artifact_receipt
    ]
    case_result = _read(args.startup_device_case_result, "startup-device-case-result")
    telemetry = _read(args.telemetry_readback, "telemetry-readback")
    rollback = _read(args.rollback_receipt, "rollback-receipt")
    _read(
        args.release_video_delivery,
        "release-video-delivery",
    )
    input_digests = {
        path.expanduser().resolve(): _sha256(path) for path in all_paths
    }

    candidate_id, source_git_sha, source_tree_digest = _validate_release_manifest(
        manifest, environment=environment
    )
    try:
        validate_manifest_files(
            args.release_evidence_manifest.expanduser().resolve().parent,
            manifest,
        )
    except ValueError as exc:
        raise IdentityEvidenceError(
            f"ReleaseEvidenceManifest bundle is not canonical: {exc}"
        ) from exc
    release_identity = _validate_readiness(readiness, environment=environment)
    release_id = release_identity["releaseId"]
    release_digest = release_identity["releaseDigest"]
    import_run_id = release_identity["importRunId"]
    verify_run_id = release_identity["verifyRunId"]
    if _validate_run_receipt(
        import_receipt,
        label="import-receipt",
        environment=environment,
        release_id=release_id,
    ) != import_run_id:
        raise IdentityEvidenceError("import receipt runId drift")
    replay_run_id = _validate_run_receipt(
        replay_receipt,
        label="replay-receipt",
        environment=environment,
        release_id=release_id,
    )
    rollback_identity = _validate_rollback(
        rollback,
        environment=environment,
        release_id=release_id,
        release_digest=release_digest,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        replay_run_id=replay_run_id,
    )
    try:
        video_identity = validate_data_evidence(
            data_output_root=args.data_output_root,
            readiness_path=args.release_readiness,
            rollback_path=args.rollback_receipt,
            video_path=args.release_video_delivery,
            environment=environment,
            target=target,
            expected_release={
                "releaseId": release_id,
                "manifestDigest": release_digest,
                "mediaManifestDigest": release_identity["mediaProbe"][
                    "mediaManifestDigest"
                ],
                "importRunId": import_run_id,
                "verifyRunId": verify_run_id,
            },
        )
    except DataEvidenceError as exc:
        raise IdentityEvidenceError(str(exc)) from exc
    launch_digest, launch_mode = _validate_launch_manifest(
        launch, environment=environment, target=target
    )
    app_artifacts, app_evidence = _validate_app_receipts(
        args.app_artifact_receipt,
        app_receipts,
        manifest=manifest,
        environment=environment,
    )
    attempts, devices = _validate_case_result(
        case_result,
        baseline_id=baseline_id,
        release_id=release_id,
        release_digest=release_digest,
        source_git_sha=source_git_sha,
        source_tree_digest=source_tree_digest,
        environment=environment,
        target=target,
        launch_digest=launch_digest,
        launch_mode=launch_mode,
        app_artifacts=app_artifacts,
    )
    _validate_telemetry(
        telemetry,
        baseline_id=baseline_id,
        release_id=release_id,
        release_digest=release_digest,
        environment=environment,
        target=target,
        launch_digest=launch_digest,
        attempts=attempts,
        devices=devices,
    )
    for path in all_paths:
        resolved_path = path.expanduser().resolve()
        if _sha256(path) != input_digests[resolved_path]:
            raise IdentityEvidenceError(
                f"evidence changed while identity was being validated: {path}"
            )
    evidence = {
        "releaseEvidenceManifest": _evidence_ref(
            args.release_evidence_manifest,
            digest=input_digests[args.release_evidence_manifest.expanduser().resolve()],
        ),
        "releaseReadiness": _evidence_ref(
            args.release_readiness,
            digest=input_digests[args.release_readiness.expanduser().resolve()],
        ),
        "importReceipt": _evidence_ref(
            args.import_receipt,
            digest=input_digests[args.import_receipt.expanduser().resolve()],
        ),
        "replayReceipt": _evidence_ref(
            args.replay_receipt,
            digest=input_digests[args.replay_receipt.expanduser().resolve()],
        ),
        "effectiveLaunchManifest": _evidence_ref(
            args.effective_launch_manifest,
            digest=input_digests[
                args.effective_launch_manifest.expanduser().resolve()
            ],
        ),
        "appArtifactReceipts": app_evidence,
        "startupDeviceCaseResult": _evidence_ref(
            args.startup_device_case_result,
            digest=input_digests[
                args.startup_device_case_result.expanduser().resolve()
            ],
        ),
        "telemetryReadback": _evidence_ref(
            args.telemetry_readback,
            digest=input_digests[args.telemetry_readback.expanduser().resolve()],
        ),
        "rollbackReceipt": _evidence_ref(
            args.rollback_receipt,
            digest=input_digests[args.rollback_receipt.expanduser().resolve()],
        ),
        "releaseVideoDelivery": _evidence_ref(
            args.release_video_delivery,
            digest=input_digests[args.release_video_delivery.expanduser().resolve()],
        ),
    }
    identity = {
        "baselineId": baseline_id,
        "candidateId": candidate_id,
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "environment": environment,
        "target": target,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "dataCounts": release_identity["counts"],
        "objectIds": release_identity["objects"],
        "apiReadback": {"feedQueries": release_identity["feedQueries"]},
        "mediaProbe": release_identity["mediaProbe"],
        "videoDelivery": video_identity,
        "effectiveLaunchManifestDigest": launch_digest,
        "appArtifacts": app_artifacts,
        "devices": devices,
        "attemptIds": attempts,
        **rollback_identity,
    }
    return {
        "schema": SCHEMA,
        "status": "passed",
        "identityDigest": _canonical_digest(identity),
        "identity": identity,
        "evidence": evidence,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    output = path.expanduser().resolve()
    if path.is_symlink():
        raise IdentityEvidenceError("output must not be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.output.is_symlink():
            raise IdentityEvidenceError("output must not be a symlink")
        args.output.unlink(missing_ok=True)
        payload = render(args)
        _atomic_write(args.output, payload)
    except (IdentityEvidenceError, OSError) as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
