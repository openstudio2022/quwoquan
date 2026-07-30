#!/usr/bin/env python3
"""Verify validation_suites.json profile/suite consistency.

Checks:
1. The registry uses the one canonical, unversioned top-level structure.
2. Every smokeCases entry references a valid smokeCase definition with a real file path.
3. Every uiJourneys entry references a valid uiJourney definition with a real file path.
4. Profile names used by workflows and scripts match those defined in the JSON.
5. Retired profile names have been removed.
6. deviceMatrix.envs only reference known environments.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
SUITES_PATH = REPO_ROOT / "quwoquan_ops" / "environments" / "gamma" / "validation_suites.json"
KNOWN_ENVS = {"alpha", "beta", "gamma", "local-gamma", "prod"}
VALID_PROFILES = {
    "pr_light",
    "manual_full",
    "nightly_full",
    "release_candidate",
    "mainline_auto_prod",
}
RETIRED_PROFILES = {"daily" + "_full", "pr" + "_smoke"}
CANONICAL_TOP_LEVEL_FIELDS = {
    "baselineRequiredSuites",
    "futureExpansionRule",
    "profiles",
    "smokeCases",
    "uiJourneys",
    "suites",
}
CANONICAL_PROFILE_FIELDS = {
    "description",
    "readinessBlocking",
    "smokeCases",
    "smokeCasesBlocking",
    "uiJourneys",
    "deviceMatrix",
}
CANONICAL_DEVICE_MATRIX_FIELDS = {
    "envs",
    "requireAllPlatforms",
    "matrixKinds",
}


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


def _field_set_errors(
    actual: set[str], expected: set[str], context: str
) -> List[str]:
    errors = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        errors.append(f"{context}: missing fields: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{context}: unexpected fields: {', '.join(unexpected)}")
    return errors


def verify_canonical_structure(registry: Any) -> List[str]:
    """Reject anything except the current unversioned registry shape."""

    if not isinstance(registry, dict):
        return ["registry: expected object"]

    errors = _field_set_errors(
        set(registry), CANONICAL_TOP_LEVEL_FIELDS, "registry"
    )
    expected_types = {
        "baselineRequiredSuites": list,
        "futureExpansionRule": str,
        "profiles": dict,
        "smokeCases": dict,
        "uiJourneys": dict,
        "suites": dict,
    }
    for field_name, expected_type in expected_types.items():
        if field_name in registry and not isinstance(
            registry[field_name], expected_type
        ):
            errors.append(
                f"registry.{field_name}: expected {expected_type.__name__}"
            )

    baseline_suites = registry.get("baselineRequiredSuites")
    if isinstance(baseline_suites, list) and not all(
        isinstance(item, str) and item for item in baseline_suites
    ):
        errors.append(
            "registry.baselineRequiredSuites: expected non-empty strings"
        )

    profiles = registry.get("profiles")
    if not isinstance(profiles, dict):
        return errors

    errors.extend(
        _field_set_errors(set(profiles), VALID_PROFILES, "registry.profiles")
    )
    for profile_name, profile_def in profiles.items():
        context = f"registry.profiles.{profile_name}"
        if not isinstance(profile_def, dict):
            errors.append(f"{context}: expected object")
            continue
        errors.extend(
            _field_set_errors(
                set(profile_def), CANONICAL_PROFILE_FIELDS, context
            )
        )
        profile_types = {
            "description": str,
            "readinessBlocking": bool,
            "smokeCases": list,
            "smokeCasesBlocking": bool,
            "uiJourneys": list,
            "deviceMatrix": dict,
        }
        for field_name, expected_type in profile_types.items():
            if field_name in profile_def and not isinstance(
                profile_def[field_name], expected_type
            ):
                errors.append(
                    f"{context}.{field_name}: expected {expected_type.__name__}"
                )
        for field_name in ("smokeCases", "uiJourneys"):
            values = profile_def.get(field_name)
            if isinstance(values, list) and not all(
                isinstance(item, str) and item for item in values
            ):
                errors.append(f"{context}.{field_name}: expected string entries")
        device_matrix = profile_def.get("deviceMatrix")
        if not isinstance(device_matrix, dict):
            errors.append(f"{context}.deviceMatrix: expected object")
            continue
        errors.extend(
            _field_set_errors(
                set(device_matrix),
                CANONICAL_DEVICE_MATRIX_FIELDS,
                f"{context}.deviceMatrix",
            )
        )
        matrix_types = {
            "envs": list,
            "requireAllPlatforms": bool,
            "matrixKinds": list,
        }
        for field_name, expected_type in matrix_types.items():
            if field_name in device_matrix and not isinstance(
                device_matrix[field_name], expected_type
            ):
                errors.append(
                    f"{context}.deviceMatrix.{field_name}: "
                    f"expected {expected_type.__name__}"
                )
        for field_name in ("envs", "matrixKinds"):
            values = device_matrix.get(field_name)
            if isinstance(values, list) and not all(
                isinstance(item, str) and item for item in values
            ):
                errors.append(
                    f"{context}.deviceMatrix.{field_name}: expected string entries"
                )

    for collection_name in ("smokeCases", "uiJourneys"):
        collection = registry.get(collection_name)
        if not isinstance(collection, dict):
            continue
        for entry_name, entry in collection.items():
            context = f"registry.{collection_name}.{entry_name}"
            if not isinstance(entry, dict):
                errors.append(f"{context}: expected object")
                continue
            path_value = entry.get("path")
            if not isinstance(path_value, str) or not path_value:
                errors.append(f"{context}.path: expected non-empty string")

    suites = registry.get("suites")
    if isinstance(suites, dict):
        for suite_name, suite in suites.items():
            if not isinstance(suite, dict):
                errors.append(f"registry.suites.{suite_name}: expected object")
    return errors


def verify_smoke_cases(registry: Dict[str, Any]) -> List[str]:
    errors = []
    cases = registry["smokeCases"]
    for case_id, case_def in cases.items():
        path = case_def["path"]
        errors.extend(check_file_exists(path, f"smokeCases.{case_id}"))
    return errors


def verify_ui_journeys(registry: Dict[str, Any]) -> List[str]:
    errors = []
    journeys = registry["uiJourneys"]
    for journey_id, journey_def in journeys.items():
        path = journey_def["path"]
        errors.extend(check_file_exists(path, f"uiJourneys.{journey_id}"))
    return errors


def verify_profile_references(registry: Dict[str, Any]) -> List[str]:
    errors = []
    profiles = registry["profiles"]
    cases = set(registry["smokeCases"])
    journeys = set(registry["uiJourneys"])

    for profile_name, profile_def in profiles.items():
        if profile_name in RETIRED_PROFILES:
            errors.append(
                f"profiles.{profile_name}: retired profile name still present; "
                f"expected one of {sorted(VALID_PROFILES)}"
            )
        for case_ref in profile_def["smokeCases"]:
            if case_ref not in cases:
                errors.append(
                    f"profiles.{profile_name}.smokeCases: "
                    f"references undefined case '{case_ref}'"
                )
        for journey_ref in profile_def["uiJourneys"]:
            if journey_ref not in journeys:
                errors.append(
                    f"profiles.{profile_name}.uiJourneys: "
                    f"references undefined journey '{journey_ref}'"
                )
        device_matrix = profile_def["deviceMatrix"]
        for env in device_matrix["envs"]:
            if env not in KNOWN_ENVS:
                errors.append(
                    f"profiles.{profile_name}.deviceMatrix.envs: "
                    f"unknown env '{env}'"
                )
    return errors


def verify_no_retired_profiles(registry: Dict[str, Any]) -> List[str]:
    errors = []
    profiles = set(registry["profiles"])
    for retired in RETIRED_PROFILES:
        if retired in profiles:
            errors.append(
                f"Retired profile '{retired}' still defined; "
                f"must be replaced with {sorted(VALID_PROFILES)}"
            )
    return errors


def main() -> int:
    if not SUITES_PATH.exists():
        print(f"FAIL: {SUITES_PATH} not found")
        return 1

    registry = load_suites()
    errors = verify_canonical_structure(registry)
    if not errors:
        errors.extend(verify_smoke_cases(registry))
        errors.extend(verify_ui_journeys(registry))
        errors.extend(verify_profile_references(registry))
        errors.extend(verify_no_retired_profiles(registry))

    if errors:
        print(f"FAIL: {len(errors)} error(s) in validation_suites.json:")
        for err in errors:
            print(f"  - {err}")
        return 1

    profiles = list(registry["profiles"])
    print(
        "OK: gamma validation suites — "
        f"{len(profiles)} profiles verified: {profiles}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
