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
EVIDENCE_DOCKERFILE = ROOT / "quwoquan_ops/ci/app_candidate_evidence.Dockerfile"
SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
BUILD_PRODUCTS = (
    "android-nonprod-apk",
    "android-prod-apk",
    "ios-nonprod-app",
    "ios-prod-app",
    "web-shared",
)
RC_AUTHORITY_ENVIRONMENT = {
    "QWQ_ARTIFACT_BUILD_NUMBER": "1",
    "QWQ_QUALIFICATION_REQUEST_REF": (
        "ghcr.io/example/quwoquan/release-qualification-request@sha256:" + "8" * 64
    ),
    "QWQ_QUALIFICATION_REQUEST_DIGEST": "sha256:" + "8" * 64,
    "QWQ_RC_TAG_ADMISSION_REF": (
        "ghcr.io/example/quwoquan/rc-tag-admission@sha256:" + "9" * 64
    ),
    "QWQ_ARTIFACT_BUILD_NUMBER_ALLOCATION_REF": (
        "ghcr.io/example/quwoquan/artifact-build-number-allocation@sha256:"
        + "a" * 64
    ),
    "QWQ_ARTIFACT_BUILD_NUMBER_ALLOCATION_DIGEST": "sha256:" + "a" * 64,
}
RC_AUTHORITY_MANIFEST = {
    "qualificationRequestRef": RC_AUTHORITY_ENVIRONMENT[
        "QWQ_QUALIFICATION_REQUEST_REF"
    ],
    "qualificationRequestDigest": RC_AUTHORITY_ENVIRONMENT[
        "QWQ_QUALIFICATION_REQUEST_DIGEST"
    ],
    "rcTagAdmissionRef": RC_AUTHORITY_ENVIRONMENT["QWQ_RC_TAG_ADMISSION_REF"],
    "artifactBuildNumberAllocationRef": RC_AUTHORITY_ENVIRONMENT[
        "QWQ_ARTIFACT_BUILD_NUMBER_ALLOCATION_REF"
    ],
    "artifactBuildNumberAllocationDigest": RC_AUTHORITY_ENVIRONMENT[
        "QWQ_ARTIFACT_BUILD_NUMBER_ALLOCATION_DIGEST"
    ],
}


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

        def fake_version(*, require_hosted_build_number: bool, **_: object) -> tuple[str, str]:
            assert require_hosted_build_number is True
            return "1.0.0", "1"

        patcher.setattr(artifact_producer, "_version", fake_version)
        patcher.setenv("QWQ_ARTIFACT_BUILD_NUMBER", "1")
        for name, value in RC_AUTHORITY_ENVIRONMENT.items():
            patcher.setenv(name, value)
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
    for field in RC_AUTHORITY_MANIFEST:
        manifest.pop(field, None)
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
        "app_oci_digest",
        "source_git_sha",
        "source_tree_digest",
        "qualification_request_ref",
        "qualification_request_digest",
        "artifact_build_number",
        "artifact_build_number_allocation_ref",
        "artifact_build_number_allocation_digest",
        "android_artifact_digest",
        "ios_artifact_digest",
        "web_artifact_digest",
        "app_material_digest",
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
    assert "app-candidate-evidence/ops-portal/payload" in text
    assert "payloads/opsPortal" not in text
    assert "payloads/prod/opsPortal" not in text
    assert "render_release_application_package.py bind-special" not in text
    assert "flutter build" not in text
    assert "working-directory: quwoquan_app" not in text


def test_app_pipeline_embeds_one_hosted_build_number_in_all_five_products() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "QWQ_ARTIFACT_BUILD_NUMBER: ${{ inputs.artifact_build_number }}" in text
    assert text.count("--build-number") == 0
    assert text.count("--kind app-artifact") == 1
    assert 'manifest.get("buildNumber") != os.environ["ARTIFACT_BUILD_NUMBER"]' in text


def test_app_pipeline_promotable_factory_requires_exact_rc_and_allocator_bindings() -> None:
    payload = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    call = payload["on"]["workflow_call"]
    assert set(call["inputs"]) == {
        "source_git_sha",
        "qualification_request_ref",
        "qualification_request_digest",
        "rc_tag_admission_ref",
        "artifact_build_number",
        "artifact_build_number_allocation_ref",
        "artifact_build_number_allocation_digest",
    }
    assert all(value["required"] == "true" for value in call["inputs"].values())
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "QWQ_ARTIFACT_BUILD_NUMBER: ${{ inputs.artifact_build_number }}" in text
    assert "QWQ_ARTIFACT_BUILD_NUMBER_ALLOCATION_REF" in text
    assert "QWQ_ARTIFACT_BUILD_NUMBER_ALLOCATION_DIGEST" in text
    assert "QWQ_QUALIFICATION_REQUEST_REF" in text
    assert "QWQ_QUALIFICATION_REQUEST_DIGEST" in text
    assert "QWQ_RC_TAG_ADMISSION_REF" in text
    assert text.count("RC_TAG_ADMISSION_REF: ${{ inputs.rc_tag_admission_ref }}") == 3
    assert '"rcTagAdmissionRef": os.environ["RC_TAG_ADMISSION_REF"]' in text
    assert "iOS production identity remains externally unregistered" in text
    assert '"schema": "quwoquan_ops.app_factory_material"' in text
    assert '"materialDigest"' in text
    assert '"artifacts": manifests' in text
    assert 'output = root / "manifest.json"' in text
    assert 'output.write_bytes(canonical_bytes(material) + b"\\n")' in text
    assert "\"appEvidenceDigest\":" not in text
    assert "quwoquan_ops.app_factory_material.v" not in text
    assert "workflow_dispatch" not in text


def test_app_factory_manifest_is_written_before_publish_and_only_read_afterward() -> None:
    payload = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = payload["jobs"]["aggregate"]["steps"]
    material_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Write canonical App factory material"
    )
    publish_index = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("uses") or "").startswith("docker/build-push-action@")
    )
    readback_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Read back published App factory OCI payload"
    )
    identity_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "identity"
    )
    assert material_index < publish_index < readback_index < identity_index
    material_step = steps[material_index]
    assert "APP_EVIDENCE_DIGEST" not in material_step.get("env", {})
    assert 'root / "manifest.json"' in material_step["run"]
    assert 'output.write_bytes(canonical_bytes(material) + b"\\n")' in material_step["run"]
    identity_run = steps[identity_index]["run"]
    assert 'manifest_path = root / "manifest.json"' in identity_run
    assert 'published_manifest_path = published_root / "manifest.json"' in identity_run
    assert "raw = manifest_path.read_bytes()" in identity_run
    assert "published_manifest_path.read_bytes() != raw" in identity_run
    assert "material = {" not in identity_run
    assert "write_bytes(" not in identity_run
    assert steps[publish_index]["with"]["context"] == (
        "${{ runner.temp }}/app-candidate-evidence"
    )


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


def test_promotable_manifest_and_receipt_bind_exact_rc_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    artifact = tmp_path / "shared-web"
    write_valid_web_artifact(artifact)
    result_path = _stackctl_result(
        tmp_path,
        build_product_id="web-shared",
        artifact=artifact,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    attempt = Path(result["attemptDir"])
    manifest_path = attempt / "manifest.json"
    receipt_path = attempt / "build-receipt.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert {
        field: manifest[field] for field in RC_AUTHORITY_MANIFEST
    } == RC_AUTHORITY_MANIFEST
    assert result["manifest"] == manifest
    assert receipt["manifestDigest"] == artifact_digest(manifest_path)

    manifest["rcTagAdmissionRef"] = (
        "ghcr.io/example/quwoquan/rc-tag-admission@sha256:" + "b" * 64
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result["manifest"] = manifest
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifestDigest does not bind"):
        shard_collector.collect(result_path, tmp_path / "tampered")


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
    for field in RC_AUTHORITY_MANIFEST:
        manifest.pop(field, None)
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


def test_hosted_device_workflow_has_no_remaining_entry() -> None:
    assert not (ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml").exists()
    assert not (ROOT / ".github/workflows/beta-device-platform.yml").exists()
