# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t4
#
# integrate Alpha 准入的 App 启动 + 首页/视频书 readback：启动观察只以 launched +
# router_shell + configurationState=complete 为终态；readback 只接受 200 且集合非空；
# 任一失败都是 typed blocker，不得降级为 PASS。

from __future__ import annotations

import inspect
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

        request_signature = inspect.signature(launch._default_http_request)

        def fake_request(**kwargs):
            request_signature.bind(**kwargs)
            query = kwargs["query"]
            identity = {"releaseId": "release-test", "manifestDigest": "sha256:" + "a" * 64}
            if query.get("channelId") == "premium":
                return Observation(200, {**identity, "outcome": "empty", "emptyReason": "no_eligible_content", "items": []})
            return Observation(200, {**identity, "outcome": "content", "items": [{"postId": "post-test"}]})

        with (
            mock.patch.object(launch, "_topology_api_base", return_value="https://api.alpha.test"),
            mock.patch.object(launch, "_tls_ca_file", return_value=Path("/dev/null")),
            mock.patch.object(launch, "_default_http_request", side_effect=fake_request),
        ):
            result = launch.content_readback(target="alpha-local", expected_release={"releaseId": "release-test", "releaseDigest": "sha256:" + "a" * 64})
        self.assertFalse(result["passed"])
        self.assertEqual(result["failures"], ["video-book: items is empty"])
        self.assertEqual(result["results"]["home-feed"]["itemCount"], 1)
        # 读回真实页面的推荐与精品频道；普通视频浏览保留为独立检查。
        self.assertEqual(launch.CONTENT_READBACK_QUERIES[0][1]["channelId"], "recommend")
        self.assertEqual(launch.CONTENT_READBACK_QUERIES[0][2], "items")
        self.assertEqual(launch.CONTENT_READBACK_QUERIES[1][1]["channelId"], "premium")
        self.assertEqual(launch.CONTENT_READBACK_QUERIES[2][1]["type"], "video")

    def _readback_payloads(self, payloads):
        observations = [mock.Mock(
            status=200, payload=payload, path="/content/feed",
            request_id="r", trace_id="t", duration_ms=1,
        ) for payload in payloads]
        with (
            mock.patch.object(launch, "_topology_api_base", return_value="https://api.alpha.test"),
            mock.patch.object(launch, "_tls_ca_file", return_value=Path("/dev/null")),
            mock.patch.object(launch, "_default_http_request", side_effect=observations),
        ):
            return launch.content_readback(target="alpha-local", expected_release={"releaseId": "release-test", "releaseDigest": "sha256:" + "a" * 64})

    @staticmethod
    def _content_page(**overrides):
        return {
            "outcome": "content", "items": [{"postId": "post-test"}],
            "releaseId": "release-test", "manifestDigest": "sha256:" + "a" * 64,
            **overrides,
        }

    def test_object_cards_cannot_substitute_home_posts(self) -> None:
        result = self._readback_payloads([
            self._content_page(items=[], objectCards=[{"id": "card"}]),
            self._content_page(), self._content_page(),
        ])
        self.assertFalse(result["passed"])
        self.assertIn("home-feed: items is empty", result["failures"])

    def test_all_queries_must_read_the_same_release(self) -> None:
        for field, value in (("releaseId", "another-release"), ("manifestDigest", "sha256:" + "b" * 64)):
            with self.subTest(field=field):
                result = self._readback_payloads([
                    self._content_page(), self._content_page(**{field: value}), self._content_page(),
                ])
                self.assertFalse(result["passed"])
                self.assertIn("video-book: content identity differs from expected candidate release", result["failures"])

    def test_consistent_but_wrong_candidate_release_is_rejected(self) -> None:
        for field, value in (("releaseId", "old-release"), ("manifestDigest", "sha256:" + "b" * 64)):
            result = self._readback_payloads([self._content_page(**{field: value})] * 3)
            self.assertFalse(result["passed"])
            self.assertEqual(len(result["failures"]), 3)
            self.assertIn("expected candidate release", result["failures"][0])

    def test_nonempty_invalid_envelopes_are_not_ready(self) -> None:
        for overrides in (
            {"outcome": "empty"}, {"emptyReason": "no_eligible_content"},
            {"releaseId": ""}, {"manifestDigest": "not-a-digest"},
            {"items": [None]}, {"items": [{"postId": ""}]},
            {"items": [{"postId": "same"}, {"postId": "same"}]},
        ):
            with self.subTest(overrides=overrides):
                result = self._readback_payloads([
                    self._content_page(**overrides), self._content_page(), self._content_page(),
                ])
                self.assertFalse(result["passed"])

    def test_valid_release_bound_queries_report_sample_counts(self) -> None:
        result = self._readback_payloads([self._content_page()] * 3)
        self.assertTrue(result["passed"])
        self.assertEqual(result["results"]["video-book"]["releaseId"], "release-test")
        self.assertEqual(result["countScope"], "observed-pages")
        self.assertFalse(result["traversalComplete"])

    def test_missing_simulator_is_a_typed_blocker(self) -> None:
        with mock.patch.object(launch.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout='{"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-26-0": []}}', stderr="")
            with mock.patch.object(launch.sys, "platform", "darwin"):
                with self.assertRaises(launch.IntegrationAppLaunchError) as blocked:
                    launch.select_ios_simulator()
        self.assertEqual(blocked.exception.code, launch.DEVICE_BLOCKER)

    def test_offline_artifact_includes_identity_only_in_nonprod(self) -> None:
        import yaml
        from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import _verify_snapshot_assets

        app = ROOT / "quwoquan_app"
        declarations = yaml.safe_load((app / "pubspec.yaml").read_text())["flutter"]["assets"]
        expected = ("assets/content/alpha/manifest.json", "assets/content/alpha/bundle_identity.json")
        for name in expected:
            self.assertEqual([row for row in declarations if isinstance(row, dict) and row.get("path") == name],
                             [{"path": name, "flavors": ["nonprod"]}])
        source = app / expected[0]
        reads = []
        def read_asset(name):
            reads.append(name)
            return (app / name).read_bytes()
        _verify_snapshot_assets(read_asset, source=source, raw=source.read_bytes(), manifest={"media": []})
        self.assertEqual(reads, list(expected))

    def test_offline_raw_cannot_replace_native_screenshot_or_page_identity(self) -> None:
        import json
        from quwoquan_ops.tests.local_contract.ci.test_integration_app_offline_uat__local_contract_test import (
            _CANDIDATE, _receipt_matrix,
        )

        for damage in ("screenshot", "route", "carrier"):
            with self.subTest(damage=damage):
                root = self.root / damage
                receipts, write = _receipt_matrix(root)
                receipt = json.loads((root / receipts["android"]["ref"]).read_bytes())
                page = receipt["pageResultRefs"][0]
                if damage == "screenshot":
                    execution = json.loads((root / page["evidence"]["ref"]).read_bytes())
                    screenshot = root / execution["screenshot"]["ref"]
                    execution["screenshot"] = write(execution["screenshot"]["ref"], screenshot.read_bytes() + b"changed")
                    write(page["evidence"]["ref"], execution)
                    expected = "screenshot differs from native"
                else:
                    raw = json.loads((root / page["result"]["ref"]).read_bytes())
                    if damage == "route":
                        raw["target"]["id"] = "/another-page"
                    else:
                        raw["carrier"] = "video"
                    write(page["result"]["ref"], raw)
                    expected = "plan/launch candidate identity drifted"
                # 此单元边界隔离 exact-byte reader，直接证明原生观察/页面身份不能互换。
                def read(exact, *, binary=False):
                    raw = (root / exact["ref"]).read_bytes()
                    return raw if binary else json.loads(raw)
                binding = read(receipt["targetUatBindingRefs"]["alpha-local"])
                with self.assertRaisesRegex(ValueError, expected):
                    launch._offline_execution(read=read, page=page, result=read(page["result"]),
                                              receipt=receipt, binding=binding, candidate=_CANDIDATE)

    def test_integration_run_wires_alpha_app_launch_for_app_scope(self) -> None:
        source = Path(integration_run.__file__).read_text(encoding="utf-8")
        self.assertIn('if environment == "alpha" and "app" in scopes:', source)
        self.assertIn('phases.run("alpha.offline-pages"', source)
        self.assertNotIn("_alpha_app_launch_cases", source)
        self.assertIn('phases.run(f"{environment}.content-readback"', source)
        self.assertIn("cases.extend(app_cases)", source)
        self.assertIn('scopes=tuple(str(scope) for scope in plan["scopes"])', source)
        # health 之后、verify 之前：runtime 仍在线且尚未 down。
        self.assertLess(source.index('phases.run(f"{environment}.health"'), source.index('phases.run(f"{environment}.content-readback"'))
        self.assertLess(source.index('phases.run(f"{environment}.content-readback"'), source.index('phases.run(f"{environment}.verify"'))
        for code in ("INTEGRATION_RUN.APP_LAUNCH_FAILED", "INTEGRATION_RUN.CONTENT_READBACK_FAILED"):
            self.assertIn(code, source)


if __name__ == "__main__":
    unittest.main()
