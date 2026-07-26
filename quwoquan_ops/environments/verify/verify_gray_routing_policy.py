#!/usr/bin/env python3
"""灰度路由策略门禁。

校验 quwoquan_ops/environments/prod/rollout/routing_policy.yaml：
- schema 完整（enabled/grayUpstream/stageDimensions 四维列表）；
- carriers 只允许四大运营商枚举；provinces 必须是 GB/T 2260 六位省级码；
- appVersions 必须是 semver 形式；userIds 非空字符串；
- enabled=true 时 gray-initial/carry-on 均至少一个维度非空（禁止全空放行造成
  100% 灰度误导），full 必须为空。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "quwoquan_ops/environments/prod/rollout/routing_policy.yaml"

ALLOWED_CARRIERS = {"chinamobile", "chinaunicom", "chinatelecom", "chinabroadnet"}
PROVINCE_PATTERN = re.compile(r"^[1-9][0-9]{5}$")
APP_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$")


def main() -> int:
    failures: list[str] = []
    if not POLICY_PATH.is_file():
        print(f"FAIL: missing gray routing policy: {POLICY_PATH}")
        return 1
    doc = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    policy = (doc or {}).get("policy")
    if not isinstance(policy, dict):
        print("FAIL: gray_routing_policy.yaml must contain a policy object")
        return 1

    enabled = policy.get("enabled")
    if not isinstance(enabled, bool):
        failures.append("policy.enabled must be a boolean")

    upstream = str(policy.get("grayUpstream") or "").strip()
    if not upstream.startswith(("http://", "https://")):
        failures.append("policy.grayUpstream must be an http(s) URL to the gray stack edge")

    def validate_dimensions(label: str, dimensions: object) -> dict:
        if not isinstance(dimensions, dict):
            failures.append(f"{label} must be an object")
            return {}
        for key in ("appVersions", "userIds", "provinces", "carriers"):
            values = dimensions.get(key)
            if not isinstance(values, list):
                failures.append(f"{label}.{key} must be a list")
                continue
            for value in values:
                text = str(value).strip()
                if not text:
                    failures.append(f"{label}.{key} contains an empty value")
                elif key == "carriers" and text not in ALLOWED_CARRIERS:
                    failures.append(
                        f"{label}.carriers value {text!r} is not in {sorted(ALLOWED_CARRIERS)}"
                    )
                elif key == "provinces" and not PROVINCE_PATTERN.match(text):
                    failures.append(
                        f"{label}.provinces value {text!r} must be a GB/T 2260 six-digit code"
                    )
                elif key in {"provinces", "carriers"}:
                    failures.append(
                        f"{label}.{key} cannot be enabled until trusted edge attestation is implemented"
                    )
                elif key == "appVersions" and not APP_VERSION_PATTERN.match(text):
                    failures.append(
                        f"{label}.appVersions value {text!r} must be a semver version"
                    )
        return dimensions

    stage_dimensions = policy.get("stageDimensions")
    if not isinstance(stage_dimensions, dict) or set(stage_dimensions) != {
        "gray-initial",
        "carry-on",
        "full",
    }:
        failures.append("policy.stageDimensions must declare gray-initial/carry-on/full")
        stage_dimensions = {}
    validated_stages = {
        stage: validate_dimensions(
            f"policy.stageDimensions.{stage}",
            stage_dimensions.get(stage),
        )
        for stage in ("gray-initial", "carry-on", "full")
    }
    if any(
        validated_stages["full"].get(key)
        for key in ("appVersions", "userIds", "provinces", "carriers")
    ):
        failures.append("policy.stageDimensions.full must disable gray routing")

    canary = policy.get("syntheticCanary")
    if not isinstance(canary, dict):
        failures.append("policy.syntheticCanary must be an object")
    else:
        if int(canary.get("requests") or 0) < 100:
            failures.append("policy.syntheticCanary.requests must be >= 100")
        headers = canary.get("headers")
        if not isinstance(headers, dict) or not headers:
            failures.append("policy.syntheticCanary.headers must be non-empty")
        elif str(headers.get("X-Client-User-Id") or "") not in validated_stages[
            "gray-initial"
        ].get("userIds", []):
            failures.append("synthetic canary user must match gray-initial userIds")
    if upstream.startswith("http://") and policy.get("grayUpstreamTlsInsecureSkipVerify"):
        failures.append("HTTP gray upstream cannot enable TLS insecure skip verify")

    if enabled is True:
        for stage in ("gray-initial", "carry-on"):
            if not any(
                validated_stages[stage].get(key)
                for key in ("appVersions", "userIds", "provinces", "carriers")
            ):
                failures.append(
                    f"policy.enabled=true requires a non-empty {stage} dimension "
                    "(refuse to imply full-traffic gray routing)"
                )

    if failures:
        print("FAIL: gray routing policy validation:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("PASS: gray routing policy validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
