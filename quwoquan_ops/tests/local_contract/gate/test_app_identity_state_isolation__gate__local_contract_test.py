"""身份单轨门禁：真实源码正例与最小变异负例，不执行 Flutter/Xcode。

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_app/scripts/runtime/platform/verify_app_identity_state_isolation.py"
SCANNED_RUNTIME_PATHS = (
    "run.sh", "scripts/device/run_app_instance.sh", "scripts/device/run_app_instance.py",
    "scripts/device/verify_ios_hot_restart.py", "scripts/device/build_startup_environment_matrix.py",
    "scripts/ios/build_prepare_dart_defines.sh",
)
EXECUTOR = "scripts/device/run_app_instance.py"
MATRIX = "scripts/device/build_startup_environment_matrix.py"
IDENTITY = "android/app/app_identity.generated.json"
EXECUTOR_ISSUE = "canonical executor drivers must bind flavor, profile and source through canonical identity"
MATRIX_ISSUE = "startup matrix must bind canonical flavor, mode, source and isolated cache key"


def _load_module():
    spec = importlib.util.spec_from_file_location("identity_isolation_gate", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _canonical_tree(root: Path) -> Path:
    app = root / "quwoquan_app"
    for relative in (*SCANNED_RUNTIME_PATHS, "pubspec.yaml", IDENTITY):
        _write(app / relative, (ROOT / "quwoquan_app" / relative).read_text())
    for name in ("alpha", "beta", "gamma"):
        _write(app / f"ios/Runner.xcodeproj/xcshareddata/xcschemes/{name}.xcscheme", "<Scheme/>")
    return app


class AppIdentityStateIsolationGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.app = _canonical_tree(self.root)
        self.assertEqual(self.module.collect_issues(self.root), [])

    def _mutation(self, relative: str, old: str, new: str, issue: str, *, all_matches=False) -> None:
        path = self.app / relative
        original = path.read_text()
        self.assertIn(old, original)
        try:
            path.write_text(original.replace(old, new, -1 if all_matches else 1))
            self.assertIn(issue, self.module.collect_issues(self.root))
        finally:
            path.write_text(original)

    def test_real_repository_and_cli(self) -> None:
        self.assertEqual(self.module.collect_issues(ROOT), [])
        self.assertEqual(self.module.main(["--repo-root", str(self.root)]), 0)
        _write(self.app / "ios/Flutter/QWQEnvironment.xcconfig", "QWQ_ENV=alpha")
        self.assertEqual(self.module.main(["--repo-root", str(self.root)]), 1)

    def test_every_driver_rejects_hardcoded_or_direct_environment_flavor(self) -> None:
        path = self.app / EXECUTOR
        original = path.read_text()
        for class_name in ("AndroidPlatformDriver", "IOSSimulatorPlatformDriver", "IOSPhysicalPlatformDriver"):
            for replacement in ('"nonprod"', '"beta"', 'self.launch_handoff["environment"]'):
                with self.subTest(driver=class_name, replacement=replacement):
                    index = original.index("class " + class_name)
                    prefix, selected = original[:index], original[index:]
                    path.write_text(prefix + selected.replace("self.build_identity().flavor", replacement, 1))
                    self.assertIn(EXECUTOR_ISSUE, self.module.collect_issues(self.root))
        path.write_text(original)

    def test_executor_rejects_bypassed_resolver_and_missing_identity_bindings(self) -> None:
        cases = (
            ('environment=str(handoff["environment"])', 'environment="alpha"'),
            ('build_profile=str(handoff["buildProfile"])', 'build_profile="nonprod"'),
            ('build_mode="debug"', 'build_mode="release"'),
            ('from quwoquan_ops.cli.lib.app_identity import resolve_app_identity', 'from second_matrix import resolve_app_identity'),
            ('return identity', 'return self.unverified_identity'),
            ('if identity.application_id != self.application_id:', 'if False:'),
            ('if self.entrypoint != expected:', 'if False:'),
            ('driver.launch_handoff = handoff', 'driver.launch_handoff = {}'),
        )
        for old, new in cases:
            with self.subTest(mutation=old):
                self._mutation(EXECUTOR, old, new, EXECUTOR_ISSUE)

    def test_matrix_rejects_flavor_bypass_and_cache_dimension_loss(self) -> None:
        cases = (
            ('"--flavor", identity.flavor', '"--flavor", "nonprod"'),
            ('"--flavor", identity.flavor', '"--flavor", handoff["environment"]'),
            ('environment=str(handoff["environment"])', 'environment="alpha"'),
            ('from quwoquan_ops.cli.lib.app_identity import resolve_app_identity', 'from second_matrix import resolve_app_identity'),
            ('"release" if handoff["environment"] == "prod" else "debug"', '"debug"'),
            ('{identity.flavor}/{identity.build_mode}', '{identity.build_profile}/{identity.build_mode}'),
            ('{identity.flavor}/{identity.build_mode}', '{identity.flavor}'),
            ('return selector + ":" + str(handoff["entrypoint"]), platform', 'return selector, platform'),
            ('if handoff["entrypoint"] != expected:', 'if False:'),
            ('if build_profile_for_environment(runtime_environment) != build_profile:', 'if False:'),
            ('key = _build_key(platform, handoff)', 'key = (handoff["buildProfile"], platform)'),
            ('existing = compiled.get(key)', 'existing = compiled.get(platform)'),
            ('runtime_environment=environment,', 'runtime_environment="alpha",'),
        )
        for old, new in cases:
            with self.subTest(mutation=old):
                self._mutation(MATRIX, old, new, MATRIX_ISSUE)

    def test_missing_or_syntactically_invalid_consumers_fail_closed(self) -> None:
        for relative, issue in ((EXECUTOR, EXECUTOR_ISSUE), (MATRIX, MATRIX_ISSUE)):
            path = self.app / relative
            original = path.read_text()
            for source in ("# canonical resolver mentioned only in comments\n", "invalid python !"):
                path.write_text(source)
                self.assertIn(issue, self.module.collect_issues(self.root))
            path.write_text(original)

    def test_retired_shared_files_and_every_runtime_reference_are_rejected(self) -> None:
        for relative in ("ios/Flutter/QWQEnvironment.xcconfig", "scripts/ios/write_environment_xcconfig.sh"):
            path = self.app / relative
            _write(path, "retired")
            self.assertIn(f"shared mutable App identity state must not exist: quwoquan_app/{relative}", self.module.collect_issues(self.root))
            path.unlink()
        for relative in SCANNED_RUNTIME_PATHS:
            for marker in ("write_environment_xcconfig", "QWQEnvironment.xcconfig"):
                path = self.app / relative
                original = path.read_text()
                path.write_text(original + f"\n# {marker}\n")
                self.assertIn(f"runtime path mutates or consumes retired identity state: quwoquan_app/{relative}", self.module.collect_issues(self.root))
                path.write_text(original)

    def test_launcher_cannot_own_second_flavor_track(self) -> None:
        path = self.app / "run.sh"
        original = path.read_text()
        path.write_text('flutter run --flavor "$QWQ_APP_RUNTIME_ENV"\n')
        issues = self.module.collect_issues(self.root)
        self.assertIn("run.sh must not own a second Flutter buildProfile selection", issues)
        self.assertIn("run.sh must delegate buildProfile selection to canonical executor", issues)
        path.write_text(original + "\n# flutter run --flavor is not executed here\n")
        self.assertEqual(self.module.collect_issues(self.root), [])
        _write(self.app / "scripts/device/run_app_instance.sh", "flutter run\n")
        self.assertIn("run_app_instance.sh must delegate non-Prod flavor selection to run.sh", self.module.collect_issues(self.root))

    def test_runner_scheme_and_missing_development_scheme_are_rejected(self) -> None:
        schemes = self.app / "ios/Runner.xcodeproj/xcshareddata/xcschemes"
        _write(schemes / "Runner.xcscheme", "<Scheme/>")
        self.assertIn("unflavored shared Runner scheme must not remain selectable", self.module.collect_issues(self.root))
        (schemes / "beta.xcscheme").unlink()
        self.assertIn("canonical development environment scheme is missing: beta", self.module.collect_issues(self.root))

    def test_generated_matrix_rejects_prod_debug_and_promotable_development(self) -> None:
        path = self.app / IDENTITY
        original = path.read_text()
        for platform in ("ios", "android"):
            for mode in ("debug", "profile"):
                value = json.loads(original)
                value["identities"][platform][f"prod/{mode}"] = {"promotable": False}
                path.write_text(json.dumps(value))
                self.assertIn(f"generated {platform} identity must not expose Prod Debug/Profile", self.module.collect_issues(self.root))
                value = json.loads(original)
                value["identities"][platform][f"alpha/{mode}"]["promotable"] = True
                path.write_text(json.dumps(value))
                self.assertIn(f"generated {platform} development identity must be non-promotable: alpha/{mode}", self.module.collect_issues(self.root))
        path.write_text(original)

    def test_generated_matrix_mapping_and_required_inputs_fail_closed(self) -> None:
        path = self.app / IDENTITY
        original = path.read_text()
        for field, value, issue in (
            ("buildProfiles", ["nonprod"], "generated App identity buildProfile matrix is incomplete"),
            ("environmentProfiles", {}, "generated App identity environmentProfiles mapping is incomplete"),
            ("identities", {}, "generated android identity keys must match canonical release/development targets"),
        ):
            payload = json.loads(original)
            payload[field] = value
            path.write_text(json.dumps(payload))
            self.assertIn(issue, self.module.collect_issues(self.root))
        path.write_text("{")
        self.assertTrue(any("generated App identity document is invalid" in issue for issue in self.module.collect_issues(self.root)))
        path.write_text(original)
        for relative in (*SCANNED_RUNTIME_PATHS, "pubspec.yaml", IDENTITY):
            path = self.app / relative
            original = path.read_text()
            path.unlink()
            self.assertIn(f"required App identity input is missing: quwoquan_app/{relative}", self.module.collect_issues(self.root))
            path.write_text(original)

    def test_ios_configuration_resolver_cannot_be_bypassed(self) -> None:
        self._mutation("scripts/ios/build_prepare_dart_defines.sh", "identity = resolve_ios_configuration(sys.argv[1])", "identity = local_matrix[sys.argv[1]]", "iOS configuration must resolve canonical profile, environment and bundle identity")


if __name__ == "__main__":
    unittest.main()
