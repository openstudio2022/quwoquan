"""Validate the exact prod-sim App launch bundle in a candidate."""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.deployment_candidate_manifest as _pkg

def validate_prod_sim_app_launch_bundle(
    candidate: Mapping[str, Any],
    *,
    candidate_root: Path,
) -> dict[str, Any]:
    """Validate and resolve the exact prod-sim App launch bundle."""

    bundle = candidate.get("appLaunchBundle")
    if candidate.get("target") != "prod-sim":
        if bundle is not None:
            raise ValueError("non-prod-sim candidate must not contain App launch bundle")
        return {}
    required = {
        "schema",
        "candidateDigest",
        "baselineId",
        "sourceGitSha",
        "sourceTreeDigest",
        "sourceStatusDigest",
        "artifactManifestRef",
        "artifactManifestDigest",
        "buildReceiptRef",
        "buildReceiptDigest",
        "artifactRef",
        "artifactDigest",
        "launcherHandoffRef",
        "launcherHandoffDigest",
    }
    if not isinstance(bundle, Mapping) or set(bundle) != required:
        raise ValueError("prod-sim App launch bundle fields mismatch")
    if (
        bundle.get("schema") != "stackctl-prod-sim-app-launch-bundle.v1"
        or bundle.get("candidateDigest") != candidate.get("packageDigest")
        or bundle.get("baselineId") != candidate.get("baselineId")
        or bundle.get("sourceGitSha") != candidate.get("sourceRevision")
        or bundle.get("sourceStatusDigest") != candidate.get("workspaceStatusDigest")
    ):
        raise ValueError("prod-sim App launch bundle candidate identity drifted")
    for field in (
        "candidateDigest",
        "baselineId",
        "sourceTreeDigest",
        "sourceStatusDigest",
        "artifactManifestDigest",
        "buildReceiptDigest",
        "artifactDigest",
        "launcherHandoffDigest",
    ):
        if _pkg._DIGEST.fullmatch(str(bundle.get(field) or "")) is None:
            raise ValueError(f"prod-sim App launch bundle {field} is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", str(bundle.get("sourceGitSha") or "")) is None:
        raise ValueError("prod-sim App launch bundle sourceGitSha is invalid")
    refs = {
        "artifactManifestRef": "artifact manifest",
        "buildReceiptRef": "build receipt",
        "artifactRef": "artifact",
        "launcherHandoffRef": "launcher handoff",
    }
    resolved: dict[str, Path] = {}
    for field, label in refs.items():
        value = str(bundle.get(field) or "")
        relative = Path(value)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != value
            or not value.startswith("packages/app/prod-sim-launch/")
        ):
            raise ValueError(f"prod-sim App launch bundle {field} is invalid")
        _pkg._read_candidate_bytes(candidate_root, value, label=f"prod-sim App {label}")
        resolved[field] = candidate_root / relative
    digest_bindings = {
        "artifactManifestRef": "artifactManifestDigest",
        "buildReceiptRef": "buildReceiptDigest",
        "artifactRef": "artifactDigest",
        "launcherHandoffRef": "launcherHandoffDigest",
    }
    for ref_field, digest_field in digest_bindings.items():
        if _pkg._sha256_candidate_file(
            candidate_root,
            str(bundle[ref_field]),
            label=f"prod-sim App {ref_field}",
        ) != bundle[digest_field]:
            raise ValueError(f"prod-sim App launch bundle {digest_field} drifted")
    manifest = _pkg._read_candidate_object(
        candidate_root,
        str(bundle["artifactManifestRef"]),
        label="prod-sim App artifact manifest",
    )
    receipt = _pkg._read_candidate_object(
        candidate_root,
        str(bundle["buildReceiptRef"]),
        label="prod-sim App build receipt",
    )
    handoff = _pkg._read_candidate_object(
        candidate_root,
        str(bundle["launcherHandoffRef"]),
        label="prod-sim App launcher handoff",
    )
    runtime_package = handoff.get("runtimeConfigPackage")
    if (
        manifest.get("schema") != "app-artifact-manifest"
        or manifest.get("buildProductId") != "android-prod-apk"
        or manifest.get("platform") != "android"
        or manifest.get("buildProfile") != "prod"
        or manifest.get("buildMode") != "release"
        or manifest.get("sourceGitSha") != bundle.get("sourceGitSha")
        or manifest.get("sourceTreeDigest") != bundle.get("sourceTreeDigest")
        or manifest.get("artifactDigest") != bundle.get("artifactDigest")
        or receipt.get("schema") != "app-artifact-build-receipt"
        or receipt.get("buildProductId") != "android-prod-apk"
        or receipt.get("artifactDigest") != bundle.get("artifactDigest")
        or receipt.get("manifestDigest") != bundle.get("artifactManifestDigest")
        or handoff.get("schema") != "app-launcher-handoff"
        or handoff.get("environment") != "prod"
        or handoff.get("target") != "prod-sim"
        or not isinstance(runtime_package, Mapping)
        or runtime_package.get("sourceGitSha") != bundle.get("sourceGitSha")
        or runtime_package.get("sourceTreeDigest") != bundle.get("sourceTreeDigest")
    ):
        raise ValueError("prod-sim App launch bundle source identity drifted")
    return {
        **dict(bundle),
        "artifactManifestPath": str(resolved["artifactManifestRef"]),
        "buildReceiptPath": str(resolved["buildReceiptRef"]),
        "artifactPath": str(resolved["artifactRef"]),
        "launcherHandoffPath": str(resolved["launcherHandoffRef"]),
    }


