"""`object_path_map.py` 派生规则的本地契约。

本测试锁定的是「派生规则」本身，而不是某次扫描的具体数字：规则会被后续 16 条
domain 并行流与 W5 的 Go evidence loader 共同消费，任何静默改动都会让并行流对
对象归属产生分歧。

这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`：该 GWT 还需要统一门禁与
三层证据闭环才算达成，本工具只提供其中的路径反推部分，不代表 OPEN-001 关闭。
"""
from __future__ import annotations

import filecmp
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm


@pytest.fixture(scope="module")
def roster() -> opm.ObjectRoster:
    graph = json.loads((ROOT / opm.CONTRACT_GRAPH_PATH).read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)


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


def test_scope_named_segment_is_not_claimed_as_an_object(
    roster: opm.ObjectRoster,
) -> None:
    """`circle` 既是 domain 又是 `circle.circle`，作用域优先。"""
    claim = opm.derive_app_object_claim(
        ("cloud", "circle", "generated", "circle_membership_errors.g.dart"),
        roster,
        {},
        "quwoquan_app/lib/cloud/circle/generated/circle_membership_errors.g.dart",
    )

    assert claim["objectIds"] == ["circle.circle_membership"]
    assert claim["method"] == "filename_object_scoped"

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


def test_required_app_layers_are_sound_against_the_cloud_rule() -> None:
    """端侧必需层必须能经等价映射落回云侧同 kind 的必需层，不得凭空新增。"""
    for kind, app_layers in opm.REQUIRED_APP_LAYERS_BY_KIND.items():
        cloud_equivalents = {
            opm.APP_TO_CLOUD_LAYER_EQUIVALENCE[layer] for layer in app_layers
        }
        if kind == "external_reference":
            allowed = set(opm.CLOUD_EXTERNAL_REFERENCE_REQUIRED) | set(
                opm.CLOUD_EXTERNAL_REFERENCE_EITHER
            )
        else:
            allowed = set(opm.required_cloud_layers(kind))
        assert cloud_equivalents <= allowed, kind


def test_presentation_requirement_comes_from_the_page_object_contract() -> None:
    assert "presentation" not in opm.REQUIRED_APP_LAYERS_BY_KIND["aggregate_root"]
    assert "presentation" in opm.required_app_layers(
        "aggregate_root", claimed_by_page=True
    )
    assert "presentation" not in opm.required_app_layers(
        "aggregate_root", claimed_by_page=False
    )
    # append_only_fact 禁止 presentation，即便被页面引用也不得要求该层。
    assert "presentation" not in opm.required_app_layers(
        "append_only_fact", claimed_by_page=True
    )


def test_target_paths_follow_the_object_shaped_layout() -> None:
    assert (
        opm.derive_app_target_path(
            "chat", "chat", "conversation", "adapters", "conversation_remote.dart"
        )
        == "quwoquan_app/lib/chat/chat/conversation/adapters/conversation_remote.dart"
    )
    assert opm.derive_app_test_target_path(
        "local_contract", "chat", "chat", "conversation", "x_test.dart"
    ) == ("quwoquan_app/test/local_contract/chat/chat/conversation/x_test.dart")
    # 横切面只有两个落点，且剥离现状 `core/` 前缀与目标根自身的段。
    assert opm.derive_app_cross_cutting_target_path(
        "runtime", ("core", "platform", "x.dart")
    ) == ("quwoquan_app/lib/runtime/platform/x.dart")
    assert opm.derive_app_cross_cutting_target_path(
        "design_system", ("core", "design_system", "tokens.dart")
    ) == ("quwoquan_app/lib/design_system/tokens.dart")


# ---------------------------------------------------------------------------
# 派生幂等：derive(derive(p)) == derive(p)
#
# 四条 domain 流与 W1b 每搬一个对象就重跑派生器与端侧架构门禁，已搬迁路径一旦被
# 当成未搬迁路径再推导一层，就会持续产生假归属与假违规，且随搬迁推进越来越重。
# 因此「已处于目标形态的路径派生结果等于自身」是硬不变量，不是优化项。
# ---------------------------------------------------------------------------

LIB_PREFIX = f"{opm.APP_LIB_ROOT.as_posix()}/"
TEST_PREFIX = f"{opm.APP_TEST_ROOT.as_posix()}/"


def _library_relative(repository_relative_path: str) -> tuple[str, ...]:
    assert repository_relative_path.startswith(LIB_PREFIX), repository_relative_path
    return tuple(repository_relative_path[len(LIB_PREFIX) :].split("/"))


def _cross_cutting_target(library_relative_parts: tuple[str, ...]) -> str:
    """横切面派生的完整一步：先定根，再构造目标路径。"""
    root = opm.derive_app_cross_cutting_root(library_relative_parts)
    return opm.derive_app_cross_cutting_target_path(root, library_relative_parts)


def test_cross_cutting_target_path_is_idempotent() -> None:
    """已在 `lib/runtime/**` / `lib/design_system/**` 的文件不得被再套一层根段。"""
    already_migrated = (
        ("runtime", "di", "content_dependencies.dart"),
        ("runtime", "transport", "cloud_client.dart"),
        ("design_system", "tokens", "spacing.dart"),
    )
    for parts in already_migrated:
        target = _cross_cutting_target(parts)
        assert target == f"{LIB_PREFIX}{'/'.join(parts)}", parts
        assert _cross_cutting_target(_library_relative(target)) == target, parts

    # 未搬迁路径仍按旧前缀规则归位，且归位结果本身已是不动点。
    for parts in (
        ("core", "di", "app_production_composition.dart"),
        ("core", "providers", "app_providers.dart"),
        ("core", "design_system", "tokens.dart"),
    ):
        target = _cross_cutting_target(parts)
        assert _cross_cutting_target(_library_relative(target)) == target, parts


def test_cross_cutting_root_follows_physical_placement_once_migrated() -> None:
    """段名启发式不得改判已搬迁文件：`lib/runtime/theme/` 属于 runtime。"""
    assert opm.derive_app_cross_cutting_root(("runtime", "theme", "x.dart")) == "runtime"
    assert opm.derive_app_cross_cutting_root(("runtime", "tokens", "x.dart")) == "runtime"
    assert (
        opm.derive_app_cross_cutting_root(("design_system", "shell", "x.dart"))
        == "design_system"
    )
    # 尚未搬迁时才由段名判定落点。
    assert (
        opm.derive_app_cross_cutting_root(("core", "theme", "x.dart")) == "design_system"
    )
    assert opm.derive_app_cross_cutting_root(("core", "config", "x.dart")) == "runtime"


def test_migrated_object_tree_file_is_claimed_by_its_physical_position(
    roster: opm.ObjectRoster,
) -> None:
    """`lib/<domain>/<context>/<object>/<layer>/` 命中即精确归属，不再走启发式。"""
    parts = ("chat", "chat", "conversation", "adapters", "conversation_remote.dart")
    claim = opm.derive_app_object_claim(parts, roster, {}, "irrelevant")

    assert claim["method"] == "app_target_shape"
    assert opm.CLAIM_METHOD_CONFIDENCE[claim["method"]] == "exact"
    assert claim["objectIds"] == ["chat.conversation"]
    assert claim["ambiguous"] is False
    assert claim["targetLayer"] == "adapters"
    # 已搬迁文件绝不能落回作用域级结论。
    assert claim["method"] not in {"context_only", "domain_only", "unowned"}


def test_declared_layer_segment_wins_over_deeper_markers(
    roster: opm.ObjectRoster,
) -> None:
    """层内可选子路径（与云侧 `adapters/inbound/http/` 同构）不得改判层与对象。"""
    nested_marker = ("content", "content", "post", "presentation", "providers", "x.dart")
    assert opm.derive_app_layer(nested_marker, roster) == "presentation"
    # 不传 roster 时是「未搬迁路径」的旧口径，会被深层段带偏；正是它必须让位的原因。
    assert opm.derive_app_layer(nested_marker) == "application"

    nested_object = ("content", "content", "post", "presentation", "comment", "x.dart")
    claim = opm.derive_app_object_claim(nested_object, roster, {}, "irrelevant")
    assert claim["objectIds"] == ["content.post"]


def test_target_shape_recognition_rejects_paths_that_are_not_migrated(
    roster: opm.ObjectRoster,
) -> None:
    """目标形态识别必须精确：前三段命中 roster 且第四段是声明层，否则不成立。"""
    # 第四段不是声明层。
    assert (
        opm.derive_app_target_shape_identity(
            ("chat", "chat", "conversation", "widgets", "x.dart"), roster
        )
        is None
    )
    # 前三段不是 roster 内的真实对象。
    assert (
        opm.derive_app_target_shape_identity(
            ("assistant", "application", "domain", "domain", "x.dart"), roster
        )
        is None
    )
    # 只有目录没有文件时不成立（目标形态至少 4 段 + 文件名）。
    assert (
        opm.derive_app_target_shape_identity(
            ("chat", "chat", "conversation", "domain"), roster
        )
        is None
    )
    # 现状旧树不得被误认为已搬迁。
    for legacy in (
        ("ui", "chat", "pages", "x_page.dart"),
        ("cloud", "services", "chat", "conversation_remote.dart"),
        ("core", "providers", "app_providers.dart"),
    ):
        assert opm.derive_app_target_shape_identity(legacy, roster) is None, legacy


def test_object_shaped_target_path_round_trips_through_identity(
    roster: opm.ObjectRoster,
) -> None:
    """构造 → 反推 → 再构造必须回到同一路径（对象树侧幂等的代数形式）。"""
    for object_id, record in sorted(roster.objects.items()):
        for layer in opm.APP_LAYERS:
            target = opm.derive_app_target_path(
                record["domain"],
                record["context"],
                record["objectName"],
                layer,
                "x.dart",
            )
            parts = _library_relative(target)
            identity = opm.derive_app_target_shape_identity(parts, roster)
            assert identity == (
                record["domain"],
                record["context"],
                record["objectName"],
                layer,
            ), (object_id, layer)
            assert opm.derive_app_layer(parts, roster) == layer
            claim = opm.derive_app_object_claim(parts, roster, {}, target)
            assert claim["objectIds"] == [object_id], (object_id, layer)
            assert (
                opm.derive_app_target_path(*identity, "x.dart") == target
            ), (object_id, layer)


def test_test_tree_target_path_round_trips_through_identity(
    roster: opm.ObjectRoster,
) -> None:
    """测试树侧同构：`test/<layer>/<domain>/<context>/<object>/` 精确反推。"""
    for object_id, record in sorted(roster.objects.items()):
        target = opm.derive_app_test_target_path(
            "local_contract",
            record["domain"],
            record["context"],
            record["objectName"],
            "x__local_contract_test.dart",
        )
        inner = tuple(target[len(TEST_PREFIX) :].split("/"))[1:]
        assert opm.derive_app_test_target_shape_identity(inner, roster) == (
            record["domain"],
            record["context"],
            record["objectName"],
        ), object_id


def test_scanned_targets_are_fixed_points_of_the_derivation(
    roster: opm.ObjectRoster,
) -> None:
    """对全树实测：每一行的 `targetPath` 再派生一次必须仍是它自己。

    这条断言覆盖 `scan_app` 的真实输出（数千行），因此不会因为某个具体文件搬迁
    完成或尚未开始而变成空断言。
    """
    page_claims, _ = opm.load_page_claims()
    rows, _ = opm.scan_app(roster, page_claims)

    checked = {"object": 0, "cross_cutting": 0, "test": 0}
    for row in rows:
        target = row.get("targetPath")
        if not target:
            continue
        if row["method"] == "cross_cutting":
            assert _cross_cutting_target(_library_relative(target)) == target, row["path"]
            checked["cross_cutting"] += 1
            continue
        if row["role"].startswith("test"):
            inner = tuple(target[len(TEST_PREFIX) :].split("/"))[1:]
            assert opm.derive_app_test_target_shape_identity(inner, roster) == (
                row["domain"],
                row["context"],
                row["objectName"],
            ), row["path"]
            checked["test"] += 1
            continue
        parts = _library_relative(target)
        assert opm.derive_app_target_shape_identity(parts, roster) == (
            row["domain"],
            row["context"],
            row["objectName"],
            row["targetLayer"],
        ), row["path"]
        claim = opm.derive_app_object_claim(parts, roster, page_claims, target)
        assert claim["objectIds"] == [row["objectId"]], row["path"]
        assert opm.derive_app_layer(parts, roster) == row["targetLayer"], row["path"]
        checked["object"] += 1

    assert all(count > 0 for count in checked.values()), checked


def test_already_migrated_files_on_disk_are_reported_as_canonical(
    roster: opm.ObjectRoster,
) -> None:
    """物理已在目标位置的文件必须 `targetPath == path`，且不再记为无主 finding。"""
    page_claims, _ = opm.load_page_claims()
    rows, findings = opm.scan_app(roster, page_claims)
    finding_paths = {finding["path"] for finding in findings}

    for row in rows:
        if row["role"] != "production":
            continue
        parts = _library_relative(row["path"])
        if opm.derive_app_target_shape_identity(parts, roster) is not None:
            assert row["status"] == "canonical", row["path"]
            assert row["targetPath"] == row["path"], row["path"]
            assert row["path"] not in finding_paths, row["path"]
            continue
        if opm.derive_app_cross_cutting_shape_root(parts) is None:
            continue
        # 已搬到横切根下的文件：目标即自身，且不再算「无法反推的待裁决项」。
        assert row["targetPath"] == row["path"], row["path"]
        assert row["status"] == "canonical_cross_cutting", row["path"]
        assert row["path"] not in finding_paths, row["path"]


def test_derivation_is_idempotent_and_writes_only_disposable_output(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert opm.main(["--output-dir", str(first)]) == 0
    assert opm.main(["--output-dir", str(second)]) == 0

    produced = sorted(path.name for path in first.iterdir())
    assert produced == sorted(path.name for path in second.iterdir())
    match, mismatch, errors = filecmp.cmpfiles(first, second, produced, shallow=False)
    assert (sorted(match), mismatch, errors) == (sorted(produced), [], [])

    payload = json.loads((first / "object_path_map.json").read_text(encoding="utf-8"))
    assert payload["ruleId"] == opm.RULE_ID
    # 产物只描述派生结果，不得成为受版本控制的对象归属台账。
    assert payload["inputs"]["contractGraph"]["path"] == (
        opm.CONTRACT_GRAPH_PATH.as_posix()
    )
    assert not (ROOT / "quwoquan_ops" / "gate" / "object_path_map.json").exists()
