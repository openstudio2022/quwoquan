from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_object_relation_edge_type_contract.py"
SPEC = importlib.util.spec_from_file_location(
    "object_relation_edge_type_contract", VERIFIER_PATH
)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


class ObjectRelationEdgeTypeContractTest(unittest.TestCase):
    def test_repository_contract_is_exactly_aligned(self) -> None:
        failures = verifier.validate(
            shared_values=verifier.load_shared_values(verifier.TYPES_PATH),
            go_values=verifier.load_go_values(verifier.GO_PATH),
            dart_values=verifier.load_dart_values(verifier.DART_PATH),
            dart_labelled=verifier.load_dart_labelled_values(verifier.DART_LABEL_PATH),
        )

        self.assertEqual(failures, [])

    def test_spatial_edge_types_reached_every_consumer(self) -> None:
        shared = verifier.load_shared_values(verifier.TYPES_PATH)

        # 本轮新增的四类空间边是整改目标本身：任一消费方漏掉就退回到「实体间无地理包含」。
        for spatial in ("located_in", "part_of", "near", "route_stop"):
            self.assertIn(spatial, shared)
        self.assertIn("geo_proximity", shared)

    def test_half_vocabulary_fails_closed(self) -> None:
        # 复现整改前的真实形态：生产方与消费方各持一半词表，彼此都不报错。
        failures = verifier.validate(
            shared_values=("author_of", "tag_overlap", "located_in"),
            go_values=("tag_overlap",),
            dart_values=("author_of",),
            dart_labelled=("authorOf",),
        )

        self.assertEqual(len(failures), 3)
        self.assertTrue(any("Go ObjectRelationEdgeType drift" in item for item in failures))
        self.assertTrue(any("Dart ObjectRelationEdgeType drift" in item for item in failures))
        self.assertTrue(any("label switch is missing arms" in item for item in failures))

    def test_new_type_without_a_presentation_label_fails_closed(self) -> None:
        failures = verifier.validate(
            shared_values=("author_of", "route_stop"),
            go_values=("author_of", "route_stop"),
            dart_values=("author_of", "route_stop"),
            dart_labelled=("authorOf",),
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("routeStop", failures[0])

    def test_go_constant_missing_from_the_ordered_slice_is_a_gap(self) -> None:
        source = verifier.GO_PATH.read_text(encoding="utf-8")
        # 常量存在但没进有序切片，等于该类型不会出现在 BSON $in 过滤里，读端直接漏掉它。
        self.assertIn("EdgeTypeRouteStop,", source)


if __name__ == "__main__":
    unittest.main()
