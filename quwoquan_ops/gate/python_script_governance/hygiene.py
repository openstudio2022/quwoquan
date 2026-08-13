"""命名、缓存/临时文件卫生与无 owner tool 违规。"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .constants import (
    FORBIDDEN_CACHE_DIR_NAMES,
    FORBIDDEN_TEMP_FILE_SUFFIXES,
    MILESTONE_NAME_RE,
    PYTHON_SCOPE_ROOTS,
    TEMP_SCRIPT_NAME_RE,
)
from .inventory import ripgrep_files
from .models import Issue, ScriptRecord, relative_path


def naming_issues(root: Path, scripts: Sequence[Path]) -> list[Issue]:
    issues: list[Issue] = []
    for path in scripts:
        if MILESTONE_NAME_RE.search(path.name):
            relative = relative_path(root, path)
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


def source_hygiene_issues(root: Path, scopes: Sequence[str]) -> list[Issue]:
    issues: list[Issue] = []
    for scope in scopes:
        scope_root = root / PYTHON_SCOPE_ROOTS[scope]
        if not scope_root.is_dir():
            continue
        cache_globs = tuple(
            f"**/{name}/**" for name in sorted(FORBIDDEN_CACHE_DIR_NAMES)
        )
        cache_directories: set[Path] = set()
        for path in ripgrep_files(
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
                path=relative_path(root, path),
                message=(
                    "Python/lint/test cache belongs under .qwq_output "
                    "or a managed external cache"
                ),
            )
            for path in sorted(cache_directories)
        )

        hygiene_files = ripgrep_files(
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
                        path=relative_path(root, path),
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
                        path=relative_path(root, path),
                        message=(
                            "temporary scripts require a stable owner "
                            "and semantic name"
                        ),
                    )
                )
    return issues


def tool_owner_issues(records: Sequence[ScriptRecord]) -> list[Issue]:
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
