"""Acceptance actor identities and canonical UAT entrypoint targets.

`stackctl` 只保留唯一 CLI 入口与 dispatch；验收 Actor 身份、dart UAT 目标与
受管 manifest/validator/runner 路径是独立 concern，由本模块单独拥有并经
`stackctl` 再导出，保持 `_stackctl.<name>` 消费与测试 patch 语义零漂移。
"""

from __future__ import annotations

from enum import StrEnum


class ProfileActorCaseId(StrEnum):
    """Strong identities for profile commands that need one isolated actor."""

    GAMMA_ONBOARDING_AUTHOR_IMPACT = "gamma-onboarding-author-impact"
    GAMMA_SEARCH_REMOTE = "gamma-search-remote"
    GAMMA_ASSISTANT_LEARNING = "gamma-assistant-learning"
    GAMMA_PROFILE_PROPOSAL = "gamma-profile-proposal"
    BETA_REPORT_FEEDBACK = "beta-report-feedback"
    GAMMA_REPORT_FEEDBACK = "gamma-report-feedback"
    BETA_MEDIA_PUBLICATION = "beta-media-publication"
    GAMMA_MEDIA_PUBLICATION = "gamma-media-publication"
    BETA_CHAT_GROUP = "beta-chat-group"
    GAMMA_CHAT_GROUP = "gamma-chat-group"
    APP_CONTENT_UAT = "app-content-uat"


GAMMA_CONTENT_UAT_TARGET = "gamma-local"
RELEASE_HOMEPAGE_UAT_TEST_TARGET = (
    "test/user_acceptance/service/entity_service/entity_homepage/homepage/"
    "release_homepage__consumer_render__functional__user_acceptance_test.dart"
)
RUNTIME_RECOVERY_UAT_TEST_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "runtime_recovery_journey__user_acceptance_test.dart"
)
ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "product-ops-service/gamma/account_enforcement_gamma_uat_manifest.json"
)
ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "product-ops-service/gamma/account_enforcement_gamma_uat.py"
)
ACCOUNT_ENFORCEMENT_GAMMA_DEVICE_RUNNER = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "product-ops-service/smoke/run_account_enforcement_device_matrix.py"
)
