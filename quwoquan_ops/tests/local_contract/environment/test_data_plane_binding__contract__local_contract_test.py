from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from quwoquan_ops.cli.lib import data_plane_binding as data_plane_binding_module
from quwoquan_ops.cli.lib.data_plane_binding import (
    DataPlaneBindingError,
    canonical_data_plane_binding,
    materialize_data_plane_binding_package,
    resolve_data_plane_environment,
    validate_contract_graph_data_plane_bindings,
    validate_data_plane_binding,
)
from quwoquan_ops.cli.lib.environment_topology import (
    load_environment_topology,
    validate_data_plane_metrics_coverage,
    validate_environment_topology,
    validate_prod_data_plane_backup_coverage,
)
from quwoquan_ops.cli.lib.runtime_topology_package import (
    RuntimeTopologyPackageError,
    load_runtime_topology_package,
    materialize_runtime_topology_package,
)


ROOT = Path(__file__).resolve().parents[4]


def _binding(
    service: str,
    slot: str,
    engine: str,
    resource: str,
    namespace: str,
    inject: dict[str, dict[str, str]],
    *,
    secret_ref: str | None = None,
    shared: bool = True,
) -> dict[str, object]:
    return {
        "service": service,
        "slot": slot,
        "engine": engine,
        "resource": resource,
        "namespace": namespace,
        "secretRef": secret_ref,
        "shared": shared,
        "required": True,
        "backupRef": "backup-policy",
        "metricsRef": (
            "search-objects-metrics"
            if slot.startswith("search.objects.")
            else "metrics-policy"
        ),
        "inject": inject,
    }


def _target() -> dict[str, object]:
    return {
        "dataPlane": {
            "resources": {
                "shared-mongodb": {
                    "engine": "mongodb",
                    "physicalIdentity": {
                        "external": "prod-mongodb",
                        "local": "mongodb",
                        "prevalidate": "mongodb",
                    },
                    "failureDomain": "data-a",
                    "shared": True,
                },
                "search-elasticsearch": {
                    "engine": "elasticsearch",
                    "physicalIdentity": {
                        "external": "prod-search",
                        "local": "elasticsearch",
                        "prevalidate": "elasticsearch",
                    },
                    "failureDomain": "data-b",
                    "shared": True,
                },
                "telemetry-elasticsearch": {
                    "engine": "elasticsearch",
                    "physicalIdentity": {
                        "external": "prod-telemetry",
                        "local": "elasticsearch",
                        "prevalidate": "elasticsearch",
                    },
                    "failureDomain": "data-c",
                    "shared": True,
                },
            },
            "bindings": {
                "content-service.mongodb": _binding(
                    "content-service",
                    "mongodb",
                    "mongodb",
                    "shared-mongodb",
                    "quwoquan_content",
                    {"CONTENT_MONGO_URI": {"kind": "uri"}},
                    secret_ref="PROD_CONTENT_MONGO_URI",
                ),
                "search-service.search.objects.reader": _binding(
                    "search-service",
                    "search.objects.reader",
                    "elasticsearch",
                    "search-elasticsearch",
                    "quwoquan_objects-v1",
                    {
                        "SEARCH_ES_ENDPOINTS": {
                            "kind": "endpoint",
                            "secretRef": "PROD_SEARCH_ENDPOINT",
                        },
                        "SEARCH_ES_API_KEY": {
                            "kind": "api_key",
                            "secretRef": "PROD_SEARCH_READER",
                        },
                        "SEARCH_ES_INDEX": {"kind": "index"},
                    },
                    secret_ref="PROD_SEARCH_READER",
                ),
                "content-service.search.objects.writer": _binding(
                    "content-service",
                    "search.objects.writer",
                    "elasticsearch",
                    "search-elasticsearch",
                    "quwoquan_objects-v1",
                    {
                        "SEARCH_ES_ENDPOINTS": {
                            "kind": "endpoint",
                            "secretRef": "PROD_SEARCH_ENDPOINT",
                        },
                        "SEARCH_ES_API_KEY": {
                            "kind": "api_key",
                            "secretRef": "PROD_SEARCH_WRITER",
                        },
                        "SEARCH_ES_INDEX": {"kind": "index"},
                    },
                    secret_ref="PROD_SEARCH_WRITER",
                ),
                "search-service.search.objects.writer": _binding(
                    "search-service",
                    "search.objects.writer",
                    "elasticsearch",
                    "search-elasticsearch",
                    "quwoquan_objects-v1",
                    {
                        "SEARCH_ES_WRITER_ENDPOINTS": {
                            "kind": "endpoint",
                            "secretRef": "PROD_SEARCH_ENDPOINT",
                        },
                        "SEARCH_ES_WRITER_API_KEY": {
                            "kind": "api_key",
                            "secretRef": "PROD_SEARCH_WRITER",
                        },
                        "SEARCH_ES_WRITER_INDEX": {"kind": "index"},
                    },
                    secret_ref="PROD_SEARCH_WRITER",
                ),
                "deployment-control.telemetry.admin": _binding(
                    "deployment-control",
                    "telemetry.admin",
                    "elasticsearch",
                    "telemetry-elasticsearch",
                    "product-ops-observability",
                    {},
                    secret_ref="PROD_TELEMETRY_ADMIN",
                ),
                "deployment-control.search.objects.admin": _binding(
                    "deployment-control",
                    "search.objects.admin",
                    "elasticsearch",
                    "search-elasticsearch",
                    "quwoquan_objects-v1",
                    {},
                    secret_ref="PROD_SEARCH_ADMIN",
                ),
            },
        }
    }


def test_explicit_co_location_passes_and_digest_is_map_order_stable() -> None:
    target = _target()
    first = canonical_data_plane_binding(target)
    reversed_target = copy.deepcopy(target)
    data_plane = reversed_target["dataPlane"]
    assert isinstance(data_plane, dict)
    data_plane["resources"] = dict(reversed(list(data_plane["resources"].items())))
    data_plane["bindings"] = dict(reversed(list(data_plane["bindings"].items())))

    second = canonical_data_plane_binding(reversed_target)

    assert first["bindingDigest"] == second["bindingDigest"]
    assert validate_data_plane_binding(target, required=True) == []


def test_co_location_without_explicit_resource_and_binding_sharing_blocks() -> None:
    target = _target()
    data_plane = target["dataPlane"]
    assert isinstance(data_plane, dict)
    resources = data_plane["resources"]
    bindings = data_plane["bindings"]
    assert isinstance(resources, dict) and isinstance(bindings, dict)
    resources["shared-mongodb"]["shared"] = False
    bindings["content-service.mongodb"]["shared"] = False
    bindings["user-service.mongodb"] = _binding(
        "user-service",
        "mongodb",
        "mongodb",
        "shared-mongodb",
        "quwoquan_user",
        {"USER_MONGO_URI": {"kind": "uri"}},
        secret_ref="PROD_USER_MONGO_URI",
        shared=False,
    )

    issues = validate_data_plane_binding(target, required=True)

    assert any("co-located resource shared-mongodb" in issue for issue in issues)
    assert any("co-located binding content-service.mongodb" in issue for issue in issues)


def test_mode_specific_physical_identity_co_location_requires_sharing() -> None:
    target = _target()
    resources = target["dataPlane"]["resources"]
    bindings = target["dataPlane"]["bindings"]
    resources["telemetry-elasticsearch"]["shared"] = False
    bindings["deployment-control.telemetry.admin"]["shared"] = False

    issues = validate_data_plane_binding(target, required=True)

    assert any(
        "co-located resource telemetry-elasticsearch in local" in issue
        for issue in issues
    )
    assert any(
        "co-located resource telemetry-elasticsearch in prevalidate" in issue
        for issue in issues
    )
    assert not any(
        "co-located resource telemetry-elasticsearch in external" in issue
        for issue in issues
    )
    assert any(
        "co-located binding deployment-control.telemetry.admin in local" in issue
        for issue in issues
    )


def test_each_mode_reports_its_own_physical_identity_conflict() -> None:
    target = _target()
    resources = target["dataPlane"]["resources"]
    bindings = target["dataPlane"]["bindings"]
    search_identity = resources["search-elasticsearch"]["physicalIdentity"]
    telemetry_identity = resources["telemetry-elasticsearch"]["physicalIdentity"]
    search_identity["external"] = "shared-external"
    telemetry_identity["external"] = "shared-external"
    search_identity["local"] = "shared-local"
    telemetry_identity["local"] = "shared-local"
    search_identity["prevalidate"] = "search-prevalidate"
    telemetry_identity["prevalidate"] = "telemetry-prevalidate"
    resources["telemetry-elasticsearch"]["shared"] = False
    bindings["deployment-control.telemetry.admin"]["shared"] = False

    issues = validate_data_plane_binding(target, required=True)

    for mode in ("external", "local"):
        assert any(
            f"co-located resource telemetry-elasticsearch in {mode}" in issue
            for issue in issues
        )
        assert any(
            f"co-located binding deployment-control.telemetry.admin in {mode}"
            in issue
            for issue in issues
        )
    assert not any("in prevalidate" in issue for issue in issues)


def test_string_physical_identity_applies_to_every_mode() -> None:
    target = _target()
    resources = target["dataPlane"]["resources"]
    bindings = target["dataPlane"]["bindings"]
    resources["search-elasticsearch"]["physicalIdentity"] = "shared-es"
    resources["telemetry-elasticsearch"]["physicalIdentity"] = "shared-es"
    resources["telemetry-elasticsearch"]["shared"] = False
    bindings["deployment-control.telemetry.admin"]["shared"] = False

    issues = validate_data_plane_binding(target, required=True)

    for mode in ("external", "local", "prevalidate"):
        assert any(
            f"co-located resource telemetry-elasticsearch in {mode}" in issue
            for issue in issues
        )
        assert any(
            f"co-located binding deployment-control.telemetry.admin in {mode}"
            in issue
            for issue in issues
        )


def test_engine_mismatch_and_namespace_collision_block() -> None:
    target = _target()
    bindings = target["dataPlane"]["bindings"]
    bindings["content-service.mongodb"]["engine"] = "postgres"
    bindings["user-service.mongodb"] = _binding(
        "user-service",
        "mongodb",
        "mongodb",
        "shared-mongodb",
        "quwoquan_content",
        {"USER_MONGO_URI": {"kind": "uri"}},
        secret_ref="PROD_USER_MONGO_URI",
    )

    issues = validate_data_plane_binding(target, required=True)

    assert any("engine must match resource engine" in issue for issue in issues)
    assert any("namespace collision" in issue for issue in issues)


def test_canonical_excludes_secret_material_and_binding_change_changes_digest() -> None:
    target = _target()
    canonical = canonical_data_plane_binding(target)
    serialized = json.dumps(canonical, sort_keys=True)
    changed = copy.deepcopy(target)
    changed["dataPlane"]["bindings"]["content-service.mongodb"][
        "namespace"
    ] = "quwoquan_content_next"

    assert "actual-password" not in serialized
    assert "PROD_CONTENT_MONGO_URI" in serialized
    assert (
        canonical["bindingDigest"]
        != canonical_data_plane_binding(changed)["bindingDigest"]
    )
    injected = resolve_data_plane_environment(target, mode="external")["environment"]
    assert injected["content-service"]["CONTENT_MONGO_URI"] == (
        "${PROD_CONTENT_MONGO_URI:?}"
    )


def test_unknown_inject_value_shape_cannot_carry_secret_material() -> None:
    target = _target()
    target["dataPlane"]["bindings"]["content-service.mongodb"]["inject"] = {
        "CONTENT_MONGO_URI": {"kind": "uri", "value": "actual-password"}
    }

    with pytest.raises(DataPlaneBindingError, match="fields forbidden"):
        canonical_data_plane_binding(target)


def test_empty_backup_and_metrics_refs_block() -> None:
    target = _target()
    binding = target["dataPlane"]["bindings"]["content-service.mongodb"]
    binding["backupRef"] = ""
    binding["metricsRef"] = ""

    issues = validate_data_plane_binding(target, required=True)

    assert any("backupRef must be non-empty" in issue for issue in issues)
    assert any("metricsRef must be non-empty" in issue for issue in issues)


def test_search_fanout_requires_same_generation_and_role_separated_credentials() -> None:
    target = _target()
    bindings = target["dataPlane"]["bindings"]
    bindings["content-service.search.objects.writer"][
        "namespace"
    ] = "quwoquan_objects-v2"
    bindings["content-service.search.objects.writer"][
        "secretRef"
    ] = "PROD_SEARCH_READER"

    issues = validate_data_plane_binding(target, required=True)

    assert any("share resource, namespace, and vN generation" in issue for issue in issues)
    assert any("role-separated" in issue for issue in issues)


def test_deployment_control_classification_requires_empty_inject_for_any_slot() -> None:
    target = _target()
    bindings = target["dataPlane"]["bindings"]
    admin = bindings["deployment-control.telemetry.admin"]
    admin["slot"] = "maintenance"
    admin["inject"] = {"FORBIDDEN_ENDPOINT": {"kind": "endpoint"}}
    bindings["deployment-control.maintenance"] = admin
    del bindings["deployment-control.telemetry.admin"]

    issues = validate_data_plane_binding(target, required=True)

    assert any(
        "deployment-control.maintenance.inject must be empty for "
        "deployment-control binding" in issue
        for issue in issues
    )


def test_deployment_only_classification_has_no_tuple_allowlist() -> None:
    source = (
        ROOT / "quwoquan_ops/cli/lib/data_plane_binding.py"
    ).read_text(encoding="utf-8")

    assert "_SEARCH_ADMIN_BINDING" not in source
    assert "_TELEMETRY_ADMIN_BINDING" not in source
    assert "def _is_deployment_only_service(service: object)" in source
    assert "return service == _DEPLOYMENT_CONTROL_SERVICE" in source


def test_non_admin_deployment_control_slot_resolves_as_deployment_only() -> None:
    target = _target()
    bindings = target["dataPlane"]["bindings"]
    maintenance = _binding(
        "deployment-control",
        "maintenance",
        "elasticsearch",
        "telemetry-elasticsearch",
        "maintenance",
        {},
        secret_ref="PROD_MAINTENANCE_ADMIN",
    )
    maintenance["backupRef"] = "maintenance-backup"
    maintenance["metricsRef"] = "maintenance-metrics"
    bindings["deployment-control.maintenance"] = maintenance

    projection = resolve_data_plane_environment(target, mode="local")

    assert "deployment-control" not in projection["environment"]
    assert projection["deploymentEnvironment"][
        "deployment-control.maintenance"
    ] == {
        "endpoint": "http://elasticsearch:9200",
        "credential": "local-development-admin",
    }


def test_required_non_deployment_control_binding_requires_non_empty_inject() -> None:
    target = _target()
    target["dataPlane"]["bindings"]["content-service.mongodb"]["inject"] = {}

    issues = validate_data_plane_binding(target, required=True)

    assert any(
        "content-service.mongodb.inject must be a non-empty mapping when required"
        in issue
        for issue in issues
    )


def test_search_admin_stays_on_exact_deployment_control_slot() -> None:
    target = _target()
    bindings = target["dataPlane"]["bindings"]
    admin = bindings["deployment-control.search.objects.admin"]
    admin["service"] = "release-control"
    bindings["release-control.search.objects.admin"] = admin
    del bindings["deployment-control.search.objects.admin"]

    issues = validate_data_plane_binding(target, required=True)

    assert any("search.objects admin must be deployment-only" in issue for issue in issues)


def test_search_admin_is_required_deployment_only_and_not_injected() -> None:
    target = _target()
    del target["dataPlane"]["bindings"]["deployment-control.search.objects.admin"]

    issues = validate_data_plane_binding(target, required=True)

    assert any("deployment-only admin" in issue for issue in issues)


def test_search_role_credentials_include_distinct_admin_ref() -> None:
    target = _target()
    target["dataPlane"]["bindings"]["deployment-control.search.objects.admin"][
        "secretRef"
    ] = "PROD_SEARCH_WRITER"

    issues = validate_data_plane_binding(target, required=True)

    assert any("reader/writer/admin credential refs" in issue for issue in issues)


def test_explicit_index_value_is_safe_and_endpoint_value_is_forbidden() -> None:
    target = _target()
    reader = target["dataPlane"]["bindings"][
        "search-service.search.objects.reader"
    ]
    reader["inject"]["SEARCH_ES_INDEX"]["value"] = "quwoquan_objects-v1"
    assert validate_data_plane_binding(target, required=True) == []

    reader["inject"]["SEARCH_ES_ENDPOINTS"]["value"] = "http://forbidden:9200"
    issues = validate_data_plane_binding(target, required=True)
    assert any("fields forbidden for kind endpoint" in issue for issue in issues)


def test_external_required_api_key_without_secret_ref_fails_closed() -> None:
    target = _target()
    reader = target["dataPlane"]["bindings"][
        "search-service.search.objects.reader"
    ]
    reader["secretRef"] = None
    reader["inject"]["SEARCH_ES_API_KEY"].pop("secretRef")

    with pytest.raises(DataPlaneBindingError, match="role-separated"):
        resolve_data_plane_environment(target, mode="external")


def test_duplicate_service_environment_key_across_bindings_blocks() -> None:
    target = _target()
    target["dataPlane"]["bindings"]["content-service.mongodb"]["inject"] = {
        "SEARCH_ES_INDEX": {"kind": "database"}
    }

    issues = validate_data_plane_binding(target, required=True)

    assert any("inject duplicates content-service.SEARCH_ES_INDEX" in issue for issue in issues)


def test_logical_owner_metrics_and_backup_refs_must_be_distinct() -> None:
    target = _target()
    resources = target["dataPlane"]["resources"]
    resources["telemetry-elasticsearch"] = copy.deepcopy(
        resources["search-elasticsearch"]
    )
    bindings = target["dataPlane"]["bindings"]
    bindings["product-ops-service.telemetry"] = _binding(
        "product-ops-service",
        "telemetry",
        "elasticsearch",
        "telemetry-elasticsearch",
        "app-product-telemetry-raw",
        {"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_RAW_INDEX": {"kind": "index"}},
        secret_ref="PROD_TELEMETRY",
    )
    bindings["product-ops-service.runtime-logs"] = _binding(
        "product-ops-service",
        "runtime-logs",
        "elasticsearch",
        "telemetry-elasticsearch",
        "runtime-diagnostics-raw",
        {"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_RAW_INDEX": {"kind": "index"}},
        secret_ref="PROD_RUNTIME_LOGS",
    )
    bindings["product-ops-service.telemetry"]["metricsRef"] = (
        "product-telemetry-metrics"
    )
    bindings["product-ops-service.runtime-logs"]["metricsRef"] = (
        "runtime-logs-metrics"
    )
    bindings["product-ops-service.telemetry"]["backupRef"] = "shared-backup"
    bindings["product-ops-service.runtime-logs"]["backupRef"] = "shared-backup"

    issues = validate_data_plane_binding(target, target_name="prod-hosted", required=True)

    assert any("backupRef must be distinct" in issue for issue in issues)


def test_metrics_ref_must_resolve_to_canonical_profile() -> None:
    topology = load_environment_topology()
    prod = topology["targets"]["prod-hosted"]
    prod["dataPlane"]["bindings"]["product-ops-service.telemetry"][
        "metricsRef"
    ] = "missing-profile"

    issues = validate_data_plane_metrics_coverage(topology)

    assert (
        "prod-hosted: product-ops-service.telemetry.metricsRef has no metrics "
        "profile: missing-profile"
    ) in issues


def test_duplicate_physical_binding_profiles_are_rejected_globally() -> None:
    topology = load_environment_topology()
    metrics = yaml.safe_load(
        (ROOT / "quwoquan_ops/observability/data-plane-metrics.yaml").read_text(
            encoding="utf-8"
        )
    )
    duplicate = copy.deepcopy(
        metrics["bindingProfiles"]["search-elasticsearch-physical-metrics"]
    )
    metrics["bindingProfiles"]["duplicate-search-physical-metrics"] = duplicate

    issues = validate_data_plane_metrics_coverage(
        topology, metrics_manifest=metrics
    )

    assert any(
        "physicalProfileRef search-elasticsearch has multiple physical_resource "
        "binding profiles" in issue
        for issue in issues
    )


def test_shared_elasticsearch_has_one_physical_metrics_scrape_and_owner_profiles() -> None:
    topology = load_environment_topology()

    assert validate_data_plane_metrics_coverage(topology) == []
    metrics = yaml.safe_load(
        (ROOT / "quwoquan_ops/observability/data-plane-metrics.yaml").read_text(
            encoding="utf-8"
        )
    )
    profiles = metrics["bindingProfiles"]
    assert "search-objects-physical-metrics" not in profiles
    assert profiles["search-elasticsearch-physical-metrics"] == {
        "engine": "elasticsearch",
        "physicalProfileRef": "search-elasticsearch",
        "scrapeJob": "search-elasticsearch-exporter",
        "scope": "physical_resource",
        "ownerLabel": None,
        "namespacePatterns": [],
    }
    assert profiles["telemetry-elasticsearch-physical-metrics"] == {
        "engine": "elasticsearch",
        "physicalProfileRef": "telemetry-elasticsearch",
        "scrapeJob": "telemetry-elasticsearch-exporter",
        "scope": "physical_resource",
        "ownerLabel": None,
        "namespacePatterns": [],
    }
    assert {
        profiles[profile]["ownerLabel"]
        for profile in ("product-telemetry-metrics", "runtime-logs-metrics")
    } == {"product-telemetry", "runtime-logs"}
    assert all(
        profiles[profile]["scrapeJob"] != "telemetry-elasticsearch-exporter"
        for profile in ("product-telemetry-metrics", "runtime-logs-metrics")
    )


def test_same_elasticsearch_resource_requires_one_endpoint_reference() -> None:
    topology = load_environment_topology()
    prod = topology["targets"]["prod-hosted"]
    runtime_logs = prod["dataPlane"]["bindings"][
        "product-ops-service.runtime-logs"
    ]
    runtime_logs["inject"][
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT"
    ]["secretRef"] = "PROD_RUNTIME_LOGS_ES_ENDPOINT"

    issues = validate_data_plane_binding(
        prod, target_name="prod-hosted", required=True
    )

    assert any(
        "telemetry-elasticsearch endpoint refs must be identical" in issue
        for issue in issues
    )


def test_telemetry_admin_stays_on_exact_deployment_control_slot() -> None:
    topology = load_environment_topology()
    prod = topology["targets"]["prod-hosted"]
    bindings = prod["dataPlane"]["bindings"]
    admin = bindings["deployment-control.telemetry.admin"]
    admin["service"] = "release-control"
    bindings["release-control.telemetry.admin"] = admin
    del bindings["deployment-control.telemetry.admin"]

    issues = validate_data_plane_binding(
        prod, target_name="prod-hosted", required=True
    )

    assert any(
        "telemetry/runtime-logs require exactly one deployment-only admin" in issue
        for issue in issues
    )


def test_telemetry_admin_is_required_and_not_injected() -> None:
    topology = load_environment_topology()
    prod = topology["targets"]["prod-hosted"]
    del prod["dataPlane"]["bindings"]["deployment-control.telemetry.admin"]

    issues = validate_data_plane_binding(
        prod, target_name="prod-hosted", required=True
    )

    assert any("deployment-only admin" in issue for issue in issues)


def test_prod_logical_owner_api_keys_cannot_cross_roles() -> None:
    topology = load_environment_topology()
    prod = topology["targets"]["prod-hosted"]
    runtime_logs = prod["dataPlane"]["bindings"][
        "product-ops-service.runtime-logs"
    ]
    runtime_logs["inject"][
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_API_KEY"
    ]["secretRef"] = "PROD_PRODUCT_TELEMETRY_ES_API_KEY"

    issues = validate_data_plane_binding(
        prod, target_name="prod-hosted", required=True
    )

    assert any("must inject only its owner API key" in issue for issue in issues)


def _contract_graph_with_resources() -> dict[str, object]:
    return {
        "objects": [
            {
                "id": "search.search_index_view",
                "storageResources": [
                    {
                        "localName": "search_documents",
                        "identity": (
                            "search-service/search/search_index_view/search_documents"
                        ),
                        "engine": "elasticsearch",
                        "role": "query_projection",
                        "required": True,
                    },
                    {
                        "localName": "projection_inbox_and_watermarks",
                        "identity": (
                            "search-service/search/search_index_view/"
                            "projection_inbox_and_watermarks"
                        ),
                        "engine": "mongodb",
                        "role": "query_projection",
                        "required": True,
                    },
                ],
            },
            {
                "id": "content.post",
                "storageResources": [
                    {
                        "localName": "search_documents",
                        "identity": "content-service/content/post/search_documents",
                        "engine": "elasticsearch",
                        "role": "query_projection",
                        "required": True,
                    }
                ],
            },
        ]
    }


def test_gamma_and_prod_current_required_resources_resolve_uniquely() -> None:
    graph = json.loads(
        (ROOT / "quwoquan_service/generated/contract_graph.json").read_text(
            encoding="utf-8"
        )
    )
    schema = yaml.safe_load(
        (
            ROOT
            / "quwoquan_service/services/recommendation-service/config/schema.yaml"
        ).read_text(encoding="utf-8")
    )
    schema_keys = {row["key"] for row in schema["configs"]}
    expected_inject = {
        f"RECOMMENDATION_REDIS_{scene.upper()}_ADDR": {"kind": "addr"}
        for scene in ("general", "rec")
        if f"sys.recommendation-service.redis.{scene}.addr" in schema_keys
    }
    assert set(expected_inject) == {
        "RECOMMENDATION_REDIS_GENERAL_ADDR",
        "RECOMMENDATION_REDIS_REC_ADDR",
    }

    for environment, target, secret_ref in (
        ("gamma", "gamma-local", None),
        ("prod", "prod-hosted", "PROD_RECOMMENDATION_REDIS_ADDR"),
    ):
        runtime = yaml.safe_load(
            (ROOT / f"quwoquan_ops/environments/{environment}/runtime.yaml").read_text(
                encoding="utf-8"
            )
        )
        data_plane = runtime["targets"][target]["dataPlane"]
        candidates = [
            (key, binding)
            for key, binding in data_plane["bindings"].items()
            if binding["service"] == "recommendation-service"
            and binding["engine"] == "redis"
        ]

        assert len(candidates) == 1
        binding_key, binding = candidates[0]
        assert binding_key == "recommendation-service.redis"
        assert binding["slot"] == "redis"
        assert binding["resource"] == "primary-redis"
        assert binding["namespace"] == "db-recommendation"
        assert binding["secretRef"] == secret_ref
        assert binding["required"] is True
        assert binding["inject"] == expected_inject
        assert data_plane["resources"][binding["resource"]]["engine"] == "redis"
        assert validate_contract_graph_data_plane_bindings(
            graph, data_plane, target_name=target
        ) == []


@pytest.mark.parametrize(
    ("environment", "target"),
    (("gamma", "gamma-local"), ("prod", "prod-hosted")),
)
def test_required_environment_package_calls_contract_graph_cross_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: str,
    target: str,
) -> None:
    graph = {
        "objects": [
            {
                "storageResources": [
                    {
                        "localName": "required_state",
                        "identity": "missing-service/demo/demo_object/required_state",
                        "engine": "mongodb",
                        "role": "runtime",
                        "required": True,
                    }
                ]
            }
        ]
    }
    monkeypatch.setattr(
        data_plane_binding_module,
        "_load_contract_graph_for_binding",
        lambda _repo_root: graph,
    )
    package_root = tmp_path / target
    package_root.mkdir()

    with pytest.raises(
        DataPlaneBindingError,
        match="missing binding missing-service.mongodb",
    ):
        materialize_data_plane_binding_package(
            environment,
            target,
            package_root,
            repo_root=ROOT,
        )


def test_object_storage_engine_derives_underscore_default_slot() -> None:
    graph = {
        "objects": [
            {
                "storageResources": [
                    {
                        "localName": "asset_blobs",
                        "identity": "content-service/media/media_asset/asset_blobs",
                        "engine": "object_storage",
                        "role": "authority",
                        "required": True,
                    }
                ]
            }
        ]
    }
    binding = _binding(
        "content-service",
        "object_storage",
        "object_storage",
        "asset-storage",
        "content-assets",
        {"CONTENT_OBJECT_STORAGE_ENDPOINT": {"kind": "endpoint"}},
    )
    data_plane = {
        "bindings": {"content-service.object_storage": binding}
    }

    assert validate_contract_graph_data_plane_bindings(graph, data_plane) == []


def test_required_object_resource_missing_binding_fails_closed() -> None:
    graph = _contract_graph_with_resources()
    data_plane = copy.deepcopy(_target()["dataPlane"])
    del data_plane["bindings"]["content-service.mongodb"]

    issues = validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name="gamma-local"
    )

    assert issues == [
        "gamma-local: required object resource "
        "search-service/search/search_index_view/projection_inbox_and_watermarks "
        "is missing binding search-service.mongodb"
    ]


def test_required_object_resource_ambiguous_binding_fails_closed() -> None:
    graph = _contract_graph_with_resources()
    data_plane = copy.deepcopy(_target()["dataPlane"])
    duplicate = copy.deepcopy(data_plane["bindings"]["content-service.mongodb"])
    duplicate["service"] = "search-service"
    duplicate["slot"] = "mongodb"
    data_plane["bindings"]["search-service.mongodb"] = duplicate
    data_plane["bindings"]["alias-search-mongodb"] = copy.deepcopy(duplicate)

    issues = validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name="prod-hosted"
    )

    assert any(
        "projection_inbox_and_watermarks has ambiguous binding "
        "search-service.mongodb" in issue
        for issue in issues
    )


def test_required_object_resource_wrong_engine_fails_closed() -> None:
    graph = _contract_graph_with_resources()
    data_plane = copy.deepcopy(_target()["dataPlane"])
    mongodb = data_plane["bindings"]["content-service.mongodb"]
    mongodb["service"] = "search-service"
    mongodb["slot"] = "mongodb"
    mongodb["engine"] = "redis"
    data_plane["bindings"]["search-service.mongodb"] = mongodb
    del data_plane["bindings"]["content-service.mongodb"]

    issues = validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name="prod-hosted"
    )

    assert any(
        "projection_inbox_and_watermarks engine mongodb does not match binding "
        "search-service.mongodb engine redis" in issue
        for issue in issues
    )


def test_required_search_projection_uses_existing_writer_seam_only() -> None:
    graph = _contract_graph_with_resources()
    data_plane = copy.deepcopy(_target()["dataPlane"])

    issues = validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name="gamma-local"
    )

    assert not any("search-service.elasticsearch" in issue for issue in issues)
    assert not any("search_documents" in issue for issue in issues)


def test_orphan_search_writer_binding_fails_closed() -> None:
    graph = _contract_graph_with_resources()
    data_plane = copy.deepcopy(_target()["dataPlane"])
    orphan = copy.deepcopy(
        data_plane["bindings"]["content-service.search.objects.writer"]
    )
    orphan["service"] = "user-service"
    orphan["slot"] = "search.objects.writer"
    data_plane["bindings"]["user-service.search.objects.writer"] = orphan

    issues = validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name="prod-hosted"
    )

    assert (
        "prod-hosted: search writer binding user-service.search.objects.writer "
        "has no required ContractGraph query_projection resource"
    ) in issues


def test_current_runtime_declarations_resolve_without_secret_material() -> None:
    targets = {}
    for environment, target in (
        ("alpha", "alpha-local"),
        ("beta", "beta-local"),
        ("gamma", "gamma-local"),
        ("prod", "prod-hosted"),
    ):
        targets[target] = yaml.safe_load(
            (ROOT / f"quwoquan_ops/environments/{environment}/runtime.yaml").read_text(
                encoding="utf-8"
            )
        )["targets"][target]

    prod_projection = resolve_data_plane_environment(
        targets["prod-hosted"], mode="external", target_name="prod-hosted"
    )
    local_projections = {
        target: resolve_data_plane_environment(
            targets[target], mode="local", target_name=target
        )
        for target in ("alpha-local", "beta-local", "gamma-local")
    }
    gamma_projection = local_projections["gamma-local"]

    assert prod_projection["deploymentEnvironment"][
        "deployment-control.telemetry.admin"
    ] == {
        "endpoint": "${PROD_PRODUCT_TELEMETRY_ES_ENDPOINT:?}",
        "credential": "${PROD_PRODUCT_TELEMETRY_ES_ADMIN:?}",
    }
    assert "deployment-control" not in prod_projection["environment"]
    assert prod_projection["environment"]["search-service"][
        "SEARCH_ES_API_KEY"
    ] == "${PROD_SEARCH_OBJECTS_READER:?}"
    assert prod_projection["environment"]["search-service"][
        "SEARCH_ES_WRITER_API_KEY"
    ] == "${PROD_SEARCH_OBJECTS_WRITER:?}"
    assert prod_projection["environment"]["search-service"][
        "SEARCH_ES_WRITER_ENDPOINTS"
    ] == "${PROD_SEARCH_OBJECTS_ENDPOINT:?}"
    assert prod_projection["environment"]["search-service"][
        "SEARCH_ES_WRITER_INDEX"
    ] == "quwoquan_objects"
    assert prod_projection["environment"]["content-service"][
        "SEARCH_ES_API_KEY"
    ] == "${PROD_SEARCH_OBJECTS_WRITER:?}"
    for target, projection in local_projections.items():
        search = projection["environment"]["search-service"]
        assert search["SEARCH_ES_ENABLED"] == "true", target
        assert search["SEARCH_ES_ENDPOINTS"] == "http://elasticsearch:9200", target
        assert search["SEARCH_ES_INDEX"] == "quwoquan_objects", target
        assert search["SEARCH_ES_WRITER_ENABLED"] == "true", target
        assert search["SEARCH_ES_WRITER_ENDPOINTS"] == "http://elasticsearch:9200", target
        assert search["SEARCH_ES_WRITER_INDEX"] == "quwoquan_objects", target
    assert gamma_projection["environment"]["content-service"][
        "CONTENT_MONGO_URI"
    ].startswith("mongodb://mongodb:27017/")
    assert {
        key: value
        for key, value in prod_projection["environment"][
            "recommendation-service"
        ].items()
        if key.startswith("RECOMMENDATION_REDIS_")
    } == {
        "RECOMMENDATION_REDIS_GENERAL_ADDR": "${PROD_RECOMMENDATION_REDIS_ADDR:?}",
        "RECOMMENDATION_REDIS_GENERAL_MODE": "standalone",
        "RECOMMENDATION_REDIS_GENERAL_TLS": "false",
        "RECOMMENDATION_REDIS_REC_ADDR": "${PROD_RECOMMENDATION_REDIS_ADDR:?}",
        "RECOMMENDATION_REDIS_REC_MODE": "standalone",
        "RECOMMENDATION_REDIS_REC_TLS": "false",
    }
    assert {
        key: value
        for key, value in gamma_projection["environment"][
            "recommendation-service"
        ].items()
        if key.startswith("RECOMMENDATION_REDIS_")
    } == {
        "RECOMMENDATION_REDIS_GENERAL_ADDR": "redis:6379",
        "RECOMMENDATION_REDIS_GENERAL_MODE": "standalone",
        "RECOMMENDATION_REDIS_GENERAL_TLS": "false",
        "RECOMMENDATION_REDIS_REC_ADDR": "redis:6379",
        "RECOMMENDATION_REDIS_REC_MODE": "standalone",
        "RECOMMENDATION_REDIS_REC_TLS": "false",
    }
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_RAW_INDEX"
    ] == "app-product-telemetry-raw"
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_AGGREGATE_INDEX"
    ] == "app-product-telemetry-hourly"
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_RAW_INDEX"
    ] == "runtime-diagnostics-raw"
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_AGGREGATE_INDEX"
    ] == "runtime-diagnostics-hourly"
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_API_KEY"
    ] == "${PROD_RUNTIME_LOGS_ES_API_KEY:?}"
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT"
    ] == "${PROD_PRODUCT_TELEMETRY_ES_ENDPOINT:?}"
    assert prod_projection["environment"]["product-ops-service"][
        "PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT"
    ] == "${PROD_PRODUCT_TELEMETRY_ES_ENDPOINT:?}"
    for environment, target in (
        ("alpha", "alpha-local"),
        ("beta", "beta-local"),
        ("gamma", "gamma-local"),
        ("prod", "prod-hosted"),
    ):
        runtime = yaml.safe_load(
            (ROOT / f"quwoquan_ops/environments/{environment}/runtime.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert (
            "user-service.search.objects.writer"
            not in runtime["targets"][target]["dataPlane"]["bindings"]
        )
    assert "deployment-control" not in prod_projection["environment"]
    assert "actual-password" not in json.dumps(prod_projection)


def test_prod_backup_plan_must_cover_explicit_index_members() -> None:
    topology = load_environment_topology()
    plan = yaml.safe_load(
        (ROOT / "quwoquan_ops/environments/prod/backup-recovery.yaml").read_text(
            encoding="utf-8"
        )
    )
    telemetry = next(
        dataset for dataset in plan["datasets"]
        if dataset["id"] == "product-telemetry"
    )
    telemetry["namespaces"].remove("app-product-telemetry-hourly")

    issues = validate_prod_data_plane_backup_coverage(
        topology, backup_plan=plan
    )

    assert any(
        "app-product-telemetry-hourly is outside backup dataset" in issue
        for issue in issues
    )


@pytest.mark.parametrize(
    ("target", "environment"),
    (
        ("alpha-local", "alpha"),
        ("beta-local", "beta"),
        ("gamma-local", "gamma"),
        ("prod-hosted", "prod"),
    ),
)
def test_every_canonical_target_requires_data_plane(
    target: str, environment: str
) -> None:
    topology = load_environment_topology()
    del topology["targets"][target]["dataPlane"]

    issues = validate_environment_topology(topology)

    assert f"{target}: dataPlane is required" in issues


@pytest.mark.parametrize(
    ("environment", "target"),
    (
        ("alpha", "alpha-local"),
        ("beta", "beta-local"),
        ("gamma", "gamma-local"),
        ("prod", "prod-hosted"),
    ),
)
def test_every_canonical_target_resolves_required_contract_graph_resources(
    environment: str, target: str
) -> None:
    runtime = yaml.safe_load(
        (ROOT / f"quwoquan_ops/environments/{environment}/runtime.yaml").read_text(
            encoding="utf-8"
        )
    )
    graph = json.loads(
        (ROOT / "quwoquan_service/generated/contract_graph.json").read_text(
            encoding="utf-8"
        )
    )

    data_plane = runtime["targets"][target]["dataPlane"]

    assert validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name=target
    ) == []



@pytest.mark.parametrize(
    ("environment", "target"),
    (("alpha", "alpha-local"), ("beta", "beta-local")),
)
def test_local_candidate_compose_injects_search_reader_and_writer(
    tmp_path: Path, environment: str, target: str
) -> None:
    candidate = tmp_path / target
    shared = candidate / "packages/runtime-shared"
    shared.mkdir(parents=True)

    manifest = materialize_runtime_topology_package(
        environment,
        target,
        shared,
        repo_root=ROOT,
    )
    result = load_runtime_topology_package(
        candidate,
        environment=environment,
        target=target,
        workload="full",
    )

    merged: dict[str, object] = {}
    for compose_file in result["composeFiles"]:
        compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
        service_core = (compose.get("services") or {}).get("service-core")
        if not isinstance(service_core, dict):
            continue
        environment_values = service_core.get("environment")
        if isinstance(environment_values, dict):
            merged.update(environment_values)

    assert result["dataPlaneBindingDigest"] == manifest["dataPlaneBinding"][
        "bindingDigest"
    ]
    assert merged["SEARCH_ES_ENABLED"] == "true"
    assert merged["SEARCH_ES_ENDPOINTS"] == "http://elasticsearch:9200"
    assert merged["SEARCH_ES_INDEX"] == "quwoquan_objects"
    assert merged["SEARCH_ES_WRITER_ENABLED"] == "true"
    assert merged["SEARCH_ES_WRITER_ENDPOINTS"] == "http://elasticsearch:9200"
    assert merged["SEARCH_ES_WRITER_INDEX"] == "quwoquan_objects"

def test_runtime_package_data_plane_artifact_tamper_blocks(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    shared = candidate / "packages/runtime-shared"
    shared.mkdir(parents=True)
    materialize_runtime_topology_package(
        "gamma",
        "gamma-local",
        shared,
        repo_root=ROOT,
    )
    artifact = shared / "data-plane-binding.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["bindings"]["content-service.mongodb"]["namespace"] = "tampered"
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        RuntimeTopologyPackageError,
        match="data-plane binding artifact drifted",
    ):
        load_runtime_topology_package(
            candidate,
            environment="gamma",
            target="gamma-local",
            workload="full",
        )


def test_named_slot_resource_resolves_when_default_engine_slot_is_absent() -> None:
    """DEC-032 具名 slot：同一服务对同一引擎持有多个逻辑资源时，资源 localName（_ 归一为 -）
    必须与 binding slot 同名；默认 <engine> slot 缺席不再误判为缺 binding。"""
    graph = {
        "objects": [
            {
                "storageResources": [
                    {
                        "localName": "telemetry",
                        "identity": "product-ops-service/product_ops/event_record/telemetry",
                        "engine": "elasticsearch",
                        "role": "append_only_fact",
                        "required": True,
                    },
                    {
                        "localName": "runtime_logs",
                        "identity": "product-ops-service/product_ops/event_record/runtime_logs",
                        "engine": "elasticsearch",
                        "role": "append_only_fact",
                        "required": True,
                    },
                ]
            }
        ]
    }
    telemetry = _binding(
        "product-ops-service",
        "telemetry",
        "elasticsearch",
        "telemetry-elasticsearch",
        "app-product-telemetry-raw",
        {"PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT": {"kind": "endpoint"}},
    )
    runtime_logs = _binding(
        "product-ops-service",
        "runtime-logs",
        "elasticsearch",
        "telemetry-elasticsearch",
        "runtime-diagnostics-raw",
        {"PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT": {"kind": "endpoint"}},
    )
    data_plane = {
        "bindings": {
            "product-ops-service.telemetry": telemetry,
            "product-ops-service.runtime-logs": runtime_logs,
        }
    }

    assert validate_contract_graph_data_plane_bindings(graph, data_plane) == []

    # 具名 slot 缺席时仍 fail closed，不回退到任意同引擎 binding。
    del data_plane["bindings"]["product-ops-service.runtime-logs"]
    issues = validate_contract_graph_data_plane_bindings(
        graph, data_plane, target_name="alpha-local"
    )
    assert issues == [
        "alpha-local: required object resource "
        "product-ops-service/product_ops/event_record/runtime_logs "
        "is missing binding product-ops-service.elasticsearch"
    ]
