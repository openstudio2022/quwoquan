#!/usr/bin/env python3
"""领域服务自治目录的唯一仓库门禁。

该门禁只读取可版本控制的事实：服务本地 contracts、源码路径、四环境入口和
Kustomize 基线。它不读取服务注册表、人工 topology、readiness 或迁移清单。
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "quwoquan_service"
SERVICES_ROOT = SERVICE_ROOT / "services"
OPS_ROOT = ROOT / "quwoquan_ops"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
LAYERS = {"domain", "application", "adapters", "infrastructure"}
KINDS = {
    "aggregate_root",
    "append_only_fact",
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


def load_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("expected YAML mapping")
    return document


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def service_roots() -> list[Path]:
    """仅从服务自身的 contracts/domain.yaml 发现领域服务。"""

    if not SERVICES_ROOT.is_dir():
        return []
    return sorted(
        domain_path.parent.parent
        for domain_path in SERVICES_ROOT.glob("*/contracts/domain.yaml")
        if domain_path.is_file()
    )


def physical_service_roots() -> list[Path]:
    if not SERVICES_ROOT.is_dir():
        return []
    return sorted(path for path in SERVICES_ROOT.iterdir() if path.is_dir())


def domain_service_names() -> set[str]:
    return {service.name for service in service_roots()}


def _compose_ownership_violations(
    service_name: str, services: Any
) -> list[str] | None:
    """Return sorted illegal Compose service keys, or None when ownership is valid.

    A service fragment must include its primary workload and may also declare
    one-shot companions named `{service}-migrate*`.
    """
    if not isinstance(services, dict):
        return ["<non-mapping services>"]
    names = set(services)
    if service_name not in names:
        return sorted(names)
    illegal = sorted(
        name
        for name in names
        if name != service_name and not name.startswith(f"{service_name}-migrate")
    )
    return illegal or None


class Verification:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.objects: dict[tuple[str, str, str], tuple[str, Path, dict[str, Any]]] = {}
        self.contexts: set[tuple[str, str]] = set()
        self.source_owners: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self.routed_objects: set[tuple[str, str, str]] = set()
        self.application_sources: dict[tuple[str, str, str], set[Path]] = defaultdict(set)
        self.object_kinds: Counter[str] = Counter()
        self.aggregate_members = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def verify(self) -> None:
        self.verify_service_set_and_truth_sources()
        self.verify_contracts()
        self.verify_service_templates()
        self.verify_source_and_test_paths()
        self.verify_generated_paths()
        self.verify_dependency_boundaries()
        self.verify_resources_and_migrations()
        self.verify_compose_ownership()
        self.verify_runtime_port_contracts()
        self.verify_special_assets()
        self.verify_kustomize_entries()
        self.verify_no_source_artifacts()
        self.run_subgates()

    def verify_service_set_and_truth_sources(self) -> None:
        for service in physical_service_roots():
            domain_path = service / "contracts" / "domain.yaml"
            if not domain_path.is_file():
                self.error(
                    f"{relative(service)}: 服务根必须声明 contracts/domain.yaml"
                )
        for source in sorted(BANNED_PATHS):
            if (ROOT / source).exists():
                self.error(f"retired second truth source exists: {source}")
        ops_environment_root = OPS_ROOT / "environments"
        unexpected_ops_environment_files = {
            path.name
            for path in ops_environment_root.iterdir()
            if path.is_file() and path.name not in ALLOWED_OPS_ENVIRONMENT_ROOT_FILES
        }
        if unexpected_ops_environment_files:
            self.error(
                "Ops environment root may only contain cross-service technical policy: "
                f"{sorted(unexpected_ops_environment_files)}"
            )
        unexpected_ops_environment_directories = {
            path.name
            for path in ops_environment_root.iterdir()
            if path.is_dir() and path.name not in ALLOWED_OPS_ENVIRONMENT_ROOT_DIRS
        }
        if unexpected_ops_environment_directories:
            self.error(
                "Ops environment root contains an unknown physical environment/technical area: "
                f"{sorted(unexpected_ops_environment_directories)}"
            )
        for service in service_roots():
            allowed_entries = {
                "AGENTS.md",
                "Makefile",
                "build",
                "cmd",
                "config",
                "contracts",
                "deploy",
                "environments",
                "generated",
                "internal",
                "observability",
                "resources",
                "tests",
            }
            if service.name == "recommendation-service":
                allowed_entries.add("pyproject.toml")
            unexpected_entries = {
                child.name for child in service.iterdir() if child.name not in allowed_entries
            }
            if unexpected_entries:
                self.error(
                    f"{service.name}: unsupported service-root entries: "
                    f"{sorted(unexpected_entries)}"
                )
            retired_manifests = set(service.rglob("codegen_*_manifest.yaml"))
            retired_manifests.update(service.rglob("codegen_*manifest.*"))
            for retired_manifest in sorted(retired_manifests):
                self.error(
                    "retired codegen second truth source exists: "
                    f"{relative(retired_manifest)}"
                )
            for retired in (
                "configs",
                "config/environments",
                "deploy/overlays",
                "resources/seeds",
                ".qwq_output",
            ):
                if (service / retired).exists():
                    self.error(f"{service.name}: retired service layout exists: {retired}")

    def contract_owners(self) -> Iterable[tuple[str, Path]]:
        for service in service_roots():
            yield service.name, service / "contracts"
        platform = SERVICE_ROOT / "control-plane/platform-ops/contracts"
        if platform.is_dir():
            yield "platform-ops", platform

    def verify_contracts(self) -> None:
        kinds: Counter[str] = Counter()
        members = 0
        object_contexts: dict[tuple[str, str], set[str]] = defaultdict(set)
        for owner, contracts in self.contract_owners():
            domain_path = contracts / "domain.yaml"
            if not domain_path.is_file():
                self.error(f"{relative(contracts)}: missing domain.yaml")
                continue
            try:
                domain = str(load_yaml(domain_path).get("domain") or "").strip()
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self.error(f"{relative(domain_path)}: {exc}")
                continue
            if not domain or not re.fullmatch(r"[a-z][a-z0-9_]*", domain):
                self.error(f"{relative(domain_path)}: invalid metadata domain {domain!r}")
                continue
            context_names = set()
            for context_path in sorted(contracts.glob("*/context.yaml")):
                context = context_path.parent.name
                context_names.add(context)
                self.contexts.add((domain, context))
            for object_path in sorted(contracts.glob("*/*/object.yaml")):
                context, object_name = object_path.parts[-3:-1]
                if context not in context_names:
                    self.error(f"{relative(object_path)}: missing sibling context.yaml")
                if context == object_name:
                    self.error(
                        f"{relative(object_path)}: bounded context and business object "
                        "must use distinct, intention-revealing names"
                    )
                key = (domain, context, object_name)
                if key in self.objects:
                    previous = self.objects[key]
                    self.error(
                        f"{'.'.join(key)} has two contract owners: {previous[0]} and {owner}"
                    )
                    continue
                try:
                    document = load_yaml(object_path)
                except (OSError, ValueError, yaml.YAMLError) as exc:
                    self.error(f"{relative(object_path)}: {exc}")
                    continue
                kind = str(document.get("kind") or "")
                if kind not in KINDS:
                    self.error(f"{relative(object_path)}: invalid kind={kind!r}")
                kinds[kind] += 1
                raw_members = document.get("members") or {}
                if not isinstance(raw_members, (dict, list)):
                    self.error(f"{relative(object_path)}: members must be mapping/list")
                else:
                    values = raw_members.values() if isinstance(raw_members, dict) else raw_members
                    for member in values:
                        if not isinstance(member, dict) or member.get("kind") not in {
                            "owned_entity",
                            "value_object",
                        }:
                            self.error(
                                f"{relative(object_path)}: aggregate member kind must be owned_entity/value_object"
                            )
                        members += 1
                repeated = {
                    "domain",
                    "domain_id",
                    "bounded_context",
                    "context_id",
                    "object",
                    "object_id",
                    "service",
                    "service_name",
                    "source_path",
                    "test_path",
                    "readiness",
                } & set(document)
                if repeated:
                    self.error(
                        f"{relative(object_path)}: path-derived identity/status repeated: {sorted(repeated)}"
                    )
                self.objects[key] = (owner, object_path, document)
                operations_path = object_path.with_name("operations.yaml")
                if operations_path.is_file():
                    try:
                        operations = load_yaml(operations_path)
                    except (OSError, ValueError, yaml.YAMLError) as exc:
                        self.error(f"{relative(operations_path)}: {exc}")
                    else:
                        api_routes = operations.get("api_routes") or []
                        if not isinstance(api_routes, list):
                            self.error(f"{relative(operations_path)}: api_routes must be a list")
                        elif api_routes:
                            self.routed_objects.add(key)
                object_contexts[(domain, object_name)].add(context)
            for other in contracts.glob("*/*/*.yaml"):
                if other.name != "object.yaml" and re.search(
                    r"(?m)^object_kind\s*:", other.read_text(encoding="utf-8")
                ):
                    self.error(f"{relative(other)}: object_kind may only exist in object.yaml")
        self.object_kinds = kinds
        self.aggregate_members = members
        for (domain, object_name), contexts in object_contexts.items():
            if len(contexts) != 1:
                self.error(
                    f"{domain}.{object_name} appears in multiple contexts: {sorted(contexts)}"
                )

    def service_identity(self, service: Path) -> tuple[str, set[tuple[str, str]]]:
        domain = str(load_yaml(service / "contracts/domain.yaml").get("domain") or "")
        objects = {
            (path.parts[-3], path.parts[-2])
            for path in (service / "contracts").glob("*/*/object.yaml")
        }
        return domain, objects

    def verify_service_templates(self) -> None:
        for service in service_roots():
            for required in (
                "AGENTS.md",
                "Makefile",
                "contracts/domain.yaml",
                "config/schema.yaml",
                "deploy/base/kustomization.yaml",
                "build/Dockerfile",
                "cmd",
                "internal",
                "generated",
                "tests",
            ):
                if not (service / required).exists():
                    self.error(f"{service.name}: missing required {required}")
            dockerfile = service / "build" / "Dockerfile"
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", str(dockerfile)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if ignored.returncode == 0:
                self.error(
                    f"{relative(dockerfile)}: required service Dockerfile is ignored by Git"
                )
            entries = list((service / "cmd").glob("**/main.go")) + list(
                (service / "cmd").glob("**/main.py")
            )
            if not entries:
                self.error(f"{service.name}: cmd has no executable entry")
            if service.name == "recommendation-service":
                if not (service / "pyproject.toml").is_file():
                    self.error("recommendation-service: pyproject.toml is required")
            elif not (SERVICE_ROOT / "go.mod").is_file():
                self.error(f"{service.name}: shared quwoquan_service/go.mod is missing")
            environments_root = service / "environments"
            actual = sorted(
                path.name for path in environments_root.iterdir() if path.is_dir()
            ) if environments_root.is_dir() else []
            if actual != list(ENVIRONMENTS):
                self.error(f"{service.name}: environments are {actual}, want {list(ENVIRONMENTS)}")
                continue
            for environment in ENVIRONMENTS:
                entry = environments_root / environment
                for required in ("config.yaml", "deploy/kustomization.yaml"):
                    if not (entry / required).is_file():
                        self.error(f"{relative(entry)}: missing {required}")
                text = "\n".join(
                    path.read_text(encoding="utf-8", errors="replace")
                    for path in entry.rglob("*")
                    if path.is_file()
                )
                for other in set(ENVIRONMENTS) - {environment}:
                    if re.search(rf"environments[/\\]{other}(?:[/\\]|$)", text):
                        self.error(f"{relative(entry)}: environment inheritance to {other}")

    def verify_source_and_test_paths(self) -> None:
        for service in service_roots():
            domain, objects = self.service_identity(service)
            internal = service / "internal"
            for path in internal.rglob("*"):
                if path.is_dir() and path.name in FUZZY_DIRECTORIES:
                    self.error(f"{relative(path)}: fuzzy business directory is forbidden")
                if not path.is_file():
                    continue
                parts = path.relative_to(internal).parts
                if len(parts) < 4:
                    self.error(f"{relative(path)}: expected <context>/<object>/<layer>/file")
                    continue
                context, object_name, layer = parts[:3]
                if (context, object_name) not in objects:
                    self.error(f"{relative(path)}: has no service-local object contract")
                    continue
                if layer not in LAYERS:
                    self.error(f"{relative(path)}: unknown DDD layer {layer!r}")
                    continue
                key = (domain, context, object_name)
                self.source_owners[key].add(service.name)
                if (
                    layer == "application"
                    and path.suffix in {".go", ".py"}
                    and not path.name.endswith("_test.go")
                    and "__local_contract_test" not in path.name
                ):
                    self.application_sources[key].add(path)
            tests = service / "tests"
            allowed_test_roots = {"local_contract", "api_integration", "support"}
            for child in tests.iterdir() if tests.is_dir() else []:
                if child.name not in allowed_test_roots:
                    self.error(f"{relative(child)}: unsupported service test root")
            for layer in ("local_contract", "api_integration"):
                test_root = tests / layer
                if not test_root.is_dir():
                    continue
                for path in test_root.rglob("*"):
                    if not path.is_file():
                        continue
                    parts = path.relative_to(test_root).parts
                    if len(parts) < 3 or tuple(parts[:2]) not in objects:
                        self.error(f"{relative(path)}: expected <context>/<object>/file")
        for key, owners in self.source_owners.items():
            if len(owners) != 1:
                self.error(f"{'.'.join(key)} has multiple source owners: {sorted(owners)}")
        for key in sorted(self.routed_objects):
            owner, object_path, _ = self.objects[key]
            if owner not in domain_service_names():
                continue
            if not self.application_sources.get(key):
                self.error(
                    f"{relative(object_path.parent)}: api_routes require a non-test "
                    "application source in the same object"
                )

    def verify_generated_paths(self) -> None:
        for service in service_roots():
            domain, objects = self.service_identity(service)
            generated = service / "generated"
            contract_error_owners = {
                tuple(path.relative_to(service / "contracts").parts[:2])
                for path in (service / "contracts").glob("*/*/errors.yaml")
            }
            generated_error_paths = {
                tuple(path.relative_to(generated).parts[:2]): path
                for path in generated.rglob("*")
                if path.is_file()
                and path.name in {"errors.go", "errors.py"}
                and len(path.relative_to(generated).parts) >= 3
            }
            if generated_error_paths:
                missing_error_outputs = contract_error_owners - set(generated_error_paths)
                extra_error_outputs = set(generated_error_paths) - contract_error_owners
                if missing_error_outputs:
                    self.error(
                        f"{service.name}: generated errors are missing object owners "
                        f"{sorted(missing_error_outputs)}"
                    )
                if extra_error_outputs:
                    self.error(
                        f"{service.name}: generated errors have no object contract "
                        f"{sorted(extra_error_outputs)}"
                    )
                for owner, error_path in generated_error_paths.items():
                    header = error_path.read_text(encoding="utf-8", errors="replace")[:2048]
                    sources = set(GENERATED_OBJECT_SOURCE_RE.findall(header))
                    expected_source = {(domain, owner[0], owner[1])}
                    if sources != expected_source:
                        self.error(
                            f"{relative(error_path)}: generated errors must name exactly "
                            f"one owning errors.yaml; sources={sorted(sources)} "
                            f"expected={sorted(expected_source)}"
                        )
            for path in generated.rglob("*"):
                if not path.is_file():
                    continue
                parts = path.relative_to(generated).parts
                if parts == ("openapi.yaml",):
                    if "Code generated" not in path.read_text(
                        encoding="utf-8", errors="replace"
                    )[:512]:
                        self.error(f"{relative(path)}: generated OpenAPI marker is missing")
                    continue
                if len(parts) < 3 or tuple(parts[:2]) not in objects:
                    self.error(f"{relative(path)}: generated output has no object owner")
                    continue
                header = path.read_text(encoding="utf-8", errors="replace")[:2048]
                if "Code generated" not in header:
                    self.error(f"{relative(path)}: generated output marker is missing")
                if "/**/" in header:
                    self.error(
                        f"{relative(path)}: generated source must name one object, not a wildcard"
                    )
                generated_sources = set(GENERATED_OBJECT_SOURCE_RE.findall(header))
                if path.name == "external_provider_bindings.g.go" or "metadata" in path.stem:
                    expected_source = {(domain, parts[0], parts[1])}
                    if generated_sources != expected_source:
                        self.error(
                            f"{relative(path)}: object-derived generated output must name "
                            f"exactly one owning source; sources={sorted(generated_sources)} "
                            f"expected={sorted(expected_source)}"
                        )
                for source_domain, source_context, source_object in generated_sources:
                    known_source = (source_domain, source_context, source_object) in self.objects
                    if not known_source:
                        self.error(
                            f"{relative(path)}: generated source "
                            f"{source_domain}/{source_context}/{source_object} has no object contract"
                        )
                    elif source_domain == domain and (
                        source_context,
                        source_object,
                    ) != tuple(parts[:2]):
                        self.error(
                            f"{relative(path)}: generated owner {domain}/{parts[0]}/{parts[1]} "
                            f"differs from contract source "
                            f"{source_domain}/{source_context}/{source_object}"
                        )
            for path in (service / "internal").rglob("*"):
                if not path.is_file():
                    continue
                if path.name.endswith((".g.go", ".generated.go", ".generated.py")):
                    self.error(f"{relative(path)}: generated output is forbidden under internal")
        control_plane_internal = SERVICE_ROOT / "control-plane" / "platform-ops" / "internal"
        for path in control_plane_internal.rglob("*") if control_plane_internal.is_dir() else []:
            if not path.is_file():
                continue
            if "generated" in path.relative_to(control_plane_internal).parts or path.name.endswith(
                (".g.go", ".generated.go", ".generated.py")
            ):
                self.error(f"{relative(path)}: control-plane generated output is forbidden under internal")

    def verify_dependency_boundaries(self) -> None:
        infrastructure_tokens = (
            "net/http",
            "database/sql",
            "go.mongodb.org",
            "github.com/jackc/pgx",
            "github.com/redis",
            "pymongo",
            "fastapi",
            "sqlalchemy",
        )
        for service in service_roots():
            for path in service.rglob("*"):
                if not path.is_file() or path.suffix not in {".go", ".py"}:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for imported_service, _ in SERVICE_IMPORT_RE.findall(text):
                    if imported_service != service.name:
                        self.error(
                            f"{relative(path)}: cross-service internal/generated import from {imported_service}"
                        )
                parts = path.relative_to(service).parts
                is_test = (
                    path.name.endswith("_test.go")
                    or path.name.startswith("test_")
                    or "__local_contract_test" in path.name
                    or "__api_integration_test" in path.name
                )
                if not is_test and len(parts) >= 4 and parts[0] == "internal":
                    source_context, source_object = parts[1:3]
                    for imported_service, target_context, target_object, target_layer in (
                        OBJECT_PRIVATE_IMPORT_RE.findall(text)
                    ):
                        if imported_service != service.name:
                            continue
                        if (target_context, target_object) != (
                            source_context,
                            source_object,
                        ):
                            self.error(
                                f"{relative(path)}: object {source_context}/{source_object} "
                                f"imports sibling private {target_context}/{target_object}/"
                                f"{target_layer}; depend on its domain/application port or "
                                "compose adapters in cmd"
                            )
                if len(parts) >= 5 and parts[0] == "internal" and parts[3] == "domain":
                    if any(token in text for token in infrastructure_tokens):
                        self.error(f"{relative(path)}: domain imports infrastructure SDK")
                    if "/transport/" in text or "/persistence/" in text:
                        self.error(f"{relative(path)}: domain imports generated transport/persistence")

    def verify_resources_and_migrations(self) -> None:
        for service in service_roots():
            resources = service / "resources"
            allowed_common = {"migrations", "templates", "policies", "skills", "static", "models"}
            if resources.is_dir():
                unexpected = {
                    path.name for path in resources.iterdir() if path.name not in allowed_common
                }
                if unexpected:
                    self.error(
                        f"{service.name}: unsupported common resource roots: {sorted(unexpected)}"
                    )
            for path in resources.rglob("*") if resources.is_dir() else []:
                lowered = {part.lower() for part in path.parts}
                if path.is_file() and lowered & {"fixture", "fixtures", "testdata"}:
                    self.error(f"{relative(path)}: test fixture is forbidden in runtime resources")
            migrations = sorted((resources / "migrations").rglob("*")) if resources.is_dir() else []
            numbers: dict[int, Path] = {}
            for path in migrations:
                if not path.is_file():
                    continue
                match = MIGRATION_RE.match(path.name)
                if not match:
                    self.error(f"{relative(path)}: migration requires numeric prefix")
                    continue
                number = int(match.group(1))
                if number in numbers:
                    self.error(
                        f"{service.name}: duplicate migration number {number}: "
                        f"{relative(numbers[number])}, {relative(path)}"
                    )
                numbers[number] = path
            if numbers and sorted(numbers) != list(range(1, max(numbers) + 1)):
                self.error(f"{service.name}: migration numbering must be contiguous from 001")
            for environment in ("gamma", "prod"):
                seed_root = service / "environments" / environment / "resources" / "seeds"
                if seed_root.exists() and any(path.is_file() for path in seed_root.rglob("*")):
                    self.error(f"{relative(seed_root)}: gamma/prod seed is forbidden")
            for environment in ENVIRONMENTS:
                environment_resources = service / "environments" / environment / "resources"
                if service.name == "content-service":
                    delivery_manifest = (
                        environment_resources / "artifacts" / "media" / "delivery_manifest.yaml"
                    )
                    if delivery_manifest.exists():
                        self.error(
                            f"{relative(delivery_manifest)}: environment media manifests are forbidden; immutable release activation owns public media"
                        )
                if not environment_resources.is_dir():
                    continue
                allowed_environment = {"seeds", "releases", "artifacts"}
                unexpected = {
                    path.name
                    for path in environment_resources.iterdir()
                    if path.name not in allowed_environment
                }
                if unexpected:
                    self.error(
                        f"{relative(environment_resources)}: unsupported resource roots: "
                        f"{sorted(unexpected)}"
                    )
                for category in ("releases", "artifacts"):
                    for manifest in (environment_resources / category).rglob("*.yaml"):
                        try:
                            document = load_yaml(manifest)
                        except (OSError, ValueError, yaml.YAMLError) as exc:
                            self.error(f"{relative(manifest)}: invalid resource manifest: {exc}")
                            continue
                        reference = str(
                            document.get("releaseRef") or document.get("artifactRef") or ""
                        )
                        digest = str(document.get("digest") or "")
                        if not reference or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                            self.error(
                                f"{relative(manifest)}: requires releaseRef/artifactRef and sha256 digest"
                            )
                            continue
                        if reference.startswith("service-resource://"):
                            source = resources / reference.removeprefix("service-resource://")
                            if not source.is_file():
                                self.error(
                                    f"{relative(manifest)}: service resource does not exist: {relative(source)}"
                                )
                                continue
                            actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
                            if actual != digest:
                                self.error(
                                    f"{relative(manifest)}: digest {digest} differs from {actual}"
                                )

    def verify_compose_ownership(self) -> None:
        for service in service_roots():
            path = service / "deploy" / "compose.yaml"
            if not path.is_file():
                self.error(f"{service.name}: active local workload requires deploy/compose.yaml")
                continue
            try:
                services = load_yaml(path).get("services") or {}
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self.error(f"{relative(path)}: invalid Compose fragment: {exc}")
                continue
            illegal = _compose_ownership_violations(service.name, services)
            if illegal is not None:
                self.error(
                    f"{relative(path)}: must own only {service.name} "
                    f"(optional `{service.name}-migrate*` one-shots), got {illegal}"
                )
            for environment_overlay in sorted(
                (service / "environments").glob("*/deploy/compose.yaml")
            ):
                try:
                    overlay_services = load_yaml(environment_overlay).get("services") or {}
                except (OSError, ValueError, yaml.YAMLError) as exc:
                    self.error(
                        f"{relative(environment_overlay)}: invalid service Compose overlay: {exc}"
                    )
                    continue
                illegal = _compose_ownership_violations(service.name, overlay_services)
                if illegal is not None:
                    self.error(
                        f"{relative(environment_overlay)}: must own only {service.name} "
                        f"(optional `{service.name}-migrate*` one-shots), got {illegal}"
                    )

        platform_path = SERVICE_ROOT / "control-plane/platform-ops/deploy/compose.yaml"
        try:
            platform_services = load_yaml(platform_path).get("services") or {}
        except (OSError, ValueError, yaml.YAMLError) as exc:
            self.error(f"{relative(platform_path)}: invalid Compose fragment: {exc}")
        else:
            if set(platform_services) != {"platform-ops-service"}:
                self.error(
                    f"{relative(platform_path)}: must own only platform-ops-service"
                )

        compose_root = OPS_ROOT / "environments" / "compose"
        for path in sorted(compose_root.glob("*.y*ml")):
            try:
                services = load_yaml(path).get("services") or {}
            except (OSError, ValueError, yaml.YAMLError) as exc:
                self.error(f"{relative(path)}: invalid Ops Compose assembly: {exc}")
                continue
            first_party = domain_service_names() | {"platform-ops-service"}
            duplicated: list[str] = []
            for name in sorted(set(services) & first_party):
                service = services.get(name) or {}
                # Merge-only overlays (e.g. gamma ES depends_on) are allowed; full
                # workload copies that redefine image/build must stay in service fragments.
                if isinstance(service, dict) and (
                    "image" in service or "build" in service
                ):
                    duplicated.append(name)
            if duplicated:
                self.error(
                    f"{relative(path)}: first-party workload copies belong to service fragments: "
                    f"{duplicated}"
                )

    def verify_special_assets(self) -> None:
        required = {
            "quwoquan_ops/external/coturn/base/kustomization.yaml",
            "quwoquan_ops/external/livekit/base/kustomization.yaml",
            "quwoquan_service/static/legal/manifest.yaml",
            "quwoquan_service/static/legal/tests/local_contract/manifest_contract_test.py",
            "quwoquan_service/control-plane/platform-ops/build/Dockerfile",
            "quwoquan_service/control-plane/platform-ops/deploy/base/kustomization.yaml",
        }
        for source in sorted(required):
            if not (ROOT / source).is_file():
                self.error(f"required external/static/control-plane asset is missing: {source}")
        if any(path.name == "seed-box" for path in ROOT.rglob("seed-box")):
            self.error("retired seed-box physical directory returned")
        for workload in ("coturn", "livekit"):
            environment_root = OPS_ROOT / "external" / workload / "environments"
            actual = sorted(path.name for path in environment_root.iterdir() if path.is_dir())
            if actual != list(ENVIRONMENTS):
                self.error(f"external {workload}: environment set is {actual}")

    def verify_runtime_port_contracts(self) -> None:
        for service in service_roots():
            deployment_path = service / "deploy/base/deployment.yaml"
            dockerfile_path = service / "build/Dockerfile"
            schema_path = service / "config/schema.yaml"
            try:
                deployment = load_yaml(deployment_path)
                container = deployment["spec"]["template"]["spec"]["containers"][0]
            except (OSError, ValueError, yaml.YAMLError, KeyError, IndexError, TypeError) as exc:
                self.error(f"{relative(deployment_path)}: invalid deployment container: {exc}")
                continue
            ports = [
                int(item["containerPort"])
                for item in container.get("ports") or []
                if isinstance(item, dict) and "containerPort" in item
            ]
            if len(ports) != 1:
                self.error(f"{relative(deployment_path)}: expected one service container port")
                continue
            docker_ports = [
                int(value)
                for value in re.findall(
                    r"(?m)^EXPOSE\s+(\d+)", dockerfile_path.read_text(encoding="utf-8")
                )
            ]
            if docker_ports != ports:
                self.error(
                    f"{service.name}: Docker EXPOSE {docker_ports} differs from deployment {ports}"
                )
            definitions = load_yaml(schema_path).get("configs") or []
            address_key = f"sys.{service.name}.service.http.addr"
            addresses = [
                item.get("default")
                for item in definitions
                if isinstance(item, dict) and item.get("key") == address_key
            ]
            if len(addresses) != 1 or str(addresses[0]) != f":{ports[0]}":
                self.error(
                    f"{service.name}: {address_key} default {addresses} differs from :{ports[0]}"
                )
            env_from = container.get("envFrom") or []
            expected_secret = f"{service.name}-runtime-secrets"
            if not any(
                isinstance(item, dict)
                and isinstance(item.get("secretRef"), dict)
                and item["secretRef"].get("name") == expected_secret
                for item in env_from
            ):
                self.error(f"{service.name}: deployment must envFrom {expected_secret}")
            mounts = container.get("volumeMounts") or []
            if not any(
                isinstance(item, dict)
                and item.get("name") == "runtime-config"
                and item.get("readOnly") is True
                for item in mounts
            ):
                self.error(f"{service.name}: runtime config must be mounted read-only")

    def verify_kustomize_entries(self) -> None:
        builder = shutil.which("kustomize")
        command_prefix = [builder, "build"] if builder else []
        if not command_prefix and shutil.which("kubectl"):
            command_prefix = [shutil.which("kubectl") or "kubectl", "kustomize"]
        if not command_prefix:
            self.error("kustomize or kubectl is required for 60 environment builds")
            return
        entries = [
            service / "environments" / environment / "deploy"
            for service in service_roots()
            for environment in ENVIRONMENTS
        ] + [OPS_ROOT / "environments" / environment for environment in ENVIRONMENTS]
        for entry in entries:
            result = subprocess.run(
                command_prefix + [str(entry)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                tail = "\n".join((result.stdout + result.stderr).splitlines()[-8:])
                self.error(f"{relative(entry)}: kustomize build failed:\n{tail}")

    def verify_no_source_artifacts(self) -> None:
        # Align with gate_repo.sh: purge ephemeral caches before asserting absence.
        # Concurrent local agents may recreate bytecode mid-gate; a single purge+scan
        # keeps the check deterministic without allowing committed cache debt.
        os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        sys.dont_write_bytecode = True
        source_roots = (
            ROOT / "quwoquan_app",
            SERVICE_ROOT,
            ROOT / "quwoquan_data",
            OPS_ROOT,
        )
        for source_root in source_roots:
            if not source_root.is_dir():
                continue
            for path in source_root.rglob("*"):
                if path.name in {"__pycache__", ".pytest_cache"}:
                    shutil.rmtree(path, ignore_errors=True)
                elif path.suffix in {".pyc", ".pyo"} and path.is_file():
                    path.unlink(missing_ok=True)
        for source_root in source_roots:
            if not source_root.is_dir():
                continue
            for path in source_root.rglob("*"):
                if path.name in {"__pycache__", ".pytest_cache"} or path.suffix in {
                    ".pyc",
                    ".pyo",
                }:
                    self.error(f"source-tree cache is forbidden: {relative(path)}")
                if path.is_file() and (path.name in {".coverage", "coverage.out"} or path.suffix == ".test"):
                    self.error(f"source-tree test artifact is forbidden: {relative(path)}")

    def run_subgates(self) -> None:
        commands = [
            (
                ["bash", "quwoquan_service/scripts/runtime/verify_service_config_layout.sh"],
                "service config ownership",
            ),
            (
                [sys.executable, "quwoquan_ops/gate/verify_environment_assembly.py"],
                "derived environment topology",
            ),
            (
                [sys.executable, "quwoquan_ops/gate/verify_prod_plane_access_isolation.py"],
                "prod access isolation",
            ),
        ]
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        for command, label in commands:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
                self.error(f"{label} failed:\n{tail}")


def main() -> int:
    verification = Verification()
    verification.verify()
    if verification.errors:
        print("[verify-service-architecture] FAIL")
        for error in verification.errors:
            print(f"  - {error}")
        return 1
    summary = {
        "services": len(service_roots()),
        "contexts": len(verification.contexts),
        "objects": len(verification.objects),
        "objectKinds": dict(sorted(verification.object_kinds.items())),
        "aggregateMembers": verification.aggregate_members,
        "sourceObjects": len(verification.source_owners),
        "serviceEnvironmentEntries": len(service_roots()) * len(ENVIRONMENTS),
        "opsEnvironmentEntries": len(ENVIRONMENTS),
    }
    print("[verify-service-architecture] OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
