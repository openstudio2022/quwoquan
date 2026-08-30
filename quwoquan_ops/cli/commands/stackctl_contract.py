"""Stable stackctl CLI constants shared with command packages."""
from __future__ import annotations

RUNTIME_CANDIDATE_ROOT_ENV = "QWQ_RUNTIME_CANDIDATE_ROOT"
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV = (
    "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
)
TEST_DATA_TARGETS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
}


VERIFY_COMMAND_GROUPS = {
    "topology": [
        ["python3", "quwoquan_ops/gate/verify_stackctl_args_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_environment_assembly.py"],
        ["python3", "quwoquan_ops/gate/verify_local_env_port_manifest.py"],
    ],
    "config": [
        ["python3", "quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_media_delivery_contract.py"],
        # 推荐 policy 单轨：gamma 只绑定 canonical 内容摘要，不允许环境变体。
        ["python3", "quwoquan_ops/gate/verify_canonical_recommendation_policy.py"],
    ],
    "packaging": [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"],
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ],
}

DEFAULT_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
PROVIDER_CONFORMANCE_SCRIPT = "quwoquan_ops/cli/lib/provider_conformance.py"
PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PROVIDER_CONFORMANCE_LAYERS = (
    "local_contract",
    "api_integration",
    "user_acceptance",
)

__all__ = [
    "DEFAULT_TARGET_BY_ENV", "PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS",
    "PROVIDER_CONFORMANCE_LAYERS", "PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV",
    "PROVIDER_CONFORMANCE_SCRIPT", "RUNTIME_CANDIDATE_ROOT_ENV", "TEST_DATA_TARGETS",
    "VERIFY_COMMAND_GROUPS",
]
