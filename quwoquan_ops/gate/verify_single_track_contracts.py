#!/usr/bin/env python3
"""全仓单轨契约零兼容门禁：禁止版本信封、aliases、双读与 warn-only 逃逸。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

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
# 已知契约身份前缀 + 版本后缀（/N .vN .mN）
VERSIONED_INLINE = re.compile(
    r"\b(?:quwoquan_(?:data|service)|quwoquan\.[A-Za-z0-9_.-]+|"
    r"environment-topology|media-delivery-manifest|local-env-port-manifest|"
    r"prod-plane-access-isolation|legal-static|qwq\.runtime_shared_package|"
    r"app_remote_config|feed_patch|assistant_stream_event|"
    r"qwq-rich-md|release_desired_state|"
    r"content_import_report|homepage_import_report)"
    r"[A-Za-z0-9_.-]*(?:/v?[0-9]+|\.v[0-9]+|\.m[0-9]+)\b"
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
        "quwoquan_app/lib/cloud/runtime/errors/cloud_error_mapper.dart",
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
        "quwoquan_app/lib/cloud/runtime/models/app_remote_config_snapshot.dart",
        "quwoquan_app/lib/core/providers/app_providers_content_runtime.dart",
        "quwoquan_app/lib/core/providers/app_providers_content_runtime_defaults.dart",
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
    ".swift",
}


@dataclass
class Finding:
    category: str
    path: str
    detail: str


@dataclass
class Inventory:
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, category: str, path: Path, detail: str) -> None:
        rel = path.relative_to(ROOT).as_posix()
        self.findings.append(Finding(category, rel, detail))
        self.counts[category] += 1


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SKIP_DIR_NAMES)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in TEXT_SUFFIXES:
                continue
            if should_skip(path):
                continue
            files.append(path)
    return sorted(files)


def scan_versioned_golden_assets(inv: Inventory) -> None:
    """Golden 基线是唯一当前 UI 事实，文件名不得维护 v1/v2 平行身份。"""
    test_root = ROOT / "quwoquan_app" / "test"
    if not test_root.exists():
        return
    for path in sorted(test_root.rglob("*")):
        if not path.is_file() or "goldens" not in path.parts:
            continue
        if VERSIONED_GOLDEN_ASSET_NAME.search(path.name):
            inv.add("T1_versioned_golden_identity", path, path.name)


def is_metadata_object_yaml(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if not rel.startswith("quwoquan_service/contracts/metadata/"):
        return False
    if "/_schemas/" in rel or rel.endswith("business_object_map.yaml"):
        return False
    if path.suffix not in {".yaml", ".yml"}:
        return False
    return True


def is_custom_control_document(path: Path) -> bool:
    """Return custom control documents that must not define version keys.

    Scope is deliberately path-based. Provider/Kubernetes manifests, pubspec,
    OpenAPI and domain aggregate/media contracts retain their own legitimate
    version semantics outside these custom control-plane documents.
    """
    rel = path.relative_to(ROOT).as_posix()
    if path.suffix not in {".yaml", ".yml", ".json"}:
        return False
    return (
        rel.startswith("quwoquan_data/control_plane/_shared/catalogs/")
        or rel.startswith("quwoquan_data/control_plane/_shared/routing/")
        or rel.startswith("quwoquan_service/runtime/reliabletask/resources/")
        or rel.startswith("quwoquan_ops/policies/gates/")
        or (
            rel.startswith("quwoquan_service/services/")
            and "/observability/slo/" in rel
        )
        or rel.endswith(
            "/recommendation_model_release/infrastructure/model_runtime/scripts/feature_registry.yaml"
        )
    )


def _custom_control_version_fields(
    value: object,
    prefix: str = "",
) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            field_path = f"{prefix}.{key}" if prefix else key
            if key in CUSTOM_CONTROL_VERSION_FIELDS:
                findings.append((field_path, key))
            findings.extend(_custom_control_version_fields(child, field_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            field_path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            findings.extend(_custom_control_version_fields(child, field_path))
    return findings


def is_contract_yaml(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if path.suffix not in {".yaml", ".yml"}:
        return False
    return rel.startswith("quwoquan_service/contracts/") or (
        rel.startswith("quwoquan_service/") and "/contracts/" in rel
    )


def is_external_grafana_dashboard_schema(rel: str, field_name: str) -> bool:
    """Grafana dashboard schemaVersion belongs to the external JSON format."""
    return (
        field_name == "schemaVersion"
        and rel.startswith(
            "quwoquan_ops/observability/monitoring/dashboards/"
        )
    )


def _is_comment_line(line: str, suffix: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if suffix in {".go", ".dart", ".js", ".ts"} and stripped.startswith("//"):
        return True
    if suffix == ".py" and stripped.startswith("#"):
        return True
    return False


def _is_persistence_go_path(rel: str) -> bool:
    return (
        "/infrastructure/" in rel
        or "/persistence/" in rel
        or "/runtime/search/es/" in rel
    )


def _is_mongo_seed_scenario(rel: str) -> bool:
    # 仅 _id 的 Mongo seed 可保留；双键由 T7 另拦
    return "/scenarios/" in rel and rel.endswith(".json")


def _is_test_path(rel: str) -> bool:
    return (
        "/test/" in rel
        or "/tests/" in rel
        or rel.endswith("_test.go")
        or rel.endswith("_test.dart")
        or rel.endswith("_test.py")
        or "__local_contract_test" in rel
        or "__api_integration_test" in rel
    )


def _is_elasticsearch_bulk_metadata_context(
    rel: str, lines: list[str], line_number: int
) -> bool:
    """Allow provider-owned Bulk API `_id`, never an App/HTTP DTO `_id`."""
    if not _is_test_path(rel) or "elasticsearch" not in Path(rel).name.lower():
        return False
    start = max(0, line_number - 8)
    end = min(len(lines), line_number + 8)
    context = "\n".join(lines[start:end])
    return 'json:"_index"' in context and 'json:"index"' in context


def _is_governance_scanner(rel: str) -> bool:
    """Separate policy implementation from runtime contract sources."""
    path = Path(rel)
    return (
        rel.startswith("quwoquan_ops/gate/")
        or "/scripts/verify/" in rel
        or ("/scripts/" in rel and path.name.startswith("verify_"))
    )


def _is_governance_test(rel: str) -> bool:
    return _is_test_path(rel) and "single_track_contracts" in Path(rel).name


def _is_rejection_context(lines: list[str], line_number: int) -> bool:
    start = max(0, line_number - 12)
    end = min(len(lines), line_number + 12)
    context = "\n".join(lines[start:end])
    return bool(
        re.search(
            r"reject|拒绝|forbidden|不得|禁止|旧|retired|退休|must not|must be rejected|"
            r"invalid|bad request|unknown field|fails closed|"
            r"not in |isdisjoint|does not contain|must not contain|never accepts",
            context,
            re.I,
        )
    )


def _is_sha256_algorithm_identity(lines: list[str], line_number: int) -> bool:
    """Allow named hash algorithms, never an ordinary digest-valued field."""
    start = max(0, line_number - 2)
    end = min(len(lines), line_number + 2)
    context = "\n".join(lines[start:end])
    return bool(SHA256_ALGORITHM_IDENTITY_CONTEXT.search(context))


def _is_sha256_documentation_placeholder(
    rel: str,
    lines: list[str],
    line_number: int,
    value: str,
) -> bool:
    """Allow the exact ellipsis syntax only when it documents a value shape."""
    if value != "sha256:...":
        return False
    line = lines[line_number - 1]
    suffix = Path(rel).suffix.lower()
    if suffix in {".md", ".mdx"}:
        return "`" in line or "@sha256:..." in line
    return bool(
        re.search(
            r"\b(?:help|usage|example|format)\b|\u9884\u671f|\u683c\u5f0f|\u4f8b\u5982|\u5f62\u5982|@sha256:\.\.\.",
            line,
            re.I,
        )
    )


def _is_explicit_sha256_negative_fixture(
    rel: str,
    lines: list[str],
    line_number: int,
) -> bool:
    if not _is_test_path(rel):
        return False
    line = lines[line_number - 1]
    if EXPLICIT_INVALID_SHA256_FIXTURE.search(line):
        return _is_rejection_context(lines, line_number)
    start = max(0, line_number - 10)
    end = min(len(lines), line_number + 20)
    context = "\n".join(lines[start:end])
    return bool(
        SHA256_NEGATIVE_FIXTURE_CONTEXT.search(context)
        and SHA256_REJECTION_ASSERTION.search(context)
    )


def _is_canonical_concatenated_sha256(
    lines: list[str],
    line_number: int,
) -> bool:
    """Recognize a canonical digest split across adjacent source literals."""
    context = "\n".join(lines[line_number - 1 : line_number + 4])
    string_parts = re.findall(r"[\"']([^\"']*)[\"']", context)
    for index, part in enumerate(string_parts):
        if "sha256:" not in part:
            continue
        candidate = part[part.index("sha256:") :]
        for continuation in string_parts[index + 1 :]:
            if not re.fullmatch(r"[0-9a-f]+", continuation):
                break
            candidate += continuation
            if CANONICAL_SHA256_DIGEST.fullmatch(candidate):
                return True
            if len(candidate) > len("sha256:") + 64:
                break
    return False


def _is_external_provider_path(rel: str) -> bool:
    """External wire revisions belong to the provider anticorruption boundary."""
    parts = set(Path(rel).parts)
    return bool(
        parts
        & {
            "external",
            "provider",
            "providers",
            "third_party",
            "third-party",
            "vendor",
        }
    )


def _retired_domain_identity_applies(
    scope: str,
    rel: str,
    lines: list[str],
    line_number: int,
) -> bool:
    """Match retired fields only inside the first-party object that retired them."""
    if _is_external_provider_path(rel):
        return False
    start = max(0, line_number - 16)
    end = min(len(lines), line_number + 16)
    context = "\n".join(lines[start:end]).lower()
    rel_lower = rel.lower()

    if scope == "assistant_policy_release":
        return (
            rel_lower.startswith(
                "quwoquan_service/services/assistant-service/"
            )
            or rel_lower.startswith(
                "specs/feature-tree/assistant-run-learning/"
            )
            or (
                rel_lower.startswith("quwoquan_app/")
                and "/assistant/" in rel_lower
            )
            or "assistantpolicyrelease" in context
            or "assistant_policy_release" in context
        )
    if scope == "product_ops_experiment_assignment":
        return (
            rel_lower.startswith(
                "quwoquan_service/services/product-ops-service/"
            )
            or rel_lower.startswith(
                "specs/feature-tree/product-operations/"
            )
            or "experimentassignmentfact" in context
            or "experiment_assignment_fact" in context
        )
    if scope == "recommendation_content_identity":
        return (
            rel_lower.startswith(
                "quwoquan_service/services/recommendation-service/"
            )
            or rel_lower.startswith("quwoquan_service/runtime/recommendation/")
            or rel_lower.startswith("quwoquan_service/runtime/recpolicy/")
            or (
                rel_lower.startswith("quwoquan_app/")
                and "recommendation" in rel_lower
            )
            or (
                rel_lower.startswith("specs/feature-tree/")
                and "recommend" in rel_lower
            )
            or rel_lower.endswith("/l3_rec_model.json")
            or "recommendationmodelexposure" in context
            or "recommendationexposurefact" in context
            or "recommendationmodelrelease" in context
            or "recommendation_model_release" in context
            or "rankedfeedwindow" in context
        )
    if scope == "assistant_learning_fact":
        return (
            "assistant_learning_fact" in rel_lower
            or "/assistant/learning/" in rel_lower
            or rel_lower.startswith(
                "specs/feature-tree/assistant-run-learning/"
                "learning-event-feedback-injection/"
            )
            or "assistantlearningfact" in context
            or "assistant_learning_fact" in context
        )
    return False


def _json_object_has_dual_id(obj: object) -> bool:
    if isinstance(obj, dict):
        if "_id" in obj and "id" in obj:
            return True
        return any(_json_object_has_dual_id(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_json_object_has_dual_id(v) for v in obj)
    return False


def scan_file(path: Path, inv: Inventory) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    rel = path.relative_to(ROOT).as_posix()
    suffix = path.suffix
    if _is_governance_scanner(rel) or _is_governance_test(rel):
        return
    lines = text.splitlines()
    in_custom_control = is_custom_control_document(path)

    for identity_name, pattern, canonical in FROZEN_IDENTITY_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if value == canonical:
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_mutated_frozen_identity",
                path,
                f"L{line_number}: {identity_name}={value}; canonical={canonical}",
            )

    for match in RETIRED_CUSTOM_IDENTITY.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        inv.add(
            "T1_retired_custom_identity",
            path,
            f"L{line_number}: {match.group(0)}",
        )

    for match in RETIRED_USER_IDENTITY.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_test_path(rel) and _is_rejection_context(lines, line_number):
            continue
        inv.add(
            "T1_retired_user_identity",
            path,
            f"L{line_number}: {match.group(0).strip()}",
        )

    retired_search_recommendation_lines: set[int] = set()
    for match in RETIRED_SEARCH_RECOMMENDATION_IDENTITY.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if line_number in retired_search_recommendation_lines:
            continue
        if _is_rejection_context(lines, line_number):
            continue
        retired_search_recommendation_lines.add(line_number)
        inv.add(
            "T1_retired_search_recommendation_identity",
            path,
            f"L{line_number}: {match.group(0)}",
        )

    if rel.startswith("quwoquan_service/runtime/persona/"):
        for match in RETIRED_PERSONA_MIGRATION_TYPE.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_retired_persona_migration_type",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel in RUNTIME_ERROR_SINGLE_TRACK_PATHS:
        for match in RETIRED_RUNTIME_ERROR_MESSAGE_ALIAS.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T3_runtime_error_message_alias",
                path,
                f"L{line_number}: {match.group(0).strip()}",
            )

    retired_domain_lines: set[tuple[str, int]] = set()
    for scope, pattern in RETIRED_DOMAIN_IDENTITY_FIELDS:
        for match in pattern.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            key = (scope, line_number)
            if key in retired_domain_lines:
                continue
            if _is_rejection_context(lines, line_number):
                continue
            if not _retired_domain_identity_applies(
                scope,
                rel,
                lines,
                line_number,
            ):
                continue
            retired_domain_lines.add(key)
            inv.add(
                "T1_retired_domain_identity_field",
                path,
                f"L{line_number}: {scope}: {match.group(0)}",
            )

    if suffix in {".go", ".dart", ".py", ".yaml", ".yml", ".json"}:
        for match in POLICY_DIGEST_LITERAL_ASSIGNMENT.finditer(text):
            value = match.group("value")
            if value in {"", "unknown"} or CANONICAL_SHA256_DIGEST.fullmatch(value):
                continue
            if re.match(r"\s*\+", text[match.end() : match.end() + 8]):
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_noncanonical_policy_digest_literal",
                path,
                f"L{line_number}: {value}",
            )

    for match in SHA256_LITERAL.finditer(text):
        value = match.group(0)
        if CANONICAL_SHA256_DIGEST.fullmatch(value):
            continue
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_sha256_algorithm_identity(lines, line_number):
            continue
        if _is_sha256_documentation_placeholder(rel, lines, line_number, value):
            continue
        if _is_explicit_sha256_negative_fixture(rel, lines, line_number):
            continue
        if _is_canonical_concatenated_sha256(lines, line_number):
            continue
        inv.add(
            "T1_noncanonical_sha256_literal",
            path,
            f"L{line_number}: {value}",
        )

    if rel == "quwoquan_ops/cli/lib/mock_public_plane.py":
        for match in RETIRED_MOCK_EXPERIMENT_RUNTIME.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T1_mock_experiment_second_runtime",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel == "quwoquan_app/lib/app/navigation/app_router.dart":
        for match in RETIRED_CREATE_ROUTE_EXTRA.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T3_create_route_extra_compat",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel.startswith("quwoquan_app/lib/"):
        for match in RETIRED_CLIENT_STATE_SYNC_DERIVED_FIELD.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_client_state_sync_second_truth",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel in {
        "quwoquan_service/services/chat-service/internal/chat/conversation/application/message_service.go",
        "quwoquan_service/services/chat-service/internal/chat/conversation/application/rtc_call_log_projector.go",
    }:
        for match in RETIRED_MESSAGE_EVENT_ID_SEGMENT.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T1_versioned_event_identity",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel == "quwoquan_service/services/circle-service/internal/circle_management/circle/application/circle_service.go":
        for match in RETIRED_CIRCLE_SNAPSHOT_SEGMENT.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T1_versioned_snapshot_identity",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel == "quwoquan_service/services/content-service/cmd/api/main_feed_quota_runtime.go":
        for match in RETIRED_QUOTA_LOG_VERSION.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T1_versioned_observability_dimension",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel.startswith("quwoquan_ops/observability/"):
        for match in RETIRED_QUOTA_SHARD_VERSION.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_versioned_observability_dimension",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel in {
        "quwoquan_service/runtime/media/group_avatar_service.go",
        "quwoquan_service/services/chat-service/internal/chat/conversation/application/group_avatar_support.go",
    }:
        for match in RETIRED_GROUP_AVATAR_LAYOUT.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T1_versioned_layout_identity",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel in APP_REMOTE_CONFIG_SINGLE_IDENTITY_PATHS:
        for match in FORBIDDEN_APP_REMOTE_CONFIG_PACKAGE_VERSION.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_remote_config_dual_identity",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if in_custom_control:
        try:
            if suffix == ".json":
                control_document = json.loads(text)
            else:
                control_document = yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError) as error:
            detail = str(error).splitlines()[0][:140]
            inv.add("T1_custom_control_parse_error", path, detail)
        else:
            for field_path, field_name in _custom_control_version_fields(
                control_document
            ):
                inv.add(
                    "T1_custom_control_version_field",
                    path,
                    f"{field_path}: {field_name}",
                )

    for pattern in PUBLIC_IDENTITY_RETIRED_PATTERNS:
        for match in pattern.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T8_public_identity_alias",
                path,
                f"L{line_number}: {match.group(0)}",
            )

    if rel == "quwoquan_app/lib/core/models/user_models.dart":
        for pattern in PUBLIC_USER_MODEL_RETIRED_PATTERNS:
            for match in pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                if _is_rejection_context(lines, line_number):
                    continue
                inv.add(
                    "T8_public_identity_alias",
                    path,
                    f"L{line_number}: {match.group(0)}",
                )

    if is_metadata_object_yaml(path) and TOP_LEVEL_VERSION.search(text):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.match(r"^version:\s*", line):
                inv.add("T1_metadata_top_level_version", path, f"L{lineno}: {line.strip()}")
                break

    if suffix in {".yaml", ".yml"}:
        in_contract = is_contract_yaml(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if in_contract and (
                ALIASES_LINE.search(line) or re.search(r"^\s*-\s*aliases\s*:", line)
            ):
                inv.add("T2_metadata_aliases", path, f"L{lineno}: {line.strip()}")
            if in_contract and SKIP_EMPTY_ALIASES.search(line):
                inv.add("T2_skip_empty_string_aliases", path, f"L{lineno}: {line.strip()}")
            if in_contract and AUTH_REQUIRED_LINE.search(line):
                inv.add("T4_auth_required", path, f"L{lineno}: {line.strip()}")
            if (
                in_contract
                and CONTRACT_COMPAT_ALIAS.search(line)
                and not re.search(r"(?:零|无|禁止|不得|不保留)兼容别名", line)
            ):
                inv.add(
                    "T2_contract_compat_alias",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )

    for field_name in FORBIDDEN_ENVELOPE_FIELDS:
        if is_external_grafana_dashboard_schema(rel, field_name):
            continue
        if in_custom_control and field_name in CUSTOM_CONTROL_VERSION_FIELDS:
            # Custom control documents are parsed structurally above so nested
            # YAML/JSON keys produce one precise finding instead of duplicates.
            continue
        if field_name not in text:
            continue
        # 军规 / 规格中列举禁词（禁止 schemaVersion 等）不计违规
        if suffix in {".md", ".mdc"} and (
            "禁止" in text
            or "forbidden" in text.lower()
            or "retired" in text.lower()
            or "GATE_BLOCK" in text
        ):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if field_name not in line:
                continue
            if _is_comment_line(line, suffix):
                continue
            if _is_rejection_context(lines, lineno):
                continue
            if re.search(rf"\b{field_name}\b", line):
                inv.add("T1_forbidden_envelope_field", path, f"L{lineno}: {field_name}")

    for match in VERSIONED_INLINE.finditer(text):
        value = match.group(0)
        if "/posts/" in value or "posts/article" in value:
            continue
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        inv.add("T1_versioned_schema_identity", path, value)

    for match in SCHEMA_VALUE_V_SUFFIX.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        value = match.group("value")
        if not VERSIONED_SCHEMA_VALUE.search(value):
            continue
        inv.add("T1_versioned_schema_identity", path, value)

    if suffix in {
        ".go",
        ".dart",
        ".java",
        ".kt",
        ".swift",
        ".yaml",
        ".yml",
        ".json",
    }:
        for match in VERSIONED_LOCAL_IDENTITY_LITERAL.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if match.group("value") in FROZEN_VERSIONED_LOCAL_IDENTITIES:
                continue
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_versioned_local_identity",
                path,
                f"L{line_number}: {match.group('value')}",
            )

    if suffix == ".dart":
        for match in VERSIONED_INTERPOLATED_QUEUE_IDENTITY.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_versioned_local_identity",
                path,
                f"L{line_number}: {match.group('value')}",
            )

    if suffix in {".go", ".dart", ".py", ".sh", ".yaml", ".yml", ".json"}:
        for match in VERSIONED_MIGRATION_IDENTITY.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            if _is_rejection_context(lines, line_number):
                continue
            inv.add(
                "T1_versioned_migration_identity",
                path,
                f"L{line_number}: {match.group('value')}",
            )

    for match in NUMERIC_SCHEMA_LITERAL.finditer(text):
        line_number = text.count("\n", 0, match.start()) + 1
        if _is_rejection_context(lines, line_number):
            continue
        inv.add("T1_numeric_schema_identity", path, match.group(0))

    if OPTIONAL_ALIAS_HELPER.search(text):
        inv.add("T3_alias_helper", path, "alias helper symbol")

    # 多键解码：Dart / Go 全量（含手写 lib / generated），同标识符且键名不同才计
    if suffix in {".dart", ".go"}:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            for match in MULTI_KEY_DECODE.finditer(line):
                if match.group("k1") == match.group("k2"):
                    continue
                inv.add(
                    "T3_multi_key_decode",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )
            if MULTI_KEY_GO_TEMPLATE.search(line):
                inv.add(
                    "T3_multi_key_decode",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )

    # specs / 军规：禁止再教短期双读或协议版本身份（同行含「禁止」则放过）
    if suffix in {".md", ".mdc"} and (
        rel.startswith("specs/")
        or rel.startswith(".cursor/rules/")
        or rel.startswith("quwoquan_service/contracts/")
    ):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not DOC_DUAL_TRACK_TEACHING.search(line):
                continue
            if re.search(r"禁止|不得|GATE_BLOCK|已删除|不得保留", line):
                continue
            inv.add(
                "T5_doc_dual_track_teaching",
                path,
                f"L{lineno}: {line.strip()[:140]}",
            )

    if suffix == ".dart" and (
        "mapListFirstPresent" in text or "mapListFirstNonEmpty" in text
    ):
        if "/lib/" in rel.replace("\\", "/"):
            inv.add(
                "T3_map_list_first_present",
                path,
                "mapListFirstPresent/mapListFirstNonEmpty forbidden in lib",
            )
        else:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "mapListFirstPresent" in line or "mapListFirstNonEmpty" in line:
                    window = "\n".join(text.splitlines()[lineno - 1 : lineno + 6])
                    keys = re.findall(r"'([A-Za-z0-9_]+)'", window)
                    if len(keys) >= 2:
                        inv.add(
                            "T3_map_list_first_present",
                            path,
                            f"L{lineno}: multi-key {keys}",
                        )

    for pattern in COMPAT_SMELLS:
        for lineno, line in enumerate(lines, start=1):
            if _is_comment_line(line, suffix):
                continue
            if not pattern.search(line):
                continue
            if _is_rejection_context(lines, lineno):
                continue
            # 军规/规格中「禁止 dual-read / 逃逸」等否定句不计为气味
            if re.search(
                r"禁止|不得|不保留|无\s*dual|删除|GATE_BLOCK|must not|forbidden|逃逸|阻断",
                line,
                re.I,
            ):
                continue
            if rel.startswith(".cursor/rules/") or rel.startswith("specs/"):
                # 规则清单里出现 mode=compat 等禁词本身即治理文案
                continue
            inv.add("T4_compat_smell", path, f"L{lineno}: {line.strip()[:120]}")

    # 正向 alias 测试语义
    if "test" in rel and suffix in {".dart", ".go", ".py"}:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if POSITIVE_ALIAS_TEST.search(line):
                # 同行若已含 rejects/拒绝 则放过
                if re.search(r"reject|拒绝|forbidden|不得|must not", line, re.I):
                    continue
                inv.add(
                    "T6_positive_alias_test",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )

    # T3_wire_id_key：客户端 wire 禁止 _id JSON 键
    if suffix == ".dart" and (
        "/lib/" in rel
        or "/packages/" in rel
        or "/generated/" in rel
        or _is_test_path(rel)
    ):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            if not DART_WIRE_ID_KEY.search(line) and "['_id']" not in line and '["_id"]' not in line:
                continue
            if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                continue
            # 测试夹具里用 _id 证明拒绝
            if _is_test_path(rel) and (
                "拒绝 _id" in text
                or "rejects _id" in text
                or "reject _id" in text.lower()
                or "rejects aggregate storage" in text
            ):
                if re.search(
                    r"""['\"]_id['\"]\s*:|\[['\"]_id['\"]\]\s*=""",
                    line,
                ):
                    continue
            inv.add("T3_wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")

    if suffix == ".go" and not _is_persistence_go_path(rel):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            if GO_BSON_ID_TAG.search(line) and not GO_JSON_ID_TAG.search(line):
                continue
            if GO_JSON_ID_TAG.search(line):
                if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                    continue
                if _is_elasticsearch_bulk_metadata_context(rel, lines, lineno):
                    continue
                inv.add("T3_wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")
                continue
            # map 出站 "_id":
            if GO_MAP_ID_KEY.search(line) and (
                "/adapters/" in rel
                or "/application/" in rel
                or "/domain/" in rel
                or "/generated/" in rel
            ):
                if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                    continue
                inv.add("T3_wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")

    # T3_multi_key_helper：_firstNonEmpty(..., '_id', ...)
    if suffix in {".dart", ".go"} and MULTI_KEY_HELPER_ID.search(text):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "_firstNonEmpty" in line or "mapListFirstPresent" in line or "mapListFirstNonEmpty" in line:
                if "'_id'" in line or '"_id"' in line:
                    inv.add(
                        "T3_multi_key_helper",
                        path,
                        f"L{lineno}: {line.strip()[:140]}",
                    )

    # T5：metadata 正向 _id/id 兼容教学
    if rel.startswith("quwoquan_service/contracts/metadata/") and suffix in {
        ".yaml",
        ".yml",
        ".md",
    }:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not ID_COMPAT_TEACHING.search(line):
                continue
            if re.search(r"禁止|不得|reject|拒绝|GATE_BLOCK", line, re.I):
                continue
            # source: _id 存储投影合法，不在此拦
            if re.search(r"^\s*source:\s*_id\s*$", line):
                continue
            inv.add(
                "T5_id_compat_teaching",
                path,
                f"L{lineno}: {line.strip()[:140]}",
            )

    # T7：fixture 同对象同时含 _id 与 id
    if suffix == ".json" and (
        "/test_fixtures/" in rel
        or "/fixtures/" in rel
        or (rel.startswith("quwoquan_app/assets/") and "fixture" in rel.lower())
        or _is_mongo_seed_scenario(rel)
    ):
        # scenarios 仅当双键并存才拦（纯 Mongo seed 只有 _id 放过）
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None and _json_object_has_dual_id(data):
            inv.add(
                "T7_fixture_dual_id",
                path,
                "JSON object contains both _id and id keys",
            )


def write_inventory(inv: Inventory, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Single-track contract inventory",
        "",
        "## Counts",
        "",
    ]
    for key in sorted(inv.counts):
        lines.append(f"- {key}: {inv.counts[key]}")
    lines.extend(["", "## Findings", ""])
    by_cat: dict[str, list[Finding]] = defaultdict(list)
    for finding in inv.findings:
        by_cat[finding.category].append(finding)
    for cat in sorted(by_cat):
        lines.append(f"### {cat}")
        lines.append("")
        for item in by_cat[cat][:200]:
            lines.append(f"- `{item.path}`: {item.detail}")
        if len(by_cat[cat]) > 200:
            lines.append(f"- ... {len(by_cat[cat]) - 200} more")
        lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "counts": dict(inv.counts),
        "total": sum(inv.counts.values()),
    }
    summary_path = out_path.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inventory-out",
        default=str(
            ROOT / ".qwq_output/env/repo/runs/single-track-inventory.md"
        ),
    )
    args = parser.parse_args()

    inv = Inventory()
    for path in iter_files():
        scan_file(path, inv)
    scan_versioned_golden_assets(inv)

    out_path = Path(args.inventory_out)
    write_inventory(inv, out_path)

    total = sum(inv.counts.values())
    print(
        f"[single-track] inventory={out_path.relative_to(ROOT).as_posix()} "
        f"total_findings={total}"
    )
    for key in sorted(inv.counts):
        print(f"  {key}: {inv.counts[key]}")

    if total == 0:
        print("[single-track] OK: zero dual-track / versioned-contract findings")
        return 0

    print("[single-track] FAIL: dual-track or versioned-contract residue remains", file=sys.stderr)
    for finding in inv.findings[:40]:
        print(f"  {finding.category}: {finding.path}: {finding.detail}", file=sys.stderr)
    if total > 40:
        print(f"  ... {total - 40} more (see inventory)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
