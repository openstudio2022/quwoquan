"""`object_path_map.py` 派生规则的本地契约（claim / alias / layer 派生规则组）。

本测试锁定的是「派生规则」本身，而不是某次扫描的具体数字：规则会被后续 16 条
domain 并行流与 W5 的 Go evidence loader 共同消费，任何静默改动都会让并行流对
对象归属产生分歧。

这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`：该 GWT 还需要统一门禁与
三层证据闭环才算达成，本工具只提供其中的路径反推部分，不代表 OPEN-001 关闭。

由 1000 行硬顶拆分：object view/baseline 组见
test_object_path_map__object_view__local_contract_test.py，派生幂等组见
test_object_path_map__idempotence__local_contract_test.py，共享 `roster`
fixture 下沉 conftest.py。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm


def test_cloud_kind_rule_stays_mirrored_with_the_service_architecture_gate() -> None:
    assert opm.check_cloud_layer_rule_mirror() == []


def test_cloud_identity_is_reversed_from_path_without_heuristics() -> None:
    assert opm.derive_cloud_source_identity(
        ("chat", "conversation", "application", "facade.go")
    ) == ("chat", "conversation", "application")
    # 层名不在 CLOUD_LAYERS 内时必须拒绝反推，而不是猜一个层。
    assert (
        opm.derive_cloud_source_identity(
            ("chat", "conversation", "helpers", "facade.go")
        )
        is None
    )
    assert opm.derive_cloud_test_identity(
        ("local_contract", "chat", "conversation", "x_test.go")
    ) == ("local_contract", "chat", "conversation")
    assert opm.derive_cloud_test_identity(("support", "real_mongo.go")) is None


def test_object_aliases_only_trim_domain_prefix_and_declared_suffixes() -> None:
    aliases = dict(opm.object_aliases("circle", "circle_behavior_fact"))

    assert aliases["circle_behavior_fact"] == "canonical"
    assert aliases["behavior_fact"] == "domain_trimmed"
    assert aliases["behavior"] == "suffix_trimmed"
    # 未登记的裁剪方式不得产生别名。
    assert "circle_behavior" not in aliases or aliases["circle_behavior"] == "suffix_trimmed"
    assert "fact" not in aliases


def test_object_aliases_also_derive_the_domain_qualified_form() -> None:
    """端侧文件名普遍用 `<domain>_` 限定通用对象名，是 `domain_trimmed` 的逆变换。"""
    aliases = dict(opm.object_aliases("content", "post"))

    assert aliases["post"] == "canonical"
    assert aliases["content_post"] == "domain_prefixed"

    # 对象名已自带 domain 前缀时不得再套一层。
    prefixed = dict(opm.object_aliases("circle", "circle_membership"))
    assert "circle_circle_membership" not in prefixed
    # 对象名与 domain 同名时同样不套壳。
    assert "circle_circle" not in dict(opm.object_aliases("circle", "circle"))
    # 别名只由 roster 的 (domain, objectName) 机械派生，不引入人工同义词。
    assert set(dict(opm.object_aliases("content", "outbound_share_fact"))) == {
        "outbound_share_fact",
        "outbound_share",
        "content_outbound_share_fact",
        "content_outbound_share",
    }


def test_canonical_app_target_shape_claims_content_post_detail_payload(
    roster: opm.ObjectRoster,
) -> None:
    """Canonical App object shape owns the post detail payload directly."""
    claim = opm.derive_app_object_claim(
        (
            "service",
            "content_service",
            "content",
            "post",
            "domain",
            "content_post_detail_payload.dart",
        ),
        roster,
        {},
        "quwoquan_app/lib/service/content_service/content/post/domain/"
        "content_post_detail_payload.dart",
    )

    assert claim["method"] == "app_target_shape"
    assert claim["objectIds"] == ["content.post"]
    assert claim["ambiguous"] is False
    assert claim["targetLayer"] == "domain"


def test_domain_qualified_file_name_claims_the_object_when_directories_are_mute(
    roster: opm.ObjectRoster,
) -> None:
    """目录完全不表达作用域时，`<domain>_<object>_*` 文件名是受控的对象级信号。"""
    claim = opm.derive_app_object_claim(
        ("unscoped_models", "content_post_detail_payload.dart"),
        roster,
        {},
        "quwoquan_app/lib/unscoped_models/content_post_detail_payload.dart",
    )

    assert claim["method"] == "filename_object_qualified"
    assert claim["objectIds"] == ["content.post"]
    assert claim["ambiguous"] is False
    # 后缀裁剪出来的别名同样可用，只要文件名仍被 domain 限定。
    fact = opm.derive_app_object_claim(
        ("core", "trackers", "content_behavior_tracker.dart"),
        roster,
        {},
        "quwoquan_app/lib/core/trackers/content_behavior_tracker.dart",
    )
    assert fact["objectIds"] == ["content.content_behavior_fact"]


def test_file_name_alias_without_the_domain_qualifier_is_never_claimed(
    roster: opm.ObjectRoster,
) -> None:
    """裁剪出来的短别名与端侧通用 UI 词汇同形，缺 domain 限定时必须拒绝反推。

    `settings` / `file` / `conversation` 分别来自 `user.user_settings`、
    `circle.circle_file`、`chat.conversation`，但这三个文件都不是对应对象的实现。
    错报比欠报更贵：它会把真横切件推进 domain 树，并让门禁产生假违规。
    """
    for parts in (
        ("components", "settings_form", "settings_form.dart"),
        ("core", "platform", "file_storage_gateway.dart"),
        ("core", "widgets", "conversation_sheet.dart"),
        ("core", "models", "post_models.dart"),
    ):
        claim = opm.derive_app_object_claim(parts, roster, {}, "irrelevant")
        assert claim["objectIds"] == [], parts
        assert claim["method"] == "unowned", parts


def test_file_name_scope_qualifier_requires_the_path_to_express_a_layer(
    roster: opm.ObjectRoster,
) -> None:
    """文件名作用域限定只在现状路径同时表达层角色时成立。"""
    scoped = opm.derive_app_object_claim(
        ("core", "services", "cache", "content_cache_services.dart"),
        roster,
        {},
        "quwoquan_app/lib/core/services/cache/content_cache_services.dart",
    )
    assert scoped["method"] == "context_only"
    assert scoped["contextIds"] == ["content.content"]
    assert scoped["objectIds"] == []

    domain_scoped = opm.derive_app_object_claim(
        ("core", "models", "user_models.dart"),
        roster,
        {},
        "quwoquan_app/lib/core/models/user_models.dart",
    )
    assert domain_scoped["method"] == "domain_only"
    assert domain_scoped["domains"] == ["user"]

    # `constants` / `utils` 不表达层：这里的 domain 名是限定词而非归属，
    # 共享文案与工具必须留在横切面，否则会给真横切件造出反向依赖假违规。
    for parts in (
        ("core", "constants", "chat_text_constants.dart"),
        ("core", "constants", "search_semantic_constants.dart"),
        ("core", "utils", "chat_time_formatter.dart"),
    ):
        claim = opm.derive_app_object_claim(parts, roster, {}, "irrelevant")
        assert claim["method"] == "unowned", parts


def test_composition_root_never_carries_object_identity(
    roster: opm.ObjectRoster,
) -> None:
    """`**/di/**` 是端侧装配点，按定义横跨 domain，文件名不得反推出对象。"""
    assert opm.derive_app_is_composition_root(("core", "di", "x.dart")) is True
    assert opm.derive_app_is_composition_root(("runtime", "di", "x.dart")) is True
    assert opm.derive_app_is_composition_root(("core", "services", "x.dart")) is False

    for parts in (
        ("runtime", "di", "circle_dependencies.dart"),
        ("core", "di", "ops_event_record_dependencies.dart"),
    ):
        claim = opm.derive_app_object_claim(parts, roster, {}, "irrelevant")
        assert claim["objectIds"] == [], parts
        assert claim["method"] == "unowned", parts


def test_composition_root_target_prefix_is_derived_from_the_cross_cutting_root() -> None:
    """组合根前缀必须由横切根 + 组合根段派生，供端侧架构门禁复用同一个定义。"""
    assert opm.APP_COMPOSITION_ROOT_TARGET_PREFIX == (
        f"{opm.APP_CROSS_CUTTING_ROOTS['runtime'].split('/', 1)[1]}/"
        f"{opm.APP_COMPOSITION_ROOT_SEGMENT}/"
    )
    assert opm.APP_COMPOSITION_ROOT_SEGMENT not in opm.APP_LAYER_BY_SEGMENT


def test_file_name_signals_never_override_physical_cross_cutting_placement(
    roster: opm.ObjectRoster,
) -> None:
    """已搬到横切根的文件的结论就是横切面，文件名启发式必须让位（派生幂等）。"""
    for parts in (
        ("runtime", "observability", "content_post_telemetry.dart"),
        ("runtime", "models", "content_cache_services.dart"),
        ("runtime", "transport", "media", "content_media_url.dart"),
        (
            "runtime",
            "platform",
            "media",
            "app_image_cache_controller.dart",
        ),
        ("design_system", "tokens", "content_post_spacing.dart"),
    ):
        claim = opm.derive_app_object_claim(parts, roster, {}, "irrelevant")
        assert claim["objectIds"] == [], parts
        assert claim["method"] == "unowned", parts
        assert opm.derive_app_cross_cutting_shape_root(parts) is not None, parts


def test_runtime_generated_error_catalog_is_cross_cutting(
    roster: opm.ObjectRoster,
) -> None:
    """runtime error catalog 是横切派生物，不反向冒充 circle 领域对象。"""
    parts = (
        "runtime",
        "errors",
        "generated",
        "circle",
        "circle_membership_errors.g.dart",
    )
    claim = opm.derive_app_object_claim(
        parts,
        roster,
        {},
        "quwoquan_app/lib/runtime/errors/generated/circle/"
        "circle_membership_errors.g.dart",
    )

    assert claim["objectIds"] == []
    assert claim["method"] == "unowned"
    assert opm.derive_app_cross_cutting_shape_root(parts) == "runtime"


def test_scope_named_segment_is_not_claimed_as_an_object(
    roster: opm.ObjectRoster,
) -> None:
    """`circle` 既是 domain 又是 `circle.circle`，对象树祖先优先。"""
    membership = opm.derive_app_object_claim(
        (
            "service",
            "circle_service",
            "circle_management",
            "circle_membership",
            "domain",
            "circle_membership_errors.dart",
        ),
        roster,
        {},
        "quwoquan_app/lib/service/circle_service/circle_management/circle_membership/"
        "domain/circle_membership_errors.dart",
    )
    assert membership["objectIds"] == ["circle.circle_membership"]
    assert membership["method"] == "app_target_shape"

    # 作用域已由祖先段确立时，同名段才允许按对象解释。
    scoped = opm.derive_app_object_claim(
        ("cloud", "remote", "circle", "circle", "circle_remote.dart"),
        roster,
        {},
        "quwoquan_app/lib/cloud/remote/circle/circle/circle_remote.dart",
    )
    assert scoped["objectIds"] == ["circle.circle"]
    assert scoped["method"] == "path_object_scoped"


def test_ambiguous_alias_is_reported_instead_of_arbitrarily_resolved(
    roster: opm.ObjectRoster,
) -> None:
    """`behavior` 同时命中 circle 与 content 的事实对象，必须报歧义。"""
    claim = opm.derive_app_object_claim(
        ("cloud", "services", "behavior", "behavior_repository.dart"),
        roster,
        {},
        "quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart",
    )

    assert claim["ambiguous"] is True
    assert len(claim["objectIds"]) > 1


def test_page_object_contract_is_the_authoritative_presentation_signal(
    roster: opm.ObjectRoster,
) -> None:
    page_path = "quwoquan_app/lib/ui/content/pages/example_page.dart"
    single = opm.derive_app_object_claim(
        ("ui", "content", "pages", "example_page.dart"),
        roster,
        {page_path: ["content.post"]},
        page_path,
    )

    assert single["method"] == "page_object_contract"
    assert single["objectIds"] == ["content.post"]
    assert single["ambiguous"] is False

    multi = opm.derive_app_object_claim(
        ("ui", "content", "pages", "example_page.dart"),
        roster,
        {page_path: ["content.post", "content.comment"]},
        page_path,
    )
    # 一页横跨多个对象时不得替业务择一，必须暴露为需拆页的歧义。
    assert multi["ambiguous"] is True
    assert multi["objectIds"] == ["content.comment", "content.post"]


def test_app_layer_is_derived_from_the_rightmost_marker_segment() -> None:
    assert opm.derive_app_layer(("ui", "chat", "pages", "x.dart")) == "presentation"
    assert (
        opm.derive_app_layer(("ui", "settings", "providers", "x.dart")) == "application"
    )
    assert opm.derive_app_layer(("cloud", "remote", "user", "persona", "x.dart")) == (
        "adapters"
    )
    # 现状路径没有表达层角色时返回 None，由调用方标记为待裁决，绝不默认成某一层。
    assert opm.derive_app_layer(("cloud", "runtime", "generated", "x.dart")) is None


def test_app_layer_rules_only_produce_declared_app_layers() -> None:
    produced = {
        opm.APP_LAYER_ALIASES.get(layer, layer)
        for layer in opm.APP_LAYER_BY_SEGMENT.values()
    }

    assert produced <= set(opm.APP_LAYERS)
