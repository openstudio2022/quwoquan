"""`object_path_map.py` 派生规则的本地契约（object view / baseline / 目标路径组）。

由 1000 行硬顶拆分自 test_object_path_map__derivation__local_contract_test.py；
测试逐字搬移。本组测试用内联最小 graph 自建 roster，不依赖共享 fixture。

与原文件相同，这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm


def test_required_app_layers_follow_real_client_capabilities_not_cloud_kind() -> None:
    assert opm.required_app_layers(
        has_client_contract_operation=False,
        owns_page=False,
        has_client_invariant=False,
    ) == ()
    assert opm.required_app_layers(
        has_client_contract_operation=True,
        owns_page=False,
        has_client_invariant=False,
    ) == ("adapters", "application")
    assert opm.required_app_layers(
        has_client_contract_operation=False,
        owns_page=True,
        has_client_invariant=False,
    ) == ("application", "presentation")
    assert opm.required_app_layers(
        has_client_contract_operation=False,
        owns_page=False,
        has_client_invariant=True,
    ) == ("domain",)


def test_pure_cloud_object_does_not_get_empty_app_layer_obligations() -> None:
    graph = {
        "objects": [
            {
                "id": "assistant.assistant_policy_release",
                "domain": "assistant",
                "kind": "aggregate_root",
                "sourcePath": "assistant/assistant/assistant_policy_release",
            },
            {
                "id": "gateway.rate_limit_bucket",
                "domain": "gateway",
                "kind": "runtime_session",
                "sourcePath": "gateway/gateway/rate_limit_bucket",
            },
        ],
        "operations": [],
        "businessObjectMaps": [],
    }
    roster = opm.ObjectRoster(graph)
    view = opm.build_object_view(roster, [], [], {}, [])

    for object_id in (
        "assistant.assistant_policy_release",
        "gateway.rate_limit_bucket",
    ):
        assert view[object_id]["hasAppClientContractOperation"] is False
        assert view[object_id]["ownsPage"] is False
        assert view[object_id]["requiredAppLayers"] == []
        assert view[object_id]["missingAppLayers"] == []


def test_client_contract_operation_requires_application_and_adapter() -> None:
    graph = {
        "objects": [
            {
                "id": "content.post",
                "domain": "content",
                "kind": "aggregate_root",
                "sourcePath": "content/content/post",
            }
        ],
        "operations": [
            {
                "id": "content.post.GetPost",
                "objectId": "content.post",
                "clientContract": {"responseType": "ContentPostViewData"},
            },
            {
                "id": "content.post.InternalProjectPost",
                "objectId": "content.post",
            },
        ],
        "businessObjectMaps": [],
    }
    roster = opm.ObjectRoster(graph)
    view = opm.build_object_view(roster, [], [], {}, [])
    post = view["content.post"]

    assert post["appClientContractOperationIds"] == ["content.post.GetPost"]
    assert post["requiredAppLayers"] == ["adapters", "application"]
    assert post["missingAppLayers"] == ["adapters", "application"]


def test_page_participant_does_not_become_the_presentation_owner() -> None:
    graph = {
        "objects": [
            {
                "id": "content.post",
                "domain": "content",
                "kind": "aggregate_root",
                "sourcePath": "content/content/post",
            },
            {
                "id": "content.comment",
                "domain": "content",
                "kind": "aggregate_root",
                "sourcePath": "content/content/comment",
            },
        ],
        "operations": [],
        "businessObjectMaps": [],
    }
    roster = opm.ObjectRoster(graph)
    page_path = (
        "quwoquan_app/lib/service/content_service/content/post/presentation/"
        "example_page.dart"
    )
    app_rows = [
        {
            "objectId": "content.post",
            "role": "production",
            "targetLayer": "presentation",
            "path": page_path,
        }
    ]
    page_claims = {page_path: ["content.comment", "content.post"]}
    pages = [
        {
            "path": page_path,
            "objectIds": ["content.comment", "content.post"],
        }
    ]
    view = opm.build_object_view(roster, [], app_rows, page_claims, pages)

    owner = view["content.post"]
    participant = view["content.comment"]
    assert opm.derive_page_physical_owner(page_path, roster) == "content.post"
    assert owner["ownsPage"] is True
    assert owner["requiredAppLayers"] == ["application", "presentation"]
    assert owner["missingAppLayers"] == ["application"]
    assert participant["claimedByPage"] is True
    assert participant["ownsPage"] is False
    assert participant["requiredAppLayers"] == []
    assert participant["missingAppLayers"] == []


def test_domain_directory_does_not_invent_a_client_invariant_requirement() -> None:
    graph = {
        "objects": [
            {
                "id": "content.post",
                "domain": "content",
                "kind": "aggregate_root",
                "sourcePath": "content/content/post",
            }
        ],
        "operations": [],
        "businessObjectMaps": [],
    }
    roster = opm.ObjectRoster(graph)
    app_rows = [
        {
            "objectId": "content.post",
            "role": "production",
            "targetLayer": "domain",
            "path": "quwoquan_app/lib/service/content_service/content/post/domain/"
            "post_state.dart",
        }
    ]
    view = opm.build_object_view(roster, [], app_rows, {}, [])

    assert list(view["content.post"]["app"]["layers"]) == ["domain"]
    assert view["content.post"]["requiredAppLayers"] == []
    assert view["content.post"]["missingAppLayers"] == []


def test_cross_cutting_app_sources_are_separate_from_unowned_business_sources() -> None:
    roster = opm.ObjectRoster(
        {"objects": [], "operations": [], "businessObjectMaps": []}
    )
    app_rows = [
        {
            "path": "quwoquan_app/lib/runtime/transport/cloud_client.dart",
            "method": "cross_cutting",
            "status": "canonical_cross_cutting",
            "crossCuttingRoot": "runtime",
        },
        {
            "path": "quwoquan_app/lib/core/config/runtime_config.dart",
            "method": "cross_cutting",
            "status": "cross_cutting",
            "crossCuttingRoot": "runtime",
        },
        {
            "path": "quwoquan_app/lib/legacy/unknown.dart",
            "method": "unowned",
            "status": "unowned",
        },
    ]

    baseline = opm.build_baseline(roster, [], app_rows, [], {})

    assert baseline["appBusinessObjectClaimedFileTotal"] == 0
    assert baseline["appCrossCuttingFileTotal"] == 2
    assert baseline["appCanonicalCrossCuttingFileTotal"] == 1
    assert baseline["appPendingCrossCuttingFileTotal"] == 1
    assert baseline["appCrossCuttingFilesByRoot"] == {"runtime": 2}
    assert baseline["appUnownedFileTotal"] == 1
    assert baseline["appUnownedFilesByStatus"] == {"unowned": 1}


def test_target_paths_follow_the_object_shaped_layout() -> None:
    assert (
        opm.derive_app_target_path(
            "chat", "chat", "conversation", "adapters", "conversation_remote.dart"
        )
        == "quwoquan_app/lib/service/chat_service/chat/conversation/adapters/"
        "conversation_remote.dart"
    )
    assert opm.derive_app_test_target_path(
        "local_contract", "chat", "chat", "conversation", "x_test.dart"
    ) == (
        "quwoquan_app/test/local_contract/service/chat_service/chat/conversation/x_test.dart"
    )
    # 横切面只有两个落点，且剥离现状 `core/` 前缀与目标根自身的段。
    assert opm.derive_app_cross_cutting_target_path(
        "runtime", ("core", "platform", "x.dart")
    ) == ("quwoquan_app/lib/runtime/platform/x.dart")
    assert opm.derive_app_cross_cutting_target_path(
        "design_system", ("core", "design_system", "tokens.dart")
    ) == ("quwoquan_app/lib/design_system/tokens.dart")


def test_context_to_service_is_derived_for_same_name_renamed_and_split_domains() -> None:
    mapping = opm.context_to_service()

    assert mapping["chat"] == "chat_service"
    assert mapping["account"] == "user_service"
    assert mapping["product_ops"] == "product_ops_service"
    assert mapping["platform_ops"] == "platform_ops"
    assert opm.app_service_for_context("ops", "product_ops") != (
        opm.app_service_for_context("ops", "platform_ops")
    )


def test_python_and_go_evidence_loaders_share_the_service_shape_contract() -> None:
    """锁住两份独立实现，防止一侧改路径后另一侧静默扫空 evidence。"""
    source = (
        ROOT / "quwoquan_service/internal/metadata/load/evidence.go"
    ).read_text(encoding="utf-8")
    root_match = re.search(r'appServiceRoot\s*=\s*"([^"]+)"', source)

    assert root_match is not None
    assert root_match.group(1) == opm.APP_SERVICE_ROOT_SEGMENT
    assert opm.APP_TARGET_SHAPE_SEGMENTS == 5
    assert opm.APP_TEST_TARGET_SHAPE_SEGMENTS == 4
    assert re.search(
        r'"lib"\s*,\s*appServiceRoot\s*,\s*service\s*,\s*context\s*,'
        r"\s*objectSegment",
        source,
    )
    assert re.search(
        r'"test"\s*,\s*testLayerUserAcceptance\s*,\s*appServiceRoot\s*,'
        r"\s*appServiceSegment\(serviceRoot\)\s*,\s*context\s*,\s*objectSegment",
        source,
    )
