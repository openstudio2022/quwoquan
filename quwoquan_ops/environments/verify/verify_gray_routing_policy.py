#!/usr/bin/env python3
"""Validate the immutable API Edge production rollout policy.

The gate intentionally validates policy semantics, not Caddy matchers.  Caddy is
transport-only; stable/candidate allocation belongs to API Edge.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "quwoquan_ops/environments/prod/rollout/routing_policy.yaml"

STAGES = ("canary", "5", "20", "50", "100")
EXPECTED_BASIS_POINTS = {
    "canary": 0,
    "5": 500,
    "20": 2000,
    "50": 5000,
    "100": 10000,
}
ALLOWED_PLATFORMS = {"android", "ios", "web"}
ALLOWED_CARRIERS = {
    "chinamobile",
    "chinaunicom",
    "chinatelecom",
    "chinabroadnet",
    "unknown",
}
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
APP_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
)
REGION_PATTERN = re.compile(r"^(?:[1-9][0-9]{5}|unknown)$")


def _as_strings(values: object, label: str, failures: list[str]) -> list[str]:
    if not isinstance(values, list):
        failures.append(f"{label} must be a list")
        return []
    result = [str(value).strip() for value in values]
    if any(not value for value in result):
        failures.append(f"{label} contains an empty value")
    if len(result) != len(set(result)):
        failures.append(f"{label} contains duplicate values")
    return result


def _validate_selector(
    selector: object,
    *,
    label: str,
    allowed_modes: set[str],
    failures: list[str],
) -> tuple[str, list[str]]:
    if not isinstance(selector, dict):
        failures.append(f"{label} must be an object")
        return "", []
    mode = str(selector.get("mode") or "").strip()
    if mode not in allowed_modes:
        failures.append(f"{label}.mode must be one of {sorted(allowed_modes)}")
    values = _as_strings(selector.get("values"), f"{label}.values", failures)
    if mode == "all" and values:
        failures.append(f"{label}.values must be empty when mode=all")
    if mode == "include" and not values:
        failures.append(f"{label}.values must be non-empty when mode=include")
    if mode == "supported" and values:
        failures.append(f"{label}.values must be empty when mode=supported")
    return mode, values


def _selector_is_subset(
    previous: tuple[str, set[str]],
    current: tuple[str, set[str]],
    *,
    universal_mode: str,
) -> bool:
    previous_mode, previous_values = previous
    current_mode, current_values = current
    if current_mode == universal_mode:
        return True
    if previous_mode == universal_mode:
        return False
    return previous_values.issubset(current_values)


def validate_policy(policy: object) -> list[str]:
    failures: list[str] = []
    if not isinstance(policy, dict):
        return ["policy must be an object"]

    if not isinstance(policy.get("enabled"), bool):
        failures.append("policy.enabled must be a boolean")
    for field in ("campaignId", "allocationKeyId"):
        value = str(policy.get(field) or "").strip()
        if ID_PATTERN.fullmatch(value) is None:
            failures.append(f"policy.{field} is invalid")
    digest = str(policy.get("candidateDigest") or "").strip()
    if SHA256_PATTERN.fullmatch(digest) is None:
        failures.append("policy.candidateDigest must be sha256:<64 lowercase hex>")
    if policy.get("subjectKind") != "device_actor":
        failures.append("policy.subjectKind must be device_actor")
    if str(policy.get("stage") or "") not in STAGES:
        failures.append(f"policy.stage must be one of {list(STAGES)}")
    if policy.get("status") not in {"active", "paused", "rolled_back", "complete"}:
        failures.append("policy.status is invalid")
    upstream = urlparse(str(policy.get("candidateUpstream") or ""))
    if upstream.scheme not in {"http", "https"} or not upstream.netloc:
        failures.append("policy.candidateUpstream must be an absolute HTTP(S) origin")
    if int(policy.get("assignmentTtlDaysAfterCampaign") or 0) != 30:
        failures.append("policy.assignmentTtlDaysAfterCampaign must be 30")

    canary = policy.get("internalCanary")
    if not isinstance(canary, dict):
        failures.append("policy.internalCanary must be an object")
        canary = {}
    account_ids = _as_strings(
        canary.get("accountIds"), "policy.internalCanary.accountIds", failures
    )
    device_ids = _as_strings(
        canary.get("deviceActorIds"),
        "policy.internalCanary.deviceActorIds",
        failures,
    )
    if not account_ids and not device_ids:
        failures.append("policy.internalCanary requires at least one trusted subject")

    stages = policy.get("stages")
    if not isinstance(stages, dict) or tuple(stages) != STAGES:
        failures.append(f"policy.stages must declare exactly {list(STAGES)} in order")
        stages = {}

    previous: dict[str, tuple[str, set[str]]] | None = None
    for stage_name in STAGES:
        stage = stages.get(stage_name)
        label = f"policy.stages.{stage_name}"
        if not isinstance(stage, dict):
            failures.append(f"{label} must be an object")
            continue
        if stage.get("basisPoints") != EXPECTED_BASIS_POINTS[stage_name]:
            failures.append(
                f"{label}.basisPoints must be {EXPECTED_BASIS_POINTS[stage_name]}"
            )
        app_mode, app_values = _validate_selector(
            stage.get("appVersions"),
            label=f"{label}.appVersions",
            allowed_modes={"supported", "include"},
            failures=failures,
        )
        platform_mode, platform_values = _validate_selector(
            stage.get("platforms"),
            label=f"{label}.platforms",
            allowed_modes={"include"},
            failures=failures,
        )
        region_mode, region_values = _validate_selector(
            stage.get("regions"),
            label=f"{label}.regions",
            allowed_modes={"all", "include"},
            failures=failures,
        )
        carrier_mode, carrier_values = _validate_selector(
            stage.get("carriers"),
            label=f"{label}.carriers",
            allowed_modes={"all", "include"},
            failures=failures,
        )
        invalid_platforms = set(platform_values) - ALLOWED_PLATFORMS
        if invalid_platforms:
            failures.append(f"{label}.platforms has invalid values {sorted(invalid_platforms)}")
        if any(APP_VERSION_PATTERN.fullmatch(value) is None for value in app_values):
            failures.append(f"{label}.appVersions contains a non-semver value")
        if any(REGION_PATTERN.fullmatch(value) is None for value in region_values):
            failures.append(f"{label}.regions contains an invalid region")
        invalid_carriers = set(carrier_values) - ALLOWED_CARRIERS
        if invalid_carriers:
            failures.append(f"{label}.carriers has invalid values {sorted(invalid_carriers)}")

        current = {
            "platforms": (platform_mode, set(platform_values)),
            "appVersions": (app_mode, set(app_values)),
            "regions": (region_mode, set(region_values)),
            "carriers": (carrier_mode, set(carrier_values)),
        }
        if previous is not None:
            universal_modes = {
                "platforms": "",
                "appVersions": "supported",
                "regions": "all",
                "carriers": "all",
            }
            for dimension, current_selector in current.items():
                if not _selector_is_subset(
                    previous[dimension],
                    current_selector,
                    universal_mode=universal_modes[dimension],
                ):
                    failures.append(
                        f"{label}.{dimension} must not shrink the previous stage"
                    )
        previous = current

        if app_mode == "supported" and app_values:
            failures.append(f"{label}.appVersions supported mode cannot declare values")

    terminal = stages.get("100") if isinstance(stages, dict) else None
    if isinstance(terminal, dict):
        for dimension in ("regions", "carriers"):
            selector = terminal.get(dimension) or {}
            if selector.get("mode") != "all":
                failures.append(f"policy.stages.100.{dimension}.mode must be all")
        platforms = ((terminal.get("platforms") or {}).get("values") or [])
        if set(platforms) != ALLOWED_PLATFORMS:
            failures.append("policy.stages.100.platforms must include android/ios/web")
        if (terminal.get("appVersions") or {}).get("mode") != "supported":
            failures.append("policy.stages.100.appVersions.mode must be supported")

    synthetic = policy.get("syntheticCanary")
    if not isinstance(synthetic, dict):
        failures.append("policy.syntheticCanary must be an object")
    else:
        if int(synthetic.get("requests") or 0) < 120:
            failures.append("policy.syntheticCanary.requests must be >= 120")
        if not str(synthetic.get("path") or "").startswith("/"):
            failures.append("policy.syntheticCanary.path must be absolute")
        headers = synthetic.get("headers")
        if not isinstance(headers, dict) or str(
            headers.get("X-Release-Canary-Actor") or ""
        ) not in account_ids:
            failures.append(
                "synthetic canary actor must match internalCanary.accountIds"
            )
    return failures


def main() -> int:
    if not POLICY_PATH.is_file():
        print(f"FAIL: missing rollout policy: {POLICY_PATH}")
        return 1
    document = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
    failures = validate_policy(document.get("policy"))
    if failures:
        print("FAIL: rollout policy validation:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS: API Edge rollout policy validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
