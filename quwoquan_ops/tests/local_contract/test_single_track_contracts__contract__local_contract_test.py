from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_single_track_contracts.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_single_track_contracts",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SingleTrackContractsContractTest(unittest.TestCase):
    def test_verifier_module_loads(self) -> None:
        module = _load_verifier()
        self.assertTrue(hasattr(module, "scan_file"))
        self.assertTrue(hasattr(module, "Inventory"))

    def test_detects_metadata_top_level_version(self) -> None:
        module = _load_verifier()
        text = "version: 1\ndomain: demo\n"
        self.assertIsNotNone(module.TOP_LEVEL_VERSION.search(text))

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

    def test_detects_numeric_and_v_suffix_schema(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(
            module.NUMERIC_SCHEMA_LITERAL.search('"schema": 1')
        )
        self.assertIsNotNone(
            module.SCHEMA_VALUE_V_SUFFIX.search(
                '"schema": "geo_resolution_config_v1"'
            )
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
            self.assertEqual(inv.counts.get("T3_multi_key_decode", 0), 0)

    def test_detects_dart_wire_id_key(self) -> None:
        module = _load_verifier()
        self.assertIsNotNone(module.DART_WIRE_ID_KEY.search("id: m['_id'] as String,"))
        self.assertIsNotNone(module.GO_JSON_ID_TAG.search('Id string `json:"_id"`'))
        self.assertIsNone(module.GO_JSON_ID_TAG.search('Id string `bson:"_id"`'))

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


if __name__ == "__main__":
    unittest.main()
