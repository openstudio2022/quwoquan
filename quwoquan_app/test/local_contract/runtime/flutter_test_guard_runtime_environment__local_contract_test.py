"""Flutter local_contract runner must consume the selected stackctl environment.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_app.scripts.device.verify_flutter_run_defines import (
    RUNTIME_VALUE_DEFINE_KEYS,
)

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "env"
    / "run_flutter_test_guarded.py"
)


def _load_subject():
    spec = importlib.util.spec_from_file_location("run_flutter_test_guarded", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_values() -> dict[str, str]:
    """按 canonical 键映射派生取值替身，测试不自持第二份键集合。"""
    values = {key: f"https://{key.lower()}.example" for key in RUNTIME_VALUE_DEFINE_KEYS}
    values["appRuntimeEnv"] = "beta"
    values["gatewayBaseUrl"] = "https://gateway.example"
    return values


_RUNTIME_VALUES = _runtime_values()


class FlutterDiagnosticArchiveContractTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
    def test_exact_diagnostic_bytes_are_archived_before_source_removal(self):
        import hashlib
        import json
        import subprocess
        from quwoquan_ops.cli.lib import output_paths
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            relative = "quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/app_page_error_state_light_testImage.png"
            source = root / relative
            source.parent.mkdir(parents=True)
            raw = b"\x89PNG\r\n\x1a\narchive-test-bytes"
            source.write_bytes(raw)
            archive = root / ".qwq_output/env/repo/runs/archive"
            with mock.patch.object(subject, "REPOSITORY_ROOT", root), mock.patch.object(
                output_paths, "repo_run_dir", return_value=archive
            ), mock.patch.object(subject.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 1, "", ""),
            ]), mock.patch.object(subject.subprocess, "check_output", return_value="a" * 40):
                result = subject._archive_failure_diagnostics([relative], provenance="historical test run; exact invocation unknown")
            self.assertEqual(result, archive)
            self.assertEqual((archive / source.name).read_bytes(), raw)
            self.assertFalse(source.exists())
            receipt = json.loads((archive / "result.json").read_bytes())
            self.assertEqual(receipt["files"][0]["sha256"], "sha256:" + hashlib.sha256(raw).hexdigest())
            self.assertTrue((archive / "archive-plan.json").is_file())

    def test_unknown_path_and_symlink_are_not_archived(self):
        subject = _load_subject()
        with self.assertRaisesRegex(ValueError, "SCOPE_INVALID"):
            subject._archive_failure_diagnostics(["quwoquan_app/lib/main.dart"], provenance="not diagnostic")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            relative = "quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/app_page_error_state_dark_testImage.png"
            source = root / relative
            source.parent.mkdir(parents=True)
            original = root / "original.png"
            original.write_bytes(b"\x89PNG\r\n\x1a\nkept")
            source.symlink_to(original)
            with mock.patch.object(subject, "REPOSITORY_ROOT", root):
                with self.assertRaisesRegex(ValueError, "SYMLINK"):
                    subject._archive_failure_diagnostics([relative], provenance="test")
            self.assertTrue(original.exists())
            self.assertTrue(source.is_symlink())

    def test_busy_or_tracked_diagnostics_remain_untouched(self):
        import subprocess
        from quwoquan_ops.cli.lib import output_paths
        subject = _load_subject()
        for tracked in (True, False):
            with self.subTest(tracked=tracked), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                relative = "quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/app_page_error_state_dark_testImage.png"
                source = root / relative
                source.parent.mkdir(parents=True)
                source.write_bytes(b"\x89PNG\r\n\x1a\nkept")
                with mock.patch.object(subject, "REPOSITORY_ROOT", root), mock.patch.object(
                    output_paths, "repo_run_dir"
                ) as allocate, mock.patch.object(subject.subprocess, "run", side_effect=[
                    subprocess.CompletedProcess([], 0, relative if tracked else "", ""),
                    subprocess.CompletedProcess([], 0, "123\n", ""),
                ]):
                    with self.assertRaisesRegex(ValueError, "TRACKED_SOURCE|IN_USE_OR_UNKNOWN"):
                        subject._archive_failure_diagnostics([relative], provenance="test")
                    allocate.assert_not_called()
                self.assertTrue(source.exists())


class FlutterTestGuardRuntimeEnvironmentContractTest(unittest.TestCase):
    def test_default_host_tests_use_remote_beta_not_offline_alpha(self) -> None:
        subject = _load_subject()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            subject, "test_live_runtime_values", return_value=_RUNTIME_VALUES
        ) as resolve:
            args = subject._with_runtime_environment_defines([])
        self.assertEqual(resolve.call_args.args, ("beta", "beta-local"))
        self.assertIn("--dart-define=APP_RUNTIME_ENV=beta", args)

    def test_stackctl_environment_selects_the_packaged_runtime(self) -> None:
        subject = _load_subject()
        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_RUNTIME_ENV": "beta", "QWQ_DEPLOY_TARGET": "beta-local"},
            clear=False,
        ), mock.patch.object(
            subject, "test_live_runtime_values", return_value=_RUNTIME_VALUES
        ) as resolve:
            args = subject._with_runtime_environment_defines([])

        # 取值与 App 同源：runner 直接向 test_live 取值面要该环境的 endpoint，
        # 不再经由第二个 CLI 进程转译。
        self.assertEqual(resolve.call_args.args, ("beta", "beta-local"))
        self.assertIn("--dart-define=APP_RUNTIME_ENV=beta", args)
        self.assertIn(
            "--dart-define=CLOUD_GATEWAY_BASE_URL=https://gateway.example",
            args,
        )

    def test_explicit_dart_define_overrides_the_process_environment(self) -> None:
        subject = _load_subject()
        overridden = {**_RUNTIME_VALUES, "appRuntimeEnv": "gamma"}
        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_RUNTIME_ENV": "beta", "QWQ_DEPLOY_TARGET": "gamma-local"},
            clear=False,
        ), mock.patch.object(
            subject, "test_live_runtime_values", return_value=overridden
        ) as resolve:
            args = subject._with_runtime_environment_defines(
                ["--dart-define=APP_RUNTIME_ENV=gamma"]
            )

        self.assertEqual(resolve.call_args.args, ("gamma", "gamma-local"))
        self.assertEqual(args.count("--dart-define=APP_RUNTIME_ENV=gamma"), 1)

    def test_serial_mode_only_runs_files_that_declare_the_serial_tag(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary)
            test_root = app_root / "test/local_contract"
            test_root.mkdir(parents=True)
            (test_root / "file_serial__local_contract_test.dart").write_text(
                "@Tags(<String>['serial', 'visual'])\nvoid main() {}\n",
                encoding="utf-8",
            )
            (test_root / "inline_serial__local_contract_test.dart").write_text(
                "void main() { test('x', () {}, tags: <String>['serial']); }\n",
                encoding="utf-8",
            )
            (test_root / "multiline_annotation__local_contract_test.dart").write_text(
                "@Tags(<String>[\n  'serial',\n  'visual',\n])\nvoid main() {}\n",
                encoding="utf-8",
            )
            (test_root / "multiline_inline__local_contract_test.dart").write_text(
                "void main() {\n  test(\n    'x',\n    () {},\n    tags: <String>[\n      'serial',\n    ],\n  );\n}\n",
                encoding="utf-8",
            )
            (test_root / "ordinary__local_contract_test.dart").write_text(
                "void main() { final serialized = true; }\n",
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {"FLUTTER_TEST_SERIAL_MODE": "only"},
                clear=False,
            ), mock.patch.object(subject, "APP_ROOT", app_root):
                args = subject._with_serial_target_selection(
                    ["test/local_contract/", "-r", "compact"]
                )

        self.assertEqual(
            args,
            [
                "test/local_contract/file_serial__local_contract_test.dart",
                "test/local_contract/inline_serial__local_contract_test.dart",
                "test/local_contract/multiline_annotation__local_contract_test.dart",
                "test/local_contract/multiline_inline__local_contract_test.dart",
                "-r",
                "compact",
            ],
        )

    def test_serial_directory_selection_fails_closed_when_no_tagged_file_exists(
        self,
    ) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary)
            test_root = app_root / "test/local_contract"
            test_root.mkdir(parents=True)
            (test_root / "ordinary__local_contract_test.dart").write_text(
                "void main() {}\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"FLUTTER_TEST_SERIAL_MODE": "only"},
                clear=False,
            ), mock.patch.object(subject, "APP_ROOT", app_root):
                with self.assertRaisesRegex(RuntimeError, "no tagged test files"):
                    subject._with_serial_target_selection(["test/local_contract/"])

    def test_same_file_serial_tag_alias_fails_closed(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary)
            test_root = app_root / "test/local_contract"
            test_root.mkdir(parents=True)
            (test_root / "alias__local_contract_test.dart").write_text(
                "const serialTags = <String>['serial'];\n"
                "void main() { test('x', () {}, tags: serialTags); }\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"FLUTTER_TEST_SERIAL_MODE": "only"},
                clear=False,
            ), mock.patch.object(subject, "APP_ROOT", app_root):
                with self.assertRaisesRegex(RuntimeError, "not auditable"):
                    subject._with_serial_target_selection(["test/local_contract/"])

    def test_imported_serial_tag_alias_fails_closed(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary)
            test_root = app_root / "test/local_contract"
            test_root.mkdir(parents=True)
            (test_root / "alias__local_contract_test.dart").write_text(
                "void main() { test('x', () {}, tags: serialTags); }\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"FLUTTER_TEST_SERIAL_MODE": "only"},
                clear=False,
            ), mock.patch.object(subject, "APP_ROOT", app_root):
                with self.assertRaisesRegex(RuntimeError, "not auditable"):
                    subject._with_serial_target_selection(["test/local_contract/"])

    def test_raw_strings_inside_callback_do_not_hide_a_literal_serial_tag(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            test_file = Path(temporary) / "raw_string_test.dart"
            test_file.write_text(
                "void main() {\n"
                "  test('x', () {\n"
                "    final windowsPath = r'\\';\n"
                "    final multilineSingle = r'''\\''';\n"
                '    final multilineDouble = r"""\\""";\n'
                "    final codeLike = r'''test('nested', () {}, "
                "tags: tagRefs); @Tags(tagRefs)''';\n"
                "    // test('comment', () {}, tags: tagRefs);\n"
                "    // @Tags(tagRefs)\n"
                "  }, tags: <String>['serial']);\n"
                "}\n",
                encoding="utf-8",
            )

            self.assertTrue(subject.declares_serial_tests(test_file))

    def test_business_tags_argument_inside_callback_is_not_a_test_tag(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            test_file = Path(temporary) / "business_tags_test.dart"
            test_file.write_text(
                "void main() {\n"
                "  test('x', () {\n"
                "    final event = BehaviorEvent(tags: tagRefs);\n"
                "  });\n"
                "}\n",
                encoding="utf-8",
            )

            self.assertFalse(subject.declares_serial_tests(test_file))

    def test_generic_imported_test_tag_alias_fails_closed(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            test_file = Path(temporary) / "generic_alias_test.dart"
            test_file.write_text(
                "void main() { test('x', () {}, tags: tagRefs); }\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "not auditable"):
                subject.declares_serial_tests(test_file)

    def test_spread_test_tag_alias_fails_closed(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            test_file = Path(temporary) / "spread_alias_test.dart"
            test_file.write_text(
                "void main() {\n"
                "  test('x', () {}, tags: <String>['serial', ...tagRefs]);\n"
                "}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "literal values"):
                subject.declares_serial_tests(test_file)

    def test_default_policy_allows_only_one_classified_fresh_retry(self) -> None:
        subject = _load_subject()
        self.assertEqual(subject.DEFAULT_MAX_ATTEMPTS, 2)
        with mock.patch.object(
            subject,
            "_stream_command",
            side_effect=[
                (1, "Connection closed while receiving data", False),
                (1, "Connection closed while receiving data", False),
                (0, "", False),
            ],
        ) as run, mock.patch.object(subject.time, "sleep"):
            exit_code = subject._run_flutter_test_with_retries(["flutter", "test"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(run.call_count, 2)

    def test_deterministic_flutter_failure_is_never_retried(self) -> None:
        subject = _load_subject()
        with mock.patch.object(
            subject, "_stream_command", return_value=(1, "Expected true, got false", False)
        ) as run:
            exit_code = subject._run_flutter_test_with_retries(["flutter", "test"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(run.call_count, 1)

    def test_coverage_retry_removes_the_previous_attempt_artifact(self) -> None:
        subject = _load_subject()
        with tempfile.TemporaryDirectory() as temporary:
            coverage_path = Path(temporary) / "coverage.lcov.info"
            observations: list[bool] = []

            def fake_stream(*_args, **_kwargs):
                observations.append(coverage_path.exists())
                if len(observations) == 1:
                    coverage_path.write_text("partial", encoding="utf-8")
                    return 1, "Connection closed while receiving data", False
                coverage_path.write_text("final", encoding="utf-8")
                return 0, "", False

            with mock.patch.object(
                subject, "_stream_command", side_effect=fake_stream
            ), mock.patch.object(subject.time, "sleep"):
                exit_code = subject._run_flutter_test_with_retries(
                    ["flutter", "test", f"--coverage-path={coverage_path}"],
                    cwd=Path(temporary),
                    max_attempts=2,
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(observations, [False, False])
            self.assertEqual(coverage_path.read_text(encoding="utf-8"), "final")


if __name__ == "__main__":
    unittest.main()
