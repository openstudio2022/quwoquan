"""Inventory、扫描文件枚举与 `scan_file` 主扫描流程。

本模块的 ``ROOT`` 是模块级全局：contract 测试通过替换本模块的 ``ROOT``
把扫描根指向临时 fixture 树，因此消费 ``ROOT`` 的函数必须留在本模块内。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .constants import (
    ALIASES_LINE,
    APP_REMOTE_CONFIG_SINGLE_IDENTITY_PATHS,
    APP_ROUTER_SINGLE_TRACK_PATH,
    AUTH_REQUIRED_LINE,
    CANONICAL_SHA256_DIGEST,
    COMPAT_SMELLS,
    CONTRACT_COMPAT_ALIAS,
    CUSTOM_CONTROL_VERSION_FIELDS,
    DART_WIRE_ID_KEY,
    DOC_DUAL_TRACK_TEACHING,
    FORBIDDEN_APP_REMOTE_CONFIG_PACKAGE_VERSION,
    FORBIDDEN_ENVELOPE_FIELDS,
    FROZEN_IDENTITY_PATTERNS,
    FROZEN_VERSIONED_LOCAL_IDENTITIES,
    GO_BSON_ID_TAG,
    GO_BSON_MAP_ID_KEY,
    GO_JSON_ID_TAG,
    GO_MAP_ID_KEY,
    ID_COMPAT_TEACHING,
    IMMUTABLE_EVIDENCE_SCHEMA_PATHS,
    MULTI_KEY_DECODE,
    MULTI_KEY_GO_TEMPLATE,
    MULTI_KEY_HELPER_ID,
    NEGATIVE_ID_TEST_LINE,
    NUMERIC_SCHEMA_LITERAL,
    OPTIONAL_ALIAS_HELPER,
    POLICY_DIGEST_LITERAL_ASSIGNMENT,
    POSITIVE_ALIAS_TEST,
    PUBLIC_IDENTITY_RETIRED_PATTERNS,
    PUBLIC_USER_MODEL_RETIRED_PATTERNS,
    PUBLIC_USER_MODEL_SINGLE_TRACK_ROOT,
    RETIRED_CIRCLE_SNAPSHOT_SEGMENT,
    RETIRED_CLIENT_STATE_SYNC_DERIVED_FIELD,
    RETIRED_CREATE_ROUTE_EXTRA,
    RETIRED_CUSTOM_IDENTITY,
    RETIRED_DOMAIN_IDENTITY_FIELDS,
    RETIRED_GROUP_AVATAR_LAYOUT,
    RETIRED_MESSAGE_EVENT_ID_SEGMENT,
    RETIRED_MOCK_EXPERIMENT_RUNTIME,
    RETIRED_PERSONA_MIGRATION_TYPE,
    RETIRED_QUOTA_LOG_VERSION,
    RETIRED_QUOTA_SHARD_VERSION,
    RETIRED_RUNTIME_ERROR_MESSAGE_ALIAS,
    RETIRED_SEARCH_RECOMMENDATION_IDENTITY,
    RETIRED_USER_IDENTITY,
    ROOT,
    RUNTIME_ERROR_SINGLE_TRACK_PATHS,
    SCAN_ROOTS,
    SCHEMA_VALUE_V_SUFFIX,
    SHA256_LITERAL,
    SINGLE_TRACK_BASELINE_PATH,
    SINGLE_TRACK_BASELINE_SCHEMA,
    SKIP_DIR_NAMES,
    SKIP_EMPTY_ALIASES,
    SOURCE_KEYS_ALIAS_LINE,
    TEXT_SUFFIXES,
    TOP_LEVEL_VERSION,
    VERSIONED_GOLDEN_ASSET_NAME,
    VERSIONED_INLINE,
    VERSIONED_INTERPOLATED_QUEUE_IDENTITY,
    VERSIONED_LOCAL_IDENTITY_LITERAL,
    VERSIONED_MIGRATION_IDENTITY,
    VERSIONED_SCHEMA_VALUE,
)
from .heuristics import (
    _custom_control_version_fields,
    _is_canonical_concatenated_sha256,
    _is_comment_line,
    _is_elasticsearch_bulk_metadata_context,
    _is_explicit_sha256_negative_fixture,
    _is_governance_scanner,
    _is_governance_test,
    _is_mongo_seed_scenario,
    _is_persistence_go_path,
    _is_rejection_context,
    _is_sha256_algorithm_identity,
    _is_sha256_documentation_placeholder,
    _is_test_path,
    _json_object_has_dual_id,
    is_external_grafana_dashboard_schema,
)
from .ownership import _retired_domain_identity_applies


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
    if parts & SKIP_DIR_NAMES:
        return True
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return relative == SINGLE_TRACK_BASELINE_PATH


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


def is_contract_yaml(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if path.suffix not in {".yaml", ".yml"}:
        return False
    return rel.startswith("quwoquan_service/contracts/") or (
        rel.startswith("quwoquan_service/") and "/contracts/" in rel
    )


def _is_immutable_evidence_schema(rel: str, value: str) -> bool:
    """只允许 canonical persisted evidence 在登记的 exact path 使用。"""
    return rel in IMMUTABLE_EVIDENCE_SCHEMA_PATHS.get(value, ())


def scan_file(path: Path, inv: Inventory) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    rel = path.relative_to(ROOT).as_posix()
    suffix = path.suffix
    if _is_governance_scanner(rel) or _is_governance_test(rel):
        return
    # This gate's own exact debt ledger quotes the forbidden semantic values it
    # tracks. Its fixed schema/location is parsed fail-closed by baseline.py and
    # governed separately; treating quoted evidence as a runtime contract would
    # recursively manufacture findings from the baseline itself.
    if rel == SINGLE_TRACK_BASELINE_PATH and suffix == ".json":
        try:
            baseline_document = json.loads(text)
        except json.JSONDecodeError:
            baseline_document = None
        if (
            isinstance(baseline_document, dict)
            and baseline_document.get("schema") == SINGLE_TRACK_BASELINE_SCHEMA
            and isinstance(baseline_document.get("findings"), list)
        ):
            return
    lines = text.splitlines()
    in_custom_control = is_custom_control_document(path)

    # Contract fields have one canonical source. ``source_keys`` encodes an
    # ordered fallback list and therefore revives wire dual-read even when the
    # runtime decoder is generated later. Storage/BSON aliases belong in the
    # persistence adapter, never in an App/API projection contract.
    if is_contract_yaml(path):
        for match in SOURCE_KEYS_ALIAS_LINE.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "T1_contract_source_keys_alias",
                path,
                f"L{line_number}: source_keys is forbidden; declare one canonical source",
            )

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
                "runtime_error_message_alias",
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
            if not _retired_domain_identity_applies(scope, rel):
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

    if rel == APP_ROUTER_SINGLE_TRACK_PATH:
        for match in RETIRED_CREATE_ROUTE_EXTRA.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            inv.add(
                "create_route_extra_compat",
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

    if rel.startswith(PUBLIC_USER_MODEL_SINGLE_TRACK_ROOT):
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
                inv.add("auth_required", path, f"L{lineno}: {line.strip()}")
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
        if _is_immutable_evidence_schema(rel, value):
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
        if _is_immutable_evidence_schema(rel, value):
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
        inv.add("alias_helper", path, "alias helper symbol")

    # 多键解码：Dart / Go 全量（含手写 lib / generated），同标识符且键名不同才计
    if suffix in {".dart", ".go"}:
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line, suffix):
                continue
            for match in MULTI_KEY_DECODE.finditer(line):
                if match.group("k1") == match.group("k2"):
                    continue
                inv.add(
                    "multi_key_decode",
                    path,
                    f"L{lineno}: {line.strip()[:140]}",
                )
            if MULTI_KEY_GO_TEMPLATE.search(line):
                inv.add(
                    "multi_key_decode",
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
                "map_list_first_present",
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
                            "map_list_first_present",
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
            inv.add("compat_smell", path, f"L{lineno}: {line.strip()[:120]}")

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

    # wire_id_key：客户端 wire 禁止 _id JSON 键
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
            inv.add("wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")

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
                inv.add("wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")
                continue
            # map 出站 "_id":
            if GO_MAP_ID_KEY.search(line) and (
                "/adapters/" in rel
                or "/application/" in rel
                or "/domain/" in rel
                or "/generated/" in rel
            ):
                if GO_BSON_MAP_ID_KEY.search(line):
                    continue
                if _is_test_path(rel) and NEGATIVE_ID_TEST_LINE.search(line):
                    continue
                inv.add("wire_id_key", path, f"L{lineno}: {line.strip()[:140]}")

    # multi_key_helper：_firstNonEmpty(..., '_id', ...)
    if suffix in {".dart", ".go"} and MULTI_KEY_HELPER_ID.search(text):
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "_firstNonEmpty" in line or "mapListFirstPresent" in line or "mapListFirstNonEmpty" in line:
                if "'_id'" in line or '"_id"' in line:
                    inv.add(
                        "multi_key_helper",
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
