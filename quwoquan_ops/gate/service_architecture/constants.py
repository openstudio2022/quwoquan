"""领域服务架构门禁的扫描根、DDD 层/对象 kind 规则表与正则常量唯一定义处。"""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "quwoquan_service"
SERVICES_ROOT = SERVICE_ROOT / "services"
OPS_ROOT = ROOT / "quwoquan_ops"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
LAYERS = {"domain", "application", "adapters", "infrastructure"}
KINDS = {
    "aggregate_root",
    "append_only_fact",
    "process_manager",
    "projection",
    "external_reference",
    "runtime_session",
}
FUZZY_DIRECTORIES = {"common", "utils", "helpers", "manager", "misc"}
BANNED_PATHS = {
    "quwoquan_service/contracts/metadata/business_object_map.yaml",
    "quwoquan_service/contracts/metadata/entity_catalog.yaml",
    "quwoquan_service/contracts/metadata/event_catalog.yaml",
    "quwoquan_service/service_asset_profiles.json",
    "quwoquan_ops/environments/environment_topology_manifest.yaml",
    "quwoquan_ops/environments/process_domain_mapping.yaml",
    "quwoquan_ops/environments/process_domain_plane_mapping.yaml",
    "quwoquan_ops/environments/module_package_mapping.yaml",
    "quwoquan_ops/environments/workload_topology_inventory.yaml",
    "quwoquan_ops/environments/workloads",
    "quwoquan_ops/environments/kustomization",
    "quwoquan_ops/environments/provider_conformance_manifest.yaml",
    "quwoquan_ops/environments/external_provider_bindings.yaml",
    "quwoquan_ops/environments/reliable_task_module_catalog.yaml",
    "quwoquan_ops/environments/reliable_task_retention_policy.yaml",
    "quwoquan_ops/environments/content_release_readiness.yaml",
    "quwoquan_ops/environments/content_sampling_manifest.yaml",
    "quwoquan_ops/environments/gamma_curated_media_bundle.json",
    "quwoquan_service/services/content-service/environments/gamma/resources/artifacts/media/gamma_curated_media_bundle.json",
    "quwoquan_ops/environments/media_delivery_manifest.json",
    "quwoquan_ops/environments/media_slice_registry.json",
    "quwoquan_ops/environments/gamma_validation_suites.json",
    "quwoquan_ops/environments/gray_rollout_stages.yaml",
    "quwoquan_ops/environments/gray_routing_policy.yaml",
    "quwoquan_ops/environments/local-gamma",
    "docs/external_service_registry.yaml",
    "docs/external_service_dependency_registry.md",
    "quwoquan_service/contracts/metadata/_control_plane/domain_onboarding_schema.yaml",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/user_pool.json",
    "quwoquan_service/services/chat-service/codegen_chat_service_manifest.yaml",
    "quwoquan_service/services/content-service/codegen_storage_manifest.yaml",
    "quwoquan_service/services/tag-service/codegen_storage_manifest.yaml",
    "quwoquan_service/services/user-service/codegen_storage_manifest.yaml",
}
ALLOWED_OPS_ENVIRONMENT_ROOT_FILES = {
    "commit_gate_sla_verification.json",
    "commit_gate_timing_baseline.json",
    "data_execution_fleet.json",
    "domain_governance.yaml",
    "local_env_port_manifest.yaml",
    "output_layout_manifest.yaml",
    "output_layout_reconciliation_plan.schema.json",
    "pr_gate_timing_budgets.json",
    "provider_conformance_evidence.schema.json",
    "release_video_delivery_evidence.schema.json",
}
ALLOWED_OPS_ENVIRONMENT_ROOT_DIRS = {
    "alpha",
    "beta",
    "gamma",
    "prod",
    "cloud-providers",
    "compose",
    "evidence",
    "provider_conformance_prerequisites",
    "verify",
}
SERVICE_IMPORT_RE = re.compile(
    r"quwoquan_service/services/([^/\"'\s]+)/(internal|generated)(?:/|\"|'|\s)"
)
OBJECT_PRIVATE_IMPORT_RE = re.compile(
    r"quwoquan_service/services/([^/\"'\s]+)/internal/"
    r"([a-z][a-z0-9_]*)/([a-z][a-z0-9_]*)/"
    r"(adapters|infrastructure)(?:/|\"|'|\s)"
)
MIGRATION_RE = re.compile(r"^(\d+)[_-].+")
GENERATED_OBJECT_SOURCE_RE = re.compile(
    r"(?:from\s+|contracts/metadata/)([a-z][a-z0-9_]*)/"
    r"([a-z][a-z0-9_]*)/([a-z][a-z0-9_]*)/"
    r"[a-z][a-z0-9_]*\.yaml"
)
GENERIC_OBJECT_DESCRIPTION_RE = re.compile(
    r"(?:领域对象契约|domain\s+object\s+contract|business\s+object\s+contract)",
    re.IGNORECASE,
)
OBJECT_TEST_SPEC_REF_RE = re.compile(
    r"(?m)^\s*(?://|#)\s*spec_ref:\s*"
    r"(specs/feature-tree/(?:[A-Za-z0-9_.-]+/)*spec\.md)#"
    r"((?:uat|dom|sit|gwt)-\d{3,})\b",
    re.IGNORECASE,
)
OBJECT_ACCESS_BY_KIND = {
    "aggregate_root": {
        "commands": "aggregate_facade",
        "queries": {"named_reader", "none"},
        "cross_context": {"public_contract_only", "event_only"},
    },
    "append_only_fact": {
        "commands": "append_only_sink",
        "queries": {"named_reader", "none"},
        "cross_context": {"event_only", "public_contract_only"},
    },
    # 长流程编排器（saga）的命令面是 process_facade，不复用 aggregate_facade：
    # 调用方推进/取消/恢复的是流程，不是聚合状态。queries 的收紧条件见
    # PROCESS_MANAGER_PUBLIC_QUERY_ACCESS。
    "process_manager": {
        "commands": "process_facade",
        "queries": {"named_reader", "none"},
        "cross_context": {"public_contract_only", "event_only"},
    },
    "projection": {
        "commands": "none",
        "queries": "named_reader",
        "cross_context": "public_contract_only",
    },
    "runtime_session": {
        "commands": "session_facade",
        "queries": "named_reader",
        "cross_context": "public_contract_only",
    },
    "external_reference": {
        "commands": "none",
        "queries": "external_port",
        "cross_context": "public_contract_only",
    },
}
#: 经公开合同暴露的 process_manager 必须给出具名状态读取面：外部调用方需要能查
#: 进度与终态。只经事件参与的内部 saga（cross_context=event_only）没有外部调用方，
#: 可以没有 reader。与 Go 侧 validate.validateObjectAccess 的 process_manager 分支同源。
PROCESS_MANAGER_PUBLIC_QUERY_ACCESS = "named_reader"
OBJECT_VERSION_SOURCE_BY_KIND = {
    "aggregate_root": {"field", "store_commit"},
    "append_only_fact": {"immutable"},
    # saga 的进度真相是 checkpoint，不是聚合版本。
    "process_manager": {"checkpoint"},
    "projection": {"checkpoint"},
    "runtime_session": {"session"},
    "external_reference": {"external"},
}
RUNTIME_ENTRYPOINT_KIND_BY_OBJECT_KIND = {
    "aggregate_root": set(),
    "append_only_fact": {"subscription", "internal_port"},
    # 与 aggregate_root 同口径：事件消费入口经 object.yaml#lifecycle.event_consumers
    # 声明，不再走 operations.yaml#runtime_entrypoints。
    "process_manager": set(),
    "projection": {"projector"},
    "runtime_session": {"middleware"},
    "external_reference": {"external_port"},
}
LIFECYCLE_CONSUMER_KINDS = {"projector", "event_handler", "subscription"}
LIFECYCLE_CONSUMER_IDEMPOTENCY = {
    "event_id",
    "aggregate_version",
    "identity_payload_digest",
    "transaction_identity",
}
LIFECYCLE_ONLY_ENTRYPOINT_KINDS = {"projection"}
CANONICAL_EVENT_REF_RE = re.compile(
    r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*$"
)

# Stable service-owned resource root-entry roles. These are layout semantics enforced by
# this gate, not an asset registry: services still own the actual resources and
# are discovered solely from their physical directories.
COMMON_RESOURCE_ROOT_ROLES = {
    "coverage-toolchain.lock": "coverage_toolchain_lock",
    "migrations": "schema_migration",
    "templates": "runtime_template",
    "policies": "runtime_policy",
    "skill_packages": "controlled_publisher_source",
    "skills": "immutable_runtime_asset",
    "static": "static_asset",
    "models": "model_asset",
}
SKILL_PACKAGE_SOURCE_RELATIVE_ROOT = Path("skill_packages/official")
SKILL_PACKAGE_RUNTIME_RELATIVE_ROOT = Path("skills/packages/official")
