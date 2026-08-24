"""诊断域共享报告 helper（health / inspect / doctor / status 共用）。

从 stackctl.py 逐字迁出健康检查矩阵与候选工作区报告：

- `_health_checks_for_target` 及其角色矩阵子函数：被 `command_health`
  与 `command_inspect`（经 `_metrics_report`）消费；
- `_script_probe_plan_for_target`：同上两域共用的脚本探针计划；
- `_candidate_workspace_report`：被 `command_inspect`（含 `_data_report`）
  与 `command_status` 消费。

端口/拓扑/候选包等基础设施符号（`load_port_manifest` /
`_expected_local_roles` / `_active_provider_runtime` /
`active_deployment_candidate` 等）仍由 stackctl 命名空间拥有（up /
verify / deploy 等留守域共用，且测试经 ``mock.patch.object(stackctl,
...)`` patch 它们），因此函数体内一律经函数内延迟导入 `_stackctl`
属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.read_only_user_availability import (
    read_only_user_availability_report as _read_only_user_availability_report,
    validate_read_only_user_availability_report,
)
from quwoquan_ops.cli.lib.service_runtime_probes import service_probe_matrix


def _diagnostic_aggregation_boundary() -> None:
    """保留 health/inspect/status 共享聚合符号的显式归属。"""




def _script_probe_plan_for_target(
    topology: dict[str, Any],
    target_name: str,
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = _stackctl.get_target(topology, target_name)
    if target_name == "alpha-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "beta-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "prod-sim":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "prod-hosted":
        return [
            {"name": "integration-readonly", "kind": "readonly-http"},
            {"name": "release-state", "kind": "rollout-state"},
        ]
    if str(target.get("env")) == "gamma" and target_name == "gamma-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    return []


def _media_edge_health_url(public_bases: dict[str, Any]) -> str:
    """Probe media-edge root /healthz; never append carrier pathBase (/media/image)."""
    import quwoquan_ops.cli.stackctl as _stackctl

    return f"{_stackctl._public_url_origin(str(public_bases['mediaImage'])).rstrip('/')}/healthz"


PUBLIC_WEB_STATIC_SCOPE = "public-web"

# 恢复面是纯静态资源，必须与 API 平面独立观测：API 全停时 Shell、脚本、
# Service Worker、hosting runtime config 与中文字体仍须 200，否则「使用网页版」
# 这条恢复路径就是断的。
_PUBLIC_WEB_STATIC_PROBES = (
    ("public-web-shell", "/index.html", 200, "text/html"),
    ("public-web-main", "/main.dart.js", 200, ""),
    ("public-web-service-worker", "/flutter_service_worker.js", 200, ""),
    (
        "public-web-runtime-config-trust",
        "/runtime-config-trust.json",
        200,
        "application/json",
    ),
    (
        "public-web-runtime-config-package",
        "/runtime-config-package.json",
        200,
        "application/json",
    ),
    (
        "public-web-font",
        "/assets/assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf",
        200,
        "font/ttf",
    ),
)


def _public_web_static_health_checks(
    public_bases: dict[str, Any],
) -> list[dict[str, Any]]:
    origin = str(public_bases.get("publicWeb") or "").rstrip("/")
    if not origin:
        return []
    checks: list[dict[str, Any]] = []
    for name, path, expected_status, content_type in _PUBLIC_WEB_STATIC_PROBES:
        check: dict[str, Any] = {
            "name": name,
            "scope": PUBLIC_WEB_STATIC_SCOPE,
            "url": f"{origin}{path}",
            "expectedStatus": expected_status,
        }
        if content_type:
            check["expectedContentTypePrefix"] = content_type
        checks.append(check)
    return checks


def _health_checks_for_target(
    topology: dict[str, Any],
    target_name: str,
    scope: str,
    *,
    workload: str | None = None,
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = _stackctl.get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    public_bases = target.get("publicBases") or {}
    checks: list[dict[str, Any]] = []
    edge_probes = service_probe_matrix()
    if scope in {
        "edge",
        "full",
        "content-import",
        "content-consumer",
        "content-commercial",
    }:
        api_base = str(public_bases["api"]).rstrip("/")
        api_edge = edge_probes["api-edge"]
        checks.append(
            {
                "name": "api-health",
                "scope": "edge",
                "url": f"{api_base}{api_edge.liveness}",
            }
        )
        if api_edge.readiness_is_distinct:
            # api-edge 承载 App 全部流量，且声明了独立就绪探针：存活 200
            # 只说明网关进程活着，上游依赖断裂只在就绪端点上可见。
            checks.append(
                {
                    "name": "api-readiness",
                    "scope": "edge",
                    "url": f"{api_base}{api_edge.readiness}",
                }
            )
    if scope in {"edge", "full", "content-commercial"}:
        product_ops_base = str(public_bases["productOps"]).rstrip("/")
        product_ops = edge_probes["product-ops-service"]
        checks.append(
            {
                "name": "product-ops-health",
                "scope": "edge",
                "url": f"{product_ops_base}{product_ops.liveness}",
            }
        )
        if product_ops.readiness_is_distinct:
            checks.append(
                {
                    "name": "product-ops-readiness",
                    "scope": "edge",
                    "url": f"{product_ops_base}{product_ops.readiness}",
                }
            )
    if scope in {
        "media",
        "full",
        "content-import",
        "content-consumer",
        "content-commercial",
    } and "mediaImage" in public_bases:
        checks.append(
            {
                "name": "media-edge-health",
                "scope": "media",
                "url": _stackctl._media_edge_health_url(public_bases),
            }
        )
    if scope in {"edge", "full"} and "publicWeb" in public_bases:
        checks.extend(_public_web_static_health_checks(public_bases))
    if scope in {"service", "full"}:
        checks.extend(_stackctl._service_health_checks_for_target(target_name))
    if scope in {"content-import", "content-consumer", "content-commercial", "full"}:
        plane_workload = (
            "full"
            if scope == "full"
            else (workload or _stackctl._current_runtime_workload(target_name))
        )
        checks.extend(
            _stackctl._content_data_plane_health_checks(
                target_name,
                workload=plane_workload,
            )
        )
    if scope in {"content-consumer", "content-commercial", "full"}:
        checks.extend(_stackctl._content_consumer_health_checks(target_name, public_bases))
    if scope == "content-commercial":
        checks.extend(_stackctl._content_commercial_health_checks(target_name))
    if scope == "full":
        checks.extend(_stackctl._full_scope_health_checks(target_name, public_bases, env_cfg))
    return checks


_CONTENT_DATA_PLANE_ROLES = frozenset(
    {"content-service", "entity-service", "tag-service", "search-service"}
)


def _content_data_plane_health_checks(
    target_name: str,
    *,
    workload: str = "full",
) -> list[dict[str, Any]]:
    """Only probes required by immutable content import and API consumption."""
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        if target_name == "prod-hosted":
            api_base = str((target.get("publicBases") or {}).get("api") or "").rstrip("/")
            if not api_base:
                return []
            # prod edge /healthz is routed directly to content-service.  This is
            # the hosted data-plane liveness proof; local-only loopback ports
            # and SSH management addresses must never become App/public config.
            return [
                {
                    "name": "content-service-public",
                    "scope": "content-import",
                    "url": f"{api_base}/healthz",
                }
            ]
        return []
    manifest = _stackctl.load_port_manifest()
    role_names = [
        role_name
        for role_name in _stackctl._expected_local_roles(target_name, workload=workload)
        if role_name in _stackctl._CONTENT_DATA_PLANE_ROLES
    ]
    checks: list[dict[str, Any]] = []
    for role_name in role_names:
        port = _stackctl.canonical_port(manifest, str(profile_name), role_name)
        checks.append(
            {
                "name": role_name,
                "scope": "content-import",
                "url": f"http://127.0.0.1:{port}/healthz",
            }
        )
    return checks


def _content_consumer_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
) -> list[dict[str, Any]]:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-hosted"}:
        return []
    api_base = str(public_bases.get("api") or "").rstrip("/")
    if not api_base:
        return []
    # Probe the exact default homepage channel route.  An identity=work query is
    # a discovery-browser read, while a bare feed query leaves the App route
    # ambiguous; neither proves that the visible Recommend tab can assemble a
    # ranked page.
    feed_url = (
        f"{api_base}/content/feed?sort=recommend&channelId=recommend&limit=1"
        "&sessionId=stackctl-content-consumer-health"
    )
    return [
        {"name": "app-config", "scope": "content-consumer", "url": f"{api_base}/config/app"},
        {"name": "content-feed", "scope": "content-consumer", "url": feed_url},
    ]


def _content_commercial_health_checks(target_name: str) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        return []
    target = _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
    profile_name = str(target.get("portProfile") or "")
    if not profile_name:
        return []
    port = _stackctl.canonical_port(
        _stackctl.load_port_manifest(), profile_name, "product-ops-service"
    )
    return [
        {
            "name": "product-ops-service",
            "scope": "content-commercial",
            "url": f"http://127.0.0.1:{port}/healthz",
        }
    ]


def _service_health_checks_for_target(target_name: str) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    env_name = str(target["env"])
    mock_flags = (topology["environments"][env_name].get("mockBoundaryFlags") or {})
    if mock_flags.get("servicePlane"):
        return [
            {
                "name": "service-plane-mocked",
                "scope": "service",
                "url": "",
                "skip": True,
                "reason": "service plane is mocked in this target",
            }
        ]
    profile_name = target.get("portProfile")
    if not profile_name:
        return []
    manifest = _stackctl.load_port_manifest()
    checks: list[dict[str, Any]] = []
    provider_roles: set[str] = set()
    if target_name in {"alpha-local", "beta-local", "gamma-local"}:
        provider_runtime = _stackctl._active_provider_runtime(env_name, target_name)
        provider_roles = {
            str(workload["role"])
            for workload in provider_runtime["composition"]["workloads"]
        }
    non_service_paths = {
        "realtime-gateway": "/healthz",
        "livekit-http": "/",
        "livekit-metrics": "/metrics",
    }
    probe_matrix = service_probe_matrix()

    def _probe_check(name: str, role: str, port: int, path: str) -> dict[str, Any]:
        check: dict[str, Any] = {
            "name": name,
            "scope": "service",
            "url": f"http://127.0.0.1:{port}{path}",
            # service-core 虚拟 HTTP 路由按 Host 头分发合并模块;独立监听的
            # 服务忽略该头,因此对全部 service 角色统一携带服务名 Host。
            "headers": {"Host": role},
        }
        if role in provider_roles:
            check["url"] = f"https://127.0.0.1:{port}{path}"
            try:
                check["caFile"] = str(_stackctl.root_certificate_path(target_name))
            except _stackctl.PublicDomainTlsError:
                check["caFile"] = ""
        return check

    for role_name in _stackctl._expected_local_roles(target_name):
        if (
            not role_name.endswith("-service")
            and role_name not in non_service_paths
            and role_name not in provider_roles
        ):
            continue
        port = _stackctl.canonical_port(manifest, str(profile_name), role_name)
        # 第一方服务的探针形态由其 deploy 清单声明；Provider 与外部
        # workload 不拥有该声明，沿用本地拓扑的固定路径。
        probes = probe_matrix.get(role_name)
        liveness_path = (
            probes.liveness
            if probes is not None
            else non_service_paths.get(role_name, "/healthz")
        )
        checks.append(_probe_check(role_name, role_name, port, liveness_path))
        if probes is not None and probes.readiness_is_distinct:
            # 存活与就绪独立上报：进程活着但依赖断裂时，失败必须能定位到
            # 具体服务的就绪端点，而不是被存活探针的 200 掩盖。
            checks.append(
                _probe_check(
                    f"{role_name}-readiness",
                    role_name,
                    port,
                    probes.readiness,
                )
            )
    return checks


def _full_scope_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
    env_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    checks: list[dict[str, Any]] = []
    env_name = str(env_cfg.get("artifactPolicy", {}).get("app", {}).get("runtimeEnv", ""))
    if target_name == "beta-local":
        notification_port = _stackctl.canonical_port(
            _stackctl.load_port_manifest(),
            "beta-local",
            "notification-service",
        )
        checks.append(
            {
                "name": "app-config",
                "scope": "full",
                "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
            }
        )
        # 全量探针只能打 contract_graph 里 anonymous_policy=allow 的路由:
        # /chat/contacts 与 /content/intersections* 均为 auth_mode=required 的
        # private 路由,匿名探针必然 401,不能作为健康信号。
        # Ranked feeds require sessionId; bare /content/feed is
        # CONTENT.USER.invalid_argument.
        beta_feed_smoke = (
            f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1"
            "&sessionId=stackctl-beta-route-smoke"
        )
        checks.extend(
            [
                {
                    "name": "content-feed",
                    "scope": "full",
                    "url": beta_feed_smoke,
                },
                {
                    "name": "notification-service-health",
                    "scope": "full",
                    "url": f"http://127.0.0.1:{notification_port}/healthz",
                    # 与 service 域探针同源:service-core 的虚拟 HTTP 路由按 Host
                    # 头分发合并模块,缺该头会被投递到错误模块。
                    "headers": {"Host": "notification-service"},
                },
            ]
        )
    elif target_name == "gamma-local":
        # Ranked feeds require sessionId; bare ?limit=1 is CONTENT.USER.invalid_argument.
        gamma_feed_smoke = (
            f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1"
            "&sessionId=stackctl-gamma-route-smoke"
        )
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
                },
                {
                    "name": "gamma-route-smoke",
                    "scope": "full",
                    "url": gamma_feed_smoke,
                },
                {
                    "name": "tag-public-catalog-smoke",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/tag/resolve?tagRef=Topic%2F%E6%97%85%E8%A1%8C"
                    ),
                },
            ]
        )
    elif target_name == "prod-sim":
        # Keep sessionId parity with content-consumer / gamma full probes.
        prod_sim_feed_smoke = (
            f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1"
            "&sessionId=stackctl-prod-sim-route-smoke"
        )
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
                },
                {
                    "name": "prod-sim-route-smoke",
                    "scope": "full",
                    "url": prod_sim_feed_smoke,
                },
            ]
        )
    return checks


def _candidate_workspace_report(
    target_name: str,
    *,
    purpose: str = "self_verify",
) -> dict[str, Any]:
    """Self-verify candidate bytes; current source comparison is explicit."""
    import quwoquan_ops.cli.stackctl as _stackctl

    report: dict[str, Any] = {
        "status": "unavailable",
        "purpose": purpose,
        "selfVerified": False,
        "currentSourceClaim": "not_evaluated",
        "nonPromotable": None,
        "drifted": None,
        "candidate": None,
        "current": None,
        "mismatchedFields": [],
        "issues": [],
        "warnings": [],
    }
    if purpose not in {"self_verify", "currentness"}:
        report["issues"] = ["candidate validation purpose is invalid"]
        return report
    try:
        topology = _stackctl.load_environment_topology()
        environment = str(_stackctl.get_target(topology, target_name).get("env") or "")
        active = _stackctl.active_deployment_candidate(target_name)
        if active is None:
            report.update(
                {
                    "status": "no_active_candidate",
                    "drifted": True,
                    "issues": [f"no active immutable candidate for {target_name}"],
                }
            )
            return report
        candidate_root = Path(str(active["candidateDir"]))
        self_verified, self_verify_detail = _stackctl.can_reuse_package(
            environment,
            target_name,
            include_services=True,
            purpose="self_verify",
            candidate_root=candidate_root,
        )
        if not self_verified:
            raise ValueError(self_verify_detail)
        candidate = _stackctl.load_candidate_manifest(
            environment,
            target_name,
            str(active["baselineId"]),
            require_full=True,
            purpose="self_verify",
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        report["issues"] = ["candidate self-verify is unavailable: " + str(exc)]
        return report

    candidate_identity = {
        "baselineId": candidate.get("baselineId"),
        "sourceRevision": candidate.get("sourceRevision"),
        "workspaceStatusDigest": candidate.get("workspaceStatusDigest"),
        "deploymentInputDigest": candidate.get("workspaceDigest"),
    }
    status = "self_verified"
    current_source_claim = "not_evaluated"
    non_promotable: bool | None = None
    drifted: bool | None = None
    current_identity: dict[str, Any] | None = None
    mismatched: list[str] = []
    warnings: list[str] = []
    if purpose == "currentness":
        current, detail = _stackctl.can_reuse_package(
            environment,
            target_name,
            include_services=True,
            purpose="currentness",
            candidate_root=candidate_root,
        )
        status = "current" if current else "drifted"
        current_source_claim = status
        non_promotable = not current
        drifted = not current
        current_identity = {"detail": detail}
        if not current:
            mismatched = ["deploymentInputClosure"]
            warnings.append(detail)
    report.update(
        {
            "status": status,
            "selfVerified": True,
            "currentSourceClaim": current_source_claim,
            "nonPromotable": non_promotable,
            "drifted": drifted,
            "candidate": candidate_identity,
            "current": current_identity,
            "mismatchedFields": mismatched,
            "warnings": warnings,
        }
    )
    return report
