from __future__ import annotations

# spec_ref: specs/feature-tree/platform-ops-governance/security-privacy-audit/spec.md#sit-001
import json
import shutil
from pathlib import Path

import pytest

from quwoquan_ops.ci import collect_stackctl_app_shard as shard_collector
from quwoquan_ops.ci import materialize_app_pipeline_web_release as web_materializer
from quwoquan_ops.cli.commands import package_app_artifact as artifact_producer
from quwoquan_ops.cli.commands import package_app_artifact_helpers as artifact_helpers
from quwoquan_ops.cli.commands.package_app_artifact_helpers import (
    artifact_digest,
    build_provenance_digest,
)
from quwoquan_ops.cli.lib.web_official_release import web_official_content_digest
from quwoquan_ops.tests.local_contract.release.test_app_pipeline_candidate_chain__local_contract_test import (
    ROOT,
    _source,
    _stackctl_result,
)
from quwoquan_ops.tests.local_contract.release.test_official_distribution_release__supply_chain__local_contract_test import (
    _android_package,
    _deploy,
    _official_graph,
)
from quwoquan_ops.tests.support.app_pipeline_web_artifact_test_support import (
    write_valid_web_artifact,
)


_REAL_CURRENT_BUILD_INPUT_IDENTITY = artifact_helpers._current_build_input_identity


@pytest.mark.parametrize("build_product_id,required", [
    ("ios-nonprod-app", ("ios",)), ("ios-prod-app", ("ios",)),
    ("android-nonprod-apk", ("android",)), ("web-shared", ("android", "ios")),
])
def test_currentness_uses_canonical_build_product_platform(monkeypatch, build_product_id, required):
    from types import SimpleNamespace
    calls = []

    def snapshot(**kwargs):
        calls.append(kwargs)
        assert kwargs["dependency_platforms"] == required
        return {"sourceRevision": "a" * 40, "deploymentInputDigest": "sha256:" + "3" * 64}

    monkeypatch.setattr(artifact_helpers, "workspace_snapshot", snapshot)
    monkeypatch.setattr(artifact_helpers.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="b" * 40))
    monkeypatch.setattr(artifact_helpers, "resolved_flutter_identity", lambda env: {})
    monkeypatch.setattr(artifact_helpers, "load_json_yaml", lambda path: {"version": "1.0.0+1"})
    current = _REAL_CURRENT_BUILD_INPUT_IDENTITY(build_product_id=build_product_id)
    assert current["sourceCapsuleDigest"] == "sha256:" + "3" * 64
    assert len(calls) == 1


@pytest.mark.parametrize("build_product_id", ["ios", "all", "", "ios-unknown"])
def test_currentness_rejects_noncanonical_product_before_dependency_read(monkeypatch, build_product_id):
    from unittest.mock import Mock
    snapshot = Mock(side_effect=AssertionError("dependency read forbidden"))
    monkeypatch.setattr(artifact_helpers, "workspace_snapshot", snapshot)
    with pytest.raises(ValueError):
        _REAL_CURRENT_BUILD_INPUT_IDENTITY(build_product_id=build_product_id)
    snapshot.assert_not_called()


def test_receipt_wrong_platform_is_rejected_before_currentness(tmp_path, monkeypatch):
    from unittest.mock import Mock
    artifact = tmp_path / "ios.app"
    artifact.mkdir()
    (artifact / "payload").write_bytes(b"local contract artifact")
    result_path = _stackctl_result(tmp_path, build_product_id="ios-nonprod-app", artifact=artifact)
    result = json.loads(result_path.read_bytes())
    attempt = Path(result["attemptDir"])
    manifest = json.loads((attempt / "manifest.json").read_bytes())
    manifest["platform"] = "android"
    (attempt / "manifest.json").write_text(json.dumps(manifest))
    receipt = json.loads((attempt / "build-receipt.json").read_bytes())
    receipt["manifestDigest"] = artifact_digest(attempt / "manifest.json")
    (attempt / "build-receipt.json").write_text(json.dumps(receipt))
    currentness = Mock(side_effect=AssertionError("currentness forbidden"))
    monkeypatch.setattr(artifact_helpers, "_current_build_input_identity", currentness)
    with pytest.raises(ValueError, match="product identity drifted: platform"):
        artifact_helpers.validate_app_artifact_build_receipt(attempt_dir=attempt,
            expected_build_product_id="ios-nonprod-app", expected_manifest=manifest)
    currentness.assert_not_called()


@pytest.fixture(autouse=True)
def _bind_fake_producer_semantic_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    revision, tree = _source()
    monkeypatch.setattr(
        artifact_helpers,
        "_current_build_input_identity",
        lambda *, build_product_id: {
            "sourceGitSha": revision,
            "sourceTreeDigest": tree,
            "sourceCapsuleDigest": "sha256:" + "3" * 64,
            "sourceStatusDigest": artifact_producer._EMPTY_STATUS_DIGEST,
            "flutterVersion": "3.35.1",
            "commandResolutionDigest": "sha256:" + "6" * 64,
            "displayVersion": "1.0.0",
            "buildNumber": "1",
        },
    )
    monkeypatch.setattr(
        artifact_helpers,
        "_artifact_semantic_identity",
        lambda **_kwargs: ("sha256:" + "1" * 64, "sha256:" + "4" * 64),
    )


@pytest.mark.parametrize(
    ("claim", "mutated", "blocker"),
    (
        ("sourceStatusDigest", "sha256:" + "7" * 64, "source/toolchain"),
        ("commandResolutionDigest", "sha256:" + "8" * 64, "source/toolchain"),
        ("flutterVersion", "9.9.9", "source/toolchain"),
        ("signingIdentityDigest", "sha256:" + "8" * 64, "signing identity"),
        (
            "runtimeConfigTrustEnvelopeDigest",
            "sha256:" + "9" * 64,
            "runtime trust",
        ),
    ),
)
def test_collector_rejects_coordinated_semantic_claim_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    claim: str,
    mutated: str,
    blocker: str,
) -> None:
    monkeypatch.chdir(ROOT)
    source = tmp_path / "nonprod.apk"
    source.write_bytes(b"fake signed apk")
    result_path = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=source,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    attempt = Path(result["attemptDir"])
    manifest_path = attempt / "manifest.json"
    receipt_path = attempt / "build-receipt.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if claim in receipt:
        receipt[claim] = mutated
    else:
        manifest[claim] = mutated
        if claim == "signingIdentityDigest":
            provenance = build_provenance_digest(
                build_product_id=manifest["buildProductId"],
                source_git_sha=manifest["sourceGitSha"],
                source_tree_digest=manifest["sourceTreeDigest"],
                source_capsule_digest=receipt["sourceCapsuleDigest"],
                artifact_digest=manifest["artifactDigest"],
                signing_identity_digest=mutated,
            )
            manifest["buildProvenanceDigest"] = provenance
            receipt["buildProvenanceDigest"] = provenance
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt["manifestDigest"] = artifact_digest(manifest_path)
        result["manifest"] = manifest
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=blocker):
        shard_collector.collect(result_path, tmp_path / f"bundle-{claim}")


def test_producer_collector_web_digest_survives_official_deploy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    source = tmp_path / "shared-web"
    write_valid_web_artifact(source)
    result_path = _stackctl_result(
        tmp_path,
        build_product_id="web-shared",
        artifact=source,
    )
    materialized_manifest = tmp_path / "materialized-web-manifest.json"
    materialized = web_materializer.materialize(
        result_path=result_path,
        output_path=materialized_manifest,
    )
    bundle = tmp_path / "collector-bundle"
    shard_collector.collect(
        result_path,
        bundle,
        web_release_manifest=materialized_manifest,
    )

    web_release = json.loads(
        (bundle / "public-web-manifest.json").read_text(encoding="utf-8")
    )
    source_git_sha = str(web_release["artifactManifest"]["sourceGitSha"])
    source_tree_digest = str(web_release["artifactManifest"]["sourceTreeDigest"])
    web_release["artifactManifest"]["buildNumber"] = "17"
    web_release["artifactManifest"]["qualificationRequestRef"] = (
        "ghcr.io/owner/repo/qualification-request@sha256:" + "1" * 64
    )
    web_release["artifactManifest"]["qualificationRequestDigest"] = "sha256:" + "1" * 64
    web_release["artifactManifest"]["rcTagAdmissionRef"] = (
        "ghcr.io/owner/repo/rc-admission@sha256:" + "3" * 64
    )
    web_release["artifactManifest"]["artifactBuildNumberAllocationRef"] = (
        "ghcr.io/owner/repo/build-number-allocation@sha256:" + "2" * 64
    )
    web_release["artifactManifest"]["artifactBuildNumberAllocationDigest"] = "sha256:" + "2" * 64
    (bundle / "public-web-manifest.json").write_text(
        json.dumps(web_release, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    android_manifest = _android_package(
        tmp_path / "android-package",
        build="17",
        source_git_sha=source_git_sha,
        source_tree_digest=source_tree_digest,
    )
    deploy_web = tmp_path / "factory-web"
    deploy_web.mkdir()
    (deploy_web / "manifest.json").write_bytes(
        (bundle / "public-web-manifest.json").read_bytes()
    )
    shutil.copytree(
        bundle / "payloads/web-shared/public-web", deploy_web / "public"
    )
    authority = _official_graph(
        tmp_path / "authority",
        web_manifest=deploy_web / "manifest.json",
        android_manifest=android_manifest,
    )
    receipt = _deploy(
        "web",
        authority,
        tmp_path / "official-origin",
    )

    expected = web_official_content_digest(
        bundle / "payloads/web-shared/public-web"
    )
    assert materialized["contentSHA256"] == expected
    assert receipt["contentSHA256"] == expected
    assert receipt["selectedAppArtifactDigest"] == "sha256:" + expected
    assert receipt["candidateMaterialId"] == authority["material_id"]
    assert (tmp_path / "official-origin/web/current").is_symlink()
