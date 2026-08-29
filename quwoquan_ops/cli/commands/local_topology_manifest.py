"""stackctl 本地拓扑与端口 manifest 域: beta/gamma env 派生、
端口占用报告与本地角色期望。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_all_services` / `_public_url_origin`、`_beta_env_from_port_manifest` /
`_gamma_env_from_port_manifest`、`_formal_release_compose_project_name`、
`_current_runtime_workload`、`_network_report` /
`_canonical_port_occupancy_report` / `_project_target_runtime_owned_ports` /
`_runtime_owned_port_occupancy_report` / `_other_local_target_port_blocks`、
`_expected_local_roles`、`_scoped_process_environment`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import contextlib
import errno
import os
import socket
import time
import urllib
import urllib.error
import urllib.parse
import urllib.request

from collections.abc import Callable
from collections.abc import Sequence
from typing import Any
from typing import Mapping


def _all_services() -> list[str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    return list(_stackctl.first_party_service_names(_stackctl.ROOT))


def _public_url_origin(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme not in {"https", "wss"} or not parsed.netloc:
        raise RuntimeError(f"GATE_BLOCK: invalid public URL projection: {raw_url!r}")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _beta_env_from_port_manifest(
    topology: dict[str, Any],
    target_name: str,
) -> dict[str, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    manifest = _stackctl.load_port_manifest()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    port_profile = str(target.get("portProfile") or "")
    if not port_profile:
        raise RuntimeError(f"GATE_BLOCK: {target_name} lacks a port profile")
    build_images = target.get("buildImages")
    if not isinstance(build_images, dict):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name}.buildImages policy must be an object"
        )

    def required_build_image(name: str) -> str:
        value = build_images.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"GATE_BLOCK: {target_name}.buildImages.{name} must be a non-empty string"
            )
        return value.strip()

    ports = _stackctl.profile_ports(manifest, port_profile)
    return {
        "GATEWAY_PORT": str(ports["api-edge"]),
        "PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "OPS_PORTAL_PORT": str(ports["ops-portal"]),
        "MEDIA_PORT": str(ports["media-edge"]),
        "ASSISTANT_PORT": str(ports["assistant-service"]),
        "CHAT_PORT": str(ports["chat-service"]),
        "QWQ_COMPOSE_GO_BASE_IMAGE": required_build_image("goBaseImage"),
        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": required_build_image("alpineBaseImage"),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL": str(public_bases["publicWeb"]),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL": _stackctl._public_url_origin(
            str(public_bases["mediaImage"])
        ),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
    }


def _formal_release_compose_project_name(target_name: str) -> str:
    import quwoquan_ops.cli.stackctl as _stackctl

    return _stackctl.formal_release_compose_project_name(
        target_name,
        run_id=os.environ.get("GITHUB_RUN_ID", ""),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    )


def _gamma_env_from_port_manifest(
    topology: dict[str, Any],
    target_name: str,
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Project any Alpha/Beta/Gamma local target into the shared OCI runtime."""
    import quwoquan_ops.cli.stackctl as _stackctl

    resolved_manifest = (
        manifest if manifest is not None else _stackctl.load_port_manifest()
    )
    profile_name = str(_stackctl.get_target(topology, target_name).get("portProfile"))
    ports = _stackctl.profile_ports(resolved_manifest, profile_name)
    target = _stackctl.get_target(topology, target_name)
    environment_name = str(target["env"])
    if environment_name not in {"alpha", "beta", "gamma"}:
        raise RuntimeError(
            f"GATE_BLOCK: shared local release runtime does not support {target_name}"
        )
    public_bases = target.get("publicBases") or {}
    def public_host(name: str, *, schemes: set[str]) -> str:
        parsed = urllib.parse.urlsplit(str(public_bases.get(name) or ""))
        if parsed.scheme not in schemes or not parsed.hostname:
            raise RuntimeError(
                f"GATE_BLOCK: {target_name} publicBases.{name} has no canonical host"
            )
        return parsed.hostname
    startup = target.get("startup")
    if not isinstance(startup, dict):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name} startup policy must be an object"
        )
    build_images = target.get("buildImages")
    if not isinstance(build_images, dict):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name} buildImages policy must be an object"
        )

    def required_positive_seconds(name: str) -> str:
        value = startup.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RuntimeError(
                f"GATE_BLOCK: {target_name}.startup.{name} must be a positive integer"
            )
        return str(value)

    def required_build_image(name: str) -> str:
        value = build_images.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"GATE_BLOCK: {target_name}.buildImages.{name} must be a non-empty string"
            )
        return value.strip()

    environment = {
        # Every first-party service builds from the same large Go module
        # context.  Colima's SSHFS source session can lose a sibling file when
        # Compose asks BuildKit to upload that context many times in parallel
        # (observed as alternating go.mod/go.sum checksum misses).  Test-live
        # favors a deterministic current-worktree build over parallelism.
        "COMPOSE_PARALLEL_LIMIT": "1",
        # Compose fragments may persist rebuildable runtime logs and reports,
        # but mutable test-live must still bind them to the one canonical
        # repository output tree instead of relying on the caller shell.
        "QWQ_OUTPUT_ROOT": str(_stackctl.output_root().expanduser().resolve()),
        "LOCAL_GAMMA_HTTP_PORT": str(ports["api-edge"]),
        "LOCAL_GAMMA_PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "LOCAL_GAMMA_PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "LOCAL_GAMMA_MEDIA_EDGE_PORT": str(ports["media-edge"]),
        "LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
        "LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL": str(public_bases["mediaVideo"]),
        "LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "CONTENT_MEDIA_DELIVERY_BASE_URL": _stackctl._public_url_origin(
            str(public_bases["mediaImage"])
        ),
        "CONTENT_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL": _stackctl._public_url_origin(
            str(public_bases["mediaImage"])
        ),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL": str(public_bases["rtc"]),
        "LOCAL_GAMMA_CONTENT_PORT": str(ports["content-service"]),
        "LOCAL_GAMMA_CHAT_PORT": str(ports["chat-service"]),
        "LOCAL_GAMMA_USER_PORT": str(ports["user-service"]),
        "LOCAL_GAMMA_ASSISTANT_PORT": str(ports["assistant-service"]),
        "LOCAL_GAMMA_ENTITY_PORT": str(ports["entity-service"]),
        "LOCAL_GAMMA_CIRCLE_PORT": str(ports["circle-service"]),
        "LOCAL_GAMMA_INTEGRATION_PORT": str(ports["integration-service"]),
        "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT": str(
            ports["sms-provider-substitute"]
        ),
        "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_PORT": str(
            ports["provider-protocol-substitute"]
        ),
        "LOCAL_GAMMA_NOTIFICATION_PORT": str(ports["notification-service"]),
        "LOCAL_GAMMA_REALTIME_PORT": str(ports["realtime-gateway"]),
        "LOCAL_GAMMA_RTC_PORT": str(ports["rtc-service"]),
        "LOCAL_GAMMA_REC_MODEL_PORT": str(ports["recommendation-service"]),
        "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT": str(ports["product-ops-service"]),
        "LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT": str(ports["platform-ops-service"]),
        "LOCAL_GAMMA_TAG_PORT": str(ports["tag-service"]),
        "LOCAL_GAMMA_SEARCH_PORT": str(ports["search-service"]),
        "LOCAL_GAMMA_MONGO_PORT": str(ports["mongodb"]),
        "LOCAL_GAMMA_REDIS_PORT": str(ports["redis"]),
        "LOCAL_GAMMA_POSTGRES_PORT": str(ports["postgres"]),
        "QWQ_COMPOSE_ELASTICSEARCH_PORT": str(ports["elasticsearch"]),
        "LOCAL_GAMMA_ADMIN_PORT": str(ports["caddy-admin"]),
        "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": str(ports["object-storage-edge"]),
        "LOCAL_GAMMA_MEDIA_ORIGIN_PORT": str(ports["media-origin"]),
        "LOCAL_GAMMA_LIVEKIT_HTTP_PORT": str(ports["livekit-http"]),
        "LOCAL_GAMMA_LIVEKIT_RTC_TCP_PORT": str(ports["livekit-rtc-tcp"]),
        "LOCAL_GAMMA_LIVEKIT_RTC_UDP_PORT": str(ports["livekit-rtc-udp"]),
        "LOCAL_GAMMA_LIVEKIT_METRICS_PORT": str(ports["livekit-metrics"]),
        "LOCAL_GAMMA_TURN_TCP_PORT": str(ports["coturn"]),
        "LOCAL_GAMMA_TURN_UDP_PORT": str(ports["coturn"]),
        "LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS": required_positive_seconds(
            "dockerProbeTimeoutSeconds"
        ),
        "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": required_positive_seconds(
            "composeBuildTimeoutSeconds"
        ),
        "LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS": required_positive_seconds(
            "composeBuildNoProgressTimeoutSeconds"
        ),
        "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": required_positive_seconds(
            "composeUpTimeoutSeconds"
        ),
        "LOCAL_GAMMA_GO_BASE_IMAGE": required_build_image("goBaseImage"),
        "LOCAL_GAMMA_ALPINE_BASE_IMAGE": required_build_image("alpineBaseImage"),
        # 服务 deploy/compose.yaml 的 build args 统一引用 QWQ_COMPOSE_* 键;
        # package 路径直接 docker build 时必须携带同一批值。
        "QWQ_COMPOSE_GO_BASE_IMAGE": required_build_image("goBaseImage"),
        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": required_build_image("alpineBaseImage"),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL": str(public_bases["publicWeb"]),
        "QWQ_PUBLIC_API_HOST": public_host("api", schemes={"https"}),
        "QWQ_PUBLIC_WEB_HOST": public_host("publicWeb", schemes={"https"}),
        "QWQ_PUBLIC_RTC_HOST": public_host("rtc", schemes={"wss"}),
        "QWQ_PUBLIC_OPS_HOST": public_host("productOps", schemes={"https"}),
        "QWQ_PUBLIC_CDN_HOST": public_host("mediaImage", schemes={"https"}),
        "QWQ_PUBLIC_UPLOAD_HOST": public_host("mediaUpload", schemes={"https"}),
        "QWQ_LOCAL_PUBLIC_UPLOAD_HOST": public_host(
            "mediaUpload", schemes={"https"}
        ),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
        "QWQ_LOCAL_RELEASE_ENV": environment_name,
        "QWQ_LOCAL_RELEASE_TARGET": target_name,
        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": _stackctl._formal_release_compose_project_name(
            target_name
        ),
    }
    return environment


def _current_runtime_workload(target_name: str) -> str:
    """Map the active local runtime slice to an expected-role workload."""
    import quwoquan_ops.cli.stackctl as _stackctl


    scope = _stackctl._current_runtime_health_scope(target_name)
    if scope in {
        "content-import",
        "content-consumer",
    }:
        return "content-release"
    if scope == "content-commercial":
        return "content-commercial"
    return "full"


def socket_probe(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.2)
            result = sock.connect_ex(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(
            f"TCP port probe failed for 127.0.0.1:{port}: {exc}"
        ) from exc
    if result == 0:
        return True
    if result == errno.ECONNREFUSED:
        return False
    raise RuntimeError(
        "TCP port probe failed for "
        f"127.0.0.1:{port}: {os.strerror(result)} (errno={result})"
    )


def _wait_for_network_ports_released(
    target_name: str,
    *,
    timeout_seconds: float = 45.0,
    poll_interval_seconds: float = 0.5,
    port_reporter: Callable[[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Wait for target-owned host forwards to converge after compose down.

    Docker Desktop/Colima can remove containers before its host forwarding
    process closes the corresponding listening sockets. A single immediate
    probe therefore creates a false cleanup failure. The bounded wait keeps
    the fail-closed resource-release contract without restarting or otherwise
    mutating the shared container runtime.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    deadline = time.monotonic() + timeout_seconds
    reporter = port_reporter or _stackctl._network_report
    while True:
        occupied = [
            item for item in reporter(target_name)["ports"] if item["open"]
        ]
        if not occupied or time.monotonic() >= deadline:
            return occupied
        time.sleep(poll_interval_seconds)


def _published_endpoint_identity(
    endpoint: Mapping[str, object],
) -> tuple[str, int, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if not isinstance(endpoint, Mapping):
        raise ValueError("runtime published endpoint must be an object")
    role = str(endpoint.get("role") or "").strip()
    protocol = str(endpoint.get("protocol") or "").strip().lower()
    host_port = _stackctl.require_published_endpoint_port(
        [endpoint],
        role=role,
        protocol=protocol,
    )
    return role, host_port, protocol


def _published_endpoint_is_occupied(endpoint: Mapping[str, object]) -> bool:
    import quwoquan_ops.cli.stackctl as _stackctl

    role, host_port, protocol = _published_endpoint_identity(endpoint)
    if protocol == "tcp":
        try:
            return _stackctl.socket_probe(host_port)
        except RuntimeError as exc:
            raise RuntimeError(
                "TCP published endpoint probe failed for "
                f"{role}:{host_port}/{protocol}: {exc}"
            ) from exc
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", host_port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            return True
        raise RuntimeError(
            "UDP published endpoint probe failed for "
            f"{role}:{host_port}/{protocol}: {exc}"
        ) from exc
    return False


def _wait_for_published_endpoints_released(
    published_endpoints: Sequence[Mapping[str, object]],
    *,
    timeout_seconds: float = 45.0,
    poll_interval_seconds: float = 0.5,
) -> list[dict[str, object]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        isinstance(published_endpoints, (str, bytes, bytearray, Mapping))
        or not isinstance(published_endpoints, Sequence)
        or not published_endpoints
    ):
        raise ValueError("runtime published endpoint ownership is required")
    normalized: list[dict[str, object]] = []
    identities: set[tuple[str, int, str]] = set()
    for endpoint in published_endpoints:
        identity = _published_endpoint_identity(endpoint)
        if identity in identities:
            raise ValueError("runtime published endpoint identities must be distinct")
        identities.add(identity)
        normalized.append(
            {
                "role": identity[0],
                "hostPort": identity[1],
                "protocol": identity[2],
            }
        )
    deadline = time.monotonic() + timeout_seconds
    while True:
        occupied = [
            endpoint
            for endpoint in normalized
            if _stackctl._published_endpoint_is_occupied(endpoint)
        ]
        if not occupied or time.monotonic() >= deadline:
            return occupied
        time.sleep(poll_interval_seconds)


def _network_report(target_name: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        public_bases = target.get("publicBases") or {}
        endpoints = [
            {"name": name, "url": value}
            for name, value in public_bases.items()
            if isinstance(value, str) and value.strip()
        ]
        return {
            "profile": "",
            "ports": [],
            "publicEndpoints": endpoints,
        }
    manifest = _stackctl.load_port_manifest()
    ports = []
    for role in _stackctl._expected_local_roles(target_name):
        if role not in manifest["roles"]:
            continue
        port = _stackctl.canonical_port(manifest, profile_name, role)
        ports.append({"name": role, "port": port, "open": _stackctl.socket_probe(port)})
    return {
        "profile": profile_name,
        "ports": ports,
        "publicEndpoints": [],
    }


def _canonical_port_occupancy_report(target_name: str) -> dict[str, Any]:
    """Inspect the complete canonical target block without trusting runtime state."""
    import quwoquan_ops.cli.stackctl as _stackctl


    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    profile_name = str(target.get("portProfile") or "").strip()
    if not profile_name:
        return {"profile": "", "ports": [], "publicEndpoints": []}
    manifest = _stackctl.load_port_manifest()
    ports = [
        {"name": role, "port": port, "open": _stackctl.socket_probe(port)}
        for role, port in _stackctl.profile_ports(manifest, profile_name).items()
    ]
    return {"profile": profile_name, "ports": ports, "publicEndpoints": []}


def _project_target_runtime_owned_ports(
    target_name: str,
    *,
    published_ports: Sequence[Mapping[str, object]] | None = None,
    topology: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    resolved_topology = topology if topology is not None else _stackctl.load_environment_topology()
    target = _stackctl.get_target(resolved_topology, target_name)
    profile_name = str(target.get("portProfile") or "").strip()
    if not profile_name:
        raise ValueError(f"{target_name} runtime port profile is required")
    resolved_manifest = manifest if manifest is not None else _stackctl.load_port_manifest()
    return _stackctl.project_runtime_owned_ports(
        port_profile=profile_name,
        published_ports=published_ports,
        manifest=resolved_manifest,
    )


def _runtime_owned_port_occupancy_report(
    target_name: str,
    *,
    published_ports: Sequence[Mapping[str, object]] | None = None,
    topology: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    resolved_topology = topology if topology is not None else _stackctl.load_environment_topology()
    target = _stackctl.get_target(resolved_topology, target_name)
    profile_name = str(target.get("portProfile") or "").strip()
    resolved_manifest = manifest if manifest is not None else _stackctl.load_port_manifest()
    owned_ports = _stackctl._project_target_runtime_owned_ports(
        target_name,
        published_ports=published_ports,
        topology=resolved_topology,
        manifest=resolved_manifest,
    )
    return {
        "profile": profile_name,
        "publishedEndpoints": [
            {
                **endpoint,
                "open": _stackctl._published_endpoint_is_occupied(endpoint),
            }
            for endpoint in owned_ports
        ],
        "publicEndpoints": [],
    }


def _other_local_target_port_blocks(target_name: str) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        raise ValueError(f"local target port blocks do not support {target_name!r}")
    manifest = _stackctl.load_port_manifest()
    blocks: list[dict[str, Any]] = []
    for candidate in ("alpha-local", "beta-local", "gamma-local"):
        if candidate == target_name:
            continue
        profile = manifest.get("profiles", {}).get(candidate)
        if not isinstance(profile, dict):
            raise ValueError(f"canonical port block is missing for {candidate}")
        blocks.append(
            {
                "target": candidate,
                "blockStart": int(profile["blockStart"]),
                "blockEnd": int(profile["blockEnd"]),
            }
        )
    return blocks


def _expected_local_roles(
    target_name: str,
    *,
    workload: str = "full",
) -> list[str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if workload in {"content-release", "content-commercial"} and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        # content-release 启动的就是这条 consumer data plane；不能要求
        # assistant/chat/Ops 等 full workload 才会启动的端口，否则集成验证
        # 会错误重启已经健康的发布环境。
        roles = [
            "api-edge",
            "media-edge",
            "media-origin",
            "content-service",
            "user-service",
            "entity-service",
        ]
        if workload == "content-commercial":
            roles.extend(
                [
                    "product-ops-edge",
                    "product-ops-service",
                    "recommendation-service",
                ]
            )
        return roles
    # Alpha/Beta/Gamma share one packaged Remote composition.  A target must
    # never look healthy merely because its historical, smaller role subset is
    # listening; the full gate is identical across all three physical stacks.
    full_local_roles = [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "object-storage-edge",
            "chat-service",
            "user-service",
            "content-service",
            "assistant-service",
            "recommendation-service",
            "product-ops-service",
            "platform-ops-service",
            "tag-service",
            "search-service",
            "entity-service",
            "circle-service",
            "integration-service",
            "notification-service",
            "realtime-gateway",
            "rtc-service",
            "livekit-http",
            "livekit-rtc-tcp",
            "livekit-metrics",
            "coturn",
            "postgres",
            "mongodb",
            "redis",
            "elasticsearch",
    ]
    if target_name in {"alpha-local", "beta-local", "gamma-local"}:
        environment_name = target_name.removesuffix("-local")
        provider_runtime = _stackctl._active_provider_runtime(environment_name, target_name)
        expected_digest = str(
            provider_runtime["composition"]["runtimeCompositionDigest"]
        )

        def _startup_identity_current(candidate: object) -> bool:
            return (
                isinstance(candidate, dict)
                and candidate.get("status") == "running"
                and candidate.get("workload") == "full"
                and candidate.get("providerRuntimeDigest") == expected_digest
            )

        def _startup_is_running(candidate: object) -> bool:
            return isinstance(candidate, dict) and candidate.get("status") == "running"

        # release 栈与 mutable test-live 栈各自持有 startup receipt，同一 target 同时
        # 只能有一个 running。互斥由 up/dev-session 保证，但保证不等于事实：两份都
        # running 说明两套栈在抢同一批 canonical 端口，此时任取其一都会把端口所有权
        # 判给错误的栈。所以两份都读出来显式裁决，而不是读到一份就回落。
        release_startup = _stackctl.load_startup_attempt(target_name)
        test_live_startup = _stackctl.load_test_live_startup_attempt(target_name)
        if _startup_is_running(release_startup) and _startup_is_running(
            test_live_startup
        ):
            raise RuntimeError(
                f"GATE_BLOCK: {target_name} has a running release startup receipt and a "
                "running mutable test-live startup receipt at the same time; stop one "
                "stack before reading local topology"
            )
        # 只有一份 running 时它就是唯一权威；两份都不 current 才是身份漂移。
        startup = (
            release_startup
            if _startup_identity_current(release_startup)
            else test_live_startup
        )
        if not _startup_identity_current(startup):
            raise RuntimeError(
                f"GATE_BLOCK: {target_name} startup Provider runtime identity is not current"
            )
        full_local_roles.extend(
            str(item["role"])
            for item in provider_runtime["composition"]["workloads"]
        )
    role_map = {
        "alpha-local": full_local_roles,
        "beta-local": full_local_roles,
        "gamma-local": full_local_roles,
        "prod-sim": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
        ],
    }
    return role_map.get(target_name, [])


@contextlib.contextmanager
def _scoped_process_environment(values: Mapping[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update({key: str(value) for key, value in values.items()})
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
