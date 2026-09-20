#!/usr/bin/env python3
"""Canonical local-readiness impact planner shared with hosted scope detection."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

sys.dont_write_bytecode = True
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.impact_planner_core import (  # noqa: E402
    ImpactPlannerError,
    classify_impacts,
    normalize_changed_paths,
    planner_identity,
)
from quwoquan_ops.gate.commit_gate_select import (  # noqa: E402
    DATA_SEMANTIC_PORTAL_SOURCE,
    build_plan as build_commit_plan,
)

PLAN_SCHEMA = "local-readiness-plan-v2"
TIMEOUT_POLICY_SCHEMA = "local-readiness-timeouts-v1"
CONTRACT_PATH = ROOT / "quwoquan_ops/policies/local_readiness_contract.yaml"
_RAW_CHECK_FIELDS = ("id", "scope", "phase", "command", "cwd", "resources")
CHECK_FIELDS = (*_RAW_CHECK_FIELDS, "timeout_seconds")
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
    "retired_terms_zero": (["python3", "-B", "quwoquan_app/scripts/runtime/architecture/verify_retired_terms_zero.py"], ".", ["ops-static"]),
    "branch_policy": (["python3", "-B", "quwoquan_ops/gate/verify_git_branch_policy.py", "--local-commit"], ".", ["git-index"]),
    "feature_tree": (["make", "verify-feature-tree"], ".", ["feature-tree"]),
    "entrypoint_script_paths": (["python3", "-B", "quwoquan_ops/gate/verify_entrypoint_script_paths.py"], ".", ["ops-static"]),
    "workflow_cli_arguments": (["python3", "-B", "quwoquan_ops/gate/verify_workflow_cli_arguments.py"], ".", ["ops-static"]),
    "workflow_actionlint": (["bash", "quwoquan_ops/gate/verify_workflow_actionlint.sh"], ".", ["ops-static"]),
    "local_worktree_lifecycle": (["python3", "-B", "quwoquan_ops/gate/verify_local_worktree_lifecycle.py"], ".", ["git-worktree"]),
    "service_architecture": (["make", "verify-service-architecture"], ".", ["service-static"]),
    "service_probe_homology": (["make", "verify-service-probe-homology"], ".", ["service-static"]),
    "app_generated_manifest": (["make", "verify-app-generated-manifest"], ".", ["app-codegen"]),
    "app_contract_handoff": (["make", "verify-app-contract-handoff"], ".", ["app-codegen"]),
    "metadata_contract": (["bash", "quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh"], ".", ["contract-graph"]),
    "contract_closure": (["python3", "-B", "quwoquan_data/scripts/cli.py", "verify", "contract-closure"], ".", ["contract-graph"]),
    "commercial_contract": (["make", "verify-commercial-contract-generation"], ".", ["contract-graph"]),
    "data_verify": (["python3", "-B", "quwoquan_data/scripts/cli.py", "verify", "all", "--scope", "source"], ".", ["data-verify"]),
    "pageflip_backward_mainline": (["make", "verify-app-pageflip-back-mainline"], ".", ["app-static"]),
    "app_uat_widget_key_references": (["make", "verify-app-uat-widget-key-references"], ".", ["app-static"]),
    "verify-app-mock-isolation": (["make", "verify-app-mock-isolation"], ".", ["app-static"]),
    "verify-app-cloud-package-boundaries": (["make", "verify-app-cloud-package-boundaries"], ".", ["app-static"]),
    "verify-app-login-entry-loop": (["make", "verify-app-login-entry-loop-contract"], ".", ["app-static"]),
    "verify-app-enum-typed-binding": (["make", "verify-app-enum-typed-binding"], ".", ["app-static"]),
    "verify-app-assistant-search-weak-typing-ratchet": (["make", "verify-app-assistant-search-weak-typing-ratchet"], ".", ["app-static"]),
    "code_health_delta_fast": (["python3", "-B", "quwoquan_ops/gate/verify_incremental_code_health.py", "--base", "HEAD", "--head", "HEAD", "--working-tree", "--mode", "fast"], ".", ["code-health"]),
}


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bounded_timeout(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 86400):
        raise ValueError(f"local readiness {label} 必须为 1..86400 的整数秒")
    return value


def load_timeout_policy(path: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = path or CONTRACT_PATH
    try:
        contract = yaml.safe_load(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"local readiness timeout policy 无法读取: {exc}") from exc
    if not isinstance(contract, dict) or contract.get("schema_version") != 2:
        raise ValueError("local readiness contract schema_version 非法")
    policy = contract.get("timeouts")
    expected = {
        "schema_version", "default_seconds", "default_by_level",
        "default_by_phase", "maximum_by_level", "overrides_by_check",
        "resolution_order",
    }
    if not isinstance(policy, dict) or set(policy) != expected:
        raise ValueError("local readiness timeouts 字段漂移")
    if policy.get("schema_version") != 1:
        raise ValueError("local readiness timeouts schema_version 非法")
    _bounded_timeout(policy.get("default_seconds"), label="timeouts.default_seconds")
    levels = policy.get("default_by_level")
    maxima = policy.get("maximum_by_level")
    phases = policy.get("default_by_phase")
    overrides = policy.get("overrides_by_check")
    if not isinstance(levels, dict) or set(levels) != {"fast", "scope", "release"}:
        raise ValueError("local readiness timeout level defaults 必须闭合 fast/scope/release")
    if not isinstance(maxima, dict) or set(maxima) != {"fast", "scope", "release"}:
        raise ValueError("local readiness timeout level maxima 必须闭合 fast/scope/release")
    if not isinstance(phases, dict) or set(phases) != {"static", "focused", "scope_build", "release"}:
        raise ValueError("local readiness timeout phase defaults 必须闭合")
    if not isinstance(overrides, dict) or not all(isinstance(key, str) and key for key in overrides):
        raise ValueError("local readiness timeout check overrides 非法")
    for label, values in (
        ("default_by_level", levels),
        ("maximum_by_level", maxima),
        ("default_by_phase", phases),
        ("overrides_by_check", overrides),
    ):
        for key, value in values.items():
            _bounded_timeout(value, label=f"timeouts.{label}.{key}")
    for level in ("fast", "scope", "release"):
        if levels[level] > maxima[level]:
            raise ValueError(f"local readiness timeout level default 超过上限: {level}")
    if policy.get("resolution_order") != ["check", "phase", "level", "default"]:
        raise ValueError("local readiness timeout resolution_order 非 canonical")
    identity = {
        "schema": TIMEOUT_POLICY_SCHEMA,
        "source": "quwoquan_ops/policies/local_readiness_contract.yaml",
        "digest": _canonical_digest(policy),
    }
    return policy, identity


def _canonical_check_timeout(
    check: dict[str, Any], *, level: str, policy: dict[str, Any]
) -> dict[str, Any]:
    configured = policy["overrides_by_check"].get(check["id"])
    if configured is None:
        configured = policy["default_by_phase"].get(check["phase"])
    if configured is None:
        configured = policy["default_by_level"].get(level)
    if configured is None:
        configured = policy["default_seconds"]
    timeout_seconds = min(configured, policy["maximum_by_level"][level])
    value = {**check, "timeout_seconds": timeout_seconds}
    if tuple(value) != CHECK_FIELDS:
        raise ValueError(f"check={check['id']} timeout schema 漂移")
    return value


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
    if tuple(value) != _RAW_CHECK_FIELDS:
        raise ValueError(f"check={check_id} raw schema 漂移")
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


def _data_semantic_portal_checks(paths: list[str]) -> list[dict[str, Any]]:
    """TS 生成物必须跑真实 Portal 消费者，Python 交接合同不能替代它。"""
    if DATA_SEMANTIC_PORTAL_SOURCE not in paths:
        return []
    return [_check(
        "focused:data-semantic-portal", "data", "focused", ["npm", "test"],
        cwd="quwoquan_data/control_plane/content_workbench/portal",
        resources=["npm:data-portal"],
    )]


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
    timeout_policy, timeout_policy_identity = load_timeout_policy(
        (repo_root / "quwoquan_ops/policies/local_readiness_contract.yaml")
        if (repo_root / "quwoquan_ops/policies/local_readiness_contract.yaml").is_file()
        else CONTRACT_PATH
    )
    if not paths:
        return {
            "schema": PLAN_SCHEMA,
            "impact_planner": planner_identity(),
            "timeout_policy": timeout_policy_identity,
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

    source_paths = [
        path for path in normalized
        if path.startswith(("quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/"))
    ]
    if level != "fast" and source_paths:
        checks = [check for check in checks if check["id"] != "static:code_health_delta_fast"]
        # L1/L2 看整条 lane 相对 dev1.0 的分歧（merge-base），而不是只看未提交改动；
        # L0 fast 仍只判本次 staged 内容。
        code_health_command = [
            "python3", "-B", "quwoquan_ops/gate/verify_incremental_code_health.py",
            "--base", "auto", "--head", "HEAD", "--working-tree", "--mode", "full",
        ]
        for path in source_paths:
            code_health_command.extend(["--changed-file", path])
        checks.append(_check("static:code-health-delta", "spec_contract", "static", code_health_command, resources=["code-health"]))
    pytest_paths = list(commit["pytest_paths"])
    pytest_deferred = [
        path
        for path in commit["deferred_to_ci"]
        if path.endswith(".py") or "tests/local_contract" in path
    ]
    if pytest_deferred and level == "fast":
        # L0 preserves every deferred selector target. L1/L2 do not splice
        # directory suites back into managed-pytest: their canonical scoped
        # build/release profiles own that coverage instead.
        deferred.extend(
            {
                "scope": "data" if path.startswith("quwoquan_data/") else "ops",
                "work": path,
            }
            for path in pytest_deferred
        )
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

    checks.extend(_data_semantic_portal_checks(normalized))

    if level != "fast" and "service" in scopes and not go_services:
        checks.append(_check("scope_build:service-compile", "service", "scope_build", ["go", "test", "./...", "-run", "^$", "-count=1", "-p=4"], cwd="quwoquan_service", resources=["go:service-all"]))
        checks.append(_check("scope_build:service-build", "service", "scope_build", ["go", "build", "./..."], cwd="quwoquan_service", resources=["go:service-all"]))
    if "app" in scopes:
        # App 可编译是每一级 readiness（含 integrate 默认的 fast）的基础事实：
        # Debug-nonprod 构建期自供给（environment-topology-and-packaging REQ-003
        # build_time_self_supply）让裸 SDK 构建也能过 trust gate，因此这里直接以
        # canonical 入口编译，不再依赖 handoff 或 facade。iOS simulator 只能在 darwin
        # 主机执行；Android 必须带 nonprod flavor（工程声明了 buildProfile flavor 维度）。
        # readiness capsule 只物化 tracked 文件，没有 .dart_tool/package_config.json，所以不能 --no-pub：
        # 由 flutter 按 tracked pubspec.lock 从本地 pub cache 解析（无网且无缓存时 typed 失败）。
        if sys.platform == "darwin":
            checks.append(_check(
                "scope_build:app-compile-ios-simulator", "app", "scope_build",
                ["flutter", "build", "ios", "--simulator", "--debug", "--flavor", "nonprod", "--no-codesign"],
                cwd="quwoquan_app", resources=["flutter-build"],
            ))
        checks.append(_check(
            "scope_build:app-package-smoke", "app", "scope_build",
            ["flutter", "build", "apk", "--debug", "--flavor", "nonprod", "--android-skip-build-dependency-validation"],
            cwd="quwoquan_app", resources=["flutter-build"],
        ))
    if level != "fast" and "data" in scopes:
        if not any(check["id"] == "static:data_verify" for check in checks):
            checks.append(_check("scope_build:data-verify-all", "data", "scope_build", ["python3", "-B", "quwoquan_data/scripts/cli.py", "verify", "all"], resources=["data-verify"]))
        selector_deferred_data_suite = any(
            path.startswith("quwoquan_data/tests/local_contract")
            for path in pytest_deferred
        )
        if (
            any(path.startswith("quwoquan_data/") for path in normalized)
            and not any(path.startswith("quwoquan_data/tests/local_contract/") for path in pytest_paths)
            and not selector_deferred_data_suite
        ):
            raise ValueError("data scope planner 未能选择 affected tests；拒绝以 verify-only 生成 scope_ready")
        if level == "scope" and selector_deferred_data_suite:
            checks.append(
                _check(
                    "scope_build:data-local-contract",
                    "data",
                    "scope_build",
                    [
                        "env",
                        "GATE_DATA_PHASE=local_contract",
                        "bash",
                        "quwoquan_ops/gate/gate_repo.sh",
                        "--scope",
                        "data",
                    ],
                    resources=["data-tests"],
                )
            )
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
    checks = [
        _canonical_check_timeout(check, level=level, policy=timeout_policy)
        for check in checks
    ]
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
        "timeout_policy": timeout_policy_identity,
        "level": level,
        "paths": normalized,
        "scopes": scopes,
        "lockfiles": lockfiles,
        "checks": unique,
        "deferred": deferred,
    }


def _lane_gate_checks(*, base: str, head: str, paths: list[str]) -> list[dict[str, Any]]:
    """扩充既有 push runner，不新增独立 receipt 或执行流水线。"""
    from quwoquan_ops.gate.delivery_gate_data_shard import sharded_test_files

    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))["lane_gate"]
    if contract["schema_version"] != 1 or contract["required_groups"] != [
        "governance", "impact_boundary", "code_health_full", "ops_local_contract",
    ] or contract["ops_shards"] != 4:
        raise ValueError("Lane Gate required contract drifted")
    checks = [
        _check("lane_gate:" + Path(script).stem, "spec_contract", "static",
               ["python3", "-B", script], resources=["ops-static"])
        for script in contract["governance_scripts"]
    ]
    for scope in contract["python_governance_scopes"]:
        checks.append(_static_check("python_script_governance_" + scope))
    checks.append(_check(
        "lane_gate:feature-tree",
        "spec_contract",
        "static",
        [
            *contract["feature_tree_command"],
            f"CONTENT_REVIEW_ARGS=--base {base} --head {head}",
        ],
        resources=["feature-tree"],
    ))
    boundary = ["python3", "-B", "quwoquan_ops/ci/local_readiness_planner.py",
                "--validate-lane-impact", "--base", base, "--head", head]
    for path in paths:
        boundary.extend(["--changed-file", path])
    checks.append(_check("lane_gate:impact-boundary", "spec_contract", "static", boundary,
                         resources=["impact-plan"]))
    for shard in range(contract["ops_shards"]):
        # 直接复用 hosted selector 与 managed pytest；精确文件列表进入 command fingerprint。
        files = sharded_test_files(ROOT, contract["ops_shards"], shard, "ops", lane_gate=True)
        if not files:
            raise ValueError(f"Lane Gate ops shard {shard} is empty")
        checks.append(_check(f"lane_gate:ops-local-contract:{shard}", "spec_contract", "focused",
            ["python3", "-B", "quwoquan_ops/cli/local_readiness.py", "managed-pytest", *files],
            resources=["python-tests"]))
    return checks


def _bind_lane_gate(plan: dict[str, Any], *, base: str, head: str) -> dict[str, Any]:
    generated = _lane_gate_checks(base=base, head=head, paths=plan["paths"])
    covered = {
        path
        for check in generated
        if check["id"].startswith("lane_gate:ops-local-contract:")
        for path in check["command"][4:]
    }
    required = [
        check
        for check in generated
        if not check["id"].startswith("lane_gate:ops-local-contract:")
    ]
    commands = {tuple(check["command"]) for check in required}
    checks = []
    for check in plan["checks"]:
        # source-admitted push 只左移治理脚本、ImpactPlan 边界与 Code Health。
        # App/Service 全量套件、iOS/APK 编译以及 ops 四片（含 Gamma/prod 合同）
        # 留给 live Alpha / L2，不挡 origin/dev1.0 写入。
        if (
            check["id"] == "focused:dart"
            or check["id"].startswith("focused:go:")
            or check["id"].startswith("scope_build:")
        ):
            continue
        if tuple(check["command"]) in commands or check["id"] == "static:branch_policy":
            continue
        if check["id"] == "focused:python":
            # source-admitted 不跑 ops 四片；这里同步剔除，避免 focused:python 把全集补回来。
            prefix, files = check["command"][:4], check["command"][4:]
            files = [path for path in files if path not in covered]
            if not files:
                continue
            check = {**check, "command": [*prefix, *files]}
        checks.append(check)
    policy, _ = load_timeout_policy()
    checks.extend(_canonical_check_timeout(check, level=plan["level"], policy=policy) for check in required)
    deferred = [item for item in plan["deferred"]
                if not item["work"].startswith("quwoquan_ops/tests/local_contract")]
    return {**plan, "checks": checks, "deferred": deferred}


def validate_lane_impact(*, base: str, head: str, paths: list[str]) -> None:
    """同 hosted 的 exact ImpactPlan build/validate/changed boundary，不执行其他检查。"""
    from quwoquan_ops.ci.detect_ci_impacted_scopes import git_changed_files
    from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan, validate_delivery_impact_plan
    from quwoquan_ops.ci.verify_ci_changed_boundary import verify
    import subprocess

    actual = normalize_changed_paths(git_changed_files(base, head))
    if actual != normalize_changed_paths(paths):
        raise ValueError("Lane Gate changed paths differ from exact candidate range")
    tree = subprocess.run(["git", "rev-parse", f"{head}^{{tree}}"], cwd=ROOT,
                          check=True, text=True, capture_output=True).stdout.strip()
    plan = build_delivery_impact_plan(actual, source_sha=head, base_sha=base, head_sha=head,
        synthetic_sha=head, source_tree_digest=f"sha1:{tree}", execution_profile="manual",
        force_device=False, fail_closed_empty=True, required_scopes=[])
    validate_delivery_impact_plan(plan, expected_source_sha=head, expected_tree_digest=f"sha1:{tree}")
    path = ROOT / ".qwq_output/env/repo/runs/lane-impact" / plan["plan_digest"].removeprefix("sha256:") / "impact-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    verify(path, expected_source_sha=head, expected_tree_digest=f"sha1:{tree}", expected_plan_digest=plan["plan_digest"])
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True))


def bind_source_health_plan(
    plan: dict[str, Any], *, mode: str, base: str, head: str,
) -> dict[str, Any]:
    """把健康检查绑定实际源码身份；push 等级不降低 full 准出判据。"""
    source_paths = [path for path in plan["paths"] if path.startswith(
        ("quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/")
    )]
    if mode not in {"push", "staged"} or (mode == "staged" and not source_paths):
        return plan
    checks = [check for check in plan["checks"] if "code-health" not in check["resources"]]
    health_mode = "full" if mode == "push" else "fast"
    command = ["python3", "-B", "quwoquan_ops/gate/verify_incremental_code_health.py",
               "--base", base, "--head", head, "--mode", health_mode]
    if mode == "staged":
        command.extend(["--working-tree", "--index-only"])
    for path in plan["paths"]:
        command.extend(["--changed-file", path])
    health = _check("static:code-health-delta", "spec_contract", "static", command, resources=["code-health"])
    policy, _ = load_timeout_policy()
    checks.insert(0, _canonical_check_timeout(health, level=plan["level"], policy=policy))
    bound = {**plan, "checks": checks}
    return _bind_lane_gate(bound, base=base, head=head) if mode == "push" else bound


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("fast", "scope", "release"))
    parser.add_argument("--validate-lane-impact", action="store_true")
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--flutter-cap", type=int, default=40)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.validate_lane_impact:
            validate_lane_impact(base=args.base, head=args.head, paths=args.changed_file)
            return 0
        plan = build_impact_plan(args.changed_file, level=args.level, flutter_cap=args.flutter_cap)
    except (ImpactPlannerError, ValueError) as exc:
        print(f"local-readiness-planner: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    json.dump(plan, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
