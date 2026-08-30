#!/usr/bin/env python3
"""Enforce the data-script ownership tree and import direction."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from verify.legacy_runtime_entries import (
    LEGACY_ORCHESTRATION_FAMILIES,
    scan_data_legacy_orchestration_entries,
    scan_legacy_runtime_entries,
    scan_live_python_import_graph,
)


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parent.parent
PRESERVED_PROTOCOL_KERNELS = ("closure", "runtime_evidence", "scale")
RETIREMENT_INVENTORY_RELATIVE = Path(
    "quwoquan_data/control_plane/execution/legacy_orchestration_retirement.json"
)
_RETIREMENT_INVENTORY_KEYS = frozenset(
    {
        "schema",
        "state",
        "deleteFamilies",
        "preserveProtocolKernels",
        "forbiddenCompatibility",
    }
)
ALLOWED_ROOT_ENTRIES = {"cli.py", "core", "content", "governance", "verify", "__init__.py"}
EXECUTION_ROOT_MODULES = frozenset(
    {
        "__init__.py",
        "asset_registry.py",
        "baseline.py",
        "baseline_packet.py",
        "carrier_contract.py",
        "context.py",
        "contracts.py",
        "coverage.py",
        "diagnostics.py",
        "execution_state_journal.py",
        "execution_supersession.py",
        "execution_terminal.py",
        "handler.py",
        "identity.py",
        "model_contract.py",
        "operation_views.py",
        "operational_fingerprint.py",
        "production_contracts.py",
        "prompt_snapshot.py",
        "receipt_state_reducer.py",
        "request.py",
        "runtime_contract.py",
        "runtime_state.py",
        "spec_contract.py",
        "stable_production_proof.py",
        "stage_receipt.py",
        "stage_receipt_cli.py",
        "stage_reports.py",
        "task_init.py",
        "task_init_cli.py",
        "store.py",
        "support.py",
        "target_integrity.py",
        "terminal_evidence_precheck.py",
        "terminal_state_integrity.py",
        "workspace.py",
    }
)
FORBIDDEN_DATA_CACHE_DIRS = frozenset(
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
LOOKUP_INDEX_MODULE = Path(
    "content/release/canonical/build_lookup_indexes.py"
)
_MILESTONE_NAME_FRAGMENTS = (
    "t[1-4]",
    "m6",
    "m7",
    "b" + "10",
    "ph" + "ase" + "[0-9]+",
    "p" + "art" + "[0-9]+",
)
MILESTONE_NAME_RE = re.compile(
    r"(^|[_-])(?:" + "|".join(_MILESTONE_NAME_FRAGMENTS) + r")(?=[_.-]|$)",
    re.IGNORECASE,
)
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


def _lookup_index_boundary_issues() -> list[str]:
    path = SCRIPTS_ROOT / LOOKUP_INDEX_MODULE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "content.release.environment",
        "OUTPUT_ROOT",
        "envImports",
        "homepageId",
        "introductionUrl",
    )
    return [
        f"{path.relative_to(REPO_ROOT)}: immutable lookup indexes "
        f"must not depend on environment runtime token {token}"
        for token in forbidden
        if token in text
    ]


def _retirement_inventory() -> tuple[str, list[str]]:
    path = REPO_ROOT / RETIREMENT_INVENTORY_RELATIVE
    if not path.is_file() or path.is_symlink():
        return "pre_delete", []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return "blocked", [
            f"GATE_BLOCK {path.relative_to(REPO_ROOT)}: "
            f"retirement inventory unreadable: {exc}"
        ]
    issues: list[str] = []
    expected = {
        "schema": "quwoquan_data.legacy_orchestration_retirement_inventory",
        "deleteFamilies": list(LEGACY_ORCHESTRATION_FAMILIES),
        "preserveProtocolKernels": list(PRESERVED_PROTOCOL_KERNELS),
        "forbiddenCompatibility": ["alias", "dual_read", "dual_write", "shim"],
    }
    if not isinstance(value, dict) or set(value) != _RETIREMENT_INVENTORY_KEYS:
        issues.append(
            f"GATE_BLOCK {path.relative_to(REPO_ROOT)}: "
            "retirement inventory fields mismatch"
        )
        return "blocked", issues
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            issues.append(
                f"GATE_BLOCK {path.relative_to(REPO_ROOT)}: "
                f"retirement inventory {field} drifted"
            )
    state = value.get("state")
    if state not in {"pre_delete", "operationally_retired", "retired"}:
        issues.append(
            f"GATE_BLOCK {path.relative_to(REPO_ROOT)}: "
            "retirement inventory state is invalid"
        )
    return (str(state) if not issues else "blocked"), issues


def _legacy_orchestration_post_delete_issues() -> list[str]:
    package_roots = tuple(
        name
        for name in ("quwoquan_app", "quwoquan_service", "quwoquan_ops", ".github")
        if (REPO_ROOT / name).exists()
    )
    package_scan = scan_legacy_runtime_entries(REPO_ROOT, root_names=package_roots)
    data_scan = scan_data_legacy_orchestration_entries(
        scripts_root=SCRIPTS_ROOT, repo_root=REPO_ROOT
    )
    return [
        *(f"GATE_BLOCK {ref}" for ref in data_scan.legacy_entry_refs),
        *(f"GATE_BLOCK {ref}" for ref in package_scan.legacy_entry_refs),
        *(f"GATE_BLOCK {error}" for error in data_scan.scan_errors),
        *(f"GATE_BLOCK {error}" for error in package_scan.scan_errors),
    ]


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
    execution_root = SCRIPTS_ROOT / "content/execution"
    for path in sorted(execution_root.glob("*.py")):
        if path.name not in EXECUTION_ROOT_MODULES:
            issues.append(
                f"{path.relative_to(REPO_ROOT)}: execution root only permits "
                "stable kernel and CLI binding modules"
            )
    for path in _python_files(SCRIPTS_ROOT):
        if MILESTONE_NAME_RE.search(path.name):
            issues.append(
                f"{path.relative_to(REPO_ROOT)}: "
                "stable script names must describe behavior, not "
                "T/M/B/phase/part milestones"
            )
        text = path.read_text(encoding="utf-8")
        # 末行换行符不开启新的一行。多算 1 行会把恰好用满预算的模块报成超限。
        lines = text.count("\n") + (0 if text.endswith("\n") else 1)
        if path == SCRIPTS_ROOT / "cli.py":
            limit = MAX_CLI_LINES
        elif path.parent == SCRIPTS_ROOT / "content/execution/controller":
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
    for cache_name in sorted(FORBIDDEN_DATA_CACHE_DIRS):
        direct = SCRIPTS_ROOT.parent / cache_name
        if direct.exists():
            issues.append(
                f"{direct.relative_to(REPO_ROOT)}: generated cache must not exist in source tree"
            )
        for scan_root in (SCRIPTS_ROOT, SCRIPTS_ROOT.parent / "tests"):
            for path in sorted(scan_root.rglob(cache_name)):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}: generated cache must not exist in source tree"
                )
    issues.extend(_lookup_index_boundary_issues())
    retirement_state, retirement_issues = _retirement_inventory()
    issues.extend(retirement_issues)
    live_scan = scan_live_python_import_graph(scripts_root=SCRIPTS_ROOT)
    issues.extend(f"GATE_BLOCK {ref}" for ref in live_scan.legacy_entry_refs)
    issues.extend(f"GATE_BLOCK {error}" for error in live_scan.scan_errors)
    if retirement_state == "retired":
        issues.extend(_legacy_orchestration_post_delete_issues())
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
