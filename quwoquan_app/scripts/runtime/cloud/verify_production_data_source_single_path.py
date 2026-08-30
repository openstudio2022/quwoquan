#!/usr/bin/env python3
"""Fail closed unless every App environment uses one production Remote path."""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

from pathlib import Path
import re
import sys


ROOT = REPO_ROOT
APP = ROOT / "quwoquan_app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (  # noqa: E402
    LaunchManifestContractError,
    load_launch_manifest_contract,
)
RETIRED_AGGREGATE_MOCK_PACKAGE = APP / "packages/quwoquan_cloud_mock"
FORBIDDEN_SYMBOLS = (
    "AppDataSourceMode",
    "appDataSourceModeProvider",
    "mockDataSourceActiveProvider",
    "cloudRepositoryImplForMode",
)
FORBIDDEN_RUNTIME_TOKENS = (
    "runners/alpha",
    "quwoquan_cloud_mock",
    "CONTRACT_FIXTURE_PROFILE",
    "app_alpha_seed_manifest",
    "app_beta_seed_manifest",
    "app_gamma_seed_manifest",
)
FORBIDDEN_UAT_COMPOSITION_TOKENS = (
    "quwoquan_cloud_mock",
    "buildAlphaCloudOverrides",
    "repository_mock_reexports",
    "providerScopeOverrides",
)
PATROL_SUPPORT = APP / "test/support/runtime/patrol/patrol_test_support.dart"
MANAGED_PATROL_AUTH_OVERRIDE_RE = re.compile(
    r"providerScopeOverrides\s*:\s*\[\s*"
    r"authSessionControllerProvider\.overrideWith\(\s*"
    r"_PatrolAuthSessionController\.new\s*,?\s*"
    r"\)\s*,?\s*"
    r"\]",
)
EMPTY_PATROL_OVERRIDE_RE = re.compile(
    r"providerScopeOverrides\s*:\s*const\s*\[\s*\]",
)


def patrol_provider_scope_override_issues(source: str) -> list[str]:
    """只接受 Patrol runner 的认证控制器装配，不开放业务 Provider 注入。"""
    token_count = source.count("providerScopeOverrides")
    managed_matches = MANAGED_PATROL_AUTH_OVERRIDE_RE.findall(source)
    empty_matches = EMPTY_PATROL_OVERRIDE_RE.findall(source)
    if token_count != 2 or len(managed_matches) != 1 or len(empty_matches) != 1:
        return [
            "Patrol support must contain exactly one managed "
            "authSessionController override and one explicit empty override list; "
            "generic business Provider override injection is forbidden"
        ]
    return []


def main() -> int:
    issues: list[str] = []
    if RETIRED_AGGREGATE_MOCK_PACKAGE.exists():
        issues.append(
            "quwoquan_app/packages/quwoquan_cloud_mock: "
            "retired aggregate Mock package returned"
        )

    pubspec = (APP / "pubspec.yaml").read_text(encoding="utf-8")
    if "quwoquan_cloud_mock" in pubspec:
        issues.append("quwoquan_app/pubspec.yaml: aggregate Mock dependency returned")

    for path in sorted((APP / "lib").rglob("*.dart")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for symbol in FORBIDDEN_SYMBOLS:
            if symbol in text:
                issues.append(
                    f"{path.relative_to(ROOT)}: forbidden runtime selector `{symbol}`"
                )

    runtime_inputs = [
        APP / "run.sh",
        APP / "scripts/device/build_launcher_handoff.py",
        APP / "scripts/device/run_app_instance.sh",
        APP / "scripts/env/build_app_env_package.sh",
        APP / "scripts/env/print_app_env_dart_defines.py",
        *(APP / "configs").glob("*/app_runtime.yaml"),
    ]
    for path in sorted({item for item in runtime_inputs if item.is_file()}):
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                issues.append(
                    f"{path.relative_to(ROOT)}: runtime input contains `{token}`"
                )
        if path.name == "app_runtime.yaml" and "\nseed:" in text:
            issues.append(
                f"{path.relative_to(ROOT)}: App runtime must not carry seed config"
            )

    runner = APP / "runners" / "alpha"
    if any((runner / "lib").rglob("*.dart")) or (runner / "pubspec.yaml").exists():
        issues.append(
            "quwoquan_app/runners/alpha: retired Alpha runtime composition returned"
        )

    uat_roots = (
        APP / "test/user_acceptance",
        APP / "test/support/runtime/patrol",
    )
    for root in uat_roots:
        for path in sorted(root.rglob("*.dart")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN_UAT_COMPOSITION_TOKENS:
                if token == "providerScopeOverrides" and path == PATROL_SUPPORT:
                    continue
                if token in text:
                    issues.append(
                        f"{path.relative_to(ROOT)}: "
                        f"UAT support contains forbidden injection token `{token}`"
                    )

    patrol_source = PATROL_SUPPORT.read_text(encoding="utf-8")
    canonical_signature = (
        "Future<void> launchPatrolAppOnce(PatrolIntegrationTester $) async"
    )
    if canonical_signature not in patrol_source:
        issues.append(
            f"{PATROL_SUPPORT.relative_to(ROOT)}: "
            "launchPatrolAppOnce must not expose a Provider override parameter"
        )
    if "List<Override>" in patrol_source or "...providerScopeOverrides" in patrol_source:
        issues.append(
            f"{PATROL_SUPPORT.relative_to(ROOT)}: "
            "generic business Provider override injection returned"
        )
    for issue in patrol_provider_scope_override_issues(patrol_source):
        issues.append(f"{PATROL_SUPPORT.relative_to(ROOT)}: {issue}")

    handoff = (APP / "scripts/device/build_launcher_handoff.py").read_text(
        encoding="utf-8"
    )
    try:
        launch_contract = load_launch_manifest_contract()
        entrypoint = launch_contract["schemas"]["app_effective_launch_manifest"][
            "fields"
        ]["entrypoint"]["const"]
    except (KeyError, TypeError, LaunchManifestContractError) as exc:
        issues.append(f"launcher handoff metadata is invalid: {exc}")
        entrypoint = ""
    if entrypoint != "lib/main_prod.dart":
        issues.append(
            "launcher handoff metadata must require lib/main_prod.dart for every environment"
        )
    if 'entrypoint = effective_schema["fields"]["entrypoint"]["const"]' not in handoff:
        issues.append(
            "launcher handoff must derive its entrypoint from canonical metadata"
        )

    if issues:
        print("production_data_source_single_path: FAIL")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("production_data_source_single_path: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
