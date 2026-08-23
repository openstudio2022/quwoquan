from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.ci import render_release_application_package as subject
from quwoquan_ops.cli.lib.app_identity import (
    application_id_for_build_product,
    resolve_build_product,
)


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
    build_product_id: str,
    revision: str,
    tree: str,
    artifact_digest: str,
) -> dict[str, object]:
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
        "sourceGitSha": revision,
        "sourceTreeDigest": tree,
        "buildProvenanceDigest": "sha256:" + "2" * 64,
        "artifactDigest": artifact_digest,
        "promotable": product.distribution_class in {"store", "hosted_web"},
    }
    if product.platform in {"android", "ios"}:
        manifest["runtimeConfigTrustEnvelopeDigest"] = "sha256:" + "4" * 64
    return manifest


def _write_product_artifact(root: Path, build_product_id: str) -> Path:
    product = resolve_build_product(build_product_id)
    artifact = root / subject.PAYLOAD_NAMES[build_product_id]
    if product.artifact_format in {"app", "web"}:
        artifact.mkdir(parents=True)
        (artifact / "payload.bin").write_bytes(build_product_id.encode("utf-8"))
    else:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(build_product_id.encode("utf-8"))
    return artifact


def test_render_binds_real_product_package_to_current_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    package = tmp_path / "android-nonprod-apk"
    artifact = _write_product_artifact(package, "android-nonprod-apk")

    payload = subject.render(
        build_product_id="android-nonprod-apk",
        package=package,
        source_git_sha=revision,
        source_tree_digest=tree,
        artifact_manifest=_artifact_manifest(
            build_product_id="android-nonprod-apk",
            revision=revision,
            tree=tree,
            artifact_digest=subject._package_digest(artifact),
        ),
    )

    assert set(payload) == subject.GENERIC_FIELDS
    assert payload["schema"] == "release-application-package"
    assert payload["buildProductId"] == "android-nonprod-apk"
    assert payload["buildProfile"] == "nonprod"
    assert payload["platform"] == "android"
    assert payload["sourceGitSha"] == revision
    assert payload["sourceTreeDigest"] == tree
    assert payload["packageDigest"] == subject._sha256_tree(package)
    assert not any("version" in key.lower() for key in payload)


def test_render_rejects_file_instead_of_canonical_payload_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    package = tmp_path / "app-release.apk"
    package.write_bytes(b"signed-package")

    with pytest.raises(ValueError, match="canonical payload directory"):
        subject.render(
            build_product_id="android-nonprod-apk",
            package=package,
            source_git_sha=revision,
            source_tree_digest=tree,
            artifact_manifest=_artifact_manifest(
                build_product_id="android-nonprod-apk",
                revision=revision,
                tree=tree,
                artifact_digest=subject._package_digest(package),
            ),
        )


def test_bundle_requires_exactly_five_build_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    bundle = tmp_path / "bundle"
    applications = bundle / "application-packages"

    for build_product_id in subject.BUILD_PRODUCT_IDS:
        package = bundle / "payloads" / build_product_id
        artifact = _write_product_artifact(package, build_product_id)
        _write_json(
            applications / f"{build_product_id}.json",
            subject.render(
                build_product_id=build_product_id,
                package=package,
                source_git_sha=revision,
                source_tree_digest=tree,
                artifact_manifest=_artifact_manifest(
                    build_product_id=build_product_id,
                    revision=revision,
                    tree=tree,
                    artifact_digest=subject._package_digest(artifact),
                ),
            ),
        )

    subject.validate_bundle(
        bundle_dir=bundle,
        source_git_sha=revision,
        source_tree_digest=tree,
    )

    apk = (
        bundle
        / "payloads/android-prod-apk"
        / subject.PAYLOAD_NAMES["android-prod-apk"]
    )
    apk.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="android-prod-apk hosted payload digest mismatch"):
        subject.validate_bundle(
            bundle_dir=bundle,
            source_git_sha=revision,
            source_tree_digest=tree,
        )


def test_bundle_rejects_environment_duplicated_package_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert SPEC_REF
    monkeypatch.chdir(ROOT)
    revision, tree = _source()
    bundle = tmp_path / "bundle"
    applications = bundle / "application-packages"

    for build_product_id in subject.BUILD_PRODUCT_IDS:
        package = bundle / "payloads" / build_product_id
        artifact = _write_product_artifact(package, build_product_id)
        _write_json(
            applications / f"{build_product_id}.json",
            subject.render(
                build_product_id=build_product_id,
                package=package,
                source_git_sha=revision,
                source_tree_digest=tree,
                artifact_manifest=_artifact_manifest(
                    build_product_id=build_product_id,
                    revision=revision,
                    tree=tree,
                    artifact_digest=subject._package_digest(artifact),
                ),
            ),
        )
    _write_json(applications / "alpha--android.json", {})

    with pytest.raises(ValueError, match="App build product package set mismatch"):
        subject.validate_bundle(
            bundle_dir=bundle,
            source_git_sha=revision,
            source_tree_digest=tree,
        )


def test_product_evidence_rejects_contract_version_fields() -> None:
    assert SPEC_REF
    revision, tree = _source()
    payload = {
        "schema": subject.SCHEMA,
        "buildProductId": "web-shared",
        "buildProfile": "shared",
        "platform": "web",
        "sourceGitSha": revision,
        "sourceTreeDigest": tree,
        "packageDigest": "sha256:" + "a" * 64,
        "artifactManifest": _artifact_manifest(
            build_product_id="web-shared",
            revision=revision,
            tree=tree,
            artifact_digest="sha256:" + "b" * 64,
        ),
        "schemaVersion": "forbidden",
    }
    with pytest.raises(ValueError, match="fields are not canonical"):
        subject.validate_package(payload, build_product_id="web-shared")
