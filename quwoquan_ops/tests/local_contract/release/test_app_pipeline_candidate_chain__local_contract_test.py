from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from quwoquan_ops.ci import collect_stackctl_app_shard as shard_collector
from quwoquan_ops.ci.render_release_application_package import _package_digest
from quwoquan_ops.cli import stackctl as stackctl_module
from quwoquan_ops.cli.commands import package_app_artifact as artifact_producer
from quwoquan_ops.cli.commands import package_app_artifact_helpers as artifact_helpers
from quwoquan_ops.cli.commands.package_app_artifact_helpers import artifact_digest
from quwoquan_ops.tests.support.app_pipeline_web_artifact_test_support import (
    write_valid_web_artifact,
)

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/app_pipeline.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PLATFORM_WORKFLOW = ROOT / ".github/workflows/beta-device-platform.yml"
DEVICE_EVIDENCE = ROOT / "quwoquan_ops/ci/render_beta_device_evidence.py"
DEVICE_LEASE = ROOT / "quwoquan_ops/ci/device_runner_lease.py"
PLATFORM_RUNNER = ROOT / "quwoquan_ops/ci/run_mobile_platform_matrix.sh"
TIMING_BUDGETS = ROOT / "quwoquan_ops/environments/pr_gate_timing_budgets.json"
EVIDENCE_DOCKERFILE = ROOT / "quwoquan_ops/ci/app_candidate_evidence.Dockerfile"
SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
BUILD_PRODUCTS = (
    "android-nonprod-apk",
    "android-prod-apk",
    "ios-nonprod-app",
    "ios-prod-app",
    "web-shared",
)


@pytest.fixture(autouse=True)
def _bind_fake_producer_semantic_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    revision, tree = _source()
    monkeypatch.setattr(
        artifact_helpers,
        "_current_build_input_identity",
        lambda: {
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


def _source() -> tuple[str, str]:
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    return revision, f"sha1:{tree}"


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write_private_json(path: Path, value: dict[str, object]) -> str:
    encoded = _canonical_bytes(value)
    path.write_bytes(encoded)
    path.chmod(0o600)
    return _sha256(encoded)


def _dependency_projection_evidence(
    attempt: Path,
    *,
    source_capsule_digest: str,
) -> dict[str, str]:
    identity_digest = "sha256:" + "7" * 64
    projection_root = str(attempt / "deleted-dependency-projection")
    component = {
        "kind": "pub",
        "treePath": "production-pub",
        "lockPath": "production-pub.lock",
        "manifestDigest": identity_digest,
        "treeDigest": identity_digest,
        "entryCount": 1,
        "directoryCount": 1,
        "lockDigest": identity_digest,
    }
    environment_values = {"FLUTTER_SWIFT_PACKAGE_MANAGER": "false"}
    environment = {
        "values": environment_values,
        "digest": _sha256(
            _canonical_bytes(
                {
                    "schema": "stackctl-app-dependency-command-environment.v1",
                    "values": environment_values,
                }
            )
        ),
    }
    expectation = {
        "schema": "stackctl-app-dependency-projection-expectation.v2",
        "projectionRoot": projection_root,
        "source": {
            "manifestPath": str(attempt / "source-capsule-manifest.json"),
            "manifestDigest": identity_digest,
            "baselineId": identity_digest,
            "inputDigest": source_capsule_digest,
            "inputCount": 1,
            "dependencyMarkers": [
                {
                    "logicalPath": "dependency:dart-pub-cache-v2",
                    "digest": identity_digest,
                    "size": 1,
                }
            ],
        },
        "components": {"productionPub": component},
        "environments": {"production": environment},
        "patrolCommandEnvelope": None,
    }
    expectation_path = attempt / "dependency-projection-expectation.json"
    expectation_digest = _write_private_json(expectation_path, expectation)
    readback = {
        "schema": "stackctl-app-dependency-projection-readback.v2",
        "expectationDigest": expectation_digest,
        "projectionRoot": projection_root,
        "sourceManifestDigest": identity_digest,
        "components": {
            "productionPub": {
                field: component[field]
                for field in (
                    "manifestDigest",
                    "treeDigest",
                    "entryCount",
                    "directoryCount",
                    "lockDigest",
                )
            }
        },
        "patrolCommandEnvelopeDigest": None,
    }
    prebuild_path = attempt / "dependency-projection-prebuild-readback.json"
    postbuild_path = attempt / "dependency-projection-postbuild-readback.json"
    prebuild_digest = _write_private_json(prebuild_path, readback)
    postbuild_digest = _write_private_json(postbuild_path, readback)
    return {
        "dependencyProjectionExpectationRef": str(expectation_path),
        "dependencyProjectionExpectationDigest": expectation_digest,
        "dependencyProjectionPrebuildReadbackRef": str(prebuild_path),
        "dependencyProjectionPrebuildReadbackDigest": prebuild_digest,
        "dependencyProjectionPostbuildReadbackRef": str(postbuild_path),
        "dependencyProjectionPostbuildReadbackDigest": postbuild_digest,
    }


def _stackctl_result(
    root: Path,
    *,
    build_product_id: str,
    artifact: Path,
) -> Path:
    revision, tree = _source()
    source_capsule_digest = "sha256:" + "3" * 64
    signing_identity_digest = "sha256:" + "1" * 64
    trust_digest = "sha256:" + "4" * 64

    def fake_build(*, attempt_dir: Path, **_: object) -> dict[str, object]:
        destination = attempt_dir / (
            build_product_id + (artifact.suffix if artifact.is_file() else "")
        )
        if artifact.is_dir():
            shutil.copytree(artifact, destination)
        else:
            shutil.copy2(artifact, destination)
        dependency_evidence = _dependency_projection_evidence(
            attempt_dir,
            source_capsule_digest=source_capsule_digest,
        )
        (attempt_dir / "sbom.spdx.json").write_text(
            json.dumps({"spdxVersion": "SPDX-2.3"}) + "\n",
            encoding="utf-8",
        )
        (attempt_dir / "compile.log").write_text("compiled\n", encoding="utf-8")
        return {
            "artifactPath": str(destination),
            "artifactDigest": artifact_digest(destination),
            "artifactFilesystemIdentity": (1,),
            "signingIdentityDigest": signing_identity_digest,
            "sourceCapsuleDigest": source_capsule_digest,
            "sourceStatusDigest": artifact_producer._EMPTY_STATUS_DIGEST,
            "flutterVersion": "3.35.1",
            "commandResolutionDigest": "sha256:" + "6" * 64,
            "dependencyProjectionEvidence": dependency_evidence,
            "runtimeConfigTrustEnvelopeDigest": trust_digest,
        }

    snapshot = {
        "deploymentInputDigest": source_capsule_digest,
        "workspaceStatusDigest": artifact_producer._EMPTY_STATUS_DIGEST,
    }
    package_root = root / "producer-output"
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(artifact_producer, "_build_from_capsule", fake_build)
        patcher.setattr(artifact_producer, "_git_identity", lambda: (revision, tree))
        patcher.setattr(artifact_producer, "_version", lambda: ("1.0.0", "1"))
        patcher.setattr(
            artifact_producer,
            "workspace_snapshot",
            lambda **_: dict(snapshot),
        )
        patcher.setattr(
            artifact_producer,
            "read_runtime_config_trust_envelope",
            lambda **kwargs: SimpleNamespace(
                artifact_digest=kwargs["expected_artifact_digest"],
                signing_identity_digest=signing_identity_digest,
                runtime_config_trust_envelope_digest=trust_digest,
            ),
        )
        patcher.setattr(
            stackctl_module,
            "deployment_target_path",
            lambda *_: package_root,
        )
        produced = artifact_producer.command_package_app_artifact(
            argparse.Namespace(
                build_product_id=build_product_id,
                artifact_path="",
                env="",
                target="",
                app_platform="",
                app_build_mode="",
                distribution_class="",
                artifact_format="",
                device="",
                service="",
                release_attestation="",
                rollback_release_attestation="",
            )
        )
    assert produced["exitCode"] == 0, produced
    result = root / f"result-{build_product_id}.json"
    result.write_text(
        json.dumps(produced, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _web_release_manifest(root: Path, result: Path) -> Path:
    manifest = json.loads(result.read_text(encoding="utf-8"))["manifest"]
    content_digest = manifest["artifactDigest"].removeprefix("sha256:")
    payload = {
        "schema": "client-app.web.official-release",
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
    }
    path = root / "web-release-manifest.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_app_pipeline_is_reusable_only_and_publishes_immutable_oci() -> None:
    assert SPEC_REF
    text = WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)
    triggers = payload["on"]

    assert set(triggers) == {"workflow_call"}
    outputs = triggers["workflow_call"]["outputs"]
    assert set(outputs) == {
        "app_evidence_ref",
        "app_evidence_digest",
        "source_git_sha",
        "machine_critical_path_seconds",
    }
    assert "refs/tags" not in text
    assert "workflow_dispatch" not in text
    assert "environment: production" not in text
    assert "app-candidate-artifact@" in text
    assert "docker/build-push-action@" in text
    assert "render_app_candidate_timing.py" in text
    assert "actions/upload-artifact@" not in text
    assert "actions/download-artifact@" not in text
    assert "oras-project/setup-oras@1d808f7d7f6995cc68b7bf507bfe5c5446e1dc9d" in text
    assert "app_candidate_oci_transport.py materialize-shards" in text
    assert 'CMD ["/evidence"]' in EVIDENCE_DOCKERFILE.read_text(encoding="utf-8")
    jobs = payload["jobs"]
    product_job = jobs["product"]
    assert product_job["name"] == "App package product / ${{ matrix.buildProductId }}"
    assert product_job["strategy"]["matrix"]["include"] == [
        {
            "buildProductId": "android-nonprod-apk",
            "profile": "nonprod",
            "format": "apk",
        },
        {
            "buildProductId": "android-prod-apk",
            "profile": "prod",
            "format": "apk",
        },
        {
            "buildProductId": "ios-nonprod-app",
            "profile": "nonprod",
            "format": "app",
        },
        {
            "buildProductId": "ios-prod-app",
            "profile": "prod",
            "format": "app",
        },
        {
            "buildProductId": "web-shared",
            "profile": "shared",
            "format": "web",
        },
    ]
    assert "environment" not in product_job["strategy"]["matrix"]
    assert product_job["runs-on"] == "macos-latest"
    assert jobs["aggregate"]["needs"] == ["product"]
    assert text.count("--kind app-artifact") == 1
    selector = '--build-product-id "${{ matrix.buildProductId }}"'
    assert text.count(selector) == 2
    preparation = text.index("quwoquan_ops/ci/prepare_app_pipeline_inputs.py")
    compilation = text.index("--kind app-artifact")
    first_selector = text.index(selector)
    second_selector = text.index(selector, first_selector + 1)
    assert preparation < first_selector < compilation < second_selector
    assert text.count("--web-release-manifest") == 1
    assert "--kind app-release" in text
    assert "--kind ops-portal" in text
    assert "payloads/opsPortal" in text
    assert "payloads/prod/opsPortal" not in text
    assert "render_release_application_package.py bind-special" not in text
    assert "flutter build" not in text
    assert "working-directory: quwoquan_app" not in text


def test_app_pipeline_requires_exactly_five_build_products_without_environment_compilation() -> (
    None
):
    assert SPEC_REF
    text = WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)
    matrix = payload["jobs"]["product"]["strategy"]["matrix"]["include"]

    assert tuple(item["buildProductId"] for item in matrix) == BUILD_PRODUCTS
    assert tuple((item["profile"], item["format"]) for item in matrix) == (
        ("nonprod", "apk"),
        ("prod", "apk"),
        ("nonprod", "app"),
        ("prod", "app"),
        ("shared", "web"),
    )
    assert "matrix.environment" not in text
    assert "environment: [alpha, beta, gamma, prod]" not in text
    assert "app-candidate-shard-android-" not in text
    assert "app-candidate-shard-ios-" not in text
    assert "app-candidate-shard-web-" not in text
    assert "app-candidate-shard-${{ matrix.buildProductId }}" in text
    assert "--app-platform macos" not in text
    assert "App package shard / macOS" not in text
    assert "--app-platform" not in text
    assert "--app-build-mode" not in text
    assert "--distribution-class" not in text
    assert "--artifact-format" not in text
    product_command = re.search(
        r"--kind app-artifact \\\n(?P<arguments>.*?)> \"\$RESULT\"",
        text,
        flags=re.DOTALL,
    )
    assert product_command is not None
    assert "--env" not in product_command.group("arguments")
    collector = (ROOT / "quwoquan_ops/ci/collect_stackctl_app_shard.py").read_text(
        encoding="utf-8"
    )
    assert '"application-packages" / f"{build_product_id}.json"' in collector
    assert '"payloads" / build_product_id' in collector
    assert '"evidence" / build_product_id' in collector
    assert "build_product_id=build_product_id" in collector


def test_app_pipeline_missing_signing_inputs_are_typed_gate_blocks() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("quwoquan_ops/gate/require_ci_inputs.py") == 2
    assert text.count("--scope release-signing") == 2
    for required in (
        "QWQ_ANDROID_RELEASE_KEYSTORE_B64",
        "QWQ_ANDROID_RELEASE_KEY_ALIAS",
        "QWQ_ANDROID_NONPROD_GOOGLE_SERVICES_JSON",
        "QWQ_ANDROID_PROD_GOOGLE_SERVICES_JSON",
    ):
        assert required in text
    for retired in (
        "QWQ_ANDROID_ALPHA_GOOGLE_SERVICES_JSON",
        "QWQ_ANDROID_BETA_GOOGLE_SERVICES_JSON",
        "QWQ_ANDROID_GAMMA_GOOGLE_SERVICES_JSON",
    ):
        assert retired not in text
    assert "FIREBASE_INPUT=QWQ_ANDROID_NONPROD_GOOGLE_SERVICES_JSON" in text


def test_collector_preserves_nonpromotable_baseline_product_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "nonprod.apk"
    artifact.write_bytes(b"nonprod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=artifact,
    )
    bundle = tmp_path / "bundle"

    collected = shard_collector.collect(result, bundle)

    package_path = bundle / "application-packages/android-nonprod-apk.json"
    package = json.loads(package_path.read_text())
    assert collected["buildProductId"] == "android-nonprod-apk"
    assert package["artifactManifest"]["distributionClass"] == "dev_direct"
    assert package["artifactManifest"]["promotable"] is False
    assert (bundle / "payloads/android-nonprod-apk/app-release.apk").is_file()
    assert (bundle / "evidence/android-nonprod-apk/manifest.json").is_file()
    assert (
        bundle / "evidence/android-nonprod-apk/dependency-projection-expectation.json"
    ).is_file()


def test_collector_accepts_real_ios_producer_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "Runner.app"
    artifact.mkdir()
    (artifact / "Info.plist").write_bytes(b"ios app")
    result = _stackctl_result(
        tmp_path,
        build_product_id="ios-nonprod-app",
        artifact=artifact,
    )

    collected = shard_collector.collect(result, tmp_path / "bundle")

    assert collected["buildProductId"] == "ios-nonprod-app"
    assert (
        tmp_path / "bundle/payloads/ios-nonprod-app/quwoquan.app/Info.plist"
    ).is_file()


def test_collector_rejects_missing_dependency_projection_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "nonprod.apk"
    artifact.write_bytes(b"nonprod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=artifact,
    )
    attempt = Path(json.loads(result.read_text())["attemptDir"])
    receipt_path = attempt / "build-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt.pop("dependencyProjectionPostbuildReadbackDigest")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="dependencyProjectionPostbuildReadbackDigest",
    ):
        shard_collector.collect(result, tmp_path / "bundle")


def test_collector_rejects_dependency_evidence_from_another_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "nonprod.apk"
    artifact.write_bytes(b"nonprod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=artifact,
    )
    attempt = Path(json.loads(result.read_text())["attemptDir"])
    receipt_path = attempt / "build-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    other_attempt = tmp_path / "other-attempt"
    other_attempt.mkdir()
    foreign = other_attempt / "dependency-projection-expectation.json"
    original = Path(receipt["dependencyProjectionExpectationRef"])
    foreign.write_bytes(original.read_bytes())
    foreign.chmod(0o600)
    receipt["dependencyProjectionExpectationRef"] = str(foreign)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ValueError, match="not bound to the build attempt"):
        shard_collector.collect(result, tmp_path / "bundle")


def test_collector_rejects_tampered_dependency_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "nonprod.apk"
    artifact.write_bytes(b"nonprod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=artifact,
    )
    attempt = Path(json.loads(result.read_text())["attemptDir"])
    receipt = json.loads((attempt / "build-receipt.json").read_text())
    expectation = Path(receipt["dependencyProjectionExpectationRef"])
    expectation.write_bytes(expectation.read_bytes() + b" ")

    with pytest.raises(ValueError, match="dependency projection evidence invalid"):
        shard_collector.collect(result, tmp_path / "bundle")


def test_collector_rejects_postbuild_dependency_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "nonprod.apk"
    artifact.write_bytes(b"nonprod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=artifact,
    )
    attempt = Path(json.loads(result.read_text())["attemptDir"])
    receipt_path = attempt / "build-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    postbuild = Path(receipt["dependencyProjectionPostbuildReadbackRef"])
    payload = json.loads(postbuild.read_text())
    payload["components"]["productionPub"]["entryCount"] = 2
    receipt["dependencyProjectionPostbuildReadbackDigest"] = _write_private_json(
        postbuild,
        payload,
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ValueError, match="postbuild readback identity drifted"):
        shard_collector.collect(result, tmp_path / "bundle")


def test_collector_retains_web_special_without_replacing_baseline_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "shared-web"
    write_valid_web_artifact(artifact)
    result = _stackctl_result(
        tmp_path,
        build_product_id="web-shared",
        artifact=artifact,
    )
    bundle = tmp_path / "bundle"
    official = _web_release_manifest(tmp_path, result)

    shard_collector.collect(result, bundle, web_release_manifest=official)

    special = json.loads((bundle / "public-web-manifest.json").read_text())
    baseline = json.loads((bundle / "application-packages/web-shared.json").read_text())
    assert special["schema"] == "client-app.web.official-release"
    assert special["artifactManifest"]["promotable"] is True
    assert baseline["buildProductId"] == "web-shared"
    copied_artifact = bundle / "payloads/web-shared/public-web"
    assert (copied_artifact / "index.html").is_file()
    assert (
        _package_digest(copied_artifact)
        == special["artifactManifest"]["artifactDigest"]
    )


def test_collector_requires_explicit_exact_web_release_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "shared-web"
    write_valid_web_artifact(artifact)
    result = _stackctl_result(
        tmp_path,
        build_product_id="web-shared",
        artifact=artifact,
    )

    with pytest.raises(ValueError, match="requires its stackctl official manifest"):
        shard_collector.collect(result, tmp_path / "missing")

    official = _web_release_manifest(tmp_path, result)
    payload = json.loads(official.read_text(encoding="utf-8"))
    payload["contentSHA256"] = "0" * 64
    official.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not bind AppArtifactManifest"):
        shard_collector.collect(
            result,
            tmp_path / "drifted",
            web_release_manifest=official,
        )


@pytest.mark.parametrize("drift", ("attempt", "manifest", "artifact", "mixed"))
def test_collector_rejects_stale_or_mixed_producer_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "nonprod.apk"
    artifact.write_bytes(b"nonprod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-nonprod-apk",
        artifact=artifact,
    )
    attempt = Path(json.loads(result.read_text(encoding="utf-8"))["attemptDir"])
    receipt_path = attempt / "build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if drift == "attempt":
        receipt["attemptId"] = "00000000-0000-0000-0000-000000000000"
        receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    elif drift == "manifest":
        (attempt / "manifest.json").write_bytes(
            (attempt / "manifest.json").read_bytes() + b" "
        )
    elif drift == "artifact":
        Path(receipt["artifactPath"]).write_bytes(b"tampered apk")
    else:
        foreign_root = tmp_path / "foreign"
        foreign_root.mkdir()
        foreign_artifact = foreign_root / "nonprod.apk"
        foreign_artifact.write_bytes(b"foreign apk")
        foreign_result = _stackctl_result(
            foreign_root,
            build_product_id="android-nonprod-apk",
            artifact=foreign_artifact,
        )
        foreign_attempt = Path(
            json.loads(foreign_result.read_text(encoding="utf-8"))["attemptDir"]
        )
        receipt_path.write_bytes((foreign_attempt / "build-receipt.json").read_bytes())

    with pytest.raises(ValueError, match="attempt|manifest|artifact|receipt"):
        shard_collector.collect(result, tmp_path / f"bundle-{drift}")


def test_collector_retains_android_special_without_replacing_baseline_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "prod.apk"
    artifact.write_bytes(b"prod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-prod-apk",
        artifact=artifact,
    )
    manifest = json.loads(result.read_text())["manifest"]
    official = tmp_path / "official.json"
    official.write_text(
        json.dumps(
            {
                "schema": "client-app.android.official-release",
                "apkSHA256": manifest["artifactDigest"].removeprefix("sha256:"),
                "apkSigningCertificateSHA256": manifest[
                    "signingIdentityDigest"
                ].removeprefix("sha256:"),
                "packagedAPK": "quwoquan.apk",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle"

    shard_collector.collect(result, bundle, android_release_manifest=official)

    special = json.loads((bundle / "android-release-manifest.json").read_text())
    baseline = json.loads(
        (bundle / "application-packages/android-prod-apk.json").read_text()
    )
    assert special["artifactManifest"]["buildProductId"] == "android-prod-apk"
    assert baseline["buildProductId"] == "android-prod-apk"
    assert (bundle / "payloads/android-prod-apk/app-release.apk").is_file()


def test_collector_rejects_prod_android_without_canonical_official_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "prod.apk"
    artifact.write_bytes(b"prod apk")
    result = _stackctl_result(
        tmp_path,
        build_product_id="android-prod-apk",
        artifact=artifact,
    )

    with pytest.raises(ValueError, match="requires its stackctl official manifest"):
        shard_collector.collect(result, tmp_path / "bundle")


def test_app_release_evidence_identity_has_no_contract_number_suffix() -> None:
    assert SPEC_REF
    sources = (
        WORKFLOW,
        ROOT / "quwoquan_ops/ci/render_release_application_package.py",
        ROOT / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    for forbidden in (
        "schemaVersion",
        "contractVersion",
        "registryRevision",
        "app-launcher-handoff-v1",
        "app-effective-launch-manifest-v1",
    ):
        assert forbidden not in combined


def test_beta_device_receipt_binds_candidate_directly_without_identity_shim() -> None:
    assert SPEC_REF
    workflow = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    evidence = DEVICE_EVIDENCE.read_text(encoding="utf-8")
    text = workflow + evidence

    assert "--identity-evidence" not in text
    assert "release-bound-environment-identity" not in text
    assert '"candidateId": candidate' in evidence
    assert '"sourceGitSha": git_sha' in evidence
    assert '"sourceTreeDigest": tree_digest' in evidence
    assert '--evidence "devices=$RAW/devices.json"' in workflow


def test_device_matrix_nightly_schedule_selects_full_profile() -> None:
    assert SPEC_REF
    text = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)

    assert payload["on"]["schedule"] == [{"cron": "0 18 * * *"}]
    assert 'if [ "$EVENT_NAME" = "schedule" ]; then PROFILE="nightly_full"; fi' in text
    assert "vars.RELEASED_RELEASE_EVIDENCE_REF" in text
    assert "consume_released_release_evidence.py" in text
    assert "NIGHTLY_" not in text
    assert "stackctl.py dev-session" in text
    assert "--env gamma" in text
    assert "managed_runtime_started" in text
    assert "Inspect and doctor the managed Gamma runtime before soak" in text
    assert "Inspect and doctor the managed Gamma runtime after soak" in text
    assert text.count("stackctl.py inspect") >= 2
    assert text.count("stackctl.py doctor") >= 2
    assert '--budget-profile "$VALIDATION_PROFILE"' in text
    assert "canonical App device timing status" in text


def test_beta_android_and_ios_run_in_parallel_before_one_receipt_aggregation() -> None:
    assert SPEC_REF
    text = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    platform_text = PLATFORM_WORKFLOW.read_text(encoding="utf-8")
    lease_text = DEVICE_LEASE.read_text(encoding="utf-8")
    runner_text = PLATFORM_RUNNER.read_text(encoding="utf-8")
    payload = yaml.load(text, Loader=yaml.BaseLoader)
    jobs = payload["jobs"]
    outputs = payload["on"]["workflow_call"]["outputs"]
    aggregate_job = jobs["mobile_matrix"]

    assert set(outputs) == {
        "discover_duration_seconds",
        "mobile_duration_seconds",
        "android_result",
        "ios_result",
        "allow_missing_platforms",
        "has_android",
        "has_ios",
        "machine_critical_path_seconds",
        "summary_result",
        "receipt_ref",
        "receipt_digest",
    }
    assert (
        outputs["receipt_ref"]["value"]
        == "${{ jobs.mobile_matrix.outputs.receipt_ref }}"
    )
    assert (
        outputs["receipt_digest"]["value"]
        == "${{ jobs.mobile_matrix.outputs.receipt_digest }}"
    )
    assert set(aggregate_job["needs"]) == {
        "beta_stack",
        "android_device_matrix",
        "ios_device_matrix",
    }
    assert aggregate_job["name"] == "Aggregate mobile matrix evidence"
    assert aggregate_job["runs-on"] == "ubuntu-latest"
    canonical_mobile_runner = ["self-hosted", "macOS", "ARM64"]
    assert jobs["beta_stack"]["runs-on"] == canonical_mobile_runner
    assert jobs["beta_teardown"]["runs-on"] == canonical_mobile_runner
    assert (
        jobs["android_device_matrix"]["uses"]
        == "./.github/workflows/beta-device-platform.yml"
    )
    assert (
        jobs["ios_device_matrix"]["uses"]
        == "./.github/workflows/beta-device-platform.yml"
    )
    assert jobs["android_device_matrix"]["needs"] == "beta_stack"
    assert jobs["ios_device_matrix"]["needs"] == "beta_stack"
    assert jobs["android_device_matrix"]["with"]["platform"] == "android"
    assert jobs["ios_device_matrix"]["with"]["platform"] == "ios"
    for job_name in ("android_device_matrix", "ios_device_matrix"):
        inputs = jobs[job_name]["with"]
        assert (
            inputs["account_closure_disposable_ack"]
            == "${{ inputs.account_closure_disposable_ack == true }}"
        )
        assert (
            inputs["account_closure_prod_platform"]
            == "${{ inputs.account_closure_prod_platform || 'ios' }}"
        )
    assert jobs["beta_teardown"]["needs"][-1] == "mobile_matrix"
    assert "runs-on: [self-hosted, macOS, ARM64]" in platform_text
    assert "PUB_HOSTED_URL: https://pub.flutter-io.cn" in platform_text
    assert "FLUTTER_STORAGE_BASE_URL: https://storage.flutter-io.cn" in platform_text
    assert "flutter pub get --enforce-lockfile" in platform_text
    assert "run: flutter pub get\n" not in platform_text
    assert "MOBILE_MATRIX_ENV_JSON: ${{ inputs.env_json }}" in platform_text
    assert 'MATRIX_ENV_ARGS+=(--environment "$environment")' in platform_text
    assert '"${MATRIX_ENV_ARGS[@]}"' in platform_text
    assert (
        'runs-on: [self-hosted, macOS, ARM64, "mobile-${{ inputs.platform }}"]'
        not in platform_text
    )
    assert '--runner-label "mobile-${{ inputs.platform }}"' in platform_text
    assert "device_runner_lease.py acquire" in platform_text
    assert "device_runner_lease.py release" in platform_text
    assert "expected-host-digest" in platform_text
    assert "execution-started-at" in platform_text
    assert "execution-ended-at" in platform_text
    assert "did not overlap" in DEVICE_EVIDENCE.read_text(encoding="utf-8")
    assert "MOBILE_DEVICE_ID" in runner_text
    assert '--device-id "$MOBILE_DEVICE_ID"' in runner_text
    assert "Beta receipt requires one immutable stack" in text
    assert "render_beta_device_evidence.py merge" in text
    assert "render_beta_device_evidence.py stack" in text
    assert '--android-ref "$ANDROID_REF"' in text
    assert '--ios-ref "$IOS_REF"' in text
    assert "materialize_evidence_oci.py" in text
    assert "@${{ steps.receipt_bundle.outputs.digest }}" in text
    combined = f"{text}\n{platform_text}\n{lease_text}\n{runner_text}"
    assert 'export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"' in runner_text
    assert 'cd "$ROOT"' in runner_text
    assert "actions/upload-artifact@" not in combined
    assert "actions/download-artifact@" not in combined
    assert "rm -rf" not in combined
    assert "git clean" not in combined
    assert "ASSISTANT_MODEL_PROVIDER: deterministic" not in combined
    assert "docker pull" not in text
    assert "RepoDigests" not in text
    assert "timeout-minutes: 120" not in combined
    assert "timeout-minutes: 30" not in combined
    assert jobs["beta_stack"]["timeout-minutes"] == "20"
    assert "mainline_auto_prod" in aggregate_job["timeout-minutes"]
    assert "20" in aggregate_job["timeout-minutes"]
    assert "|| 2" in aggregate_job["timeout-minutes"]
    aggregate_checkout = next(
        step
        for step in aggregate_job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert aggregate_checkout["if"] == (
        "${{ needs.beta_stack.outputs.profile == 'mainline_auto_prod' }}"
    )
    assert "10 || 1" in jobs["beta_teardown"]["timeout-minutes"]
    platform_payload = yaml.load(platform_text, Loader=yaml.BaseLoader)
    platform_timeout = platform_payload["jobs"]["device"]["timeout-minutes"]
    assert "nightly_full" in platform_timeout
    assert "120" in platform_timeout
    assert "release_candidate" in platform_timeout
    assert "manual_full" in platform_timeout
    assert "mainline_auto_prod" in platform_timeout
    assert "90" in platform_timeout
    assert "|| 60" in platform_timeout
    assert re.search(r"\|\|\s+4(?:\D|$)", platform_timeout) is None
    timing_gate = json.loads(TIMING_BUDGETS.read_text(encoding="utf-8"))["gates"][
        "05.app_env_device_matrix_pr"
    ]
    assert timing_gate["profileHardFailSeconds"]["mainline_auto_prod"] == 480
    assert timing_gate["profileHardFailSeconds"]["nightly_full"] == 7200
    assert '--budget-profile "$VALIDATION_PROFILE"' in text
    assert "canonical App device timing status=${timing_status}" in text
    assert '"$calendar_lead_time_seconds" -gt "$profile_hard_fail_seconds"' not in text
    assert 'if [ "$calendar_lead_time_seconds" -gt 480 ]' not in text
    assert 'STACKCTL_AUTO_WIPE_MIGRATION_DRIFT: "0"' in text
    assert "stackctl.py up" in text
    assert "--formal-release" in text
    assert '--release-manifest "$QWQ_PROD_RELEASE_ARTIFACT_ROOT/manifest.json"' in text
    assert "--skip-build" in text
    assert "--skip-app" in text
    formal_teardown = next(
        step
        for step in jobs["beta_teardown"]["steps"]
        if step.get("name") == "Teardown only the recorded formal Beta runtime"
    )
    assert formal_teardown["if"] == (
        "${{ needs.beta_stack.outputs.formal_runtime_started == 'true' }}"
    )
    formal_teardown_run = formal_teardown["run"]
    assert "stackctl.py down" in formal_teardown_run
    assert "--target beta-local" in formal_teardown_run
    assert "--formal-release" in formal_teardown_run
    assert (
        '--release-manifest "$QWQ_OUTPUT_ROOT/env/repo/runs/beta-stack/'
        'release-evidence-manifest/manifest.json"'
    ) in formal_teardown_run
    assert text.count("Require exact clean candidate checkout") == 1
    assert platform_text.count("Require exact clean candidate checkout") == 1
    assert text.count('[[ "$EXPECTED_SOURCE" =~ ^[0-9a-f]{40}$ ]]') == 1
    assert platform_text.count('[[ "$EXPECTED_SOURCE" =~ ^[0-9a-f]{40}$ ]]') == 1
    assert 'test -z "$(git status --porcelain --untracked-files=all)"' in text
    assert 'test -z "$(git status --porcelain --untracked-files=all)"' in platform_text
    assert "docker compose up --build" not in text
    assert "source-built or destructive Beta formal runtime" not in text
    assert "steps.formal_runtime.outputs.started" in text
    assert "destructiveActions" in DEVICE_EVIDENCE.read_text(encoding="utf-8")
    assert combined.count("persist-credentials: false") == 10
    assert "config --local http.https://github.com/.extraheader" not in combined
    checkout_steps = [
        step
        for job in jobs.values()
        for step in job.get("steps", [])
        if str(step.get("uses") or "").startswith("actions/checkout@")
    ]
    called_checkout_steps = [
        step
        for job in platform_payload["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("uses") or "").startswith("actions/checkout@")
    ]
    assert len(checkout_steps) == 9
    assert len(called_checkout_steps) == 1
    assert sum(step["with"].get("clean") == "false" for step in checkout_steps) == 7
    assert all(step["with"]["clean"] == "false" for step in called_checkout_steps)
    assert all(
        step["with"]["persist-credentials"] == "false" for step in checkout_steps
    )
    assert all(
        step["with"]["persist-credentials"] == "false" for step in called_checkout_steps
    )
