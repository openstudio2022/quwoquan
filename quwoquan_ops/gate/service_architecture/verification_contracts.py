"""Verification 契约与模板检查段：服务集合、对象契约、服务模板与环境自治。"""
from __future__ import annotations

from collections import Counter, defaultdict
import re
import subprocess
from pathlib import Path
from typing import Iterable

import yaml

from .constants import (
    ALLOWED_OPS_ENVIRONMENT_ROOT_DIRS,
    ALLOWED_OPS_ENVIRONMENT_ROOT_FILES,
    BANNED_PATHS,
    ENVIRONMENTS,
    KINDS,
    OPS_ROOT,
    ROOT,
    RUNTIME_ENTRYPOINT_KIND_BY_OBJECT_KIND,
    SERVICE_ROOT,
)
from .object_semantics import (
    lifecycle_authored_consumers,
    object_contract_semantic_issues,
    object_entrypoint_mode,
    snake_to_pascal,
)
from .repository import load_yaml, physical_service_roots, relative, service_roots


class ContractVerificationMixin:
    """承载原 Verification 类中契约/模板相关方法，方法体逐字搬移。"""

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
                for issue in object_contract_semantic_issues(document):
                    self.error(f"{relative(object_path)}: {issue}")
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
                if not operations_path.is_file():
                    self.error(
                        f"{relative(object_path.parent)}: canonical object requires "
                        "operations.yaml with one HTTP or typed non-HTTP entrypoint"
                    )
                else:
                    try:
                        operations = load_yaml(operations_path)
                    except (OSError, ValueError, yaml.YAMLError) as exc:
                        self.error(f"{relative(operations_path)}: {exc}")
                    else:
                        raw_api_routes = operations.get("api_routes") or []
                        raw_runtime_entrypoints = (
                            operations.get("runtime_entrypoints") or []
                        )
                        api_routes = (
                            raw_api_routes if isinstance(raw_api_routes, list) else []
                        )
                        runtime_entrypoints = (
                            raw_runtime_entrypoints
                            if isinstance(raw_runtime_entrypoints, list)
                            else []
                        )
                        if not isinstance(raw_api_routes, list):
                            self.error(f"{relative(operations_path)}: api_routes must be a list")
                        elif api_routes:
                            self.routed_objects.add(key)
                        if not isinstance(raw_runtime_entrypoints, list):
                            self.error(
                                f"{relative(operations_path)}: runtime_entrypoints must be a list"
                            )
                        elif runtime_entrypoints:
                            self.runtime_entrypoint_objects.add(key)
                            runtime_entrypoint = runtime_entrypoints[0]
                            runtime_kind = str(
                                runtime_entrypoint.get("kind")
                                if isinstance(runtime_entrypoint, dict)
                                else ""
                            ).strip()
                            self.runtime_entrypoint_kinds[key] = runtime_kind
                            allowed_runtime_kinds = (
                                RUNTIME_ENTRYPOINT_KIND_BY_OBJECT_KIND.get(kind, set())
                            )
                            if runtime_kind not in allowed_runtime_kinds:
                                self.error(
                                    f"{relative(operations_path)}: kind={kind} requires "
                                    "runtime_entrypoints.kind in "
                                    f"{sorted(allowed_runtime_kinds)}, got {runtime_kind!r}"
                                )
                            if isinstance(runtime_entrypoint, dict):
                                application = runtime_entrypoint.get("application") or {}
                                actual_owner = (
                                    application.get("object_owner")
                                    if isinstance(application, dict)
                                    else None
                                )
                                expected_owner = snake_to_pascal(object_name)
                                if actual_owner != expected_owner:
                                    self.error(
                                        f"{relative(operations_path)}: runtime entrypoint "
                                        "application.object_owner must be "
                                        f"{expected_owner}, got {actual_owner!r}"
                                    )
                        lifecycle_consumers: list[dict[str, str]] = []
                        lifecycle_issues: list[str] = []
                        if not api_routes and not runtime_entrypoints:
                            lifecycle_consumers, lifecycle_issues = (
                                lifecycle_authored_consumers(document)
                            )
                            for issue in lifecycle_issues:
                                self.error(f"{relative(object_path)}: {issue}")
                        entry_mode, entrypoint_issues = object_entrypoint_mode(
                            kind,
                            api_routes,
                            runtime_entrypoints,
                            lifecycle_consumers if not lifecycle_issues else [],
                        )
                        for issue in entrypoint_issues:
                            self.error(f"{relative(operations_path)}: {issue}")
                        if entry_mode == "lifecycle":
                            self.lifecycle_entrypoint_candidates[key] = lifecycle_consumers
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
