"""prod plane 数据面接线：把服务的存储 scene 接到本平面的实例上。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .constants import EXTERNAL_DATA_HOST
from .package_inputs import _prevalidation_spec


def _runtime_network_name(plane: str, instance: str, replica: str) -> str:
    if plane not in {"service", "edge"} or instance not in {"prod", "gray", "prevalidate"} or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", replica):
        raise SystemExit("GATE_BLOCK: invalid runtime network identity")
    return f"quwoquan-{plane}-{instance}-{replica}"


def _prevalidation_port_bindings() -> list[dict[str, Any]]:
    """渲染/前检共同消费 manifest 的发布口，拒绝歧义和 image-only 暴露。"""
    spec = _prevalidation_spec()
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for plane, projection in spec["planes"].items():
        enabled = set(projection["startupServices"])
        if plane == "service":
            enabled.update(spec["isolatedData"]["services"])
            enabled.add("gamma-proxy")
        for binding in projection.get("publishedPorts", []):
            service = binding["service"]
            target, published = binding["target"], binding["published"]
            if (
                service not in enabled
                or type(target) is not int or not 1 <= target <= 65535
                or type(published) is not int or not 1024 <= published <= 65535
                or published in seen
            ):
                raise SystemExit(f"GATE_BLOCK: invalid prevalidation publishedPorts: {service}")
            seen.add(published)
            result.append({**binding, "plane": plane})
    return result


def _prevalidation_host_port(service: str, target: int | None = None) -> int:
    matches = [
        item["published"] for item in _prevalidation_port_bindings()
        if item["service"] == service and (target is None or item["target"] == target)
    ]
    if len(matches) != 1:
        raise SystemExit(f"GATE_BLOCK: no unique prevalidation port for {service}")
    return matches[0]


def _rewrite_prevalidation_urls(value: Any, selected: set[str]) -> Any:
    """仅按 manifest 服务身份重写第一方跨 plane origin，保留路径与 query。"""
    bindings = {item["service"]: item for item in _prevalidation_port_bindings()
                if item["service"] != "gamma-proxy"}
    if isinstance(value, dict):
        return {key: _rewrite_prevalidation_urls(item, selected) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_prevalidation_urls(item, selected) for item in value]
    if not isinstance(value, str) or not value.startswith(("http://", "https://", "ws://", "wss://")):
        return value
    parsed = urlsplit(value)
    binding = bindings.get(parsed.hostname or "")
    if binding is None:
        return value
    host = binding["service"] if binding["service"] in selected else EXTERNAL_DATA_HOST
    port = binding["target"] if binding["service"] in selected else binding["published"]
    return urlunsplit((parsed.scheme, f"{host}:{port}", parsed.path, parsed.query, parsed.fragment))


def _validate_prevalidation_startup(startup_services: set[str]) -> None:
    """不靠裁剪 depends_on 把正式 OTP/mTLS 未实现伪装为可启动。"""
    for service, dependencies in _prevalidation_spec().get("startupDependencies", {}).items():
        if service not in startup_services:
            continue
        missing = set(dependencies) - startup_services
        if missing:
            raise SystemExit(
                f"GATE_BLOCK: prevalidation {service} startup dependency unavailable: "
                + ", ".join(sorted(missing))
                + "; formal integration OTP/mTLS must be provisioned, not placeholder credentials"
            )


def _wire_redis_scene(
    environment: dict[str, Any],
    key_root: str,
    addr: str,
) -> None:
    """把一个 Redis scene 接到 prod plane 的明文单点 Redis 上。

    地址、物理组网与传输安全必须成套注入，因此它们只有这一个写入口。环境快照
    描述的是云上 prod 的组网（多数 scene 声明 `mode: cluster` / `tls: true`），
    而本平面只有一个明文单点实例；只注入地址而漏掉组网降档会让单点地址被当成
    集群种子——`addrs` 为空，servicekit 在装配期直接判否，服务起不来；漏掉 TLS
    降档则是按 TLS 握手连明文端口，只表现为依赖超时而不是配置错误。
    """
    environment[f"{key_root}_ADDR"] = addr
    environment[f"{key_root}_MODE"] = "standalone"
    environment[f"{key_root}_TLS"] = "false"
