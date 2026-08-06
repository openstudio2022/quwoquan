"""`verify_app_architecture.py`（端侧对象化架构门禁 v1）的本地契约。

本测试锁定四件事：

1. 规则来源单一：顶层白名单与对象归属都必须从 `object_path_map.py` 与
   `quwoquan_app/l10n.yaml` 派生，门禁不得内置第二套路径反推或 domain 名单。
2. 跨对象只能依赖目标对象 `application/public/**`；同对象与横切代码不得误报。
3. ratchet 语义：新违规与陈旧基线条目都必须阻断，`--domain` 只收窄 R2/R3/R4
   的比对范围，共享的顶层规则在任何 scope 下都全量求值；R4 绝不进入基线。
4. 仓库基线只减不增：基线里不得残留陈旧条目，也不得引用磁盘上已不存在的路径。

这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`：端侧对象化目录尚未搬迁，
本门禁只提供其中的静态约束与基线部分，不代表 OPEN-001 关闭。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_app_architecture as vaa

GATE_REPO_PATH = ROOT / "quwoquan_ops/gate/gate_repo.sh"
APP_ARCHITECTURE_COMMAND = (
    "python3 quwoquan_ops/gate/verify_app_architecture.py || exit 1"
)


@pytest.fixture(scope="module")
def roster() -> opm.ObjectRoster:
    return vaa.load_roster()


@pytest.fixture(scope="module")
def evaluation(roster: opm.ObjectRoster) -> dict:
    return vaa._normalized(vaa.evaluate(roster))


# ---------------------------------------------------------------------------
# 规则来源单一
# ---------------------------------------------------------------------------


def test_top_level_whitelist_is_derived_and_not_hardcoded(
    roster: opm.ObjectRoster,
) -> None:
    allowed = vaa.allowed_top_level_directories(roster)

    # 业务对象统一落在 service 容器；横切部分来自派生器的唯一两个横切根。
    assert opm.APP_SERVICE_ROOT_SEGMENT in allowed
    assert not (set(roster.domains) & allowed)
    assert set(opm.APP_CROSS_CUTTING_ROOTS) <= allowed
    # l10n 根来自 l10n.yaml 的 arb-dir，不是门禁里写死的字符串。
    assert vaa.l10n_top_level_segment() in allowed
    assert allowed == {opm.APP_SERVICE_ROOT_SEGMENT} | set(
        opm.APP_CROSS_CUTTING_ROOTS
    ) | {
        vaa.l10n_top_level_segment()
    }
    # 现状按技术角色分层的顶层目录一律不在白名单内。
    assert not {"ui", "core", "cloud", "components", "app", "application"} & allowed


def test_only_entry_files_are_allowed_at_the_lib_top_level() -> None:
    assert vaa.TOP_LEVEL_ENTRY_RE.match("main.dart")
    assert vaa.TOP_LEVEL_ENTRY_RE.match("main_prod.dart")
    # bootstrap 与 shell 属于 runtime/shell/，不是入口。
    assert not vaa.TOP_LEVEL_ENTRY_RE.match("app_bootstrap.dart")
    assert not vaa.TOP_LEVEL_ENTRY_RE.match("quwoquan_app_shell.dart")


def test_import_resolution_only_keeps_in_package_library_edges() -> None:
    assert (
        vaa._resolve_import_uri("core/providers/app_providers.dart", "../errors/x.dart")
        == "core/errors/x.dart"
    )
    assert (
        vaa._resolve_import_uri("main.dart", "package:quwoquan_app/ui/chat/x.dart")
        == "ui/chat/x.dart"
    )
    assert vaa._resolve_import_uri(
        "main.dart",
        "package:quwoquan_app/service/content_service/content/post/../comment/domain/comment.dart",
    ) == "service/content_service/content/comment/domain/comment.dart"
    assert vaa._resolve_import_uri(
        "service/content_service/content/post/application/public/post_reader.dart",
        "package:quwoquan_app/service/content_service/content/post/application/public/"
        "%2e%2e/private_reader.dart",
    ) == "service/content_service/content/post/application/private_reader.dart"
    # dart:*、其他 package:* 不构成本包内依赖边。
    assert vaa._resolve_import_uri("main.dart", "dart:async") is None
    assert vaa._resolve_import_uri("main.dart", "package:flutter/material.dart") is None
    # 共享 generated value types 属于 contracts package，不是 App 对象私有实现。
    assert (
        vaa._resolve_import_uri(
            "service/content_service/content/post/application/public/post_reader.dart",
            "package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart",
        )
        is None
    )
    with pytest.raises(ValueError, match="越出 lib"):
        vaa._resolve_import_uri(
            "main.dart", "package:quwoquan_app/../../outside.dart"
        )
    with pytest.raises(ValueError, match="越出 lib"):
        vaa._resolve_import_uri(
            "main.dart", "package:quwoquan_app/%2e%2e/outside.dart"
        )
    with pytest.raises(ValueError, match="越出 lib"):
        vaa._resolve_import_uri(
            "service/chat_service/chat/conversation/presentation/page.dart",
            "../../../../../../outside.dart",
        )
    with pytest.raises(ValueError, match="静态 POSIX"):
        vaa._resolve_import_uri("main.dart", "package:quwoquan_app/$target.dart")
    with pytest.raises(ValueError, match="percent escape"):
        vaa._resolve_import_uri("main.dart", "package:quwoquan_app/invalid%2.dart")


def test_dart_lexer_finds_conditional_import_export_and_part_only() -> None:
    source = r'''
// import 'commented.dart';
/* export 'blocked.dart'; /* part 'nested_comment.dart'; */ */
const fake = "import 'inside_string.dart';";
const triple = """export 'inside_triple_string.dart';""";
import 'base.dart'
  if (dart.library.io) 'io.dart'
  if (dart.library.html) r'web.dart';
export 'surface.dart' if (dart.library.io) 'surface_io.dart';
part 'library_part.dart';
part of 'library_owner.dart';
'''

    assert vaa.parse_dart_uri_directives(source) == [
        vaa.DartUriDirective("import", "base.dart"),
        vaa.DartUriDirective("import", "io.dart"),
        vaa.DartUriDirective("import", "web.dart"),
        vaa.DartUriDirective("export", "surface.dart"),
        vaa.DartUriDirective("export", "surface_io.dart"),
        vaa.DartUriDirective("part", "library_part.dart"),
    ]


def test_dart_lexer_fails_closed_on_unterminated_authored_source() -> None:
    with pytest.raises(ValueError, match="unterminated Dart block comment"):
        vaa.parse_dart_uri_directives("/* import 'hidden.dart';")
    with pytest.raises(ValueError, match="unterminated Dart import directive"):
        vaa.parse_dart_uri_directives("import 'missing_semicolon.dart'")


def test_target_root_folds_object_path_map_claims(roster: opm.ObjectRoster) -> None:
    by_domain: dict[str, str] = {}
    for object_id, record in sorted(roster.objects.items()):
        by_domain.setdefault(record["domain"], object_id)
    first_domain, second_domain = sorted(by_domain)[:2]

    assert vaa.derive_target_root(
        {"objectId": by_domain[first_domain], "domain": first_domain}, roster
    ) == ("domain", first_domain)
    # 只能反推到 bounded context / domain 时，仍按该 domain 计。
    assert vaa.derive_target_root({"contextIds": [f"{first_domain}.x"]}, roster) == (
        "domain",
        first_domain,
    )
    assert vaa.derive_target_root({"domains": [second_domain]}, roster) == (
        "domain",
        second_domain,
    )
    # 跨 domain 的歧义绝不代替业务择一。
    assert vaa.derive_target_root(
        {"objectIds": [by_domain[first_domain], by_domain[second_domain]]}, roster
    ) == ("unresolved", None)
    assert vaa.derive_target_root({"crossCuttingRoot": "design_system"}, roster) == (
        "cross_cutting",
        "design_system",
    )
    assert vaa.derive_target_root({}, roster) == ("unresolved", None)


def test_composition_root_exemption_is_limited_to_entry_and_runtime_di() -> None:
    composition_target = opm.derive_app_cross_cutting_target_path(
        "runtime", ("core", "di", "app_production_composition.dart")
    )
    # 例外范围由派生出的目标路径决定，不是另写一份现状路径名单。
    assert composition_target == (
        "quwoquan_app/lib/runtime/di/app_production_composition.dart"
    )
    assert vaa.is_composition_root(
        "core/di/app_production_composition.dart", composition_target
    )
    assert vaa.is_composition_root("main.dart", "quwoquan_app/lib/runtime/main.dart")
    # 已经搬到目标形态的组合根：派生目标会被再套一层 `runtime/`，必须按物理路径判定。
    assert vaa.is_composition_root(
        "runtime/di/content_dependencies.dart",
        opm.derive_app_cross_cutting_target_path(
            "runtime", ("runtime", "di", "content_dependencies.dart")
        ),
    )

    provider_target = opm.derive_app_cross_cutting_target_path(
        "runtime", ("core", "providers", "app_providers.dart")
    )
    assert not vaa.is_composition_root(
        "core/providers/app_providers.dart", provider_target
    )
    assert not vaa.is_composition_root(
        "app_bootstrap.dart", "quwoquan_app/lib/runtime/app_bootstrap.dart"
    )


def _identity(
    object_id: str,
    *,
    domain: str,
    context: str,
    object_name: str,
    layer: str,
) -> vaa.AppObjectLibraryIdentity:
    return vaa.AppObjectLibraryIdentity(
        object_id=object_id,
        domain=domain,
        context=context,
        object_name=object_name,
        layer=layer,
    )


class _FakeObjectIndex:
    def __init__(
        self,
        identities: dict[str, vaa.AppObjectLibraryIdentity],
        directives: dict[str, list[vaa.ResolvedDartUriDirective]],
    ) -> None:
        self.object_identity = identities
        self._directives = directives

    def directives(
        self, library_relative_path: str
    ) -> list[vaa.ResolvedDartUriDirective]:
        return self._directives.get(library_relative_path, [])


def _directive(
    kind: str,
    target: str | None,
    *,
    uri: str | None = None,
) -> vaa.ResolvedDartUriDirective:
    return vaa.ResolvedDartUriDirective(kind, uri or target or "dart:core", target)


def test_cross_object_public_seam_allows_only_application_public_directory() -> None:
    identity = _identity(
        "content.post",
        domain="content",
        context="content",
        object_name="post",
        layer="application",
    )
    assert vaa.is_cross_object_public_seam(
        "service/content_service/content/post/application/public/post_reader.dart", identity
    )
    # 文件名叫 public.dart 不是显式 public 子目录，不能伪装成公开 seam。
    assert not vaa.is_cross_object_public_seam(
        "service/content_service/content/post/application/public.dart", identity
    )


def test_cross_object_scanner_allows_public_same_object_and_cross_cutting_edges() -> None:
    source = "service/chat_service/chat/conversation/presentation/conversation_page.dart"
    same_object = "service/chat_service/chat/conversation/application/conversation_query.dart"
    public_target = (
        "service/content_service/content/post/application/public/content_post_reader.dart"
    )
    runtime_target = "runtime/config/cloud_runtime_config.dart"
    design_target = "design_system/components/loading_state.dart"
    identities = {
        source: _identity(
            "chat.conversation",
            domain="chat",
            context="chat",
            object_name="conversation",
            layer="presentation",
        ),
        same_object: _identity(
            "chat.conversation",
            domain="chat",
            context="chat",
            object_name="conversation",
            layer="application",
        ),
        public_target: _identity(
            "content.post",
            domain="content",
            context="content",
            object_name="post",
            layer="application",
        ),
    }
    index = _FakeObjectIndex(
        identities,
        {
            source: [
                _directive("import", same_object),
                _directive("import", public_target),
                _directive("import", None, uri="package:flutter/material.dart"),
                _directive("import", None, uri=runtime_target),
                _directive("import", None, uri=design_target),
                # target identity 不可派生时不猜 legacy/generated owner。
                _directive("import", None, uri="cloud/legacy_generated.dart"),
            ],
            # 横切文件没有对象身份；即使它依赖对象，R4 不会与 R2/R3 重复计数。
            runtime_target: [_directive("import", same_object)],
        },
    )

    assert vaa.scan_cross_object_private_import_violations(index) == {}


@pytest.mark.parametrize(
    ("directive_kind", "source_layer", "target_layer", "target_suffix"),
    [
        ("import", "adapters", "adapters", "remote.dart"),
        ("import", "adapters", "presentation", "page.dart"),
        ("import", "application", "adapters", "remote.dart"),
        ("import", "application", "presentation", "page.dart"),
        ("import", "domain", "presentation", "page.dart"),
        ("import", "presentation", "adapters", "remote.dart"),
        ("import", "presentation", "application", "private_query.dart"),
        ("import", "presentation", "presentation", "private_widget.dart"),
        ("export", "application", "domain", "private_value.dart"),
        ("part", "presentation", "presentation", "foreign_part.dart"),
    ],
)
def test_cross_object_scanner_rejects_private_layer_edges(
    directive_kind: str,
    source_layer: str,
    target_layer: str,
    target_suffix: str,
) -> None:
    source = f"service/chat_service/chat/conversation/{source_layer}/source.dart"
    target = f"service/content_service/content/post/{target_layer}/{target_suffix}"
    index = _FakeObjectIndex(
        {
            source: _identity(
                "chat.conversation",
                domain="chat",
                context="chat",
                object_name="conversation",
                layer=source_layer,
            ),
            target: _identity(
                "content.post",
                domain="content",
                context="content",
                object_name="post",
                layer=target_layer,
            ),
        },
        {source: [_directive(directive_kind, target)]},
    )

    assert vaa.scan_cross_object_private_import_violations(index) == {
        "chat": [f"{directive_kind}: {source} -> {target}"]
    }


def test_public_seam_rejects_barrels_and_impure_dependencies() -> None:
    source = "service/chat_service/chat/conversation/application/public/conversation_reader.dart"
    same_object_domain = "service/chat_service/chat/conversation/domain/conversation_id.dart"
    same_object_public = (
        "service/chat_service/chat/conversation/application/public/conversation_id.dart"
    )
    same_object_private = (
        "service/chat_service/chat/conversation/application/private_reader.dart"
    )
    other_object_public = (
        "service/content_service/content/post/application/public/post_reader.dart"
    )
    runtime_target = "runtime/errors/ui_error_semantics.dart"
    local_generated_target = "cloud/runtime/generated/legacy_value.g.dart"
    index = _FakeObjectIndex(
        {
            source: _identity(
                "chat.conversation",
                domain="chat",
                context="chat",
                object_name="conversation",
                layer="application",
            ),
            same_object_domain: _identity(
                "chat.conversation",
                domain="chat",
                context="chat",
                object_name="conversation",
                layer="domain",
            ),
            same_object_public: _identity(
                "chat.conversation",
                domain="chat",
                context="chat",
                object_name="conversation",
                layer="application",
            ),
            same_object_private: _identity(
                "chat.conversation",
                domain="chat",
                context="chat",
                object_name="conversation",
                layer="application",
            ),
            other_object_public: _identity(
                "content.post",
                domain="content",
                context="content",
                object_name="post",
                layer="application",
            ),
        },
        {
            source: [
                _directive("import", same_object_domain),
                _directive("import", same_object_public),
                _directive("import", other_object_public),
                _directive("import", same_object_private),
                _directive("export", same_object_domain),
                _directive("part", same_object_domain),
                _directive(
                    "export",
                    None,
                    uri="package:quwoquan_cloud_contracts/generated.dart",
                ),
                _directive("import", None, uri="package:flutter/widgets.dart"),
                _directive("import", None, uri="dart:async"),
                _directive(
                    "import",
                    None,
                    uri="package:quwoquan_cloud_contracts/generated.dart",
                ),
                _directive("import", runtime_target, uri=runtime_target),
                _directive(
                    "import",
                    local_generated_target,
                    uri=(
                        "package:quwoquan_app/cloud/runtime/generated/"
                        "legacy_value.g.dart"
                    ),
                ),
                _directive(
                    "import",
                    None,
                    uri="package:quwoquan_app/missing_legacy_value.g.dart",
                ),
                _directive("import", None, uri="missing_relative_value.dart"),
            ]
        },
    )

    index.target_root = {runtime_target: ("cross_cutting", "runtime")}

    assert vaa.scan_cross_object_private_import_violations(index) == {
        "chat": sorted([
            (
                    "export: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> "
                    "service/chat_service/chat/conversation/domain/conversation_id.dart"
            ),
            (
                    "export: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> "
                "package:quwoquan_cloud_contracts/generated.dart"
            ),
            (
                    "import: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> "
                    "service/chat_service/chat/conversation/application/private_reader.dart"
            ),
            (
                    "import: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> "
                "cloud/runtime/generated/legacy_value.g.dart"
            ),
            (
                    "import: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> missing_relative_value.dart"
            ),
            (
                    "import: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> package:flutter/widgets.dart"
            ),
            (
                    "import: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> "
                "package:quwoquan_app/missing_legacy_value.g.dart"
            ),
            (
                    "import: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> runtime/errors/ui_error_semantics.dart"
            ),
            (
                    "part: service/chat_service/chat/conversation/application/public/"
                "conversation_reader.dart -> "
                    "service/chat_service/chat/conversation/domain/conversation_id.dart"
            ),
        ])
    }


def test_repository_has_no_cross_cutting_reverse_import_edges(
    evaluation: dict,
) -> None:
    """R2/R3 已清零后继续保持零容忍，不用历史违规为门禁本身制造夹具。"""
    for section in evaluation["domains"].values():
        assert section[vaa.RULE_TARGET_REVERSE_IMPORT] == []
        assert section[vaa.RULE_PHYSICAL_REVERSE_IMPORT] == []


def test_repository_cross_object_findings_are_real_private_edges(
    roster: opm.ObjectRoster,
    evaluation: dict,
) -> None:
    """迁移存量可为红，但每条必须是真实跨对象私有边，不能来自路径猜测。"""
    index = vaa.AppSourceIndex(roster)
    findings = [
        (domain, edge)
        for domain, section in evaluation["domains"].items()
        for edge in section[vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT]
    ]
    observed = vaa.scan_cross_object_private_import_violations(index)
    assert findings == [
        (domain, edge)
        for domain in sorted(observed)
        for edge in observed[domain]
    ]
    assert len(findings) == len(set(findings))
    for domain, edge in findings:
        directive_kind, dependency = edge.split(": ", 1)
        source, target = dependency.split(" -> ")
        source_identity = index.object_identity[source]
        assert domain == source_identity.domain
        if vaa.is_cross_object_public_seam(source, source_identity):
            if directive_kind in {"export", "part"}:
                continue
            target_identity = index.object_identity.get(target)
            if target_identity is None:
                target_root, _ = index.target_root.get(
                    target, ("unresolved", None)
                )
                assert target_root == "cross_cutting" or not target.startswith(
                    ("dart:", vaa.CLOUD_CONTRACTS_URI_PREFIX)
                )
                continue
            if target_identity.object_id == source_identity.object_id:
                assert target_identity.layer != "domain"
                assert not vaa.is_cross_object_public_seam(target, target_identity)
                continue
            assert not vaa.is_cross_object_public_seam(target, target_identity)
            continue
        target_identity = index.object_identity.get(target)
        assert target_identity is not None
        assert source_identity.object_id != target_identity.object_id
        assert not vaa.is_cross_object_public_seam(target, target_identity)


# ---------------------------------------------------------------------------
# ratchet 语义
# ---------------------------------------------------------------------------


def _document(shared: list[str], domains: dict[str, list[str]]) -> dict:
    return vaa._normalized(
        {
            "shared": {vaa.RULE_TOP_LEVEL: shared},
            "domains": {
                domain: {vaa.RULE_TARGET_REVERSE_IMPORT: edges}
                for domain, edges in domains.items()
            },
        }
    )


def test_ratchet_blocks_both_new_violations_and_stale_baseline_entries() -> None:
    baseline = _document(["ui/"], {"content": ["runtime/a.dart -> content/b.dart"]})
    current = _document(
        ["ui/", "legacy/"], {"content": ["runtime/a.dart -> content/c.dart"]}
    )

    new_violations, stale_entries = vaa.diff(current, baseline, None)

    assert new_violations == [
        f"{vaa.RULE_TOP_LEVEL}: legacy/",
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: runtime/a.dart -> content/c.dart",
    ]
    # 违规消失后必须显式收敛基线，不允许长期挂账。
    assert stale_entries == [
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: runtime/a.dart -> content/b.dart"
    ]
    assert vaa.diff(baseline, baseline, None) == ([], [])


def test_domain_scope_narrows_domain_rules_but_keeps_the_shared_top_level_rule() -> None:
    baseline = _document([], {})
    current = _document(
        ["legacy/"],
        {
            "content": ["runtime/a.dart -> content/b.dart"],
            "chat": ["runtime/a.dart -> chat/b.dart"],
        },
    )

    new_violations, _ = vaa.diff(current, baseline, "content")

    assert new_violations == [
        f"{vaa.RULE_TOP_LEVEL}: legacy/",
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: runtime/a.dart -> content/b.dart",
    ]


def test_absolute_cross_object_rule_cannot_be_suppressed_by_a_baseline() -> None:
    edge = (
        "import: chat/chat/a/presentation/a.dart -> "
        "content/content/b/domain/b.dart"
    )
    current = vaa._normalized(
        {
            "shared": {},
            "domains": {"chat": {vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT: [edge]}},
        }
    )
    # 即使调用方手工构造同名 baseline 条目，diff 仍把 observed R4 视为新违规。
    forged_baseline = vaa._normalized(current)

    assert vaa.diff(current, forged_baseline, None) == (
        [f"{vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT}[chat]: {edge}"],
        [],
    )


def test_domain_scope_attributes_r4_to_the_consumer_source_domain() -> None:
    edge = (
        "import: chat/chat/a/presentation/a.dart -> "
        "content/content/b/domain/b.dart"
    )
    current = vaa._normalized(
        {
            "shared": {},
            "domains": {"chat": {vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT: [edge]}},
        }
    )
    baseline = _document([], {})

    assert vaa.diff(current, baseline, "chat") == (
        [f"{vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT}[chat]: {edge}"],
        [],
    )
    assert vaa.diff(current, baseline, "content") == ([], [])


def test_baseline_writer_never_persists_the_absolute_cross_object_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    current = vaa._normalized(
        {
            "shared": {vaa.RULE_TOP_LEVEL: ["cloud/"]},
            "domains": {
                "content": {
                    vaa.RULE_TARGET_REVERSE_IMPORT: [
                        "runtime/a.dart -> content/content/b/domain/b.dart"
                    ],
                    vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT: [
                        (
                            "import: chat/chat/a/presentation/a.dart -> "
                            "content/content/b/domain/b.dart"
                        )
                    ],
                }
            },
        }
    )

    vaa.write_baseline(current, domain=None)

    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT not in json.dumps(written)
    assert written["domains"]["content"][vaa.RULE_TARGET_REVERSE_IMPORT]


def test_baseline_loader_rejects_a_handwritten_absolute_rule_allowance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    baseline_path.write_text(
        json.dumps(
            {
                "ruleId": vaa.RULE_ID,
                "shared": {},
                "domains": {
                    "content": {vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT: []}
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="不得进入 baseline/allowance"):
        vaa.load_baseline()


def test_write_baseline_cli_refuses_while_absolute_violations_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    roster: opm.ObjectRoster,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    edge = (
        "import: chat/chat/a/presentation/a.dart -> "
        "content/content/b/domain/b.dart"
    )
    monkeypatch.setattr(vaa, "load_roster", lambda: roster)
    monkeypatch.setattr(
        vaa,
        "evaluate",
        lambda _: {
            "shared": {vaa.RULE_TOP_LEVEL: []},
            "domains": {"chat": {vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT: [edge]}},
        },
    )

    assert vaa.main(["--write-baseline"]) == 1
    assert not baseline_path.exists()


def test_domain_scoped_baseline_write_preserves_other_domains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)

    original = _document(
        ["ui/"],
        {
            "content": ["runtime/a.dart -> content/b.dart"],
            "chat": ["runtime/a.dart -> chat/b.dart"],
        },
    )
    original["_governance"] = {
        "owner": "runtime-client-foundation",
        "reason": "temporary ratchet",
        "expires_when": "legacy roots are empty",
    }
    vaa.write_baseline(original, domain=None)
    first = baseline_path.read_text(encoding="utf-8")
    vaa.write_baseline(original, domain=None)
    assert baseline_path.read_text(encoding="utf-8") == first

    fixed_content = _document(["ui/"], {"chat": ["runtime/a.dart -> chat/b.dart"]})
    vaa.write_baseline(fixed_content, domain="content")

    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["ruleId"] == vaa.RULE_ID
    assert "content" not in written["domains"]
    # 其他并行流的分区与共享分区不得被顺带改写。
    assert written["domains"]["chat"][vaa.RULE_TARGET_REVERSE_IMPORT] == [
        "runtime/a.dart -> chat/b.dart"
    ]
    assert written["shared"][vaa.RULE_TOP_LEVEL] == ["ui/"]
    assert written["_governance"] == original["_governance"]


def test_domain_scoped_baseline_write_initializes_only_when_file_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    current = _document(
        [], {"content": ["runtime/a.dart -> content/content/post/domain/post.dart"]}
    )

    vaa.write_baseline(current, domain="content")

    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["ruleId"] == vaa.RULE_ID
    assert written["domains"]["content"][vaa.RULE_TARGET_REVERSE_IMPORT]


@pytest.mark.parametrize(
    "invalid_baseline",
    [
        "{not-json",
        json.dumps(
            {
                "ruleId": "wrong-rule",
                "shared": {vaa.RULE_TOP_LEVEL: ["cloud/"]},
                "domains": {
                    "chat": {
                        vaa.RULE_TARGET_REVERSE_IMPORT: [
                            "runtime/a.dart -> chat/chat/conversation/domain/id.dart"
                        ]
                    }
                },
            }
        ),
        json.dumps(
            {
                "ruleId": vaa.RULE_ID,
                "shared": {},
                "domains": {},
                "unknownMetadata": {"must": "not be silently dropped"},
            }
        ),
        json.dumps(
            {
                "ruleId": vaa.RULE_ID,
                "shared": {},
                "domains": {"chat": {"unknown_rule": ["kept"]}},
            }
        ),
        json.dumps(
            {"ruleId": vaa.RULE_ID, "shared": [], "domains": {}}
        ),
        json.dumps(
            {"ruleId": vaa.RULE_ID, "shared": {}, "domains": False}
        ),
    ],
)
def test_domain_scoped_write_never_replaces_an_invalid_existing_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_baseline: str,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    baseline_path.write_text(invalid_baseline, encoding="utf-8")
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    current = _document(
        [], {"content": ["runtime/a.dart -> content/content/post/domain/post.dart"]}
    )

    with pytest.raises(ValueError):
        vaa.write_baseline(current, domain="content")
    assert baseline_path.read_text(encoding="utf-8") == invalid_baseline


def test_domain_scoped_write_cli_reports_invalid_baseline_without_overwriting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    roster: opm.ObjectRoster,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    original = json.dumps(
        {
            "ruleId": "wrong-rule",
            "shared": {vaa.RULE_TOP_LEVEL: ["cloud/"]},
            "domains": {"chat": {vaa.RULE_TARGET_REVERSE_IMPORT: ["kept"]}},
        }
    )
    baseline_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(vaa, "load_roster", lambda: roster)
    monkeypatch.setattr(
        vaa,
        "evaluate",
        lambda _: {"shared": {vaa.RULE_TOP_LEVEL: []}, "domains": {}},
    )

    assert vaa.main(["--domain", "content", "--write-baseline"]) == 1
    assert baseline_path.read_text(encoding="utf-8") == original


def test_unknown_domain_is_rejected_instead_of_silently_passing() -> None:
    assert vaa.main(["--domain", "not_a_domain"]) == 2


# ---------------------------------------------------------------------------
# 唯一 App gate 入口
# ---------------------------------------------------------------------------


def _gate_function(source: str, name: str, next_name: str) -> str:
    start = source.index(f"\n{name}() {{") + 1
    end = source.index(f"\n{next_name}() {{", start)
    return source[start:end]


def test_repo_gate_runs_app_architecture_only_from_app_static_phase() -> None:
    source = GATE_REPO_PATH.read_text(encoding="utf-8")
    service = _gate_function(source, "run_service", "run_app")
    app = _gate_function(source, "run_app", "run_portal")

    assert source.count(APP_ARCHITECTURE_COMMAND) == 1
    assert APP_ARCHITECTURE_COMMAND not in service
    assert APP_ARCHITECTURE_COMMAND in app
    static_start = app.index(
        'if [[ "$app_phase" == "all" || "$app_phase" == "static" ]]; then'
    )
    static_end = app.index('if [[ "$app_phase" == "static" ]]; then', static_start)
    assert APP_ARCHITECTURE_COMMAND in app[static_start:static_end]

    dispatch = source[source.index('\ncase "$scope" in') :]
    assert "all)\n    run_service\n    run_data\n    run_app" in dispatch
    assert "service)\n    run_service\n    ;;" in dispatch
    assert "app)\n    run_app\n    ;;" in dispatch


def test_repo_gate_app_static_executes_architecture_once(
    tmp_path: Path,
) -> None:
    """执行真实 run_app shell 函数，防止文本位置看似正确但实际不可达。"""
    source = GATE_REPO_PATH.read_text(encoding="utf-8")
    app = _gate_function(source, "run_app", "run_portal")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    log_path = tmp_path / "commands.log"
    stub = '#!/usr/bin/env sh\nprintf "%s %s\\n" "$0" "$*" >>"$GATE_STUB_LOG"\n'
    for executable in ("python3", "dart", "flutter", "bash"):
        path = stub_dir / executable
        path.write_text(stub, encoding="utf-8")
        path.chmod(0o755)
    harness = tmp_path / "run_app_static.sh"
    harness.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        f"ROOT={str(ROOT)!r}\ncd \"$ROOT\"\n"
        f"{app}\nrun_app\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "GATE_APP_PHASE": "static",
            "GATE_STUB_LOG": str(log_path),
            "PATH": f"{stub_dir}:/usr/bin:/bin",
        }
    )

    completed = subprocess.run(
        ["/bin/bash", str(harness)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    commands = log_path.read_text(encoding="utf-8").splitlines()
    assert sum(
        "quwoquan_ops/gate/verify_app_architecture.py" in command
        for command in commands
    ) == 1


# ---------------------------------------------------------------------------
# 仓库基线只减不增
# ---------------------------------------------------------------------------


def _baseline_referenced_library_paths(recorded: dict) -> set[str]:
    """基线条目里出现的全部 `lib/` 相对路径。

    R1 条目是顶层名字（目录带 `/` 后缀），R2/R3 条目是 `source -> target` 依赖边。
    """
    referenced: set[str] = set()
    for entry in recorded.get("shared", {}).get(vaa.RULE_TOP_LEVEL, []) or []:
        referenced.add(entry.rstrip("/"))
    for section in (recorded.get("domains") or {}).values():
        for rule in vaa.DOMAIN_RULES:
            for edge in section.get(rule, []) or []:
                referenced.update(edge.split(" -> "))
    return referenced


def test_baseline_never_references_a_path_that_left_the_disk() -> None:
    """陈旧条目会让 ratchet 悄悄失效，必须在测试层就拦住堆积。

    搬迁会把违规源文件挪到新路径。旧条目留着既不阻断任何东西，又会掩盖同一条违规
    在新路径上的复现，因此基线只允许引用磁盘上真实存在的路径。
    """
    library_root = vaa.ROOT / opm.APP_LIB_ROOT
    missing = sorted(
        reference
        for reference in _baseline_referenced_library_paths(vaa.load_baseline())
        if not (library_root / reference).exists()
    )
    assert missing == []


def test_baseline_holds_no_stale_entry_and_domain_scope_runs(
    evaluation: dict,
) -> None:
    """基线不得记录已经消失的违规。

    这里刻意不断言 `vaa.main([]) == 0`：搬迁把违规源文件搬到新路径后，同一条违规会
    以新路径进入 new 列表，此时门禁 BLOCK 是正确行为，必须靠解耦消除，不能靠
    `--write-baseline` 把新路径吸收进基线来换取绿灯。
    """
    recorded = vaa.load_baseline()
    assert recorded["ruleId"] == vaa.RULE_ID

    _, stale_entries = vaa.diff(evaluation, recorded, None)
    assert stale_entries == []
    assert vaa.main(["--domain", "content"]) in {0, 1}


def test_evaluation_is_idempotent(roster: opm.ObjectRoster, evaluation: dict) -> None:
    assert vaa._normalized(vaa.evaluate(roster)) == evaluation
