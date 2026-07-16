#!/usr/bin/env python3
"""验证四环境登录外部依赖配置不含已退休的绕过机制。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - repository tool dependency
    print("FAIL: PyYAML is required for verify_login_dependency_config", file=sys.stderr)
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[3]
USER_CONFIGS = ROOT / "quwoquan_service" / "services" / "user-service" / "configs"
USER_CMD_API = ROOT / "quwoquan_service" / "services" / "user-service" / "cmd" / "api"
USER_INTEGRATION = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "user-service"
    / "internal"
    / "infrastructure"
    / "integration"
)
USER_DOCKERFILE = ROOT / "quwoquan_service" / "services" / "user-service" / "deploy" / "Dockerfile"
GAMMA_COMPOSE = ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.gamma-local.yaml"
ENVIRONMENTS = ("default", "alpha", "beta", "gamma", "prod")
RETIRED_KEYS = frozenset(
    {
        "pass_through_enabled",
        "pass_through_debt_id",
        "pass_through_owner",
        "pass_through_expires_at",
        "debug_reveal_enabled",
        "sandbox_allowlist",
        "sandbox_phones",
    }
)


def load_mapping(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def retired_key_paths(value: object, path: str = "") -> list[str]:
    if isinstance(value, Mapping):
        findings: list[str] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key) in RETIRED_KEYS:
                findings.append(child_path)
            findings.extend(retired_key_paths(child, child_path))
        return findings
    if isinstance(value, list):
        findings = []
        for index, child in enumerate(value):
            findings.extend(retired_key_paths(child, f"{path}[{index}]"))
        return findings
    return []


def verify_config(env: str, config: Mapping[str, object]) -> list[str]:
    failures = [f"{env}: retired login config key {key}" for key in retired_key_paths(config)]
    integration = config.get("integration")
    if not isinstance(integration, Mapping):
        return failures + [f"{env}: integration config is required"]

    base_url = integration.get("external_interaction_base_url")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        failures.append(f"{env}: integration.external_interaction_base_url must use https")
    social = integration.get("social")
    if not isinstance(social, Mapping) or not isinstance(social.get("providers"), Mapping):
        failures.append(f"{env}: integration.social.providers must be a mapping")
    one_tap = integration.get("one_tap")
    if not isinstance(one_tap, Mapping) or one_tap.get("resolver") != "aliyun":
        failures.append(f"{env}: integration.one_tap.resolver must be aliyun")
    otp = integration.get("otp")
    expected_otp_mode = "provider" if env == "prod" else "fixed_test"
    if not isinstance(otp, Mapping) or otp.get("mode") != expected_otp_mode:
        failures.append(
            f"{env}: integration.otp.mode must be {expected_otp_mode}"
        )
    return failures


def verify_nonprod_source_isolation() -> list[str]:
    failures: list[str] = []
    nonprod_files = (
        USER_CMD_API / "otp_runtime_nonprod.go",
        USER_CMD_API / "otp_dispatch_nonprod.go",
    )
    prod_files = (
        USER_CMD_API / "otp_runtime_prod.go",
        USER_CMD_API / "otp_dispatch_prod.go",
    )
    for path in nonprod_files:
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not source.startswith("//go:build nonprod\n"):
            failures.append(f"nonprod OTP source must use nonprod build tag: {path}")
    for path in prod_files:
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not source.startswith("//go:build !nonprod\n"):
            failures.append(f"prod OTP source must exclude nonprod build: {path}")
    for path in USER_CMD_API.glob("*.go"):
        if path in nonprod_files or path.name.endswith("_test.go"):
            continue
        if "123456" in path.read_text(encoding="utf-8"):
            failures.append(f"fixed OTP code leaked into prod source set: {path}")
    dockerfile = USER_DOCKERFILE.read_text(encoding="utf-8")
    if "ARG GO_BUILD_FLAGS=-p=1 -tags=nonprod" in dockerfile:
        failures.append("user-service production Dockerfile must not default to nonprod tag")
    compose = GAMMA_COMPOSE.read_text(encoding="utf-8")
    if 'LOCAL_GAMMA_USER_GO_BUILD_FLAGS:--p=1 -tags=nonprod' not in compose:
        failures.append("gamma-local user-service must explicitly compile the nonprod OTP adapter")
    mtls_source = (USER_INTEGRATION / "service_mtls_client.go").read_text(encoding="utf-8")
    for env_name in (
        "INTEGRATION_SERVICE_MTLS_CA_FILE",
        "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE",
        "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE",
    ):
        if env_name not in mtls_source:
            failures.append(f"remote OTP mTLS source is missing {env_name}")
    otp_runtime = (USER_CMD_API / "otp_runtime.go").read_text(encoding="utf-8")
    if "NewIntegrationServiceMTLSClient" not in otp_runtime:
        failures.append("remote OTP assembly must use the integration-service mTLS client")
    return failures


def main() -> int:
    failures: list[str] = []
    for env in ENVIRONMENTS:
        config_path = USER_CONFIGS / env / "config.yaml"
        if not config_path.is_file():
            failures.append(f"{env}: config file missing: {config_path}")
            continue
        failures.extend(verify_config(env, load_mapping(config_path)))
    failures.extend(verify_nonprod_source_isolation())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("verify_login_dependency_config: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
