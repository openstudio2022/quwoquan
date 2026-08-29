"""Data ReliableTask endpoints are resolved from the Ops-owned local topology.

spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/config-source-governance/spec.md#gwt-001
"""
from __future__ import annotations

import copy
import json

import pytest
import yaml

from quwoquan_ops.cli.lib import data_execution_fleet as data_execution_fleet_module
from quwoquan_ops.cli.lib.data_execution_fleet import (
    COMPOSE_PATH,
    DataExecutionFleetConfig,
    _redis_writable,
    data_execution_fleet_status,
    load_data_execution_fleet_config,
    project_canonical_runtime_owned_ports,
    project_runtime_owned_ports,
    require_published_endpoint_port,
    resolve_data_execution_fleet_endpoint,
)
from quwoquan_ops.cli.lib.port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
    profile_ports,
)


def test_data_execution_fleet__uses_one_declared_local_target__contract__local_contract() -> None:
    config = load_data_execution_fleet_config()
    endpoint = resolve_data_execution_fleet_endpoint(config)
    ports = profile_ports(load_port_manifest(), config.port_profile)

    assert endpoint.target == config.target == "data-local"
    assert endpoint.mongo_uri.endswith(f":{ports[config.mongo_port_role]}/?directConnection=true")
    assert endpoint.redis_addr.endswith(f":{ports[config.redis_port_role]}")
    assert config.mongo_port_role == "data-execution-mongodb"
    assert config.redis_port_role == "data-execution-redis"
    assert ports[config.mongo_port_role] != ports["mongodb"]
    assert ports[config.redis_port_role] != ports["redis"]


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


def test_canonical_runtime_endpoint_projection_is_complete_transport_exact_and_excludes_data_fleet__contract__local_contract() -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    fleet = load_data_execution_fleet_config()

    endpoints = project_canonical_runtime_owned_ports(
        port_profile="beta-local",
        manifest=manifest,
    )
    identities = {
        (item["role"], item["hostPort"], item["protocol"]) for item in endpoints
    }

    assert ("coturn", beta_ports["coturn"], "tcp") in identities
    assert ("coturn", beta_ports["coturn"], "udp") in identities
    assert all(item[0] not in {fleet.mongo_port_role, fleet.redis_port_role} for item in identities)
    assert endpoints == sorted(
        endpoints,
        key=lambda item: (item["hostPort"], item["protocol"], item["role"]),
    )


def test_data_execution_fleet__compose_service_names_equal_their_port_roles__contract__local_contract() -> None:
    """fleet 的 Compose service 名必须就是它自有的 role 名。

    publisher 身份是 `(composeService, containerPort, protocol, hostPort)`，而目标 runtime
    的 backing 栈也有名为 `mongodb`/`redis`、容器口同为 27017/6379 的 service。service 名
    一旦不是 role 名，fleet 的发布口会被归因给目标 runtime 自有的那两个 role —— 那种漂移
    在门禁里表现为「有 role 认领」的假通过，不会自己暴露。
    """
    config = load_data_execution_fleet_config()
    manifest = load_port_manifest()

    assert data_execution_fleet_module.MONGO_COMPOSE_SERVICE == config.mongo_port_role
    assert data_execution_fleet_module.REDIS_COMPOSE_SERVICE == config.redis_port_role

    compose = yaml.safe_load(
        data_execution_fleet_module.COMPOSE_PATH.read_text(encoding="utf-8")
    )
    services = set(compose["services"])
    assert data_execution_fleet_module.MONGO_COMPOSE_SERVICE in services
    assert data_execution_fleet_module.REDIS_COMPOSE_SERVICE in services
    # 撞名的旧名必须不再是 service 名（别名不算：别名不参与 publisher 身份判定）。
    assert "mongodb" not in services
    assert "redis" not in services

    # 两个 fleet role 与目标 runtime 的 mongodb/redis role 现在是不同的容器身份。
    closure = compose_publisher_container_role_closure(
        compose_published_endpoint_roles(manifest, config.port_profile)
    )
    assert closure[(config.mongo_port_role, 27017, "tcp")] == frozenset(
        {config.mongo_port_role}
    )
    assert closure[("mongodb", 27017, "tcp")] == frozenset({"mongodb"})


def test_data_execution_fleet__compose_service_role_drift_fails_closed__contract__local_contract(
    tmp_path,
) -> None:
    """service 名与 role 名分叉时装载即判否，不等到门禁假通过。"""
    document = {
        "target": "data-local",
        "portProfile": "beta-local",
        "mongoPortRole": "mongodb",
        "redisPortRole": "redis",
    }
    path = tmp_path / "data_execution_fleet.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="must equal their port roles"):
        load_data_execution_fleet_config(path)


def test_data_execution_fleet__rejects_implicit_or_extra_configuration__contract__local_contract() -> None:
    try:
        DataExecutionFleetConfig.from_document(
            {
                "target": "data-local",
                "portProfile": "gamma-local",
                "mongoPortRole": "mongodb",
                "redisPortRole": "redis",
                "fallbackTarget": "beta-local",
            }
        )
    except ValueError as exc:
        assert "unexpected fields" in str(exc)
    else:
        raise AssertionError("fleet topology must not accept a fallback target")


def test_data_execution_fleet__runtime_endpoint_projection_uses_exact_profile_role_port_and_protocol_identity__contract__local_contract() -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    alpha_ports = profile_ports(manifest, "alpha-local")
    beta_published_endpoints = [
        {"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "udp"},
        {
            "role": "data-execution-mongodb",
            "hostPort": beta_ports["data-execution-mongodb"],
            "protocol": "tcp",
        },
        {
            "role": "data-execution-redis",
            "hostPort": beta_ports["data-execution-redis"],
            "protocol": "tcp",
        },
    ]

    beta_runtime_owned = project_runtime_owned_ports(
        port_profile="beta-local",
        published_ports=beta_published_endpoints,
        manifest=manifest,
    )
    alpha_runtime_owned = project_runtime_owned_ports(
        port_profile="alpha-local",
        published_ports=[
            {
                "role": "data-execution-mongodb",
                "hostPort": alpha_ports["data-execution-mongodb"],
                "protocol": "tcp",
            },
            {
                "role": "data-execution-redis",
                "hostPort": alpha_ports["data-execution-redis"],
                "protocol": "tcp",
            },
        ],
        manifest=manifest,
    )

    assert beta_runtime_owned == [
        {"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "tcp"},
        {"role": "coturn", "hostPort": beta_ports["coturn"], "protocol": "udp"},
    ]
    assert alpha_runtime_owned == [
        {
            "role": "data-execution-mongodb",
            "hostPort": alpha_ports["data-execution-mongodb"],
            "protocol": "tcp",
        },
        {
            "role": "data-execution-redis",
            "hostPort": alpha_ports["data-execution-redis"],
            "protocol": "tcp",
        },
    ]


def test_data_execution_fleet__published_endpoint_query_requires_one_exact_role_and_protocol__contract__local_contract() -> None:
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


def test_data_execution_fleet__runtime_endpoint_projection_rejects_absent_unknown_duplicate_and_drifted_ownership__contract__local_contract(
    monkeypatch,
) -> None:
    manifest = load_port_manifest()
    beta_ports = profile_ports(manifest, "beta-local")
    valid_config = load_data_execution_fleet_config()
    valid_endpoints = [
        {"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "tcp"},
        {
            "role": "data-execution-mongodb",
            "hostPort": beta_ports["data-execution-mongodb"],
            "protocol": "tcp",
        },
        {
            "role": "data-execution-redis",
            "hostPort": beta_ports["data-execution-redis"],
            "protocol": "tcp",
        },
    ]

    invalid_cases = []
    unknown_role = DataExecutionFleetConfig(
        target=valid_config.target,
        port_profile=valid_config.port_profile,
        mongo_port_role="unknown-data-role",
        redis_port_role=valid_config.redis_port_role,
    )
    invalid_cases.append((manifest, valid_endpoints, unknown_role, "not declared"))
    duplicate_role = DataExecutionFleetConfig(
        target=valid_config.target,
        port_profile=valid_config.port_profile,
        mongo_port_role=valid_config.mongo_port_role,
        redis_port_role=valid_config.mongo_port_role,
    )
    invalid_cases.append((manifest, valid_endpoints, duplicate_role, "distinct"))
    unknown_profile = DataExecutionFleetConfig(
        target=valid_config.target,
        port_profile="unknown-profile",
        mongo_port_role=valid_config.mongo_port_role,
        redis_port_role=valid_config.redis_port_role,
    )
    invalid_cases.append((manifest, valid_endpoints, unknown_profile, "profile"))
    drifted_endpoints = copy.deepcopy(valid_endpoints)
    drifted_endpoints[1]["hostPort"] += 1
    invalid_cases.append((manifest, drifted_endpoints, valid_config, "canonical"))
    invalid_cases.append((manifest, None, valid_config, "required"))
    invalid_cases.append((manifest, [], valid_config, "required"))
    invalid_cases.append((manifest, beta_ports, valid_config, "list"))
    invalid_cases.append(
        (
            manifest,
            [
                *valid_endpoints,
                {"role": "unknown-runtime-role", "hostPort": 18880, "protocol": "tcp"},
            ],
            valid_config,
            "not declared",
        )
    )
    invalid_cases.append(
        (manifest, [*valid_endpoints, dict(valid_endpoints[0])], valid_config, "distinct")
    )
    invalid_cases.append(
        (
            manifest,
            [{"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "sctp"}],
            valid_config,
            "protocol",
        )
    )
    invalid_cases.append(
        (
            manifest,
            [{"role": "api-edge", "hostPort": beta_ports["api-edge"], "protocol": "udp"}],
            valid_config,
            "publisher protocol",
        )
    )
    invalid_cases.append(
        (
            manifest,
            [
                {
                    "role": "livekit-rtc-udp",
                    "hostPort": beta_ports["livekit-rtc-udp"],
                    "protocol": "tcp",
                }
            ],
            valid_config,
            "publisher protocol",
        )
    )
    duplicate_manifest = copy.deepcopy(manifest)
    duplicate_manifest["roles"][valid_config.redis_port_role]["slotOffset"] = duplicate_manifest[
        "roles"
    ][valid_config.mongo_port_role]["slotOffset"]
    invalid_cases.append((duplicate_manifest, valid_endpoints, valid_config, "manifest"))

    for candidate_manifest, published_ports, config, expected in invalid_cases:
        monkeypatch.setattr(
            data_execution_fleet_module,
            "load_data_execution_fleet_config",
            lambda config=config: config,
        )
        with pytest.raises((RuntimeError, ValueError), match=expected):
            project_runtime_owned_ports(
                port_profile="beta-local",
                published_ports=published_ports,
                manifest=candidate_manifest,
            )

    monkeypatch.setattr(
        data_execution_fleet_module,
        "load_data_execution_fleet_config",
        lambda: valid_config,
    )
    with pytest.raises(ValueError, match="runtime port profile is not declared"):
        project_runtime_owned_ports(
            port_profile="unknown-profile",
            published_ports=valid_endpoints,
            manifest=manifest,
        )


def test_data_execution_fleet__compose_model_projects_exact_canonical_publish_endpoints__contract__local_contract() -> None:
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

    endpoints = data_execution_fleet_module.project_compose_published_endpoints(
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
def test_data_execution_fleet__compose_model_rejects_unowned_or_indeterminate_publish_endpoints__contract__local_contract(
    service,
    ports,
    expected,
) -> None:
    with pytest.raises((TypeError, ValueError), match=expected):
        data_execution_fleet_module.project_compose_published_endpoints(
            port_profile="alpha-local",
            compose_model={"services": {service: {"ports": ports}}},
            manifest=load_port_manifest(),
        )


def test_data_execution_fleet__dedicated_compose_owns_both_endpoints__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._socket_ready",
        lambda _host, _port: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._compose_running_services",
        lambda _endpoint: frozenset(
            {
                data_execution_fleet_module.MONGO_COMPOSE_SERVICE,
                data_execution_fleet_module.REDIS_COMPOSE_SERVICE,
            }
        ),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._mongo_writable",
        lambda _endpoint: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._redis_writable",
        lambda _endpoint: True,
    )

    status = data_execution_fleet_status()

    assert status.ready is True
    assert status.owned is True
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "QWQ_DATA_FLEET_MONGO_PORT" in compose
    assert "QWQ_DATA_FLEET_REDIS_PORT" in compose
    assert "127.0.0.1:${QWQ_DATA_FLEET_MONGO_PORT" in compose
    assert "127.0.0.1:${QWQ_DATA_FLEET_REDIS_PORT" in compose
    assert "postgres" not in compose
    assert "object-storage" not in compose


def test_data_execution_fleet__tcp_without_writable_backends_is_not_ready__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._socket_ready",
        lambda _host, _port: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._compose_running_services",
        lambda _endpoint: frozenset(
            {
                data_execution_fleet_module.MONGO_COMPOSE_SERVICE,
                data_execution_fleet_module.REDIS_COMPOSE_SERVICE,
            }
        ),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._mongo_writable",
        lambda _endpoint: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._redis_writable",
        lambda _endpoint: False,
    )

    status = data_execution_fleet_status()

    assert status.ready is False
    assert status.mongo is True
    assert status.redis is False
    assert status.issue_code == "DATA.POOL.DELIVERY_UNAVAILABLE"


def test_data_execution_fleet__owned_internal_service_without_host_mapping_is_unavailable__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._socket_ready",
        lambda _host, _port: False,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._compose_running_services",
        lambda _endpoint: frozenset(
            {
                data_execution_fleet_module.MONGO_COMPOSE_SERVICE,
                data_execution_fleet_module.REDIS_COMPOSE_SERVICE,
            }
        ),
    )

    status = data_execution_fleet_status()

    assert status.owned is True
    assert status.mongo is False
    assert status.redis is False
    assert status.ready is False
    assert status.issue_code == "DATA.POOL.DELIVERY_UNAVAILABLE"


def test_data_execution_fleet__redis_probe_requires_exact_write_read_delete_result__contract__local_contract(
    monkeypatch,
) -> None:
    endpoint = resolve_data_execution_fleet_endpoint()

    class Result:
        returncode = 0
        stdout = "LOADING Redis is loading the dataset in memory\n"
        stderr = ""

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet.subprocess.run",
        lambda *_args, **_kwargs: Result(),
    )

    assert _redis_writable(endpoint) is False
