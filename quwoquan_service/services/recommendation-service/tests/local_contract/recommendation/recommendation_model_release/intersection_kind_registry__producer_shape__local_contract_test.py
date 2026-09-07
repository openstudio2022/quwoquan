#!/usr/bin/env python3
"""spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[7]
SCRIPT = (
    REPO_ROOT
    / "quwoquan_service"
    / "scripts"
    / "recommendation-service"
    / "recommendation"
    / "recommendation_model_release"
    / "verify_intersection_kind_registry.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_intersection_kind_registry",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 源码树禁止 __pycache__；加载被测门禁脚本时不得写字节码。
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class IntersectionKindRegistryProducerShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def valid_shapes(self) -> dict:
        return {
            # outputObjectKinds 与 outputKinds 各自登记的 objectKind 交叉校验需要 kinds 本体。
            "kinds": [{"kind": "coVisitedEntity", "objectKind": "place"}],
            "factProducerShapes": {
                "declared_visit": {
                    "visibility": "intersection",
                    "inputRefs": ["content.post.visitedAt"],
                    "outputKinds": ["coVisitedEntity"],
                    "outputObjectKinds": ["place"],
                    "outputTaxonomyRoots": [],
                },
                "capture_facts": {
                    "visibility": "recommendation_only",
                    "inputRefs": ["media.media_asset.captureMetadata"],
                    "outputKinds": [],
                    "outputObjectKinds": [],
                    "outputTaxonomyRoots": ["Topic/摄影"],
                },
            }
        }

    def test_accepts_structured_intersection_and_recommendation_shapes(self) -> None:
        shapes = self.verifier.validate_fact_producer_shapes(
            self.valid_shapes(),
            object_kinds={"place"},
            registered_kinds={"coVisitedEntity"},
        )
        self.assertEqual(set(shapes), {"declared_visit", "capture_facts"})

    def test_intersection_shape_object_kinds_must_match_its_kinds(self) -> None:
        # 生产者 shape 声明的主对象 kind 与 kind 本体不一致（例如经历交集主对象是人却登记 gathering）时阻断。
        data = copy.deepcopy(self.valid_shapes())
        data["factProducerShapes"]["declared_visit"]["outputObjectKinds"] = ["gathering"]
        with self.assertRaises(SystemExit):
            self.verifier.validate_fact_producer_shapes(
                data,
                object_kinds={"place", "gathering"},
                registered_kinds={"coVisitedEntity"},
            )

    def test_recommendation_only_shape_cannot_emit_intersection_kind(self) -> None:
        data = copy.deepcopy(self.valid_shapes())
        data["factProducerShapes"]["capture_facts"]["outputKinds"] = [
            "coVisitedEntity"
        ]
        with self.assertRaises(SystemExit):
            self.verifier.validate_fact_producer_shapes(
                data,
                object_kinds={"place"},
                registered_kinds={"coVisitedEntity"},
            )

    def test_every_kind_requires_statement_template(self) -> None:
        problems: list[str] = []
        self.verifier.validate_statement_templates(
            {
                "statementTemplates": {
                    "slots": ["actor"],
                    "byKind": {
                        "otherKind": {
                            "template": "{actor}",
                            "l10nKey": "intersection.statement.other_kind",
                        }
                    },
                }
            },
            {
                "canonicalKind": {},
                "otherKind": {},
            },
            problems,
        )
        self.assertTrue(
            any("missing kinds" in problem for problem in problems),
            problems,
        )


if __name__ == "__main__":
    unittest.main()
