"""本地容器运行时的容量水位前置判定。

容量耗尽不会以「容量耗尽」的形式暴露：它表现为 mongodb 以 133 退出、
postgres healthcheck 报 `no space left on device`、Docker 内嵌 DNS 解析失败。
等这些症状被人从界面上看见时，环境已经腐烂了很久。

本模块把容量变成执行前的一等判定，覆盖两个互相独立的 scope：

- `host`：开发机宿主盘。构建产物、候选包与 Docker 数据盘镜像都在这里增长。
- `container-store`：Docker 数据盘。macOS 上它是宿主上的独立配额镜像，
  宿主盘还有余量时它可以先写满，因此不能用宿主可用量代替。

阈值来自 `quwoquan_ops/environments/local_runtime_capacity.yaml`，与 prod
`access-isolation.yaml` 的 `minimumHostResources` 同构，不在代码里硬编码。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import re
import shutil

from quwoquan_ops.cli.lib.common import ROOT, load_json_yaml

# 容量耗尽的 typed blocker，遵循 MODULE.KIND.REASON。
# 取代对底层 `no space left on device` 文本的字符串特判。
CAPACITY_BLOCKER = "OPS.CAPACITY.disk_exhausted"

MANIFEST_PATH = ROOT / "quwoquan_ops" / "environments" / "local_runtime_capacity.yaml"

HOST_SCOPE = "host"
CONTAINER_STORE_SCOPE = "container-store"

# Docker 报告容量用 SI 单位（GB = 1e9），不是 IEC。混用会让阈值判定偏差 7%。
_SI_UNITS = {
    "b": 1,
    "kb": 10**3,
    "mb": 10**6,
    "gb": 10**9,
    "tb": 10**12,
    "pb": 10**15,
}
_IEC_UNITS = {
    "kib": 2**10,
    "mib": 2**20,
    "gib": 2**30,
    "tib": 2**40,
}
_SIZE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)")
# `no space left on device` 与 ENOSPC 是同一件事的两种表述。
_ENOSPC = re.compile(r"no space left on device|errno\s*28\b|enospc", re.IGNORECASE)


class LocalRuntimeCapacityError(ValueError):
    """容量声明缺失或不合法。"""


def parse_docker_size(text: str) -> int:
    """把 Docker 的 `11GB (81%)` / `6.561MB` 解析为字节。

    只解析前导数值与单位，忽略百分比尾部。无法解析时抛错而不是返回 0：
    把「读不出来」塌陷成「零占用」会让判定悄悄失真。
    """
    match = _SIZE.match(str(text))
    if match is None:
        raise LocalRuntimeCapacityError(f"docker size is unparseable: {text!r}")
    amount = float(match.group(1))
    unit = match.group(2).strip().lower() or "b"
    scale = _IEC_UNITS.get(unit) or _SI_UNITS.get(unit)
    if scale is None:
        raise LocalRuntimeCapacityError(f"docker size unit is unknown: {text!r}")
    return int(amount * scale)


def is_disk_exhausted(*fragments: str) -> bool:
    """判断命令输出是否在报容量耗尽。"""
    return any(_ENOSPC.search(str(item) or "") for item in fragments)


@dataclass(frozen=True)
class CapacityThresholds:
    host_free_bytes: int
    container_free_bytes: int
    post_reclaim_container_free_bytes: int


@dataclass(frozen=True)
class ContainerStoreProbeSpec:
    candidate_images: tuple[str, ...]
    mount_path: str


@dataclass(frozen=True)
class CapacityPolicy:
    thresholds: CapacityThresholds
    container_store_probe: ContainerStoreProbeSpec
    reclaim_commands: Mapping[str, str]

    def threshold_for(self, scope: str) -> int:
        if scope == HOST_SCOPE:
            return self.thresholds.host_free_bytes
        if scope == CONTAINER_STORE_SCOPE:
            return self.thresholds.container_free_bytes
        raise LocalRuntimeCapacityError(f"capacity scope is unknown: {scope}")

    def reclaim_command_for(self, scope: str) -> str:
        key = "host" if scope == HOST_SCOPE else "containerStore"
        return str(self.reclaim_commands.get(key) or "")


@dataclass(frozen=True)
class CapacityProbe:
    """一个 scope 的容量观测结果。

    `free_bytes` 为 `None` 表示未观测（缺席），与「可用空间为 0」是两件
    不同的事：前者不构成阻断，但必须显式报出。
    """

    scope: str
    threshold_bytes: int
    free_bytes: int | None = None
    total_bytes: int | None = None
    reclaimable_bytes: int | None = None
    reclaim_command: str = ""
    absent_reason: str = ""

    @property
    def observed(self) -> bool:
        return self.free_bytes is not None

    @property
    def satisfied(self) -> bool:
        """未观测时不判失败：缺席不等于不足，也不等于充足。"""
        return not self.observed or int(self.free_bytes or 0) >= self.threshold_bytes

    def describe(self) -> str:
        if not self.observed:
            return (
                f"{self.scope} capacity is unobserved: "
                f"{self.absent_reason or 'no probe available'}"
            )
        reclaimable = (
            f", reclaimable={_gib(self.reclaimable_bytes)}"
            if self.reclaimable_bytes is not None
            else ""
        )
        command = f"; reclaim with: {self.reclaim_command}" if self.reclaim_command else ""
        return (
            f"{CAPACITY_BLOCKER}: {self.scope} free space is below threshold "
            f"(free={_gib(self.free_bytes)}, required={_gib(self.threshold_bytes)}"
            f"{reclaimable}){command}"
        )

    def as_evidence(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "observed": self.observed,
            "freeBytes": self.free_bytes,
            "totalBytes": self.total_bytes,
            "thresholdBytes": self.threshold_bytes,
            "reclaimableBytes": self.reclaimable_bytes,
            "satisfied": self.satisfied,
            "absentReason": self.absent_reason,
            "reclaimCommand": self.reclaim_command if not self.satisfied else "",
        }


@dataclass(frozen=True)
class CapacityReport:
    probes: tuple[CapacityProbe, ...]

    @property
    def insufficient(self) -> tuple[CapacityProbe, ...]:
        return tuple(item for item in self.probes if not item.satisfied)

    @property
    def unobserved(self) -> tuple[CapacityProbe, ...]:
        return tuple(item for item in self.probes if not item.observed)

    @property
    def status(self) -> str:
        return "gate_block" if self.insufficient else "passed"

    @property
    def blocker(self) -> str:
        """不足时返回 typed blocker；充足时返回空字符串（在场为空）。"""
        return CAPACITY_BLOCKER if self.insufficient else ""

    def issues(self) -> list[str]:
        return [item.describe() for item in self.insufficient]

    def warnings(self) -> list[str]:
        return [item.describe() for item in self.unobserved]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "blocker": self.blocker,
            "probes": [item.as_evidence() for item in self.probes],
        }


def _gib(value: int | None) -> str:
    if value is None:
        return "unobserved"
    return f"{int(value) / 2**30:.2f}GiB"


def load_capacity_policy(path: str | Path | None = None) -> CapacityPolicy:
    """读取本地容量阈值声明。"""
    manifest_path = Path(path) if path is not None else MANIFEST_PATH
    payload = load_json_yaml(manifest_path)
    if not isinstance(payload, Mapping):
        raise LocalRuntimeCapacityError(
            f"{manifest_path} is not a local-runtime-capacity mapping"
        )
    if str(payload.get("schema") or "") != "local-runtime-capacity":
        raise LocalRuntimeCapacityError(
            f"{manifest_path} declares an unexpected schema"
        )
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise LocalRuntimeCapacityError(f"{manifest_path} has no thresholds")
    required = (
        "hostFreeBytes",
        "containerFreeBytes",
        "postReclaimContainerFreeBytes",
    )
    missing = [field for field in required if not isinstance(thresholds.get(field), int)]
    if missing:
        raise LocalRuntimeCapacityError(
            f"{manifest_path} thresholds require integer bytes for {', '.join(missing)}"
        )
    probe = payload.get("containerStoreProbe")
    if not isinstance(probe, Mapping):
        raise LocalRuntimeCapacityError(
            f"{manifest_path} has no containerStoreProbe declaration"
        )
    images = tuple(
        str(item) for item in (probe.get("candidateImages") or ()) if str(item).strip()
    )
    if not images:
        raise LocalRuntimeCapacityError(
            f"{manifest_path} containerStoreProbe declares no candidate image"
        )
    reclaim = payload.get("reclaimCommands")
    return CapacityPolicy(
        thresholds=CapacityThresholds(
            host_free_bytes=int(thresholds["hostFreeBytes"]),
            container_free_bytes=int(thresholds["containerFreeBytes"]),
            post_reclaim_container_free_bytes=int(
                thresholds["postReclaimContainerFreeBytes"]
            ),
        ),
        container_store_probe=ContainerStoreProbeSpec(
            candidate_images=images,
            mount_path=str(probe.get("mountPath") or "/"),
        ),
        reclaim_commands=(
            {str(key): str(value) for key, value in reclaim.items()}
            if isinstance(reclaim, Mapping)
            else {}
        ),
    )


def probe_host_capacity(
    policy: CapacityPolicy,
    *,
    path: str | Path | None = None,
) -> CapacityProbe:
    """观测宿主盘可用空间。"""
    target = Path(path) if path is not None else ROOT
    threshold = policy.threshold_for(HOST_SCOPE)
    try:
        usage = shutil.disk_usage(target)
    except OSError as exc:
        return CapacityProbe(
            scope=HOST_SCOPE,
            threshold_bytes=threshold,
            reclaim_command=policy.reclaim_command_for(HOST_SCOPE),
            absent_reason=f"host disk usage is unreadable: {exc}",
        )
    return CapacityProbe(
        scope=HOST_SCOPE,
        threshold_bytes=threshold,
        free_bytes=int(usage.free),
        total_bytes=int(usage.total),
        reclaim_command=policy.reclaim_command_for(HOST_SCOPE),
    )


def _docker_reclaimable_bytes(runner: Any) -> int | None:
    """从 `docker system df` 求可回收总量；读不出来时返回缺席。"""
    result = runner(
        ["docker", "system", "df", "--format", "json"],
        timeout_seconds=60,
    )
    if getattr(result, "returncode", 1) != 0:
        return None
    total = 0
    seen = False
    for line in str(getattr(result, "stdout", "")).splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            row = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if not isinstance(row, Mapping):
            return None
        try:
            total += parse_docker_size(str(row.get("Reclaimable") or "0B"))
        except LocalRuntimeCapacityError:
            return None
        seen = True
    return total if seen else None


def _local_image_present(runner: Any, image: str) -> bool:
    result = runner(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        timeout_seconds=60,
    )
    return getattr(result, "returncode", 1) == 0


def _parse_df_available_bytes(payload: str) -> tuple[int, int] | None:
    """解析 `df -P -k` 的数据行，返回 (available, total) 字节。"""
    for line in str(payload).splitlines()[1:]:
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            total_kb = int(fields[1])
            available_kb = int(fields[3])
        except ValueError:
            continue
        return available_kb * 1024, total_kb * 1024
    return None


def probe_container_store_capacity(
    policy: CapacityPolicy,
    *,
    runner: Any,
) -> CapacityProbe:
    """观测 Docker 数据盘可用空间。

    只使用本地已存在的候选镜像，绝不为了体检拉镜像；候选全部缺失时返回
    未观测的 probe，让调用方显式报出而不是假装充足。
    """
    threshold = policy.threshold_for(CONTAINER_STORE_SCOPE)
    reclaim_command = policy.reclaim_command_for(CONTAINER_STORE_SCOPE)
    reclaimable = _docker_reclaimable_bytes(runner)
    spec = policy.container_store_probe
    for image in spec.candidate_images:
        if not _local_image_present(runner, image):
            continue
        result = runner(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "df",
                image,
                "-P",
                "-k",
                spec.mount_path,
            ],
            timeout_seconds=120,
        )
        detail = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"
        if getattr(result, "returncode", 1) != 0:
            # Docker 数据盘写满时连一次性容器都起不来，这本身就是耗尽证据。
            if is_disk_exhausted(detail):
                return CapacityProbe(
                    scope=CONTAINER_STORE_SCOPE,
                    threshold_bytes=threshold,
                    free_bytes=0,
                    reclaimable_bytes=reclaimable,
                    reclaim_command=reclaim_command,
                )
            continue
        parsed = _parse_df_available_bytes(str(getattr(result, "stdout", "")))
        if parsed is None:
            continue
        available, total = parsed
        return CapacityProbe(
            scope=CONTAINER_STORE_SCOPE,
            threshold_bytes=threshold,
            free_bytes=available,
            total_bytes=total,
            reclaimable_bytes=reclaimable,
            reclaim_command=reclaim_command,
        )
    return CapacityProbe(
        scope=CONTAINER_STORE_SCOPE,
        threshold_bytes=threshold,
        reclaimable_bytes=reclaimable,
        reclaim_command=reclaim_command,
        absent_reason=(
            "no declared candidate image is present locally: "
            + ", ".join(spec.candidate_images)
        ),
    )


def capacity_preflight_applies(target: Mapping[str, Any]) -> bool:
    """只有在本机容器运行时上执行的 target 才受本地容量水位约束。

    判据取 canonical topology 声明的 `backend`，不枚举 target 名。
    """
    return str(target.get("backend") or "") == "local"


def verify_local_runtime_capacity(
    *,
    runner: Any,
    path: str | Path | None = None,
    policy: CapacityPolicy | None = None,
) -> CapacityReport:
    """对宿主盘与 Docker 数据盘做一次容量前置判定。"""
    resolved = policy if policy is not None else load_capacity_policy()
    return CapacityReport(
        probes=(
            probe_host_capacity(resolved, path=path),
            probe_container_store_capacity(resolved, runner=runner),
        )
    )


NOT_APPLICABLE_EVIDENCE: dict[str, Any] = {
    "status": "not_applicable",
    "blocker": "",
    "issues": [],
    "warnings": [],
    "reclaimCommands": [],
    "evidence": {"status": "not_applicable", "blocker": "", "probes": []},
}


def local_runtime_capacity_evidence(
    target: Mapping[str, Any],
    *,
    runner: Any | None = None,
) -> dict[str, Any]:
    """命令层统一入口：把容量判定摊平成 issues/warnings/证据。

    非本机容器 target 返回 `not_applicable`（未命中，不是通过）。容量声明
    本身不可读时按阻断处理：读不出阈值就无法证明容量足够。
    """
    if not capacity_preflight_applies(target):
        return dict(NOT_APPLICABLE_EVIDENCE)
    if runner is None:
        from quwoquan_ops.cli.lib.common import run as default_runner

        runner = default_runner
    try:
        report = verify_local_runtime_capacity(runner=runner)
    except (LocalRuntimeCapacityError, OSError, RuntimeError, TypeError) as exc:
        return {
            "status": "gate_block",
            "blocker": CAPACITY_BLOCKER,
            "issues": [f"{CAPACITY_BLOCKER}: capacity is unverifiable: {exc}"],
            "warnings": [],
            "reclaimCommands": [],
            "evidence": {
                "status": "gate_block",
                "blocker": CAPACITY_BLOCKER,
                "probes": [],
            },
        }
    return {
        "status": report.status,
        "blocker": report.blocker,
        "issues": report.issues(),
        "warnings": report.warnings(),
        "reclaimCommands": [
            item.reclaim_command
            for item in report.insufficient
            if item.reclaim_command
        ],
        "evidence": report.as_evidence(),
    }
