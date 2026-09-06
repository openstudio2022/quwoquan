"""脚本角色派生与 orphan 候选判定。"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

from .constants import ACCEPTANCE_ROOT
from .models import ScriptRecord, relative_path
from .references import read_text


def is_acceptance_script(relative: str) -> bool:
    return relative.startswith(f"{ACCEPTANCE_ROOT.as_posix()}/")


def _is_dunder_main_guard(test: ast.expr) -> bool:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
        return False
    operands = (test.left, test.comparators[0])
    return any(
        isinstance(name, ast.Name)
        and name.id == "__name__"
        and isinstance(value, ast.Constant)
        and value.value == "__main__"
        for name, value in (operands, operands[::-1])
    )


def _has_dunder_main_entry(path: Path) -> bool:
    if path.suffix != ".py":
        return False
    try:
        tree = ast.parse(read_text(path), filename=str(path))
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.If) and _is_dunder_main_guard(node.test)
        for node in tree.body
    )


def is_owned_data_package_module(root: Path, path: Path) -> bool:
    scripts_root = root / "quwoquan_data/scripts"
    try:
        local = path.relative_to(scripts_root)
    except ValueError:
        return False
    return (
        path.suffix == ".py"
        and len(local.parts) > 1
        and (scripts_root / local.parts[0]).is_dir()
        and not _has_dunder_main_entry(path)
    )


def derive_role(
    relative: str,
    referenced_by: Sequence[str],
    imported_by: Sequence[str],
    *,
    owned_data_package_module: bool,
) -> tuple[str, tuple[str, ...]]:
    path = Path(relative)
    name = path.name
    stem = path.stem
    reasons: list[str] = []

    if "/hooks/" in f"/{relative}":
        return "hook", ("located under hooks",)
    if "/migrations/" in f"/{relative}":
        return "migration", ("located under migrations",)
    if is_acceptance_script(relative):
        role = "gate" if stem.startswith("verify_") else "runner"
        return role, ("located under service_ops acceptance evidence",)
    if name in {"cli.py", "stackctl.py"} or path.parent.name == "cli":
        return "cli", ("canonical CLI entry",)
    if stem.startswith("verify_"):
        reasons.append("verify_ naming")
        return "gate", tuple(reasons)
    if stem.startswith(
        ("generate_", "render_", "collect_", "sync_", "build_", "gen_")
    ):
        reasons.append("generator naming")
        return "generator", tuple(reasons)
    if stem.startswith("run_"):
        reasons.append("runner naming")
        return "runner", tuple(reasons)
    if "lib" in path.parts:
        return "lib", ("explicit library path",)
    if ("tools" in path.parts or stem.startswith("scan_")) and not imported_by:
        reasons.append("manual tool path or naming")
        return "tool", tuple(reasons)
    if name in {"__init__.py", "handler.py"}:
        return "lib", ("package or CLI handler module",)
    if name == "repository_root.py":
        return "lib", ("root discovery bootstrap module",)
    if owned_data_package_module:
        return "lib", ("owned Data package module without __main__ entry",)
    if imported_by:
        return "lib", ("imported by another managed script",)
    if referenced_by:
        return "lib", ("referenced by another managed entry",)
    return "unclassified", ("no canonical role signal",)


def role_records(
    root: Path,
    scope_scripts: Sequence[tuple[str, Path]],
    path_references: dict[str, set[str]],
    import_references: dict[str, set[str]],
) -> list[ScriptRecord]:
    records: list[ScriptRecord] = []
    for scope, path in scope_scripts:
        relative = relative_path(root, path)
        referenced_by = tuple(sorted(path_references.get(relative, set())))
        imported_by = tuple(sorted(import_references.get(relative, set())))
        role, reasons = derive_role(
            relative,
            referenced_by,
            imported_by,
            owned_data_package_module=is_owned_data_package_module(root, path),
        )
        orphan_candidate = (
            role in {"gate", "generator", "runner", "unclassified"}
            and not referenced_by
            and not imported_by
            and not is_acceptance_script(relative)
        )
        records.append(
            ScriptRecord(
                path=relative,
                scope=scope,
                role=role,
                reasons=reasons,
                referencedBy=referenced_by,
                importedBy=imported_by,
                orphanCandidate=orphan_candidate,
            )
        )
    return records
