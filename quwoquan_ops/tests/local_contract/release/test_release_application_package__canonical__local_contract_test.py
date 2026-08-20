from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.ci import render_release_application_package as subject


ROOT = Path(__file__).resolve().parents[4]
SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"


def _source() -> tuple[str, str]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return revision, f"sha1:{tree}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact_manifest(
    *,
    environment: str,
    surface: str,
    revision: str,
    tree: str,
    artifact_digest: str,
) -> dict[str, object]:
    distribution = (
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
        "distributionClass": distribution,
        "applicationId": f"test.{surface}.{environment}",
        "displayVersion": "1.0.0",
        "buildNumber": "1",
        "signingIdentityDigest": "sha256:" + "1" * 64,
        "sourceGitSha": revision,
        "sourceTreeDigest": tree,
        "artifactDigest": artifact_digest,
        "launchManifestDigest": "sha256:" + "2" * 64,
        "promotable": distribution in {"hosted_web", "official_web"},
    }


def test_render_binds_real_package_to_current_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    package = tmp_path / "app-release.apk"
    package.write_bytes(b"signed-package")

    payload = subject.render(
        environment="beta",
        surface="android",
        package=package.parent,
        source_git_sha=revision,
        source_tree_digest=tree,
        artifact_manifest=_artifact_manifest(
            environment="beta",
            surface="android",
            revision=revision,
            tree=tree,
            artifact_digest=subject._package_digest(package),
        ),
    )

    assert set(payload) == subject.GENERIC_FIELDS
    assert payload["schema"] == "release-application-package"
    assert payload["sourceGitSha"] == revision
    assert payload["sourceTreeDigest"] == tree
    assert payload["packageDigest"] == subject._sha256_tree(package.parent)
    assert not any("version" in key.lower() for key in payload)


def test_render_rejects_file_digest_that_cannot_round_trip_through_payload_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    package = tmp_path / "app-release.apk"
    package.write_bytes(b"signed-package")

    with pytest.raises(ValueError, match="canonical payload directory"):
        subject.render(
            environment="beta",
            surface="android",
            package=package,
            source_git_sha=revision,
            source_tree_digest=tree,
            artifact_manifest=_artifact_manifest(
                environment="beta",
                surface="android",
                revision=revision,
                tree=tree,
                artifact_digest=subject._package_digest(package),
            ),
        )


def test_bundle_requires_every_real_environment_surface_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    bundle = tmp_path / "bundle"
    applications = bundle / "application-packages"
    for environment, surface in subject.GENERIC_PACKAGES:
        package = (
            bundle
            / "payloads"
            / environment
            / surface
            / subject.PAYLOAD_NAMES[surface]
        )
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(f"{environment}-{surface}".encode("utf-8"))
        _write_json(
            applications / f"{environment}--{surface}.json",
            subject.render(
                environment=environment,
                surface=surface,
                package=package.parent,
                source_git_sha=revision,
                source_tree_digest=tree,
                artifact_manifest=_artifact_manifest(
                    environment=environment,
                    surface=surface,
                    revision=revision,
                    tree=tree,
                    artifact_digest=subject._package_digest(package),
                ),
            ),
        )

    web_root = bundle / "payloads/prod/web"
    web_root.mkdir(parents=True)
    (web_root / "index.html").write_text("prod web", encoding="utf-8")
    web_digest = subject._sha256_tree(web_root)
    _write_json(
        bundle / "public-web-manifest.json",
        {
            "schema": "client-app.web.official-release",
            "sourceGitSha": revision,
            "sourceTreeDigest": tree,
            "contentSHA256": web_digest.removeprefix("sha256:"),
            "artifactManifest": _artifact_manifest(
                environment="prod",
                surface="web",
                revision=revision,
                tree=tree,
                artifact_digest=web_digest,
            ),
        },
    )
    android_root = bundle / "payloads/prod/android"
    android_root.mkdir(parents=True)
    apk = android_root / "quwoquan-1.apk"
    apk.write_bytes(b"prod android")
    apk_digest = subject._sha256_file(apk)
    _write_json(
        bundle / "android-release-manifest.json",
        {
            "schema": "client-app.android.official-release",
            "sourceGitSha": revision,
            "sourceTreeDigest": tree,
            "packagedAPK": apk.name,
            "apkSHA256": apk_digest.removeprefix("sha256:"),
            "artifactManifest": _artifact_manifest(
                environment="prod",
                surface="android",
                revision=revision,
                tree=tree,
                artifact_digest=apk_digest,
            ),
        },
    )
    portal_root = bundle / "payloads/prod/opsPortal"
    (portal_root / "dist").mkdir(parents=True)
    (portal_root / "manifest.json").write_text("portal manifest", encoding="utf-8")
    (portal_root / "dist/index.js").write_text("portal", encoding="utf-8")
    portal_dist_digest = subject._ops_portal_tree_digest(portal_root / "dist")
    _write_json(
        bundle / "ops-portal-provenance.json",
        {
            "schema": "qwq.ops_portal_package",
            "sourceGitSha": revision,
            "sourceTreeDigest": tree,
            "packageDigest": portal_dist_digest,
            "digests": {
                "manifest": subject._sha256_file(portal_root / "manifest.json"),
                "distTree": portal_dist_digest,
            },
        },
    )

    subject.validate_bundle(
        bundle_dir=bundle,
        source_git_sha=revision,
        source_tree_digest=tree,
    )

    apk.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="prod/android special payload digest mismatch"):
        subject.validate_bundle(
            bundle_dir=bundle,
            source_git_sha=revision,
            source_tree_digest=tree,
        )


def test_generic_evidence_rejects_contract_version_fields() -> None:
    assert SPEC_REF
    revision, tree = _source()
    payload = {
        "schema": subject.SCHEMA,
        "environment": "alpha",
        "surface": "web",
        "sourceGitSha": revision,
        "sourceTreeDigest": tree,
        "packageDigest": "sha256:" + "a" * 64,
        "artifactManifest": _artifact_manifest(
            environment="alpha",
            surface="web",
            revision=revision,
            tree=tree,
            artifact_digest="sha256:" + "b" * 64,
        ),
        "schemaVersion": "forbidden",
    }
    with pytest.raises(ValueError, match="fields are not canonical"):
        subject.validate_generic(payload, environment="alpha", surface="web")
