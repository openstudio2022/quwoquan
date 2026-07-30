from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.ci import render_release_application_package as subject


ROOT = Path(__file__).resolve().parents[3]
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
            ),
        )

    web_root = tmp_path / "web-release"
    (web_root / "public").mkdir(parents=True)
    (web_root / "public/index.html").write_text("prod-web", encoding="utf-8")
    web_digest = subject._public_web_tree_digest(web_root / "public").removeprefix(
        "sha256:"
    )
    web_manifest = web_root / "manifest.json"
    _write_json(
        web_manifest,
        {
            "schema": "qwq.public-web.release",
            "environment": "prod",
            "contentSHA256": web_digest,
        },
    )
    web_payload = bundle / "payloads/prod/web"
    web_payload.mkdir(parents=True)
    (web_payload / "index.html").write_text("prod-web", encoding="utf-8")
    _write_json(
        bundle / "public-web-manifest.json",
        subject.bind_special(
            kind="publicWeb",
            manifest_path=web_manifest,
            source_git_sha=revision,
            source_tree_digest=tree,
        ),
    )

    android_root = tmp_path / "android-release"
    android_root.mkdir()
    apk = android_root / "quwoquan.apk"
    apk.write_bytes(b"prod-android")
    android_manifest = android_root / "manifest.json"
    _write_json(
        android_manifest,
        {
            "schema": "qwq.android.official-release",
            "platform": "android",
            "packagedAPK": apk.name,
            "apkSHA256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        },
    )
    hosted_apk = bundle / "payloads/prod/android" / apk.name
    hosted_apk.parent.mkdir(parents=True)
    hosted_apk.write_bytes(apk.read_bytes())
    _write_json(
        bundle / "android-release-manifest.json",
        subject.bind_special(
            kind="android",
            manifest_path=android_manifest,
            source_git_sha=revision,
            source_tree_digest=tree,
        ),
    )

    portal_root = bundle / "payloads/prod/opsPortal"
    (portal_root / "dist").mkdir(parents=True)
    (portal_root / "dist/index.html").write_text("portal", encoding="utf-8")
    _write_json(portal_root / "manifest.json", {"packageDigest": "sha256:" + "a" * 64})
    portal_provenance = tmp_path / "portal-provenance.json"
    portal_dist_digest = subject._ops_portal_tree_digest(portal_root / "dist")
    _write_json(
        portal_provenance,
        {
            "schema": "qwq.ops_portal_package",
            "environment": "prod",
            "target": "prod-hosted",
            "gitRevision": revision,
            "packageDigest": portal_dist_digest,
            "digests": {
                "manifest": subject._sha256_file(portal_root / "manifest.json"),
                "distTree": portal_dist_digest,
            },
        },
    )
    _write_json(
        bundle / "ops-portal-provenance.json",
        subject.bind_special(
            kind="opsPortal",
            manifest_path=portal_provenance,
            source_git_sha=revision,
            source_tree_digest=tree,
        ),
    )

    subject.validate_bundle(
        bundle_dir=bundle,
        source_git_sha=revision,
        source_tree_digest=tree,
    )

    hosted_apk.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="Android hosted payload digest mismatch"):
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
        "schemaVersion": "forbidden",
    }
    with pytest.raises(ValueError, match="fields are not canonical"):
        subject.validate_generic(payload, environment="alpha", surface="web")
