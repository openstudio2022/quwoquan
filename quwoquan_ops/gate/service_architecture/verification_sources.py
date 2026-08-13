"""Verification 源码归属检查段：对象源码/测试路径、生成物归属与依赖边界。

原类中的 ``verify_kind_aware_object_implementation`` 因 object_path_map 门禁的
AST 镜像必须留在入口文件 ``verify_service_architecture.py``；本模块的
``verify_source_and_test_paths`` 经 ``self`` 动态调用它。
"""
from __future__ import annotations

from .constants import (
    FUZZY_DIRECTORIES,
    GENERATED_OBJECT_SOURCE_RE,
    LAYERS,
    OBJECT_PRIVATE_IMPORT_RE,
    SERVICE_IMPORT_RE,
    SERVICE_ROOT,
)
from .repository import domain_service_names, relative, service_roots
from .source_analysis import (
    is_substantive_implementation_source,
    is_substantive_test_source,
    lifecycle_handler_binding_issues,
    valid_object_test_spec_refs,
)


class SourceVerificationMixin:
    """承载原 Verification 类中源码/生成物/依赖边界方法，方法体逐字搬移。"""

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
                if is_substantive_implementation_source(path):
                    self.source_owners[key].add(service.name)
                    self.layer_sources[key][layer].add(path)
                    if layer == "application":
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
                        continue
                    key = (domain, parts[0], parts[1])
                    substantive = is_substantive_test_source(path)
                    if layer == "local_contract" and substantive:
                        self.local_contract_objects.add(key)
                    elif layer == "api_integration" and substantive:
                        self.api_integration_objects.add(key)
                    if substantive:
                        refs, issues = valid_object_test_spec_refs(path)
                        self.object_test_spec_refs[key].update(refs)
                        for issue in issues:
                            self.error(f"{relative(path)}: {issue}")
        platform = SERVICE_ROOT / "control-plane/platform-ops"
        if platform.is_dir():
            domain, objects = self.service_identity(platform)
            internal = platform / "internal"
            for path in internal.rglob("*"):
                if not path.is_file():
                    continue
                parts = path.relative_to(internal).parts
                if len(parts) < 4:
                    self.error(f"{relative(path)}: expected <context>/<object>/<layer>/file")
                    continue
                context, object_name, layer = parts[:3]
                if (context, object_name) not in objects:
                    self.error(f"{relative(path)}: has no platform-ops object contract")
                    continue
                if layer not in LAYERS:
                    self.error(f"{relative(path)}: unknown DDD layer {layer!r}")
                    continue
                key = (domain, context, object_name)
                if is_substantive_implementation_source(path):
                    self.source_owners[key].add("platform-ops")
                    self.layer_sources[key][layer].add(path)
                    if layer == "application":
                        self.application_sources[key].add(path)
            for layer in ("local_contract", "api_integration"):
                test_root = platform / "tests" / layer
                for path in test_root.rglob("*") if test_root.is_dir() else []:
                    if not path.is_file():
                        continue
                    parts = path.relative_to(test_root).parts
                    if len(parts) < 3 or tuple(parts[:2]) not in objects:
                        self.error(f"{relative(path)}: expected <context>/<object>/file")
                        continue
                    key = (domain, parts[0], parts[1])
                    substantive = is_substantive_test_source(path)
                    if layer == "local_contract" and substantive:
                        self.local_contract_objects.add(key)
                    elif layer == "api_integration" and substantive:
                        self.api_integration_objects.add(key)
                    if substantive:
                        refs, issues = valid_object_test_spec_refs(path)
                        self.object_test_spec_refs[key].update(refs)
                        for issue in issues:
                            self.error(f"{relative(path)}: {issue}")
        self.verify_lifecycle_entrypoint_sources()
        for key, owners in self.source_owners.items():
            if len(owners) != 1:
                self.error(f"{'.'.join(key)} has multiple source owners: {sorted(owners)}")
        self.verify_kind_aware_object_implementation()
        for key, (owner, object_path, _) in sorted(self.objects.items()):
            if owner not in domain_service_names() and owner != "platform-ops":
                continue
            if not self.source_owners.get(key):
                self.error(
                    f"{relative(object_path.parent)}: canonical object requires "
                    "object-local non-generated source"
                )
        for key in sorted(self.entrypoint_objects()):
            owner, object_path, _ = self.objects[key]
            if owner not in domain_service_names() and owner != "platform-ops":
                continue
            if not self.application_sources.get(key):
                self.error(
                    f"{relative(object_path.parent)}: typed entrypoint requires a non-test "
                    "application source in the same object"
                )
        for key, (_, object_path, _) in sorted(self.objects.items()):
            if key not in self.local_contract_objects:
                self.error(
                    f"{relative(object_path.parent)}: canonical object requires "
                    "object-local local_contract evidence"
                )
            if key not in self.object_test_spec_refs:
                self.error(
                    f"{relative(object_path.parent)}: canonical object requires at least "
                    "one substantive object-local test with a valid feature-tree "
                    "UAT/DOM/SIT/GWT spec_ref"
                )
        for key in sorted(self.entrypoint_objects()):
            _, object_path, _ = self.objects[key]
            if key not in self.api_integration_objects:
                self.error(
                    f"{relative(object_path.parent)}: routed/subscribed object requires "
                    "object-local api_integration evidence"
                )

    def entrypoint_objects(self) -> set[tuple[str, str, str]]:
        return (
            self.routed_objects
            | self.runtime_entrypoint_objects
            | self.lifecycle_entrypoint_objects
        )

    def verify_lifecycle_entrypoint_sources(self) -> None:
        for key, consumers in sorted(self.lifecycle_entrypoint_candidates.items()):
            _, object_path, _ = self.objects[key]
            context, object_name = key[1:]
            object_source_root = (
                object_path.parents[2].parent / "internal" / context / object_name
            )
            source_paths = set()
            for layer in ("application", "adapters"):
                source_paths.update(self.layer_sources.get(key, {}).get(layer, set()))
            issues = lifecycle_handler_binding_issues(
                consumers,
                object_source_root,
                source_paths,
            )
            if issues:
                for issue in issues:
                    self.error(f"{relative(object_path)}: {issue}")
                continue
            self.lifecycle_entrypoint_objects.add(key)

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
