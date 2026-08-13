"""verify_single_track_contracts 的 wire 键与别名双轨拦截合约。

由 test_single_track_contracts__contract__local_contract_test.py（Python 1000
行硬顶治理）按场景拆出：JSON 多键双读/别名教学/兼容分支拦截、`_id` wire 键
与 bson 例外边界、公开身份退役别名与第二真相字段拦截。测试逐字搬移；共享
harness 见 tests/support。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.single_track_contracts_test_support import (
    _load_verifier,
    _scan_fixture,
)

class SingleTrackContractsContractTest(unittest.TestCase):
    def test_detects_aliases_and_versioned_schema_identity(self) -> None:
        module = _load_verifier()
        text = (
            "fields:\n  - name: id\n    aliases: [postId]\n"
            "schemaVersion: quwoquan_data.release/1\n"
        )
        self.assertTrue("aliases:" in text)
        self.assertIsNotNone(module.VERSIONED_INLINE.search(text))

    def test_detects_json_multi_key_decode(self) -> None:
        module = _load_verifier()
        line = "updatedAt: json['updatedAt']?.toString() ?? json['updated_at']?.toString(),"
        match = module.MULTI_KEY_DECODE.search(line)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertNotEqual(match.group("k1"), match.group("k2"))
        same_key = "w = map['coverWidth'] ?? payload['coverWidth'];"
        same = module.MULTI_KEY_DECODE.search(same_key)
        # 同名跨 map：正则要求同一 ident，故不匹配
        self.assertIsNone(same)
        any_ident = "id: (dm['userId'] ?? dm['id'] ?? '').toString(),"
        any_match = module.MULTI_KEY_DECODE.search(any_ident)
        self.assertIsNotNone(any_match)

    def test_detects_doc_dual_track_teaching(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.DOC_DUAL_TRACK_TEACHING.search("允许短期双读旧字段")
        )
        self.assertIsNotNone(
            module.DOC_DUAL_TRACK_TEACHING.search("feature flag 双读")
        )

        contract_inventory = _scan_fixture(
            module,
            "quwoquan_service/contracts/feedback_and_learning.md",
            "体验事件建议进入日志与指标双写或可互相导出。\n",
        )
        self.assertEqual(
            contract_inventory.counts.get("T5_doc_dual_track_teaching"),
            1,
        )
        prohibition_inventory = _scan_fixture(
            module,
            "quwoquan_service/contracts/feedback_and_learning.md",
            "日志和指标只由事件事实派生，禁止向第二事实存储双写。\n",
        )
        self.assertEqual(
            prohibition_inventory.counts.get("T5_doc_dual_track_teaching", 0),
            0,
        )

    def test_runtime_error_decoder_has_no_message_alias_track(self) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/contracts/metadata/_shared/openapi_common.yaml",
                "        message:\n          type: string\n",
            ),
            (
                "quwoquan_service/runtime/errors/errors.go",
                'Message string `json:"message,omitempty"`\n',
            ),
            (
                "quwoquan_app/lib/runtime/errors/cloud_error_mapper.dart",
                "final value = body['reasonMessage'];\n",
            ),
        )
        for relative_path, source in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, source)
                self.assertEqual(
                    inventory.counts.get("runtime_error_message_alias"),
                    1,
                )

        canonical = _scan_fixture(
            module,
            "quwoquan_app/lib/cloud/runtime/errors/cloud_error_mapper.dart",
            "final value = body['userMessage'];\n",
        )
        self.assertEqual(
            canonical.counts.get("runtime_error_message_alias", 0),
            0,
        )

    def test_detects_create_route_extra_compat_branch(self) -> None:
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_app/lib/runtime/di/navigation/app_router.dart",
            "final extra = state.extra is HomepageCanonicalReference;\n",
        )
        self.assertEqual(inventory.counts.get("create_route_extra_compat"), 1)

    def test_client_state_sync_rejects_derived_second_truth_in_business_source(
        self,
    ) -> None:
        module = _load_verifier()
        business_source = _scan_fixture(
            module,
            "quwoquan_app/lib/core/models/client_state_sync.dart",
            "final bool needsRemoteSync;\n",
        )
        self.assertEqual(
            business_source.counts.get("T1_client_state_sync_second_truth"),
            1,
        )

        rejection_evidence = _scan_fixture(
            module,
            "quwoquan_app/lib/core/models/client_state_sync.dart",
            "// Retired needsRemoteSync input must be rejected.\n"
            "if (json.containsKey('needsRemoteSync')) throw FormatException();\n",
        )
        self.assertEqual(
            rejection_evidence.counts.get("T1_client_state_sync_second_truth", 0),
            0,
        )

        test_fixture = _scan_fixture(
            module,
            "quwoquan_app/test/local_contract/client_state_sync_test.dart",
            "const retired = {'needsRemoteSync': false};\n",
        )
        self.assertEqual(
            test_fixture.counts.get("T1_client_state_sync_second_truth", 0),
            0,
        )

    def test_remote_config_rejects_package_version_without_touching_package_semver(
        self,
    ) -> None:
        module = _load_verifier()
        runtime = _scan_fixture(
            module,
            "quwoquan_app/lib/runtime/config/app_remote_config_snapshot.dart",
            "final String packageVersion;\n",
        )
        self.assertEqual(runtime.counts.get("T1_remote_config_dual_identity"), 1)

        pubspec = _scan_fixture(
            module,
            "quwoquan_app/packages/example/pubspec.yaml",
            "name: example\nversion: 1.2.3+4\n",
        )
        self.assertEqual(pubspec.findings, [])

    def test_detects_service_contract_compat_alias_description(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.CONTRACT_COMPAT_ALIAS.search(
                "description: 兼容别名；值与 userHandle 保持一致"
            )
        )
        self.assertIsNotNone(
            module.CONTRACT_COMPAT_ALIAS.search("只有标准名，零兼容别名")
        )

    def test_detects_positive_alias_test_semantics(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.POSITIVE_ALIAS_TEST.search("test('_id alias → id 正确解析'")
        )
        self.assertIsNotNone(
            module.POSITIVE_ALIAS_TEST.search(
                "test('别名输入 likesCount 也能正确投射'"
            )
        )
        self.assertIsNone(
            module.POSITIVE_ALIAS_TEST.search("test('rejects _id alias'")
        )
        self.assertIsNone(
            module.POSITIVE_ALIAS_TEST.search(
                "test('拒绝 likesCount/commentsCount/savesCount alias'"
            )
        )

    def test_scan_file_flags_multi_key_in_temp_dart(self) -> None:
        module = _load_verifier()
        inv = module.Inventory()
        with tempfile.TemporaryDirectory() as tmp:
            # 写入 ROOT 外无法用 scan_file 的 ROOT 相对路径；直接测正则 + CATEGORY 逻辑
            line = "id: (map['_id'] ?? map['id'] ?? '') as String,"
            self.assertIsNotNone(module.MULTI_KEY_DECODE.search(line))
            self.assertEqual(inv.counts.get("multi_key_decode", 0), 0)

    def test_detects_dart_wire_id_key(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(module.DART_WIRE_ID_KEY.search("id: m['_id'] as String,"))
        self.assertIsNotNone(module.GO_JSON_ID_TAG.search('Id string `json:"_id"`'))
        self.assertIsNone(module.GO_JSON_ID_TAG.search('Id string `bson:"_id"`'))

    def test_allows_bson_id_map_but_rejects_application_wire_map(self) -> None:
        module = _load_verifier()
        bson_inventory = _scan_fixture(
            module,
            "quwoquan_service/services/circle-service/tests/local_contract/"
            "circle_management/gathering/application/query__local_contract_test.go",
            'package application\nvar query = bson.M{"_id": "aggregate-1"}\n',
        )
        wire_inventory = _scan_fixture(
            module,
            "quwoquan_service/services/circle-service/internal/"
            "circle_management/gathering/application/query.go",
            'package application\nvar payload = map[string]any{"_id": "aggregate-1"}\n',
        )

        self.assertEqual(bson_inventory.counts.get("wire_id_key", 0), 0)
        self.assertEqual(wire_inventory.counts.get("wire_id_key", 0), 1)

    def test_allows_elasticsearch_bulk_metadata_id_only_in_provider_harness(self) -> None:
        module = _load_verifier()
        lines = [
            "var metadata struct {",
            "  Index struct {",
            '    Index string `json:"_index"`',
            '    ID string `json:"_id"`',
            '  } `json:"index"`',
            "}",
        ]

        self.assertTrue(
            module._is_elasticsearch_bulk_metadata_context(
                "quwoquan_service/services/product-ops-service/tests/local_contract/"
                "product_ops/event_record/elasticsearch_log_sink__local_contract_test.go",
                lines,
                4,
            )
        )
        self.assertFalse(
            module._is_elasticsearch_bulk_metadata_context(
                "quwoquan_service/services/product-ops-service/tests/local_contract/"
                "product_ops/event_record/http_event_dto__local_contract_test.go",
                lines,
                4,
            )
        )

    def test_detects_multi_key_helper_with_id(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.MULTI_KEY_HELPER_ID.search(
                "_firstNonEmpty([map['postId'], map['_id'], map['id']])"
            )
        )

    def test_detects_fixture_dual_id(self) -> None:
        module = _load_verifier()
        self.assertTrue(
            module._json_object_has_dual_id({"_id": "a", "id": "a", "name": "x"})
        )
        self.assertFalse(module._json_object_has_dual_id({"_id": "a", "name": "x"}))

    def test_detects_id_compat_teaching(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.ID_COMPAT_TEACHING.search("支持 _id / id 兼容读取")
        )

    def test_detects_retired_public_identity_aliases(self) -> None:
        module = _load_verifier()
        retired = (
            "/user/{username}",
            "AppRoutePaths.userProfile(username: value)",
            "OtherProfilePage(username: value)",
            "currentUser.username",
            "user.avatarUrlOrAvatar",
        )
        for source in retired:
            self.assertTrue(
                any(
                    pattern.search(source)
                    for pattern in module.PUBLIC_IDENTITY_RETIRED_PATTERNS
                ),
                source,
            )

        retired_user_model = (
            "final String? username;",
            "this.username,",
            "json['username']",
            "'username': username,",
            "final String? avatar;",
            "this.avatar,",
            "json['avatar']",
            "'avatar': avatar,",
        )
        for source in retired_user_model:
            self.assertTrue(
                any(
                    pattern.search(source)
                    for pattern in module.PUBLIC_USER_MODEL_RETIRED_PATTERNS
                ),
                source,
            )

        canonical = (
            "/user/{userHandle}",
            "AppRoutePaths.userProfile(userHandle: value)",
            "final String? avatarUrl;",
        )
        for source in canonical:
            self.assertFalse(
                any(
                    pattern.search(source)
                    for pattern in (
                        *module.PUBLIC_IDENTITY_RETIRED_PATTERNS,
                        *module.PUBLIC_USER_MODEL_RETIRED_PATTERNS,
                    )
                ),
                source,
            )


if __name__ == "__main__":
    unittest.main()
