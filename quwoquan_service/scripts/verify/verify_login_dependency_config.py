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
USER_SERVICE = ROOT / "quwoquan_service" / "services" / "user-service"
USER_CONFIG_SCHEMA = USER_SERVICE / "config" / "schema.yaml"
USER_ENVIRONMENTS = USER_SERVICE / "environments"
USER_CMD_API = ROOT / "quwoquan_service" / "services" / "user-service" / "cmd" / "api"
USER_INTEGRATION = (
    USER_SERVICE
    / "internal"
    / "account"
    / "user_account"
    / "infrastructure"
    / "integration"
)
USER_DOCKERFILE = USER_SERVICE / "build" / "Dockerfile"
GAMMA_COMPOSE = USER_SERVICE / "deploy" / "compose.yaml"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
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
RETIRED_OTP_MODE_KEY = "sys.user-service.integration.otp.mode"


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


def schema_defaults(schema: Mapping[str, object]) -> dict[str, object]:
    definitions = schema.get("configs")
    if not isinstance(definitions, list):
        return {}
    return {
        str(item["key"]): item.get("default")
        for item in definitions
        if isinstance(item, Mapping) and item.get("key") and "default" in item
    }


def verify_config(
    env: str,
    config: Mapping[str, object],
    defaults: Mapping[str, object],
) -> list[str]:
    failures = [f"{env}: retired login config key {key}" for key in retired_key_paths(config)]
    overrides = config.get("overrides")
    if not isinstance(overrides, Mapping):
        overrides = {}
    base_url = overrides.get(
        "sys.user-service.integration.external_interaction_base_url",
        defaults.get("sys.user-service.integration.external_interaction_base_url"),
    )
    if env == "prod":
        if not isinstance(base_url, str) or not base_url.startswith("https://"):
            failures.append(
                f"{env}: sys.user-service.integration.external_interaction_base_url must use https"
            )
    elif base_url != "http://integration-service:18086":
        failures.append(
            f"{env}: sys.user-service.integration.external_interaction_base_url "
            "must be the canonical nonprod internal http mesh URL "
            "http://integration-service:18086"
        )
    if RETIRED_OTP_MODE_KEY in overrides or RETIRED_OTP_MODE_KEY in defaults:
        failures.append(
            f"{env}: retired OTP mode configuration {RETIRED_OTP_MODE_KEY}"
        )
    bindings = config.get("externalBindings")
    if not isinstance(bindings, Mapping):
        failures.append(f"{env}: externalBindings must declare the login capability states")
        return failures
    sms_binding = bindings.get("identity.sms.otp")
    if not isinstance(sms_binding, Mapping) or sms_binding.get("state") != "enabled":
        failures.append(
            f"{env}: identity.sms.otp consumer binding must be enabled"
        )
    optional_state = "enabled" if env == "prod" else "not_required"
    for capability_id in ("identity.carrier.one_tap", "identity.social.login"):
        binding = bindings.get(capability_id)
        if not isinstance(binding, Mapping) or binding.get("state") != optional_state:
            failures.append(
                f"{env}: {capability_id} must be {optional_state} for the selected login profile"
            )
    return failures


def verify_auth_boundary_isolation() -> list[str]:
    failures: list[str] = []
    forbidden_vendor_tokens = ("wechat", "alipay", "aliyun", "qq")
    for path in (USER_SERVICE / "internal").rglob("*.go"):
        parts = path.relative_to(USER_SERVICE / "internal").parts
        if len(parts) < 4 or parts[2] not in {"application", "domain"}:
            continue
        source = path.read_text(encoding="utf-8").lower()
        for token in forbidden_vendor_tokens:
            if token in source:
                failures.append(
                    f"vendor token {token!r} leaked into application/domain source: {path}"
                )
    composition = (USER_CMD_API / "main_auth_runtime.go").read_text(encoding="utf-8")
    for retired_selector in (
        "USER_AUTH_EXTERNAL_PROVIDER_MODE",
        "socialAuthProviderClient",
        "oneTapResolver",
        "map[string]userintegration.ProviderOAuthConfig",
    ):
        if retired_selector in composition:
            failures.append(
                f"auth composition must not retain runtime provider selection: {retired_selector}"
            )
    for required_binding in (
        "newFederatedLoginBindings",
        "NewWechatFederatedIdentityVerifier",
        "NewAlipayFederatedIdentityVerifier",
        "NewQqFederatedIdentityVerifier",
        "newCarrierPhoneResolver",
    ):
        if required_binding not in composition:
            failures.append(
                f"auth composition is missing explicit fail-closed binding: {required_binding}"
            )
    return failures


def verify_nonprod_source_isolation() -> list[str]:
    failures: list[str] = []
    retired_otp_files = (
        USER_CMD_API / "otp_runtime_nonprod.go",
        USER_CMD_API / "otp_dispatch_nonprod.go",
        USER_CMD_API / "otp_runtime_prod.go",
        USER_CMD_API / "otp_dispatch_prod.go",
    )
    for path in retired_otp_files:
        if path.exists():
            failures.append(f"retired OTP runtime source must be deleted: {path}")
    for path in USER_CMD_API.glob("*.go"):
        if path.name.endswith("_test.go"):
            continue
        source = path.read_text(encoding="utf-8")
        for retired_token in (
            "fixed_test",
            "USER_AUTH_OTP_MODE",
            "otpExternalInteractionClientForEnvironment",
        ):
            if retired_token in source:
                failures.append(f"retired OTP bypass leaked into runtime source: {path}")
    dockerfile = USER_DOCKERFILE.read_text(encoding="utf-8")
    if "ARG GO_BUILD_FLAGS=-p=1 -tags=nonprod" in dockerfile:
        failures.append("user-service production Dockerfile must not default to nonprod tag")
    compose = GAMMA_COMPOSE.read_text(encoding="utf-8")
    if "-tags=nonprod" in compose:
        failures.append("gamma-local user-service must not compile a special OTP adapter")
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
    schema = load_mapping(USER_CONFIG_SCHEMA)
    failures.extend(
        f"schema: retired login config key {key}" for key in retired_key_paths(schema)
    )
    defaults = schema_defaults(schema)
    for env in ENVIRONMENTS:
        config_path = USER_ENVIRONMENTS / env / "config.yaml"
        if not config_path.is_file():
            failures.append(f"{env}: config file missing: {config_path}")
            continue
        failures.extend(verify_config(env, load_mapping(config_path), defaults))
    failures.extend(verify_auth_boundary_isolation())
    failures.extend(verify_nonprod_source_isolation())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("verify_login_dependency_config: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
