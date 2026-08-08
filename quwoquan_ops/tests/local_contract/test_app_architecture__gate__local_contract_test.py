"""`verify_app_architecture.py`（端侧对象化架构门禁 v1）的本地契约。

本测试锁定五件事：

1. 规则来源单一：顶层白名单与对象归属都必须从 `object_path_map.py` 与
   `quwoquan_app/l10n.yaml` 派生，门禁不得内置第二套路径反推或 domain 名单。
2. 跨对象只能依赖目标对象 `application/public/**`；同对象与横切代码不得误报。
3. strict-zero 语义：任一 R1-R5 违规都必须阻断，`--domain` 只收窄 R2/R3/R4
   的检查范围，共享的 R1/R5 在任何 scope 下都全量求值。
4. 迁移期 baseline 已退休：文件必须不存在，CLI 不得提供重建或吸收入口。
5. `runtime/di/**` 只做装配：Provider/factory/typed WidgetBuilder/composition
   合法，Widget 类、业务文案与业务状态是不可基线化的共享绝对违规。

这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`：端侧对象化目录尚未搬迁，
本门禁只提供其中的静态约束与基线部分，不代表 OPEN-001 关闭。
"""
from __future__ import annotations

import ast
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
GATE_SOURCE_PATH = ROOT / "quwoquan_ops/gate/verify_app_architecture.py"
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


def test_lib_top_level_whitelist_and_attribution_roots_are_the_same_set(
    roster: opm.ObjectRoster,
) -> None:
    """R1 白名单与派生器的横切根必须是同一份集合，不允许第二份「合法顶层」清单。

    分叉的后果不是本门禁误报，而是下游归属整批塌陷：l10n 根曾经只登记在这里，
    `object_path_map` 不认识它，于是 `lib/l10n/**` 同时是「R1 合法顶层」与
    「待搬去 lib/runtime/l10n 的横切件」，status 停在 `cross_cutting`，
    `verify_canonical_coverage` 把它们连同顶层入口共 28 个文件判成无主源码，
    App 覆盖率 scope 一个单元都发现不了。收敛前本断言失败，收敛后才通过。
    """
    allowed = vaa.allowed_top_level_directories(roster)

    assert allowed == {opm.APP_SERVICE_ROOT_SEGMENT} | set(
        opm.APP_CROSS_CUTTING_ROOTS
    )
    # l10n 根仍必须由 l10n.yaml 派生，只是它现在经 APP_CROSS_CUTTING_ROOTS 表达。
    assert vaa.l10n_top_level_segment() in opm.APP_CROSS_CUTTING_ROOTS


def test_entry_file_rule_has_exactly_one_definition() -> None:
    """入口文件形态只能有一处定义；本门禁复用派生器的常量而不是另写一份正则。

    两份正则会让「R1 认可的顶层入口」与「派生器认可的终态位置」再次分叉，
    重演 `lib/main*.dart` 被推去 `lib/runtime/main.dart` 的无主源码事故。

    这里必须断言**源码形态**而不是 `vaa.TOP_LEVEL_ENTRY_RE is opm.APP_ENTRY_FILE_RE`：
    `re.compile` 对同一 pattern 返回缓存里的同一个对象，所以两处各写一遍
    `re.compile(r"^main...")` 也会通过 `is` 断言，那样的测试没有鉴别力。
    """
    tree = ast.parse(GATE_SOURCE_PATH.read_text(encoding="utf-8"))
    bindings = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TOP_LEVEL_ENTRY_RE"
            for target in node.targets
        )
    ]

    assert len(bindings) == 1, "TOP_LEVEL_ENTRY_RE 必须只被赋值一次"
    value = bindings[0]
    assert isinstance(value, ast.Attribute) and value.attr == "APP_ENTRY_FILE_RE", (
        "TOP_LEVEL_ENTRY_RE 必须直接复用 object_path_map.APP_ENTRY_FILE_RE，"
        "不得在本门禁里另行 re.compile 一份入口正则"
    )
    assert vaa.TOP_LEVEL_ENTRY_RE is opm.APP_ENTRY_FILE_RE


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


def test_runtime_di_purity_allows_provider_factory_builder_and_composition(
    tmp_path: Path,
) -> None:
    runtime_di = tmp_path / "runtime/di"
    runtime_di.mkdir(parents=True)
    (runtime_di / "feature_dependencies.dart").write_text(
        """// class FakeCard extends StatelessWidget {}
const fakeSource = 'ProfileText.title Text( business State';
final featureProvider = Provider<FeatureService>((ref) => createFeatureService());
FeatureService createFeatureService() => FeatureService();
typedef FeatureWidgetBuilder = Widget Function(BuildContext context);
final class FeatureComposition {
  const FeatureComposition(this.pageBuilder);
  final WidgetBuilder pageBuilder;
}
abstract final class ContentMediaCreationComposition {
  static Widget camera({required CameraCaptureModePolicy modePolicy}) {
    return CameraCapturePage(modePolicy: modePolicy);
  }
  static Widget mediaPicker({required MediaPickerPort mediaPickerPort}) {
    return CreateMediaPickerPage(mediaPickerPort: mediaPickerPort);
  }
}
""",
        encoding="utf-8",
    )

    assert vaa.scan_runtime_di_presentation_purity_violations(runtime_di) == []


def test_runtime_di_purity_rejects_widgets_business_copy_and_state(
    tmp_path: Path,
) -> None:
    runtime_di = tmp_path / "runtime/di"
    runtime_di.mkdir(parents=True)
    (runtime_di / "feature_presentation.dart").write_text(
        """class FeatureCard extends StatelessWidget {}
class FeaturePage extends StatefulWidget {}
class FeaturePanel extends ConsumerWidget {}
class FeatureFlow extends ConsumerStatefulWidget {}
class FeatureState {}
enum LoadingState { idle }
const heading = ProfileText.featureTitle;
Widget buildCopy() => Text('hello');
final spec = FeatureSpec(title: 'literal title');
""",
        encoding="utf-8",
    )

    assert vaa.scan_runtime_di_presentation_purity_violations(runtime_di) == [
        (
            "runtime/di/feature_presentation.dart: business_copy "
            "[literal, text_catalog, text_widget]"
        ),
        (
            "runtime/di/feature_presentation.dart: business_state "
            "[class FeatureState, enum LoadingState]"
        ),
        (
            "runtime/di/feature_presentation.dart: widget_class "
            "[FeatureCard extends StatelessWidget, "
            "FeatureFlow extends ConsumerStatefulWidget, "
            "FeaturePage extends StatefulWidget, FeaturePanel extends ConsumerWidget]"
        ),
    ]


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
# strict-zero 语义
# ---------------------------------------------------------------------------


def test_strict_zero_reports_every_observed_violation() -> None:
    current = vaa._normalized(
        {
            "shared": {vaa.RULE_TOP_LEVEL: ["legacy/"]},
            "domains": {
                "content": {
                    vaa.RULE_TARGET_REVERSE_IMPORT: [
                        "runtime/a.dart -> content/b.dart"
                    ]
                }
            },
        }
    )

    assert vaa.violation_entries(current, None) == [
        f"{vaa.RULE_TOP_LEVEL}: legacy/",
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: "
        "runtime/a.dart -> content/b.dart",
    ]


def test_domain_scope_narrows_domain_rules_but_keeps_shared_rules() -> None:
    current = vaa._normalized(
        {
            "shared": {vaa.RULE_TOP_LEVEL: ["legacy/"]},
            "domains": {
                "content": {
                    vaa.RULE_TARGET_REVERSE_IMPORT: [
                        "runtime/a.dart -> content/b.dart"
                    ]
                },
                "chat": {
                    vaa.RULE_TARGET_REVERSE_IMPORT: [
                        "runtime/a.dart -> chat/b.dart"
                    ]
                },
            },
        }
    )

    assert vaa.violation_entries(current, "content") == [
        f"{vaa.RULE_TOP_LEVEL}: legacy/",
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: "
        "runtime/a.dart -> content/b.dart",
    ]


def test_cross_object_rule_is_strict_zero() -> None:
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
    assert vaa.violation_entries(current, None) == [
        f"{vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT}[chat]: {edge}"
    ]


def test_runtime_di_purity_is_shared_strict_zero() -> None:
    finding = (
        "runtime/di/presentation/card.dart: widget_class "
        "[Card extends StatelessWidget]"
    )
    current = vaa._normalized(
        {
            "shared": {vaa.RULE_RUNTIME_DI_PRESENTATION_PURITY: [finding]},
            "domains": {},
        }
    )
    assert vaa.violation_entries(current, "content") == [
        f"{vaa.RULE_RUNTIME_DI_PRESENTATION_PURITY}: {finding}"
    ]


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
    assert vaa.violation_entries(current, "chat") == [
        f"{vaa.RULE_CROSS_OBJECT_PRIVATE_IMPORT}[chat]: {edge}"
    ]
    assert vaa.violation_entries(current, "content") == []


def test_retired_baseline_must_remain_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)
    vaa.verify_retired_baseline_absent()

    baseline_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="retired baseline must remain absent"):
        vaa.verify_retired_baseline_absent()


def test_cli_has_no_baseline_write_or_allowance_path() -> None:
    source = GATE_SOURCE_PATH.read_text(encoding="utf-8")

    assert "--write-baseline" not in source
    assert "def write_baseline" not in source
    assert "def load_baseline" not in source


def test_strict_zero_cli_blocks_observed_violations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    roster: opm.ObjectRoster,
) -> None:
    monkeypatch.setattr(vaa, "BASELINE_PATH", tmp_path / "retired.json")
    monkeypatch.setattr(vaa, "load_roster", lambda: roster)
    monkeypatch.setattr(
        vaa,
        "evaluate",
        lambda _: {
            "shared": {vaa.RULE_TOP_LEVEL: ["legacy/"]},
            "domains": {},
        },
    )

    assert vaa.main([]) == 1


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
# 仓库 strict-zero 事实
# ---------------------------------------------------------------------------


def test_repository_has_no_architecture_baseline() -> None:
    assert not vaa.BASELINE_PATH.exists()


def test_repository_is_strict_zero_in_all_and_domain_scope(
    evaluation: dict,
) -> None:
    assert vaa.violation_entries(evaluation, None) == []
    assert vaa.main([]) == 0
    assert vaa.main(["--domain", "content"]) == 0


def test_evaluation_is_idempotent(roster: opm.ObjectRoster, evaluation: dict) -> None:
    assert vaa._normalized(vaa.evaluate(roster)) == evaluation
