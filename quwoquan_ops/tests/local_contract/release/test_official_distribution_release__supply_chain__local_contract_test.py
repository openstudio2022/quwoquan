# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-002
# spec_ref: specs/feature-tree/platform-ops-governance/security-privacy-audit/spec.md#sit-001
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import StringIO
from unittest import mock

from collections.abc import Callable
from pathlib import Path
from typing import Any

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import deploy_domain
from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    deploy_official_distribution,
    inspect_official_distribution,
    prevalidate_android_distribution_candidate,
)
from quwoquan_ops.cli.lib.web_official_release import web_official_content_digest
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)
from quwoquan_ops.tests.support.app_pipeline_web_artifact_test_support import (
    write_valid_web_artifact,
)

SOURCE_GIT_SHA = "b" * 40
SOURCE_TREE = "c" * 40
SOURCE_TREE_DIGEST = "sha1:" + SOURCE_TREE
REQUEST_OCI_REF = "ghcr.io/owner/repo/qualification-request@sha256:" + "1" * 64
ALLOCATION_OCI_REF = "ghcr.io/owner/repo/build-number-allocation@sha256:" + "2" * 64
RC_OCI_REF = "ghcr.io/owner/repo/rc-admission@sha256:" + "3" * 64
APP_OCI_REF = "ghcr.io/owner/repo/app-factory@sha256:" + "4" * 64
SERVICE_OCI_REF = "ghcr.io/owner/repo/service-factory@sha256:" + "5" * 64


class OfficialDistributionReleaseTest(unittest.TestCase):
    def test_android_candidate_prevalidates_download_object_and_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            android_manifest = _android_package(root / "android-package", build="18201")

            report = prevalidate_android_distribution_candidate(
                package_manifest_path=android_manifest,
                scratch_root=root / "preflight",
            )

            self.assertEqual(report["status"], "component-ready")
            self.assertTrue(report["downloadObjectValidated"])
            self.assertTrue(report["latestPointerValidated"])
            self.assertEqual(report["buildNumber"], "18201")

    def test_web_and_android_are_loaded_from_one_formal_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authority = _official_graph(
                root / "authority",
                web_manifest=_web_package(root / "web-package", build="18201"),
                android_manifest=_android_package(root / "android-package", build="18201"),
            )
            distribution = root / "origin"

            web_receipt = _deploy("web", authority, distribution)
            android_receipt = _deploy("app-release", authority, distribution)

            for receipt in (web_receipt, android_receipt):
                self.assertEqual(receipt["stableTag"], "v1.8.2")
                self.assertEqual(receipt["candidateMaterialId"], authority["material_id"])
                self.assertEqual(receipt["releaseTagAdmissionRef"], authority["stable_ref"]["ref"])
                self.assertEqual(receipt["releaseTagAdmissionDigest"], authority["stable_ref"]["digest"])
                self.assertEqual(receipt["appFactoryRef"], APP_OCI_REF)
                self.assertNotIn("artifactDigest", receipt)
                self.assertNotIn("candidateId", receipt)
                readback = json.loads(Path(receipt["receiptPath"]).read_text(encoding="utf-8"))
                self.assertEqual(readback, {key: value for key, value in receipt.items() if key != "receiptPath"})
            self.assertEqual(web_receipt["channelId"], "hosted_web")
            self.assertEqual(android_receipt["channelId"], "official_web")
            self.assertNotEqual(
                web_receipt["selectedAppArtifactDigest"],
                android_receipt["selectedAppArtifactDigest"],
            )
            self.assertTrue((distribution / "web/current").is_symlink())
            latest = json.loads((distribution / "download/android/latest.json").read_text())
            self.assertEqual(latest["buildNumber"], "18201")
            self.assertEqual(
                inspect_official_distribution(distribution_root=distribution)["status"],
                "ready",
            )

    def test_android_latest_pointer_uses_cas_and_preserves_old_apk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _official_graph(
                root / "authority-1",
                web_manifest=_web_package(root / "web-18201", build="18201"),
                android_manifest=_android_package(root / "android-18201", build="18201"),
            )
            distribution = root / "origin"
            _deploy("app-release", first, distribution)

            second = _official_graph(
                root / "authority-2",
                web_manifest=_web_package(root / "web-18301", build="18301"),
                android_manifest=_android_package(root / "android-18301", build="18301"),
            )
            with self.assertRaisesRegex(OfficialDistributionReleaseError, "CAS conflict"):
                _deploy("app-release", second, distribution, expected_current="wrong-build")
            _deploy("app-release", second, distribution, expected_current="18201")

            self.assertTrue(
                (distribution / "download/android/1.8.2/18201/quwoquan-18201.apk").is_file()
            )
            self.assertEqual(
                json.loads((distribution / "download/android/latest.json").read_text())["buildNumber"],
                "18301",
            )

    def test_old_release_evidence_inputs_are_not_a_formal_surface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(TypeError, "unexpected keyword argument"):
                deploy_official_distribution(
                    kind="web",
                    package_manifest_path=root / "package.json",  # type: ignore[call-arg]
                    release_manifest_path=root / "release-manifest.json",  # type: ignore[call-arg]
                    distribution_root=root / "origin",
                )
            self.assertFalse((root / "origin").exists())

    def test_stackctl_parser_accepts_only_exact_formal_distribution_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            graph_root = root / "graph"
            app_factory_root = root / "app-factory"
            graph_root.mkdir()
            app_factory_root.mkdir()
            stable_locator = "release-tags/stable/v1.8.2/admission.json=sha256:" + "a" * 64
            args = stackctl.build_parser().parse_args(
                [
                    "deploy",
                    "--target",
                    "prod-hosted",
                    "--artifact-kind",
                    "web",
                    "--dry-run",
                    "true",
                    "--official-distribution-graph-root",
                    str(graph_root),
                    "--stable-tag-admission",
                    stable_locator,
                    "--app-factory-root",
                    str(app_factory_root),
                ]
            )

            self.assertEqual(args.official_distribution_graph_root, graph_root.resolve())
            self.assertEqual(
                args.stable_tag_admission,
                {
                    "ref": "release-tags/stable/v1.8.2/admission.json",
                    "digest": "sha256:" + "a" * 64,
                },
            )
            self.assertEqual(args.app_factory_root, app_factory_root.resolve())
            self.assertFalse(hasattr(args, "artifact_manifest"))
            self.assertFalse(hasattr(args, "release_manifest"))

            for retired in ("--artifact-manifest", "--release-manifest"):
                with self.subTest(retired=retired), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        stackctl.build_parser().parse_args(
                            [
                                "deploy",
                                "--target",
                                "prod-hosted",
                                "--artifact-kind",
                                "web",
                                retired,
                                "legacy.json",
                            ]
                        )
                    self.assertEqual(raised.exception.code, 2)

            invalid_inputs = (
                (
                    "mutable stable ref",
                    [
                        "--official-distribution-graph-root",
                        str(graph_root),
                        "--stable-tag-admission",
                        "release-tags/stable/current=sha256:" + "a" * 64,
                        "--app-factory-root",
                        str(app_factory_root),
                    ],
                ),
                (
                    "invalid stable digest",
                    [
                        "--official-distribution-graph-root",
                        str(graph_root),
                        "--stable-tag-admission",
                        "release-tags/stable/v1.8.2/admission.json=" + "a" * 64,
                        "--app-factory-root",
                        str(app_factory_root),
                    ],
                ),
                (
                    "relative graph root",
                    [
                        "--official-distribution-graph-root",
                        "relative-graph",
                        "--stable-tag-admission",
                        stable_locator,
                        "--app-factory-root",
                        str(app_factory_root),
                    ],
                ),
                (
                    "missing app factory root",
                    [
                        "--official-distribution-graph-root",
                        str(graph_root),
                        "--stable-tag-admission",
                        stable_locator,
                        "--app-factory-root",
                        str(root / "missing-app-factory"),
                    ],
                ),
            )
            for label, exact_inputs in invalid_inputs:
                with self.subTest(label=label), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        stackctl.build_parser().parse_args(
                            [
                                "deploy",
                                "--target",
                                "prod-hosted",
                                "--artifact-kind",
                                "web",
                                *exact_inputs,
                            ]
                        )
                    self.assertEqual(raised.exception.code, 2)

    def test_stackctl_dispatch_passes_exact_graph_mapping_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            graph_root = root / "graph"
            app_factory_root = root / "app-factory"
            graph_root.mkdir()
            app_factory_root.mkdir()
            stable_ref = {
                "ref": "release-tags/stable/v1.8.2/admission.json",
                "digest": "sha256:" + "a" * 64,
            }
            args = stackctl.build_parser().parse_args(
                [
                    "deploy",
                    "--target",
                    "prod-hosted",
                    "--artifact-kind",
                    "web",
                    "--dry-run",
                    "true",
                    "--official-distribution-graph-root",
                    str(graph_root),
                    "--stable-tag-admission",
                    f"{stable_ref['ref']}={stable_ref['digest']}",
                    "--app-factory-root",
                    str(app_factory_root),
                    "--report-dir",
                    str(root / "reports"),
                ]
            )
            receipt = {
                "candidateMaterialId": "sha256:" + "b" * 64,
                "selectedAppArtifactDigest": "sha256:" + "c" * 64,
                "stableTag": "v1.8.2",
                "receiptSHA256": "sha256:" + "d" * 64,
                "receiptPath": str(root / "dry-run-receipt.json"),
            }

            def fake_deploy(**values: Any) -> dict[str, Any]:
                self.assertFalse(values["distribution_root"].exists())
                return dict(receipt)
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {"prod-hosted": {"env": "prod"}}},
                ),
                mock.patch.object(stackctl, "deploy_official_distribution", side_effect=fake_deploy) as deploy,
                mock.patch.object(stackctl, "write_json"),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_deploy(args)

            self.assertEqual(result["exitCode"], 0)
            deploy.assert_called_once()
            call = deploy.call_args.kwargs
            self.assertEqual(call["kind"], "web")
            self.assertEqual(call["graph_root"], graph_root.resolve())
            self.assertEqual(call["stable_tag_admission_ref"], stable_ref)
            self.assertEqual(call["app_factory_root"], app_factory_root.resolve())
            self.assertIsInstance(call["distribution_root"], Path)
            self.assertFalse(call["distribution_root"].exists())
            self.assertNotIn("package_manifest_path", call)
            self.assertNotIn("release_manifest_path", call)
            self.assertIn("candidateMaterialId=", result["details"][0])
            self.assertIn("selectedAppArtifactDigest=", result["details"][1])
            self.assertIn("stableTag=v1.8.2", result["details"][2])

    def test_stackctl_missing_or_drifted_graph_blocks_before_report_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            graph_root = root / "graph"
            app_factory_root = root / "app-factory"
            graph_root.mkdir()
            app_factory_root.mkdir()
            base = dict(
                artifact_kind="web",
                official_distribution_graph_root=graph_root,
                stable_tag_admission={
                    "ref": "release-tags/stable/v1.8.2/admission.json",
                    "digest": "sha256:" + "a" * 64,
                },
                app_factory_root=app_factory_root,
                env="prod",
                target="prod-hosted",
                dry_run="true",
                distribution_root="",
                expected_current="",
                verify_hosted=False,
                report_dir=str(root / "reports"),
                command="deploy",
            )
            for label, change, expected in (
                (
                    "missing",
                    {"official_distribution_graph_root": None},
                    "official-distribution-graph-root",
                ),
                ("drift", {}, "exact bytes drifted"),
            ):
                with self.subTest(label=label):
                    args = Namespace(**(base | change))
                    with (
                        mock.patch.object(
                            stackctl,
                            "load_environment_topology",
                            return_value={"targets": {"prod-hosted": {"env": "prod"}}},
                        ),
                        mock.patch.object(
                            stackctl,
                            "deploy_official_distribution",
                            side_effect=OfficialDistributionReleaseError("releaseTagAdmission exact bytes drifted"),
                        ) as deploy,
                        mock.patch.object(stackctl, "write_json") as write_json,
                    ):
                        result = deploy_domain._command_deploy_distribution(args)
                    self.assertEqual(result["exitCode"], 2)
                    self.assertIn(expected, result["details"][0])
                    write_json.assert_not_called()
                    if label == "missing":
                        deploy.assert_not_called()
                    else:
                        deploy.assert_called_once()
                    self.assertFalse((root / "reports").exists())

    def test_graph_ref_and_canonical_byte_tamper_block_before_first_write(self) -> None:
        for label, mutate in (
            (
                "exact digest",
                lambda authority: (authority["graph_root"] / authority["qualification_ref"]["ref"]).write_bytes(
                    (authority["graph_root"] / authority["qualification_ref"]["ref"]).read_bytes() + b" "
                ),
            ),
            (
                "canonical JSON",
                lambda authority: _rewrite_stable_noncanonically(authority),
            ),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                authority = _official_graph(
                    root / "authority",
                    web_manifest=_web_package(root / "web", build="18201"),
                    android_manifest=_android_package(root / "android", build="18201"),
                )
                mutate(authority)
                distribution = root / "origin"
                with self.assertRaisesRegex(
                    OfficialDistributionReleaseError,
                    "exact bytes drifted|canonical JSON",
                ):
                    _deploy("web", authority, distribution)
                self.assertFalse(distribution.exists())

    def test_semantic_graph_and_factory_drift_block_before_first_write(self) -> None:
        cases: tuple[tuple[str, Callable[[dict[str, Any]], None], str], ...] = (
            ("source", lambda authority: _mutate_app_material(authority, "sourceGitSha", "f" * 40), "source"),
            ("tree", lambda authority: _mutate_app_material(authority, "sourceTreeDigest", "sha1:" + "f" * 40), "source|tree"),
            ("material", _break_app_material_self_digest, "material digest"),
            ("package", _drift_application_package, "source|package"),
            ("payload", _drift_android_payload, "packageDigest|artifact digest|payload"),
            ("channel", _drift_android_channel, "official|channel|HTTPS"),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                authority = _official_graph(
                    root / "authority",
                    web_manifest=_web_package(root / "web", build="18201"),
                    android_manifest=_android_package(root / "android", build="18201"),
                )
                mutate(authority)
                distribution = root / "origin"
                with self.assertRaisesRegex(OfficialDistributionReleaseError, expected):
                    _deploy("app-release", authority, distribution)
                self.assertFalse(distribution.exists())


def _deploy(
    kind: str,
    authority: dict[str, Any],
    distribution_root: Path,
    *,
    expected_current: str = "",
) -> dict[str, Any]:
    return deploy_official_distribution(
        kind=kind,
        graph_root=authority["graph_root"],
        stable_tag_admission_ref=authority["stable_ref"],
        app_factory_root=authority["app_factory_root"],
        distribution_root=distribution_root,
        expected_current=expected_current,
    )


def _artifact_manifest(
    build_product_id: str,
    artifact_digest: str,
    build: str,
    *,
    source_git_sha: str = SOURCE_GIT_SHA,
    source_tree_digest: str = SOURCE_TREE_DIGEST,
) -> dict[str, Any]:
    value = app_artifact_manifest(
        build_product_id=build_product_id,
        source_git_sha=source_git_sha,
        source_tree_digest=source_tree_digest,
        artifact_digest=artifact_digest,
    )
    value.update(
        {
            "displayVersion": "1.8.2",
            "buildNumber": build,
            "qualificationRequestRef": REQUEST_OCI_REF,
            "qualificationRequestDigest": REQUEST_OCI_REF.rsplit("@", 1)[1],
            "rcTagAdmissionRef": RC_OCI_REF,
            "artifactBuildNumberAllocationRef": ALLOCATION_OCI_REF,
            "artifactBuildNumberAllocationDigest": ALLOCATION_OCI_REF.rsplit("@", 1)[1],
            "promotable": True,
        }
    )
    return value


def _web_package(root: Path, *, build: str = "18201") -> Path:
    public = root / "public"
    root.mkdir(parents=True)
    write_valid_web_artifact(public)
    content_digest = _tree_sha256(public)
    manifest = {
        "schema": "client-app.web.official-release",
        "sourceGitSha": SOURCE_GIT_SHA,
        "sourceTreeDigest": SOURCE_TREE_DIGEST,
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
        "artifactManifest": _artifact_manifest(
            "web-shared", "sha256:" + content_digest, build
        ),
    }
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _android_package(
    root: Path,
    *,
    build: str,
    source_git_sha: str = SOURCE_GIT_SHA,
    source_tree_digest: str = SOURCE_TREE_DIGEST,
) -> Path:
    root.mkdir(parents=True)
    apk = root / f"quwoquan-{build}.apk"
    apk.write_bytes(f"signed-apk-{build}".encode())
    apk_digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    manifest = {
        "schema": "client-app.android.official-release",
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "platform": "android",
        "versionName": "1.8.2",
        "buildNumber": build,
        "minAndroidVersion": "26",
        "packageName": "com.leadwise.quwoquan",
        "apkUrl": f"https://cdn.quwoquan.com/download/android/1.8.2/{build}/quwoquan-{build}.apk",
        "apkSHA256": apk_digest,
        "apkSizeBytes": apk.stat().st_size,
        "apkSigningCertificateSHA256": "a" * 64,
        "apkHostAllowlist": ["cdn.quwoquan.com"],
        "publicOrigin": "https://quwoquan.com",
        "recoveryUrl": "https://quwoquan.com/download",
        "updateUrl": f"https://cdn.quwoquan.com/download/android/1.8.2/{build}/quwoquan-{build}.apk",
        "minimumSupportedVersion": "1.7.0",
        "minimumSupportedBuild": "17000",
        "packagedAPK": apk.name,
        "remoteVerified": False,
        "artifactManifest": _artifact_manifest(
            "android-prod-apk",
            "sha256:" + apk_digest,
            build,
            source_git_sha=source_git_sha,
            source_tree_digest=source_tree_digest,
        ),
    }
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _official_graph(
    root: Path,
    *,
    web_manifest: Path,
    android_manifest: Path,
) -> dict[str, Any]:
    graph_root = root / "graph"
    app_root = root / "app-factory"
    graph_root.mkdir(parents=True)
    app_root.mkdir(parents=True)
    web = json.loads(web_manifest.read_text(encoding="utf-8"))
    android = json.loads(android_manifest.read_text(encoding="utf-8"))
    build = str(android["buildNumber"])
    source_git_sha = str(android["artifactManifest"]["sourceGitSha"])
    source_tree_digest = str(android["artifactManifest"]["sourceTreeDigest"])
    source_tree = source_tree_digest.split(":", 1)[1]
    if (
        web["artifactManifest"]["buildNumber"] != build
        or web["artifactManifest"]["sourceGitSha"] != source_git_sha
        or web["artifactManifest"]["sourceTreeDigest"] != source_tree_digest
    ):
        raise AssertionError("test factory inputs must share source/tree/build identity")

    android_payload_root = app_root / "payloads/android-prod-apk"
    android_payload_root.mkdir(parents=True)
    shutil.copy2(
        android_manifest.parent / android["packagedAPK"],
        android_payload_root / "app-release.apk",
    )
    web_payload_root = app_root / "payloads/web-shared"
    shutil.copytree(web_manifest.parent / "public", web_payload_root / "public-web")
    _write_json(app_root / "android-release-manifest.json", android)
    _write_json(app_root / "public-web-manifest.json", web)

    for product_id, special, payload_root in (
        ("android-prod-apk", android, android_payload_root),
        ("web-shared", web, web_payload_root),
    ):
        descriptor = {
            "schema": "release-application-package",
            "buildProductId": product_id,
            "buildProfile": special["artifactManifest"]["buildProfile"],
            "platform": special["artifactManifest"]["platform"],
            "sourceGitSha": source_git_sha,
            "sourceTreeDigest": source_tree_digest,
            "packageDigest": _application_package_digest(payload_root),
            "artifactManifest": special["artifactManifest"],
        }
        destination = app_root / f"application-packages/{product_id}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        _write_json(destination, descriptor)

    ios = _artifact_manifest(
        "ios-prod-app",
        "sha256:" + hashlib.sha256(b"ios-app").hexdigest(),
        build,
        source_git_sha=source_git_sha,
        source_tree_digest=source_tree_digest,
    )
    artifacts = {
        "android": android["artifactManifest"],
        "ios": ios,
        "web": web["artifactManifest"],
    }
    app_material: dict[str, Any] = {
        "schema": "quwoquan_ops.app_factory_material",
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "qualificationRequest": {
            "ref": REQUEST_OCI_REF,
            "digest": REQUEST_OCI_REF.rsplit("@", 1)[1],
        },
        "rcTagAdmissionRef": RC_OCI_REF,
        "artifactBuildNumber": _build_number_value(build),
        "artifactBuildNumberAllocation": {
            "ref": ALLOCATION_OCI_REF,
            "digest": ALLOCATION_OCI_REF.rsplit("@", 1)[1],
        },
        "artifacts": artifacts,
    }
    app_material["materialDigest"] = _digest_object(app_material)
    _write_fact(app_root / "manifest.json", app_material)

    request_body: dict[str, Any] = {
        "schema": "quwoquan_ops.release_qualification_request.v1",
        "rcTagAdmission": {"ref": RC_OCI_REF, "digest": "sha256:" + "6" * 64},
        "tagName": "v1.8.2-rc.1",
        "sourceGitSha": source_git_sha,
        "sourceTree": source_tree,
    }
    request_body["requestId"] = _digest_object(request_body)
    request_ref = _write_exact(graph_root, "qualification/request.json", request_body)
    allocation_body: dict[str, Any] = {
        "schema": "quwoquan_ops.artifact_build_number_allocation.v1",
        "requestId": request_body["requestId"],
        "qualificationRequest": request_ref,
        "artifactBuildNumber": _build_number_value(build),
        "predecessor": None,
        "hostedAuthority": {
            "provider": "github_actions_workflow_run_number",
            "runId": "9001",
            "runNumber": _build_number_value(build),
        },
    }
    allocation_body["allocationId"] = _digest_object(allocation_body)
    allocation_ref = _write_exact(graph_root, "qualification/allocation.json", allocation_body)

    exact_artifacts = [
        {"platform": platform, "ociRef": APP_OCI_REF, "digest": APP_OCI_REF.rsplit("@", 1)[1]}
        for platform in ("android", "ios")
    ] + [
        {"platform": "service", "ociRef": SERVICE_OCI_REF, "digest": SERVICE_OCI_REF.rsplit("@", 1)[1]},
        {"platform": "web", "ociRef": APP_OCI_REF, "digest": APP_OCI_REF.rsplit("@", 1)[1]},
    ]
    app_output = {
        "ociRef": APP_OCI_REF,
        "ociDigest": APP_OCI_REF.rsplit("@", 1)[1],
        "payloadDigest": _sha256_prefixed(app_root / "manifest.json"),
        "materialDigest": app_material["materialDigest"],
        "artifactDigests": {
            platform: manifest["artifactDigest"] for platform, manifest in artifacts.items()
        },
        "artifactManifests": artifacts,
        "sourceTreeDigest": source_tree_digest,
    }
    material_body: dict[str, Any] = {
        "schema": "quwoquan_ops.candidate_material_manifest.v1",
        "qualificationRequest": request_ref,
        "qualificationRequestOciRef": REQUEST_OCI_REF,
        "sourceGitSha": source_git_sha,
        "sourceTree": source_tree,
        "tagName": "v1.8.2-rc.1",
        "artifactBuildNumber": _build_number_value(build),
        "artifactBuildNumberAllocation": allocation_ref,
        "artifactBuildNumberAllocationOciRef": ALLOCATION_OCI_REF,
        "productVersionManifest": {"ref": "source/product-version.json", "digest": "sha256:" + "7" * 64},
        "artifacts": exact_artifacts,
        "factoryOutputs": {
            "service": {"ociRef": SERVICE_OCI_REF},
            "app": app_output,
            "qualificationRequestOciRef": REQUEST_OCI_REF,
            "artifactBuildNumberAllocationOciRef": ALLOCATION_OCI_REF,
        },
        "supplyChainSubjects": [APP_OCI_REF, SERVICE_OCI_REF],
        "artifactByteDigests": {
            **app_output["artifactDigests"],
            "service": "sha256:" + "8" * 64,
        },
        "buildPolicy": "build_sign_attest_once",
        "createdAt": "2026-09-05T10:20:00Z",
    }
    material_body["materialId"] = _digest_object(material_body)
    material_ref = _write_exact(graph_root, "qualification/material.json", material_body)
    qualification_body: dict[str, Any] = {
        "schema": "quwoquan_ops.qualification_fact.v1",
        "decision": "qualified",
        "qualificationRequest": request_ref,
        "candidateMaterialManifest": material_ref,
        "sourceGitSha": source_git_sha,
        "sourceTree": source_tree,
        "tagName": "v1.8.2-rc.1",
        "artifactBuildNumber": _build_number_value(build),
        "artifacts": exact_artifacts,
        "evidence": {},
        "qualifiedAt": "2026-09-05T10:30:00Z",
    }
    qualification_body["qualificationId"] = _digest_object(qualification_body)
    qualification_ref = _write_exact(graph_root, "qualification/fact.json", qualification_body)
    stable_body: dict[str, Any] = {
        "schema": "quwoquan_ops.release_tag_admission_fact.v1",
        "decision": "admitted",
        "tagKind": "stable",
        "tagName": "v1.8.2",
        "tagObjectOid": "d" * 40,
        "peeledCommit": source_git_sha,
        "sourceTree": source_tree,
        "qualificationFact": qualification_ref,
        "qualificationId": qualification_body["qualificationId"],
        "candidateMaterialManifest": material_ref,
        "candidateMaterialId": material_body["materialId"],
        "candidateIdentity": "sha256:" + "9" * 64,
        "artifactBuildNumber": _build_number_value(build),
        "artifacts": exact_artifacts,
        "admittedAt": "2026-09-05T11:00:00Z",
    }
    stable_body["admissionId"] = _digest_object(stable_body)
    stable_ref = _write_exact(graph_root, "release-tags/stable/v1.8.2/admission.json", stable_body)
    return {
        "graph_root": graph_root,
        "app_factory_root": app_root,
        "stable_ref": stable_ref,
        "qualification_ref": qualification_ref,
        "material_ref": material_ref,
        "material_id": material_body["materialId"],
    }


def _build_number_value(value: str) -> int:
    normalized = int(value)
    if normalized < 1:
        raise AssertionError("test build number must be positive")
    return normalized


def _rewrite_stable_noncanonically(authority: dict[str, Any]) -> None:
    path = authority["graph_root"] / authority["stable_ref"]["ref"]
    payload = json.loads(path.read_text())
    _write_json(path, payload)
    authority["stable_ref"] = {"ref": authority["stable_ref"]["ref"], "digest": _sha256_prefixed(path)}


def _mutate_app_material(authority: dict[str, Any], field: str, value: Any) -> None:
    path = authority["app_factory_root"] / "manifest.json"
    payload = json.loads(path.read_text())
    payload[field] = value
    payload.pop("materialDigest")
    payload["materialDigest"] = _digest_object(payload)
    _write_fact(path, payload)
    _rebind_app_payload(authority)


def _break_app_material_self_digest(authority: dict[str, Any]) -> None:
    path = authority["app_factory_root"] / "manifest.json"
    payload = json.loads(path.read_text())
    payload["materialDigest"] = "sha256:" + "f" * 64
    _write_fact(path, payload)
    _rebind_app_payload(authority, carry_material_digest=True)


def _rebind_app_payload(authority: dict[str, Any], *, carry_material_digest: bool = True) -> None:
    app_path = authority["app_factory_root"] / "manifest.json"
    app = json.loads(app_path.read_text())
    material_path = authority["graph_root"] / authority["material_ref"]["ref"]
    material = json.loads(material_path.read_text())
    material["factoryOutputs"]["app"]["payloadDigest"] = _sha256_prefixed(app_path)
    if carry_material_digest:
        material["factoryOutputs"]["app"]["materialDigest"] = app["materialDigest"]
    material.pop("materialId")
    material["materialId"] = _digest_object(material)
    authority["material_ref"] = _write_exact(
        authority["graph_root"], authority["material_ref"]["ref"], material
    )
    qualification_path = authority["graph_root"] / authority["qualification_ref"]["ref"]
    qualification = json.loads(qualification_path.read_text())
    qualification["candidateMaterialManifest"] = authority["material_ref"]
    qualification.pop("qualificationId")
    qualification["qualificationId"] = _digest_object(qualification)
    authority["qualification_ref"] = _write_exact(
        authority["graph_root"], authority["qualification_ref"]["ref"], qualification
    )
    stable_path = authority["graph_root"] / authority["stable_ref"]["ref"]
    stable = json.loads(stable_path.read_text())
    stable["candidateMaterialManifest"] = authority["material_ref"]
    stable["candidateMaterialId"] = material["materialId"]
    stable["qualificationFact"] = authority["qualification_ref"]
    stable["qualificationId"] = qualification["qualificationId"]
    stable.pop("admissionId")
    stable["admissionId"] = _digest_object(stable)
    authority["stable_ref"] = _write_exact(
        authority["graph_root"], authority["stable_ref"]["ref"], stable
    )
    authority["material_id"] = material["materialId"]


def _drift_application_package(authority: dict[str, Any]) -> None:
    path = authority["app_factory_root"] / "application-packages/android-prod-apk.json"
    payload = json.loads(path.read_text())
    payload["sourceGitSha"] = "f" * 40
    _write_json(path, payload)


def _drift_android_payload(authority: dict[str, Any]) -> None:
    path = authority["app_factory_root"] / "payloads/android-prod-apk/app-release.apk"
    path.write_bytes(path.read_bytes() + b"tamper")


def _drift_android_channel(authority: dict[str, Any]) -> None:
    path = authority["app_factory_root"] / "android-release-manifest.json"
    payload = json.loads(path.read_text())
    payload["apkUrl"] = payload["apkUrl"].replace("cdn.quwoquan.com", "evil.example")
    _write_json(path, payload)


def _write_exact(root: Path, relative: str, payload: dict[str, Any]) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_fact(path, payload)
    return {"ref": relative, "digest": _sha256_prefixed(path)}


def _write_fact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest_object(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _sha256_prefixed(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _application_package_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    return web_official_content_digest(root)


if __name__ == "__main__":
    unittest.main()
