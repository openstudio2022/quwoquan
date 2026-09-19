"""Matched-edge serving/training feature parity contract.

spec_ref:
  - specs/feature-tree/recommendation-platform/rec-model-training/training-pipeline/spec.md#gwt-001
  - specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
"""

from __future__ import annotations

import ast
import importlib.util
import sys

import pytest
from pathlib import Path

from support.path_setup import model_runtime_root
from generated.recommendation.recommendation_model_release.content_type_encoding import CONTENT_TYPE_MAP

_RUNTIME_ROOT = model_runtime_root()
_SCRIPTS_DIR = _RUNTIME_ROOT / "scripts"
_ENCODER_PATH = _RUNTIME_ROOT / "features" / "intersection_feature_encoder.py"


def _load_encoder():
    spec = importlib.util.spec_from_file_location(
        "intersection_feature_encoder_contract",
        _ENCODER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # 源码树禁止 __pycache__；加载被测模块时不得写字节码。
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


_ENCODER = _load_encoder()

_SOURCES = {
    "train": (_SCRIPTS_DIR / "train.py", "_extract_features"),
    "train_multiobjective": (
        _SCRIPTS_DIR / "train_multiobjective.py",
        "_extract_features",
    ),
    "serving": (_RUNTIME_ROOT / "models" / "content_feed.py", "_extract_feature_vector"),
}

_EXTRACTOR_CONSTANTS = {
    "ITEM_NUMERIC_FEATURES",
    "ITEM_NUMERIC",
    "USER_NUMERIC_FEATURES",
    "USER_NUMERIC",
    "CONTEXT_NUMERIC_FEATURES",
    "CONTEXT_NUMERIC",
    "RECALL_PATH_MAP",
    "ITEM_FEATURE_KEYS",
}


def _load_extractor(path: Path, function_name: str):
    """Load the pure vector extractor without importing DB/model dependencies."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if names & _EXTRACTOR_CONSTANTS:
                selected.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                selected.append(node)
    namespace = {
        "append_intersection_features": _ENCODER.append_intersection_features,
        "CONTENT_TYPE_MAP": CONTENT_TYPE_MAP,
    }
    exec(  # noqa: S102 - compile only selected pure constants/function from repo source.
        compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace[function_name]


@pytest.mark.parametrize("content_type,code", [("image", 0), ("video", 1), ("article", 2)])
def test_content_type_encoding_is_stable_across_serving_and_training(content_type, code):
    item = {"contentType": content_type}
    vectors = []
    for label, (path, name) in _SOURCES.items():
        extractor = _load_extractor(path, name)
        vector = extractor(item, {}, {}) if label == "serving" else extractor({"itemFeatures": item})
        assert vector[14] == code
        vectors.append(vector)
    assert vectors[0] == vectors[1] == vectors[2]
    embedding = _load_extractor(_SCRIPTS_DIR / "train_embedding.py", "_build_item_vector")
    assert embedding({"itemFeatures": item})[-1] == code


@pytest.mark.parametrize("content_type", ["micro", "moment", "photo", "homepage", "unknown", "", None])
def test_retired_or_unknown_content_type_is_not_an_encodable_category(content_type):
    item = {"contentType": content_type}
    for label, (path, name) in _SOURCES.items():
        extractor = _load_extractor(path, name)
        with pytest.raises((KeyError, ValueError)):
            extractor(item, {}, {}) if label == "serving" else extractor({"itemFeatures": item})
    embedding = _load_extractor(_SCRIPTS_DIR / "train_embedding.py", "_build_item_vector")
    with pytest.raises((KeyError, ValueError)):
        embedding({"itemFeatures": item})


@pytest.mark.parametrize("model", [None, object()])
def test_scorer_rejects_retired_type_before_model_or_rule_fallback(model):
    from types import SimpleNamespace

    path = _RUNTIME_ROOT / "models" / "content_feed.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    scorer = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ContentFeedScorer")
    score = next(node for node in scorer.body if isinstance(node, ast.FunctionDef) and node.name == "score")
    namespace = {"ModelScoreRequest": object, "ModelScoreResponse": object,
                 "CONTENT_TYPE_MAP": CONTENT_TYPE_MAP,
                 "build_candidate_features": lambda request: [{"contentType": "micro"}]}
    validator = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "_validated_candidate_features")
    exec(compile(ast.Module(body=[validator, score], type_ignores=[]), str(path), "exec"), namespace)
    with pytest.raises(ValueError, match="unsupported content type"):
        namespace["score"](SimpleNamespace(_model=model), object())


def test_seed_content_types_match_training_categories_without_database_access():
    tree = ast.parse((_SCRIPTS_DIR / "generate_seed_data.py").read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"CONTENT_TYPES", "CONTENT_TYPE_WEIGHTS"}
    }
    assert constants["CONTENT_TYPES"] == ["image", "video", "article"]
    assert len(constants["CONTENT_TYPE_WEIGHTS"]) == 3
    assert sum(constants["CONTENT_TYPE_WEIGHTS"]) == 1


_SAMPLE_USER = {
    "tagAffinities": {"Topic/旅行": 0.7},
    "authorAffinities": {"author-1": 0.8},
    "topicAffinities": {"Topic/旅行": 0.6},
    "audienceAffinities": {},
    "formatAffinities": {},
    "entityAffinities": {},
    "entityInstanceAffinities": {"place-1": 0.5},
    "circleTagAffinities": {"Topic/旅行": 0.4},
    "typeENER": {"article": 0.3},
    "depthDistribution": {"L0": 1, "L1": 2, "L2": 3, "L3": 4, "L4": 5},
    "avgEngagementDepth": 2.3,
    "socialInterestScore": 0.2,
    "engagementRate": 0.1,
    "totalLikes": 3,
    "totalShares": 1,
    "totalEvents": 8,
    "sharedFolloweesCount": 3,
    "sharedCircleCount": 1,
    "coCommentedCount": 2,
    "coVisitedEntityCount": 4,
    "followeeInObjectActive": 1,
    "followeeViewingActive": 0,
    "affinityIntersectionScore": 0.42,
    "intersectionEdgeWeight": 0.91,
    "intersectionEdgeFreshness": 0.73,
    "intersectionEdgeKind": "coVisitedEntity",
}
_SAMPLE_ITEM = {
    "contentId": "post-1",
    "contentType": "article",
    "authorId": "author-1",
    "tagRefs": ["Topic/旅行"],
    "entityRefs": ["place-1"],
    "ageHours": 2.0,
    "publishHour": 9,
    "viewCount": 12,
    "likeCount": 4,
    "commentCount": 2,
    "shareCount": 1,
    "tagCount": 1,
    "qualityScore": 0.8,
    "recallPath": "tag_recall",
    "intersectionFactStrength": 2.5,
    "intersectionFreshness": 0.8,
    "affinityIntersectionScore": 0.6,
    "intersectionConfidenceLabel": "high",
    "intersectionClass": "fact",
    **{
        field: _SAMPLE_USER[field]
        for field in (
            "intersectionEdgeWeight",
            "intersectionEdgeFreshness",
            "intersectionEdgeKind",
        )
    },
}
_SAMPLE_CONTEXT = {"requestHour": 12, "requestDayOfWeek": 3}


def _vector(name: str) -> list[float]:
    path, function_name = _SOURCES[name]
    extractor = _load_extractor(path, function_name)
    if name == "serving":
        return extractor(_SAMPLE_ITEM, _SAMPLE_USER, _SAMPLE_CONTEXT)
    return extractor(
        {
            "itemFeatures": _SAMPLE_ITEM,
            "userFeatures": _SAMPLE_USER,
            "contextFeatures": _SAMPLE_CONTEXT,
        }
    )


def test_serving_and_training_vectors_are_isomorphic_for_matched_edge() -> None:
    vectors = {name: _vector(name) for name in _SOURCES}
    reference = vectors["serving"]
    for name, vector in vectors.items():
        assert vector == reference, f"{name} vector drifted from serving"


def test_intersection_segment_consumes_exact_matched_edge_triple() -> None:
    features: list[float] = []
    _ENCODER.append_intersection_features(
        features,
        _SAMPLE_ITEM,
        _SAMPLE_USER,
        _SAMPLE_USER,
    )
    assert len(features) == 14
    assert features[7] == 0.91
    assert features[8] == 0.73
    assert features[9] == _ENCODER.encode_intersection_kind("coVisitedEntity")
    assert features[9] > 0


def test_candidate_affinity_requires_confidence_label() -> None:
    with_label: list[float] = []
    _ENCODER.append_intersection_features(
        with_label,
        _SAMPLE_ITEM,
        _SAMPLE_USER,
        _SAMPLE_USER,
    )
    without_label: list[float] = []
    _ENCODER.append_intersection_features(
        without_label,
        {**_SAMPLE_ITEM, "intersectionConfidenceLabel": ""},
        _SAMPLE_USER,
        _SAMPLE_USER,
    )
    assert with_label[12] == 0.6
    assert without_label[12] == 0.0


def test_kind_encoding_is_derived_from_canonical_registry() -> None:
    codes = _ENCODER.canonical_intersection_kind_codes()
    assert codes["coVisitedEntity"] == _ENCODER.encode_intersection_kind(
        "coVisitedEntity"
    )
    assert _ENCODER.encode_intersection_kind("sharedFollowees") != codes[
        "coVisitedEntity"
    ]
    assert _ENCODER.encode_intersection_kind("unregistered-kind") == 0.0
    vector_width = len(_vector("train"))
    indexes = _ENCODER.matched_edge_categorical_features(vector_width)
    assert indexes == [vector_width - 5]


def test_all_content_type_consumers_import_generated_encoding() -> None:
    paths = [path for path, _ in _SOURCES.values()] + [_SCRIPTS_DIR / "train_embedding.py"]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
                   and node.module == "generated.recommendation.recommendation_model_release.content_type_encoding"
                   and any(alias.name == "CONTENT_TYPE_MAP" and alias.asname is None for alias in node.names)]
        assert len(imports) == 1, f"{path} must import the canonical encoding"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                assert node.id != "CONTENT_TYPE_MAP", f"{path} redefines model encoding"
    assert dict(CONTENT_TYPE_MAP) == {"image": 0, "video": 1, "article": 2}
    with pytest.raises(TypeError):
        CONTENT_TYPE_MAP["image"] = 99


def test_all_rankers_import_one_matched_edge_encoder() -> None:
    for name, (path, _) in _SOURCES.items():
        source = path.read_text(encoding="utf-8")
        assert "from features.intersection_feature_encoder import" in source
        assert "append_intersection_features" in source
        assert "INTERSECTION_KIND_MAP" not in source
        if name != "serving":
            assert "matched_edge_categorical_features" in source
            assert "categorical_feature=categorical_features" in source
