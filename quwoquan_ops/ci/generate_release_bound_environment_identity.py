#!/usr/bin/env python3
"""Collect one fail-closed, release-bound environment activation identity.

This is an evidence collector, not a deployment or activation entrypoint.  It
never infers lifecycle state from the environment name and it is intentionally
not wired into the App package pipeline.  The immutable Data readiness receipt
owns release/source/lifecycle identity; Ops only joins that identity to sealed
App, runtime, telemetry, rollback and media evidence.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.release_bound_data_evidence import (
    DataEvidenceError,
    validate_data_evidence,
)
from quwoquan_ops.ci.render_release_application_package import validate_package
from quwoquan_ops.cli.lib.app_identity import (
    build_profile_for_environment,
    supported_build_products,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    canonical_candidate_digest,
    canonical_manifest_digest,
    validate_manifest,
    validate_manifest_files,
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


def _build_product_ids_for_environment(environment: str) -> tuple[str, ...]:
    profile = build_profile_for_environment(environment)
    return tuple(
        product.build_product_id
        for product in supported_build_products()
        if product.build_profile in {profile, "shared"}
    )


SPEC_REFS = (
    "specs/feature-tree/spec.md#uat-003",
    "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
    "specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004",
    "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001",
    "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002",
)

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_GIT_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_TREE_DIGEST = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
_READINESS_COUNTS = {
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
_OBJECT_COUNTS = {
    "entityRefs": "entities",
    "postIds": "posts",
    "creatorIds": "creators",
    "tagRefs": "tags",
    "mediaAssetIds": "mediaAssets",
}
_RUN_FIELDS = {
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
_ROLLBACK_FIELDS = {
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
    """Evidence cannot support one immutable environment activation identity."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--environment", required=True, choices=ENVIRONMENT_TARGETS)
    parser.add_argument("--target", required=True, choices=ENVIRONMENT_TARGETS.values())
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
    parser.add_argument("--release-media-readback", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    candidate = path.expanduser().resolve()
    if path.is_symlink() or not candidate.is_file():
        raise IdentityEvidenceError(f"evidence is missing or unsafe: {path}")
    return "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()


def _read(path: Path, *, label: str) -> dict[str, Any]:
    candidate = path.expanduser().resolve()
    if path.is_symlink() or not candidate.is_file():
        raise IdentityEvidenceError(f"{label} is missing or unsafe: {path}")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IdentityEvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise IdentityEvidenceError(f"{label} must contain a JSON object")
    return value


def _text(value: object, *, label: str) -> str:
    result = str(value or "").strip()
    if result in {"", "unknown"}:
        raise IdentityEvidenceError(f"{label} is missing or unknown")
    return result


def _digest(value: object, *, label: str) -> str:
    result = str(value or "").strip()
    if _DIGEST.fullmatch(result) is None:
        raise IdentityEvidenceError(f"{label} is not a canonical sha256 digest")
    return result


def _verify_checksum(value: Mapping[str, Any], *, label: str) -> None:
    unsigned = dict(value)
    declared = str(unsigned.pop("verificationChecksum", ""))
    if declared != _canonical_digest(unsigned):
        raise IdentityEvidenceError(f"{label}.verificationChecksum drift")


def _validate_manifest(
    value: dict[str, Any], *, environment: str
) -> tuple[str, str, str]:
    try:
        validate_manifest(
            value, allowed_statuses={"candidate-ready", "deployable", "released"}
        )
    except ValueError as exc:
        raise IdentityEvidenceError(
            f"ReleaseEvidenceManifest is not canonical: {exc}"
        ) from exc
    if environment == "prod" and value.get("status") == "candidate-ready":
        raise IdentityEvidenceError("Prod requires a deployable or released manifest")
    candidate = _digest(value.get("candidateId"), label="candidateId")
    artifact = _digest(value.get("artifactDigest"), label="artifactDigest")
    if candidate != canonical_candidate_digest(
        value
    ) or artifact != canonical_manifest_digest(value):
        raise IdentityEvidenceError("ReleaseEvidenceManifest seal drift")
    source = value.get("source")
    if not isinstance(source, Mapping):
        raise IdentityEvidenceError("ReleaseEvidenceManifest.source is missing")
    git_sha = str(source.get("gitSha") or "")
    tree = str(source.get("treeDigest") or "")
    if _GIT_SHA.fullmatch(git_sha) is None or _TREE_DIGEST.fullmatch(tree) is None:
        raise IdentityEvidenceError(
            "ReleaseEvidenceManifest source identity is invalid"
        )
    packages = value.get("applicationPackages")
    required_products = set(_build_product_ids_for_environment(environment))
    if not isinstance(packages, Mapping) or not required_products.issubset(packages):
        raise IdentityEvidenceError("ReleaseEvidenceManifest App products are missing")
    return candidate, git_sha, tree


def _validate_activation(
    readiness: Mapping[str, Any], *, environment: str
) -> dict[str, Any]:
    release_class = str(readiness.get("releaseClass") or "")
    lifecycle = str(readiness.get("productLifecycleState") or "")
    phase = str(readiness.get("readinessPhase") or "")
    if release_class not in {"research", "commercial"} or lifecycle != release_class:
        raise IdentityEvidenceError("release readiness lifecycle identity mismatch")
    if phase not in {"research", "commercial"} or phase != release_class:
        raise IdentityEvidenceError(
            "activation phase must match immutable release lifecycle"
        )
    source_identity = {
        field: _digest(readiness.get(field), label=f"release-readiness.{field}")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    }
    app_uat = readiness.get("appUatEnvelope")
    if not isinstance(app_uat, Mapping):
        raise IdentityEvidenceError("release-readiness.appUatEnvelope is missing")
    for field, expected in (
        ("releaseId", readiness.get("releaseId")),
        ("releaseClass", release_class),
        ("productLifecycleState", lifecycle),
    ):
        if app_uat.get(field) != expected:
            raise IdentityEvidenceError(f"appUatEnvelope.{field} drift")
    app_uat_digest = _canonical_digest(app_uat)
    if readiness.get("appUatEnvelopeDigest") != app_uat_digest:
        raise IdentityEvidenceError("appUatEnvelopeDigest drift")
    activation = readiness.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise IdentityEvidenceError("release-readiness.activationEnvelope is missing")
    expected = {
        "schema": "quwoquan_data.environment_activation_envelope",
        "environment": environment,
        "releaseId": readiness.get("releaseId"),
        "manifestDigest": readiness.get("manifestDigest"),
        **source_identity,
        "releaseClass": release_class,
        "productLifecycleState": lifecycle,
        "readinessPhase": phase,
        "importRunId": readiness.get("importRunId"),
        "verifyRunId": readiness.get("verifyRunId"),
        "appUatEnvelopeDigest": app_uat_digest,
    }
    for field, expected_value in expected.items():
        if activation.get(field) != expected_value:
            raise IdentityEvidenceError(f"activationEnvelope.{field} drift")
    _text(activation.get("importReportRef"), label="activationEnvelope.importReportRef")
    _digest(
        activation.get("importReportDigest"),
        label="activationEnvelope.importReportDigest",
    )
    isolation = activation.get("researchIsolationPolicy")
    if release_class == "research":
        if not isinstance(isolation, Mapping):
            raise IdentityEvidenceError("research activation requires isolation policy")
        for field in ("policyRef", "verificationRef", "subjectHash"):
            _text(isolation.get(field), label=f"researchIsolationPolicy.{field}")
        for field in ("policyDigest", "verificationDigest"):
            _digest(isolation.get(field), label=f"researchIsolationPolicy.{field}")
        if readiness.get("internalSubjectHash") != isolation.get("subjectHash"):
            raise IdentityEvidenceError("research activation subjectHash drift")
        if readiness.get("researchIsolationVerificationRef") != isolation.get(
            "verificationRef"
        ):
            raise IdentityEvidenceError("research isolation verificationRef drift")
        if readiness.get("researchIsolationVerificationDigest") != isolation.get(
            "verificationDigest"
        ):
            raise IdentityEvidenceError("research isolation verificationDigest drift")
    elif isolation is not None:
        raise IdentityEvidenceError(
            "commercial activation cannot carry research isolation"
        )
    if readiness.get("activationEnvelopeDigest") != _canonical_digest(activation):
        raise IdentityEvidenceError("activationEnvelopeDigest drift")
    return dict(activation)


def _validate_readiness(value: dict[str, Any], *, environment: str) -> dict[str, Any]:
    if (
        value.get("schema") != "quwoquan_data.environment_release_readiness"
        or value.get("environment") != environment
        or value.get("releaseKind") != "content"
        or value.get("sourceOwner") != "qwq_data"
        or value.get("passed") is not True
    ):
        raise IdentityEvidenceError("release-readiness is not a passed Data receipt")
    _verify_checksum(value, label="release-readiness")
    counts = value.get("counts")
    if (
        not isinstance(counts, Mapping)
        or set(counts) != _READINESS_COUNTS
        or any(
            not isinstance(item, int) or isinstance(item, bool) or item <= 0
            for item in counts.values()
        )
    ):
        raise IdentityEvidenceError("release-readiness counts are incomplete")
    objects: dict[str, list[str]] = {}
    for field, count_field in _OBJECT_COUNTS.items():
        items = value.get(field)
        if (
            not isinstance(items, list)
            or len(items) != counts[count_field]
            or len(items) != len(set(items))
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise IdentityEvidenceError(f"release-readiness.{field} is incomplete")
        objects[field] = list(items)
    activation = _validate_activation(value, environment=environment)
    queries = value.get("feedQueries")
    if not isinstance(queries, list) or not queries:
        raise IdentityEvidenceError("release-readiness.feedQueries are missing")
    feed_queries: list[dict[str, Any]] = []
    for query in queries:
        matched = query.get("matchedPostIds") if isinstance(query, Mapping) else None
        if (
            not isinstance(query, Mapping)
            or query.get("path") != "/content/feed"
            or query.get("status") != 200
            or query.get("releaseBound") is not True
            or not isinstance(matched, list)
            or not matched
            or not set(matched).issubset(objects["postIds"])
        ):
            raise IdentityEvidenceError("release-readiness feed query is not exact")
        feed_queries.append(
            {
                "name": str(query.get("name")),
                "query": str(query.get("query")),
                "matchedPostIds": list(matched),
            }
        )
    return {
        "releaseId": _text(value.get("releaseId"), label="release-readiness.releaseId"),
        "releaseDigest": _digest(
            value.get("manifestDigest"), label="release-readiness.manifestDigest"
        ),
        "importRunId": _text(
            value.get("importRunId"), label="release-readiness.importRunId"
        ),
        "verifyRunId": _text(
            value.get("verifyRunId"), label="release-readiness.verifyRunId"
        ),
        "releaseClass": str(value["releaseClass"]),
        "productLifecycleState": str(value["productLifecycleState"]),
        "sourceIdentity": {
            field: str(value[field])
            for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
        },
        "activationEnvelope": activation,
        "activationEnvelopeDigest": str(value["activationEnvelopeDigest"]),
        "counts": dict(counts),
        "objects": objects,
        "feedQueries": sorted(feed_queries, key=lambda item: item["name"]),
        "mediaProbe": {
            "mediaManifestDigest": _digest(
                value.get("mediaManifestDigest"),
                label="release-readiness.mediaManifestDigest",
            ),
            "mediaManifestRef": _text(
                value.get("mediaManifestRef"),
                label="release-readiness.mediaManifestRef",
            ),
            "mediaAssetIds": objects["mediaAssetIds"],
            "avatarAssets": counts["avatarAssets"],
            "imageAssets": counts["imageAssets"],
            "premiumPlayableVideos": counts["premiumPlayableVideos"],
        },
    }


def _validate_run(
    value: dict[str, Any], *, label: str, environment: str, release_id: str
) -> str:
    if set(value) != _RUN_FIELDS:
        raise IdentityEvidenceError(f"{label} fields are not canonical")
    if (
        value.get("schema") != "quwoquan_data.environment_release_result"
        or value.get("environment") != environment
        or value.get("releaseId") != release_id
        or value.get("status") != "completed"
    ):
        raise IdentityEvidenceError(f"{label} is not a completed release result")
    _verify_checksum(value, label=label)
    return _text(value.get("runId"), label=f"{label}.runId")


def _validate_rollback(
    value: dict[str, Any],
    *,
    environment: str,
    release_id: str,
    release_digest: str,
    import_run_id: str,
    verify_run_id: str,
    replay_run_id: str,
) -> dict[str, str]:
    if set(value) != _ROLLBACK_FIELDS:
        raise IdentityEvidenceError("rollback receipt fields are not canonical")
    if (
        value.get("schema") != "quwoquan_data.environment_release_lifecycle_exit"
        or value.get("environment") != environment
        or value.get("sourceOwner") != "qwq_data"
        or value.get("passed") is not True
    ):
        raise IdentityEvidenceError("rollback receipt is not passed")
    _verify_checksum(value, label="rollback-receipt")
    expected = {
        "originalReleaseId": release_id,
        "originalManifestDigest": release_digest,
        "originalImportRunId": import_run_id,
        "originalVerifyRunId": verify_run_id,
        "replayImportRunId": replay_run_id,
        "replayManifestDigest": release_digest,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise IdentityEvidenceError(f"rollback-receipt.{field} drift")
    rollback_release = _text(
        value.get("rollbackToReleaseId"), label="rollbackToReleaseId"
    )
    if rollback_release == release_id:
        raise IdentityEvidenceError("rollback target must be a distinct release")
    for field in (
        "rollbackRunId",
        "rollbackVerifyRunId",
        "replayVerifyRunId",
        "replayVerifyResultRef",
    ):
        _text(value.get(field), label=f"rollback-receipt.{field}")
    return {
        "exitRunId": _text(value.get("exitRunId"), label="rollback-receipt.exitRunId"),
        "rollbackReleaseId": rollback_release,
        "rollbackReleaseDigest": _digest(
            value.get("rollbackToManifestDigest"), label="rollbackToManifestDigest"
        ),
        "rollbackRunId": str(value["rollbackRunId"]),
        "replayRunId": replay_run_id,
    }


def _validate_app_receipts(
    paths: list[Path],
    values: list[dict[str, Any]],
    *,
    manifest: dict[str, Any],
    environment: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    artifacts: dict[str, str] = {}
    evidence: list[dict[str, str]] = []
    descriptors = manifest["applicationPackages"]
    required_products = set(_build_product_ids_for_environment(environment))
    for path, value in zip(paths, values, strict=True):
        build_product_id = str(value.get("buildProductId") or "")
        if build_product_id not in required_products or build_product_id in artifacts:
            raise IdentityEvidenceError(
                "App build product is unsupported or duplicated for the environment"
            )
        try:
            package = validate_package(
                value,
                build_product_id=build_product_id,
                source_git_sha=manifest["source"]["gitSha"],
                source_tree_digest=manifest["source"]["treeDigest"],
            )
        except ValueError as exc:
            raise IdentityEvidenceError(
                f"App artifact receipt is invalid: {exc}"
            ) from exc
        package_digest = str(package["packageDigest"])
        receipt_digest = _file_digest(path)
        descriptor = descriptors.get(build_product_id)
        if (
            not isinstance(descriptor, Mapping)
            or descriptor.get("digest") != receipt_digest
            or descriptor.get("packageDigest") != package_digest
        ):
            raise IdentityEvidenceError("App artifact differs from sealed manifest")
        artifacts[build_product_id] = package_digest
        evidence.append(
            {
                "buildProductId": build_product_id,
                "ref": path.resolve().as_posix(),
                "sha256": receipt_digest,
            }
        )
    if set(artifacts) != required_products:
        raise IdentityEvidenceError("environment App build product receipts are required")
    return artifacts, sorted(evidence, key=lambda item: item["buildProductId"])


def _require_counts(value: Mapping[str, Any], *, label: str) -> None:
    required = value.get("required")
    if (
        not isinstance(required, int)
        or required <= 0
        or value.get("executed") != required
    ):
        raise IdentityEvidenceError(f"{label} execution count drift")
    if value.get("skipped") != 0 or value.get("failed") != 0:
        raise IdentityEvidenceError(f"{label} contains skipped or failed cases")


def _validate_app_readback_receipts(_: dict[str, Any]) -> None:
    raise IdentityEvidenceError(
        "canonical App readback authority is not replayably bound"
    )


def _validate_case(
    value: dict[str, Any],
    *,
    baseline_id: str,
    release_id: str,
    release_digest: str,
    source_git_sha: str,
    source_tree_digest: str,
    environment: str,
    target: str,
    launch_digest: str,
    app_artifacts: dict[str, str],
) -> tuple[list[str], list[dict[str, str]]]:
    if (
        value.get("schema") != "qwq.startup-environment-case-result"
        or value.get("status") != "passed"
    ):
        raise IdentityEvidenceError("startup/device CaseResult is not passed")
    _require_counts(value, label="startup/device CaseResult")
    expected = {
        "baselineId": baseline_id,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "applicationArtifacts": app_artifacts,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise IdentityEvidenceError(f"startup/device CaseResult {field} drift")
    runtime = value.get("runtimeEvidence")
    readbacks = value.get("readbackEvidence")
    if not isinstance(runtime, Mapping) or not isinstance(readbacks, Mapping):
        raise IdentityEvidenceError("startup/device evidence is missing")
    attempts: list[str] = []
    devices: list[dict[str, str]] = []
    for profile in sorted(EXPECTED_DEVICE_PROFILES[environment]):
        key = f"{target}/{profile}"
        wrapper = runtime.get(key)
        run = wrapper.get("evidence") if isinstance(wrapper, Mapping) else None
        readback_wrapper = readbacks.get(key)
        readback = (
            readback_wrapper.get("evidence")
            if isinstance(readback_wrapper, Mapping)
            else None
        )
        if (
            not isinstance(run, Mapping)
            or run.get("passed") is not True
            or not isinstance(readback, Mapping)
            or readback.get("status") != "passed"
        ):
            raise IdentityEvidenceError(
                f"runtime/readback evidence is not passed: {profile}"
            )
        samples = run.get("samples")
        if (
            not isinstance(samples, list)
            or not samples
            or run.get("runs") != len(samples)
        ):
            raise IdentityEvidenceError(f"runtime evidence has no samples: {profile}")
        if environment == "prod" and len(samples) != 20:
            raise IdentityEvidenceError(
                f"runtime {profile} must contain exactly 20 cold starts"
            )
        profile_devices: set[str] = set()
        for sample in samples:
            if not isinstance(sample, Mapping) or sample.get("passed") is not True:
                raise IdentityEvidenceError(f"runtime sample is not passed: {profile}")
            attempt = _text(sample.get("attemptId"), label="attemptId")
            device = _text(sample.get("deviceId"), label="deviceId")
            if (
                sample.get("runtimeEnv") != environment
                or sample.get("runtimeTarget") != target
                or sample.get("effectiveLaunchManifestDigest") != launch_digest
            ):
                raise IdentityEvidenceError(f"runtime sample identity drift: {profile}")
            attempts.append(attempt)
            profile_devices.add(device)
        if len(profile_devices) != 1:
            raise IdentityEvidenceError(
                f"runtime profile changes device identity: {profile}"
            )
        device = next(iter(profile_devices))
        if (
            readback.get("deviceId") != device
            or readback.get("effectiveLaunchManifestDigest") != launch_digest
        ):
            raise IdentityEvidenceError(
                f"App readback device/launch identity drift: {profile}"
            )
        devices.append(
            {
                "profile": profile,
                "platform": profile.split("-", 1)[0],
                "deviceId": device,
            }
        )
    if len(attempts) != len(set(attempts)):
        raise IdentityEvidenceError("startup/device CaseResult reuses an attemptId")
    _validate_app_readback_receipts(value)
    return attempts, devices


def _validate_telemetry_backend_receipt(_: dict[str, Any]) -> None:
    raise IdentityEvidenceError(
        "canonical telemetry backend authority is not replayably bound"
    )


def _validate_telemetry(
    value: dict[str, Any],
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
    if (
        value.get("schema") != "qwq.startup-observability-readback"
        or value.get("status") != "passed"
    ):
        raise IdentityEvidenceError("telemetry readback is not passed")
    _require_counts(value, label="telemetry readback")
    expected = {
        "baselineId": baseline_id,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "environment": environment,
        "target": target,
        "effectiveLaunchManifestDigest": launch_digest,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise IdentityEvidenceError(f"telemetry readback {field} drift")
    backend = _text(value.get("telemetryBackend"), label="telemetryBackend").lower()
    receipt = _text(value.get("backendReceiptRef"), label="backendReceiptRef").lower()
    if any(
        marker in backend or marker in receipt
        for marker in ("local", "mock", "memory", "fixture", "synthetic")
    ):
        raise IdentityEvidenceError("telemetry backend is local, mock, or synthetic")
    if set(value.get("attemptIds") or []) != set(attempts) or set(
        value.get("deviceIds") or []
    ) != {item["deviceId"] for item in devices}:
        raise IdentityEvidenceError("telemetry attempts/devices drift")
    _validate_telemetry_backend_receipt(value)


def render(args: argparse.Namespace) -> dict[str, Any]:
    baseline_id = _text(args.baseline_id, label="baselineId")
    environment = str(args.environment)
    target = str(args.target)
    if ENVIRONMENT_TARGETS[environment] != target:
        raise IdentityEvidenceError("environment/target mismatch")
    paths = [
        args.release_evidence_manifest,
        args.release_readiness,
        args.import_receipt,
        args.replay_receipt,
        args.effective_launch_manifest,
        *args.app_artifact_receipt,
        args.startup_device_case_result,
        args.telemetry_readback,
        args.rollback_receipt,
        args.release_media_readback,
    ]
    if len({path.expanduser().resolve() for path in paths}) != len(paths):
        raise IdentityEvidenceError("one evidence file cannot satisfy multiple inputs")
    snapshots = {path.expanduser().resolve(): _file_digest(path) for path in paths}
    manifest = _read(args.release_evidence_manifest, label="ReleaseEvidenceManifest")
    readiness = _read(args.release_readiness, label="release-readiness")
    import_receipt = _read(args.import_receipt, label="import-receipt")
    replay_receipt = _read(args.replay_receipt, label="replay-receipt")
    launch = _read(args.effective_launch_manifest, label="effective-launch-manifest")
    app_receipts = [
        _read(path, label="app-artifact-receipt") for path in args.app_artifact_receipt
    ]
    case = _read(args.startup_device_case_result, label="startup-device-case-result")
    telemetry = _read(args.telemetry_readback, label="telemetry-readback")
    rollback = _read(args.rollback_receipt, label="rollback-receipt")
    _read(args.release_media_readback, label="release-media-readback")

    candidate_id, git_sha, tree_digest = _validate_manifest(
        manifest, environment=environment
    )
    try:
        validate_manifest_files(
            args.release_evidence_manifest.resolve().parent, manifest
        )
    except ValueError as exc:
        raise IdentityEvidenceError(
            f"ReleaseEvidenceManifest bundle is invalid: {exc}"
        ) from exc
    release = _validate_readiness(readiness, environment=environment)
    import_run = _validate_run(
        import_receipt,
        label="import-receipt",
        environment=environment,
        release_id=release["releaseId"],
    )
    if import_run != release["importRunId"]:
        raise IdentityEvidenceError("import receipt runId drift")
    replay_run = _validate_run(
        replay_receipt,
        label="replay-receipt",
        environment=environment,
        release_id=release["releaseId"],
    )
    rollback_identity = _validate_rollback(
        rollback,
        environment=environment,
        release_id=release["releaseId"],
        release_digest=release["releaseDigest"],
        import_run_id=import_run,
        verify_run_id=release["verifyRunId"],
        replay_run_id=replay_run,
    )
    try:
        media_readback = validate_data_evidence(
            data_output_root=args.data_output_root,
            readiness_path=args.release_readiness,
            rollback_path=args.rollback_receipt,
            media_readback_path=args.release_media_readback,
            environment=environment,
            target=target,
            expected_release=release,
        )
    except DataEvidenceError as exc:
        raise IdentityEvidenceError(str(exc)) from exc
    if (
        launch.get("schema") != "app-effective-launch-manifest"
        or launch.get("environment") != environment
        or launch.get("target") != target
    ):
        raise IdentityEvidenceError("effective launch manifest identity drift")
    launch_digest = _canonical_digest(launch)
    app_artifacts, app_evidence = _validate_app_receipts(
        args.app_artifact_receipt,
        app_receipts,
        manifest=manifest,
        environment=environment,
    )
    attempts, devices = _validate_case(
        case,
        baseline_id=baseline_id,
        release_id=release["releaseId"],
        release_digest=release["releaseDigest"],
        source_git_sha=git_sha,
        source_tree_digest=tree_digest,
        environment=environment,
        target=target,
        launch_digest=launch_digest,
        app_artifacts=app_artifacts,
    )
    _validate_telemetry(
        telemetry,
        baseline_id=baseline_id,
        release_id=release["releaseId"],
        release_digest=release["releaseDigest"],
        environment=environment,
        target=target,
        launch_digest=launch_digest,
        attempts=attempts,
        devices=devices,
    )
    for path in paths:
        if _file_digest(path) != snapshots[path.expanduser().resolve()]:
            raise IdentityEvidenceError(f"evidence changed during validation: {path}")
    identity = {
        "baselineId": baseline_id,
        "candidateId": candidate_id,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "environment": environment,
        "target": target,
        "releaseId": release["releaseId"],
        "releaseDigest": release["releaseDigest"],
        "releaseClass": release["releaseClass"],
        "productLifecycleState": release["productLifecycleState"],
        "dataSourceIdentity": release["sourceIdentity"],
        "activationEnvelope": release["activationEnvelope"],
        "activationEnvelopeDigest": release["activationEnvelopeDigest"],
        "importRunId": import_run,
        "verifyRunId": release["verifyRunId"],
        "dataCounts": release["counts"],
        "objectIds": release["objects"],
        "apiReadback": {"feedQueries": release["feedQueries"]},
        "mediaProbe": release["mediaProbe"],
        "mediaReadback": media_readback,
        "effectiveLaunchManifestDigest": launch_digest,
        "appArtifacts": app_artifacts,
        "devices": devices,
        "attemptIds": attempts,
        **rollback_identity,
    }
    evidence = {
        "releaseEvidenceManifest": {
            "ref": args.release_evidence_manifest.resolve().as_posix(),
            "sha256": snapshots[args.release_evidence_manifest.resolve()],
        },
        "releaseReadiness": {
            "ref": args.release_readiness.resolve().as_posix(),
            "sha256": snapshots[args.release_readiness.resolve()],
        },
        "importReceipt": {
            "ref": args.import_receipt.resolve().as_posix(),
            "sha256": snapshots[args.import_receipt.resolve()],
        },
        "replayReceipt": {
            "ref": args.replay_receipt.resolve().as_posix(),
            "sha256": snapshots[args.replay_receipt.resolve()],
        },
        "effectiveLaunchManifest": {
            "ref": args.effective_launch_manifest.resolve().as_posix(),
            "sha256": snapshots[args.effective_launch_manifest.resolve()],
        },
        "appArtifactReceipts": app_evidence,
        "startupDeviceCaseResult": {
            "ref": args.startup_device_case_result.resolve().as_posix(),
            "sha256": snapshots[args.startup_device_case_result.resolve()],
        },
        "telemetryReadback": {
            "ref": args.telemetry_readback.resolve().as_posix(),
            "sha256": snapshots[args.telemetry_readback.resolve()],
        },
        "rollbackReceipt": {
            "ref": args.rollback_receipt.resolve().as_posix(),
            "sha256": snapshots[args.rollback_receipt.resolve()],
        },
        "releaseMediaReadback": {
            "ref": args.release_media_readback.resolve().as_posix(),
            "sha256": snapshots[args.release_media_readback.resolve()],
        },
    }
    return {
        "schema": SCHEMA,
        "status": "passed",
        "identityDigest": _canonical_digest(identity),
        "identity": identity,
        "evidence": evidence,
    }


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    output = path.expanduser().resolve()
    if path.is_symlink():
        raise IdentityEvidenceError("output must not be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(dict(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.output.is_symlink():
            raise IdentityEvidenceError("output must not be a symlink")
        args.output.unlink(missing_ok=True)
        value = render(args)
        _write_atomic(args.output, value)
    except (IdentityEvidenceError, OSError) as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
