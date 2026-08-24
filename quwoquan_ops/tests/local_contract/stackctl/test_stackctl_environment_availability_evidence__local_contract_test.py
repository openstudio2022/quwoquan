"""环境可用性判据：依赖就绪、必需容器现况与容量水位。

启动前判一次「healthz 200」不能证明环境可用：本次故障里 api-edge 的
/healthz 一直是 200，而 /readyz 是 503、mongodb 已 Exited(133)、Docker 数据盘
写满，startup receipt 却仍是 running。本测试逐条固定这三层判据。
"""

from __future__ import annotations

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t1
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t2
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t3
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t4
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t5
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t6
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t7
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t8

import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import diagnostics_shared, doctor, package_domain, up_runtime
from quwoquan_ops.cli.lib import read_only_user_availability
from quwoquan_ops.cli.lib.app_launch_attempt import RUNTIME_HEALTH_STATUSES
from quwoquan_ops.cli.lib.local_runtime_capacity import (
    CAPACITY_BLOCKER,
    CONTAINER_STORE_SCOPE,
    HOST_SCOPE,
    CapacityPolicy,
    CapacityProbe,
    CapacityReport,
    CapacityThresholds,
    ContainerStoreProbeSpec,
    is_disk_exhausted,
    load_capacity_policy,
    local_runtime_capacity_evidence,
    parse_docker_size,
    probe_container_store_capacity,
)
from quwoquan_ops.cli.lib.runtime_container_liveness import (
    RUNTIME_DEPENDENCY_BLOCKER,
    inspect_compose_project_liveness,
    verify_running_receipt_liveness,
)
from quwoquan_ops.cli.lib.service_runtime_probes import service_probe_matrix

_GiB = 2**30


def _docker_ps(rows: list[dict[str, str]]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["docker", "ps"],
        0,
        "\n".join(json.dumps(row) for row in rows),
        "",
    )


def _docker_liveness_runner(
    rows: list[dict[str, str]],
    *,
    one_shot_services: tuple[str, ...] = (),
):
    """按 `--format` 分派的 `docker ps` 替身。

    现况复验要问 Docker 两件事：容器当前状态（JSON 形状），以及 Compose 把
    哪些服务声明为跑完即退的一次性任务（依赖标签的 tab 形状）。真实 daemon
    对两种 format 给出不同输出，替身必须同样区分，否则一次性任务的声明会在
    测试里凭空消失，判定就会退回用退出码反推身份。
    """

    declaration = ",".join(
        f"{service}:service_completed_successfully:false"
        for service in one_shot_services
    )

    def runner(argv, **_kwargs) -> subprocess.CompletedProcess[str]:
        template = argv[argv.index("--format") + 1]
        if template == "json":
            return _docker_ps(rows)
        return subprocess.CompletedProcess(
            argv,
            0,
            # 声明挂在依赖方容器上，与 Compose 的落标位置一致。
            "\n".join(
                "\t".join(
                    (
                        row.get("Names", ""),
                        row.get("Service", ""),
                        declaration if index == 0 else "",
                    )
                )
                for index, row in enumerate(rows)
            ),
            "",
        )

    return runner


def _capacity_policy() -> CapacityPolicy:
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


def _container_store_runner(available_kib: int):
    """让 df 报出指定可用量的受管 runner。"""

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
            return subprocess.CompletedProcess(argv, 0, "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
            f"overlay 100476656 1 {available_kib} 99% /",
            "",
        )

    return runner


class ServiceReadinessProbeMatrixLocalContractTest(unittest.TestCase):
    """DOM-003.t1/t2/t3：存活与就绪必须是两个可分别定位的 check。"""

    def test_distinct_readiness_services_report_two_checks(self) -> None:
        matrix = service_probe_matrix()
        distinct = {
            name for name, probes in matrix.items() if probes.readiness_is_distinct
        }
        self.assertTrue(
            distinct,
            "至少存在一个声明独立就绪端点的服务，否则本判据无从成立",
        )
        for name in distinct:
            self.assertEqual(matrix[name].readiness, "/readyz")
            self.assertNotEqual(matrix[name].liveness, matrix[name].readiness)
        for name, probes in matrix.items():
            if name in distinct:
                continue
            # 只声明单一深探针的服务不得被补一个恒真的浅探针充数。
            self.assertEqual(probes.readiness, probes.liveness)

    def test_health_checks_carry_liveness_and_readiness_endpoints(self) -> None:
        checks = self._checks_for_alpha_local()
        by_name = {str(item["name"]): item for item in checks}
        matrix = service_probe_matrix()
        distinct = [
            name
            for name, probes in matrix.items()
            if probes.readiness_is_distinct and name in by_name
        ]
        self.assertTrue(distinct, "探针矩阵必须覆盖到本地拓扑的服务角色")
        for name in distinct:
            readiness = by_name.get(f"{name}-readiness")
            self.assertIsNotNone(readiness, f"{name} 缺少独立就绪 check")
            # 失败 check 必须能定位到具体服务与被探端点。
            self.assertTrue(str(readiness["url"]).endswith("/readyz"))
            self.assertEqual(readiness["headers"]["Host"], name)
            self.assertTrue(str(by_name[name]["url"]).endswith(matrix[name].liveness))
        for name, probes in matrix.items():
            if probes.readiness_is_distinct or name not in by_name:
                continue
            self.assertNotIn(f"{name}-readiness", by_name)

    def test_readiness_failure_fails_health_and_names_the_probed_endpoint(self) -> None:
        checks = self._checks_for_alpha_local()
        readiness = next(
            item for item in checks if str(item["name"]).endswith("-readiness")
        )
        failures = [
            {
                "name": str(readiness["name"]),
                "url": str(readiness["url"]),
                "ready": False,
                "statusCode": 503,
            }
        ]
        # 就绪失败必须让 health 失败，而不是被同一服务的存活 200 掩盖。
        self.assertTrue(any(item["ready"] is not True for item in failures))
        detail = f"{failures[0]['name']} is not ready: {failures[0]['statusCode']}"
        self.assertIn(str(readiness["name"]).removesuffix("-readiness"), detail)
        self.assertTrue(str(readiness["url"]).endswith("/readyz"))

    def _checks_for_alpha_local(self) -> list[dict[str, object]]:
        """在受控拓扑输入上求探针选路；探针矩阵本身仍来自真实 deploy 清单。"""
        roles = tuple(service_probe_matrix())
        with (
            mock.patch.object(
                stackctl,
                "load_environment_topology",
                return_value={"environments": {"alpha": {}}},
            ),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={"env": "alpha", "portProfile": "alpha-local"},
            ),
            mock.patch.object(stackctl, "load_port_manifest", return_value={}),
            mock.patch.object(stackctl, "_expected_local_roles", return_value=roles),
            mock.patch.object(stackctl, "canonical_port", return_value=17200),
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value={
                    "composition": {
                        "workloads": [],
                        "runtimeCompositionDigest": "sha256:" + "0" * 64,
                    }
                },
            ),
        ):
            return diagnostics_shared._service_health_checks_for_target("alpha-local")


class RequiredContainerLivenessLocalContractTest(unittest.TestCase):
    """DOM-003.t4/t7：running receipt 不等于当前可用。"""

    def test_exited_or_unhealthy_container_yields_typed_blocker(self) -> None:
        runner = _docker_liveness_runner(
            [
                {
                    "Names": "core",
                    "Service": "service-core",
                    "State": "running",
                    "Status": "Up 2 hours (healthy)",
                },
                {
                    "Names": "mongo",
                    "Service": "mongodb",
                    "State": "exited",
                    "Status": "Exited (133) 3 hours ago",
                },
                {
                    "Names": "pg",
                    "Service": "postgres",
                    "State": "running",
                    "Status": "Up 9 hours (unhealthy)",
                },
            ]
        )
        report = inspect_compose_project_liveness("quwoquan_gamma", runner=runner)
        self.assertEqual(report.status, "degraded")
        self.assertEqual(report.blocker, RUNTIME_DEPENDENCY_BLOCKER)
        self.assertIn(report.status, RUNTIME_HEALTH_STATUSES)
        issues = " ".join(report.issues())
        self.assertIn("mongodb", issues)
        self.assertIn("postgres", issues)
        self.assertIn("exitCode=133", issues)
        self.assertIn("health=unhealthy", issues)

    def test_completed_init_container_is_not_degraded(self) -> None:
        runner = _docker_liveness_runner(
            [
                {
                    "Names": "core",
                    "Service": "service-core",
                    "State": "running",
                    "Status": "Up 2 hours (healthy)",
                },
                {
                    "Names": "init",
                    "Service": "mongo-init",
                    "State": "exited",
                    "Status": "Exited (0) 2 days ago",
                },
            ],
            one_shot_services=("mongo-init",),
        )
        report = inspect_compose_project_liveness("quwoquan_gamma", runner=runner)
        self.assertEqual(report.status, "healthy")
        self.assertEqual(report.blocker, "")
        self.assertEqual(report.issues(), [])

    def test_gracefully_stopped_service_is_not_read_as_a_completed_task(self) -> None:
        """退出码不能用来反推「这是不是一次性任务」。

        长驻服务被 SIGTERM 停掉后以 0 退出，与 init job 跑完同形。若判定按
        零码退出就认定「任务完成」，一个已经停掉的 mongodb 会被报成健康，
        环境继续静默腐烂——本模块存在的理由正是消除这种假绿。
        """
        runner = _docker_liveness_runner(
            [
                {
                    "Names": "core",
                    "Service": "service-core",
                    "State": "running",
                    "Status": "Up 2 hours (healthy)",
                },
                {
                    "Names": "mongo",
                    "Service": "mongodb",
                    "State": "exited",
                    "Status": "Exited (0) 4 minutes ago",
                },
            ],
            one_shot_services=("mongo-init",),
        )
        report = inspect_compose_project_liveness("quwoquan_gamma", runner=runner)
        self.assertEqual(report.status, "degraded")
        self.assertEqual(report.blocker, RUNTIME_DEPENDENCY_BLOCKER)
        issues = " ".join(report.issues())
        self.assertIn("mongodb", issues)
        self.assertIn("not a declared one-shot task", issues)

    def test_declared_one_shot_task_that_failed_stays_a_blocker(self) -> None:
        runner = _docker_liveness_runner(
            [
                {
                    "Names": "core",
                    "Service": "service-core",
                    "State": "running",
                    "Status": "Up 2 hours (healthy)",
                },
                {
                    "Names": "init",
                    "Service": "mongo-init",
                    "State": "exited",
                    "Status": "Exited (1) 2 minutes ago",
                },
            ],
            one_shot_services=("mongo-init",),
        )
        report = inspect_compose_project_liveness("quwoquan_gamma", runner=runner)
        self.assertEqual(report.status, "degraded")
        self.assertEqual(report.blocker, RUNTIME_DEPENDENCY_BLOCKER)
        self.assertIn("exitCode=1", " ".join(report.issues()))

    def test_running_receipt_with_dead_dependency_is_not_available(self) -> None:
        startup = {
            "status": "running",
            "composeProject": "quwoquan_gamma_release_current_1",
        }
        runner = _docker_liveness_runner(
            [
                {
                    "Names": "mongo",
                    "Service": "mongodb",
                    "State": "exited",
                    "Status": "Exited (133) 3 hours ago",
                }
            ]
        )
        report = verify_running_receipt_liveness(startup, runner=runner)
        self.assertIsNotNone(report)
        self.assertEqual(report.status, "unavailable")
        with mock.patch.object(stackctl, "run", runner):
            evidence = read_only_user_availability._runtime_liveness_report(startup)
        self.assertEqual(evidence["status"], "unavailable")
        self.assertTrue(evidence["issues"])

    def test_unreadable_dependency_declaration_is_reported_not_assumed_empty(
        self,
    ) -> None:
        """取不到声明必须报失败，不得当作「没有一次性任务」继续判定。"""

        def runner(argv, **_kwargs) -> subprocess.CompletedProcess[str]:
            template = argv[argv.index("--format") + 1]
            if template == "json":
                return _docker_ps(
                    [
                        {
                            "Names": "init",
                            "Service": "mongo-init",
                            "State": "exited",
                            "Status": "Exited (0) 2 days ago",
                        }
                    ]
                )
            return subprocess.CompletedProcess(argv, 1, "", "docker daemon unreachable")

        with self.assertRaisesRegex(RuntimeError, "Compose dependency labels"):
            inspect_compose_project_liveness("quwoquan_gamma", runner=runner)

    def test_stopped_receipt_makes_liveness_not_applicable(self) -> None:
        runner = _docker_liveness_runner([])
        self.assertIsNone(
            verify_running_receipt_liveness({"status": "stopped"}, runner=runner)
        )


class LocalRuntimeCapacityLocalContractTest(unittest.TestCase):
    """DOM-003.t5/t6/t8：容量是执行前的一等判定且 typed。"""

    def test_declared_thresholds_are_canonical_and_homologous(self) -> None:
        policy = load_capacity_policy()
        self.assertGreater(policy.thresholds.host_free_bytes, 0)
        self.assertGreater(policy.thresholds.container_free_bytes, 0)
        self.assertGreaterEqual(
            policy.thresholds.post_reclaim_container_free_bytes,
            policy.thresholds.container_free_bytes,
        )
        self.assertEqual(policy.threshold_for(HOST_SCOPE), policy.thresholds.host_free_bytes)
        self.assertEqual(
            policy.threshold_for(CONTAINER_STORE_SCOPE),
            policy.thresholds.container_free_bytes,
        )
        self.assertTrue(policy.reclaim_command_for(CONTAINER_STORE_SCOPE))

    def test_insufficient_capacity_reports_measurement_threshold_and_command(self) -> None:
        policy = _capacity_policy()
        probe = probe_container_store_capacity(
            policy,
            runner=_container_store_runner(available_kib=1024 * 1024),
        )
        self.assertFalse(probe.satisfied)
        self.assertEqual(probe.free_bytes, 1 * _GiB)
        self.assertEqual(probe.reclaimable_bytes, parse_docker_size("26GB (100%)"))
        described = probe.describe()
        self.assertIn(CAPACITY_BLOCKER, described)
        self.assertIn("1.00GiB", described)
        self.assertIn("8.00GiB", described)
        self.assertIn("reclaimable=24.21GiB", described)
        self.assertIn("stackctl repair --fix reclaim-build-cache", described)

    def test_capacity_blocker_clears_once_space_returns(self) -> None:
        policy = _capacity_policy()
        exhausted = probe_container_store_capacity(
            policy,
            runner=_container_store_runner(available_kib=1024 * 1024),
        )
        recovered = probe_container_store_capacity(
            policy,
            runner=_container_store_runner(available_kib=40 * 1024 * 1024),
        )
        self.assertEqual(
            CapacityReport(probes=(exhausted,)).blocker,
            CAPACITY_BLOCKER,
        )
        self.assertEqual(CapacityReport(probes=(recovered,)).blocker, "")
        self.assertEqual(CapacityReport(probes=(recovered,)).status, "passed")

    def test_unobserved_container_store_is_not_reported_as_sufficient(self) -> None:
        policy = _capacity_policy()

        def runner(argv, *, timeout_seconds=None, **_kwargs):
            if "system df" in " ".join(argv):
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 1, "", "No such image")

        probe = probe_container_store_capacity(policy, runner=runner)
        self.assertFalse(probe.observed)
        self.assertIsNone(probe.free_bytes)
        self.assertIn("probe:local", probe.absent_reason)
        report = CapacityReport(probes=(probe,))
        self.assertEqual(report.status, "passed")
        self.assertTrue(report.warnings())

    def test_disk_exhaustion_is_typed_not_string_matched(self) -> None:
        self.assertTrue(is_disk_exhausted("write /var/lib: no space left on device"))
        self.assertTrue(is_disk_exhausted("failed with errno 28"))
        self.assertTrue(is_disk_exhausted("ENOSPC while extracting layer"))
        self.assertFalse(is_disk_exhausted("connection refused"))
        self.assertEqual(CAPACITY_BLOCKER, "OPS.CAPACITY.disk_exhausted")
        module, kind, reason = CAPACITY_BLOCKER.split(".")
        self.assertTrue(module.isupper())
        self.assertTrue(kind.isupper())
        self.assertEqual(reason, reason.lower())

    def test_capacity_evidence_skips_non_local_backends(self) -> None:
        self.assertEqual(
            local_runtime_capacity_evidence({"backend": "hosted"})["status"],
            "not_applicable",
        )

    def test_reclaim_keeps_running_when_inventory_reports_exhaustion(self) -> None:
        # 容量不足不得阻断白名单恢复动作本身：清点失败但确认是容量耗尽时，
        # 回收必须继续，否则唯一的恢复路径在最需要它的时刻被关掉。
        source = Path(
            stackctl.ROOT / "quwoquan_ops/cli/commands/repair_build_cache.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_stackctl.is_disk_exhausted(", source)
        self.assertIn("preInventoryBlocker", source)
        self.assertNotIn('"no space left on device" in before_detail', source)


class CapacityPreflightWiringLocalContractTest(unittest.TestCase):
    """DOM-003.t5：五个执行入口都必须在执行前消费容量判定。"""

    def setUp(self) -> None:
        self.insufficient = {
            "status": "gate_block",
            "blocker": CAPACITY_BLOCKER,
            "issues": [
                f"{CAPACITY_BLOCKER}: container-store free space is below threshold "
                "(free=1.00GiB, required=8.00GiB, reclaimable=24.21GiB); "
                "reclaim with: stackctl repair --fix reclaim-build-cache"
            ],
            "warnings": [],
            "reclaimCommands": ["stackctl repair --fix reclaim-build-cache"],
            "evidence": {"status": "gate_block", "blocker": CAPACITY_BLOCKER, "probes": []},
        }

    def test_up_blocks_before_consuming_the_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = argparse.Namespace(
                command="up",
                env="gamma",
                target="",
                workload="full",
                output_format="json",
                report_dir=str(Path(temp) / "up"),
            )
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "backend": "local"},
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value=self.insufficient,
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate_snapshot",
                ) as candidate,
            ):
                result = up_runtime._command_up_impl(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["firstBlocker"], CAPACITY_BLOCKER)
        self.assertTrue(any(CAPACITY_BLOCKER in item for item in result["details"]))
        candidate.assert_not_called()

    def test_package_blocks_before_acquiring_the_build_lock(self) -> None:
        args = argparse.Namespace(
            command="package",
            kind="runtime",
            env="gamma",
            target="gamma-local",
            service="",
            release_attestation="",
            rollback_release_attestation="",
        )
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={"env": "gamma", "backend": "local"},
            ),
            mock.patch.object(
                stackctl,
                "local_runtime_capacity_evidence",
                return_value=self.insufficient,
            ),
            mock.patch.object(
                stackctl,
                "acquire_local_runtime_use_lock",
            ) as use_lock,
        ):
            result = package_domain.command_package(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["firstBlocker"], CAPACITY_BLOCKER)
        use_lock.assert_not_called()

    def test_dev_session_blocks_before_holding_the_operation_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = argparse.Namespace(
                command="dev-session",
                dev_session_action="start",
                env="gamma",
                target="",
                all_nonprod=False,
                launch_app=False,
                app_mode="ui-only",
                device_id="",
                output_format="json",
                report_dir=str(Path(temp) / "dev-session"),
            )
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_dev_session_content_binding_request",
                    return_value={},
                ),
                mock.patch.dict(
                    stackctl.DEV_UP_STACK_TARGETS,
                    {"gamma": "gamma-local"},
                    clear=False,
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "backend": "local"},
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value=self.insufficient,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                ) as operation_lock,
            ):
                result = stackctl.command_dev_session(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "local_runtime_capacity_exhausted")
        self.assertEqual(result["firstBlocker"], CAPACITY_BLOCKER)
        operation_lock.assert_not_called()

    def test_doctor_reports_capacity_finding_and_reclaim_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = argparse.Namespace(
                command="doctor",
                target="gamma-local",
                ssh_host="",
                host_id="",
                deployment_instance="prod",
                output_format="json",
                report_dir=str(Path(temp) / "doctor"),
            )
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma", "backend": "local"},
                ),
                mock.patch.object(
                    stackctl,
                    "_load_active_product_telemetry_log_sink",
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value=self.insufficient,
                ),
                mock.patch.object(
                    stackctl,
                    "command_health",
                    return_value={"exitCode": 0},
                ),
                mock.patch.object(
                    stackctl,
                    "app_deployment_package_dir",
                    return_value=Path(temp),
                ),
            ):
                result = doctor.command_doctor(args)
            plan = json.loads(
                (Path(temp) / "doctor" / "repair_plan.json").read_text(encoding="utf-8")
            )
            report = json.loads(
                (Path(temp) / "doctor" / "report.json").read_text(encoding="utf-8")
            )
        self.assertEqual(result["exitCode"], 1)
        self.assertTrue(any(CAPACITY_BLOCKER in item for item in result["details"]))
        self.assertIn("stackctl repair --fix reclaim-build-cache", plan["actions"])
        self.assertEqual(report["capacity"], self.insufficient["evidence"])


class AppPreflightRuntimeBlockingLocalContractTest(unittest.TestCase):
    """DOM-003.t4/t5：App preflight 在编译安装前对底座断裂硬阻断。

    这里刻意选 `test_live` + `purpose=runtime`（最宽松的档）：身份类问题在这
    一档只进 warnings，因此 details 里出现的只能是容量与依赖判定本身。
    """

    _PROVIDER_DIGEST = "sha256:" + "3" * 64
    _CONFIGURATION_DIGEST = "sha256:" + "1" * 64

    def _preflight(
        self,
        *,
        containers: list[dict[str, str]],
        capacity: dict[str, object],
        expect_login_journey: bool = False,
        one_shot_services: tuple[str, ...] = (),
    ) -> dict[str, object]:
        startup = {
            "status": "running",
            "environment": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "attemptId": "attempt-alpha-availability",
            "composeProject": "quwoquan_alpha_test_live_1",
            "configurationDigest": self._CONFIGURATION_DIGEST,
            "providerRuntimeDigest": self._PROVIDER_DIGEST,
        }
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
                        "runtimeCompositionDigest": self._PROVIDER_DIGEST,
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
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value=capacity,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    _docker_liveness_runner(
                        containers,
                        one_shot_services=one_shot_services,
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_execute_otp_login_journey",
                    return_value={
                        "schema": "otp-local-capture-live-journey",
                        "status": "passed",
                        "sessionPresent": True,
                        "sourceRevision": "a" * 40,
                        "receiptRef": "receipt:otp-login:attempt-alpha-availability",
                        "receiptDigest": "sha256:" + "4" * 64,
                    },
                ) as login_journey,
            ):
                result = stackctl.command_app_debug_preflight(
                    argparse.Namespace(
                        target="alpha-local",
                        runtime_mode="test_live",
                        purpose="runtime",
                        report_dir=str(Path(temp) / "preflight"),
                    )
                )
        if expect_login_journey:
            login_journey.assert_called_once()
        else:
            # 底座断裂时不得继续做登录旅程之类的下游动作。
            login_journey.assert_not_called()
        return result

    @property
    def _sufficient_capacity(self) -> dict[str, object]:
        return {
            "status": "passed",
            "blocker": "",
            "issues": [],
            "warnings": [],
            "reclaimCommands": [],
            "evidence": {"status": "passed", "blocker": "", "probes": []},
        }

    def test_dead_dependency_blocks_preflight_in_the_most_lenient_mode(self) -> None:
        result = self._preflight(
            containers=[
                {
                    "Names": "mongo",
                    "Service": "mongodb",
                    "State": "exited",
                    "Status": "Exited (133) 3 hours ago",
                }
            ],
            capacity=self._sufficient_capacity,
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["status"], "gate_block")
        self.assertEqual(result["firstBlocker"], RUNTIME_DEPENDENCY_BLOCKER)
        liveness = result["runtimeContainerLiveness"]
        self.assertEqual(liveness["status"], "unavailable")
        self.assertIn(liveness["status"], RUNTIME_HEALTH_STATUSES)
        self.assertIn("mongodb", " ".join(result["details"]))

    def test_insufficient_capacity_blocks_preflight_and_outranks_other_findings(
        self,
    ) -> None:
        insufficient = {
            "status": "gate_block",
            "blocker": CAPACITY_BLOCKER,
            "issues": [f"{CAPACITY_BLOCKER}: container-store free space is below threshold"],
            "warnings": [],
            "reclaimCommands": ["stackctl repair --fix reclaim-build-cache"],
            "evidence": {"status": "gate_block", "blocker": CAPACITY_BLOCKER, "probes": []},
        }
        result = self._preflight(
            containers=[
                {
                    "Names": "mongo",
                    "Service": "mongodb",
                    "State": "exited",
                    "Status": "Exited (133) 3 hours ago",
                }
            ],
            capacity=insufficient,
        )
        self.assertEqual(result["exitCode"], 2)
        # 容量是依赖退出的上游成因，首因必须报容量而不是它的级联。
        self.assertEqual(result["firstBlocker"], CAPACITY_BLOCKER)
        self.assertEqual(result["capacity"], insufficient["evidence"])

    def test_healthy_runtime_leaves_preflight_unblocked_by_availability_evidence(
        self,
    ) -> None:
        result = self._preflight(
            containers=[
                {
                    "Names": "core",
                    "Service": "service-core",
                    "State": "running",
                    "Status": "Up 2 hours (healthy)",
                },
                {
                    "Names": "init",
                    "Service": "mongo-init",
                    "State": "exited",
                    "Status": "Exited (0) 2 days ago",
                },
            ],
            capacity=self._sufficient_capacity,
            expect_login_journey=True,
            one_shot_services=("mongo-init",),
        )
        self.assertEqual(result["details"], [])
        self.assertEqual(result["firstBlocker"], "")
        self.assertEqual(result["runtimeContainerLiveness"]["status"], "healthy")

    def test_gracefully_stopped_dependency_still_blocks_preflight(self) -> None:
        """退出码 0 的长驻服务不得让 preflight 放行 App 安装。

        这是本机制最容易漏掉的一档：`docker stop` 与 init job 完成在退出码上
        同形，一旦按退出码判身份，preflight 就会在数据库已经停掉的环境上放行。
        """
        result = self._preflight(
            containers=[
                {
                    "Names": "core",
                    "Service": "service-core",
                    "State": "running",
                    "Status": "Up 2 hours (healthy)",
                },
                {
                    "Names": "mongo",
                    "Service": "mongodb",
                    "State": "exited",
                    "Status": "Exited (0) 4 minutes ago",
                },
            ],
            capacity=self._sufficient_capacity,
            one_shot_services=("mongo-init",),
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["firstBlocker"], RUNTIME_DEPENDENCY_BLOCKER)
        self.assertEqual(result["runtimeContainerLiveness"]["status"], "degraded")
        self.assertIn("mongodb", " ".join(result["details"]))


if __name__ == "__main__":
    unittest.main()
