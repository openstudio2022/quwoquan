#!/usr/bin/env python3
"""派生全 Python 治理边界及 Python/Shell 脚本 owner、角色与结构违规。

本门只读取物理树、既有入口和 canonical owner 目录，不维护脚本 registry、
债务 baseline 或 orphan allowlist。每个 Python 文件必须唯一落入派生治理边界；
``report`` 总是输出实时派生结果，``check`` 只阻断可确定的目录、命名、角色、
临时文件和无 owner tool 违规。外部入口路径闭包由
``verify_entrypoint_script_paths.py`` 单独负责。
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

DEFAULT_ROOT = repository_root()
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))

from quwoquan_ops.gate import object_path_map


SCOPES = ("app", "service", "ops", "data")
SCRIPT_SUFFIXES = {".py", ".sh"}
PYTHON_SCOPE_ROOTS = {
    "app": Path("quwoquan_app"),
    "service": Path("quwoquan_service"),
    "ops": Path("quwoquan_ops"),
    "data": Path("quwoquan_data"),
}
FORBIDDEN_CACHE_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        ".nox",
        ".ipynb_checkpoints",
    }
)
FORBIDDEN_TEMP_FILE_SUFFIXES = (
    ".bak",
    ".orig",
    ".rej",
    ".swp",
    ".swo",
    "~",
)
TRAVERSAL_IGNORED_DIR_NAMES = frozenset(
    {
        ".dart_tool",
        ".git",
        ".gradle",
        ".idea",
        ".qwq_output",
        ".venv",
        "Pods",
        "build",
        "dist",
        "node_modules",
    }
)
RIPGREP_EXCLUDED_GLOBS = tuple(
    f"!**/{name}/**" for name in sorted(TRAVERSAL_IGNORED_DIR_NAMES)
)
TEMP_SCRIPT_NAME_RE = re.compile(
    r"^(?:tmp|temp|scratch|copy_of)[_-].*\.(?:py|sh)$",
    re.IGNORECASE,
)
_MILESTONE_TOKENS = (
    "t" + "[1-4]",
    "m" + "6",
    "m" + "7",
    "b" + "10",
    "phase" + "0",
    "part" + "[0-9]+",
)
MILESTONE_NAME_RE = re.compile(
    r"(^|[_-])(?:" + "|".join(_MILESTONE_TOKENS) + r")(?=[_.-]|$)",
    re.IGNORECASE,
)
REPO_SCRIPT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:quwoquan_(?:app|service|data|ops)/)[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
RELATIVE_SCRIPTS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(scripts/[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
PACKAGE_SCRIPT_ROOTS = {
    "quwoquan_app": "quwoquan_app",
    "quwoquan_service": "quwoquan_service",
    "quwoquan_data": "quwoquan_data",
}

APP_CONCERN_ROOTS = {
    "_common",
    "device",
    "env",
    "fonts",
    "gamma",
    "ios",
    "runtime",
    "tools",
    "web",
}
APP_CLOUD_LAYOUT_SEGMENTS = {
    "config",
    "deploy",
    "environments",
}
APP_RUNTIME_CONCERNS = {
    "architecture",
    "auth",
    "cloud",
    "codegen",
    "error",
    "media",
    "observability",
    "page",
    "platform",
}
SERVICE_CONCERN_ROOTS = {
    "codegen",
    "contracts",
    "runtime",
    "tools",
    "verify",
}
SERVICE_RUNTIME_CONCERNS = {
    "experiments",
    "packaging",
    "reliabletask",
}
OPS_MANAGED_ROOTS = (
    "ci",
    "cli",
    "environments/verify",
    "gate",
    "hooks",
    "migrations",
)
OPS_ALLOWED_TOP_LEVEL = {
    "ci",
    "cli",
    "environments",
    "gate",
    "hooks",
    "migrations",
    "observability",
    "tests",
    "tools",
}
ACCEPTANCE_ROOT = Path(
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops"
)


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class Warning:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ScriptRecord:
    path: str
    scope: str
    role: str
    reasons: tuple[str, ...]
    referencedBy: tuple[str, ...]
    importedBy: tuple[str, ...]
    orphanCandidate: bool


@dataclass(frozen=True)
class PythonFileRecord:
    path: str
    scope: str
    boundary: str


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _script_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
        and candidate.suffix in SCRIPT_SUFFIXES
        and "__pycache__" not in candidate.parts
    )


def enumerate_scripts(root: Path, scope: str) -> list[Path]:
    if scope == "app":
        return _script_files(root / "quwoquan_app/scripts")
    if scope == "service":
        return _script_files(root / "quwoquan_service/scripts")
    if scope == "data":
        return _script_files(root / "quwoquan_data/scripts")
    if scope == "ops":
        paths: set[Path] = set()
        for relative in OPS_MANAGED_ROOTS:
            paths.update(_script_files(root / "quwoquan_ops" / relative))
        paths.update(_script_files(root / ACCEPTANCE_ROOT))
        return sorted(paths)
    raise ValueError(f"unsupported scope: {scope}")


def _ripgrep_files(
    root: Path,
    *,
    include_globs: Sequence[str],
    no_ignore: bool = False,
) -> list[Path]:
    if not root.is_dir():
        return []
    command = ["rg", "--files", "--hidden"]
    if no_ignore:
        command.append("--no-ignore")
    for pattern in (*include_globs, *RIPGREP_EXCLUDED_GLOBS):
        command.extend(("--glob", pattern))
    command.append(str(root))
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            f"unable to enumerate Python governance files under {root}: "
            f"{completed.stderr.strip()}"
        )
    return sorted(
        Path(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def enumerate_python_files(root: Path, scope: str) -> list[Path]:
    return [
        path
        for path in _ripgrep_files(
            root / PYTHON_SCOPE_ROOTS[scope],
            include_globs=("*.py",),
            no_ignore=True,
        )
        if not any(
            part in FORBIDDEN_CACHE_DIR_NAMES for part in path.parts
        )
    ]


def _python_boundary(
    root: Path,
    scope: str,
    path: Path,
    managed_scripts: set[Path],
) -> str:
    if path in managed_scripts:
        return "managed_script"
    local = path.relative_to(root / PYTHON_SCOPE_ROOTS[scope])
    parts = local.parts
    if "vendor" in parts:
        return "vendor"
    if (
        "generated" in parts
        or "ephemeral" in parts
        or path.name.endswith((".g.py", "_generated.py"))
    ):
        return "generated"
    test_segment = "test" if scope == "app" else "tests"
    if test_segment in parts:
        if "support" in parts or path.name in {"conftest.py", "__init__.py"}:
            return "test_support"
        return "test_evidence"
    if scope == "service" and parts and parts[0] in {
        "contracts",
        "services",
        "runtime",
        "internal",
        "control-plane",
        "tools",
    }:
        return "production_module"
    if scope == "app" and parts and parts[0] in {"tool"}:
        return "production_module"
    if scope == "ops" and path.name == "__init__.py":
        return "production_module"
    return "unknown"


def _python_file_records(
    root: Path,
    scopes: Sequence[str],
    scripts_by_scope: dict[str, list[Path]],
) -> list[PythonFileRecord]:
    records: list[PythonFileRecord] = []
    for scope in scopes:
        managed = {
            path.resolve()
            for path in scripts_by_scope.get(scope, ())
            if path.suffix == ".py"
        }
        for path in enumerate_python_files(root, scope):
            records.append(
                PythonFileRecord(
                    path=_relative(root, path),
                    scope=scope,
                    boundary=_python_boundary(root, scope, path.resolve(), managed),
                )
            )
    return records


def _central_reference_sources(root: Path) -> list[Path]:
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


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _makefile_scripts_prefix(root: Path, source: Path) -> str | None:
    relative = _relative(root, source)
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
    relative = _relative(root, source)
    for package, prefix in PACKAGE_SCRIPT_ROOTS.items():
        if relative.startswith(f"{package}/"):
            return prefix
    return None


def _referenced_script_targets(root: Path, source: Path) -> set[str]:
    text = _text(source)
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


def _path_references(
    root: Path,
    scripts: Sequence[Path],
) -> dict[str, set[str]]:
    script_paths = {_relative(root, path) for path in scripts}
    references = {path: set() for path in script_paths}
    basename_targets: dict[str, set[str]] = {}
    for target in script_paths:
        basename_targets.setdefault(Path(target).name, set()).add(target)
    sources = {*_central_reference_sources(root), *scripts}
    for source in sorted(sources):
        source_relative = _relative(root, source)
        source_text = _text(source)
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
        text = _text(path)
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
        tree = ast.parse(_text(path), filename=str(path))
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


def _import_references(
    root: Path,
    scripts: Sequence[Path],
) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for path in scripts:
        relative = _relative(root, path)
        for alias in _module_aliases(root, path):
            aliases.setdefault(alias, set()).add(relative)

    references = {_relative(root, path): set() for path in scripts}
    for source in scripts:
        source_relative = _relative(root, source)
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


def _is_acceptance_script(relative: str) -> bool:
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
        tree = ast.parse(_text(path), filename=str(path))
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.If) and _is_dunder_main_guard(node.test)
        for node in tree.body
    )


def _is_owned_data_package_module(root: Path, path: Path) -> bool:
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


def _derive_role(
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
    if _is_acceptance_script(relative):
        role = "gate" if stem.startswith("verify_") else "runner"
        return role, ("located under service_ops acceptance evidence",)
    if name in {"cli.py", "stackctl.py"} or path.parent.name == "cli":
        return "cli", ("canonical CLI entry",)
    if stem.startswith("verify_"):
        reasons.append("verify_ naming")
        return "gate", tuple(reasons)
    if stem.startswith(("generate_", "sync_", "build_", "gen_")):
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


def _role_records(
    root: Path,
    scope_scripts: Sequence[tuple[str, Path]],
    path_references: dict[str, set[str]],
    import_references: dict[str, set[str]],
) -> list[ScriptRecord]:
    records: list[ScriptRecord] = []
    for scope, path in scope_scripts:
        relative = _relative(root, path)
        referenced_by = tuple(sorted(path_references.get(relative, set())))
        imported_by = tuple(sorted(import_references.get(relative, set())))
        role, reasons = _derive_role(
            relative,
            referenced_by,
            imported_by,
            owned_data_package_module=_is_owned_data_package_module(root, path),
        )
        orphan_candidate = (
            role in {"gate", "generator", "runner", "unclassified"}
            and not referenced_by
            and not imported_by
            and not _is_acceptance_script(relative)
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


def _naming_issues(root: Path, scripts: Sequence[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in scripts:
        if MILESTONE_NAME_RE.search(path.name):
            relative = _relative(root, path)
            issues.append(
                Issue(
                    code="SCRIPT.MILESTONE_NAME",
                    path=relative,
                    message=(
                        "stable script names must describe behavior, not "
                        "T/M/B/phase/part milestones"
                    ),
                )
            )
    return issues


def _source_hygiene_issues(root: Path, scopes: Sequence[str]) -> list[Issue]:
    issues: list[Issue] = []
    for scope in scopes:
        scope_root = root / PYTHON_SCOPE_ROOTS[scope]
        if not scope_root.is_dir():
            continue
        cache_globs = tuple(
            f"**/{name}/**" for name in sorted(FORBIDDEN_CACHE_DIR_NAMES)
        )
        cache_directories: set[Path] = set()
        for path in _ripgrep_files(
            scope_root,
            include_globs=cache_globs,
            no_ignore=True,
        ):
            for parent in path.parents:
                if parent.name in FORBIDDEN_CACHE_DIR_NAMES:
                    cache_directories.add(parent)
                    break
        issues.extend(
            Issue(
                code="PYTHON.SOURCE_CACHE_FORBIDDEN",
                path=_relative(root, path),
                message=(
                    "Python/lint/test cache belongs under .qwq_output "
                    "or a managed external cache"
                ),
            )
            for path in sorted(cache_directories)
        )

        hygiene_files = _ripgrep_files(
            scope_root,
            include_globs=(
                "*.py",
                "*.sh",
                "*.pyc",
                "*.pyo",
                "*.bak",
                "*.orig",
                "*.rej",
                "*.swp",
                "*.swo",
                "*~",
            ),
            no_ignore=True,
        )
        for path in hygiene_files:
            if any(part in FORBIDDEN_CACHE_DIR_NAMES for part in path.parts):
                continue
            if path.suffix in {".pyc", ".pyo"} or path.name.endswith(
                FORBIDDEN_TEMP_FILE_SUFFIXES
            ):
                issues.append(
                    Issue(
                        code="PYTHON.TEMP_FILE_FORBIDDEN",
                        path=_relative(root, path),
                        message=(
                            "bytecode, editor backup, and patch residue "
                            "are forbidden in source trees"
                        ),
                    )
                )
            elif TEMP_SCRIPT_NAME_RE.fullmatch(path.name):
                issues.append(
                    Issue(
                        code="PYTHON.TEMP_SCRIPT_NAME",
                        path=_relative(root, path),
                        message=(
                            "temporary scripts require a stable owner "
                            "and semantic name"
                        ),
                    )
                )
    return issues


def _tool_owner_issues(records: Sequence[ScriptRecord]) -> list[Issue]:
    return [
        Issue(
            code="SCRIPT.TOOL_OWNER_MISSING",
            path=record.path,
            message=(
                "manual tool requires a live CLI/Make/runbook/spec/test/README "
                "reference proving owner and purpose"
            ),
        )
        for record in records
        if record.role == "tool"
        and not record.referencedBy
        and not record.importedBy
    ]


def _app_structure_issues(root: Path, scripts: Sequence[Path]) -> list[Issue]:
    issues: list[Issue] = []
    scripts_root = root / "quwoquan_app/scripts"
    app_service_root = (
        root
        / "quwoquan_app/lib"
        / object_path_map.APP_SERVICE_ROOT_SEGMENT
    )
    service_names = {
        path.name for path in app_service_root.iterdir() if path.is_dir()
    } if app_service_root.is_dir() else set()

    for path in scripts:
        local = path.relative_to(scripts_root)
        if len(local.parts) == 1:
            if local.name != "cli.py":
                issues.append(
                    Issue(
                        code="APP.SCRIPT_ROOT_FILE",
                        path=_relative(root, path),
                        message="only cli.py may live directly under app/scripts",
                    )
                )
            continue

        top = local.parts[0]
        if top == "service":
            issues.append(
                Issue(
                    code="APP.SERVICE_WRAPPER_FORBIDDEN",
                    path=_relative(root, path),
                    message=(
                        "scripts/service/ wrapper is forbidden; "
                        "use scripts/<snake>_service/ as L1"
                    ),
                )
            )
            continue

        if any(segment in APP_CLOUD_LAYOUT_SEGMENTS for segment in local.parts):
            issues.append(
                Issue(
                    code="APP.CLOUD_LAYOUT_COPY_FORBIDDEN",
                    path=_relative(root, path),
                    message=(
                        "App scripts must not copy cloud config/deploy/"
                        "environments layout; use env/ or gamma/ concerns"
                    ),
                )
            )
            continue

        if top not in APP_CONCERN_ROOTS and top not in service_names:
            issues.append(
                Issue(
                    code="APP.SCRIPT_ROOT_UNSUPPORTED",
                    path=_relative(root, path),
                    message=(
                        f"{top} is neither a canonical App service segment "
                        "nor an approved cross-cutting concern"
                    ),
                )
            )
            continue

        if top == "runtime":
            if len(local.parts) == 2 and local.name not in {"__init__.py"}:
                issues.append(
                    Issue(
                        code="APP.RUNTIME_FLAT_SCRIPT",
                        path=_relative(root, path),
                        message="runtime scripts must declare a concern directory",
                    )
                )
            elif (
                len(local.parts) >= 3
                and local.parts[1] not in APP_RUNTIME_CONCERNS
            ):
                issues.append(
                    Issue(
                        code="APP.RUNTIME_CONCERN_UNKNOWN",
                        path=_relative(root, path),
                        message=f"unknown runtime concern {local.parts[1]}",
                    )
                )
            continue

        if top not in service_names:
            continue
        if len(local.parts) >= 3:
            context_root = app_service_root / top / local.parts[1]
            if not context_root.is_dir():
                issues.append(
                    Issue(
                        code="APP.CONTEXT_OWNER_MISSING",
                        path=_relative(root, path),
                        message=f"missing App context owner {context_root.relative_to(root)}",
                    )
                )
                continue
        if len(local.parts) >= 4:
            object_root = app_service_root / top / local.parts[1] / local.parts[2]
            if not object_root.is_dir():
                issues.append(
                    Issue(
                        code="APP.OBJECT_OWNER_MISSING",
                        path=_relative(root, path),
                        message=f"missing App object owner {object_root.relative_to(root)}",
                    )
                )
    return issues


def _service_structure_issues(
    root: Path,
    scripts: Sequence[Path],
) -> list[Issue]:
    issues: list[Issue] = []
    scripts_root = root / "quwoquan_service/scripts"
    services_root = root / "quwoquan_service/services"
    service_names = {
        path.name for path in services_root.iterdir() if path.is_dir()
    } if services_root.is_dir() else set()

    for path in scripts:
        local = path.relative_to(scripts_root)
        if len(local.parts) == 1:
            issues.append(
                Issue(
                    code="SERVICE.SCRIPT_ROOT_FILE",
                    path=_relative(root, path),
                    message="service scripts must declare a concern or service owner",
                )
            )
            continue
        top = local.parts[0]
        if top not in SERVICE_CONCERN_ROOTS and top not in service_names:
            issues.append(
                Issue(
                    code="SERVICE.SCRIPT_ROOT_UNSUPPORTED",
                    path=_relative(root, path),
                    message=(
                        f"{top} is neither a canonical kebab service nor a "
                        "service-script concern"
                    ),
                )
            )
            continue
        if top == "contracts" and path.name.startswith("verify_"):
            issues.append(
                Issue(
                    code="SERVICE.CONTRACTS_VERIFY_MIXED",
                    path=_relative(root, path),
                    message="contracts contains build/sync/generate only; verifier belongs in verify",
                )
            )
        if top == "runtime":
            if len(local.parts) == 2 and local.name not in {"__init__.py"}:
                issues.append(
                    Issue(
                        code="SERVICE.RUNTIME_FLAT_SCRIPT",
                        path=_relative(root, path),
                        message="runtime scripts must declare a concern directory",
                    )
                )
            elif (
                len(local.parts) >= 3
                and local.parts[1] not in SERVICE_RUNTIME_CONCERNS
            ):
                issues.append(
                    Issue(
                        code="SERVICE.RUNTIME_CONCERN_UNKNOWN",
                        path=_relative(root, path),
                        message=f"unknown runtime concern {local.parts[1]}",
                    )
                )
            continue
        if top not in service_names:
            continue
        # Service-local tools/ is a canonical manual-tool pocket; it does not
        # require a matching internal/<context> owner.
        if len(local.parts) >= 2 and local.parts[1] == "tools":
            continue
        internal_root = services_root / top / "internal"
        if len(local.parts) >= 3:
            context_root = internal_root / local.parts[1]
            if not context_root.is_dir():
                issues.append(
                    Issue(
                        code="SERVICE.CONTEXT_OWNER_MISSING",
                        path=_relative(root, path),
                        message=f"missing service context owner {context_root.relative_to(root)}",
                    )
                )
                continue
        if len(local.parts) >= 4:
            object_root = internal_root / local.parts[1] / local.parts[2]
            if not object_root.is_dir():
                issues.append(
                    Issue(
                        code="SERVICE.OBJECT_OWNER_MISSING",
                        path=_relative(root, path),
                        message=f"missing service object owner {object_root.relative_to(root)}",
                    )
                )
    return issues


def _service_verify_single_owner_warnings(
    root: Path,
    scripts: Sequence[Path],
) -> list[Warning]:
    """Warn when ``scripts/verify/`` hosts a single-service scan root."""

    warnings: list[Warning] = []
    scripts_root = root / "quwoquan_service/scripts"
    services_root = root / "quwoquan_service/services"
    if not scripts_root.is_dir() or not services_root.is_dir():
        return warnings
    service_names = sorted(
        path.name for path in services_root.iterdir() if path.is_dir()
    )
    if not service_names:
        return warnings
    alt = "|".join(re.escape(name) for name in service_names)
    joined_pat = re.compile(
        rf"(?:quwoquan_service/)?services/({alt})(?:/|\b)"
    )
    split_pat = re.compile(
        rf"""["']services["']\s*/\s*["']({alt})["']"""
    )
    multi_walk_pat = re.compile(
        r"(services.*iterdir|for\s+\w+\s+in\s+.*services|"
        r"SERVICES_ROOT|service_names\s*=|services_root)",
        re.IGNORECASE,
    )
    other_package_pat = re.compile(
        r"quwoquan_app|quwoquan_ops|quwoquan_data"
    )
    runtime_tools_pat = re.compile(
        r"""["']/runtime/|/tools/|["']runtime["']\s*/"""
    )

    for path in scripts:
        try:
            local = path.relative_to(scripts_root)
        except ValueError:
            continue
        if len(local.parts) < 2 or local.parts[0] != "verify":
            continue
        if path.suffix != ".py":
            continue
        text = _text(path)
        hits = set(joined_pat.findall(text)) | set(split_pat.findall(text))
        if len(hits) != 1:
            continue
        if multi_walk_pat.search(text):
            continue
        if other_package_pat.search(text):
            continue
        if runtime_tools_pat.search(text):
            continue
        owner = next(iter(hits))
        warnings.append(
            Warning(
                code="SERVICE.VERIFY_SINGLE_SERVICE_OWNER",
                path=_relative(root, path),
                message=(
                    f"scan root only targets {owner}; move to "
                    f"scripts/{owner}/ (verify/ is for multi-service gates)"
                ),
            )
        )
    return warnings


def _ops_structure_issues(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    ops_root = root / "quwoquan_ops"
    if not ops_root.is_dir():
        return issues
    for child in sorted(ops_root.iterdir()):
        if not child.is_dir() or child.name in OPS_ALLOWED_TOP_LEVEL:
            continue
        if _script_files(child):
            issues.append(
                Issue(
                    code="OPS.SCRIPT_ROOT_UNSUPPORTED",
                    path=_relative(root, child),
                    message="Ops Python belongs to concern roots, not a business script island",
                )
            )
    return issues


def _data_architecture_issues(root: Path) -> list[Issue]:
    if root.resolve() != DEFAULT_ROOT.resolve():
        return []
    module_path = (
        root / "quwoquan_data/scripts/verify/verify_script_architecture.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_quwoquan_data_script_architecture",
        module_path,
    )
    if spec is None or spec.loader is None:
        return [
            Issue(
                code="DATA.SCRIPT_ARCHITECTURE_UNAVAILABLE",
                path=_relative(root, module_path),
                message="unable to load canonical Data script architecture gate",
            )
        ]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        Issue(
            code="DATA.SCRIPT_ARCHITECTURE",
            path="quwoquan_data/scripts",
            message=str(message),
        )
        for message in module.script_architecture_issues()
    ]


def derive_report(root: Path, scopes: Sequence[str]) -> dict[str, object]:
    normalized_root = root.resolve()
    scope_scripts: list[tuple[str, Path]] = []
    scripts_by_scope: dict[str, list[Path]] = {}
    for scope in scopes:
        scripts = enumerate_scripts(normalized_root, scope)
        scripts_by_scope[scope] = scripts
        scope_scripts.extend((scope, path) for path in scripts)

    # Build one reference/import graph across the selected scopes so
    # Ops → Service and Makefile-relative scripts/... edges stay visible.
    all_scripts = [path for _, path in scope_scripts]
    path_references = _path_references(normalized_root, all_scripts)
    import_references = _import_references(normalized_root, all_scripts)
    records = _role_records(
        normalized_root,
        scope_scripts,
        path_references,
        import_references,
    )
    python_file_records = _python_file_records(
        normalized_root,
        scopes,
        scripts_by_scope,
    )

    issues: list[Issue] = _source_hygiene_issues(normalized_root, scopes)
    warnings: list[Warning] = []
    for scope, scripts in scripts_by_scope.items():
        issues.extend(_naming_issues(normalized_root, scripts))
        if scope == "app":
            issues.extend(_app_structure_issues(normalized_root, scripts))
        elif scope == "service":
            issues.extend(_service_structure_issues(normalized_root, scripts))
            warnings.extend(
                _service_verify_single_owner_warnings(normalized_root, scripts)
            )
        elif scope == "ops":
            issues.extend(_ops_structure_issues(normalized_root))
        elif scope == "data":
            issues.extend(_data_architecture_issues(normalized_root))

    for record in records:
        if record.role == "unclassified":
            issues.append(
                Issue(
                    code="SCRIPT.ROLE_UNCLASSIFIED",
                    path=record.path,
                    message="script has no canonical role signal",
                )
            )
    issues.extend(_tool_owner_issues(records))
    issues.extend(
        Issue(
            code="PYTHON.BOUNDARY_UNKNOWN",
            path=record.path,
            message="Python file is outside every derived governance boundary",
        )
        for record in python_file_records
        if record.boundary == "unknown"
    )

    unique_issues = sorted(
        {issue for issue in issues},
        key=lambda issue: (issue.code, issue.path, issue.message),
    )
    unique_warnings = sorted(
        {warning for warning in warnings},
        key=lambda warning: (warning.code, warning.path, warning.message),
    )
    sorted_records = sorted(records, key=lambda record: record.path)
    sorted_python_files = sorted(
        python_file_records,
        key=lambda record: record.path,
    )
    boundary_counts: dict[str, int] = {}
    for record in sorted_python_files:
        boundary_counts[record.boundary] = (
            boundary_counts.get(record.boundary, 0) + 1
        )
    return {
        "schema": "quwoquan.python-script-governance-report.v2",
        "scopes": list(scopes),
        "summary": {
            "scriptCount": len(sorted_records),
            "pythonFileCount": len(sorted_python_files),
            "pythonBoundaryCounts": {
                key: boundary_counts[key] for key in sorted(boundary_counts)
            },
            "issueCount": len(unique_issues),
            "warningCount": len(unique_warnings),
            "orphanCandidateCount": sum(
                1 for record in sorted_records if record.orphanCandidate
            ),
        },
        "issues": [asdict(issue) for issue in unique_issues],
        "warnings": [asdict(warning) for warning in unique_warnings],
        "scripts": [asdict(record) for record in sorted_records],
        "pythonFiles": [asdict(record) for record in sorted_python_files],
    }


def _scopes(value: str) -> tuple[str, ...]:
    return SCOPES if value == "all" else (value,)


def _report_bytes(report: dict[str, object]) -> bytes:
    return (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=(*SCOPES, "all"), default="all")
    parser.add_argument("--mode", choices=("report", "check"), default="check")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Repository root; intended for local_contract fixture trees.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report path. Defaults under .qwq_output for report mode.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    scopes = _scopes(args.scope)
    report = derive_report(args.repo_root, scopes)
    payload = _report_bytes(report)

    if args.mode == "report":
        output = args.output or (
            args.repo_root
            / ".qwq_output/env/repo/runs/python-script-governance"
            / f"{args.scope}.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        print(
            "[verify_python_script_governance] REPORT "
            f"scripts={report['summary']['scriptCount']} "
            f"pythonFiles={report['summary']['pythonFileCount']} "
            f"issues={report['summary']['issueCount']} "
            f"warnings={report['summary'].get('warningCount', 0)} "
            f"orphanCandidates={report['summary']['orphanCandidateCount']} "
            f"output={output}"
        )
        return 0

    issues = report["issues"]
    warnings = report.get("warnings") or []
    if warnings:
        print("[verify_python_script_governance] WARN")
        for warning in warnings:
            print(
                f"  - {warning['code']} {warning['path']}: {warning['message']}"
            )
    if issues:
        print("[verify_python_script_governance] FAIL")
        for issue in issues:
            print(f"  - {issue['code']} {issue['path']}: {issue['message']}")
        return 1
    print(
        "[verify_python_script_governance] OK "
        f"scripts={report['summary']['scriptCount']} "
        f"pythonFiles={report['summary']['pythonFileCount']} "
        f"warnings={report['summary'].get('warningCount', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
