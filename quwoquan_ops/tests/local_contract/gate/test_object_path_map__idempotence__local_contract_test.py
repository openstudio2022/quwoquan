"""`object_path_map.py` 派生规则的本地契约（派生幂等与全树扫描不变量组）。

由 1000 行硬顶拆分自 test_object_path_map__derivation__local_contract_test.py；
测试逐字搬移，LIB_PREFIX / TEST_PREFIX 与局部 helper 只被本组使用，随组保留。
共享 `roster` fixture 见 conftest.py。

与原文件相同，这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`。
"""
from __future__ import annotations

import filecmp
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm

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
    """`lib/service/<service>/<context>/<object>/<layer>/` 命中即精确归属。"""
    parts = (
        "service",
        "chat_service",
        "chat",
        "conversation",
        "adapters",
        "conversation_remote.dart",
    )
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
    nested_marker = (
        "service",
        "content_service",
        "content",
        "post",
        "presentation",
        "providers",
        "x.dart",
    )
    assert opm.derive_app_layer(nested_marker, roster) == "presentation"
    # 不传 roster 时是「未搬迁路径」的旧口径，会被深层段带偏；正是它必须让位的原因。
    assert opm.derive_app_layer(nested_marker) == "application"

    nested_object = (
        "service",
        "content_service",
        "content",
        "post",
        "presentation",
        "comment",
        "x.dart",
    )
    claim = opm.derive_app_object_claim(nested_object, roster, {}, "irrelevant")
    assert claim["objectIds"] == ["content.post"]


def test_target_shape_recognition_rejects_paths_that_are_not_migrated(
    roster: opm.ObjectRoster,
) -> None:
    """目标形态识别必须精确：service/context/object/layer 全部必须 canonical。"""
    # 第五段不是声明层。
    assert (
        opm.derive_app_target_shape_identity(
            ("service", "chat_service", "chat", "conversation", "widgets", "x.dart"),
            roster,
        )
        is None
    )
    # service 与 context 的云侧 owner 不匹配。
    assert (
        opm.derive_app_target_shape_identity(
            ("service", "user_service", "chat", "conversation", "domain", "x.dart"),
            roster,
        )
        is None
    )
    # context/object 不是 roster 内的真实对象。
    assert (
        opm.derive_app_target_shape_identity(
            ("service", "assistant_service", "application", "domain", "domain", "x.dart"),
            roster,
        )
        is None
    )
    # 只有目录没有文件时不成立（目标形态至少 5 段 + 文件名）。
    assert (
        opm.derive_app_target_shape_identity(
            ("service", "chat_service", "chat", "conversation", "domain"), roster
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
    """测试树逐段镜像：`test/<layer>/service/<service>/<context>/<object>/`。"""
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


def test_non_object_test_identities_are_derived_only_from_canonical_roots() -> None:
    """横切/Journey/Patrol 测试不借 filename、import 或 registry 冒充 object evidence。"""
    assert opm.derive_app_test_non_object_identity(
        "local_contract", ("runtime", "transport", "content_post_client_test.dart")
    ) == {
        "kind": "test_cross_cutting",
        "root": "runtime",
        "status": "canonical_test_cross_cutting",
    }
    assert opm.derive_app_test_non_object_identity(
        "support", ("runtime", "patrol", "harness.dart")
    ) == {
        "kind": "test_support_cross_cutting",
        "root": "runtime",
        "status": "canonical_test_support_cross_cutting",
    }
    assert opm.derive_app_test_non_object_identity(
        "user_acceptance", ("journeys", "content_publish", "video_test.dart")
    ) == {
        "kind": "cross_object_journey",
        "root": "journeys",
        "status": "canonical_cross_object_journey",
    }
    assert opm.derive_app_test_non_object_identity(
        "user_acceptance", ("patrol", "test_bundle.dart")
    ) == {
        "kind": "patrol_runner",
        "root": "patrol",
        "status": "canonical_patrol_runner",
    }

    # 近似根、错误层、嵌套 Patrol 与对象名出现在文件名中均不得获得身份。
    for layer, parts in (
        ("local_contract", ("runtimeish", "content_post_test.dart")),
        ("api_integration", ("journeys", "content_publish", "video_test.dart")),
        ("user_acceptance", ("patrol", "nested", "test_bundle.dart")),
        ("user_acceptance", ("patrol", "other.dart")),
        ("local_contract", ("service", "content_service", "content_post_test.dart")),
    ):
        assert opm.derive_app_test_non_object_identity(layer, parts) is None


def test_non_object_test_identities_do_not_fill_object_test_coverage(
    roster: opm.ObjectRoster,
) -> None:
    """非对象行保留空 objectId，`build_object_view` 因而不能把它们算作对象测试。"""
    identity = opm.derive_app_test_non_object_identity(
        "local_contract", ("runtime", "transport", "content_post_client_test.dart")
    )
    assert identity is not None
    rows = [
        {
            "role": "test:local_contract",
            "path": "quwoquan_app/test/local_contract/runtime/transport/content_post_client_test.dart",
            "method": opm.APP_TEST_NON_OBJECT_IDENTITY_METHOD,
            "status": identity["status"],
            "testIdentityKind": identity["kind"],
            "testIdentityRoot": identity["root"],
            "objectIds": [],
        }
    ]
    view = opm.build_object_view(roster, [], rows, {}, [])
    assert all(not entry["app"]["tests"] for entry in view.values())
    baseline = opm.build_baseline(roster, [], rows, [], view)
    assert baseline["appUnownedFileTotal"] == 0
    assert baseline["appTestNonObjectIdentityFileTotal"] == 1
    assert baseline["appTestNonObjectIdentityFilesByKind"] == {
        "test_cross_cutting": 1
    }


def test_scanned_targets_are_fixed_points_of_the_derivation(
    roster: opm.ObjectRoster,
) -> None:
    """对全树实测：每一行的 `targetPath` 再派生一次必须仍是它自己。

    这条断言覆盖 `scan_app` 的真实输出（数千行），因此不会因为某个具体文件搬迁
    完成或尚未开始而变成空断言。
    """
    page_claims, _ = opm.load_page_claims()
    rows, _ = opm.scan_app(roster, page_claims)

    checked = {
        "object": 0,
        "cross_cutting": 0,
        "test": 0,
        "non_object_test": 0,
    }
    for row in rows:
        target = row.get("targetPath")
        if not target:
            continue
        if row["method"] == "cross_cutting":
            assert _cross_cutting_target(_library_relative(target)) == target, row["path"]
            checked["cross_cutting"] += 1
            continue
        if row["method"] == opm.APP_TEST_NON_OBJECT_IDENTITY_METHOD:
            assert row["role"].startswith("test")
            inner = tuple(target[len(TEST_PREFIX) :].split("/"))[1:]
            derived = opm.derive_app_test_non_object_identity(
                row["currentLayer"], inner
            )
            assert derived is not None
            assert derived["kind"] == row["testIdentityKind"]
            assert derived["root"] == row["testIdentityRoot"]
            assert derived["status"] == row["status"]
            assert target == row["targetPath"]
            checked["non_object_test"] += 1
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


def test_every_lib_production_file_is_owned_by_an_object_or_a_canonical_root(
    roster: opm.ObjectRoster,
) -> None:
    """`lib/**` 不得存在既无对象 owner、又不在 canonical 横切根的生产文件。

    这是 App canonical coverage 能否计量的前置条件：`verify_canonical_coverage.AppAttribution`
    只接受 `objectId` 或 `status == "canonical_cross_cutting"`，其余一律判为无主
    源码并阻断，且明确禁止用 allowance 放行。

    回归防线：l10n 根曾经只登记在 `verify_app_architecture` 的 R1 顶层白名单里，
    `APP_CROSS_CUTTING_ROOTS` 不认识它，于是派生器把 `lib/l10n/**` 的目标算成
    `lib/runtime/l10n/**`，status 永远停在 `cross_cutting`；顶层入口 `lib/main*.dart`
    同理被算成 `lib/runtime/main.dart`。两者合计 28 个文件全部变成无主源码，
    App scope 一个单元都发现不了。收敛前本断言失败，收敛后才通过。
    """
    page_claims, _ = opm.load_page_claims()
    rows, _findings = opm.scan_app(roster, page_claims)

    orphans = sorted(
        f"{row['path']} (status={row['status']}, targetPath={row['targetPath']})"
        for row in rows
        if row["role"] == "production"
        and not row.get("objectId")
        and row["status"] != "canonical_cross_cutting"
    )

    assert orphans == [], (
        "以下 lib/** 生产文件既不归属对象，也不在 canonical 横切根；"
        "必须把它们的终态位置登记进 APP_CROSS_CUTTING_ROOTS 或搬到对象树，"
        "不得靠 allowance 放行：\n  " + "\n  ".join(orphans)
    )


def test_l10n_root_is_derived_from_the_flutter_gen_l10n_config() -> None:
    """l10n 横切根的唯一真相源是 `quwoquan_app/l10n.yaml` 的 `arb-dir`。

    `arb-dir` 同时决定 arb 输入与 `app_localizations*.dart` 的生成落点，因此该根是
    工具链固定的终态位置，不是可以被派生器推去 `lib/runtime/` 的待搬迁目录。
    """
    l10n_root = opm.derive_app_l10n_cross_cutting_root()

    assert l10n_root in opm.APP_CROSS_CUTTING_ROOTS
    assert opm.APP_CROSS_CUTTING_ROOTS[l10n_root] == f"lib/{l10n_root}"
    assert (ROOT / opm.APP_LIB_ROOT / l10n_root).is_dir()
    # 根段来自配置而不是门禁里的字面量：改 arb-dir 必须同步改变派生结果。
    document = yaml.safe_load(
        (ROOT / opm.APP_L10N_CONFIG_PATH).read_text(encoding="utf-8")
    )
    assert document["arb-dir"].strip("/").split("/")[1] == l10n_root


def test_top_level_entry_files_are_a_terminal_position_not_a_pending_migration() -> None:
    """`lib/main*.dart` 是端侧组合根，横切目标路径必须等于自身。"""
    for name in ("main.dart", "main_prod.dart"):
        parts = (name,)
        assert opm.derive_app_is_entry_file(parts)
        # 入口归 runtime 横切单元，但不得被推去 lib/runtime/main.dart。
        assert opm.derive_app_cross_cutting_root(parts) == "runtime"
        assert _cross_cutting_target(parts) == f"{LIB_PREFIX}{name}"
        assert _cross_cutting_target(_library_relative(_cross_cutting_target(parts))) == (
            f"{LIB_PREFIX}{name}"
        )

    # 入口判定只认 `lib/` 顶层：同名文件落在子目录里不是入口。
    assert not opm.derive_app_is_entry_file(("runtime", "main.dart"))
    assert not opm.derive_app_is_entry_file(("app_bootstrap.dart",))


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
