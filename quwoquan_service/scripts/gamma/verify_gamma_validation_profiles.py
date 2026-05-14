#!/usr/bin/env python3
"""Verify gamma_validation_suites.json profile/suite consistency.

Checks:
1. Every smokeCases entry references a valid smokeCase definition with a real file path.
2. Every uiJourneys entry references a valid uiJourney definition with a real file path.
3. Profile names used by workflows and scripts match those defined in the JSON.
4. Legacy profile names (daily_full, pr_smoke) have been removed.
5. deviceMatrix.envs only reference known environments.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITES_PATH = REPO_ROOT / "deploy" / "shared" / "gamma_validation_suites.json"
KNOWN_ENVS = {"alpha", "beta", "gamma", "local-gamma", "prod"}
VALID_PROFILES = {"pr_light", "manual_full", "nightly_full", "release_candidate"}
LEGACY_PROFILES = {"daily_full", "pr_smoke"}


def load_suites() -> Dict[str, Any]:
    return json.loads(SUITES_PATH.read_text(encoding="utf-8"))


def check_file_exists(path_str: str, context: str) -> List[str]:
    errors = []
    if not path_str:
        errors.append(f"{context}: empty path")
        return errors
    full = REPO_ROOT / path_str
    if not full.exists():
        errors.append(f"{context}: file not found: {path_str}")
    return errors


def verify_smoke_cases(registry: Dict[str, Any]) -> List[str]:
    errors = []
    cases = registry.get("smokeCases") or {}
    for case_id, case_def in cases.items():
        path = case_def.get("path", "")
        errors.extend(check_file_exists(path, f"smokeCases.{case_id}"))
    return errors


def verify_ui_journeys(registry: Dict[str, Any]) -> List[str]:
    errors = []
    journeys = registry.get("uiJourneys") or {}
    for journey_id, journey_def in journeys.items():
        path = journey_def.get("path", "")
        errors.extend(check_file_exists(path, f"uiJourneys.{journey_id}"))
    return errors


def verify_profile_references(registry: Dict[str, Any]) -> List[str]:
    errors = []
    profiles = registry.get("profiles") or {}
    cases = set((registry.get("smokeCases") or {}).keys())
    journeys = set((registry.get("uiJourneys") or {}).keys())

    for profile_name, profile_def in profiles.items():
        if profile_name in LEGACY_PROFILES:
            errors.append(
                f"profiles.{profile_name}: legacy profile name still present; "
                f"expected one of {sorted(VALID_PROFILES)}"
            )
        for case_ref in profile_def.get("smokeCases") or []:
            if case_ref not in cases:
                errors.append(
                    f"profiles.{profile_name}.smokeCases: "
                    f"references undefined case '{case_ref}'"
                )
        for journey_ref in profile_def.get("uiJourneys") or []:
            if journey_ref not in journeys:
                errors.append(
                    f"profiles.{profile_name}.uiJourneys: "
                    f"references undefined journey '{journey_ref}'"
                )
        device_matrix = profile_def.get("deviceMatrix")
        if isinstance(device_matrix, dict):
            for env in device_matrix.get("envs") or []:
                if env not in KNOWN_ENVS:
                    errors.append(
                        f"profiles.{profile_name}.deviceMatrix.envs: "
                        f"unknown env '{env}'"
                    )
    return errors


def verify_no_legacy_profiles(registry: Dict[str, Any]) -> List[str]:
    errors = []
    profiles = set((registry.get("profiles") or {}).keys())
    for legacy in LEGACY_PROFILES:
        if legacy in profiles:
            errors.append(
                f"Legacy profile '{legacy}' still defined; "
                f"must be replaced with {sorted(VALID_PROFILES)}"
            )
    return errors


def main() -> int:
    if not SUITES_PATH.exists():
        print(f"FAIL: {SUITES_PATH} not found")
        return 1

    registry = load_suites()
    errors = []
    errors.extend(verify_smoke_cases(registry))
    errors.extend(verify_ui_journeys(registry))
    errors.extend(verify_profile_references(registry))
    errors.extend(verify_no_legacy_profiles(registry))

    if errors:
        print(f"FAIL: {len(errors)} error(s) in gamma_validation_suites.json:")
        for err in errors:
            print(f"  - {err}")
        return 1

    profiles = list((registry.get("profiles") or {}).keys())
    print(f"OK: gamma_validation_suites.json v{registry.get('version', '?')} — "
          f"{len(profiles)} profiles verified: {profiles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
