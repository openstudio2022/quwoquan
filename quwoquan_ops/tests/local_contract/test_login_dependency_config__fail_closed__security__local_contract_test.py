from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_service.scripts.verify.verify_login_dependency_config import (
    retired_key_paths,
    verify_config,
    verify_nonprod_source_isolation,
)


def test_login_dependency_config__repository_matrix__security__local_contract() -> None:
    assert verify_config(
        "gamma",
        {
            "integration": {
                "external_interaction_base_url": "https://integration-service.local",
                "otp": {"mode": "fixed_test"},
                "social": {"providers": {}},
                "one_tap": {"resolver": "aliyun"},
            }
        },
    ) == []


def test_login_dependency_config__retired_bypass__security__local_contract() -> None:
    config = {
        "integration": {
            "external_interaction_base_url": "https://integration-service.local",
            "otp": {"mode": "fixed_test"},
            "sms_otp": {"sandbox_allowlist": {"enabled": True}},
            "social": {"providers": {}},
            "one_tap": {"resolver": "aliyun", "sandbox_phones": {}},
        }
    }

    assert retired_key_paths(config) == [
        "integration.sms_otp.sandbox_allowlist",
        "integration.one_tap.sandbox_phones",
    ]
    assert verify_config("gamma", config) == [
        "gamma: retired login config key integration.sms_otp.sandbox_allowlist",
        "gamma: retired login config key integration.one_tap.sandbox_phones",
    ]


def test_login_dependency_config__prod_rejects_fixed_otp__security__local_contract() -> None:
    failures = verify_config(
        "prod",
        {
            "integration": {
                "external_interaction_base_url": "https://integration-service.prod",
                "otp": {"mode": "fixed_test"},
                "social": {"providers": {}},
                "one_tap": {"resolver": "aliyun"},
            }
        },
    )
    assert failures == ["prod: integration.otp.mode must be provider"]


def test_login_dependency_config__nonprod_adapter_excluded_from_prod__security__local_contract() -> None:
    assert verify_nonprod_source_isolation() == []
