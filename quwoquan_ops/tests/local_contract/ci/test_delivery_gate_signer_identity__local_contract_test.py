# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#open-001
"""delivery-gate.yml 注入的 signer identity 字面值必须恰为 keyring 已登记的 identity。

03. Delivery Gate 用 job env 里的两个字面常量告诉 integration_qualification.py 去 keyring
取哪个 identity 的 active 公钥验签；identity 拼错或 keyring 改名时，这个漂移只会在
hosted 验签步骤才暴露。这里把 workflow 字面值与 keyring（DEC-010 的唯一真相源）锁在一起，
并按 purpose 校验两者没有交叉。
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "delivery-gate.yml"
KEYRING = ROOT / "quwoquan_ops" / "policies" / "evidence_signing_keyring.yaml"

IDENTITY_ENV_PURPOSE = {
    "QUALIFICATION_SIGNER_IDENTITY": "integration_qualification",
    "ENVIRONMENT_SIGNER_IDENTITY": "environment_acceptance",
}


def _promotion_verify_env() -> dict[str, str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    env = workflow["jobs"]["promotion_verify"].get("env") or {}
    return {key: str(value) for key, value in env.items()}


def _keyring_identity_purpose() -> dict[str, str]:
    keyring = yaml.safe_load(KEYRING.read_text(encoding="utf-8"))
    return {str(item["identity"]): str(item["purpose"]) for item in keyring["signers"]}


def test_promotion_verify_signer_identities_are_registered_in_keyring_with_matching_purpose() -> None:
    env = _promotion_verify_env()
    identities = _keyring_identity_purpose()
    for env_name, purpose in IDENTITY_ENV_PURPOSE.items():
        identity = env.get(env_name)
        assert identity, f"promotion_verify job env must declare {env_name}"
        assert "${{" not in identity, f"{env_name} must be a literal identity, not an expression"
        assert identity in identities, f"{env_name}={identity!r} is not registered in {KEYRING.name}"
        assert identities[identity] == purpose, (
            f"{env_name}={identity!r} has keyring purpose {identities[identity]!r}, expected {purpose!r}"
        )


def test_promotion_verify_passes_each_identity_literal_to_integration_qualification() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    qualification_call = text[text.index("quwoquan_ops/ci/integration_qualification.py"):]
    qualification_call = qualification_call[: qualification_call.index("\n      - name:")]
    assert '--expected-qualification-signer-identity "$QUALIFICATION_SIGNER_IDENTITY"' in qualification_call
    for environment in ("alpha", "beta", "gamma"):
        assert f'--expected-{environment}-signer-identity "$ENVIRONMENT_SIGNER_IDENTITY"' in qualification_call
