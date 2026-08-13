"""Go 侧 generated factory / stable const 生产调用的发射证据扫描。"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Emission, ErrorDeclaration, ScanResult, _read
from .resolution import _function_name, _go_files, _split_functions


def _generated_import_path(declaration: ErrorDeclaration) -> str:
    parts = declaration.source_path.split("/")
    try:
        contracts_index = parts.index("contracts")
    except ValueError:
        return ""
    if not parts or parts[-1] != "errors.yaml" or contracts_index + 2 >= len(parts):
        return ""
    return "/".join(
        [*parts[:contracts_index], "generated", *parts[contracts_index + 1 : -1]]
    )


def _generated_symbols(
    declarations: dict[str, list[ErrorDeclaration]],
) -> dict[tuple[str, str], tuple[str, str]]:
    """Return (import path, symbol) -> (stable code, form).

    A duplicate code owner is already rejected by metadata governance. A symbol
    collision inside one generated package is unsafe here as well, so ambiguous
    mappings are removed instead of guessed.
    """
    candidates: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for code, owned in declarations.items():
        for declaration in owned:
            import_path = _generated_import_path(declaration)
            if not import_path or not declaration.go_const:
                continue
            candidates.setdefault(
                (import_path, declaration.go_const), []
            ).append((code, "go_const_identifier"))
            if declaration.go_const.startswith("Err"):
                candidates.setdefault(
                    (import_path, "AppErrorFrom" + declaration.go_const[3:]), []
                ).append((code, "generated_app_error_factory"))
    return {
        key: values[0]
        for key, values in candidates.items()
        if len({value[0] for value in values}) == 1
    }


_GO_GENERATED_IMPORT = re.compile(
    r'^\s*(?:import\s+)?(?:(?P<alias>[A-Za-z_]\w*)\s+)?'
    r'"(?P<path>quwoquan_service/[^"\n]+/generated/[^"\n]+)"',
    re.M,
)


def _scan_generated_symbol_emissions(
    root: Path,
    declarations: dict[str, list[ErrorDeclaration]],
    result: ScanResult,
) -> None:
    symbols = _generated_symbols(declarations)
    for path in _go_files(root):
        text = _read(path)
        relative = path.relative_to(root).as_posix()
        imports: dict[str, str] = {}
        for match in _GO_GENERATED_IMPORT.finditer(text):
            import_path = match.group("path")
            alias = match.group("alias")
            if not alias:
                generated_dir = root / import_path
                for generated_source in sorted(generated_dir.glob("*.go")):
                    package_match = re.search(
                        r"^package\s+([A-Za-z_]\w*)", _read(generated_source), re.M
                    )
                    if package_match:
                        alias = package_match.group(1)
                        break
            alias = alias or import_path.rsplit("/", 1)[-1]
            imports[alias] = import_path
        if not imports:
            continue
        functions = _split_functions(text)
        for alias, import_path in imports.items():
            for match in re.finditer(
                rf"\b{re.escape(alias)}\.(?P<symbol>(?:AppErrorFrom|Err)[A-Za-z0-9_]+)\b",
                text,
            ):
                mapped = symbols.get((import_path, match.group("symbol")))
                if mapped is None:
                    continue
                code, form = mapped
                function = "<file-scope>"
                function_text = ""
                for candidate in functions:
                    start = text.find("func " + candidate)
                    end = start + len("func " + candidate)
                    if start <= match.start() <= end:
                        function = _function_name(candidate)
                        function_text = candidate
                        break
                if form == "generated_app_error_factory" and "errors.Is(" in function_text:
                    form = "domain_sentinel_handler"
                result.emissions.append(
                    Emission(code=code, form=form, path=relative, function=function)
                )
