# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-002
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    deploy_official_distribution,
    inspect_official_distribution,
    prevalidate_android_distribution_candidate,
)


class OfficialDistributionReleaseTest(unittest.TestCase):
    def test_android_candidate_prevalidates_download_object_and_latest_pointer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            android_manifest = _android_package(
                root / "android-package",
                build="18201",
            )

            report = prevalidate_android_distribution_candidate(
                package_manifest_path=android_manifest,
                scratch_root=root / "preflight",
            )

            self.assertEqual(report["status"], "component-ready")
            self.assertTrue(report["downloadObjectValidated"])
            self.assertTrue(report["latestPointerValidated"])
            self.assertEqual(report["buildNumber"], "18201")

    def test_web_and_android_are_bound_to_one_release_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            distribution = root / "origin"

            web_receipt = deploy_official_distribution(
                kind="web",
                package_manifest_path=web_manifest,
                release_manifest_path=release_manifest,
                distribution_root=distribution,
            )
            android_receipt = deploy_official_distribution(
                kind="app-release",
                package_manifest_path=android_manifest,
                release_manifest_path=release_manifest,
                distribution_root=distribution,
            )

            self.assertEqual(
                web_receipt["releaseManifestDigest"],
                android_receipt["releaseManifestDigest"],
            )
            self.assertTrue((distribution / "web" / "current").is_symlink())
            latest = json.loads(
                (distribution / "downloads" / "android" / "latest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(latest["buildNumber"], "18201")
            product_ops_environment = (
                distribution / "product-ops/app-release/current.env"
            ).read_text(encoding="utf-8")
            self.assertIn("PRODUCT_OPS_ANDROID_LATEST_BUILD=18201", product_ops_environment)
            self.assertEqual(
                inspect_official_distribution(distribution_root=distribution)["status"],
                "ready",
            )

    def test_android_latest_pointer_uses_cas_and_preserves_old_apk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            first = _android_package(root / "android-18201", build="18201")
            first_release = _release_manifest(
                root / "candidate-1",
                web_manifest=web_manifest,
                android_manifest=first,
            )
            distribution = root / "origin"
            deploy_official_distribution(
                kind="app-release",
                package_manifest_path=first,
                release_manifest_path=first_release,
                distribution_root=distribution,
            )

            second = _android_package(root / "android-18301", build="18301")
            second_release = _release_manifest(
                root / "candidate-2",
                web_manifest=web_manifest,
                android_manifest=second,
            )
            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "CAS conflict",
            ):
                deploy_official_distribution(
                    kind="app-release",
                    package_manifest_path=second,
                    release_manifest_path=second_release,
                    distribution_root=distribution,
                    expected_current="wrong-build",
                )
            deploy_official_distribution(
                kind="app-release",
                package_manifest_path=second,
                release_manifest_path=second_release,
                distribution_root=distribution,
                expected_current="18201",
            )
            self.assertTrue(
                (
                    distribution
                    / "downloads/android/1.8.2/18201/quwoquan-18201.apk"
                ).is_file()
            )
            self.assertEqual(
                json.loads(
                    (distribution / "downloads/android/latest.json").read_text()
                )["buildNumber"],
                "18301",
            )

    def test_rejects_package_not_bound_by_candidate_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            package = json.loads(android_manifest.read_text(encoding="utf-8"))
            package["apkUrl"] = "https://cdn.quwoquan.com/tampered.apk"
            android_manifest.write_text(json.dumps(package), encoding="utf-8")
            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "distribution digest mismatch",
            ):
                deploy_official_distribution(
                    kind="app-release",
                    package_manifest_path=android_manifest,
                    release_manifest_path=release_manifest,
                    distribution_root=root / "origin",
                )


def _web_package(root: Path) -> Path:
    public = root / "public"
    public.mkdir(parents=True)
    (public / "index.html").write_text(
        '<html lang="zh-CN"><head><meta charset="utf-8"></head></html>',
        encoding="utf-8",
    )
    (public / "main.dart.js").write_text("main();", encoding="utf-8")
    (public / "manifest.json").write_text(
        json.dumps({"display": "standalone", "start_url": "/", "scope": "/"}),
        encoding="utf-8",
    )
    (public / "flutter_service_worker.js").write_text("worker();", encoding="utf-8")
    content_digest = _tree_sha256(public)
    manifest = {
        "schema": "qwq.public-web.release.v1",
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
    }
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _android_package(root: Path, *, build: str) -> Path:
    root.mkdir(parents=True)
    apk = root / f"quwoquan-{build}.apk"
    apk.write_bytes(f"signed-apk-{build}".encode("utf-8"))
    manifest = {
        "schema": "qwq.android.official-release.v1",
        "platform": "android",
        "versionName": "1.8.2",
        "buildNumber": build,
        "minAndroidVersion": "26",
        "packageName": "com.quwoquan.quwoquan_app",
        "apkUrl": (
            "https://cdn.quwoquan.com/downloads/android/1.8.2/"
            f"{build}/quwoquan-{build}.apk"
        ),
        "apkSHA256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "apkSizeBytes": apk.stat().st_size,
        "apkSigningCertificateSHA256": "a" * 64,
        "apkHostAllowlist": ["cdn.quwoquan.com"],
        "publicOrigin": "https://quwoquan.com",
        "recoveryUrl": "https://quwoquan.com/download",
        "packagedAPK": apk.name,
    }
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _release_manifest(
    root: Path,
    *,
    web_manifest: Path,
    android_manifest: Path,
) -> Path:
    root.mkdir(parents=True)
    manifest = {
        "schema": "mainline-release-artifact",
        "status": "deployable",
        "artifacts": {
            "publicWeb": {
                "schema": "qwq.public-web.release.v1",
                "manifestSHA256": _sha256_prefixed(web_manifest),
            },
            "androidOfficialRelease": {
                "schema": "qwq.android.official-release.v1",
                "manifestSHA256": _sha256_prefixed(android_manifest),
            },
        },
    }
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    manifest["manifestDigest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_prefixed(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
