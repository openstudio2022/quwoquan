"""现役本地 runtime published-port 所有权契约。"""
from __future__ import annotations

import copy

import pytest

from quwoquan_ops.cli.lib.port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
    profile_ports,
)
from quwoquan_ops.cli.lib.runtime_port_ownership import (
    project_canonical_runtime_owned_ports,
    project_compose_published_endpoints,
    project_runtime_owned_ports,
    require_published_endpoint_port,
)


def test_local_port_manifest__compose_publisher_identity_resolves_multi_role_services_exactly__contract__local_contract() -> None:
    manifest = load_port_manifest()
    alpha_ports = profile_ports(manifest, "alpha-local")

    roles = compose_published_endpoint_roles(manifest, "alpha-local")

    def key(service: str, container_port: int, protocol: str, role: str) -> tuple:
        return (service, container_port, protocol, alpha_ports[role])

    assert roles[key("gamma-proxy", alpha_ports["api-edge"], "tcp", "api-edge")] == (
        "api-edge"
    )
    assert roles[key("gamma-proxy", 2019, "tcp", "caddy-admin")] == "caddy-admin"
    assert roles[key("livekit-sfu", 7880, "tcp", "livekit-http")] == "livekit-http"
    assert roles[key("livekit-sfu", 7881, "tcp", "livekit-rtc-tcp")] == (
        "livekit-rtc-tcp"
    )
    assert roles[key("livekit-sfu", 7882, "udp", "livekit-rtc-udp")] == (
        "livekit-rtc-udp"
    )
    assert roles[key("livekit-sfu", 6789, "tcp", "livekit-metrics")] == (
        "livekit-metrics"
    )
    assert roles[key("coturn", 3478, "tcp", "coturn")] == "coturn"
    assert roles[key("coturn", 3478, "udp", "coturn")] == "coturn"
    assert roles[key("elasticsearch", 9200, "tcp", "elasticsearch")] == "elasticsearch"

    # service-core 把多个模块并进同一 Compose service，user/chat 共用容器口 18081、
    # assistant/notification 共用 18087；只有 canonical hostPort 能把它们分开。
    assert roles[key("service-core", 18081, "tcp", "user-service")] == "user-service"
    assert roles[key("service-core", 18081, "tcp", "chat-service")] == "chat-service"
    assert roles[key("service-core", 18087, "tcp", "assistant-service")] == (
        "assistant-service"
    )
    assert roles[key("service-core", 18087, "tcp", "notification-service")] == (
        "notification-service"
    )


def test_local_port_manifest__shared_container_port_needs_the_host_port_to_resolve__contract__local_contract() -> None:
    """三元组对 service-core 共用容器口是歧义的，四元组才能唯一定位 role。"""
    manifest = load_port_manifest()
    alpha_ports = profile_ports(manifest, "alpha-local")

    roles = compose_published_endpoint_roles(manifest, "alpha-local")

    shared = {
        identity: role
        for identity, role in roles.items()
        if identity[:3] == ("service-core", 18081, "tcp")
    }
    assert {role for role in shared.values()} == {"user-service", "chat-service"}
    assert {identity[3] for identity in shared} == {
        alpha_ports["user-service"],
        alpha_ports["chat-service"],
    }

    # 去掉 hostPort 后两个 role 塌缩成同一个键，正是三元组无法判否的歧义。
    assert len({identity[:3] for identity in shared}) == 1


def test_local_port_manifest__compose_publisher_identity_rejects_incomplete_duplicate_and_unknown_protocol__contract__local_contract() -> None:
    manifest = load_port_manifest()
    invalid_cases = []

    incomplete = copy.deepcopy(manifest)
    incomplete["roles"]["api-edge"]["composePublishedEndpoints"][0].pop("protocol")
    invalid_cases.append((incomplete, "fields"))

    duplicate = copy.deepcopy(manifest)
    duplicate["roles"]["product-ops-edge"]["composePublishedEndpoints"] = copy.deepcopy(
        duplicate["roles"]["livekit-http"]["composePublishedEndpoints"]
    )
    invalid_cases.append((duplicate, "multiple roles"))

    unknown_protocol = copy.deepcopy(manifest)
    unknown_protocol["roles"]["api-edge"]["composePublishedEndpoints"][0]["protocol"] = "sctp"
    invalid_cases.append((unknown_protocol, "protocol"))

    service_core_target_drift = copy.deepcopy(manifest)
    service_core_target_drift["roles"]["user-service"]["composePublishedEndpoints"][0][
        "containerPort"
    ] = 28081
    invalid_cases.append((service_core_target_drift, "composition target 18081"))

    # containerPort 只接受字面端口号或 `profileCanonical`；下面每种取值都必须判否，
    # 否则畸形 publisher 会带着无法解析的容器端点进入 teardown 所有权判定。
    for malformed_container_port in (0, 65536, True, "18081", None, "profilecanonical"):
        malformed = copy.deepcopy(manifest)
        malformed["roles"]["api-edge"]["composePublishedEndpoints"][0][
            "containerPort"
        ] = malformed_container_port
        invalid_cases.append((malformed, "containerPort is invalid"))

    for candidate, expected in invalid_cases:
        with pytest.raises(ValueError, match=expected):
            compose_published_endpoint_roles(candidate, "alpha-local")


def test_canonical_runtime_endpoint_projection_is_complete_and_transport_exact__contract__local_contract() -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    endpoints = project_canonical_runtime_owned_ports(
        port_profile="beta-local",
        manifest=manifest,
    )
    identities = {
        (item["role"], item["hostPort"], item["protocol"]) for item in endpoints
    }

    assert ("coturn", beta_ports["coturn"], "tcp") in identities
    assert ("coturn", beta_ports["coturn"], "udp") in identities
    assert ("mongodb", beta_ports["mongodb"], "tcp") in identities
    assert ("redis", beta_ports["redis"], "tcp") in identities
    assert endpoints == sorted(
        endpoints,
        key=lambda item: (item["hostPort"], item["protocol"], item["role"]),
    )



def test_runtime_port_ownership__projection_uses_exact_profile_role_port_and_protocol_identity__contract__local_contract() -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    published_endpoints = [
        {"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "udp"},
        {"role": "mongodb", "hostPort": beta_ports["mongodb"], "protocol": "tcp"},
    ]

    assert project_runtime_owned_ports(
        port_profile="beta-local",
        published_ports=published_endpoints,
        manifest=manifest,
    ) == published_endpoints


def test_runtime_port_ownership__published_endpoint_query_requires_one_exact_role_and_protocol__contract__local_contract() -> None:
    endpoints = [
        {"role": "coturn", "hostPort": 18180, "protocol": "tcp"},
        {"role": "coturn", "hostPort": 18180, "protocol": "udp"},
        {"role": "product-ops-service", "hostPort": 18250, "protocol": "tcp"},
    ]

    assert require_published_endpoint_port(
        endpoints,
        role="coturn",
        protocol="udp",
    ) == 18180
    assert require_published_endpoint_port(
        endpoints,
        role="product-ops-service",
        protocol="tcp",
    ) == 18250

    with pytest.raises(ValueError, match="exactly one"):
        require_published_endpoint_port(
            endpoints,
            role="product-ops-service",
            protocol="udp",
        )
    with pytest.raises(ValueError, match="exactly one"):
        require_published_endpoint_port(
            [*endpoints, dict(endpoints[-1])],
            role="product-ops-service",
            protocol="tcp",
        )
    with pytest.raises(ValueError, match="fields"):
        require_published_endpoint_port(
            [{"role": "product-ops-service", "hostPort": 18250}],
            role="product-ops-service",
            protocol="tcp",
        )


def test_runtime_port_ownership__projection_rejects_absent_unknown_duplicate_and_drifted_ownership__contract__local_contract() -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    valid = [
        {"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "udp"},
    ]
    invalid_cases = [
        (None, "required"),
        ([], "required"),
        (beta_ports, "list"),
        ([*valid, {"role": "unknown-runtime-role", "hostPort": 18880, "protocol": "tcp"}], "not declared"),
        ([*valid, dict(valid[0])], "distinct"),
        ([{"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "udp"}], "publisher protocol"),
        ([{"role": "api-edge", "hostPort": beta_ports["api-edge"] + 1, "protocol": "tcp"}], "canonical"),
    ]
    for published_ports, expected in invalid_cases:
        with pytest.raises(ValueError, match=expected):
            project_runtime_owned_ports(
                port_profile="beta-local",
                published_ports=published_ports,
                manifest=manifest,
            )

    with pytest.raises(ValueError, match="runtime port profile is not declared"):
        project_runtime_owned_ports(
            port_profile="unknown-profile",
            published_ports=valid,
            manifest=manifest,
        )


def test_runtime_port_ownership__compose_model_projects_exact_canonical_publish_endpoints__contract__local_contract() -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    compose_model = {
        "services": {
            "gamma-proxy": {
                "ports": [
                    {
                        "target": beta_ports["api-edge"],
                        "published": str(beta_ports["api-edge"]),
                        "protocol": "tcp",
                    },
                    {
                        "target": 2019,
                        "published": str(beta_ports["caddy-admin"]),
                        "protocol": "tcp",
                    },
                ]
            },
            "service-core": {
                "ports": [
                    # 共用容器口 18081 由 user/chat 同时声明；两条发布口只靠 canonical
                    # hostPort 区分，投影必须各归其主而不是塌缩成一条。
                    {
                        "target": 18081,
                        "published": str(beta_ports["user-service"]),
                        "protocol": "tcp",
                    },
                    {
                        "target": 18081,
                        "published": str(beta_ports["chat-service"]),
                        "protocol": "tcp",
                    },
                ]
            },
            "coturn": {
                "ports": [
                    {
                        "target": 3478,
                        "published": beta_ports["coturn"],
                        "protocol": "tcp",
                    },
                    {
                        "target": 3478,
                        "published": str(beta_ports["coturn"]),
                        "protocol": "udp",
                    },
                ]
            },
            "mongodb": {
                "ports": [
                    {
                        "target": 27017,
                        "published": str(beta_ports["mongodb"]),
                        "protocol": "tcp",
                    }
                ]
            },
            "internal-only": {"expose": [9090]},
        }
    }

    endpoints = project_compose_published_endpoints(
        port_profile="beta-local",
        compose_model=compose_model,
        manifest=manifest,
    )

    assert endpoints == sorted(
        [
            {
                "role": "api-edge",
                "hostPort": beta_ports["api-edge"],
                "protocol": "tcp",
            },
            {
                "role": "coturn",
                "hostPort": beta_ports["coturn"],
                "protocol": "tcp",
            },
            {
                "role": "coturn",
                "hostPort": beta_ports["coturn"],
                "protocol": "udp",
            },
            {
                "role": "user-service",
                "hostPort": beta_ports["user-service"],
                "protocol": "tcp",
            },
            {
                "role": "chat-service",
                "hostPort": beta_ports["chat-service"],
                "protocol": "tcp",
            },
            {
                "role": "mongodb",
                "hostPort": beta_ports["mongodb"],
                "protocol": "tcp",
            },
            {
                "role": "caddy-admin",
                "hostPort": beta_ports["caddy-admin"],
                "protocol": "tcp",
            },
        ],
        key=lambda endpoint: (
            endpoint["hostPort"],
            endpoint["protocol"],
            endpoint["role"],
        ),
    )


@pytest.mark.parametrize(
    ("service", "ports", "expected"),
    [
        (
            "runtime",
            [{"target": 8080, "published": "18880", "protocol": "tcp"}],
            "publisher identity",
        ),
        ("runtime", [{"target": 8080, "protocol": "tcp"}], "published host port"),
        (
            "runtime",
            [{"target": 8080, "published": "17000-17010", "protocol": "tcp"}],
            "integer",
        ),
        (
            "runtime",
            [{"target": 8080, "published": "17000", "protocol": "sctp"}],
            "protocol",
        ),
        (
            "gamma-proxy",
            [{"target": 7880, "published": "17000", "protocol": "tcp"}],
            "publisher identity",
        ),
        # 回环上游口 28081 不是声明过的发布身份：改写发布 target 会让 canonical 主机
        # 端口运行期不可服务，这里必须按未知发布身份判否。
        (
            "service-core",
            [{"target": 28081, "published": "17200", "protocol": "tcp"}],
            "publisher identity",
        ),
        # 容器身份已声明但主机端口既不属 user 也不属 chat：四元组未命中，且前缀存在，
        # 须报主机端口不 canonical 而不是含糊的未知身份。
        (
            "service-core",
            [{"target": 18081, "published": "17999", "protocol": "tcp"}],
            "host port is not canonical",
        ),
        # 共用容器口上的合法 protocol 但未声明该 protocol 的发布契约。
        (
            "service-core",
            [{"target": 18081, "published": "17210", "protocol": "udp"}],
            "publisher identity",
        ),
    ],
)
def test_runtime_port_ownership__compose_model_rejects_unowned_or_indeterminate_publish_endpoints__contract__local_contract(
    service,
    ports,
    expected,
) -> None:
    with pytest.raises((TypeError, ValueError), match=expected):
        project_compose_published_endpoints(
            port_profile="alpha-local",
            compose_model={"services": {service: {"ports": ports}}},
            manifest=load_port_manifest(),
        )
