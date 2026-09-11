"""spec_ref: runtime/runtime-config/environment-topology-and-packaging/spec.md#GWT-007"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from quwoquan_app.scripts.device.app_source_isolation import (
    SourceIsolationError, audit_source_closure, project_source_inputs,
    project_repository_inputs, materialize_alpha_assets, verify_projection_identity,
    freeze_repository_inputs, derive_frozen_projection,
)
from quwoquan_app.scripts.runtime.architecture.verify_production_release_artifact import scan_artifact, _scan_stream


class AppSourceIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "source"
        self.write("pubspec.yaml", "name: quwoquan_app\ndependencies: {}\nflutter:\n  assets: []\n")
        self.write("lib/main_prod.dart", "void main() {}\n")

    def write(self, relative, text):
        path = self.app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_remote_closure_excludes_unreachable_alpha_and_tests(self):
        self.write("lib/adapters/post_reader_bundled.dart", "class BundledContentPostReader {}")
        self.write("test/fixture.dart", "void fixture() {}")
        report = audit_source_closure(self.app, "lib/main_prod.dart")
        self.assertEqual(report["sourceFiles"], ["lib/main_prod.dart"])
        projected = self.root / "projection"
        project_source_inputs(self.app, projected, entrypoint="lib/main_prod.dart")
        self.assertFalse((projected / "lib/adapters/post_reader_bundled.dart").exists())
        self.assertFalse((projected / "test").exists())
        self.assertTrue((self.app / "lib/adapters/post_reader_bundled.dart").exists())

    def test_runtime_false_branch_does_not_hide_alpha_import(self):
        self.write("lib/main_prod.dart", "import 'adapters/post_reader_bundled.dart';\nvoid main() { if (false) {} }")
        self.write("lib/adapters/post_reader_bundled.dart", "class BundledContentPostReader {}")
        with self.assertRaisesRegex(SourceIsolationError, "main_prod.dart.*post_reader_bundled.dart"):
            audit_source_closure(self.app, "lib/main_prod.dart")

    def test_conditional_export_and_part_are_included(self):
        self.write("lib/main_prod.dart", "export 'safe.dart' if (dart.library.io) 'bad.dart';")
        self.write("lib/safe.dart", "library safe;")
        self.write("lib/bad.dart", "part 'test_fixtures/fixture.dart';")
        self.write("lib/test_fixtures/fixture.dart", "part of '../bad.dart';")
        with self.assertRaisesRegex(SourceIsolationError, "test_fixtures"):
            audit_source_closure(self.app, "lib/main_prod.dart")

    def test_multiline_directives_and_comments(self):
        self.write("lib/main_prod.dart", "/* import 'missing.dart'; */\nexport\n 'safe.dart';\n// import 'missing2.dart';")
        self.write("lib/safe.dart", "library safe;")
        self.assertEqual(len(audit_source_closure(self.app, "lib/main_prod.dart")["sourceFiles"]), 2)

    def test_missing_source_symlink_and_escape_fail_closed(self):
        self.write("lib/main_prod.dart", "import 'missing.dart';")
        with self.assertRaisesRegex(SourceIsolationError, "missing"):
            audit_source_closure(self.app, "lib/main_prod.dart")
        self.write("lib/main_prod.dart", "import '../../outside.dart';")
        (self.root / "outside.dart").write_text("library outside;")
        with self.assertRaisesRegex(SourceIsolationError, "escape"):
            audit_source_closure(self.app, "lib/main_prod.dart")
        self.write("lib/main_prod.dart", "import 'link.dart';")
        (self.app / "lib/link.dart").symlink_to(self.root / "outside.dart")
        with self.assertRaises(SourceIsolationError):
            audit_source_closure(self.app, "lib/main_prod.dart")

    def test_pubspec_flavor_cannot_hide_alpha_asset(self):
        self.write("pubspec.yaml", "name: quwoquan_app\nflutter:\n  assets:\n    - path: assets/content/alpha/manifest.json\n      flavors: [nonprod]\n")
        with self.assertRaisesRegex(SourceIsolationError, "assets/content/alpha"):
            audit_source_closure(self.app, "lib/main_prod.dart")

    def test_parent_asset_directory_cannot_hide_alpha_payload(self):
        self.write("pubspec.yaml", "name: quwoquan_app\nflutter:\n  assets: [assets/content/]\n")
        self.write("assets/content/alpha/manifest.json", "{}")
        with self.assertRaisesRegex(SourceIsolationError, "assets/content/alpha"):
            audit_source_closure(self.app, "lib/main_prod.dart")

    def test_path_package_dependency_is_walked(self):
        self.write("pubspec.yaml", "name: quwoquan_app\ndependencies:\n  helper:\n    path: packages/helper\n")
        self.write("lib/main_prod.dart", "import 'package:helper/helper.dart';")
        self.write("packages/helper/pubspec.yaml", "name: helper\n")
        self.write("packages/helper/lib/helper.dart", "import 'fixture.dart';")
        self.write("packages/helper/lib/fixture.dart", "class MockContentRepository {}")
        with self.assertRaisesRegex(SourceIsolationError, "fixture"):
            audit_source_closure(self.app, "lib/main_prod.dart")

    def test_alpha_projection_adds_exact_snapshot_only_privately(self):
        self.write("lib/main_alpha.dart", "import 'adapters/post_reader_bundled.dart';")
        self.write("lib/adapters/post_reader_bundled.dart", "class BundledContentPostReader {}")
        self.write("assets/content/alpha/manifest.json", "{\"canonical\":true}")
        self.write("assets/content/alpha/bundle_identity.json", "{}")
        self.write("assets/content/alpha/media/video.mp4", "canonical-media")
        before = (self.app / "pubspec.yaml").read_bytes()
        projection = self.root / "alpha"
        report = project_source_inputs(self.app, projection, entrypoint="lib/main_alpha.dart", alpha=True)
        self.assertEqual((projection / "assets/content/alpha/manifest.json").read_bytes(), (self.app / "assets/content/alpha/manifest.json").read_bytes())
        self.assertEqual((self.app / "pubspec.yaml").read_bytes(), before)
        self.assertIn("assets/content/alpha", (projection / "pubspec.yaml").read_text())
        self.assertFalse(report["artifactVerified"])

    def test_alpha_still_rejects_mock_and_fixture(self):
        self.write("lib/main_alpha.dart", "import 'test/fixture.dart';")
        self.write("lib/test/fixture.dart", "class MockReader {}")
        with self.assertRaises(SourceIsolationError):
            audit_source_closure(self.app, "lib/main_alpha.dart", alpha=True)

    def test_projection_refuses_existing_or_source_destination(self):
        with self.assertRaises(SourceIsolationError):
            project_source_inputs(self.app, self.app, entrypoint="lib/main_prod.dart")
        with self.assertRaises(SourceIsolationError):
            project_source_inputs(self.app, self.app / "nested", entrypoint="lib/main_prod.dart")

    def test_real_snapshot_native_asset_supply_and_online_rejection(self):
        repository = Path(__file__).resolve().parents[4]
        assets = self.root / "flutter_assets"
        materialize_alpha_assets(repository / "quwoquan_app", assets, entrypoint="lib/main_alpha.dart")
        self.assertEqual((assets / "assets/content/alpha/manifest.json").read_bytes(),
                         (repository / "quwoquan_app/assets/content/alpha/manifest.json").read_bytes())
        with self.assertRaisesRegex(SourceIsolationError, "stale Alpha"):
            materialize_alpha_assets(repository / "quwoquan_app", assets, entrypoint="lib/main_prod.dart")

    def test_real_repository_online_projection_preserves_sibling_package(self):
        repository = Path(__file__).resolve().parents[4]
        destination = self.root / "real-repo"
        report = project_repository_inputs(repository, destination, entrypoint="lib/main_prod.dart")
        self.assertGreater(len(report["sourceFiles"]), 1000)
        self.assertTrue((destination / "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors/pubspec.yaml").is_file())
        self.assertFalse((destination / "quwoquan_app/assets/content/alpha").exists())
        self.assertFalse((destination / "quwoquan_app/lib/main_alpha.dart").exists())
        second = audit_source_closure(destination / "quwoquan_app", "lib/main_prod.dart")
        self.assertEqual(second["sourceDigests"], report["sourceDigests"])

    def test_real_repository_alpha_projection_has_assets_and_sibling_packages(self):
        repository = Path(__file__).resolve().parents[4]
        destination = self.root / "real-alpha"
        report = project_repository_inputs(repository, destination, entrypoint="lib/main_alpha.dart")
        self.assertGreater(len(report["sourceFiles"]), 1000)
        self.assertTrue((destination / "quwoquan_app/lib/runtime/di/alpha_dependencies.dart").is_file())
        self.assertTrue((destination / "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors/pubspec.yaml").is_file())
        self.assertIn("assets/content/alpha/manifest.json", (destination / "quwoquan_app/pubspec.yaml").read_text())
        self.assertFalse((destination / "quwoquan_app/test_host").exists())
        second = audit_source_closure(destination / "quwoquan_app", "lib/main_alpha.dart", alpha=True)
        self.assertEqual(second["sourceDigests"], report["sourceDigests"])
        self.assertEqual(verify_projection_identity(destination)[0], report["sourceGitSha"])
        (destination / "quwoquan_app/lib/main_alpha.dart").write_text("void main() {}")
        with self.assertRaisesRegex(SourceIsolationError, "source bytes drifted"):
            verify_projection_identity(destination)

    def test_real_frozen_cohort_derives_without_any_live_git_reads(self):
        from unittest.mock import patch
        repository = Path(__file__).resolve().parents[4]
        frozen = self.root / "frozen"
        freeze_repository_inputs(repository, frozen)
        with patch("quwoquan_app.scripts.device.app_source_isolation.subprocess.check_output", side_effect=AssertionError("frozen derivation must not read live Git")):
            alpha = derive_frozen_projection(frozen, self.root / "cohort-alpha", entrypoint="lib/main_alpha.dart")
            remote = derive_frozen_projection(frozen, self.root / "cohort-remote", entrypoint="lib/main_prod.dart")
            common = set(alpha["sourceDigests"]) & set(remote["sourceDigests"])
            self.assertGreater(len(common), 1000)
            self.assertTrue(all(alpha["sourceDigests"][p] == remote["sourceDigests"][p] for p in common))
            self.assertEqual(alpha["frozenSourceManifestDigest"], remote["frozenSourceManifestDigest"])
            self.assertEqual(verify_projection_identity(self.root / "cohort-alpha"), verify_projection_identity(self.root / "cohort-remote"))
        self.assertFalse((self.root / "cohort-remote/quwoquan_app/lib/main_alpha.dart").exists())
        self.assertFalse((self.root / "cohort-remote/quwoquan_app/assets/content/alpha").exists())
        # 临时测试输入由本用例独占，解除只读仅用于 TemporaryDirectory 清理。
        for path in frozen.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        frozen.chmod(0o700)

    def test_sdk_comment_is_not_test_package_but_actual_import_is(self):
        import io
        _, comments = _scan_stream("kernel_blob.bin", io.BytesIO(b"/// for example [integration_test] library"))
        self.assertFalse(comments)
        _, implementation = _scan_stream("kernel_blob.bin", io.BytesIO(b"package:integration_test/integration_test.dart"))
        self.assertIn(b"package:integration_test/", implementation)

    def test_streaming_scanner_keeps_markers_across_chunk_boundary(self):
        import io
        payload = b"x" * (1024 * 1024 - 4) + b"BundledProfileQuery" + b"suffix"
        entry, markers = _scan_stream("kernel_blob.bin", io.BytesIO(payload))
        self.assertIn(b"BundledProfileQuery", markers)
        self.assertEqual(entry["sizeBytes"], len(payload))

    def test_artifact_rejects_alpha_assets_even_when_not_consumed(self):
        apk = self.root / "app.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("assets/flutter_assets/assets/content/alpha/manifest.json", "{}")
        findings, _ = scan_artifact(apk, "android")
        self.assertTrue(any("assets/content/alpha" in finding for finding in findings))
