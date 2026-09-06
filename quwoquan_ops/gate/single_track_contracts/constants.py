"""扫描根、禁用字段清单与全部单轨正则的唯一定义处。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SINGLE_TRACK_BASELINE_RELATIVE_PATH = (
    "quwoquan_ops/policies/gates/single_track_exact_fingerprint_baseline.json"
)
SINGLE_TRACK_BASELINE_PATH = SINGLE_TRACK_BASELINE_RELATIVE_PATH
SINGLE_TRACK_BASELINE_SCHEMA = "single-track-exact-fingerprint-baseline"

FORBIDDEN_ENVELOPE_FIELDS = (
    "schemaVersion",
    "contractVersion",
    "registryRevision",
    "styleVersion",
    "catalogVersion",
    "definitionVersion",
)
VERSIONED_SCHEMA_VALUE = re.compile(
    r"(?:/v?[0-9]+|[._-]v[0-9]+|\.m[0-9]+)$",
    re.I,
)
# CI/CD create-once / append-only evidence 的 schema 后缀是持久字节的一部分，
# 不是 runtime/local/control 协议信封。这里复制 canonical evidence gate 及其
# 同一 release chain 的 exact identities，并把每个 identity 绑定到唯一生产或
# fixture path；闭集外的 quwoquan_ops.*.vN、同值异路径及 factory material
# 仍由通用扫描器阻断。
IMMUTABLE_EVIDENCE_SCHEMA_PATHS = {
    "quwoquan_ops.exact_integration_candidate.v1": frozenset(
        {
            "quwoquan_ops/ci/scoped_candidate/core.py",
            "quwoquan_ops/tests/local_contract/ci/test_integration_qualification__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/ci/test_scoped_integration_candidate__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/environment/test_environment_execution_cli__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/environment/test_environment_scheduler__local_contract_test.py",
        }
    ),
    "quwoquan_ops.integration_publish_admission.v1": frozenset(
        {
            "quwoquan_ops/ci/integration_qualification.py",
            "quwoquan_ops/ci/scoped_candidate/core.py",
            "quwoquan_ops/tests/local_contract/ci/test_integration_qualification__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/environment/test_environment_execution_cli__local_contract_test.py",
        }
    ),
    "quwoquan_ops.integration_publish_result.v1": frozenset(
        {
            "quwoquan_ops/ci/integration_qualification.py",
            "quwoquan_ops/ci/scoped_candidate/core.py",
            "quwoquan_ops/tests/local_contract/ci/test_integration_qualification__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/environment/test_environment_execution_cli__local_contract_test.py",
        }
    ),
    "quwoquan_ops.artifact_build_number_allocation.v1": frozenset(
        {
            "quwoquan_ops/ci/artifact_build_number.py",
            "quwoquan_ops/ci/release_qualification.py",
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/tests/local_contract/release/test_release_qualification__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_official_distribution_release__supply_chain__local_contract_test.py",
        }
    ),
    "quwoquan_ops.candidate_material_manifest.v1": frozenset(
        {
            "quwoquan_ops/ci/release_qualification.py",
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_qualified_prod__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_official_distribution_release__supply_chain__local_contract_test.py",
        }
    ),
    "quwoquan_ops.initial_release_authority_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
        }
    ),
    "quwoquan_ops.release_candidate_selection_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
        }
    ),
    "quwoquan_ops.release_qualification_request.v1": frozenset(
        {
            "quwoquan_ops/ci/artifact_build_number.py",
            "quwoquan_ops/ci/release_qualification.py",
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_official_distribution_release__supply_chain__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_qualification__local_contract_test.py",
        }
    ),
    "quwoquan_ops.release_tag_reservation_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
        }
    ),
    "quwoquan_ops.prod_deploy_material.v1": frozenset(
        {
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
        }
    ),
    "quwoquan_ops.prod_runtime_config_deployment_bundle.v1": frozenset(
        {
            "quwoquan_ops/tests/local_contract/release/test_qualified_prod__local_contract_test.py",
        }
    ),
    "quwoquan_ops.prod_activation_input.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
        }
    ),
    "quwoquan_ops.prod_released_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/ci/system_backsync.py",
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
            "quwoquan_ops/environments/evidence/prod_released_fact.schema.json",
            "quwoquan_ops/tests/local_contract/ci/test_system_backsync__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_qualified_prod__local_contract_test.py",
        }
    ),
    "quwoquan_ops.rollback_readiness_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_qualified_prod__local_contract_test.py",
        }
    ),
    "quwoquan_ops.post_release_soak_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/ci/system_backsync.py",
            "quwoquan_ops/environments/evidence/post_release_soak_fact.schema.json",
            "quwoquan_ops/tests/local_contract/ci/test_system_backsync__local_contract_test.py",
        }
    ),
    "quwoquan_ops.environment_acceptance_fact.v2": frozenset(
        {
            "quwoquan_ops/cli/lib/environment_acceptance_fact_contract.py",
            "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json",
            "quwoquan_ops/tests/local_contract/ci/test_scoped_integration_candidate__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/environment/test_environment_scheduler__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/stackctl/test_environment_acceptance_fact__local_contract_test.py",
        }
    ),
    "quwoquan_ops.environment_execution_request.v1": frozenset(
        {
            "quwoquan_ops/ci/environment_scheduler.py",
            "quwoquan_ops/environments/evidence/environment_execution_request.schema.json",
        }
    ),
    "quwoquan_ops.integration_qualification_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/integration_qualification.py",
            "quwoquan_ops/ci/promotion_evidence.py",
            "quwoquan_ops/ci/release_qualification.py",
            "quwoquan_ops/environments/evidence/integration_qualification_fact.schema.json",
            "quwoquan_ops/tests/local_contract/ci/test_promotion_evidence__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_qualification__local_contract_test.py",
        }
    ),
    "quwoquan_ops.promotion_admission_receipt.v1": frozenset(
        {
            "quwoquan_ops/ci/promotion_evidence.py",
            "quwoquan_ops/tests/local_contract/ci/test_system_backsync__local_contract_test.py",
        }
    ),
    "quwoquan_ops.main_source_seal.v1": frozenset(
        {
            "quwoquan_ops/ci/promotion_evidence.py",
            "quwoquan_ops/ci/release_qualification.py",
            "quwoquan_ops/tests/local_contract/ci/test_system_backsync__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_qualification__local_contract_test.py",
        }
    ),
    "quwoquan_ops.promotion_admission_handoff.v1": frozenset(
        {
            "quwoquan_ops/ci/promotion_evidence.py",
            "quwoquan_ops/tests/local_contract/ci/test_promotion_evidence__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/ci/test_system_backsync__local_contract_test.py",
        }
    ),
    "quwoquan_ops.release_candidate_tag_admission_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/environments/evidence/release_tag_admission_fact.schema.json",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
        }
    ),
    "quwoquan_ops.release_tag_admission_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
            "quwoquan_ops/environments/evidence/release_tag_admission_fact.schema.json",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_qualified_prod__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_workflow_convergence__contract__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_official_distribution_release__supply_chain__local_contract_test.py",
        }
    ),
    "quwoquan_ops.prod_activation_admission_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
            "quwoquan_ops/environments/evidence/prod_activation_admission_fact.schema.json",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
        }
    ),
    "quwoquan_ops.qualification_fact.v1": frozenset(
        {
            "quwoquan_ops/ci/qualified_prod.py",
            "quwoquan_ops/ci/release_qualification.py",
            "quwoquan_ops/ci/release_tag_admission.py",
            "quwoquan_ops/cli/commands/deploy_release_inputs.py",
            "quwoquan_ops/tests/local_contract/release/test_prod_acceptance_rollout_binding__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_qualified_prod__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_release_tag_admission__local_contract_test.py",
            "quwoquan_ops/tests/local_contract/release/test_official_distribution_release__supply_chain__local_contract_test.py",
        }
    ),
    "application/vnd.quwoquan.environment-acceptance-fact.v2+json": frozenset(
        {
            "quwoquan_ops/cli/lib/environment_acceptance_fact_contract.py",
            "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json",
            "quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py",
        }
    ),
    "application/vnd.quwoquan.integration-qualification-fact.v1+json": frozenset(
        {
            "quwoquan_ops/ci/integration_qualification.py",
            "quwoquan_ops/ci/promotion_evidence.py",
            "quwoquan_ops/environments/evidence/integration_qualification_fact.schema.json",
            "quwoquan_ops/tests/local_contract/ci/test_promotion_evidence__local_contract_test.py",
        }
    ),
}
# 已知契约身份前缀 + 版本后缀（/N .vN .mN）。已登记 DSSE payloadType
# 从完整 media type 起始处优先匹配，避免把签名协议降格为内嵌 schema 片段。
_IMMUTABLE_DSSE_PAYLOAD_TYPE_PATTERN = "|".join(
    re.sub(r"\\\.v[0-9]+", r"\\.v[0-9]+", re.escape(value))
    for value in IMMUTABLE_EVIDENCE_SCHEMA_PATHS
    if value.startswith("application/vnd.")
)
VERSIONED_INLINE = re.compile(
    rf"\b(?:{_IMMUTABLE_DSSE_PAYLOAD_TYPE_PATTERN}|"
    r"(?:quwoquan_(?:data|service)|quwoquan\.[A-Za-z0-9_.-]+|"
    r"environment-topology|media-delivery-manifest|local-env-port-manifest|"
    r"prod-plane-access-isolation|legal-static|qwq\.runtime_shared_package|"
    r"app_remote_config|feed_patch|assistant_stream_event|"
    r"qwq-rich-md|release_desired_state|"
    r"content_import_report|homepage_import_report)"
    r"[A-Za-z0-9_.-]*(?:/v?[0-9]+|\.v[0-9]+|\.m[0-9]+))\b"
)
# schema 字段值带版本后缀（assets / json / yaml）；同一 schema 身份只允许一个稳定名。
SCHEMA_VALUE_V_SUFFIX = re.compile(
    r"""(?:^[ \t]*schema[ \t]*:[ \t]*["']?|["']schema["'][ \t]*:[ \t]*["'])"""
    r"""(?P<value>[A-Za-z0-9_.:/-]+(?:/v?[0-9]+|[._-]v[0-9]+|\.m[0-9]+))"""
    r"""["']?[ \t]*(?:,|#.*)?$""",
    re.I | re.M,
)
# App 本地持久化 key、feature flag、runtime identifier 必须使用稳定语义名，
# 不能把 v1/v2 变成第二条存储或控制轨。只扫描无空白的完整字符串字面量，
# 不涉及 UUID.v4、产品展示版本或带 /vN/ 的 immutable media release path。
VERSIONED_LOCAL_IDENTITY_LITERAL = re.compile(
    r"['\"](?P<value>(?:"
    r"qwq[._:]|comment_draft|post_publication_intents|app_permission_primer|"
    r"startup_telemetry|active_snapshot|previous_snapshot|"
    r"global_search_recent_entries|user_relationship_state|"
    r"post_interaction_state|client_state_sync_outbox|ops\.|"
    r"home_circles\.selected_channels|assistant_skill_consents|"
    r"assistant_learning_projection"
    r"|recovery-failure-queue|qwq_recovery_failure_queue"
    r")[A-Za-z0-9_.:-]*[._:-]v[0-9]+)(?::)?['\"]",
    re.I,
)
VERSIONED_INTERPOLATED_QUEUE_IDENTITY = re.compile(
    r"""['"](?P<value>[^'"\n]*\$(?:\{)?(?:baseName|queueName)(?:\})?"""
    r"""[^'"\n]*[._:-]v(?:[0-9]+|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)[._:-]"""
    r"""[^'"\n]*)['"]""",
    re.I,
)
VERSIONED_MIGRATION_IDENTITY = re.compile(
    r"['\"](?P<value>[A-Za-z0-9_.:-]*(?:canonical|migration)[A-Za-z0-9_.:-]*[._:-]v[0-9]+)['\"]",
    re.I,
)
VERSIONED_GOLDEN_ASSET_NAME = re.compile(r"(?:^|[._-])v[0-9]+(?:[._-]|$)", re.I)
# 已明确退休的第一方生产身份。这里只列业务自定义 namespace/format/profile，
# 不覆盖 Kubernetes/API/SDK/SemVer、SQL migration、aggregate revision 或
# immutable media slice 等有独立演进语义的外部/存储身份。
RETIRED_CUSTOM_IDENTITY = re.compile(
    r"(?:"
    r"content_(?:processing_(?:progressive_mp4|image_baseline)|image_normalization|video_transcode)_v[0-9]+"
    r"|premium_pool_projection_v[0-9]+"
    r"|global_premium_pool_v[0-9]+:"
    r"|opaque_aes_gcm_v[0-9]+"
    r"|otpref\.v[0-9]+\."
    r"|sourced-video-attribution-v[0-9]+"
    r"|replay-v[0-9]+"
    r"|m[0-9]+\.replay"
    r"|md\.v[0-9]+"
    r"|tool_observation_v[0-9]+"
    r")",
    re.I,
)
# These bytes already identify persisted device accounts, encrypted local
# stores, SharedPreferences journals, or a provider ticket payload. They have
# exactly one legal value. The embedded marker is historical opaque data, not
# permission to introduce a second protocol version.
FROZEN_IDENTITY_PATTERNS = (
    (
        "anonymous_device_salt",
        re.compile(r"qwq-anonymous-device(?:-v[0-9]+)?", re.I),
        "qwq-anonymous-device-v1",
    ),
    (
        "device_actor_salt",
        re.compile(r"qwq-device-actor(?:-v[0-9]+)?", re.I),
        "qwq-device-actor-v1",
    ),
    (
        "readiness_guest_salt",
        re.compile(r"qwq-readiness-guest(?:-v[0-9]+)?", re.I),
        "qwq-readiness-guest-v1",
    ),
    (
        "qq_mobile_ticket_prefix",
        re.compile(r"qq_mobile(?:_v[0-9]+)?\.", re.I),
        "qq_mobile_v1.",
    ),
    (
        "android_recovery_key_alias",
        re.compile(r"qwq_recovery_failure_queue(?:_v[0-9]+)?", re.I),
        "qwq_recovery_failure_queue_v1",
    ),
    (
        "ios_recovery_key_account",
        re.compile(r"recovery-failure-queue-key(?:-v[0-9]+)?", re.I),
        "recovery-failure-queue-key-v1",
    ),
    (
        "recovery_queue_file",
        re.compile(r"recovery_failures(?:\.v[0-9]+)?\.aesgcm", re.I),
        "recovery_failures.v1.aesgcm",
    ),
    (
        "startup_journal_key",
        re.compile(r"startup_telemetry_journal(?:_v[0-9]+)?", re.I),
        "startup_telemetry_journal_v1",
    ),
    (
        "startup_proof_key",
        re.compile(r"startup_telemetry_proof(?:_v[0-9]+)?", re.I),
        "startup_telemetry_proof_v1",
    ),
)
FROZEN_VERSIONED_LOCAL_IDENTITIES = frozenset(
    canonical
    for _, _, canonical in FROZEN_IDENTITY_PATTERNS
    if re.search(r"[._-]v[0-9]+", canonical, re.I)
)
RETIRED_USER_IDENTITY = re.compile(
    r"\bidentityRuleVersion\b|^[ \t]*[\"']?rule_version[\"']?[ \t]*:",
    re.I | re.M,
)
RETIRED_SEARCH_RECOMMENDATION_IDENTITY = re.compile(
    r"\b(?:IndexVersion|indexVersion|RankingVersion|rankingVersion|"
    r"ReasonVersion|reasonVersion)\b|"
    r"\b(?:retrieve|runtime-search|search)-v[0-9]+\b",
)
# Persona migration consumes one semantic source snapshot. ``LegacyPersona``
# and the later ``CurrentPersona`` rename both encode migration phase as a
# model identity and must never return.
RETIRED_PERSONA_MIGRATION_TYPE = re.compile(
    r"\b(?:LegacyPersona|CurrentPersona)\b"
)
RETIRED_RUNTIME_ERROR_MESSAGE_ALIAS = re.compile(
    r"(?:"
    r"^[ \t]{8}message[ \t]*:[ \t]*$"
    r"|json:\\?\"message(?:,omitempty)?\\?\""
    r"|\bMessage[ \t]*:[ \t]*debugMessage\b"
    r"|\b(?:body|error|json|map)\s*\??\s*\[\s*['\"]"
    r"(?:message|user_message|reasonMessage)['\"]\s*\]"
    r"|['\"](?:user_message|reasonMessage)['\"]"
    r")",
    re.M,
)
RUNTIME_ERROR_SINGLE_TRACK_PATHS = frozenset(
    {
        "quwoquan_service/contracts/metadata/_shared/openapi_common.yaml",
        "quwoquan_service/runtime/errors/errors.go",
        "quwoquan_app/lib/runtime/errors/cloud_error_mapper.dart",
    }
)
# 已完成字段切换的领域身份。字段名本身在外部 Provider、聚合并发修订、
# 通用可观测禁止清单等上下文仍可能合法，因此必须同时匹配领域路径或对象上下文。
RETIRED_DOMAIN_IDENTITY_FIELDS = (
    (
        "assistant_policy_release",
        re.compile(
            r"\b(?:releaseVersion|ReleaseVersion|release_version|"
            r"canonicalDigest|CanonicalDigest|canonical_digest)\b"
        ),
    ),
    (
        "product_ops_experiment_assignment",
        re.compile(r"\b(?:policyVersion|PolicyVersion|policy_version)\b"),
    ),
    (
        "recommendation_content_identity",
        re.compile(
            r"\b(?:modelVersion|ModelVersion|model_version|"
            r"featureVersion|FeatureVersion|feature_version|"
            r"featureContractVersion|FeatureContractVersion|"
            r"feature_contract_version)\b"
        ),
    ),
    (
        "assistant_learning_fact",
        re.compile(r"\b(?:eventVersion|EventVersion|event_version)\b"),
    ),
)
POLICY_DIGEST_LITERAL_ASSIGNMENT = re.compile(
    r"(?P<field_quote>[\"']?)(?:policyDigest|PolicyDigest|policy_digest)"
    r"(?P=field_quote)\s*[:=]\s*(?P<quote>[\"'])"
    r"(?P<value>[^\"'\n]*)(?P=quote)",
)
CANONICAL_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256_LITERAL = re.compile(r"sha256:[A-Za-z0-9._:-]+")
EXPLICIT_INVALID_SHA256_FIXTURE = re.compile(
    r"\binvalid_?sha256_?fixture\s*\(|\binvalidSha256Fixture\s*\(",
    re.I,
)
SHA256_ALGORITHM_IDENTITY_CONTEXT = re.compile(
    r"\b(?:algorithm|digestAlgorithm|DigestAlgorithm|implements?)\b|"
    r"\u7b97\u6cd5\u6807\u8bc6|\u5b9e\u73b0\s*sha256:",
    re.I,
)
SHA256_NEGATIVE_FIXTURE_CONTEXT = re.compile(
    r"(?:tamper(?:ed|ing)?|malformed|invalid|corrupt(?:ed|ion)?)"
    r".{0,40}(?:sha256|digest)|(?:sha256|digest)"
    r".{0,40}(?:tamper(?:ed|ing)?|malformed|invalid|corrupt(?:ed|ion)?)",
    re.I | re.S,
)
SHA256_REJECTION_ASSERTION = re.compile(
    r"require(?:Rejected|\.Error)|throws|assertRaises|assert .*error|"
    r"err\s*==\s*nil|expect\s*\([^\n]*(?:fail|reject|invalid|error)",
    re.I,
)
RETIRED_MOCK_EXPERIMENT_RUNTIME = re.compile(
    r"\b(?:ops_policy_version|ops_experiment_assignments|"
    r"_resolve_experiment_assignment|_build_experiment_stats)\b"
)
RETIRED_CREATE_ROUTE_EXTRA = re.compile(
    r"state\.extra\s+is\s+HomepageCanonicalReference"
)
APP_ROUTER_SINGLE_TRACK_PATH = (
    "quwoquan_app/lib/runtime/di/navigation/app_router.dart"
)
# client_state_sync 的同步事实只由队列记录状态表达；needsRemoteSync 是从
# 旧 guard shape 派生出的第二真相，业务源码不得重新引入。
RETIRED_CLIENT_STATE_SYNC_DERIVED_FIELD = re.compile(r"\bneedsRemoteSync\b")
RETIRED_MESSAGE_EVENT_ID_SEGMENT = re.compile(r"['\"]:v[0-9]+:['\"]", re.I)
RETIRED_CIRCLE_SNAPSHOT_SEGMENT = re.compile(r":members:v[0-9]+\b", re.I)
RETIRED_QUOTA_LOG_VERSION = re.compile(r"\bversion=v[0-9]+\b", re.I)
RETIRED_QUOTA_SHARD_VERSION = re.compile(r"\bv[0-9]+\s+quota shard\b", re.I)
RETIRED_GROUP_AVATAR_LAYOUT = re.compile(
    r"\bgroupAvatarLayoutVersion\b|[\"']layoutVersion[\"']"
)
FORBIDDEN_APP_REMOTE_CONFIG_PACKAGE_VERSION = re.compile(r"\bpackageVersion\b")
APP_REMOTE_CONFIG_SINGLE_IDENTITY_PATHS = frozenset(
    {
        "quwoquan_app/lib/runtime/config/app_remote_config_snapshot.dart",
        "quwoquan_app/lib/runtime/di/app_providers_content_runtime.dart",
        "quwoquan_app/lib/runtime/di/app_providers_content_runtime_defaults.dart",
        "quwoquan_service/services/content-service/internal/content/post/application/post_service_config_search.go",
    }
)
# schema 身份禁止纯数字 / 语义化数字版本
NUMERIC_SCHEMA_LITERAL = re.compile(
    r"""(?:^[ \t]*schema[ \t]*:|["']schema["']\s*:)\s*"""
    r"""(?:[0-9]+(?:\.[0-9]+)?|["'][0-9]+(?:\.[0-9]+)?["'])""",
    re.M,
)
TOP_LEVEL_VERSION = re.compile(r"^version:\s*", re.MULTILINE)
CUSTOM_CONTROL_VERSION_FIELDS = frozenset(
    {"version", "schemaVersion", "catalogVersion", "policyVersion"}
)
ALIASES_LINE = re.compile(r"^\s+aliases\s*:")
CONTRACT_COMPAT_ALIAS = re.compile(r"兼容别名|兼容字段别名|旧字段别名", re.I)
SKIP_EMPTY_ALIASES = re.compile(r"^\s+skip_empty_string_aliases\s*:")
SOURCE_KEYS_ALIAS_LINE = re.compile(r"^[ \t]*source_keys[ \t]*:", re.MULTILINE)
AUTH_REQUIRED_LINE = re.compile(r"^\s+auth_required\s*:")
OPTIONAL_ALIAS_HELPER = re.compile(r"_optionalAliasText|_requiredAliasText")
MAP_LIST_FIRST_PRESENT = re.compile(r"mapListFirstPresent\s*\(")
COMPAT_SMELLS = (
    re.compile(r"Back-compat|back-compat|backward compat|forward compat|forward-compat", re.I),
    re.compile(r"dual-read|dual_read|retired dual-read", re.I),
    re.compile(r"report_dir_compat"),
    re.compile(r"--warn-only"),
    re.compile(r"mode=compat"),
    re.compile(r"legacyMedia"),
)
# 同标识符多键 ??（任意变量名，含 raw?['a']）；键名不同才算双读
MULTI_KEY_DECODE = re.compile(
    r"(?P<ident>\w+)\s*\??\s*\[\s*['\"](?P<k1>[^'\"]+)['\"]\s*\]"
    r"(?:\s*(?:\?\.|\.)\s*toString\(\))?"
    r"(?:\s+as\s+\w+\?)?"
    r"\s*\?\?\s*"
    r"(?P=ident)\s*\??\s*\[\s*['\"](?P<k2>[^'\"]+)['\"]\s*\]"
)
# Go codegen 模板中的双读
MULTI_KEY_GO_TEMPLATE = re.compile(
    r"""json\[['\"][^'\"]+['\"]\][^?\n]{0,40}\?\?\s*json\[['\"][^'\"]+['\"]\]"""
)
# 正向「旧键仍可解析」测试语义（负例须用 rejects/拒绝）
POSITIVE_ALIAS_TEST = re.compile(
    r"(?:_id alias\s*→|_id alias\s*->|仍正确解析|支持\s*_id\s*alias|"
    r"parses counts with aliases|alias\s+used when|"
    r"旧字段名/alias 仍正确解析|旧字段/alias 仍正确解析|"
    r"别名兼容|也能正确投射|alias 必须被 DTO 正确归一|"
    r"likesCount alias 必须被 DTO|"
    r"WireAliases|StillParsed|CompatQueryStill)",
    re.I,
)
# specs / 军规中禁止再教「短期双读 / schemaVersion 契约信封 / 多协议版本」
DOC_DUAL_TRACK_TEACHING = re.compile(
    r"(?:短期双读|允许短期双读|短期并行读取|DTO 解析保留旧字段|feature flag 双读|"
    r"读接口双读|兼容旧字段|兼容存量版本|同时存在三个及以上版本|"
    r"schemaVersion\s*=\s*1|"
    r"支持兼容窗口|"
    r"(?:建议|允许)[^。\n]{0,80}(?:双写|可互相导出)|"
    r"双写或可互相导出)",
    re.I,
)
# 客户端 wire 禁止使用 _id 作为 JSON 键（storage/bson 除外）
DART_WIRE_ID_KEY = re.compile(
    r"""(?:m|map|json|obj|raw|root|payload|item|row|data|dm|parsed|e|v)"""
    r"""\s*\??\s*\[\s*['\"]_id['\"]\s*\]"""
)
GO_JSON_ID_TAG = re.compile(r"""json\s*:\s*["']_id["']""")
GO_BSON_ID_TAG = re.compile(r"""bson\s*:\s*["']_id["']""")
GO_MAP_ID_KEY = re.compile(r"""["']_id["']\s*:""")
GO_BSON_MAP_ID_KEY = re.compile(r"""\bbson\.M\s*\{[^\n]*["']_id["']\s*:""")
MULTI_KEY_HELPER_ID = re.compile(
    r"(?:_firstNonEmpty|mapListFirstPresent|mapListFirstNonEmpty)\s*\([^)]*['\"]_id['\"]",
    re.I | re.DOTALL,
)
ID_COMPAT_TEACHING = re.compile(
    r"(?:_id\s*/\s*id\s*兼容|id\s*/\s*_id\s*兼容|api_alias\s*:|"
    r"alias_resolution_mongodb_id|mongodb_id.*alias|_id\s*→\s*id\s*兼容)",
    re.I,
)
# 用户公开身份只认 userHandle/avatarUrl。这里仅拦截已经明确退休的公开路由、
# 页面入参和 User wire 别名；登录凭据或局部展示文案中的 username 不属于该契约。
PUBLIC_IDENTITY_RETIRED_PATTERNS = (
    re.compile(r"/user/\{username\}"),
    re.compile(r"\buserProfile\(\s*username\s*:"),
    re.compile(r"\bOtherProfilePage\(\s*username\s*:"),
    re.compile(r"\bcurrentUser\.username\b"),
    re.compile(r"\bavatarUrlOrAvatar\b"),
)
PUBLIC_USER_MODEL_RETIRED_PATTERNS = (
    re.compile(r"\b(?:final\s+)?String\??\s+username\b"),
    re.compile(r"\bthis\.username\b"),
    re.compile(r"\bjson\s*\[\s*['\"]username['\"]\s*\]"),
    re.compile(r"['\"]username['\"]\s*:"),
    re.compile(r"\b(?:final\s+)?String\??\s+avatar\b"),
    re.compile(r"\bthis\.avatar\b"),
    re.compile(r"\bjson\s*\[\s*['\"]avatar['\"]\s*\]"),
    re.compile(r"['\"]avatar['\"]\s*:"),
)
PUBLIC_USER_MODEL_SINGLE_TRACK_ROOT = (
    "quwoquan_app/lib/service/user_service/"
)
NEGATIVE_ID_TEST_LINE = re.compile(
    r"reject|拒绝|forbidden|不得|must not|只认|isEmpty|equals\(\s*''\s*\)|期望.*空",
    re.I,
)

SCAN_ROOTS = (
    "quwoquan_service/contracts",
    "quwoquan_service/tools/codegen_app_metadata",
    "quwoquan_service/internal/metadata",
    "quwoquan_service/services",
    "quwoquan_service/runtime",
    "quwoquan_service/scripts",
    "quwoquan_service/generated",
    "quwoquan_app/lib",
    "quwoquan_app/packages",
    "quwoquan_app/configs",
    "quwoquan_app/scripts",
    "quwoquan_app/assets",
    "quwoquan_app/android/app/src/main",
    "quwoquan_app/ios/Runner",
    "quwoquan_app/test",
    "quwoquan_data/schema",
    "quwoquan_data/scripts",
    "quwoquan_data/control_plane",
    "quwoquan_data/templates",
    "quwoquan_data/verticals",
    "quwoquan_data/tests",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
    "quwoquan_ops/gate",
    "quwoquan_ops/observability",
    "quwoquan_ops/policies/gates",
    "quwoquan_ops/tests",
    "quwoquan_ops/portal/src",
    "specs/feature-tree",
    ".cursor/rules",
)

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".dart_tool",
    "build",
    ".qwq_output",
    "vendor",
    "__pycache__",
    ".venv",
}

TEXT_SUFFIXES = {
    ".yaml",
    ".yml",
    ".json",
    ".go",
    ".dart",
    ".py",
    ".md",
    ".mdc",
    ".sh",
    ".java",
    ".kt",
    # Gradle 构建脚本同样声明契约校验：Android 打包期的 trust envelope 断言就写在
    # `build.gradle.kts` 里。少扫这个后缀，版本信封可以在构建脚本里长期存活。
    ".kts",
    ".swift",
}
