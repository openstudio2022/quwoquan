"""Canonical AppArtifactManifest fixtures for Release evidence contract tests."""

from __future__ import annotations

from typing import Any

from quwoquan_ops.cli.lib.app_identity import (
    application_id_for_build_product,
    resolve_build_product,
)


def app_artifact_manifest(
    *,
    build_product_id: str,
    source_git_sha: str,
    source_tree_digest: str,
    artifact_digest: str,
) -> dict[str, Any]:
    product = resolve_build_product(build_product_id)
    manifest = {
        "schema": "app-artifact-manifest",
        "buildProductId": product.build_product_id,
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "buildMode": product.build_mode,
        "distributionClass": product.distribution_class,
        "artifactFormat": product.artifact_format,
        "applicationId": application_id_for_build_product(product.build_product_id),
        "displayVersion": "1.0.0",
        "buildNumber": "1",
        "signingIdentityDigest": "sha256:" + "1" * 64,
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "buildProvenanceDigest": "sha256:" + "2" * 64,
        "artifactDigest": artifact_digest,
        "promotable": product.distribution_class in {"store", "hosted_web"},
    }
    if product.platform in {"android", "ios"}:
        manifest["runtimeConfigTrustEnvelopeDigest"] = "sha256:" + "4" * 64
    return manifest
