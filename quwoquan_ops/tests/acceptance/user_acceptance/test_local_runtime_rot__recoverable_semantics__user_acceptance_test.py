# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t5
# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/local-runtime-rot-notification/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/local-runtime-rot-notification/spec.md#gwt-001.t4
"""场景：本地运行时腐烂时，工程角色收到的是可恢复语义而非终局失败。

「无法访问服务」之所以难处理，不是因为它没被报出来，而是因为报出来的东西
不能行动：没有实测值、没有阈值、没有下一步命令。本测试站在使用者一侧，
要求每一次阻断都同时给出「测到了什么」「要求是什么」「下一步敲什么」，
并且那条下一步必须是真能执行的 stackctl 命令，而不是一句安慰。
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.local_runtime_capacity import (
    CAPACITY_BLOCKER,
    CONTAINER_STORE_SCOPE,
    load_capacity_policy,
    probe_container_store_capacity,
)
from quwoquan_ops.cli.lib.app_launch_attempt import LAUNCH_BLOCKERS
from quwoquan_ops.cli.lib.runtime_container_liveness import RUNTIME_DEPENDENCY_BLOCKER


def _df_runner(available_kib: int):
    def runner(argv, *, timeout_seconds=None, **_kwargs):
        joined = " ".join(argv)
        if "system df" in joined:
            return subprocess.CompletedProcess(
                argv,
                0,
                '{"Type":"Build Cache","Size":"26GB","Reclaimable":"26GB (100%)"}',
                "",
            )
        if "image inspect" in joined:
            return subprocess.CompletedProcess(argv, 0, "sha256:probe", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
            f"overlay 100476656 1 {available_kib} 99% /",
            "",
        )

    return runner


class LocalRuntimeRotRecoverableSemanticsTest(unittest.TestCase):
    def test_capacity_shortfall_reads_as_an_actionable_next_step(self) -> None:
        policy = load_capacity_policy()
        probe = probe_container_store_capacity(policy, runner=_df_runner(1024 * 1024))
        message = probe.describe()

        self.assertFalse(probe.satisfied)
        self.assertIn(CAPACITY_BLOCKER, message)
        # 实测值、阈值、可回收量、下一步命令：四者缺一就不可行动。
        self.assertIn("free=1.00GiB", message)
        self.assertIn(
            f"required={policy.threshold_for(CONTAINER_STORE_SCOPE) / 2**30:.2f}GiB",
            message,
        )
        self.assertIn("reclaimable=", message)
        self.assertIn(policy.reclaim_command_for(CONTAINER_STORE_SCOPE), message)

    def test_declared_reclaim_commands_are_really_executable(self) -> None:
        """给出的下一步必须是 stackctl 真能接受的命令，而不是一句安慰。"""
        policy = load_capacity_policy()
        parser = stackctl.build_parser()
        for scope in ("host", "containerStore"):
            command = str(policy.reclaim_commands.get(scope) or "")
            with self.subTest(scope=scope):
                self.assertTrue(command, f"{scope} 必须声明回收命令")
                tokens = shlex.split(command)
                self.assertEqual(tokens[:2], ["python3", "quwoquan_ops/cli/stackctl.py"])
                self.assertTrue(
                    (stackctl.ROOT / tokens[1]).is_file(),
                    f"{tokens[1]} 必须存在，否则建议无法执行",
                )
                parsed = parser.parse_args(tokens[2:])
                self.assertEqual(parsed.command, "repair")

    def test_dependency_loss_is_reported_as_recoverable_not_as_launch_failure(
        self,
    ) -> None:
        startup = {
            "status": "running",
            "environment": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "attemptId": "attempt-alpha-recoverable",
            "composeProject": "quwoquan_alpha_test_live_1",
            "configurationDigest": "sha256:" + "1" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
        }
        dead = subprocess.CompletedProcess(
            ["docker", "ps"],
            0,
            '{"Names":"mongo","Service":"mongodb","State":"exited",'
            '"Status":"Exited (133) 3 hours ago"}',
            "",
        )
        with tempfile.TemporaryDirectory() as temp:
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": "alpha",
                        "backend": "local",
                        "portProfile": "alpha",
                        "publicBases": {"api": "https://api.alpha.quwoquan.com:17000"},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "compile_provider_runtime_composition",
                    return_value={
                        "runtimeCompositionDigest": "sha256:" + "3" * 64,
                        "workloads": [],
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=startup,
                ),
                mock.patch.object(
                    stackctl,
                    "load_test_live_content_binding",
                    return_value={"releaseId": "release-a"},
                ),
                mock.patch.object(
                    stackctl,
                    "verify_certificate",
                    return_value={"profile": "local-managed", "status": "ready"},
                ),
                mock.patch.object(stackctl, "load_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "profile_ports",
                    return_value={"user-service": 17001, "integration-service": 17002},
                ),
                mock.patch.object(
                    stackctl,
                    "fetch_url",
                    side_effect=lambda *_a, **_k: (True, 200, '{"status":"ok"}', ""),
                ),
                mock.patch.object(stackctl, "run", lambda *_a, **_k: dead),
            ):
                result = stackctl.command_app_debug_preflight(
                    argparse.Namespace(
                        target="alpha-local",
                        runtime_mode="test_live",
                        purpose="runtime",
                        report_dir=str(Path(temp) / "preflight"),
                    )
                )

        # 语义是「环境依赖不可用、可恢复」，不是「App 启动失败」。
        self.assertEqual(result["firstBlocker"], RUNTIME_DEPENDENCY_BLOCKER)
        self.assertEqual(result["status"], "gate_block")
        self.assertIn("mongodb", " ".join(result["details"]))
        self.assertIn("exitCode=133", " ".join(result["details"]))
        # 重跑命令让使用者在修复后能原地复验，不必回去翻文档。
        self.assertIn("app-debug-preflight", result["recoveryCommand"])
        self.assertIn("--target alpha-local", result["recoveryCommand"])
        self.assertEqual(
            result["runtimeContainerLiveness"]["composeProject"],
            startup["composeProject"],
        )

    def test_launch_blocker_vocabulary_stays_single_track(self) -> None:
        """依赖不可用的 typed blocker 必须与 App 启动回执契约同源。"""
        manifest = (
            stackctl.ROOT
            / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(RUNTIME_DEPENDENCY_BLOCKER, manifest)
        self.assertIn(RUNTIME_DEPENDENCY_BLOCKER, LAUNCH_BLOCKERS)


if __name__ == "__main__":
    unittest.main()
