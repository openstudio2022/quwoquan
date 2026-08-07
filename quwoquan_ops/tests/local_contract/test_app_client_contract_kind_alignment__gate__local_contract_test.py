"""`verify_app_client_contract_kind_alignment.py` 的判据契约。

这里锁定的是「端侧 kind 义务」的判据本身，而不是某次扫描的具体数字：判据一旦静默
放宽，端侧就会重新把只读 / 只追加 / 会话类对象当成可变聚合消费，而云侧完全看不到。

每条规则都必须同时被正例（真实仓库现状必须通过）与负例（构造违规必须 FAIL）钉住；
只有正例会让「把判据改成恒真」也一样绿。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_app_client_contract_kind_alignment as gate


def _facts(**overrides) -> gate.ObjectFacts:
    payload = {
        "object_id": "content.sample",
        "kind": "aggregate_root",
        "access_commands": "aggregate_facade",
        "client_operation_kinds": {},
        "app_files": (),
        "owns_page": False,
    }
    payload.update(overrides)
    return gate.ObjectFacts(**payload)


def _dart(path: str, layer: str | None, text: str) -> gate.AppFile:
    return gate.AppFile(path=path, layer=layer, text=text)


def _rules(violations) -> set[str]:
    return {item.rule for item in violations}


# ---------------------------------------------------------------------------
# 正例：真实仓库现状
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def repository_objects() -> list[gate.ObjectFacts]:
    return gate.collect()


def test_repository_currently_satisfies_every_kind_obligation(
    repository_objects: list[gate.ObjectFacts],
) -> None:
    violations = gate.evaluate(repository_objects)
    assert violations == [], "\n".join(item.render() for item in violations)


def test_scan_covers_every_target_kind_with_a_positive_object_count(
    repository_objects: list[gate.ObjectFacts],
) -> None:
    """扫描范围不得被缩小：四类目标 kind 必须都有实测对象。"""
    by_kind: dict[str, int] = {}
    for facts in repository_objects:
        by_kind[facts.kind] = by_kind.get(facts.kind, 0) + 1
    for kind in (
        "append_only_fact",
        "external_reference",
        "projection",
        "runtime_session",
    ):
        assert by_kind.get(kind, 0) > 0, f"{kind} 实测对象数为 0，扫描范围被缩小"
    assert set(by_kind) <= set(gate.ACCESS_COMMANDS_BY_KIND)


def test_access_commands_stay_derived_from_kind_on_the_cloud_side(
    repository_objects: list[gate.ObjectFacts],
) -> None:
    """云侧 ``access.commands`` 必须仍然是 kind 的函数——端侧判据依赖这一点。"""
    for facts in repository_objects:
        assert facts.access_commands == gate.ACCESS_COMMANDS_BY_KIND[facts.kind], (
            f"{facts.object_id} access.commands 漂移: {facts.access_commands}"
        )


# ---------------------------------------------------------------------------
# 负例 K0：扫描前置条件
# ---------------------------------------------------------------------------


def test_missing_app_scan_root_blocks(tmp_path: Path) -> None:
    with pytest.raises(gate.GateInputError):
        gate.collect(repo_root=tmp_path)


def test_missing_cloud_contracts_scan_root_blocks(tmp_path: Path) -> None:
    with pytest.raises(gate.GateInputError):
        gate.load_access_commands(tmp_path)


def test_zero_scanned_objects_is_itself_a_violation() -> None:
    violations = gate.evaluate([])
    assert [item.rule for item in violations] == ["scan_scope"]


# ---------------------------------------------------------------------------
# 负例 K1：operation kind 与 access.commands
# ---------------------------------------------------------------------------


def test_client_command_on_a_readonly_access_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="chat.chat_inbox_view",
                kind="projection",
                access_commands="none",
                client_operation_kinds={"query": 1, "command": 1},
            )
        ]
    )
    assert "client_operation_kind_vs_access_commands" in _rules(violations)
    assert "readonly_kind_client_command_count" in _rules(violations)


def test_aggregate_command_on_a_session_facade_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="realtime.connection",
                kind="runtime_session",
                access_commands="session_facade",
                client_operation_kinds={"session": 2, "command": 1},
            )
        ]
    )
    assert _rules(violations) == {"client_operation_kind_vs_access_commands"}


def test_access_commands_drifting_from_kind_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="content.content_behavior_fact",
                kind="append_only_fact",
                access_commands="aggregate_facade",
            )
        ]
    )
    assert _rules(violations) == {"client_operation_kind_vs_access_commands"}


def test_unregistered_kind_blocks_instead_of_passing_silently() -> None:
    violations = gate.evaluate([_facts(kind="mystery_kind", access_commands="none")])
    assert _rules(violations) == {"client_operation_kind_vs_access_commands"}


# ---------------------------------------------------------------------------
# 负例 K2/K3：append_only_fact 端侧写面形状
# ---------------------------------------------------------------------------


def test_append_only_fact_with_aggregate_command_writer_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="content.content_behavior_fact",
                kind="append_only_fact",
                access_commands="append_only_sink",
                client_operation_kinds={"command": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/content_service/content/"
                        "content_behavior_fact/application/public/writer.dart",
                        "application",
                        "abstract interface class ContentBehaviorCommandWriter {\n"
                        "  Future<void> reportBehaviors(Command command);\n"
                        "}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"append_only_fact_append_port_shape"}


def test_append_only_fact_with_update_semantics_method_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="assistant.assistant_learning_fact",
                kind="append_only_fact",
                access_commands="append_only_sink",
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/assistant_service/assistant/"
                        "assistant_learning_fact/application/appender.dart",
                        "application",
                        "abstract interface class AssistantLearningFactAppender {\n"
                        "  Future<void> appendFact(Fact fact);\n"
                        "  Future<void> updateProgress(String id, int page);\n"
                        "}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"append_only_fact_append_port_shape"}


def test_append_only_fact_append_port_and_listener_registration_pass() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="tag.tag_feedback_fact",
                kind="append_only_fact",
                access_commands="append_only_sink",
                client_operation_kinds={"command": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/tag_service/tag/tag_feedback_fact/"
                        "application/tag_feedback_fact_appender.dart",
                        "application",
                        "abstract interface class TagFeedbackFactAppender {\n"
                        "  Future<Ack> reportTagFeedback(Command command);\n"
                        "  void removeInboxListener(void Function() listener);\n"
                        "}\n",
                    ),
                ),
            )
        ]
    )
    assert violations == []


# ---------------------------------------------------------------------------
# 负例 K4：runtime_session 端侧形状
# ---------------------------------------------------------------------------


def test_runtime_session_owning_presentation_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="realtime.connection",
                kind="runtime_session",
                access_commands="session_facade",
                client_operation_kinds={"session": 2, "query": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/realtime_gateway/realtime/"
                        "connection/presentation/realtime_connection_notifier.dart",
                        "presentation",
                        "class RealtimeConnectionNotifier {}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"forbidden_app_layer_for_kind"}


def test_append_only_fact_owning_presentation_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="ops.event_record",
                kind="append_only_fact",
                access_commands="append_only_sink",
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/product_ops_service/product_ops/"
                        "event_record/presentation/event_record_page.dart",
                        "presentation",
                        "class EventRecordPage {}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"forbidden_app_layer_for_kind"}


def test_external_reference_owning_domain_layer_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="integration.location",
                kind="external_reference",
                access_commands="none",
                client_operation_kinds={"query": 2},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/integration_service/"
                        "external_integration/location/domain/location_state.dart",
                        "domain",
                        "class LocationState {}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"forbidden_app_layer_for_kind"}


def test_runtime_session_registered_as_page_owner_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="assistant.page_context",
                kind="runtime_session",
                access_commands="session_facade",
                owns_page=True,
                page_paths=(
                    "quwoquan_app/lib/service/assistant_service/assistant/"
                    "page_context/presentation/page_context_page.dart",
                ),
            )
        ]
    )
    assert _rules(violations) == {"runtime_session_app_shape"}


def test_runtime_session_with_application_only_shape_passes() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="realtime.connection",
                kind="runtime_session",
                access_commands="session_facade",
                client_operation_kinds={"session": 2, "query": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/realtime_gateway/realtime/"
                        "connection/application/realtime_connection_notifier.dart",
                        "application",
                        "class RealtimeConnectionNotifier {}\n",
                    ),
                ),
            )
        ]
    )
    assert violations == []


# ---------------------------------------------------------------------------
# 负例 K5：projection 本地可变路径
# ---------------------------------------------------------------------------


def test_projection_with_its_own_command_writer_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="chat.chat_inbox_view",
                kind="projection",
                access_commands="none",
                client_operation_kinds={"query": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/chat_service/chat/chat_inbox_view/"
                        "application/public/chat_inbox_command_writer.dart",
                        "application",
                        "abstract interface class ChatInboxCommandWriter {\n"
                        "  Future<void> markRead(String id);\n"
                        "}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"projection_local_mutation_path"}


def test_projection_with_local_patch_path_blocks() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="chat.chat_inbox_view",
                kind="projection",
                access_commands="none",
                client_operation_kinds={"query": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/chat_service/chat/chat_inbox_view/"
                        "application/public/chat_inbox_cache.dart",
                        "application",
                        "abstract interface class ChatInboxCache {\n"
                        "  List<Entry> readInbox();\n"
                        "  void patchInbox(String id, Patch patch);\n"
                        "}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"projection_local_mutation_path"}


def test_projection_readonly_snapshot_with_volatile_hint_passes() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="chat.chat_inbox_view",
                kind="projection",
                access_commands="none",
                client_operation_kinds={"query": 1},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/chat_service/chat/chat_inbox_view/"
                        "application/public/chat_inbox_cache.dart",
                        "application",
                        "abstract interface class ChatInboxCache {\n"
                        "  List<Entry> readInbox();\n"
                        "  void replaceInbox(Iterable<Entry> items);\n"
                        "  void applyOptimisticInboxHint(String id, Hint hint);\n"
                        "  void addInboxListener(void Function() listener);\n"
                        "}\n",
                    ),
                ),
            )
        ]
    )
    assert violations == []


# ---------------------------------------------------------------------------
# 负例 K6：external_reference 本地 authoritative 持久化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    ["package:hive_flutter", "SharedPreferences", "package:sqflite"],
)
def test_external_reference_with_local_persistence_blocks(marker: str) -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="integration.location",
                kind="external_reference",
                access_commands="none",
                client_operation_kinds={"query": 2},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/integration_service/"
                        "external_integration/location/adapters/location_cache.dart",
                        "adapters",
                        f"import '{marker}/x.dart';\n"
                        "final class LocationCache {}\n",
                    ),
                ),
            )
        ]
    )
    assert _rules(violations) == {"external_reference_local_authoritative_state"}


def test_external_reference_read_through_only_passes() -> None:
    violations = gate.evaluate(
        [
            _facts(
                object_id="integration.location",
                kind="external_reference",
                access_commands="none",
                client_operation_kinds={"query": 2},
                app_files=(
                    _dart(
                        "quwoquan_app/lib/service/integration_service/"
                        "external_integration/location/adapters/location_remote.dart",
                        "adapters",
                        "final class RemoteLocationQuery {}\n",
                    ),
                ),
            )
        ]
    )
    assert violations == []


# ---------------------------------------------------------------------------
# 规则表与 object_path_map 同源
# ---------------------------------------------------------------------------


def test_forbidden_app_layers_stay_mirrored_with_object_path_map() -> None:
    """禁止层必须与派生器同源，否则两处会各自解释同一个 kind 义务。"""
    from quwoquan_ops.gate import object_path_map as opm

    for kind, layers in gate.KIND_FORBIDDEN_APP_LAYERS_MIRROR.items():
        assert opm.FORBIDDEN_APP_LAYERS_BY_KIND.get(kind) == layers, (
            f"{kind} 的端侧禁止层在两处漂移"
        )


def test_session_and_append_port_naming_norms_are_published() -> None:
    from quwoquan_ops.gate import object_path_map as opm

    assert opm.APP_APPEND_PORT_NAMING == gate.APP_APPEND_PORT_NAMING
    assert opm.APP_SESSION_PORT_NAMING == gate.APP_SESSION_PORT_NAMING
