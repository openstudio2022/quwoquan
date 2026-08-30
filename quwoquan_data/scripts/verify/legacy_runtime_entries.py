"""Canonical retired runtime entry patterns and fail-closed repository scan."""
from __future__ import annotations

import ast
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

SCANNED_ROOTS = ("quwoquan_app", "quwoquan_service", "quwoquan_ops", ".github")
LEGACY_ORCHESTRATION_FAMILIES = (
    "agent",
    "queue",
    "controller",
    "recovery",
    "campaign",
)
FORBIDDEN_RUNTIME_MODULE_PREFIXES = (
    "cursor_sdk",
    "codex",
    "openai_codex",
    "openai.codex",
)
PRODUCTION_SCAN_SUFFIXES = frozenset(
    {".dart", ".go", ".gradle", ".java", ".json", ".kt", ".kts", ".plist", ".py", ".rb", ".sh", ".swift", ".toml", ".xml", ".yaml", ".yml"}
)
PRODUCTION_SCAN_EXCLUDED_PARTS = frozenset(
    {".dart_tool", ".git", ".gradle", ".idea", ".qwq_output", ".symlinks", "Pods", "build", "coverage", "docs", "node_modules", "plans", "specs", "test", "testdata", "tests", "vendor"}
)
_LEGACY_FAMILY_PATTERN = "|".join(LEGACY_ORCHESTRATION_FAMILIES)
LEGACY_PYTHON_MODULE_RE = re.compile(
    rf"\bcontent(?:\.|/)execution(?:\.|/)(?:{_LEGACY_FAMILY_PATTERN})"
    r"(?=$|[^A-Za-z0-9_])"
)
LEGACY_PYTHON_IMPORT_ALIAS_RE = re.compile(
    rf"\bfrom\s+content\.execution\s+import\s+[^\n#]*"
    rf"\b(?:{_LEGACY_FAMILY_PATTERN})\b"
)
LEGACY_CLI_REGISTRATION_RE = re.compile(
    rf"\b(?:register|handle)_(?:[A-Za-z0-9]+_)*(?:{_LEGACY_FAMILY_PATTERN})"
    r"(?:_[A-Za-z0-9]+)*\b|"
    rf'\b(?:parser|subparsers|commands|sub)\.add_parser\(\s*[\'"]'
    rf'[^\'"]*(?<![A-Za-z0-9])(?:{_LEGACY_FAMILY_PATTERN})'
    rf'(?![A-Za-z0-9])[^\'"]*[\'"]',
    re.IGNORECASE,
)
LEGACY_GO_WIRE_RES = (
    (
        "Go data-content-worker wire",
        re.compile(r"data-content-worker|data_content_worker|DataContentWorker"),
    ),
    (
        "Go campaign/fleet wire",
        re.compile(
            r"DataContent(?:Campaign|Fleet)|"
            r"campaign(?:Scale|Binding|RootExecutionId|RunId|Generation|FencingToken|"
            r"PlanDigest|SourceRevision|SourceDigest|EntityCatalogDigest)|"
            r"fleet(?:MaxConcurrentWorkers|WaveCount|BatchDeadlineEpochSeconds|"
            r"ControlPlaneThroughputPerHour|AcceptedThroughputPerHour|"
            r"PeakConcurrentWorkers|StartedAt|WallClockMilliseconds)"
        ),
    ),
    (
        "ReliableTask worker wire",
        re.compile(
            r"DataContent(?:Job|WorkerFence|WorkItem|Executor|ExecutionResult|"
            r"TaskType|Queue|TaskDigest|ExecutionStore|Checkpoint|FenceStore|"
            r"Outbox|Acceptance|ResultVerifier|ConcurrencyObserver)|"
            r"reliabletask\.data\.content_supply|data\.content_object\.execute|"
            r"quwoquan\.reliabletask_fleet_report"
        ),
    ),
)
LEGACY_OPS_TOPOLOGY_RE = re.compile(
    r"data[-_]execution[-_]fleet|DataExecutionFleet", re.IGNORECASE
)
LEGACY_COMPOSE_WORKER_RE = re.compile(
    r"data-content-worker|data_content_worker", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class LegacyRuntimeScan:
    legacy_entry_refs: tuple[str, ...]
    scan_errors: tuple[str, ...]


def legacy_python_import_reference(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    prefix = "content.execution."
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.removeprefix(prefix).split(".", 1)[0]
            in LEGACY_ORCHESTRATION_FAMILIES
            for alias in node.names
            if alias.name.startswith(prefix)
        ):
            return True
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if module.startswith(prefix) and (
            module.removeprefix(prefix).split(".", 1)[0]
            in LEGACY_ORCHESTRATION_FAMILIES
        ):
            return True
        if module == "content.execution" and any(
            alias.name in LEGACY_ORCHESTRATION_FAMILIES for alias in node.names
        ):
            return True
    return False


def legacy_source_path_kind(relative: Path, *, suffix: str) -> str | None:
    normalized = relative.as_posix().lower()
    if "/services/content-service/cmd/data-content-worker/" in f"/{normalized}":
        return "Go data-content-worker path"
    if "/runtime/reliabletask/data_content_" in f"/{normalized}" and suffix == ".go":
        return "ReliableTask worker path"
    if "/application/importer/data_fleet" in f"/{normalized}" and suffix == ".go":
        return "Go campaign/fleet path"
    if "data-execution-fleet" in normalized or "data_execution_fleet" in normalized:
        return "Ops data-execution-fleet path"
    return None


def _legacy_text_kinds(
    relative: Path, text: str, *, include_cli_registration: bool
) -> tuple[str, ...]:
    suffix = relative.suffix.lower()
    kinds: set[str] = set()
    if suffix == ".py":
        if (
            LEGACY_PYTHON_MODULE_RE.search(text)
            or LEGACY_PYTHON_IMPORT_ALIAS_RE.search(text)
            or legacy_python_import_reference(text)
        ):
            kinds.add("retired Python orchestration module reference")
        if include_cli_registration and LEGACY_CLI_REGISTRATION_RE.search(text):
            kinds.add("retired orchestration CLI parser/handler registration")
    if suffix == ".go":
        for kind, pattern in LEGACY_GO_WIRE_RES:
            if pattern.search(text):
                kinds.add(kind)
    is_ops_source = relative.parts and relative.parts[0] == "quwoquan_ops"
    if is_ops_source and (
        LEGACY_OPS_TOPOLOGY_RE.search(text)
        or (
            suffix in {".json", ".toml", ".yaml", ".yml"}
            and LEGACY_COMPOSE_WORKER_RE.search(text)
        )
    ):
        kinds.add("retired Ops data-execution-fleet topology reference")
    return tuple(sorted(kinds))


def _read_regular_text(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("entry is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OSError("entry changed while reading")
    finally:
        os.close(descriptor)
    return b"".join(chunks).decode("utf-8")


def _walk_files(root: Path, *, repo_root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        filename = str(exc.filename or root)
        try:
            label = Path(filename).relative_to(repo_root).as_posix()
        except ValueError:
            label = filename
        errors.append(f"{label}: cannot enumerate: {exc}")

    try:
        root_metadata = root.lstat()
    except OSError as exc:
        return [], [f"{root.name}: scan root unavailable: {exc}"]
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        return [], [f"{root.name}: scan root must be a real directory"]
    for current, directories, names in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            candidate = current_path / name
            relative = candidate.relative_to(repo_root)
            if any(part in PRODUCTION_SCAN_EXCLUDED_PARTS for part in relative.parts):
                continue
            try:
                metadata = candidate.lstat()
            except OSError as exc:
                errors.append(f"{relative.as_posix()}: cannot inspect directory: {exc}")
                continue
            if stat.S_ISLNK(metadata.st_mode):
                errors.append(f"{relative.as_posix()}: symbolic directory is not accepted")
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                errors.append(f"{relative.as_posix()}: unknown directory entry type")
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            if name.endswith(("_test.go", "_test.py")):
                continue
            path = current_path / name
            relative = path.relative_to(repo_root)
            if any(part in PRODUCTION_SCAN_EXCLUDED_PARTS for part in relative.parts):
                continue
            try:
                metadata = path.lstat()
            except OSError as exc:
                errors.append(f"{relative.as_posix()}: cannot inspect entry: {exc}")
                continue
            if stat.S_ISLNK(metadata.st_mode):
                errors.append(f"{relative.as_posix()}: symbolic file is not accepted")
                continue
            if not stat.S_ISREG(metadata.st_mode):
                errors.append(f"{relative.as_posix()}: unknown file entry type")
                continue
            suffix = path.suffix.lower()
            path_kind = legacy_source_path_kind(relative, suffix=suffix)
            if path_kind is not None or suffix in PRODUCTION_SCAN_SUFFIXES:
                files.append(path)
    return files, errors


def scan_data_legacy_orchestration_entries(
    *, scripts_root: Path, repo_root: Path
) -> LegacyRuntimeScan:
    refs: set[str] = set()
    errors: list[str] = []
    execution_root = Path(scripts_root) / "content/execution"
    for family in LEGACY_ORCHESTRATION_FAMILIES:
        family_path = execution_root / family
        try:
            metadata = family_path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"{family_path}: cannot inspect legacy family: {exc}")
            continue
        relative = family_path.relative_to(repo_root).as_posix()
        if stat.S_ISLNK(metadata.st_mode):
            errors.append(f"{relative}: symbolic legacy family is not accepted")
        else:
            refs.add(
                f"{relative}#legacy orchestration directory remains after retirement seal ({family})"
            )
    files, scan_errors = _walk_files(Path(scripts_root), repo_root=Path(repo_root))
    errors.extend(scan_errors)
    own_sources = {
        Path(__file__).resolve(),
        (Path(scripts_root) / "verify/verify_script_architecture.py").resolve(),
    }
    for source in files:
        if source.resolve() in own_sources:
            continue
        relative = source.relative_to(repo_root)
        try:
            text = _read_regular_text(source)
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative.as_posix()}: production source unreadable: {exc}")
            continue
        for kind in _legacy_text_kinds(
            relative, text, include_cli_registration=True
        ):
            refs.add(f"{relative.as_posix()}#{kind}")
    return LegacyRuntimeScan(tuple(sorted(refs)), tuple(sorted(set(errors))))


def scan_legacy_runtime_entries(
    repo_root: Path, *, root_names: tuple[str, ...] = SCANNED_ROOTS
) -> LegacyRuntimeScan:
    root = Path(repo_root)
    refs: set[str] = set()
    errors: list[str] = []
    for root_name in root_names:
        files, root_errors = _walk_files(root / root_name, repo_root=root)
        errors.extend(root_errors)
        for path in files:
            relative = path.relative_to(root)
            path_kind = legacy_source_path_kind(relative, suffix=path.suffix.lower())
            if path_kind is not None:
                refs.add(f"{relative.as_posix()}#{path_kind}")
            if path.suffix.lower() not in PRODUCTION_SCAN_SUFFIXES:
                continue
            try:
                text = _read_regular_text(path)
            except (OSError, UnicodeError) as exc:
                errors.append(f"{relative.as_posix()}: production source unreadable: {exc}")
                continue
            for kind in _legacy_text_kinds(
                relative, text, include_cli_registration=False
            ):
                refs.add(f"{relative.as_posix()}#{kind}")
    return LegacyRuntimeScan(tuple(sorted(refs)), tuple(sorted(set(errors))))



def _module_name(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (*_module_name(node.value), node.attr)
    return ()


def python_imports(source: Path, *, module: str | None = None) -> tuple[str, ...]:
    try:
        tree = ast.parse(_read_regular_text(source))
    except (OSError, UnicodeError, SyntaxError):
        return ()
    imports: set[str] = set()
    package = module.rpartition(".")[0] if module and source.name != "__init__.py" else (module or "")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                keep = max(0, len(parts) - node.level + 1)
                imported = ".".join([*parts[:keep], imported] if imported else parts[:keep])
            if imported:
                imports.add(imported)
                for alias in node.names:
                    if alias.name != "*":
                        imports.add(f"{imported}.{alias.name}")
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            name = ".".join(_module_name(node.func))
            if name in {"importlib.import_module", "__import__"}:
                imports.add(node.args[0].value)
    return tuple(sorted(imports))


def scan_live_python_import_graph(
    *, scripts_root: Path, entry_modules: tuple[str, ...] = ("cli",)
) -> LegacyRuntimeScan:
    """Traverse only modules reachable from public CLI entry points."""
    root = Path(scripts_root).resolve()
    pending = list(entry_modules)
    visited: set[str] = set()
    missing_local: set[str] = set()
    refs: set[str] = set()
    errors: list[str] = []
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        path = root / (module.replace(".", "/") + ".py")
        if not path.is_file():
            package = root / module.replace(".", "/") / "__init__.py"
            if not package.is_file():
                if module in entry_modules:
                    missing_local.add(module)
                continue
            path = package
        for imported in python_imports(path, module=module):
            if any(imported == prefix or imported.startswith(prefix + ".") for prefix in FORBIDDEN_RUNTIME_MODULE_PREFIXES):
                refs.add(f"{path.relative_to(root).as_posix()}#forbidden runtime import {imported}")
            if imported.startswith("content.execution.") and imported.split(".")[2] in LEGACY_ORCHESTRATION_FAMILIES:
                refs.add(f"{path.relative_to(root).as_posix()}#retired live import {imported}")
            candidate = root / (imported.replace(".", "/") + ".py")
            package = root / imported.replace(".", "/") / "__init__.py"
            if candidate.is_file() or package.is_file():
                pending.append(imported)
        try:
            text = _read_regular_text(path)
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: live import scan unreadable: {exc}")
            continue
        if re.search(r"\b(?:ReliableTask|reliabletask|data-content-worker|data_content_worker)\b", text):
            refs.add(f"{path.relative_to(root).as_posix()}#forbidden Data worker/fleet runtime")
    errors.extend(f"live entry module is unavailable: {module}" for module in sorted(missing_local))
    return LegacyRuntimeScan(tuple(sorted(refs)), tuple(sorted(errors)))

__all__ = [
    "LEGACY_ORCHESTRATION_FAMILIES",
    "LegacyRuntimeScan",
    "PRODUCTION_SCAN_EXCLUDED_PARTS",
    "PRODUCTION_SCAN_SUFFIXES",
    "SCANNED_ROOTS",
    "legacy_python_import_reference",
    "legacy_source_path_kind",
    "scan_data_legacy_orchestration_entries",
    "scan_legacy_runtime_entries",
    "scan_live_python_import_graph",
    "python_imports",
    "FORBIDDEN_RUNTIME_MODULE_PREFIXES",
]
