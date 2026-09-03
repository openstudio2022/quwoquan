#!/usr/bin/env python3
"""Select L0 commit-gate static checks and impacted tests from changed paths."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TEST_ROOT = ROOT / "quwoquan_app" / "test" / "local_contract"

DEFAULT_FLUTTER_CAP = 40
MIN_FLUTTER_CAP = 24

# L0 pytest selection uses a versioned, configured estimate. These values are
# deliberately conservative planning inputs, not observed p95 measurements.
PYTEST_ESTIMATE_SCHEMA = "commit-gate-pytest-estimate-v1"
PYTEST_BUDGET_SECONDS = 120
PYTEST_CAP = 80  # Defensive last resort; duration is the primary admission rule.
DEFAULT_PYTEST_FILE_ESTIMATE_SECONDS = 12
PYTEST_FILE_ESTIMATE_SECONDS_BY_PREFIX = (
    ("quwoquan_ops/tests/local_contract/ci/", 18),
    ("quwoquan_ops/tests/local_contract/gate/", 18),
    ("quwoquan_ops/tests/local_contract/environment/", 18),
    ("quwoquan_ops/tests/local_contract/release/", 18),
    ("quwoquan_ops/tests/local_contract/stackctl/", 18),
    ("quwoquan_data/tests/local_contract/", 15),
)

DATA_LOCAL_CONTRACT_ROOT = "quwoquan_data/tests/local_contract"

# 这四处实现面被 data local_contract 的每个子目录引用，影响面就是全域。给它们
# 编一份「相关目录」清单只会假装收敛：清单外的目录同样会因这里的改动而红。
DATA_CROSSCUTTING_PREFIXES = (
    "quwoquan_data/scripts/verify/",
    "quwoquan_data/scripts/cli.py",
    "quwoquan_data/scripts/content/review/",
    "quwoquan_data/scripts/content/templates/",
)

SMOKE_STATIC = [
    "verify-app-mock-isolation",
    "verify-app-cloud-package-boundaries",
    "verify-app-login-entry-loop",
    # Both weak-typing ratchets run in ~5s combined. They used to be reachable
    # only through `make gate`, which no local commit and no CI job invokes, so
    # both baselines drifted unnoticed.
    "verify-app-enum-typed-binding",
    "verify-app-assistant-search-weak-typing-ratchet",
]

# 就绪路由与 readinessProbe 分处两棵树，任一侧单独改动都能造成探针错配，
# 因此两侧任一被触及都必须跑同源门禁（纯静态，亚秒级）。
SERVICE_PROBE_SUFFIXES = (
    "deploy/base/deployment.yaml",
    "quwoquan_ops/cli/lib/service_runtime_probes.py",
    ".go",
)

# UAT key 与实现侧 key 分处两棵树，任一侧单独改动都能造成 UAT 引用不存在的
# widget（find.byKey 永远 findsNothing），因此两侧任一被触及都跑同源门禁。
UAT_WIDGET_KEY_PREFIXES = (
    "quwoquan_app/lib/",
    "quwoquan_app/test/user_acceptance/",
    "quwoquan_app/test/support/runtime/patrol/",
)

PAGEFLIP_PREFIXES = (
    "quwoquan_app/lib/design_system/pageflip/",
    "quwoquan_app/lib/service/content_service/content/post/presentation/article_reader/pageflip/",
    "quwoquan_app/test/local_contract/design_system/pageflip/",
    "quwoquan_app/test/local_contract/service/content_service/content/post/works_image_book_pageflip_journey__local_contract_test.dart",
)

# 运行矩阵是按需/准出治理说明，不进入普通 commit 的 staged impact hard gate。
# 它仍由显式 verify-agent-context-budget 和聚焦 local_contract 校验。
NON_COMMIT_GATE_DOCUMENTS = frozenset(
    {
        "specs/feature-tree/runtime/development-workflow-governance/design.md",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Explicit changed path relative to repo root. Repeatable.",
    )
    parser.add_argument(
        "--use-staged",
        action="store_true",
        help="Read paths from git diff --cached --name-only.",
    )
    parser.add_argument(
        "--flutter-cap",
        type=int,
        default=0,
        help="Max Flutter test files (0 = auto from CPU).",
    )
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    return parser.parse_args()


def staged_files() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def cpu_count() -> int:
    try:
        return max(1, os.cpu_count() or 1)
    except Exception:
        return 1


def flutter_cap(explicit: int) -> int:
    if explicit > 0:
        return explicit
    cores = cpu_count()
    if cores < 6:
        return MIN_FLUTTER_CAP
    return DEFAULT_FLUTTER_CAP


def classify(paths: list[str]) -> dict[str, bool]:
    flags = {
        "has_service": False,
        "has_app": False,
        "has_data": False,
        "has_ops": False,
        "has_specs": False,
        "has_portal": False,
        "has_contracts": False,
        "has_app_contracts": False,
        "has_app_dart": False,
        "has_pageflip": False,
        "has_app_scripts": False,
        "has_service_scripts": False,
        "has_ops_scripts": False,
        "has_data_scripts": False,
        "has_service_probes": False,
        "has_app_uat_widget_keys": False,
    }
    for path in paths:
        if path in NON_COMMIT_GATE_DOCUMENTS:
            continue
        if path.startswith("quwoquan_service/"):
            flags["has_service"] = True
            if "/contracts/" in path or path.startswith(
                "quwoquan_service/contracts/"
            ):
                flags["has_contracts"] = True
            if "/tests/" not in path and path.endswith((".py", ".sh")):
                flags["has_service_scripts"] = True
        if path.startswith("quwoquan_app/"):
            flags["has_app"] = True
            if path.endswith(".dart"):
                flags["has_app_dart"] = True
            if "contracts" in path or path.startswith(
                "quwoquan_app/packages/quwoquan_cloud_contracts/"
            ):
                flags["has_app_contracts"] = True
            if "/tests/" not in path and "/test/" not in path and path.endswith((".py", ".sh")):
                flags["has_app_scripts"] = True
        if path.startswith("quwoquan_data/"):
            flags["has_data"] = True
            if "/tests/" not in path and path.endswith((".py", ".sh")):
                flags["has_data_scripts"] = True
        if path.startswith("quwoquan_ops/") or path.startswith("specs/"):
            flags["has_ops"] = True
        if (
            path.startswith("quwoquan_ops/")
            and "/tests/" not in path
            and path.endswith((".py", ".sh"))
        ):
            flags["has_ops_scripts"] = True
        if path.startswith("specs/"):
            flags["has_specs"] = True
        if path.startswith("quwoquan_ops/portal/"):
            flags["has_portal"] = True
        if any(path.startswith(prefix) for prefix in PAGEFLIP_PREFIXES):
            flags["has_pageflip"] = True
        if any(path.endswith(suffix) for suffix in SERVICE_PROBE_SUFFIXES):
            flags["has_service_probes"] = True
        if path.endswith(".dart") and any(
            path.startswith(prefix) for prefix in UAT_WIDGET_KEY_PREFIXES
        ):
            flags["has_app_uat_widget_keys"] = True
    return flags


def static_checks(flags: dict[str, bool]) -> list[str]:
    checks = ["branch_policy", "entrypoint_script_paths"]
    if flags["has_specs"]:
        checks.append("feature_tree")
    for scope in ("app", "service", "ops", "data"):
        if flags[f"has_{scope}_scripts"]:
            checks.append(f"python_script_governance_{scope}")
    if flags["has_service"] or flags["has_ops"]:
        checks.append("service_architecture")
    if flags["has_service_probes"]:
        checks.append("service_probe_homology")
    if flags["has_app_contracts"] or flags["has_contracts"]:
        checks.append("app_generated_manifest")
    if flags["has_app"] or flags["has_app_contracts"]:
        checks.append("app_contract_handoff")
    if flags["has_app_dart"]:
        checks.extend(SMOKE_STATIC)
    if flags["has_contracts"]:
        checks.extend(["metadata_contract", "commercial_contract"])
    if flags["has_app_uat_widget_keys"]:
        checks.append("app_uat_widget_key_references")
    if flags["has_pageflip"]:
        checks.append("pageflip_backward_mainline")
    if flags["has_data"]:
        checks.append("data_verify")
    # de-dupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in checks:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def map_app_path_to_tests(path: str) -> list[Path]:
    if not path.startswith("quwoquan_app/"):
        return []
    rel = path.removeprefix("quwoquan_app/")
    candidates: list[Path] = []
    if rel.startswith("test/local_contract/") and rel.endswith("_test.dart"):
        candidate = ROOT / "quwoquan_app" / rel
        if candidate.is_file():
            return [candidate]
    if rel.startswith("lib/"):
        # lib/service/chat_service/chat/conversation/foo.dart -> test/local_contract/service/chat_service/chat/conversation/**
        without_lib = rel.removeprefix("lib/")
        parts = Path(without_lib).parts
        if parts:
            # Try progressively shorter directory prefixes under local_contract.
            for depth in range(min(len(parts), 4), 0, -1):
                probe = APP_TEST_ROOT.joinpath(*parts[:depth])
                if probe.is_dir():
                    candidates.extend(sorted(probe.rglob("*_test.dart")))
                    break
                if probe.with_name(probe.name + "__local_contract_test.dart").is_file():
                    candidates.append(
                        probe.with_name(probe.name + "__local_contract_test.dart")
                    )
                    break
    return candidates


def select_flutter_tests(paths: list[str], cap: int) -> tuple[list[str], list[str]]:
    selected: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        for test_path in map_app_path_to_tests(path):
            if test_path not in seen:
                seen.add(test_path)
                selected.append(test_path)
    # Prefer tests whose path shares more segments with changed files.
    def score(test_path: Path) -> tuple[int, str]:
        rel = str(test_path.relative_to(ROOT))
        best = 0
        for changed in paths:
            shared = 0
            for a, b in zip(rel.split("/"), changed.split("/"), strict=False):
                if a == b:
                    shared += 1
                else:
                    break
            best = max(best, shared)
        return (-best, rel)

    selected.sort(key=score)
    kept = selected[:cap]
    deferred = selected[cap:]
    return (
        [str(p.relative_to(ROOT / "quwoquan_app")) for p in kept],
        [str(p.relative_to(ROOT)) for p in deferred],
    )


def select_go_services(paths: list[str]) -> list[str]:
    services: list[str] = []
    seen: set[str] = set()
    for path in paths:
        prefix = "quwoquan_service/services/"
        if not path.startswith(prefix):
            continue
        rest = path.removeprefix(prefix)
        svc = rest.split("/", 1)[0]
        if not svc or svc in seen:
            continue
        if (ROOT / "quwoquan_service" / "services" / svc).is_dir():
            seen.add(svc)
            services.append(svc)
    return services


def _select_pytest_targets(paths: list[str]) -> dict[str, object]:
    """Build the versioned L0 pytest admission decision.

    Directory suites are always deferred to canonical scoped/Delivery checks.
    File targets are admitted by a conservative configured duration estimate;
    the estimate is explanatory planning data and is not an observed p95.
    """
    selected: list[str] = []
    seen: set[str] = set()
    deferred: list[str] = []
    # worktree 生命周期治理的实现散在 hooks、cli/lib 与 policies 三处，决策表却只有一份。
    # 不显式映射的话，改 hook 或改阈值都不会触发它——最需要回归的两类改动恰好都漏掉。
    worktree_lifecycle_tests = (
        "quwoquan_ops/tests/local_contract/gate/"
        "test_local_worktree_lifecycle__gate__local_contract_test.py",
    )
    source_mappings = (
        ("quwoquan_ops/hooks/worktree_", worktree_lifecycle_tests),
        ("quwoquan_ops/hooks/post-commit", worktree_lifecycle_tests),
        ("quwoquan_ops/hooks/run_install_hooks.sh", worktree_lifecycle_tests),
        ("quwoquan_ops/cli/lib/local_worktree_inventory.py", worktree_lifecycle_tests),
        ("quwoquan_ops/cli/lane_worktree_commands.py", worktree_lifecycle_tests),
        ("quwoquan_ops/policies/worktree_policy.yaml", worktree_lifecycle_tests),
        ("quwoquan_ops/policies/lane_ownership.yaml", worktree_lifecycle_tests),
        (
            "quwoquan_ops/gate/lib/process_group_deadline.py",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_commit_gate_fast_path__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/gate/"
                "test_process_group_deadline__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/gate/commit_gate",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_commit_gate_fast_path__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/gate/"
                "test_commit_gate_select__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/gate/"
                "test_process_group_deadline__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/ci/local_readiness_planner.py",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_local_readiness__core__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/local_readiness.py",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_local_readiness__core__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/lib/local_readiness/",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_local_readiness__core__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/hooks/local_readiness_after_edit.py",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_local_readiness__core__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/policies/local_readiness_contract.yaml",
            (
                "quwoquan_ops/tests/local_contract/ci/"
                "test_local_readiness__core__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/gate/verify_github_supply_chain.py",
            (
                "quwoquan_ops/tests/local_contract/release/"
                "test_service_supply_chain_provenance__supply_chain__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/ci/provider_conformance/provider_patrol_lib/",
            (
                "quwoquan_ops/tests/local_contract/provider/"
                "test_provider_patrol_runtime_identity__contract__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/commands/dev_session",
            (
                "quwoquan_ops/tests/local_contract/stackctl/"
                "test_stackctl_dev_session_mutable_startup_gate__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/stackctl/"
                "test_stackctl_dev_session_resume_compose__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/stackctl/"
                "test_stackctl_dev_session_runtime_reuse__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/commands/down_shared.py",
            (
                "quwoquan_ops/tests/local_contract/stackctl/"
                "test_stackctl_mutable_test_live_teardown__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/lib/test_live_startup_attempt_receipt.py",
            (
                "quwoquan_ops/tests/local_contract/test_data/"
                "test_live_startup_attempt_receipt__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/test_data/"
                "test_test_live_content_binding__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/lib/web_official_release.py",
            (
                "quwoquan_ops/tests/local_contract/release/"
                "test_web_official_release__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/cli/stackctl.py",
            (
                "quwoquan_ops/tests/local_contract/stackctl/"
                "test_stackctl_test_live_content_binding_wiring__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/release/"
                "test_web_official_release__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
            (
                "quwoquan_ops/tests/local_contract/environment/"
                "test_environment_package_entrypoints__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/environment/"
                "test_local_gamma_service_runtime_bindings__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/environment/"
                "test_runtime_topology_package__security__local_contract_test.py",
            ),
        ),
        (
            "quwoquan_ops/environments/gamma/local/Caddyfile",
            (
                "quwoquan_ops/tests/local_contract/environment/"
                "test_local_media_origin_cache_policy__local_contract_test.py",
                "quwoquan_ops/tests/local_contract/gate/"
                "test_api_edge_single_track__local_contract_test.py",
            ),
        ),
        ("quwoquan_ops/gate/", ("quwoquan_ops/tests/local_contract/gate",)),
        (
            "quwoquan_ops/policies/gates/",
            ("quwoquan_ops/tests/local_contract/gate",),
        ),
        ("quwoquan_ops/ci/", ("quwoquan_ops/tests/local_contract/ci",)),
        (
            "quwoquan_ops/environments/",
            ("quwoquan_ops/tests/local_contract/environment",),
        ),
        ("quwoquan_ops/cli/", ("quwoquan_ops/tests/local_contract/stackctl",)),
        ("quwoquan_data/scripts/core/", ("quwoquan_data/tests/local_contract/core",)),
        (
            "quwoquan_data/scripts/content/execution/",
            ("quwoquan_data/tests/local_contract/execution",),
        ),
        (
            "quwoquan_data/scripts/content/release/",
            ("quwoquan_data/tests/local_contract/release",),
        ),
        (
            "quwoquan_data/scripts/content/source/",
            ("quwoquan_data/tests/local_contract/source",),
        ),
        (
            "quwoquan_data/scripts/governance/",
            ("quwoquan_data/tests/local_contract/governance",),
        ),
        (
            "quwoquan_data/scripts/content/filter_catalog/",
            ("quwoquan_data/tests/local_contract/filter_catalog",),
        ),
    )
    for path in sorted(dict.fromkeys(paths)):
        for root in (
            "quwoquan_data/tests/local_contract",
            "quwoquan_ops/tests/local_contract",
        ):
            if path.startswith(root + "/") and path.endswith(".py"):
                # A staged deletion still shows up as a changed path; handing it to
                # pytest aborts the whole run with "file or directory not found".
                if path not in seen and (ROOT / path).exists():
                    seen.add(path)
                    selected.append(path)
        if "/tests/" in path:
            continue
        if any(path.startswith(prefix) for prefix in DATA_CROSSCUTTING_PREFIXES):
            if DATA_LOCAL_CONTRACT_ROOT not in deferred:
                deferred.append(DATA_LOCAL_CONTRACT_ROOT)
        for source_prefix, test_targets in source_mappings:
            if path.startswith(source_prefix):
                for test_target in test_targets:
                    target_path = ROOT / test_target
                    if test_target in seen or not target_path.exists():
                        continue
                    # Exact file mappings stay L0 candidates. Broad directory
                    # mappings are explicit deferred work before budgeting.
                    if target_path.is_dir():
                        if test_target not in deferred:
                            deferred.append(test_target)
                    else:
                        seen.add(test_target)
                        selected.append(test_target)
                break
    def file_estimate_seconds(target: str) -> int:
        for prefix, seconds in PYTEST_FILE_ESTIMATE_SECONDS_BY_PREFIX:
            if target.startswith(prefix):
                return seconds
        return DEFAULT_PYTEST_FILE_ESTIMATE_SECONDS

    def target_estimate(target: str) -> tuple[int, int]:
        target_path = ROOT / target
        if target_path.is_dir():
            files = sorted(target_path.rglob("test_*.py"))
            return (
                sum(file_estimate_seconds(item.relative_to(ROOT).as_posix()) for item in files),
                len(files),
            )
        return file_estimate_seconds(target), 1

    candidate_targets = selected
    selected = []
    deferred_seen = set(deferred)
    estimated_seconds = 0
    admitted_files = 0
    estimates: list[dict[str, object]] = []

    # A directory and its child must never be passed together to pytest. Broad
    # mappings have already become deferred work, so local paths are exact files
    # and parent/child overlap is impossible by construction.
    for target in candidate_targets:
        estimate, file_count = target_estimate(target)
        target_path = ROOT / target
        reason = "within_estimated_duration_budget"
        decision = "selected"
        if target_path.is_dir():
            decision = "deferred_to_ci"
            reason = "directory_suite"
        elif admitted_files >= PYTEST_CAP:
            decision = "deferred_to_ci"
            reason = "defensive_file_cap"
        elif estimated_seconds + estimate > PYTEST_BUDGET_SECONDS:
            decision = "deferred_to_ci"
            reason = "estimated_duration_budget"
        else:
            selected.append(target)
            admitted_files += 1
            estimated_seconds += estimate
        if decision == "deferred_to_ci" and target not in deferred_seen:
            deferred.append(target)
            deferred_seen.add(target)
        estimates.append(
            {
                "target": target,
                "estimated_seconds": estimate,
                "estimated_file_count": file_count,
                "decision": decision,
                "reason": reason,
            }
        )

    # Cross-cutting suites can be deferred without first becoming candidates.
    for target in deferred:
        if any(item["target"] == target for item in estimates):
            continue
        estimate, file_count = target_estimate(target)
        estimates.append(
            {
                "target": target,
                "estimated_seconds": estimate,
                "estimated_file_count": file_count,
                "decision": "deferred_to_ci",
                "reason": "crosscutting_directory_suite" if (ROOT / target).is_dir() else "crosscutting_target",
            }
        )

    return {
        "pytest_paths": selected,
        "deferred_to_ci": deferred,
        "estimated_pytest_seconds": estimated_seconds,
        "pytest_budget_seconds": PYTEST_BUDGET_SECONDS,
        "pytest_estimate_schema": PYTEST_ESTIMATE_SCHEMA,
        "pytest_estimate_basis": "configured_conservative_estimate_not_observed_p95",
        "pytest_target_estimates": estimates,
    }


def select_pytest_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Compatibility projection returning executable files and deferred work."""

    selection = _select_pytest_targets(paths)
    return (
        list(selection["pytest_paths"]),
        list(selection["deferred_to_ci"]),
    )


def build_plan(paths: list[str], cap: int) -> dict:
    flags = classify(paths)
    flutter_tests, deferred = select_flutter_tests(paths, cap)
    pytest_selection = _select_pytest_targets(paths)
    pytest_paths = list(pytest_selection["pytest_paths"])
    pytest_deferred = list(pytest_selection["deferred_to_ci"])
    combined_deferred = list(dict.fromkeys([*deferred, *pytest_deferred]))
    return {
        "changed_files": paths,
        "flags": flags,
        "static_checks": static_checks(flags),
        "flutter_tests": flutter_tests,
        "deferred_to_ci": combined_deferred,
        "flutter_cap": cap,
        "estimated_pytest_seconds": pytest_selection["estimated_pytest_seconds"],
        "pytest_budget_seconds": pytest_selection["pytest_budget_seconds"],
        "pytest_estimate_schema": pytest_selection["pytest_estimate_schema"],
        "pytest_estimate_basis": pytest_selection["pytest_estimate_basis"],
        "pytest_target_estimates": pytest_selection["pytest_target_estimates"],
        "go_services": select_go_services(paths),
        "pytest_paths": pytest_paths,
        "run_portal": flags["has_portal"] and not (
            flags["has_app"] or flags["has_service"] or flags["has_data"]
        ),
        "forbidden": ["make gate", "gate_repo --scope all", "full local_contract"],
    }


def main() -> int:
    args = parse_args()
    paths = list(args.changed_file)
    if args.use_staged or not paths:
        paths = staged_files() if args.use_staged or not paths else paths
    if not paths and args.use_staged:
        paths = staged_files()
    cap = flutter_cap(args.flutter_cap)
    plan = build_plan(paths, cap)
    if args.format == "json":
        json.dump(plan, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"FLUTTER_CAP={plan['flutter_cap']}")
        print(f"HAS_APP={str(plan['flags']['has_app']).lower()}")
        print(f"HAS_SERVICE={str(plan['flags']['has_service']).lower()}")
        print(f"HAS_DATA={str(plan['flags']['has_data']).lower()}")
        print(f"HAS_PAGEFLIP={str(plan['flags']['has_pageflip']).lower()}")
        print(f"FLUTTER_COUNT={len(plan['flutter_tests'])}")
        print(f"DEFERRED_COUNT={len(plan['deferred_to_ci'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
