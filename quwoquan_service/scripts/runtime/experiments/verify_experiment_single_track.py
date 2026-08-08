#!/usr/bin/env python3
"""阻断推荐/搜索实验双轨回归。

当前商用契约只有一条分桶轨：
  runtime/experiments.AssignBucket
    -> recommendation recpolicy / search search_index_view experiments
    -> 实际曝光或查询事实中的 experiment bucket

Product Ops Experiment 聚合的创建 / 目录 / rollout 是策略发布的现行唯一轨（经
公开 command + 事务 outbox 发布 ExperimentPolicyActivated），因此不再冻结；
冻结的是 ExperimentAssignmentFact：它尚未由线上 runtime 分桶结果回写，必须
default-deny，且 Portal 不得展示其统计。未来启用 assignment 控制面必须先完成
durable runtime binding 和实际流量对账，而不能再增加第二个 resolver。
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
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

    # 冻结声明只属于 ExperimentAssignmentFact 对象；Experiment 聚合的
    # create/list/rollout 是现行策略发布轨，不得被要求声明 blocked。
    _require(assignment, FROZEN_GAP, assignment_path)
    _require(assignment, "status: blocked", assignment_path)

    # 反向单轨约束：Experiment 对象不得把冻结的 assignment / stats 读写面
    # 搬到自己身上来绕开冻结。
    for forbidden in (
        "GetExperimentAssignment",
        "AssignExperimentVariant",
        "GetExperimentStats",
        "/assignment",
    ):
        if forbidden in experiment:
            raise AssertionError(
                f"{experiment_path}: Experiment 控制面不得承载冻结的 assignment 面 "
                f"{forbidden!r}；该面只属于 ExperimentAssignmentFact 且保持 default-deny"
            )

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
        "internal/search/search_index_view/application/experiments.go"
    )
    search_main_path = "quwoquan_service/services/search-service/cmd/api/main.go"
    search_config_path = (
        "quwoquan_service/services/search-service/config/schema.yaml"
    )
    search_signal_path = (
        "quwoquan_service/services/search-service/"
        "internal/search/recommendation_signal_fact/infrastructure/"
        "searchsignals/stream_publisher.go"
    )

    runtime = _read(runtime_path)
    recpolicy = _read(recpolicy_path)
    rec_engine = _read(rec_engine_path)
    search = _read(search_path)
    search_main = _read(search_main_path)
    search_config = _read(search_config_path)
    search_signal = _read(search_signal_path)

    _require(runtime, "func AssignBucket(", runtime_path)
    _require(runtime, "PolicyDigest", runtime_path)
    _require(runtime, '"sha256:"', runtime_path)
    _require(recpolicy, "runtimeexperiments.AssignBucket(", recpolicy_path)
    _require(rec_engine, "ResolveBucketOr(recpolicy.ExpScoringWeights", rec_engine_path)
    _require(rec_engine, "ExperimentBucket:   scoringBucket", rec_engine_path)
    _require(search, "runtimeexperiments.AssignBucket(", search_path)
    _require(search_signal, '"experimentBucket"', search_signal_path)

    for fragment in (
        "StaticResolver",
        "runtime-static-v1",
        'PolicyVersion string',
        'PolicyVersion:',
        '"not-found"',
    ):
        if fragment in runtime:
            raise AssertionError(
                f"{runtime_path}: manual runtime experiment identity or sentinel "
                f"remains via {fragment!r}"
            )
    for fragment in ("PolicyVersion", "policyVersion", "len(buckets) == 0"):
        if fragment in search:
            raise AssertionError(
                f"{search_path}: search experiment compatibility fallback remains "
                f"via {fragment!r}"
            )
    for source, text in (
        (search_main_path, search_main),
        (search_config_path, search_config),
    ):
        if "policyVersion" in text or "PolicyVersion" in text:
            raise AssertionError(
                f"{source}: manual runtime assignment policy version remains"
            )
    # 分桶权重与开关只能来自 durable ExperimentPolicyActivated 事实；服务私有
    # config 一旦重新声明这些键，就是第二个策略真相源。
    for key in (
        "sys.search-service.ranking.experiment.enabled",
        "sys.search-service.ranking.experiment.controlWeightPct",
        "sys.search-service.ranking.experiment.termHeatWeightPct",
    ):
        if key in search_config:
            raise AssertionError(
                f"{search_config_path}: search must not read experiment bucket policy "
                f"from service-private config via {key!r}; the only policy track is "
                "ExperimentPolicyActivated"
            )

    # Product Ops 只冻结 Experiment 聚合的并发修订序号；它不是独立 policy
    # 内容身份，也不导入 runtime hot path。
    assignment_fields_path = (
        "quwoquan_service/services/product-ops-service/contracts/product_ops/"
        "experiment_assignment_fact/fields.yaml"
    )
    assignment_fields = _read(assignment_fields_path)
    _require(assignment_fields, "- name: experimentRevision", assignment_fields_path)
    _require(assignment_fields, "- POSITIVE", assignment_fields_path)

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
        "[experiment-single-track] PASS: runtime assignment policy uses one "
        "content digest and fails closed; Product Ops immutable facts remain frozen"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
