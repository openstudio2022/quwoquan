#!/usr/bin/env python3
"""阻断推荐/搜索实验双轨回归。

当前商用契约只有一条分桶轨：
  runtime/experiments.AssignBucket
    -> recommendation recpolicy / search HashResolver
    -> 实际曝光或查询事实中的 experiment bucket

Product Ops Experiment / ExperimentAssignmentFact 尚未接入该热路径，因此必须
default-deny，且 Portal 不得展示其统计。未来启用控制面必须先完成 durable runtime
binding 和实际流量对账，而不能再增加第二个 resolver。
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FROZEN_GAP = "OPS_EXPERIMENT_RUNTIME_BINDING_FROZEN"


def _read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"missing required file: {relative}")
    return path.read_text(encoding="utf-8")


def _require(text: str, fragment: str, source: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{source}: missing required contract fragment {fragment!r}")


def _assert_control_plane_frozen() -> None:
    experiment_path = (
        "quwoquan_service/services/product-ops-service/contracts/product_ops/experiment/operations.yaml"
    )
    assignment_path = (
        "quwoquan_service/services/product-ops-service/contracts/"
        "product_ops/experiment_assignment_fact/operations.yaml"
    )
    experiment = _read(experiment_path)
    assignment = _read(assignment_path)

    for source, text in (
        (experiment_path, experiment),
        (assignment_path, assignment),
    ):
        _require(text, FROZEN_GAP, source)
        _require(text, "status: blocked", source)

    if "name: recommendation-engine" in assignment:
        raise AssertionError(
            f"{assignment_path}: recommendation-engine must not be declared as an "
            "ExperimentAssignmentFact consumer before durable runtime binding exists"
        )

    portal_src = ROOT / "quwoquan_ops/portal/src"
    forbidden_portal_fragments = (
        "ExperimentListPage",
        "ExperimentDetailPage",
        'path="/experiments',
    )
    for path in portal_src.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".mjs"}:
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_portal_fragments:
            if fragment in text:
                raise AssertionError(
                    f"{path.relative_to(ROOT)}: frozen experiment control-plane "
                    f"surface reintroduced via {fragment!r}"
                )


def _assert_canonical_runtime_track() -> None:
    runtime_path = "quwoquan_service/runtime/experiments/experiments.go"
    recpolicy_path = "quwoquan_service/runtime/recpolicy/policy.go"
    rec_engine_path = "quwoquan_service/runtime/recommendation/engine.go"
    search_path = (
        "quwoquan_service/services/search-service/"
        "internal/search/search_query/application/experiments.go"
    )
    search_signal_path = (
        "quwoquan_service/services/search-service/"
        "internal/search/recommendation_signal_fact/"
        "infrastructure/searchsignals/stream_publisher.go"
    )

    runtime = _read(runtime_path)
    recpolicy = _read(recpolicy_path)
    rec_engine = _read(rec_engine_path)
    search = _read(search_path)
    search_signal = _read(search_signal_path)

    _require(runtime, "func AssignBucket(", runtime_path)
    _require(recpolicy, "runtimeexperiments.AssignBucket(", recpolicy_path)
    _require(rec_engine, "ResolveBucketOr(recpolicy.ExpScoringWeights", rec_engine_path)
    _require(rec_engine, "ExperimentBucket:   scoringBucket", rec_engine_path)
    _require(search, "runtimeexperiments.NewHashResolver()", search_path)
    _require(search_signal, '"experimentBucket"', search_signal_path)

    forbidden_runtime_fragments = (
        "GetExperimentAssignment",
        "AssignExperimentVariant",
        "ExperimentAssignmentFact",
        "/ops/product_ops/experiments/",
        "product_ops/product_ops/experiment",
    )
    roots = (
        ROOT / "quwoquan_service/runtime/recommendation",
        ROOT / "quwoquan_service/runtime/recpolicy",
        ROOT / "quwoquan_service/services/content-service/internal",
        ROOT / "quwoquan_service/services/search-service/internal",
    )
    for source_root in roots:
        for path in source_root.rglob("*.go"):
            if path.name.endswith("_test.go"):
                continue
            text = path.read_text(encoding="utf-8")
            for fragment in forbidden_runtime_fragments:
                if fragment in text:
                    raise AssertionError(
                        f"{path.relative_to(ROOT)}: runtime hot path references frozen "
                        f"Product Ops assignment track via {fragment!r}"
                    )


def main() -> int:
    try:
        _assert_control_plane_frozen()
        _assert_canonical_runtime_track()
    except AssertionError as exc:
        print(f"[experiment-single-track] FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "[experiment-single-track] PASS: runtime hash bucket + actual traffic facts "
        "are canonical; unbound Product Ops control-plane remains frozen"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
