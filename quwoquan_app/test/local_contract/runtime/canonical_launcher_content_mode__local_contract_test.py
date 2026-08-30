"""Canonical App launcher content-mode contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
LAUNCHER = APP_DIR / "run.sh"
PREFLIGHT_HANDOFF = (
    REPO_ROOT / "quwoquan_ops/cli/lib/app_debug_preflight_handoff.py"
)


class CanonicalLauncherContentModeContractTest(unittest.TestCase):
    def _workspace(
        self,
        *,
        preflight: dict[str, object],
        preflight_exit: int = 0,
        delivery: dict[str, object] | None = None,
        delivery_exit: int = 0,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, str]]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        app = root / "quwoquan_app"
        app.mkdir()
        (app / "run.sh").write_text(
            LAUNCHER.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (app / "run.sh").chmod(0o755)
        # launcher 首个工具调用前的参数预检复用 executor 的唯一 sanitizer 叶子模块，
        # stub 树直接复用生产文件，避免第二真相源。
        executor_dir = app / "scripts/device"
        (executor_dir / "canonical_app_instance").mkdir(parents=True)
        for relative in (
            "canonical_app_instance/__init__.py",
            "canonical_app_instance/arguments.py",
        ):
            (executor_dir / relative).write_text(
                (APP_DIR / "scripts/device" / relative).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (app / "ios/Pods").mkdir(parents=True)
        (app / "ios/Podfile.lock").write_text("locked\n", encoding="utf-8")
        (app / "ios/Pods/Manifest.lock").write_text(
            "locked\n", encoding="utf-8"
        )

        stackctl = root / "quwoquan_ops/cli/stackctl.py"
        stackctl.parent.mkdir(parents=True)
        preflight_log = root / "preflight_calls.log"
        stackctl.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import sys\n"
            "from pathlib import Path\n"
            f"preflight = {preflight!r}\n"
            f"delivery = {delivery!r}\n"
            "if 'app-debug-preflight' in sys.argv:\n"
            f"    with Path({str(preflight_log)!r}).open("
            "'a', encoding='utf-8') as handle:\n"
            "        handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "    print(json.dumps(preflight))\n"
            f"    raise SystemExit({preflight_exit})\n"
            "if 'verify' in sys.argv and 'content-delivery' in sys.argv:\n"
            "    print(json.dumps(delivery or {}))\n"
            f"    raise SystemExit({delivery_exit})\n"
            "raise SystemExit(93)\n",
            encoding="utf-8",
        )

        dev_up = root / "quwoquan_ops/cli/lib/dev_up.py"
        dev_up.parent.mkdir(parents=True)
        # preflight 的 purpose 映射与 receipt 复用判定只有一份实现，
        # stub 树直接复用生产文件，避免在测试里造第二真相源。
        (dev_up.parent / PREFLIGHT_HANDOFF.name).write_text(
            PREFLIGHT_HANDOFF.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        find_device_log = root / "find_device.log"
        dev_up.write_text(
            "from pathlib import Path\n"
            f"FIND_DEVICE_LOG = Path({str(find_device_log)!r})\n"
            "def find_device(*_args, **_kwargs):\n"
            "    FIND_DEVICE_LOG.write_text('called\\n', encoding='utf-8')\n"
            "    return None\n",
            encoding="utf-8",
        )
        bin_dir = root / "bin"
        bin_dir.mkdir()
        flutter_log = root / "flutter.log"
        flutter = bin_dir / "flutter"
        flutter.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> {flutter_log!s}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        flutter.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
        environment.pop("QWQ_ENVIRONMENT", None)
        # launcher 以包路径导入 `quwoquan_ops.cli.lib.dev_up`。宿主 PYTHONPATH 若指向
        # 真实仓库根，沙箱会命中生产模块而不是这里的替身，测试就不再观察 launcher 行为。
        environment.pop("PYTHONPATH", None)
        return temporary, app, environment

    def test_launcher_has_explicit_content_live_default_and_ui_only_mode(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('RUN_MODE="${QWQ_RUN_MODE:-content-live}"', source)
        self.assertIn('--mode content-live|ui-only', source)
        self.assertIn('content-live|ui-only)', source)
        self.assertIn('export QWQ_APP_RUN_MODE="$RUN_MODE"', source)
        self.assertIn('"nonPromotable": True', source)

    def test_projected_run_sh_skips_source_facade_when_resolving_real_flutter(
        self,
    ) -> None:
        payload = {
            "purpose": "runtime",
            "status": "passed",
            "contentLive": "not_evaluated",
            "nonPromotable": True,
            "firstBlocker": "",
            "warnings": [],
        }
        temporary, app, environment = self._workspace(preflight=payload)
        with temporary:
            root = Path(temporary.name)
            (root / ".git").mkdir()
            (app / ".flutter-version").write_text("3.47.0\n", encoding="utf-8")
            facade_source = APP_DIR / "scripts/tools/flutter_facade"
            facade_copy = app / "scripts/tools/flutter_facade"
            shutil.copytree(facade_source, facade_copy)

            real_flutter = root / "bin/flutter"
            real_flutter.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$*\" == \"--version --machine\" ]]; then\n"
                "  printf '%s' '{\"frameworkVersion\":\"3.47.0\","
                "\"frameworkRevision\":\"fixture-revision\"}'\n"
                "fi\n",
                encoding="utf-8",
            )
            real_flutter.chmod(0o755)

            projected_root = root / "projected"
            projected_app = projected_root / "quwoquan_app"
            projected_app.mkdir(parents=True)
            (projected_app / ".flutter-version").write_text(
                "3.47.0\n",
                encoding="utf-8",
            )
            shutil.copytree(
                facade_source,
                projected_app / "scripts/tools/flutter_facade",
            )
            projected_capture = root / "projected-real-flutter.txt"
            projected_launcher = projected_app / "run.sh"
            projected_launcher.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "PYTHONDONTWRITEBYTECODE=1 python3 "
                '"$(cd "$(dirname "$0")" && pwd)/scripts/tools/'
                'flutter_facade/resolve_real_flutter.py" '
                f"> {projected_capture!s}\n",
                encoding="utf-8",
            )
            projected_launcher.chmod(0o755)
            capsule_manifest = root / "source-capsule.json"
            capsule_manifest.write_text("{}\n", encoding="utf-8")
            projection_builder = (
                app / "scripts/device/prepare_workspace_launch_projection.py"
            )
            projection_builder.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                f"print(json.dumps({{"
                f"'projectionRoot': {str(projected_root)!r}, "
                f"'sourceCapsuleManifest': {str(capsule_manifest)!r}, "
                "'sourceRevision': 'fixture-revision', "
                "'sourceCapsuleDigest': 'sha256:' + '1' * 64}))\n",
                encoding="utf-8",
            )
            projection_builder.chmod(0o755)

            environment.pop("QWQ_REAL_FLUTTER", None)
            environment["PATH"] = os.pathsep.join(
                (
                    str(facade_copy / "bin"),
                    str(real_flutter.parent),
                    environment["PATH"],
                )
            )
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "ui-only", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                projected_capture.read_text(encoding="utf-8").strip(),
                str(real_flutter.resolve()),
            )

    def test_content_live_uses_formal_delivery_verification_before_flutter(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        app_preflight = source.index("app-debug-preflight")
        delivery = source.index('verify --env "$QWQ_APP_RUNTIME_ENV"')
        canonical_executor = source.index('scripts/device/run_app_instance.py"')
        self.assertLess(app_preflight, delivery)
        self.assertLess(delivery, canonical_executor)
        self.assertIn('--kind content-delivery --profile integration', source)
        self.assertIn('"reason": first_blocker', source)
        self.assertIn('"recoveryCommand": recovery_command', source)
        self.assertIn('record_prelaunch_warning "$CONTENT_DELIVERY_WARNING"', source)

    def test_target_is_canonical_and_ensure_runtime_only_delegates_dev_session(
        self,
    ) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('--target alpha-local|beta-local|gamma-local', source)
        self.assertIn('REQUESTED_TARGET="${1#*=}"', source)
        self.assertIn(
            '--ensure-runtime requires an explicit frozen candidate identity',
            source,
        )
        self.assertNotIn('dev-session --env "$QWQ_APP_RUNTIME_ENV"', source)
        self.assertNotIn('stackctl.py" up', source)
        self.assertNotIn('stackctl.py" repair', source)

    def test_strict_preflight_precedes_dependency_and_device_preparation(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        strict_preflight = source.index('app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"')
        self.assertLess(strict_preflight, source.index("prepare_flutter_dependencies.py"))
        self.assertLess(strict_preflight, source.index("find_device"))
        # purpose 映射不得在 launcher 内联复制，只能取自 canonical handoff 模块。
        self.assertNotIn("PREFLIGHT_PURPOSE=content_live", source)
        self.assertNotIn("PREFLIGHT_PURPOSE=runtime", source)
        self.assertIn("app_debug_preflight_purpose(sys.argv[1])", source)
        self.assertIn(
            'purpose = sys.argv[4]',
            source,
            "downstream purpose checks must consume the resolved purpose",
        )

    def test_launcher_reuses_upstream_preflight_receipt_without_rerunning(
        self,
    ) -> None:
        payload = {
            "purpose": "content_live",
            "status": "passed",
            "contentLive": "passed",
            "nonPromotable": True,
            "contentBindingState": "bound",
            "target": "alpha-local",
            "releaseId": "research-alpha",
            "manifestDigest": "sha256:" + "1" * 64,
            "readinessReceiptDigest": "sha256:" + "2" * 64,
            "contentBinding": {"verifyRunId": "verify-alpha"},
        }
        temporary, app, environment = self._workspace(preflight=payload)
        with temporary:
            root = Path(temporary.name)
            receipt = root / "upstream-preflight.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_ops.app_debug_preflight",
                        "purpose": "content_live",
                        "target": "alpha-local",
                        "payload": payload,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            environment["QWQ_APP_DEBUG_PREFLIGHT_RECEIPT"] = str(receipt)
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "content-live", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertIn("reusing upstream content_live preflight", result.stdout)
            self.assertFalse(
                (root / "preflight_calls.log").exists(),
                "launcher must not run a second preflight for the same attempt",
            )
            # 复用的回执必须继续驱动 content-live 判定，直到设备准备阶段才停。
            self.assertTrue((root / "find_device.log").exists())
            self.assertEqual(result.returncode, 2, result.stdout)

    def test_launcher_blocks_when_upstream_receipt_mismatches_the_attempt(
        self,
    ) -> None:
        temporary, app, environment = self._workspace(
            preflight={"purpose": "content_live", "status": "passed"},
        )
        with temporary:
            root = Path(temporary.name)
            receipt = root / "upstream-preflight.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_ops.app_debug_preflight",
                        "purpose": "runtime",
                        "target": "alpha-local",
                        "payload": {"purpose": "runtime", "status": "passed"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            environment["QWQ_APP_DEBUG_PREFLIGHT_RECEIPT"] = str(receipt)
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "content-live", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("APP.LAUNCH.preflight_receipt_invalid", result.stderr)
            self.assertFalse(
                (root / "preflight_calls.log").exists(),
                "a mismatched handoff must block instead of silently re-running",
            )

    def test_launcher_owns_preflight_when_no_upstream_receipt_is_handed_off(
        self,
    ) -> None:
        temporary, app, environment = self._workspace(
            preflight={
                "purpose": "runtime",
                "status": "passed",
                "contentLive": "not_requested",
                "nonPromotable": True,
                "target": "alpha-local",
            },
        )
        with temporary:
            root = Path(temporary.name)
            environment.pop("QWQ_APP_DEBUG_PREFLIGHT_RECEIPT", None)
            subprocess.run(
                ["bash", "run.sh", "--mode", "ui-only", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            calls = (root / "preflight_calls.log").read_text(encoding="utf-8")
            self.assertEqual(len(calls.strip().splitlines()), 1, calls)
            self.assertIn("--purpose runtime", calls)

    def test_content_live_transport_failures_are_test_live_warnings(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('Android transport preparation is unavailable', source)
        self.assertIn('target-bound transport trust is unavailable', source)
        self.assertIn('Android reverse ports are unavailable', source)
        self.assertIn('runtime consumer lease is unavailable', source)

    def test_content_live_preflight_block_stops_before_flutter(self) -> None:
        temporary, app, environment = self._workspace(
            preflight={
                "purpose": "content_live",
                "status": "gate_block",
                "contentLive": "gate_block",
                "firstBlocker": "release readiness evidence is missing",
                "recoveryCommand": "release supply-chain-drill --profile delivery",
            },
            preflight_exit=2,
        )
        with temporary:
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "content-live", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("release readiness evidence is missing", result.stderr)
            self.assertIn("supply-chain-drill", result.stderr)
            self.assertFalse((app.parent / "find_device.log").exists())
            self.assertFalse((app.parent / "flutter.log").exists())

    def test_passed_preflight_still_requires_a_connected_device(self) -> None:
        temporary, app, environment = self._workspace(
            preflight={
                "purpose": "content_live",
                "status": "passed",
                "contentLive": "passed",
                "nonPromotable": True,
                "contentBindingState": "bound",
                "releaseId": "research-alpha",
                "manifestDigest": "sha256:" + "1" * 64,
                "readinessReceiptDigest": "sha256:" + "2" * 64,
                "contentBinding": {"verifyRunId": "verify-alpha"},
            },
        )
        with temporary:
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "content-live", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn(
                "connected iOS/Android device is required after runtime preflight",
                result.stderr,
            )
            self.assertEqual(
                (app.parent / "find_device.log").read_text(encoding="utf-8"),
                "called\n",
            )
            self.assertFalse((app.parent / "flutter.log").exists())

    def test_delivery_block_emits_one_warning_and_continues_to_device(self) -> None:
        digest = "sha256:" + "1" * 64
        temporary, app, environment = self._workspace(
            preflight={
                "purpose": "content_live",
                "status": "passed",
                "contentLive": "passed",
                "nonPromotable": True,
                "contentBindingState": "bound",
                "releaseId": "research-alpha",
                "manifestDigest": digest,
                "readinessReceiptDigest": "sha256:" + "2" * 64,
                "contentBinding": {"verifyRunId": "verify-alpha"},
            },
            delivery={
                "exitCode": 1,
                "details": ["release readiness is unreadable"],
            },
            delivery_exit=1,
        )
        with temporary:
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "content-live", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('"contentLive": "warning"', result.stderr)
            self.assertIn('"reason": "release readiness is unreadable"', result.stderr)
            self.assertIn(
                "release supply-chain-drill --release-id research-alpha "
                "--env alpha --profile delivery",
                result.stderr,
            )
            self.assertTrue((app.parent / "find_device.log").exists())
            self.assertFalse((app.parent / "flutter.log").exists())

    def test_ui_only_requires_non_promotable_runtime_preflight(self) -> None:
        temporary, app, environment = self._workspace(
            preflight={
                "purpose": "runtime",
                "status": "warning",
                "contentLive": "not_requested",
                "nonPromotable": True,
                "warnings": ["content is unbound"],
            },
        )
        with temporary:
            result = subprocess.run(
                ["bash", "run.sh", "--mode", "ui-only", "-d", "device"],
                cwd=app,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("content is unbound", result.stderr)
            self.assertIn(
                "connected iOS/Android device is required after runtime preflight",
                result.stderr,
            )
            self.assertEqual(
                (app.parent / "find_device.log").read_text(encoding="utf-8"),
                "called\n",
            )
            self.assertFalse((app.parent / "flutter.log").exists())

    def test_launcher_remains_valid_bash(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(LAUNCHER)],
            cwd=APP_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
