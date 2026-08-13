"""声明侧：解析两个声明源（对象 errors.yaml 与 runtime_failure_codes.yaml）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from .constants import RUNTIME_FAILURE_CODES_YAML, SERVICE_DIR
from .models import ErrorDeclaration, _read


def _iter_declaration_entries(document: object) -> list[dict]:
    """吃下三种顶层形态：裸列表、`errors:` 键、`codes:` 键。

    条目内部的块形态与 flow 形态由 YAML parser 统一成 mapping，不需要区分。
    """
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get("errors")
        if items is None:
            items = document.get("codes")
        if items is None:
            items = []
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def declaration_sources(root: Path) -> list[Path]:
    sources: list[Path] = []
    service_root = root / SERVICE_DIR
    if service_root.is_dir():
        sources.extend(sorted(service_root.rglob("errors.yaml")))
    runtime_codes = root / RUNTIME_FAILURE_CODES_YAML
    if runtime_codes.is_file():
        sources.append(runtime_codes)
    return sources


def _entry_surfaces(entry: dict) -> tuple[str, ...]:
    surfaces: list[str] = []
    for emission in entry.get("emitted_by") or []:
        surface = emission if isinstance(emission, str) else emission.get("surface") if isinstance(emission, dict) else None
        if isinstance(surface, str) and surface.strip() and surface.strip() not in surfaces:
            surfaces.append(surface.strip())
    return tuple(surfaces)


def load_declarations(root: Path) -> tuple[dict[str, list[ErrorDeclaration]], list[Path]]:
    declarations: dict[str, list[ErrorDeclaration]] = {}
    sources = declaration_sources(root)
    for source in sources:
        try:
            document = yaml.safe_load(_read(source))
        except yaml.YAMLError as error:
            raise SystemExit(
                f"[emitted-error-code] FAIL: 无法解析声明源 {source}: {error}"
            )
        for entry in _iter_declaration_entries(document):
            code = entry.get("code")
            if isinstance(code, str) and code.strip():
                declaration = ErrorDeclaration(
                    code=code.strip(),
                    source_path=source.relative_to(root).as_posix(),
                    go_const=str(entry.get("go_const") or entry.get("goConst") or "").strip(),
                    dart_const=str(entry.get("dart_const") or entry.get("dartConst") or "").strip(),
                    surfaces=_entry_surfaces(entry),
                )
                declarations.setdefault(declaration.code, []).append(declaration)
    return declarations, sources


def load_declared_codes(root: Path) -> tuple[set[str], list[Path]]:
    declarations, sources = load_declarations(root)
    return set(declarations), sources
