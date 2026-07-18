#!/usr/bin/env python3
"""Enforce the data-script ownership tree and import direction."""
from __future__ import annotations

import ast
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parent.parent
ALLOWED_ROOT_ENTRIES = {"cli.py", "core", "content", "governance", "verify", "__init__.py"}
RETIRED_DIRECTORIES = {
    "annotate", "audit", "build", "data", "download", "env", "explore", "fixture",
    "homepage_assets", "media", "plan", "produce", "publish", "quality", "reconcile",
    "ship", "taxonomy", "template", "vertical", "workflow", "_common", "_scratch", "ops",
}
RETIRED_NESTED_DIRECTORIES = {
    Path("content/execution/workflow"),
    Path("content/execution/pipeline"),
}
RETIRED_MODULE_PATHS = {
    Path("content/execution/controller/run.py"),
    Path("content/post/video/workflow.py"),
}
STRONG_CONTROL_MODULES = {
    Path("content/execution/controller/orchestrator.py"),
    Path("content/release/canonical/release_attestation.py"),
    Path("content/post/video/authoring.py"),
    Path("content/post/video/materialize.py"),
}
RETIRED_PATH_FRAGMENTS = {
    "scripts/content/execution/workflow/",
    "scripts/content/execution/pipeline/",
    "scripts/content/execution/controller/cli.py",
    "scripts/content/post/entity_workflow.py",
    "scripts/download/",
    "scripts/site_supply/",
    "schema/build/",
    "schema/download/",
    "schema/explore/",
    "schema/reconcile/",
    "schema/tag/",
    "schema/template/",
    "schema/coverage/",
}
MAX_MODULE_LINES = 600
MAX_CONTROLLER_LINES = 500
MAX_CLI_LINES = 400
TYPED_ISSUE_FACTORIES = {"DataIssue", "data_issue", "data_issues"}
RETIRED_WEAK_CONTROL_TOKENS = {
    "_ABANDONED_ENTITY_RETRYABLE_REASON_MARKERS",
    "_ASSET_ID_LEGACY_RE",
    "_entity_ids_from_issue_messages",
    "auto_generate",
    "retryOnStageReset",
}
CONTROL_BUDGET_KEYWORDS = {
    "timeout",
    "timeout_seconds",
    "max_retries",
    "max_workers",
}


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _typed_issue_ast_issues(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path.relative_to(REPO_ROOT)}:{exc.lineno}: invalid Python syntax"]
    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        if name not in TYPED_ISSUE_FACTORIES:
            continue
        for keyword in node.keywords:
            if keyword.arg in {"stage", "lane", "recovery"} and isinstance(
                keyword.value, ast.Constant
            ):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                    f"{name}.{keyword.arg} must use the closed Enum, not a wire literal"
                )
    return issues


def _is_message_expression(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Attribute) and child.attr == "message"
        for child in ast.walk(node)
    )


def _control_flow_ast_issues(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            broad = (
                isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
            )
            if broad and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: broad exception must not be silently passed"
                )
        if isinstance(node, ast.Compare) and any(
            isinstance(operator, (ast.In, ast.NotIn)) for operator in node.ops
        ):
            expressions = [node.left, *node.comparators]
            if any(_is_message_expression(expression) for expression in expressions):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: DataIssue.message is presentation only and must not drive control flow"
                )
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if (
                keyword.arg in CONTROL_BUDGET_KEYWORDS
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, (int, float))
            ):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                    f"{keyword.arg} must use a named policy constant, not {keyword.value.value!r}"
                )
    return issues


def _weak_control_type_issues(path: Path) -> list[str]:
    relative = path.relative_to(SCRIPTS_ROOT)
    if relative not in STRONG_CONTROL_MODULES:
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {"Any", "Mapping"}:
            issues.append(
                f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                f"{relative} is a strong control module and may not use {node.id}"
            )
    return issues


def script_architecture_issues() -> list[str]:
    issues: list[str] = []
    for required in (
        SCRIPTS_ROOT / "content/post/article",
        SCRIPTS_ROOT / "content/post/image",
        SCRIPTS_ROOT / "content/post/video",
    ):
        if not required.is_dir():
            issues.append(f"{required.relative_to(REPO_ROOT)}: required carrier owner is missing")
    for entry in sorted(SCRIPTS_ROOT.iterdir()):
        if entry.name == "__pycache__":
            issues.append(f"{entry.relative_to(REPO_ROOT)}: generated cache must not exist in source tree")
        elif entry.name not in ALLOWED_ROOT_ENTRIES:
            issues.append(f"{entry.relative_to(REPO_ROOT)}: unsupported scripts root entry")
        elif entry.name in RETIRED_DIRECTORIES:
            issues.append(f"{entry.relative_to(REPO_ROOT)}: retired scripts directory")
    for relative in sorted(RETIRED_NESTED_DIRECTORIES):
        path = SCRIPTS_ROOT / relative
        if path.exists():
            issues.append(f"{path.relative_to(REPO_ROOT)}: retired nested scripts directory")
    for relative in sorted(RETIRED_MODULE_PATHS):
        path = SCRIPTS_ROOT / relative
        if path.exists():
            issues.append(f"{path.relative_to(REPO_ROOT)}: retired ambiguous module")
    for path in _python_files(SCRIPTS_ROOT):
        text = path.read_text(encoding="utf-8")
        lines = text.count("\n") + 1
        if path.name == "cli.py":
            limit = MAX_CLI_LINES
        elif (SCRIPTS_ROOT / "content/execution/controller") in path.parents:
            limit = MAX_CONTROLLER_LINES
        else:
            limit = MAX_MODULE_LINES
        if lines > limit:
            issues.append(
                f"{path.relative_to(REPO_ROOT)}: {lines} lines exceeds module limit {limit}"
            )
        issues.extend(_typed_issue_ast_issues(path))
        issues.extend(_control_flow_ast_issues(path))
        issues.extend(_weak_control_type_issues(path))
        if path.resolve() != Path(__file__).resolve():
            for token in sorted(RETIRED_WEAK_CONTROL_TOKENS):
                if token in text:
                    issues.append(
                        f"{path.relative_to(REPO_ROOT)}: retired weak control token {token}"
                    )
            for fragment in sorted(RETIRED_PATH_FRAGMENTS):
                if fragment in text:
                    issues.append(
                        f"{path.relative_to(REPO_ROOT)}: retired path reference {fragment}"
                    )
    for path in _python_files(SCRIPTS_ROOT / "core"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("from content.", "from governance.", "from verify.", "import content.", "import governance.", "import verify.")):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}: core may not depend on domain layer: {stripped}"
                )
                break
    return issues


def main() -> int:
    issues = script_architecture_issues()
    if issues:
        print("[verify_script_architecture] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_script_architecture] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
