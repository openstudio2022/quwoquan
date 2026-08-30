#!/usr/bin/env python3
"""Canonical local-readiness impact planner shared with hosted scope detection."""
from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.impact_planner_core import (  # noqa: E402
    ImpactPlannerError,
    classify_impacts,
    normalize_changed_paths,
    planner_identity,
)
from quwoquan_ops.gate.commit_gate_select import build_plan as build_commit_plan  # noqa: E402

PLAN_SCHEMA = "local-readiness-plan-v1"
CHECK_FIELDS = ("id", "scope", "phase", "command", "cwd", "resources")
LOCKFILE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "service": ("quwoquan_service/go.mod", "quwoquan_service/go.sum"),
    "app": ("quwoquan_app/pubspec.yaml", "quwoquan_app/pubspec.lock"),
    "portal": ("quwoquan_ops/portal/package.json", "quwoquan_ops/portal/package-lock.json"),
    "data": ("quwoquan_data/pyproject.toml", "quwoquan_data/requirements.txt"),
    "spec_contract": (
        "quwoquan_ops/policies/local_readiness_contract.yaml",
        "quwoquan_ops/policies/agent_governance_contract.yaml",
    ),
}
STATIC_COMMANDS: dict[str, tuple[list[str], str, list[str]]] = {
    "branch_policy": (["python3", "-B", "quwoquan_ops/gate/verify_git_branch_policy.py"], ".", ["git-index"]),
    "feature_tree": (["make", "verify-feature-tree"], ".", ["feature-tree"]),
    "entrypoint_script_paths": (["python3", "-B", "quwoquan_ops/gate/verify_entrypoint_script_paths.py"], ".", ["ops-static"]),
    "local_worktree_lifecycle": (["python3", "-B", "quwoquan_ops/gate/verify_local_worktree_lifecycle.py"], ".", ["git-worktree"]),
    "service_architecture": (["make", "verify-service-architecture"], ".", ["service-static"]),
    "service_probe_homology": (["make", "verify-service-probe-homology"], ".", ["service-static"]),
    "app_generated_manifest": (["make", "verify-app-generated-manifest"], ".", ["app-codegen"]),
    "app_contract_handoff": (["make", "verify-app-contract-handoff"], ".", ["app-codegen"]),
    "metadata_contract": (["bash", "quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh"], ".", ["contract-graph"]),
    "commercial_contract": (["make", "verify-commercial-contract-generation"], ".", ["contract-graph"]),
    "data_verify": (["python3", "-B", "quwoquan_data/scripts/cli.py", "verify", "all"], ".", ["data-verify"]),
    "pageflip_backward_mainline": (["make", "verify-app-pageflip-back-mainline"], ".", ["app-static"]),
    "app_uat_widget_key_references": (["make", "verify-app-uat-widget-key-references"], ".", ["app-static"]),
    "verify-app-mock-isolation": (["make", "verify-app-mock-isolation"], ".", ["app-static"]),
    "verify-app-cloud-package-boundaries": (["make", "verify-app-cloud-package-boundaries"], ".", ["app-static"]),
    "verify-app-login-entry-loop": (["make", "verify-app-login-entry-loop-contract"], ".", ["app-static"]),
    "verify-app-enum-typed-binding": (["make", "verify-app-enum-typed-binding"], ".", ["app-static"]),
    "verify-app-assistant-search-weak-typing-ratchet": (["make", "verify-app-assistant-search-weak-typing-ratchet"], ".", ["app-static"]),
}


def _normalize_paths(paths: list[str], _repo_root: Path) -> list[str]:
    return normalize_changed_paths(paths)


def classify_scopes(paths: list[str]) -> list[str]:
    """Project the canonical shared impact classifier into local scope names."""

    classified = classify_impacts(paths)
    return sorted(scope for scope, required in classified["local_scopes"].items() if required)


def _check(
    check_id: str,
    scope: str,
    phase: str,
    command: list[str],
    *,
    cwd: str = ".",
    resources: list[str] | None = None,
) -> dict[str, Any]:
    if not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError(f"check={check_id} command 非法")
    value = {
        "id": check_id,
        "scope": scope,
        "phase": phase,
        "command": command,
        "cwd": cwd,
        "resources": sorted(set(resources or [f"scope:{scope}"])),
    }
    if tuple(value) != CHECK_FIELDS:
        raise ValueError(f"check={check_id} schema 漂移")
    return value


def _static_check(check_id: str) -> dict[str, Any] | None:
    if check_id.startswith("python_script_governance_"):
        owner = check_id.removeprefix("python_script_governance_")
        return _check(
            f"static:{check_id}",
            "spec_contract",
            "static",
            ["python3", "-B", "quwoquan_ops/gate/verify_python_script_governance.py", "--scope", owner, "--mode", "check"],
            resources=["python-governance"],
        )
    registered = STATIC_COMMANDS.get(check_id)
    if registered is None:
        return None
    command, cwd, resources = registered
    return _check(f"static:{check_id}", "spec_contract", "static", list(command), cwd=cwd, resources=resources)


def build_impact_plan(
    paths: list[str],
    *,
    level: str,
    flutter_cap: int = 40,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Build one closed executable plan; only ``fast`` may retain deferred work."""

    if level not in {"fast", "scope", "release"}:
        raise ValueError(f"local readiness level 非法：{level}")
    if not paths:
        return {
            "schema": PLAN_SCHEMA,
            "impact_planner": planner_identity(),
            "level": level,
            "paths": [],
            "scopes": [],
            "lockfiles": [],
            "checks": [],
            "deferred": [],
        }
    normalized = _normalize_paths(paths, repo_root)
    commit = (
        build_commit_plan(normalized, flutter_cap)
        if repo_root.resolve() == ROOT.resolve()
        else {"static_checks": [], "pytest_paths": [], "deferred_to_ci": [], "flutter_tests": [], "go_services": []}
    )
    scopes = classify_scopes(normalized)
    if not scopes:
        scopes = ["spec_contract"]
    checks: list[dict[str, Any]] = []
    deferred: list[dict[str, str]] = []

    for static in commit["static_checks"]:
        check = _static_check(static)
        if check is None:
            raise ValueError(f"unregistered canonical static check: {static}")
        checks.append(check)

    pytest_paths = list(commit["pytest_paths"])
    pytest_deferred = [path for path in commit["deferred_to_ci"] if path.endswith(".py") or "tests/local_contract" in path]
    if level != "fast":
        pytest_paths.extend(path for path in pytest_deferred if path not in pytest_paths)
    elif pytest_deferred:
        deferred.extend({"scope": "data", "work": path} for path in pytest_deferred)
    if pytest_paths:
        checks.append(
            _check(
                "focused:python",
                "data",
                "focused",
                ["python3", "-B", "quwoquan_ops/cli/local_readiness.py", "managed-pytest", *pytest_paths],
                resources=["python-tests"],
            )
        )

    flutter_tests = list(commit["flutter_tests"])
    flutter_deferred = [path for path in commit["deferred_to_ci"] if path.endswith(".dart")]
    if level != "fast":
        flutter_tests.extend(path.removeprefix("quwoquan_app/") for path in flutter_deferred if path.removeprefix("quwoquan_app/") not in flutter_tests)
    elif flutter_deferred:
        deferred.extend({"scope": "app", "work": path} for path in flutter_deferred)
    if flutter_tests:
        checks.append(
            _check(
                "focused:dart",
                "app",
                "focused",
                ["python3", "-B", "quwoquan_app/scripts/env/run_flutter_test_guarded.py", *flutter_tests],
                resources=["flutter-test"] ,
            )
        )

    go_services = list(commit["go_services"])
    for service in go_services:
        package = f"./services/{service}/..."
        checks.append(_check(f"focused:go:{service}", "service", "focused", ["go", "test", package, "-count=1", "-p=4"], cwd="quwoquan_service", resources=[f"go:{service}"]))
        if level != "fast":
            checks.append(_check(f"scope_build:go-compile:{service}", "service", "scope_build", ["go", "test", package, "-run", "^$", "-count=1", "-p=4"], cwd="quwoquan_service", resources=[f"go:{service}"]))
            checks.append(_check(f"scope_build:go-build:{service}", "service", "scope_build", ["go", "build", package], cwd="quwoquan_service", resources=[f"go:{service}"]))

    if "portal" in scopes:
        checks.append(_check("focused:portal-test", "portal", "focused", ["python3", "-B", "quwoquan_ops/cli/local_readiness.py", "managed-portal-test"], resources=["npm:portal"]))
        if level != "fast":
            checks.append(_check("scope_build:portal-build", "portal", "scope_build", ["python3", "-B", "quwoquan_ops/cli/local_readiness.py", "managed-portal-build"], resources=["npm:portal"]))

    if level != "fast" and "service" in scopes and not go_services:
        checks.append(_check("scope_build:service-compile", "service", "scope_build", ["go", "test", "./...", "-run", "^$", "-count=1", "-p=4"], cwd="quwoquan_service", resources=["go:service-all"]))
        checks.append(_check("scope_build:service-build", "service", "scope_build", ["go", "build", "./..."], cwd="quwoquan_service", resources=["go:service-all"]))
    if level != "fast" and "app" in scopes:
        checks.append(_check("scope_build:app-package-smoke", "app", "scope_build", ["flutter", "build", "apk", "--debug", "--no-pub"], cwd="quwoquan_app", resources=["flutter-build"]))
    if level != "fast" and "data" in scopes:
        if not any(check["id"] == "static:data_verify" for check in checks):
            checks.append(_check("scope_build:data-verify-all", "data", "scope_build", ["python3", "-B", "quwoquan_data/scripts/cli.py", "verify", "all"], resources=["data-verify"]))
        if any(path.startswith("quwoquan_data/") for path in normalized) and not any(check["id"] == "focused:python" for check in checks):
            raise ValueError("data scope planner 未能选择 affected tests；拒绝以 verify-only 生成 scope_ready")
    if level != "fast" and "spec_contract" in scopes and not any(check["id"] == "static:feature_tree" for check in checks):
        checks.append(_check("scope_build:feature-tree", "spec_contract", "scope_build", ["make", "verify-feature-tree"], resources=["feature-tree"]))

    if level == "release":
        for scope in (scope for scope in scopes if scope in {"service", "app", "data", "portal"}):
            checks.append(_check(f"release:{scope}", scope, "release", ["bash", "quwoquan_ops/gate/gate_repo.sh", "--scope", scope], resources=[f"release:{scope}"]))
        if "data" in scopes:
            data_release = [check for check in checks if check["id"] == "release:data"]
            if len(data_release) != 1 or data_release[0]["command"] != ["bash", "quwoquan_ops/gate/gate_repo.sh", "--scope", "data"]:
                raise ValueError("data-required release plan 必须包含 canonical full data gate；不得 skip/defer")

    if not checks:
        checks.append(_check("focused:git-diff-check", "spec_contract", "focused", ["git", "diff", "--check", "--", *normalized], resources=["git-index"]))
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for check in checks:
        key = (check["id"], json.dumps(check["command"], ensure_ascii=False, separators=(",", ":")))
        if key not in seen:
            seen.add(key)
            unique.append(check)
    if not unique:
        raise ValueError("local readiness planner 产生空 checks")

    lockfiles = sorted({path for scope in scopes for path in LOCKFILE_CANDIDATES.get(scope, ()) if (repo_root / path).exists()})
    return {
        "schema": PLAN_SCHEMA,
        "impact_planner": planner_identity(),
        "level": level,
        "paths": normalized,
        "scopes": scopes,
        "lockfiles": lockfiles,
        "checks": unique,
        "deferred": deferred,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("fast", "scope", "release"), required=True)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--flutter-cap", type=int, default=40)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        plan = build_impact_plan(args.changed_file, level=args.level, flutter_cap=args.flutter_cap)
    except (ImpactPlannerError, ValueError) as exc:
        print(f"local-readiness-planner: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    json.dump(plan, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
