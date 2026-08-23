"""startup receipt 声明的 runtime 现况复验。

startup receipt 的 `status: running` 只记录启动那一刻的事实。容器在之后
退出（磁盘写满、OOM、依赖崩溃）不会回写任何 receipt，于是「环境可用」
这个结论可以在无人复验的情况下保持数小时甚至数天——这就是环境静默腐烂。

本模块按 receipt 声明的 Compose project 查询容器**当前**的 State 与
Health，把「启动过」和「现在还活着」分成两件事。真相源是 Docker 自身的
容器状态，不新增第二份运行台账。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from typing import Any

# 必需容器退出或 unhealthy 时，App 编译安装前必须以该 typed blocker 阻断。
# 与 app_launch_manifest.yaml 的 launch_blockers 同源。
RUNTIME_DEPENDENCY_BLOCKER = "APP.LAUNCH.runtime_dependency_unavailable"
_LIVE_STATE = "running"
_EXITED_STATE = "exited"
_UNHEALTHY = "unhealthy"
_EXIT_CODE = re.compile(r"Exited\s+\((\d+)\)")
_PROJECT_LABEL = "com.docker.compose.project"
_SERVICE_LABEL = "com.docker.compose.service"
_DEPENDS_ON_LABEL = "com.docker.compose.depends_on"
_ONE_SHOT_CONDITION = "service_completed_successfully"


class ComposeProjectAbsent(ValueError):
    """receipt 未声明 Compose project，现况无从观测。

    与「观测到不健康」是两件事：startup receipt 契约本就要求 running
    receipt 声明非空 composeProject，因此这里只会在 receipt 被绕过时出现。
    调用方必须显式报出未观测，而不是把它算作健康或不可用。
    """


@dataclass(frozen=True)
class ContainerLiveness:
    """一个容器的当前状态。

    `health` 为空表示该容器未声明 healthcheck。`exit_code` 仅在容器已退出
    时有值（缺席用 `None`）。`declared_one_shot` 记录拓扑是否把该服务声明
    为跑完即退的一次性任务。
    """

    name: str
    service: str
    state: str
    health: str
    exit_code: int | None = None
    declared_one_shot: bool = False

    @property
    def is_completed_task(self) -> bool:
        """被拓扑声明为一次性任务，且确实已成功跑完。

        一次性任务的身份只能来自声明。用「零码退出」反推会把长驻服务的
        优雅退出也算成任务完成——SIGTERM 下的数据库正是以 0 退出的，那会
        让一个已经停掉的 mongodb 被报成健康，也就是本模块要消除的那种
        静默腐烂。被声明为一次性任务但非零退出的 init job 仍是故障。
        """
        return (
            self.declared_one_shot
            and self.state == _EXITED_STATE
            and self.exit_code == 0
        )

    @property
    def is_live(self) -> bool:
        """进程在跑，且声明了 healthcheck 时未处于 unhealthy。"""
        return self.state == _LIVE_STATE and self.health != _UNHEALTHY

    @property
    def is_degraded(self) -> bool:
        """既没在健康地跑，也不是已正常完成的一次性任务。"""
        return not self.is_live and not self.is_completed_task

    def describe(self) -> str:
        health = f", health={self.health}" if self.health else ""
        code = f", exitCode={self.exit_code}" if self.exit_code is not None else ""
        # 零码退出的长驻服务最容易被读成「正常结束」，明确点出它并非 init job，
        # 否则 exitCode=0 却判故障会让人以为是误报。
        kind = (
            ", not a declared one-shot task"
            if self.state == _EXITED_STATE and not self.declared_one_shot
            else ""
        )
        return f"{self.service or self.name} (state={self.state}{code}{health}{kind})"


@dataclass(frozen=True)
class RuntimeLivenessReport:
    """一个 Compose project 的现况复验结论。"""

    compose_project: str
    containers: tuple[ContainerLiveness, ...]

    @property
    def degraded(self) -> tuple[ContainerLiveness, ...]:
        return tuple(item for item in self.containers if item.is_degraded)

    @property
    def status(self) -> str:
        """映射到 app launch attempt 的 runtimeHealthStatus 取值域。"""
        if not self.containers:
            return "unavailable"
        if not self.degraded:
            return "healthy"
        if not any(item.is_live for item in self.containers):
            return "unavailable"
        return "degraded"

    @property
    def blocker(self) -> str:
        """未就绪时返回 typed blocker；就绪时返回空字符串（在场为空）。"""
        return "" if self.status == "healthy" else RUNTIME_DEPENDENCY_BLOCKER

    def issues(self) -> list[str]:
        if not self.containers:
            return [
                f"Compose project {self.compose_project} owns no container; the "
                "running startup receipt no longer describes anything alive"
            ]
        return [
            f"required container is not live: {item.describe()}"
            for item in self.degraded
        ]


def _parse_container_rows(payload: str) -> list[dict[str, Any]]:
    """解析 `docker ps --format json` 的逐行 JSON 输出。"""
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("docker ps row is not an object")
        rows.append(parsed)
    return rows


def _health_from_status(status: str) -> str:
    """从 `Status` 文本提取 healthcheck 结论。

    Docker 的 `docker ps` 不单列 health，只在 Status 里以
    `Up 2 hours (unhealthy)` 的形式给出。
    """
    lowered = status.lower()
    for marker in ("unhealthy", "health: starting", "healthy"):
        if f"({marker})" in lowered:
            return "starting" if marker == "health: starting" else marker
    return ""


def _exit_code_from_status(status: str) -> int | None:
    """从 `Exited (0) 2 days ago` 提取退出码；未退出时缺席。"""
    match = _EXIT_CODE.search(status)
    return int(match.group(1)) if match is not None else None


def _declared_one_shot_containers(project: str, *, runner: Any) -> frozenset[str]:
    """取出被拓扑声明为一次性任务的容器名集合。

    判据是 Compose 原生的 `condition: service_completed_successfully`：谁被
    这样依赖，谁就是跑完即退的 init job。Compose 把这份依赖声明写进依赖方
    容器的标签，所以真相源仍是 Docker 自身，不必再去加载 Compose 文件，也
    不新增第二份运行台账。

    声明按服务名给出，这里就地映射回容器名，让调用方只需比对 `docker ps`
    一定会填的 `Names`。服务名取自标签而不是 `docker ps` 的 `Service` 派生
    列，后者对非 Compose 拉起的容器不保证回填。

    依赖声明本身缺席是正常的（多数服务不依赖任何 init job），但取不到声明
    是失败：那会让 init job 被误判为故障，必须报出而不是当作空集合。
    """
    result = runner(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label={_PROJECT_LABEL}={project}",
            "--format",
            "{{.Names}}\t"
            f'{{{{.Label "{_SERVICE_LABEL}"}}}}\t'
            f'{{{{.Label "{_DEPENDS_ON_LABEL}"}}}}',
        ],
        timeout_seconds=30,
    )
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"docker ps could not read Compose dependency labels for project "
            f"{project}: {str(getattr(result, 'stderr', '')).strip()}"
        )
    containers_by_service: dict[str, set[str]] = {}
    one_shot_services: set[str] = set()
    for line in str(getattr(result, "stdout", "")).splitlines():
        columns = line.split("\t")
        if len(columns) < 3:
            continue
        name, service, declaration = (item.strip() for item in columns[:3])
        if service:
            containers_by_service.setdefault(service, set()).add(name)
        for token in declaration.split(","):
            # 每项形如 `<service>:<condition>:<restart>`。
            parts = token.strip().split(":")
            if len(parts) >= 2 and parts[1] == _ONE_SHOT_CONDITION:
                one_shot_services.add(parts[0])
    return frozenset(
        name
        for service in one_shot_services
        for name in containers_by_service.get(service, ())
    )


def inspect_compose_project_liveness(
    compose_project: str,
    *,
    runner: Any,
) -> RuntimeLivenessReport:
    """查询该 Compose project 全部容器的当前状态。

    `runner` 是 stackctl 的受管命令执行器，便于测试注入。
    """
    project = str(compose_project or "").strip()
    if not project:
        raise ComposeProjectAbsent(
            "runtime liveness verification requires a Compose project"
        )
    result = runner(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            "json",
        ],
        timeout_seconds=30,
    )
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"docker ps failed for Compose project {project}: "
            f"{str(getattr(result, 'stderr', '')).strip()}"
        )
    one_shot = _declared_one_shot_containers(project, runner=runner)
    containers = tuple(
        ContainerLiveness(
            name=str(row.get("Names") or ""),
            service=str(row.get("Service") or ""),
            state=str(row.get("State") or ""),
            health=str(row.get("Health") or "")
            or _health_from_status(str(row.get("Status") or "")),
            exit_code=_exit_code_from_status(str(row.get("Status") or "")),
            declared_one_shot=str(row.get("Names") or "") in one_shot,
        )
        for row in _parse_container_rows(str(getattr(result, "stdout", "")))
    )
    return RuntimeLivenessReport(compose_project=project, containers=containers)


def verify_running_receipt_liveness(
    receipt: Mapping[str, Any] | None,
    *,
    runner: Any,
) -> RuntimeLivenessReport | None:
    """复验一份 running receipt 所声明 runtime 的现况。

    receipt 缺席或不处于 running 时返回 `None`（未命中，不是失败）：此时
    没有「启动过」这个前提，现况复验无从谈起。
    """
    if not isinstance(receipt, Mapping) or receipt.get("status") != "running":
        return None
    return inspect_compose_project_liveness(
        str(receipt.get("composeProject") or ""),
        runner=runner,
    )


def liveness_issue_details(report: RuntimeLivenessReport | None) -> Sequence[str]:
    """把复验结论摊平为报告用的详情行；就绪或未命中时为空。"""
    if report is None or report.status == "healthy":
        return ()
    return tuple(report.issues())
