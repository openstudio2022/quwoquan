#!/usr/bin/env python3
"""Fail closed unless every App environment uses one production Remote path."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
DEVICE_SCRIPTS = APP / "scripts" / "device"
if str(DEVICE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEVICE_SCRIPTS))

from launch_manifest_metadata import (  # noqa: E402
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
        APP / "scripts/device/start_app_instance.sh",
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
        APP / "test/support/patrol",
    )
    for root in uat_roots:
        for path in sorted(root.rglob("*.dart")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN_UAT_COMPOSITION_TOKENS:
                if token in text:
                    issues.append(
                        f"{path.relative_to(ROOT)}: "
                        f"UAT support contains forbidden injection token `{token}`"
                    )

    patrol_support = APP / "lib/core/testing/patrol_test_support.dart"
    patrol_source = patrol_support.read_text(encoding="utf-8")
    canonical_signature = (
        "Future<void> launchPatrolAppOnce(PatrolIntegrationTester $) async"
    )
    if canonical_signature not in patrol_source:
        issues.append(
            f"{patrol_support.relative_to(ROOT)}: "
            "launchPatrolAppOnce must not expose a Provider override parameter"
        )
    if "List<Override>" in patrol_source or "...providerScopeOverrides" in patrol_source:
        issues.append(
            f"{patrol_support.relative_to(ROOT)}: "
            "generic business Provider override injection returned"
        )

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
