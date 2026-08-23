"""真实 Docker 上的运行期依赖复验：受控 Compose project 的正反向断言。

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t3
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t6
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t7

local_contract 层用受管替身固定判定规则，但「Docker 现在怎么报状态」只有
真实 daemon 能回答：`docker ps` 的 `State`/`Status` 文本、被 kill 后的退出
码、healthcheck 括号标记都不在我们手里。本测试在一个一次性 Compose project
上做正反两向断言，不触碰任何环境栈：

- 正向：一个长驻容器 + 一个被声明为一次性任务且零码退出的容器 = healthy。
- 反向：长驻容器被 kill 后，同一 project 立刻转为不可用并给出 typed blocker，
  而 `running` receipt 一个字都没变——这正是静默腐烂的形状。
- 反向：长驻容器被 `docker stop` 优雅停止（退出码 0，与 init job 同形）后仍
  必须判为不可用；退出码不能用来反推「这是不是一次性任务」。
"""

from __future__ import annotations

import unittest
import uuid

from quwoquan_ops.cli.lib.common import run
from quwoquan_ops.cli.lib.local_runtime_capacity import load_capacity_policy
from quwoquan_ops.cli.lib.runtime_container_liveness import (
    RUNTIME_DEPENDENCY_BLOCKER,
    inspect_compose_project_liveness,
    verify_running_receipt_liveness,
)

_PROJECT_LABEL = "com.docker.compose.project"
_SERVICE_LABEL = "com.docker.compose.service"
_DEPENDS_ON_LABEL = "com.docker.compose.depends_on"


def _docker_available() -> bool:
    return run(["docker", "info", "--format", "{{.ServerVersion}}"]).returncode == 0


def _local_probe_image() -> str:
    """取一个本地已存在的声明候选镜像；绝不为测试拉镜像。"""
    for image in load_capacity_policy().container_store_probe.candidate_images:
        if run(["docker", "image", "inspect", image, "--format", "{{.Id}}"]).returncode == 0:
            return image
    return ""


class RuntimeDependencyLivenessApiIntegrationTest(unittest.TestCase):
    """DOM-003.t3/t6/t7：现况复验必须由 Docker 自身的容器状态裁定。"""

    @classmethod
    def setUpClass(cls) -> None:
        if not _docker_available():
            raise unittest.SkipTest(
                "runtime liveness api_integration requires a reachable Docker daemon"
            )
        cls.image = _local_probe_image()
        if not cls.image:
            raise unittest.SkipTest(
                "runtime liveness api_integration requires a declared candidate image "
                "to already exist locally"
            )

    def setUp(self) -> None:
        self.project = f"qwq-liveness-probe-{uuid.uuid4().hex[:12]}"
        self.containers: list[str] = []
        self.addCleanup(self._remove_containers)

    def _remove_containers(self) -> None:
        for name in self.containers:
            run(["docker", "rm", "--force", name], check=False)

    def _start(
        self,
        *,
        service: str,
        command: list[str],
        one_shot_dependencies: tuple[str, ...] = (),
    ) -> str:
        """起一个带 Compose 身份标签的容器。

        `one_shot_dependencies` 复刻 Compose 为 `condition:
        service_completed_successfully` 写下的依赖标签，这是「哪个服务是
        init job」的唯一声明来源；不带它就等于没有任何服务被声明为一次性
        任务。
        """
        name = f"{self.project}-{service}"
        labels = [
            f"{_PROJECT_LABEL}={self.project}",
            f"{_SERVICE_LABEL}={service}",
        ]
        if one_shot_dependencies:
            labels.append(
                f"{_DEPENDS_ON_LABEL}="
                + ",".join(
                    f"{dependency}:service_completed_successfully:false"
                    for dependency in one_shot_dependencies
                )
            )
        result = run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                *[argument for label in labels for argument in ("--label", label)],
                "--entrypoint",
                command[0],
                self.image,
                *command[1:],
            ],
            timeout_seconds=120,
            check=False,
        )
        self.containers.append(name)
        self.assertEqual(
            result.returncode,
            0,
            f"docker run failed for {service}: {result.stderr.strip()}",
        )
        return name

    def _await_exit(self, name: str) -> None:
        result = run(["docker", "wait", name], timeout_seconds=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.strip())

    def test_live_stack_and_completed_task_read_as_healthy(self) -> None:
        self._start(
            service="long-running",
            command=["sleep", "300"],
            one_shot_dependencies=("init-task",),
        )
        finished = self._start(service="init-task", command=["true"])
        self._await_exit(finished)

        report = inspect_compose_project_liveness(self.project, runner=run)

        self.assertEqual(report.status, "healthy")
        self.assertEqual(report.blocker, "")
        self.assertEqual(report.issues(), [])
        # `docker ps` 只在 Compose 自己拉起的容器上填 Service，手工打的 label
        # 不保证回填，因此按容器名定位——判定本身也走 `service or name` 兜底。
        by_name = {item.name: item for item in report.containers}
        self.assertEqual(by_name[f"{self.project}-long-running"].state, "running")
        # 被声明为一次性任务且零码退出，判定不得把它算成故障。
        finished_liveness = by_name[f"{self.project}-init-task"]
        self.assertTrue(finished_liveness.declared_one_shot)
        self.assertTrue(finished_liveness.is_completed_task)
        self.assertEqual(finished_liveness.exit_code, 0)

    def test_gracefully_stopped_long_running_service_is_not_a_completed_task(
        self,
    ) -> None:
        """零码退出不足以证明「跑完了」——那正是 docker stop 留下的形状。

        长驻服务收到 SIGTERM 后以 0 退出，与 init job 跑完退出在退出码上
        完全同形。只要判定用退出码反推身份，被停掉的数据库就会被报成健康，
        环境继续静默腐烂。身份必须来自拓扑声明。
        """
        stopped = self._start(
            service="long-running",
            # PID 1 只在自己装了 handler 时才响应 SIGTERM，否则内核直接忽略、
            # 最终被 SIGKILL 收走（137）。显式 trap 让容器像真实服务那样优雅
            # 退出并回 0——这才是 docker stop 一个数据库之后的形状。
            command=["sh", "-c", 'trap "exit 0" TERM; while true; do sleep 1; done'],
        )
        self.assertEqual(
            run(["docker", "stop", stopped], timeout_seconds=60, check=False).returncode,
            0,
        )
        self._await_exit(stopped)

        report = inspect_compose_project_liveness(self.project, runner=run)

        liveness = {item.name: item for item in report.containers}[stopped]
        self.assertEqual(liveness.state, "exited")
        self.assertEqual(liveness.exit_code, 0)
        self.assertFalse(liveness.declared_one_shot)
        self.assertFalse(liveness.is_completed_task)
        self.assertEqual(report.status, "unavailable")
        self.assertEqual(report.blocker, RUNTIME_DEPENDENCY_BLOCKER)
        self.assertIn("not a declared one-shot task", " ".join(report.issues()))

    def test_failed_init_job_stays_a_blocker_despite_its_declaration(self) -> None:
        """被声明为一次性任务，也只有真的成功跑完才算完成。"""
        self._start(
            service="long-running",
            command=["sleep", "300"],
            one_shot_dependencies=("init-task",),
        )
        failed = self._start(service="init-task", command=["false"])
        self._await_exit(failed)

        report = inspect_compose_project_liveness(self.project, runner=run)

        liveness = {item.name: item for item in report.containers}[failed]
        self.assertTrue(liveness.declared_one_shot)
        self.assertNotEqual(liveness.exit_code, 0)
        self.assertFalse(liveness.is_completed_task)
        self.assertEqual(report.status, "degraded")
        self.assertEqual(report.blocker, RUNTIME_DEPENDENCY_BLOCKER)

    def test_killed_dependency_turns_the_running_receipt_unavailable(self) -> None:
        killed = self._start(service="long-running", command=["sleep", "300"])
        receipt = {
            "status": "running",
            "target": "gamma-local",
            "composeProject": self.project,
        }
        healthy = verify_running_receipt_liveness(receipt, runner=run)
        self.assertIsNotNone(healthy)
        self.assertEqual(healthy.status, "healthy")

        self.assertEqual(
            run(["docker", "kill", killed], timeout_seconds=60, check=False).returncode,
            0,
        )
        self._await_exit(killed)

        # receipt 一个字节都没有变化，但结论必须变。
        degraded = verify_running_receipt_liveness(receipt, runner=run)
        self.assertIsNotNone(degraded)
        self.assertEqual(degraded.status, "unavailable")
        self.assertEqual(degraded.blocker, RUNTIME_DEPENDENCY_BLOCKER)
        issues = " ".join(degraded.issues())
        self.assertIn(f"{self.project}-long-running", issues)
        self.assertIn("state=exited", issues)
        self.assertIsNotNone(degraded.containers[0].exit_code)
        self.assertNotEqual(degraded.containers[0].exit_code, 0)

    def test_vanished_project_is_not_reported_as_available(self) -> None:
        # project 里一个容器都没有时，「startup receipt 仍是 running」不能撑起可用。
        report = verify_running_receipt_liveness(
            {"status": "running", "composeProject": self.project},
            runner=run,
        )
        self.assertIsNotNone(report)
        self.assertEqual(report.status, "unavailable")
        self.assertEqual(report.blocker, RUNTIME_DEPENDENCY_BLOCKER)
        self.assertIn("owns no container", " ".join(report.issues()))


if __name__ == "__main__":
    unittest.main()
