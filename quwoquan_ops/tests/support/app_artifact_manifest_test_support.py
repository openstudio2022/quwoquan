"""Canonical AppArtifactManifest fixtures for Release evidence contract tests."""

from __future__ import annotations

from typing import Any


def app_artifact_manifest(
    *,
    environment: str,
    surface: str,
    source_git_sha: str,
    source_tree_digest: str,
    artifact_digest: str,
) -> dict[str, Any]:
    distribution_class = (
        "hosted_web"
        if surface == "web"
        else "official_web"
        if environment == "prod" and surface == "android"
        else "dev_direct"
    )
    return {
        "schema": "app-artifact-manifest",
        "environment": environment,
        "platform": surface,
        "buildMode": "release",
        "distributionClass": distribution_class,
        "applicationId": f"com.quwoquan.test.{environment}.{surface}",
        "displayVersion": "1.0.0",
        "buildNumber": "1",
        "signingIdentityDigest": "sha256:" + "1" * 64,
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "artifactDigest": artifact_digest,
        "launchManifestDigest": "sha256:" + "2" * 64,
        "promotable": distribution_class in {"hosted_web", "official_web"},
    }
