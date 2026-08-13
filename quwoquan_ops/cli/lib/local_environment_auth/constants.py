"""local_environment_auth 包共享常量（原单文件顶部常量逐字搬移）。"""

from __future__ import annotations

from pathlib import Path

_SECRET_KEYS = (
    "jwt_secret",
    "device_ticket_secret",
    "otp_code_ref_key_b64",
    "push_token_encryption_key_b64",
    "research_identity_attestation_key_b64",
    "account_closure_subject_hmac_secret",
    "rtc_media_api_key",
    "rtc_media_api_secret",
    "sms_substitute_provider_token",
    "sms_substitute_operator_token",
    "provider_substitute_operator_token",
    "sms_substitute_capture_key_b64",
)
_LOCAL_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    # prod-sim 使用 production 配置投影，但其认证材料仍限定在本机部署目录。
    "prod": "prod-sim",
}
_TEST_DATA_IDENTITY_SET_SCHEMA = "qwq.test_data_identity_set.v1"
_TEST_DATA_IDENTITY_SET_PATH_ENV = "QWQ_TEST_DATA_IDENTITY_SET_PATH"
_TEST_DATA_IDENTITY_SET_NAME = "test-data-identity-set.json"
_TEST_DATA_IDENTITY_SET_LOCK_NAME = "test-data-identity-set.lock"
_TEST_DATA_PHONE_PROFILES = frozenset({"nonroutable", "mainland_ui"})
_RESEARCH_IDENTITY_BINDING_SCHEMA = "qwq.local_research_identity_binding.v1"
_RESEARCH_IDENTITY_BINDING_NAME = "research-identity-binding.json"
_CROCKFORD_LOWER = "0123456789abcdefghjkmnpqrstvwxyz"
# 原单文件为 parents[3]；包形态多一层目录，改为 parents[4]，值保持仓库根不变。
_REPO_ROOT = Path(__file__).resolve().parents[4]
