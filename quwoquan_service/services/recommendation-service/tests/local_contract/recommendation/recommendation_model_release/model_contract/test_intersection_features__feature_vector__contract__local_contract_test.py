"""W7 交集特征三方一致契约（B8）：serving / train / train_multiobjective 的
交集特征段必须同构——同一样本产出同一向量尾段；候选级 affinity 仅在
intersectionConfidenceLabel 存在时计入（与 Go ranking fusion 同语义）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from support.path_setup import model_runtime_root

_RUNTIME_ROOT = model_runtime_root()
_SCRIPTS_DIR = _RUNTIME_ROOT / "scripts"


def _load_append_helper(module_path: Path, module_name: str):
    """只加载 _append_intersection_features 段（避免脚本级依赖 pymongo 等）。"""
    source = module_path.read_text(encoding="utf-8")
    marker = "def _append_intersection_features"
    start = source.index(marker)
    end = source.index("\ndef ", start + 1)
    prelude_lines = []
    for line in source.splitlines():
        if line.startswith("INTERSECTION_USER_NUMERIC") or line.startswith(
            "INTERSECTION_CLASS_MAP"
        ):
            prelude_lines.append(line)
        elif prelude_lines and (line.startswith("    ") or line.startswith("]")):
            prelude_lines.append(line)
        elif prelude_lines and not line.strip():
            prelude_lines.append(line)
        elif prelude_lines and not line.startswith((" ", "]")):
            break
    snippet = "\n".join(prelude_lines) + "\n" + source[start:end]
    namespace: dict = {}
    exec(compile(snippet, str(module_path), "exec"), namespace)  # noqa: S102
    return namespace["_append_intersection_features"]


_SOURCES = {
    "train": _SCRIPTS_DIR / "train.py",
    "train_multiobjective": _SCRIPTS_DIR / "train_multiobjective.py",
    "serving": _RUNTIME_ROOT / "models" / "content_feed.py",
}

_SAMPLE_USER = {
    "sharedFolloweesCount": 3,
    "sharedCircleCount": 1,
    "coCommentedCount": 2,
    "coVisitedEntityCount": 4,
    "followeeInObjectActive": 1,
    "followeeViewingActive": 0,
    "affinityIntersectionScore": 0.42,
}
_SAMPLE_ITEM_FACT = {
    "intersectionFactStrength": 2.5,
    "intersectionFreshness": 0.8,
    "affinityIntersectionScore": 0.6,
    "intersectionConfidenceLabel": "high",
    "intersectionClass": "fact",
}


def test_intersection_feature_segments_are_isomorphic() -> None:
    vectors = {}
    for name, path in _SOURCES.items():
        helper = _load_append_helper(path, name)
        features: list[float] = []
        helper(features, _SAMPLE_ITEM_FACT, _SAMPLE_USER)
        vectors[name] = features
    reference = vectors["serving"]
    assert len(reference) == 11, f"intersection segment must be 11 dims, got {len(reference)}"
    for name, vector in vectors.items():
        assert vector == reference, (
            f"{name} intersection segment drifted: {vector} != {reference}"
        )


def test_candidate_affinity_requires_confidence_label() -> None:
    helper = _load_append_helper(_SOURCES["serving"], "serving")
    with_label: list[float] = []
    helper(with_label, _SAMPLE_ITEM_FACT, _SAMPLE_USER)
    without_label: list[float] = []
    helper(
        without_label,
        {**_SAMPLE_ITEM_FACT, "intersectionConfidenceLabel": ""},
        _SAMPLE_USER,
    )
    # 向量布局：user 7 项之后是 factStrength/freshness/candidateAffinity/class。
    assert with_label[9] == 0.6, "candidate affinity should count when label present"
    assert without_label[9] == 0.0, (
        "candidate affinity must be zeroed without intersectionConfidenceLabel "
        "(advisory channel, same semantics as Go ranking fusion)"
    )


def test_intersection_class_encoding_is_closed_set() -> None:
    helper = _load_append_helper(_SOURCES["serving"], "serving")
    for klass, expected in [("fact", 2.0), ("affinity", 1.0), ("", 0.0), ("bogus", 0.0)]:
        features: list[float] = []
        helper(features, {**_SAMPLE_ITEM_FACT, "intersectionClass": klass}, _SAMPLE_USER)
        assert features[10] == expected, f"class {klass!r} must encode to {expected}"
