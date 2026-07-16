#!/usr/bin/env python3
"""阻断 Go 服务 DDD 反向依赖与公共 runtime 存储驱动泄漏。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = SERVICE_ROOT / "services"
RUNTIME_ROOT = SERVICE_ROOT / "runtime"

IMPORT_RE = re.compile(r'^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?"([^"]+)"', re.MULTILINE)
DB_DRIVER_PREFIXES = (
    "database/sql",
    "github.com/jackc/pgx",
    "github.com/redis/go-redis",
    "go.mongodb.org/mongo-driver",
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


def _production_go_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.go")
        if not path.name.endswith("_test.go") and "tests" not in path.parts
    )


def _imports(path: Path) -> tuple[str, ...]:
    return tuple(IMPORT_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))


def _relative(path: Path) -> str:
    return path.relative_to(SERVICE_ROOT).as_posix()


def _has_driver(import_path: str) -> bool:
    return any(
        import_path == prefix or import_path.startswith(prefix + "/")
        for prefix in DB_DRIVER_PREFIXES
    )


def collect_issues() -> list[str]:
    issues: list[str] = []
    for path in _production_go_files(SERVICES_ROOT):
        relative_parts = path.relative_to(SERVICES_ROOT).parts
        try:
            internal_index = relative_parts.index("internal")
        except ValueError:
            continue
        if len(relative_parts) <= internal_index + 1:
            continue
        layer = relative_parts[internal_index + 1]
        imports = _imports(path)

        if layer == "domain":
            forbidden_fragments = (
                "/internal/application",
                "/internal/adapters",
                "/internal/infrastructure",
            )
        elif layer == "application":
            forbidden_fragments = (
                "/internal/adapters",
                "/internal/infrastructure",
            )
        elif layer == "adapters":
            forbidden_fragments = ("/internal/infrastructure",)
        else:
            forbidden_fragments = ()

        for import_path in imports:
            if any(fragment in import_path for fragment in forbidden_fragments):
                issues.append(
                    f"{_relative(path)}: {layer} 反向依赖 {import_path}"
                )
            if layer in {"domain", "application", "adapters"} and _has_driver(
                import_path
            ):
                issues.append(
                    f"{_relative(path)}: {layer} 直接导入存储驱动 {import_path}"
                )
            if any(fragment in import_path for fragment in RETIRED_IMPORT_FRAGMENTS):
                issues.append(
                    f"{_relative(path)}: 仍导入已退役公共抽象 {import_path}"
                )

    for path in _production_go_files(RUNTIME_ROOT):
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
    print("[service-layering] OK: DDD 依赖方向与 runtime 驱动隔离通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
