"""Reject Python modules whose referenced global symbols have no owner."""
from __future__ import annotations

import builtins
import symtable
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_GLOBALS = frozenset(
    {
        "__builtins__",
        "__cached__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__path__",
        "__spec__",
    }
)
_BUILTIN_NAMES = frozenset(dir(builtins)) | _RUNTIME_GLOBALS


def _module_defined_names(table: symtable.SymbolTable) -> frozenset[str]:
    return frozenset(
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_assigned()
        or symbol.is_imported()
        or symbol.is_namespace()
        or symbol.is_parameter()
    )


def source_undefined_name_issues(source: str, *, label: str) -> list[str]:
    try:
        root = symtable.symtable(source, label, "exec")
    except SyntaxError as exc:
        return [f"{label}:{exc.lineno or 1}: syntax error: {exc.msg}"]

    module_names = _module_defined_names(root)
    issues: set[tuple[int, str]] = set()

    def scan(table: symtable.SymbolTable) -> None:
        for symbol in table.get_symbols():
            name = symbol.get_name()
            if (
                symbol.is_referenced()
                and symbol.is_global()
                and name not in module_names
                and name not in _BUILTIN_NAMES
            ):
                issues.add((table.get_lineno(), name))
        for child in table.get_children():
            scan(child)

    scan(root)
    return [
        f"{label}:{line}: undefined global name {name!r}"
        for line, name in sorted(issues)
    ]


def scan_scripts(root: Path = SCRIPTS_ROOT) -> list[str]:
    issues: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        label = path.relative_to(root.parent).as_posix()
        issues.extend(
            source_undefined_name_issues(
                path.read_text(encoding="utf-8"),
                label=label,
            )
        )
    return issues


def main() -> int:
    issues = scan_scripts()
    if issues:
        print("[verify_python_symbols] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_python_symbols] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
