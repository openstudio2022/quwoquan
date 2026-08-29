#!/usr/bin/env python3
"""服务端就绪路由 ↔ deploy 探针声明同源门禁。

一个服务注册了独立的 `/readyz` 深探针，就说明它自己认为「进程活着」与
「依赖就绪」是两件事。此时 `deploy/base/deployment.yaml` 的 `readinessProbe`
必须指向 `/readyz`：否则 Kubernetes 与 `stackctl health` 都会用浅存活探针
判定就绪，依赖断裂时仍然报绿——环境静默腐烂就是这样发生的。

真相源是两侧的实际代码（Go 路由注册 + deploy 清单），实时扫描派生，
不建立第二份探针注册表。

服务可以自己注册 `/readyz`，也可以由 `servicekit.Bootstrap` 统一挂载——后者
是骨架契约（`runtime/servicekit` 的白盒测试断言 `/healthz`、`/readyz`、
`/metrics` 恒在），因此调用 `servicekit.Bootstrap(` 与自行注册路由等价。

校验规则（双向）：
1. 注册了 `/readyz` 的服务，其 `readinessProbe` 必须是 `/readyz`。
2. 未注册 `/readyz` 的服务，其 `readinessProbe` 不得声明 `/readyz`（否则
   探针必然 404，把不可用伪装成可用或反之）。
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.service_runtime_probes import (  # noqa: E402
    CONTROL_PLANE_DEPLOYMENTS,
    SERVICES_ROOT,
    service_probe_matrix,
)

READINESS_PATH = "/readyz"
_READYZ_ROUTE = re.compile(r'Handle(?:Func)?\(\s*"(?:GET\s+)?/readyz"')
# 骨架装配等价于自行注册探针三件套；语义由 servicekit 白盒测试锁定。
_SERVICEKIT_BOOTSTRAP = re.compile(r"servicekit\.Bootstrap\(")


def _service_source_roots() -> dict[str, list[Path]]:
    """服务名 → 需要扫描路由注册的 Go 源码根目录。"""
    roots: dict[str, list[Path]] = {}
    for deployment in sorted(SERVICES_ROOT.glob("*/deploy/base/deployment.yaml")):
        service = deployment.parents[2].name
        roots[service] = [SERVICES_ROOT / service]
    for service, deployment in CONTROL_PLANE_DEPLOYMENTS.items():
        roots[service] = [deployment.parents[2]]
    return roots


def services_registering_readiness_route() -> set[str]:
    """暴露独立 `/readyz` 路由的服务集合（排除测试树）。

    命中任一即算暴露：服务自己注册该路由，或经 `servicekit.Bootstrap` 装配。
    """
    registered: set[str] = set()
    for service, roots in _service_source_roots().items():
        for root in roots:
            for source in root.rglob("*.go"):
                if "/tests/" in source.as_posix():
                    continue
                text = source.read_text(encoding="utf-8")
                if _READYZ_ROUTE.search(text) or _SERVICEKIT_BOOTSTRAP.search(text):
                    registered.add(service)
                    break
            if service in registered:
                break
    return registered


def main() -> int:
    errors: list[str] = []
    matrix = service_probe_matrix()
    registered = services_registering_readiness_route()
    for service, probes in sorted(matrix.items()):
        declares_readiness = probes.readiness == READINESS_PATH
        if service in registered and not declares_readiness:
            errors.append(
                f"{service} registers {READINESS_PATH} but its readinessProbe is "
                f"{probes.readiness}; readiness would be judged by the liveness probe"
            )
        if service not in registered and declares_readiness:
            errors.append(
                f"{service} declares readinessProbe {READINESS_PATH} but registers "
                "no such route; the probe can only 404"
            )
    if errors:
        print("FAIL: service probe homology")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: service probe homology")
    print(
        f"  - {len(matrix)} first-party services checked, "
        f"{len(registered)} expose a distinct readiness route"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
