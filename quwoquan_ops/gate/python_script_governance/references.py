"""入口引用图与脚本间 import 图。"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Sequence

from .constants import (
    PACKAGE_SCRIPT_ROOTS,
    RELATIVE_SCRIPTS_PATTERN,
    REPO_SCRIPT_PATTERN,
)
from .models import relative_path


def central_reference_sources(root: Path) -> list[Path]:
    candidates = [
        root / "Makefile",
        root / "quwoquan_service/Makefile",
        root / "quwoquan_ops/cli/stackctl.py",
        root / "quwoquan_app/scripts/cli.py",
        root / "quwoquan_app/run.sh",
        root / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj",
        root / "quwoquan_data/scripts/cli.py",
    ]
    gate_root = root / "quwoquan_ops/gate"
    if gate_root.is_dir():
        # Shell orchestrators invoke managed scripts; Python verifiers may
        # mention intentional negative-path examples and are not entry edges.
        candidates.extend(sorted(gate_root.glob("*.sh")))
    candidates.extend(sorted((root / ".github/workflows").glob("*.yml")))
    candidates.extend(sorted((root / ".github/workflows").glob("*.yaml")))
    candidates.extend(
        sorted((root / "quwoquan_service/services").glob("*/Makefile"))
    )
    candidates.extend(
        sorted(
            (
                root
                / "quwoquan_ops"
                / "tests"
                / "acceptance"
                / "api_integration"
            ).rglob("*.py")
        )
    )
    candidates.extend(sorted((root / "specs").rglob("*.md")))
    for package in ("quwoquan_app", "quwoquan_service", "quwoquan_ops", "quwoquan_data"):
        package_root = root / package
        candidates.append(package_root / "AGENTS.md")
        candidates.append(package_root / "scripts/README.md")
    candidates.extend(sorted((root / "quwoquan_ops/runbooks").rglob("*.md")))
    candidates.extend(sorted((root / "quwoquan_app/test").rglob("*.py")))
    candidates.extend(sorted((root / "quwoquan_app/test").rglob("*.dart")))
    candidates.extend(
        sorted((root / "quwoquan_service/services").glob("*/tests/**/*.py"))
    )
    candidates.extend(sorted((root / "quwoquan_ops/tests").rglob("*.py")))
    candidates.extend(sorted((root / "quwoquan_data/tests").rglob("*.py")))
    return sorted(path for path in candidates if path.is_file())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _makefile_scripts_prefix(root: Path, source: Path) -> str | None:
    relative = relative_path(root, source)
    if relative == "quwoquan_service/Makefile":
        return "quwoquan_service"
    if relative == "quwoquan_app/Makefile":
        return "quwoquan_app"
    if relative == "quwoquan_data/Makefile":
        return "quwoquan_data"
    if relative.startswith("quwoquan_service/services/") and relative.endswith(
        "/Makefile"
    ):
        return str(Path(relative).parent.as_posix())
    return None


def _relative_scripts_prefix(root: Path, source: Path) -> str | None:
    makefile_prefix = _makefile_scripts_prefix(root, source)
    if makefile_prefix is not None:
        return makefile_prefix
    relative = relative_path(root, source)
    for package, prefix in PACKAGE_SCRIPT_ROOTS.items():
        if relative.startswith(f"{package}/"):
            return prefix
    return None


def _referenced_script_targets(root: Path, source: Path) -> set[str]:
    text = read_text(source)
    targets = {match.group(1) for match in REPO_SCRIPT_PATTERN.finditer(text)}
    prefix = _relative_scripts_prefix(root, source)
    for match in RELATIVE_SCRIPTS_PATTERN.finditer(text):
        relative_target = match.group(1)
        if prefix is not None:
            targets.add(f"{prefix}/{relative_target}")
            continue
        if source.is_relative_to(root / ".github" / "workflows"):
            for package_prefix in PACKAGE_SCRIPT_ROOTS.values():
                candidate = f"{package_prefix}/{relative_target}"
                if (root / candidate).is_file():
                    targets.add(candidate)
    return targets


def path_references(
    root: Path,
    scripts: Sequence[Path],
) -> dict[str, set[str]]:
    script_paths = {relative_path(root, path) for path in scripts}
    references = {path: set() for path in script_paths}
    basename_targets: dict[str, set[str]] = {}
    for target in script_paths:
        basename_targets.setdefault(Path(target).name, set()).add(target)
    sources = {*central_reference_sources(root), *scripts}
    for source in sorted(sources):
        source_relative = relative_path(root, source)
        source_text = read_text(source)
        for target in _referenced_script_targets(root, source):
            if target in references and target != source_relative:
                references[target].add(source_relative)
        if source.name == "README.md" and source.parent.name == "scripts":
            package_prefix = source.parent.parent.name
            marker = f"{package_prefix}/scripts/"
            for target in script_paths:
                if not target.startswith(marker):
                    continue
                local_target = target.removeprefix(marker)
                if local_target in source_text and target != source_relative:
                    references[target].add(source_relative)
        # stackctl and shell launchers often construct a path from semantic
        # segments. A unique live-tree basename is still a deterministic edge;
        # ambiguous basenames are deliberately ignored.
        if source not in scripts and source.name != "stackctl.py" and source.suffix != ".sh":
            continue
        for basename, targets in basename_targets.items():
            if len(targets) != 1 or basename not in source_text:
                continue
            target = next(iter(targets))
            if target != source_relative:
                references[target].add(source_relative)
    return references


def _import_names(path: Path) -> set[str]:
    if path.suffix == ".sh":
        names: set[str] = set()
        text = read_text(path)
        names.update(
            match.group(1)
            for match in re.finditer(
                r"(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)",
                text,
            )
        )
        return names
    if path.suffix != ".py":
        return set()
    try:
        tree = ast.parse(read_text(path), filename=str(path))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                names.add(module)
            for alias in node.names:
                names.add(f"{module}.{alias.name}".strip("."))
                names.add(alias.name)
    return names


def _module_aliases(root: Path, path: Path) -> set[str]:
    relative = path.relative_to(root).with_suffix("")
    aliases = {".".join(relative.parts), path.stem}
    parts = relative.parts
    if "scripts" in parts:
        index = parts.index("scripts")
        aliases.add(".".join(parts[index + 1 :]))
    return {alias for alias in aliases if alias}


def import_references(
    root: Path,
    scripts: Sequence[Path],
) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for path in scripts:
        relative = relative_path(root, path)
        for alias in _module_aliases(root, path):
            aliases.setdefault(alias, set()).add(relative)

    references = {relative_path(root, path): set() for path in scripts}
    for source in scripts:
        source_relative = relative_path(root, source)
        for imported in _import_names(source):
            parts = imported.split(".")
            matching_aliases = {
                ".".join(parts[index:]) for index in range(len(parts))
            }
            for alias in matching_aliases:
                targets = aliases.get(alias, ())
                for target in targets:
                    if target != source_relative:
                        references[target].add(source_relative)
    return references
