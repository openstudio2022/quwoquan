"""第一方服务运行探针形态的唯一派生入口。

真相源是各服务自治的 `deploy/base/deployment.yaml`：`livenessProbe` 表达
「进程还活着」，`readinessProbe` 表达「依赖就绪、可以承接流量」。两者路径
不同的服务必须分别探测——只探存活会让依赖断裂被进程存活掩盖（存活 200
而就绪 503），这正是环境静默腐烂的入口。

本模块不维护第二份探针注册表；`quwoquan_ops/gate/verify_service_probe_homology.py`
负责校验该声明与服务端实际注册的路由保持同源。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
SERVICES_ROOT = ROOT / "quwoquan_service/services"
CONTROL_PLANE_DEPLOYMENTS = {
    # platform-ops 是控制面服务，deploy 清单不在 services/ 之下。
    "platform-ops-service": ROOT
    / "quwoquan_service/control-plane/platform-ops/deploy/base/deployment.yaml",
}


@dataclass(frozen=True)
class ServiceProbes:
    """一个第一方服务声明的探针路径集合。"""

    service: str
    liveness: str
    readiness: str
    startup: str

    @property
    def readiness_is_distinct(self) -> bool:
        """就绪探针是否与存活探针指向不同路径。"""
        return self.readiness != self.liveness


def _probe_path(container: dict[str, Any], probe: str, *, source: Path) -> str:
    declared = container.get(probe)
    if not isinstance(declared, dict):
        raise ValueError(f"{source} declares no {probe}")
    http_get = declared.get("httpGet")
    if not isinstance(http_get, dict):
        raise ValueError(f"{source} {probe} is not an httpGet probe")
    path = str(http_get.get("path") or "").strip()
    if not path.startswith("/"):
        raise ValueError(f"{source} {probe} has no absolute path")
    return path


def _service_container(deployment: Path, *, service: str) -> dict[str, Any]:
    documents = [
        document
        for document in yaml.safe_load_all(deployment.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    ]
    for document in documents:
        if document.get("kind") != "Deployment":
            continue
        pod_spec = (
            ((document.get("spec") or {}).get("template") or {}).get("spec") or {}
        )
        for container in pod_spec.get("containers") or []:
            if isinstance(container, dict) and container.get("name") == service:
                return container
    raise ValueError(f"{deployment} has no container named {service}")


def probes_for_service(service: str) -> ServiceProbes:
    """按服务名读取其 deploy 清单声明的探针形态。"""
    deployment = CONTROL_PLANE_DEPLOYMENTS.get(service)
    if deployment is None:
        deployment = SERVICES_ROOT / service / "deploy/base/deployment.yaml"
    if not deployment.is_file():
        raise ValueError(f"first-party service has no deploy manifest: {service}")
    container = _service_container(deployment, service=service)
    return ServiceProbes(
        service=service,
        liveness=_probe_path(container, "livenessProbe", source=deployment),
        readiness=_probe_path(container, "readinessProbe", source=deployment),
        startup=_probe_path(container, "startupProbe", source=deployment),
    )


def service_probe_matrix() -> dict[str, ServiceProbes]:
    """全部第一方服务的探针矩阵，按服务名排序。"""
    matrix: dict[str, ServiceProbes] = {}
    for deployment in sorted(SERVICES_ROOT.glob("*/deploy/base/deployment.yaml")):
        service = deployment.parents[2].name
        matrix[service] = probes_for_service(service)
    for service in sorted(CONTROL_PLANE_DEPLOYMENTS):
        matrix[service] = probes_for_service(service)
    return matrix
