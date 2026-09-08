# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004
#
# integrate Alpha 准入的 App 启动 + 首页/视频书 readback：启动观察只以 launched +
# router_shell + configurationState=complete 为终态；readback 只接受 200 且集合非空；
# 任一失败都是 typed blocker，不得降级为 PASS。

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import integration_run  # noqa: E402
from quwoquan_ops.cli.lib import integration_app_launch as launch  # noqa: E402


def _fake_launcher(root: Path, body: str) -> Path:
    app = root / "quwoquan_app"
    app.mkdir(parents=True, exist_ok=True)
    run_sh = app / "run.sh"
    run_sh.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    run_sh.chmod(run_sh.stat().st_mode | stat.S_IXUSR)
    return run_sh


class IntegrationAppLaunchContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="qwq-app-launch-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.device = launch.SimulatorDevice(udid="SIM-1", name="iPhone Fixture", state="Booted")

    def test_launch_passes_only_after_launched_router_shell_and_complete(self) -> None:
        _fake_launcher(self.root, (
            "echo 'QWQ_APP_LAUNCH_PHASE status=compiled'\n"
            "echo 'QWQ_APP_LAUNCH_PHASE status=launched'\n"
            "echo 'QWQStartup ios_dart_startup_attempt configurationState=complete'\n"
            "echo 'QWQStartup ios_startup_safe_terminal surface=router_shell reportedElapsedMs=1'\n"
            "sleep 30\n"
        ))
        observation = launch.launch_and_observe(
            repo_root=self.root, device=self.device, log_dir=self.root / "logs",
            timeout_seconds=20, settle_seconds=0,
        )
        self.assertTrue(observation.passed)
        self.assertEqual(observation.phases, ["compiled", "launched"])
        self.assertTrue((self.root / "logs/app-launch-alpha.log").is_file())
        # 观察到终态后必须结束 launcher 会话，不能让 attach 前台挂满 timeout。
        self.assertIsNotNone(observation.exit_code)

    def test_launch_without_router_shell_is_a_typed_blocker(self) -> None:
        _fake_launcher(self.root, (
            "echo 'QWQ_APP_LAUNCH_PHASE status=launched'\n"
            "echo 'QWQStartup ios_startup_safe_terminal surface=safe_recovery'\n"
            "exit 0\n"
        ))
        observation = launch.launch_and_observe(
            repo_root=self.root, device=self.device, log_dir=self.root / "logs",
            timeout_seconds=20, settle_seconds=0,
        )
        self.assertFalse(observation.passed)
        self.assertIn(launch.LAUNCH_BLOCKER, observation.first_blocker)

    def test_gate_block_line_is_kept_as_first_blocker(self) -> None:
        _fake_launcher(self.root, (
            "echo '[canonical-executor] GATE_BLOCK: APP.DEPENDENCY.cocoapods_mixed: fixture'\n"
            "exit 2\n"
        ))
        observation = launch.launch_and_observe(
            repo_root=self.root, device=self.device, log_dir=self.root / "logs",
            timeout_seconds=20, settle_seconds=0,
        )
        self.assertFalse(observation.passed)
        self.assertIn("APP.DEPENDENCY.cocoapods_mixed", observation.first_blocker)

    def test_content_readback_requires_200_and_non_empty_collections(self) -> None:
        class Observation:
            def __init__(self, status, payload):
                self.status = status
                self.payload = payload
                self.path = "/content/feed"
                self.request_id = "r"
                self.trace_id = "t"
                self.duration_ms = 1

        def fake_request(**kwargs):
            query = kwargs["query"]
            if query.get("type") == "video":
                return Observation(200, {"items": []})
            return Observation(200, {"objectCards": [{"id": "x"}]})

        with (
            mock.patch.object(launch, "_topology_api_base", return_value="https://api.alpha.test"),
            mock.patch.object(launch, "_tls_ca_file", return_value=Path("/dev/null")),
            mock.patch.object(launch, "_default_http_request", side_effect=fake_request),
        ):
            result = launch.content_readback(target="alpha-local")
        self.assertFalse(result["passed"])
        self.assertEqual(result["failures"], ["video-book: items is empty"])
        self.assertEqual(result["results"]["home-feed"]["itemCount"], 1)
        # 查询形状与 content-api-consumer 同源：首页推荐 feed 与视频 works。
        self.assertEqual(launch.CONTENT_READBACK_QUERIES[0][1]["channelId"], "recommend")
        self.assertEqual(launch.CONTENT_READBACK_QUERIES[1][1]["type"], "video")

    def test_missing_simulator_is_a_typed_blocker(self) -> None:
        with mock.patch.object(launch.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout='{"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-26-0": []}}', stderr="")
            with mock.patch.object(launch.sys, "platform", "darwin"):
                with self.assertRaises(launch.IntegrationAppLaunchError) as blocked:
                    launch.select_ios_simulator()
        self.assertEqual(blocked.exception.code, launch.DEVICE_BLOCKER)

    def test_integration_run_wires_alpha_app_launch_for_app_scope(self) -> None:
        source = Path(integration_run.__file__).read_text(encoding="utf-8")
        self.assertIn('if environment == "alpha" and "app" in scopes:', source)
        self.assertIn('phases.run(f"{environment}.app-launch"', source)
        self.assertIn("cases.extend(app_cases)", source)
        self.assertIn('scopes=tuple(str(scope) for scope in plan["scopes"])', source)
        # health 之后、verify 之前：runtime 仍在线且尚未 down。
        self.assertLess(source.index('phases.run(f"{environment}.health"'), source.index('phases.run(f"{environment}.app-launch"'))
        self.assertLess(source.index('phases.run(f"{environment}.app-launch"'), source.index('phases.run(f"{environment}.verify"'))
        for code in ("INTEGRATION_RUN.APP_LAUNCH_FAILED", "INTEGRATION_RUN.CONTENT_READBACK_FAILED"):
            self.assertIn(code, source)


if __name__ == "__main__":
    unittest.main()
