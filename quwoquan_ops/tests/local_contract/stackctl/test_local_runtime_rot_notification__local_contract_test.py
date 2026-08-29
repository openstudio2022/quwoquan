"""本地运行期腐烂的主动告知：周期复验、跃迁报出、不刷屏、恢复也显式。"""

from __future__ import annotations

# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/local-runtime-rot-notification/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/local-runtime-rot-notification/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/local-runtime-rot-notification/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/local-runtime-rot-notification/spec.md#gwt-001.t4

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_runtime_capacity
from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    transition_app_launch_attempt,
    wait_for_app_launch_attempt,
)
from quwoquan_ops.cli.lib.local_runtime_capacity import (
    CAPACITY_BLOCKER,
    HOST_SCOPE,
    CapacityPolicy,
    CapacityProbe,
    CapacityThresholds,
    ContainerStoreProbeSpec,
)
from quwoquan_ops.cli.lib.local_runtime_rot_watch import (
    DEGRADED,
    HEALTHY,
    UNAVAILABLE,
    UNOBSERVED,
    LocalRuntimeRotWatch,
    observe_local_runtime,
)

_GiB = 2**30
_TARGET = {"backend": "local"}
_STARTUP = {"status": "running", "composeProject": "quwoquan_gamma_release_7002_1"}

_HEALTHY_CONTAINERS = [
    {
        "Names": "core",
        "Service": "service-core",
        "State": "running",
        "Status": "Up 2 hours (healthy)",
    }
]
_DEAD_CONTAINERS = [
    {
        "Names": "mongo",
        "Service": "mongodb",
        "State": "exited",
        "Status": "Exited (133) 3 hours ago",
    }
]

_ROOMY_KIB = 60 * 1024 * 1024
_CRAMPED_KIB = 1024 * 1024


def _policy() -> CapacityPolicy:
    return CapacityPolicy(
        thresholds=CapacityThresholds(
            host_free_bytes=10 * _GiB,
            container_free_bytes=8 * _GiB,
            post_reclaim_container_free_bytes=14 * _GiB,
        ),
        container_store_probe=ContainerStoreProbeSpec(
            candidate_images=("probe:local",),
            mount_path="/",
        ),
        reclaim_commands={
            "containerStore": "stackctl repair --fix reclaim-build-cache",
            "host": "stackctl repair --fix reconcile-output-layout",
        },
    )


def _runner(
    *,
    containers: list[dict[str, str]],
    available_kib: int,
    one_shot_services: tuple[str, ...] = (),
):
    """受管命令执行器：按 argv 分派容器现况与 Docker 数据盘观测。

    `docker ps` 被问两次且形状不同：容器状态走 JSON，Compose 把哪些服务声明
    为一次性任务走依赖标签的 tab 输出。这里照样区分，否则声明会凭空消失，
    零码退出的长驻服务就会被当成跑完的 init job。
    """

    def run(argv, *, timeout_seconds=None, **_kwargs):
        joined = " ".join(argv)
        if "docker ps" in joined or " ps " in f" {joined} ":
            if "--format" in argv and argv[argv.index("--format") + 1] != "json":
                declaration = ",".join(
                    f"{service}:service_completed_successfully:false"
                    for service in one_shot_services
                )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    "\n".join(
                        "\t".join(
                            (
                                row.get("Names", ""),
                                row.get("Service", ""),
                                declaration if index == 0 else "",
                            )
                        )
                        for index, row in enumerate(containers)
                    ),
                    "",
                )
            return subprocess.CompletedProcess(
                argv,
                0,
                "\n".join(json.dumps(row) for row in containers),
                "",
            )
        if "system df" in joined:
            return subprocess.CompletedProcess(
                argv,
                0,
                '{"Type":"Build Cache","Size":"26GB","Reclaimable":"26GB (100%)"}',
                "",
            )
        if "image inspect" in joined:
            return subprocess.CompletedProcess(argv, 0, "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
            f"overlay 100476656 1 {available_kib} 99% /",
            "",
        )

    return run


def _fixed_host_probe(policy: CapacityPolicy, *, path=None) -> CapacityProbe:
    """把不受测试控制的宿主盘固定为充足，使断言只反映被测判据。"""
    return CapacityProbe(
        scope=HOST_SCOPE,
        threshold_bytes=policy.threshold_for(HOST_SCOPE),
        free_bytes=policy.threshold_for(HOST_SCOPE) * 4,
        total_bytes=policy.threshold_for(HOST_SCOPE) * 10,
        reclaim_command=policy.reclaim_command_for(HOST_SCOPE),
    )


class _CapacityHarness:
    """容量判定的受控夹具：阈值与宿主盘固定，容器存储由 runner 决定。"""

    def __enter__(self):
        self._patches = [
            mock.patch.object(
                local_runtime_capacity, "load_capacity_policy", _policy
            ),
            mock.patch.object(
                local_runtime_capacity, "probe_host_capacity", _fixed_host_probe
            ),
        ]
        for item in self._patches:
            item.start()
        return self

    def __exit__(self, *_exc) -> None:
        for item in reversed(self._patches):
            item.stop()


class LocalRuntimeRotWatchLocalContractTest(unittest.TestCase):
    """GWT-001.t1/t2/t3/t4：跃迁必须被报出一次，且判据可行动。"""

    def test_dependency_loss_is_reported_once_with_its_trigger(self) -> None:
        with _CapacityHarness():
            watch = LocalRuntimeRotWatch(
                target=_TARGET,
                startup=_STARTUP,
                runner=_runner(
                    containers=_HEALTHY_CONTAINERS, available_kib=_ROOMY_KIB
                ),
            )
            self.assertIsNone(watch.observe(), "健康状态持续时不产生跃迁事件")

            watch.runner = _runner(
                containers=_DEAD_CONTAINERS, available_kib=_ROOMY_KIB
            )
            transition = watch.observe()
            self.assertIsNotNone(transition)
            self.assertEqual(transition.from_status, HEALTHY)
            self.assertEqual(transition.to_status, UNAVAILABLE)
            described = transition.describe()
            self.assertIn("degraded", described)
            # 触发判据必须点名容器与状态，而不是只说「环境不可用」。
            self.assertIn("mongodb", described)
            self.assertIn("exitCode=133", described)

            self.assertIsNone(watch.observe(), "同一降级状态持续期间不重复报出")

    def test_capacity_shortfall_reports_measurement_threshold_and_command(self) -> None:
        with _CapacityHarness():
            watch = LocalRuntimeRotWatch(
                target=_TARGET,
                startup=_STARTUP,
                runner=_runner(
                    containers=_HEALTHY_CONTAINERS, available_kib=_CRAMPED_KIB
                ),
            )
            transition = watch.observe()
        self.assertIsNotNone(transition)
        self.assertEqual(transition.to_status, DEGRADED)
        described = transition.describe()
        self.assertIn(CAPACITY_BLOCKER, described)
        self.assertIn("free=1.00GiB", described)
        self.assertIn("required=8.00GiB", described)
        self.assertIn("reclaim with: stackctl repair --fix reclaim-build-cache", described)

    def test_recovery_is_reported_as_an_explicit_fact(self) -> None:
        with _CapacityHarness():
            watch = LocalRuntimeRotWatch(
                target=_TARGET,
                startup=_STARTUP,
                runner=_runner(containers=_DEAD_CONTAINERS, available_kib=_ROOMY_KIB),
            )
            self.assertIsNotNone(watch.observe())
            watch.runner = _runner(
                containers=_HEALTHY_CONTAINERS, available_kib=_ROOMY_KIB
            )
            recovery = watch.observe()
            self.assertIsNone(watch.observe(), "恢复后同样不重复报出")
        self.assertIsNotNone(recovery)
        self.assertTrue(recovery.recovered)
        self.assertEqual(recovery.to_status, HEALTHY)
        self.assertIn("recovered", recovery.describe())

    def test_transitions_enter_a_readable_session_receipt(self) -> None:
        with _CapacityHarness():
            watch = LocalRuntimeRotWatch(
                target=_TARGET,
                startup=_STARTUP,
                runner=_runner(containers=_DEAD_CONTAINERS, available_kib=_ROOMY_KIB),
            )
            watch.observe()
            watch.runner = _runner(
                containers=_HEALTHY_CONTAINERS, available_kib=_ROOMY_KIB
            )
            watch.observe()
            evidence = watch.as_evidence()
        self.assertEqual(evidence["status"], HEALTHY)
        self.assertEqual(
            [(item["from"], item["to"]) for item in evidence["transitions"]],
            [(HEALTHY, UNAVAILABLE), (UNAVAILABLE, HEALTHY)],
        )
        for item in evidence["transitions"]:
            self.assertTrue(str(item["at"]).endswith("Z"))
            self.assertTrue(item["details"] or item["to"] == HEALTHY)
        # 回执必须可序列化后回读，否则会话结束就无跃迁序列可查。
        self.assertEqual(json.loads(json.dumps(evidence)), evidence)

    def test_unverifiable_observation_is_not_reported_as_healthy(self) -> None:
        def broken(argv, *, timeout_seconds=None, **_kwargs):
            return subprocess.CompletedProcess(argv, 1, "", "docker daemon is gone")

        with _CapacityHarness():
            observation = observe_local_runtime(
                target=_TARGET,
                startup=_STARTUP,
                runner=broken,
            )
        self.assertEqual(observation.status, UNOBSERVED)
        self.assertFalse(observation.degraded)
        self.assertTrue(observation.details)


class LaunchWaitWatchdogLocalContractTest(unittest.TestCase):
    """GWT-001.t1：编译安装启动可达十几分钟，等待窗口内必须持续复验。"""

    def test_watchdog_runs_while_waiting_for_the_launch_receipt(self) -> None:
        observed: list[int] = []
        with tempfile.TemporaryDirectory() as temp:
            receipt = Path(temp) / "app-launch.json"
            create_app_launch_attempt(
                receipt,
                environment="gamma",
                target="gamma-local",
                platform="android",
                build_profile="nonprod",
                build_mode="debug",
                run_mode="ui-only",
                launch_provenance="canonical_launcher",
                runtime_config_supply_mode="external_runtime_package",
                runtime_config_trust_envelope_digest="sha256:" + "a" * 64,
                runtime_config_package_digest="sha256:" + "a" * 64,
                application_id="com.quwoquan.fixture",
                flutter_version="3.47.0",
                command_resolution_digest="sha256:" + "a" * 64,
                device_id="emulator-5554",
            )

            def watchdog() -> None:
                observed.append(len(observed))
                if len(observed) >= 2:
                    transition_app_launch_attempt(receipt, "stopped")

            attempt = wait_for_app_launch_attempt(
                receipt,
                timeout_seconds=30,
                poll_seconds=0.01,
                watchdog=watchdog,
                watchdog_interval_seconds=0,
            )
        self.assertGreaterEqual(len(observed), 2)
        self.assertEqual(attempt["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
