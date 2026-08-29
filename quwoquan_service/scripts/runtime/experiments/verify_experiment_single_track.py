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

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
FROZEN_GAP = "OPS_EXPERIMENT_RUNTIME_BINDING_FROZEN"

_ASSIGNMENT_OPERATIONS_PATH = (
    "quwoquan_service/services/product-ops-service/contracts/"
    "product_ops/experiment_assignment_fact/operations.yaml"
)
_ASSIGNMENT_HANDLER_PATH = (
    "quwoquan_service/services/product-ops-service/internal/product_ops/"
    "experiment_assignment_fact/adapters/inbound/http/handler.go"
)
_RESOLVER_SOURCE_ROOTS = (
    "quwoquan_service/runtime/experiments",
    "quwoquan_service/runtime/recpolicy",
    "quwoquan_service/runtime/recommendation",
    "quwoquan_service/services/search-service/internal/search/search_index_view",
    (
        "quwoquan_service/services/recommendation-service/internal/recommendation/"
        "ranked_recommendation_window"
    ),
)
_PRIVATE_CONFIG_ROOTS = (
    "quwoquan_service/services/search-service/config",
    "quwoquan_service/services/search-service/environments",
    "quwoquan_service/services/recommendation-service/config",
    "quwoquan_service/services/recommendation-service/environments",
)
_BOOTSTRAP_SOURCE_ROOTS = (
    "quwoquan_ops/cli",
    "quwoquan_app/scripts/gamma",
    "quwoquan_service/services/search-service/cmd",
    "quwoquan_service/services/search-service/deploy",
    "quwoquan_service/services/search-service/environments",
    "quwoquan_service/services/recommendation-service/cmd",
    "quwoquan_service/services/recommendation-service/deploy",
    "quwoquan_service/services/recommendation-service/environments",
)
_SOURCE_SUFFIXES = frozenset({".go", ".py", ".sh", ".sql", ".yaml", ".yml"})
_RESOLVER_DECLARATION = re.compile(
    r"(?m)^\s*(?:type|class)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*(?:Resolver|Bucketer|Assigner))\b"
)
_GO_RESOLVE_METHOD = re.compile(
    r"(?s)func\s+\(\s*[A-Za-z_][A-Za-z0-9_]*\s+\*?"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\)\s+Resolve\s*\("
    r"\s*ctx\s+context\.Context\s*,\s*experimentID\s+string\s*,"
    r"\s*subjectKey\s+string"
)
_ALLOWED_RESOLVERS = {
    "quwoquan_service/runtime/experiments/experiments.go": frozenset(
        {"Resolver", "HashResolver"}
    ),
}
_CONFIG_SCHEMA_KEY = re.compile(r"^\s*-\s*key:\s*['\"]?([^'\"\s#]+)")
_CONFIG_MAPPING_KEY = re.compile(r"^\s+([A-Za-z0-9_.-]+)\s*:")
_PRIVATE_POLICY_KEY_MARKERS = (
    "experiment",
    "bucket",
    "allocationbasispoints",
    "policyversion",
    "controlweightpct",
    "termheatweightpct",
    "modelweightpct",
    "ruleweightpct",
)
_DIRECT_POLICY_SQL = re.compile(
    r"(?is)\b(?:insert\s+into|update|delete\s+from|truncate(?:\s+table)?|copy)"
    r"\s+(?:[A-Za-z0-9_\"`.]+\.)?[\"`]?"
    r"(?:experiments|experiment_policy_revisions|experiment_assignment_facts)\b"
)
_DIRECT_PROJECTION_MUTATION = re.compile(
    r"(?is)(?:rm_search_experiment_policy|rm_recommendation_experiment_policy)"
    r".{0,240}\b(?:insert|replace|update|upsert|mongoimport)\b|"
    r"\b(?:insert|replace|update|upsert|mongoimport)\b.{0,240}"
    r"(?:rm_search_experiment_policy|rm_recommendation_experiment_policy)"
)
_DIRECT_SEED_SYMBOL = re.compile(
    r"(?i)\b(?:seed|fixture)[A-Za-z0-9_-]{0,48}"
    r"(?:experiment|assignment)(?:[A-Za-z0-9_-]{0,48})\b"
)


def _read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"missing required file: {relative}")
    return path.read_text(encoding="utf-8")


def _require(text: str, fragment: str, source: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{source}: missing required contract fragment {fragment!r}")


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_sources(relative_roots: tuple[str, ...]) -> tuple[Path, ...]:
    sources: list[Path] = []
    for relative_root in relative_roots:
        source_root = ROOT / relative_root
        if source_root.is_file() and source_root.suffix in _SOURCE_SUFFIXES:
            sources.append(source_root)
            continue
        if not source_root.is_dir():
            continue
        sources.extend(
            path
            for path in source_root.rglob("*")
            if path.is_file()
            and path.suffix in _SOURCE_SUFFIXES
            and "tests" not in path.parts
            and not path.name.endswith("_test.go")
        )
    return tuple(sorted(set(sources)))


def _assert_no_second_resolver() -> None:
    sources = _iter_sources(_RESOLVER_SOURCE_ROOTS)
    if not sources:
        raise AssertionError("experiment resolver scan matched no production source")
    for path in sources:
        relative = _relative(path)
        text = path.read_text(encoding="utf-8")
        allowed = _ALLOWED_RESOLVERS.get(relative, frozenset())
        declared_types = set(_RESOLVER_DECLARATION.findall(text))
        if relative.startswith("quwoquan_service/runtime/experiments/"):
            declarations = declared_types
        else:
            declarations = {
                name
                for name in declared_types
                if "experiment" in name.lower() or "bucket" in name.lower()
            }
        declarations.update(_GO_RESOLVE_METHOD.findall(text))
        unexpected = sorted(declarations - allowed)
        if unexpected:
            raise AssertionError(
                f"{relative}: second experiment resolver is forbidden; "
                f"unexpected resolver declarations={unexpected}"
            )


def _config_keys(text: str) -> tuple[str, ...]:
    keys: list[str] = []
    for line in text.splitlines():
        schema_match = _CONFIG_SCHEMA_KEY.match(line)
        if schema_match is not None:
            keys.append(schema_match.group(1))
            continue
        mapping_match = _CONFIG_MAPPING_KEY.match(line)
        if mapping_match is not None and mapping_match.group(1).startswith(
            ("sys.search-service.", "sys.recommendation-service.")
        ):
            keys.append(mapping_match.group(1))
    return tuple(keys)


def _assert_no_private_runtime_config() -> None:
    sources = _iter_sources(_PRIVATE_CONFIG_ROOTS)
    if not sources:
        raise AssertionError("experiment private-config scan matched no authored config")
    for path in sources:
        relative = _relative(path)
        for key in _config_keys(path.read_text(encoding="utf-8")):
            normalized = key.lower().replace("_", "").replace("-", "")
            if any(marker in normalized for marker in _PRIVATE_POLICY_KEY_MARKERS):
                raise AssertionError(
                    f"{relative}: service-private experiment runtime config is "
                    f"forbidden via {key!r}; consume ExperimentPolicyActivated"
                )


def _assert_no_direct_storage_seed() -> None:
    sources = _iter_sources(_BOOTSTRAP_SOURCE_ROOTS)
    if not sources:
        raise AssertionError("experiment bootstrap scan matched no production source")
    for path in sources:
        relative = _relative(path)
        text = path.read_text(encoding="utf-8")
        if _DIRECT_POLICY_SQL.search(text):
            raise AssertionError(
                f"{relative}: direct experiment storage seed/mutation is forbidden; "
                "use Product Ops public command and transactional outbox"
            )
        if _DIRECT_PROJECTION_MUTATION.search(text) or _DIRECT_SEED_SYMBOL.search(text):
            raise AssertionError(
                f"{relative}: direct experiment projection seed is forbidden; "
                "consume ExperimentPolicyActivated"
            )


def _assert_no_assignment_write_api() -> None:
    operations_text = _read(_ASSIGNMENT_OPERATIONS_PATH)
    try:
        document = yaml.safe_load(operations_text)
    except yaml.YAMLError as exc:
        raise AssertionError(
            f"{_ASSIGNMENT_OPERATIONS_PATH}: invalid YAML: {exc}"
        ) from exc
    if not isinstance(document, dict) or not isinstance(document.get("api_routes"), list):
        raise AssertionError(  # noqa: TRY004 - gate violations use one typed failure.
            f"{_ASSIGNMENT_OPERATIONS_PATH}: api_routes must be a non-empty list"
        )
    routes = document["api_routes"]
    if not routes:
        raise AssertionError(
            f"{_ASSIGNMENT_OPERATIONS_PATH}: assignment query routes are required"
        )
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            raise AssertionError(  # noqa: TRY004 - gate violations use one typed failure.
                f"{_ASSIGNMENT_OPERATIONS_PATH}: api_routes[{index}] must be an object"
            )
        method = str(route.get("method") or "").upper()
        application = route.get("application")
        kind = application.get("kind") if isinstance(application, dict) else None
        has_write_body = bool(route.get("request_entity") or route.get("request_body_kind"))
        if method != "GET" or kind != "query" or has_write_body:
            operation = str(route.get("operation") or f"api_routes[{index}]")
            raise AssertionError(
                f"{_ASSIGNMENT_OPERATIONS_PATH}: assignment write API is frozen; "
                f"{operation} declares method={method!r}, kind={kind!r}"
            )

    handler = _read(_ASSIGNMENT_HANDLER_PATH)
    _require(handler, "if r.Method != http.MethodGet", _ASSIGNMENT_HANDLER_PATH)
    for method in ("Post", "Put", "Patch", "Delete"):
        if f"http.Method{method}" in handler:
            raise AssertionError(
                f"{_ASSIGNMENT_HANDLER_PATH}: assignment write API is frozen; "
                f"HTTP {method.upper()} handler is forbidden"
            )


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
    search_main_path = "quwoquan_service/services/search-service/cmd/api/bootstrap.go"
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
        _assert_no_second_resolver()
        _assert_no_private_runtime_config()
        _assert_no_direct_storage_seed()
        _assert_no_assignment_write_api()
    except AssertionError as exc:
        print(f"[experiment-single-track] FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "[experiment-single-track] PASS: runtime assignment policy uses one "
        "content digest and fails closed; second resolver, private config, direct "
        "storage seed, and assignment write API regressions remain blocked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
