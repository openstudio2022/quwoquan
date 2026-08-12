"""Canonical App launcher content-mode contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
LAUNCHER = APP_DIR / "run.sh"


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
        (app / "ios/Pods").mkdir(parents=True)
        (app / "ios/Podfile.lock").write_text("locked\n", encoding="utf-8")
        (app / "ios/Pods/Manifest.lock").write_text(
            "locked\n", encoding="utf-8"
        )

        stackctl = root / "quwoquan_ops/cli/stackctl.py"
        stackctl.parent.mkdir(parents=True)
        stackctl.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import sys\n"
            f"preflight = {preflight!r}\n"
            f"delivery = {delivery!r}\n"
            "if 'app-debug-preflight' in sys.argv:\n"
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
        dev_up.write_text(
            "def find_device(*_args, **_kwargs):\n"
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
        return temporary, app, environment

    def test_launcher_has_explicit_content_live_default_and_ui_only_mode(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('RUN_MODE="content-live"', source)
        self.assertIn('--mode content-live|ui-only', source)
        self.assertIn('content-live|ui-only)', source)
        self.assertIn('export QWQ_APP_RUN_MODE="$RUN_MODE"', source)
        self.assertIn('"nonPromotable": run_mode == "ui-only"', source)

    def test_content_live_uses_formal_delivery_verification_before_flutter(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        app_preflight = source.index("app-debug-preflight")
        delivery = source.index('verify --env "$QWQ_APP_RUNTIME_ENV"')
        flutter_run = source.index("flutter run \\")
        self.assertLess(app_preflight, delivery)
        self.assertLess(delivery, flutter_run)
        self.assertIn('--kind content-delivery --profile integration', source)
        self.assertIn('payload.get("contentLive") != "passed"', source)
        self.assertIn('"reason": first_blocker', source)
        self.assertIn('"recoveryCommand": recovery_command', source)

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
        self.assertLess(strict_preflight, source.index("flutter pub get --offline"))
        self.assertLess(strict_preflight, source.index("find_device"))
        self.assertIn('PREFLIGHT_PURPOSE=content_live', source)
        self.assertIn('PREFLIGHT_PURPOSE=runtime', source)

    def test_content_live_transport_failures_are_hard_blockers(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")

        self.assertIn('content-live transport preparation failed', source)
        self.assertIn('content-live requires target-bound device trust', source)
        self.assertIn('content-live requires complete Android reverse ports', source)
        self.assertIn('content-live requires a runtime consumer lease', source)

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
            self.assertFalse((app.parent / "flutter.log").exists())

    def test_delivery_block_emits_one_formal_recovery_and_stops_flutter(self) -> None:
        digest = "sha256:" + "1" * 64
        temporary, app, environment = self._workspace(
            preflight={
                "purpose": "content_live",
                "status": "passed",
                "contentLive": "passed",
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
            blocker = json.loads(result.stderr.strip().splitlines()[-1])
            self.assertEqual(blocker["contentLive"], "gate_block")
            self.assertEqual(blocker["reason"], "release readiness is unreadable")
            self.assertEqual(
                blocker["recoveryCommand"],
                "python3 quwoquan_data/scripts/cli.py release supply-chain-drill "
                "--release-id research-alpha --env alpha --profile delivery",
            )
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
                "pub get --offline", (app.parent / "flutter.log").read_text()
            )

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
