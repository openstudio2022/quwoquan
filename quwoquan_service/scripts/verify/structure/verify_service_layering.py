#!/usr/bin/env python3
"""阻断服务层反向依赖、存储驱动泄漏与缺失的 API 集成证据。"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root, require_scan_root  # noqa: E402

SERVICE_ROOT = require_scan_root(
    repository_root() / "quwoquan_service", "service-layering service root"
)

IMPORT_RE = re.compile(r'^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?"([^"]+)"', re.MULTILINE)
DB_DRIVER_PREFIXES = (
    "database/sql",
    "github.com/jackc/pgx",
    "github.com/redis/go-redis",
    "go.mongodb.org/mongo-driver",
)
PYTHON_DRIVER_PREFIXES = (
    "asyncpg",
    "motor",
    "pymongo",
    "psycopg",
    "redis",
    "sqlalchemy",
)
PUBLIC_GENERIC_TOKENS = (
    "GenericAggregateStore",
    "GenericSliceReader",
    "BaseFacade",
)
RETIRED_IMPORT_FRAGMENTS = (
    "quwoquan_service/runtime/repository",
    "quwoquan_service/runtime/registry",
)
DDD_LAYERS = frozenset({"domain", "application", "adapters", "infrastructure"})
FORBIDDEN_LAYER_IMPORTS = {
    "domain": frozenset({"application", "adapters", "infrastructure"}),
    "application": frozenset({"adapters", "infrastructure"}),
    "adapters": frozenset({"infrastructure"}),
    "infrastructure": frozenset(),
}


class LayerLocation:
    def __init__(
        self,
        service: str,
        context: str,
        object_name: str,
        layer: str,
    ) -> None:
        self.service = service
        self.context = context
        self.object_name = object_name
        self.layer = layer


def _services_root() -> Path:
    return SERVICE_ROOT / "services"


def _runtime_root() -> Path:
    return SERVICE_ROOT / "runtime"


def _is_production_source(path: Path) -> bool:
    if path.suffix not in {".go", ".py"}:
        return False
    if "tests" in path.parts or "testdata" in path.parts:
        return False
    if path.name.endswith("_test.go"):
        return False
    return not (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name.endswith("_test.py")
    )


def _production_source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for pattern in ("*.go", "*.py")
        for path in root.rglob(pattern)
        if _is_production_source(path)
    )


def _go_imports(path: Path) -> tuple[str, ...]:
    return tuple(IMPORT_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))


def _python_imports(path: Path) -> tuple[str, ...]:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return ()

    try:
        relative = path.relative_to(SERVICE_ROOT)
    except ValueError:
        return ()
    package = list(relative.with_suffix("").parts[:-1])
    if path.name == "__init__.py":
        package = list(relative.parts[:-1])

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package) + 1:
                    continue
                base = package[: len(package) - node.level + 1]
                if node.module:
                    base.extend(node.module.split("."))
                imports.append(".".join(base))
            elif node.module:
                imports.append(node.module)
    return tuple(imports)


def _imports(path: Path) -> tuple[str, ...]:
    if path.suffix == ".go":
        return _go_imports(path)
    return _python_imports(path)


def _relative(path: Path) -> str:
    return path.relative_to(SERVICE_ROOT).as_posix()


def _has_go_driver(import_path: str) -> bool:
    return any(
        import_path == prefix or import_path.startswith(prefix + "/")
        for prefix in DB_DRIVER_PREFIXES
    )


def _has_python_driver(import_path: str) -> bool:
    normalized = import_path.lstrip(".")
    return any(
        normalized == prefix or normalized.startswith(prefix + ".")
        for prefix in PYTHON_DRIVER_PREFIXES
    )


def _has_driver(import_path: str) -> bool:
    return _has_go_driver(import_path) or _has_python_driver(import_path)


def _layer_location_from_source(path: Path) -> LayerLocation | None:
    try:
        parts = path.relative_to(_services_root()).parts
    except ValueError:
        return None
    try:
        internal_index = parts.index("internal")
    except ValueError:
        return None
    if len(parts) <= internal_index + 3:
        return None
    layer = parts[internal_index + 3]
    if layer not in DDD_LAYERS:
        return None
    return LayerLocation(
        service=parts[0],
        context=parts[internal_index + 1],
        object_name=parts[internal_index + 2],
        layer=layer,
    )


def _layer_location_from_import(import_path: str) -> LayerLocation | None:
    separator = "." if "/" not in import_path else "/"
    parts = import_path.split(separator)
    try:
        services_index = parts.index("services")
        internal_index = parts.index("internal", services_index + 1)
    except ValueError:
        return None
    if (
        len(parts) <= internal_index + 3
        or services_index + 1 >= len(parts)
        or internal_index != services_index + 2
    ):
        return None
    layer = parts[internal_index + 3]
    if layer not in DDD_LAYERS:
        return None
    return LayerLocation(
        service=parts[services_index + 1],
        context=parts[internal_index + 1],
        object_name=parts[internal_index + 2],
        layer=layer,
    )


def _layer_dependency_issues(
    path: Path,
    source: LayerLocation,
    import_path: str,
) -> list[str]:
    target = _layer_location_from_import(import_path)
    if target is None:
        return []

    issues: list[str] = []
    if target.service != source.service:
        issues.append(
            f"{_relative(path)}: {source.layer} 跨服务导入内部实现 {import_path}"
        )
        return issues
    if target.layer in FORBIDDEN_LAYER_IMPORTS[source.layer]:
        issues.append(
            f"{_relative(path)}: {source.layer} 反向依赖 {import_path}"
        )
    if (
        (target.context, target.object_name)
        != (source.context, source.object_name)
        and target.layer in {"adapters", "infrastructure"}
    ):
        issues.append(
            f"{_relative(path)}: {source.layer} 跨对象导入私有 "
            f"{target.layer} {import_path}"
        )
    return issues


def _api_routes(operations_path: Path) -> tuple[tuple[str, str], ...]:
    routes: list[tuple[str, str]] = []
    in_api_routes = False
    current_method = ""
    for line in operations_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("api_routes:"):
            in_api_routes = line.strip() != "api_routes: []"
            continue
        if (
            in_api_routes
            and line
            and not line.startswith((" ", "\t", "- "))
        ):
            break
        if not in_api_routes:
            continue
        stripped = line.strip()
        if stripped.startswith("- method:"):
            current_method = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("method:"):
            current_method = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("path:"):
            routes.append((current_method, stripped.split(":", 1)[1].strip()))
    return tuple(routes)


def _api_evidence_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and (
            path.name.endswith("_test.go")
            or path.name.endswith("_test.py")
            or path.name.startswith("test_")
        )
    )


def _api_evidence_issues(services_root: Path) -> list[str]:
    issues: list[str] = []
    for operations_path in sorted(services_root.glob("*/contracts/**/operations.yaml")):
        routes = _api_routes(operations_path)
        if not routes:
            continue
        relative = operations_path.relative_to(services_root)
        service, _, context, object_name, _ = relative.parts
        source_root = services_root / service / "internal" / context / object_name
        if not any(_is_production_source(path) for path in source_root.rglob("*")):
            issues.append(
                f"{operations_path.relative_to(SERVICE_ROOT).as_posix()}: "
                f"api_routes 对象缺少源码根 internal/{context}/{object_name}"
            )
            continue

        evidence_root = services_root / service / "tests" / "api_integration"
        if _api_evidence_files(evidence_root):
            # HTTP adapters can compose several objects in one service-level
            # handler, so business tests deliberately need not mirror the
            # contract object's directory. An executable L2 suite is the
            # service's API evidence for every routed object it composes.
            continue

        local_evidence_root = (
            services_root
            / service
            / "tests"
            / "local_contract"
            / context
            / object_name
        )
        local_evidence = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in _api_evidence_files(local_evidence_root)
        )
        if not any(route_path in local_evidence for _, route_path in routes):
            issues.append(
                f"{operations_path.relative_to(SERVICE_ROOT).as_posix()}: "
                "api_routes 对象缺少 api_integration API evidence"
            )
    return issues


def collect_issues() -> list[str]:
    issues: list[str] = []
    services_root = _services_root()
    service_sources = _production_source_files(services_root)
    if not services_root.is_dir():
        issues.append("services: canonical service source root does not exist")
    elif not service_sources:
        issues.append("services: scanner matched zero production Go/Python sources")
    for path in service_sources:
        source = _layer_location_from_source(path)
        imports = _imports(path)
        for import_path in imports:
            if source is not None:
                issues.extend(_layer_dependency_issues(path, source, import_path))
            if source is not None and source.layer in {
                "domain",
                "application",
                "adapters",
            } and _has_driver(import_path):
                issues.append(
                    f"{_relative(path)}: "
                    f"{source.layer} 直接导入存储驱动 {import_path}"
                )
            if any(fragment in import_path for fragment in RETIRED_IMPORT_FRAGMENTS):
                issues.append(
                    f"{_relative(path)}: 仍导入已退役公共抽象 {import_path}"
                )

    for path in _production_source_files(_runtime_root()):
        imports = _imports(path)
        for import_path in imports:
            if _has_driver(import_path):
                issues.append(
                    f"{_relative(path)}: runtime 公共层直接导入存储驱动 {import_path}"
                )
            if any(fragment in import_path for fragment in RETIRED_IMPORT_FRAGMENTS):
                issues.append(
                    f"{_relative(path)}: 仍导入已退役公共抽象 {import_path}"
                )
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in PUBLIC_GENERIC_TOKENS:
            if token in text:
                issues.append(
                    f"{_relative(path)}: runtime 公共层禁止声明 {token}"
                )

    issues.extend(_api_evidence_issues(services_root))
    return sorted(set(issues))


def main() -> int:
    issues = collect_issues()
    if issues:
        for issue in issues:
            print(f"[service-layering] FAIL: {issue}", file=sys.stderr)
        print(
            f"[service-layering] FAIL: 共 {len(issues)} 个分层违规",
            file=sys.stderr,
        )
        return 1
    print(
        "[service-layering] OK: Go/Python DDD 依赖、驱动隔离与 API evidence 通过"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
