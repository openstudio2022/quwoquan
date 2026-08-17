from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 被测脚本位于带连字符的服务域目录，无法经常规包路径 import，按文件加载。
_SCRIPT_PATH = (
    ROOT / "quwoquan_service/scripts/user-service/verify_login_dependency_config.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "verify_login_dependency_config", _SCRIPT_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

retired_key_paths = _MODULE.retired_key_paths
verify_config = _MODULE.verify_config
verify_nonprod_source_isolation = _MODULE.verify_nonprod_source_isolation


NONPROD_DEFAULTS = {
    "sys.user-service.integration.external_interaction_base_url": (
        "http://integration-service:18086"
    ),
}
NONPROD_USER_BINDINGS = {
    "identity.carrier.one_tap": {
        "state": "enabled",
        "adapter": "ext.auth.carrier_one_tap_protocol_fixture",
    },
    "identity.social.login": {
        "state": "enabled",
        "adapter": "ext.auth.federated_identity_protocol_fixture",
    },
}
PROD_USER_BINDINGS = {
    "identity.carrier.one_tap": {
        "state": "enabled",
        "adapter": "ext.auth.carrier_one_tap",
    },
    "identity.social.login": {
        "state": "enabled",
        "adapter": "ext.auth.federated_identity",
    },
}
NONPROD_INTEGRATION_CONFIG = {
    "externalBindings": {
        "identity.sms.otp": {
            "state": "enabled",
            "adapter": "ext.sms.local_capture",
        }
    }
}
PROD_INTEGRATION_CONFIG = {
    "externalBindings": {
        "identity.sms.otp": {
            "state": "enabled",
            "adapter": "ext.sms.aliyun",
        }
    }
}


def test_login_dependency_config__repository_matrix__security__local_contract() -> None:
    assert verify_config(
        "gamma",
        {"externalBindings": NONPROD_USER_BINDINGS},
        NONPROD_DEFAULTS,
        NONPROD_INTEGRATION_CONFIG,
    ) == []


def test_login_dependency_config__retired_bypass__security__local_contract() -> None:
    config = {
        "overrides": {
            "sys.user-service.integration.external_interaction_base_url": (
                "http://integration-service:18086"
            ),
        },
        "integration": {
            "external_interaction_base_url": "http://integration-service:18086",
            "otp": {"mode": "retired"},
            "sms_otp": {"sandbox_allowlist": {"enabled": True}},
            "social": {"providers": {}},
            "one_tap": {"resolver": "aliyun", "sandbox_phones": {}},
        },
        "externalBindings": NONPROD_USER_BINDINGS,
    }

    assert retired_key_paths(config) == [
        "integration.sms_otp.sandbox_allowlist",
        "integration.one_tap.sandbox_phones",
    ]
    assert verify_config(
        "gamma", config, NONPROD_DEFAULTS, NONPROD_INTEGRATION_CONFIG
    ) == [
        "gamma: retired login config key integration.sms_otp.sandbox_allowlist",
        "gamma: retired login config key integration.one_tap.sandbox_phones",
    ]


def test_login_dependency_config__retired_otp_mode__security__local_contract() -> None:
    failures = verify_config(
        "prod",
        {
            "overrides": {
                "sys.user-service.integration.external_interaction_base_url": (
                    "https://integration-service.prod"
                ),
                "sys.user-service.integration.otp.mode": "retired",
            },
            "externalBindings": PROD_USER_BINDINGS,
        },
        NONPROD_DEFAULTS,
        PROD_INTEGRATION_CONFIG,
    )
    assert failures == [
        "prod: retired OTP mode configuration sys.user-service.integration.otp.mode"
    ]


def test_login_dependency_config__nonprod_adapter_excluded_from_prod__security__local_contract() -> None:
    assert verify_nonprod_source_isolation() == []
