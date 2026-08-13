"""对象证据闭合门禁主流程：图选择、缺口收集、盲点核对与动态商业判定。

本模块同时是既有契约测试的 patch surface：`main` / `evaluate_dynamic_readiness` /
`artifact_gaps` / `page_claims_and_consumers` 等函数与 `ROOT` /
`PAGE_OBJECT_CONTRACT` 绑定必须留在同一命名空间，供测试以
`mock.patch.object` 注入。
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from .arguments import commercial_input_values, parse_args
# 部分名字（EVIDENCE_CLASS_BY_DIMENSION / REPORT_* 等）本模块不直接使用，
# 但既有契约测试以 `closure.<name>` 直接消费，必须保留在本命名空间。
from .constants import (  # noqa: F401
    ARTIFACT_EVIDENCE_FIELDS,
    BLIND_SPOT_CLASSIFICATIONS,
    BLIND_SPOT_IMPLEMENTATION_EVIDENCE,
    BLIND_SPOT_IMPLEMENTED,
    BLIND_SPOT_MISSING,
    BLIND_SPOT_REGISTRY,
    BLINDSPOT,
    EVIDENCE_CLASS_BY_DIMENSION,
    LAYER_BY_MISSING_KEY,
    PAGE_OBJECT_CONTRACT,
    READINESS_EVALUATOR_PACKAGE,
    READINESS_EVALUATOR_RUN_TIMEOUT_SECONDS,
    READINESS_METADATA_DIR,
    REPORT_BLIND_SPOT_REGISTRY_FIELD,
    REPORT_GRAPH_FIELD,
    RESULT,
    ROOT,
    SERVICE_ROOT,
    SHA256_PATTERN,
    STATE_OWNER_KINDS,
    STORAGE_EVIDENCE_FIELDS,
    STRUCTURAL,
)
from .gap_rules import (
    domain_event_declaration_gaps,
    partition_by_evidence_class,
    publication_gap_detail,
    slice_owner_object,
    unclassified_dimensions,
)
from .graph_source import (  # noqa: F401
    derive_contract_graph,
    load_graph_with_digest,
    validate_contract_graph_shape,
    verify_graph_digest,
)
from .models import DynamicEvaluation, Gap, display_path, sha256_file
from .page_runtime import runtime_execution_consumers
from .readiness_inputs import (
    build_readiness_evaluator,
    decode_single_json_document,
    readiness_input_bindings,
    verify_readiness_input_bindings,
)
from .reporting import (  # noqa: F401
    cells_from_gaps,
    print_blind_spots,
    print_gap_inventory,
    print_result_layer,
    print_structural_gaps,
    validate_report_graph_binding,
    validate_report_policy_bindings,
    write_reports,
)


def select_graph_path(arguments: argparse.Namespace) -> Path:
    """选择唯一判定图。

    required gate 缺省必须从当前受管源码现场派生；否则单独运行本门时，
    陈旧 generated graph 会把 scanner/合同改动隐藏成假绿。只有显式 `--graph` 才允许评估
    调用者已精确绑定的图字节。
    """
    if arguments.graph is not None:
        return Path(arguments.graph)
    return derive_contract_graph(Path(arguments.report_dir))

def evaluate_dynamic_readiness(
    arguments: argparse.Namespace,
    graph_path: Path,
    graph_digest: str,
) -> DynamicEvaluation:
    """薄调用 canonical Go evaluator；不在 Python 重算任何 readiness 规则。"""
    try:
        bindings = readiness_input_bindings(arguments)
    except (OSError, ValueError) as error:
        return DynamicEvaluation(
            2,
            {
                "status": "invalid_input",
                "commercialReady": False,
                "evaluatorExitCode": 2,
                "closure": None,
                "inputs": {},
                "reason": str(error),
            },
        )

    cache_root = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "local"
        / "object-evidence-closure"
        / "cache"
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="readiness-evaluator-", dir=cache_root
        ) as temporary:
            binary, binary_digest = build_readiness_evaluator(Path(temporary))
            completed = subprocess.run(
                [
                    str(binary),
                    "--graph",
                    str(graph_path),
                    "--bundle",
                    str(arguments.readiness_bundle),
                    "--snapshot",
                    str(arguments.signed_current_snapshot),
                    "--snapshot-keyring",
                    str(arguments.snapshot_keyring),
                    "--runner-keyring",
                    str(arguments.runner_keyring),
                    "--receipt-root",
                    str(arguments.receipt_root),
                    "--evidence-root",
                    str(arguments.evidence_root),
                    "--metadata-dir",
                    str(READINESS_METADATA_DIR),
                ],
                cwd=SERVICE_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=READINESS_EVALUATOR_RUN_TIMEOUT_SECONDS,
            )
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return DynamicEvaluation(
            2,
            {
                "status": "invalid_input",
                "commercialReady": False,
                "evaluatorExitCode": 2,
                "closure": None,
                "inputs": bindings,
                "reason": f"readiness evaluator unavailable: {error}",
            },
        )

    try:
        verify_graph_digest(graph_path, graph_digest)
        verify_readiness_input_bindings(arguments, bindings)
        payload = decode_single_json_document(completed.stdout)
        if completed.returncode not in {0, 1, 2}:
            raise ValueError(
                f"readiness evaluator returned illegal exit code {completed.returncode}"
            )
        commercial_ready = payload.get("commercialReady")
        if not isinstance(commercial_ready, bool):
            raise ValueError("readiness evaluator omitted boolean commercialReady")
        if completed.returncode == 0 and commercial_ready is not True:
            raise ValueError("readiness evaluator exit 0 did not report commercialReady=true")
        if completed.returncode in {1, 2} and commercial_ready is not False:
            raise ValueError(
                "readiness evaluator blocked/invalid exit did not report commercialReady=false"
            )
        if completed.returncode == 2 and not isinstance(payload.get("error"), str):
            raise ValueError("readiness evaluator exit 2 omitted error")
    except (SystemExit, ValueError) as error:
        return DynamicEvaluation(
            2,
            {
                "status": "invalid_input",
                "commercialReady": False,
                "evaluatorExitCode": 2,
                "closure": None,
                "inputs": bindings,
                "reason": str(error),
            },
        )

    return DynamicEvaluation(
        completed.returncode,
        {
            "status": "evaluated" if completed.returncode in {0, 1} else "invalid_input",
            "commercialReady": commercial_ready,
            "evaluatorExitCode": completed.returncode,
            "evaluator": {
                "package": READINESS_EVALUATOR_PACKAGE,
                "binarySha256": binary_digest,
                "stdoutSha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
            },
            "inputs": bindings,
            "closure": payload,
        },
    )

def page_claims_and_consumers(
    graph: dict,
) -> tuple[
    set[str],
    dict[str, set[str]],
    dict[str, set[str]],
    dict[str, set[str]],
]:
    """派生页面 query/command 与非页面 runtime execution 的消费证据。

    `object_ids` 仍表达页面 participant；`query_slices` 与 `command_operations`
    分别给出读/写分类。没有页面的 runtime/background consumer 必须额外登记
    operation、生产文件和逐文件 symbol，且至少有一个真实执行 owner 位于 adapter/DI
    之外。仅有 generated adapter 绝不能把未接入的 App contract 判成已消费。
    """
    document = yaml.safe_load(PAGE_OBJECT_CONTRACT.read_text(encoding="utf-8")) or {}
    objects = {
        str(entry.get("id") or "").strip()
        for entry in graph.get("objects") or []
        if str(entry.get("id") or "").strip()
    }
    operations = {
        str(entry.get("id") or "").strip(): entry
        for entry in graph.get("operations") or []
        if str(entry.get("id") or "").strip()
    }
    claimed: set[str] = set()
    query_consumers: dict[str, set[str]] = defaultdict(set)
    command_consumers: dict[str, set[str]] = defaultdict(set)
    for page in document.get("pages") or []:
        page_id = str(page.get("page_id") or "").strip()
        page_objects = {
            str(object_id).strip()
            for object_id in page.get("object_ids") or []
            if str(object_id).strip()
        }
        claimed.update(page_objects)
        slices = page.get("query_slices")
        if isinstance(slices, str):
            slices = [slices]
        for slice_reference in slices or []:
            if not isinstance(slice_reference, str):
                continue
            owner = slice_owner_object(slice_reference, objects)
            if owner:
                query_consumers[owner].add(page_id)

        command_operations = page.get("command_operations") or []
        if not isinstance(command_operations, list):
            raise SystemExit(
                f"GATE_BLOCK page {page_id} command_operations 必须是字符串列表"
            )
        if len(command_operations) != len(set(command_operations)):
            raise SystemExit(
                f"GATE_BLOCK page {page_id} command_operations 不得重复"
            )
        for operation_id in command_operations:
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise SystemExit(
                    f"GATE_BLOCK page {page_id} command_operations 含空/非字符串项"
                )
            operation_id = operation_id.strip()
            operation_owner = operation_id.rsplit(".", 1)[0]
            if operation_owner not in page_objects:
                raise SystemExit(
                    f"GATE_BLOCK page {page_id} command operation {operation_id} "
                    f"的对象 {operation_owner} 未列入 object_ids"
                )
            # Focused/unit ContractGraph may intentionally contain a partial object
            # set. Unknown page objects are owned by the page-contract validator;
            # operation truth is checked here once its owner is present in this graph.
            if operation_owner not in objects:
                continue
            operation = operations.get(operation_id)
            if operation is None or not operation.get("clientContract"):
                raise SystemExit(
                    f"GATE_BLOCK page {page_id} command operation 不存在或非 App "
                    f"clientContract: {operation_id}"
                )
            object_id = str(operation.get("objectId") or "").strip()
            if object_id not in page_objects:
                raise SystemExit(
                    f"GATE_BLOCK page {page_id} command operation {operation_id} "
                    f"的对象 {object_id} 未列入 object_ids"
                )
            if operation.get("kind") not in {"command", "session"}:
                raise SystemExit(
                    f"GATE_BLOCK page {page_id} command_operations 不得登记 query: "
                    f"{operation_id}"
                )
            command_consumers[object_id].add(page_id)

    runtime_consumers = runtime_execution_consumers(
        document.get("runtime_execution"),
        operations=operations,
        known_objects=objects,
        claimed=claimed,
    )
    return claimed, query_consumers, command_consumers, runtime_consumers

def collect_gaps(graph: dict) -> list[Gap]:
    objects = {entry["id"]: entry for entry in graph.get("objects") or []}
    readiness = {entry["objectId"]: entry for entry in graph.get("objectReadiness") or []}
    evidence_by_object: dict[str, dict] = {}
    packets_by_object: Counter[str] = Counter()
    for packet in graph.get("readinessEvidence") or []:
        evidence_by_object[packet["objectId"]] = packet
        packets_by_object[packet["objectId"]] += 1

    if objects and not evidence_by_object:
        raise SystemExit(
            "GATE_BLOCK ContractGraph 未携带任何 readinessEvidence。"
            "重跑 `make -C quwoquan_service codegen-contract-graph`（必须带 --repo-root），"
            "或用 --graph 指向一份派生过证据的图；0 条证据不得被当成「运行证据还没到」。"
        )

    client_contract_objects = {
        operation["objectId"]
        for operation in graph.get("operations") or []
        if operation.get("clientContract")
    }
    command_objects = {
        operation["objectId"]
        for operation in graph.get("operations") or []
        if operation.get("kind") == "command"
    }
    claimed, query_consumers, command_consumers, runtime_consumers = (
        page_claims_and_consumers(graph)
    )

    gaps: list[Gap] = []
    for object_id, entry in sorted(objects.items()):
        state = readiness.get(object_id)
        kind = entry.get("kind", "")
        stage = state.get("stage", "unknown") if state else "unknown"
        if state is None:
            gaps.append(
                Gap(object_id, kind, stage, "derivation.readiness_missing",
                    "ContractGraph 没有该对象的 objectReadiness 条目")
            )
            continue
        # readiness 判定不在这里重算：直接展开 graph 给出的 missing 键。
        for key in state.get("missing") or []:
            dimension = LAYER_BY_MISSING_KEY.get(key)
            if dimension is None:
                # 契约阶段（object.* / operation.* / entrypoint.*）不属于证据闭合，
                # 由 verify-contract-graph 系列门禁承接。
                continue
            gaps.append(
                Gap(
                    object_id,
                    kind,
                    stage,
                    dimension,
                    publication_gap_detail(key, evidence_by_object.get(object_id)) or key,
                )
            )

        # aggregate_root 与 process_manager 同为状态所有者，两者的命令都可能需要
        # 事务性发布 seam，因此都必须显式表态是否发布领域事件。
        if kind in STATE_OWNER_KINDS and object_id in command_objects:
            gaps.extend(domain_event_declaration_gaps(object_id, kind, stage, entry))

        packet = evidence_by_object.get(object_id)
        if packet is None:
            if state.get("contractReady"):
                gaps.append(
                    Gap(object_id, kind, stage, "derivation.evidence_packet",
                        "contract-ready 对象没有派生出证据 packet")
                )
            continue
        gaps.extend(artifact_gaps(object_id, kind, stage, packet))
        if object_id in client_contract_objects:
            page_query = query_consumers.get(object_id) or set()
            page_command = command_consumers.get(object_id) or set()
            runtime_operations = runtime_consumers.get(object_id) or set()
            if object_id not in claimed and not (
                page_query or page_command or runtime_operations
            ):
                gaps.append(
                    Gap(
                        object_id,
                        kind,
                        stage,
                        "app.unconsumed_contract",
                        "App clientContract 没有 page query_slices / page "
                        "command_operations，也没有带生产 owner+symbol 的 "
                        "runtime_execution；仅有 adapter/DI 不算消费",
                    )
                )
    return gaps

def artifact_integrity_gaps(
    object_id: str,
    kind: str,
    stage: str,
    field: str,
    artifact: dict,
) -> list[Gap]:
    """证据路径和 SHA256 是一个原子引用；任一侧缺失或漂移都 fail-closed。"""
    path_text = str(artifact.get("path") or "")
    resolved, path_issue = resolve_repository_artifact(path_text)
    if path_issue:
        return [
            Gap(
                object_id,
                kind,
                stage,
                "derivation.artifact_missing",
                f"{field} 证据路径 {path_text!r} 无效：{path_issue}",
            )
        ]

    expected = str(artifact.get("sha256") or "")
    if not SHA256_PATTERN.fullmatch(expected):
        return [
            Gap(
                object_id,
                kind,
                stage,
                "derivation.artifact_digest",
                f"{field} 证据 {path_text!r} 缺少合法 SHA256 摘要",
            )
        ]
    try:
        actual = sha256_file(resolved)
    except OSError as error:
        return [
            Gap(
                object_id,
                kind,
                stage,
                "derivation.artifact_digest",
                f"{field} 证据 {path_text!r} 无法读取并复核摘要：{error}",
            )
        ]
    if actual == expected:
        return []
    return [
        Gap(
            object_id,
            kind,
            stage,
            "derivation.artifact_digest",
            f"{field} 证据 {path_text!r} 已漂移：expected={expected} actual={actual}",
        )
    ]


def resolve_repository_artifact(path_text: str) -> tuple[Path, str]:
    """把 EvidenceArtifact 解析为仓内文件；禁止绝对路径、穿越与 symlink 逃逸。"""
    path = Path(path_text)
    if not path_text:
        return Path(), "路径为空"
    if path.is_absolute():
        return Path(), "EvidenceArtifact.path 必须是 repository-relative"
    if ".." in path.parts:
        return Path(), "EvidenceArtifact.path 不得包含父目录穿越"

    try:
        repository_root = ROOT.resolve(strict=True)
        resolved = (ROOT / path).resolve(strict=True)
        resolved.relative_to(repository_root)
    except FileNotFoundError:
        return Path(), "文件不存在"
    except (OSError, RuntimeError) as error:
        return Path(), f"路径无法解析：{error}"
    except ValueError:
        return Path(), "符号链接或路径逃逸出 repository root"
    if not resolved.is_file():
        return Path(), "目标不是普通文件"
    return resolved, ""


def is_production_service_source(path_text: str) -> bool:
    """Blindspot 只能由第一方服务生产源码证明，测试、缓存和生成物不算实现。"""
    resolved, issue = resolve_repository_artifact(path_text)
    if issue:
        return False
    relative = resolved.relative_to(ROOT.resolve(strict=True))
    parts = relative.parts
    if parts[:2] != ("quwoquan_service", "services"):
        return False
    if any(
        part in {"test", "tests", "testdata", "fixtures", "generated", ".qwq_output"}
        for part in parts
    ):
        return False
    if resolved.name.endswith(("_test.go", "_test.py")):
        return False
    return resolved.suffix in {".go", ".py"}


def artifact_gaps(object_id: str, kind: str, stage: str, packet: dict) -> list[Gap]:
    """按 canonical producer-separated packet 复核全部结构证据字节。"""
    gaps: list[Gap] = []
    for producer, field in ARTIFACT_EVIDENCE_FIELDS:
        evidence = packet.get(producer) or {}
        for artifact in evidence.get(field) or []:
            gaps.extend(
                artifact_integrity_gaps(
                    object_id, kind, stage, f"{producer}.{field}", artifact
                )
            )
    for producer, field in STORAGE_EVIDENCE_FIELDS:
        evidence = packet.get(producer) or {}
        for storage_evidence in evidence.get(field) or []:
            artifact = storage_evidence.get("artifact") or {}
            gaps.extend(
                artifact_integrity_gaps(
                    object_id,
                    kind,
                    stage,
                    f"{producer}.{field}",
                    artifact,
                )
            )
    for storage_evidence in packet.get("publicationDelivery") or []:
        artifact = storage_evidence.get("artifact") or {}
        gaps.extend(
            artifact_integrity_gaps(
                object_id,
                kind,
                stage,
                "publicationDelivery",
                artifact,
            )
        )
    return gaps

def load_blind_spot_registry_with_digest(
    path: Path,
) -> tuple[dict[tuple[str, str], dict], str | None]:
    """读盲点登记册。结构照抄 emitted_error_code_declaration_baseline.yaml 的
    `unresolved_sites`，但手工搜索范围本身不能证明实现存在。

    每项必须明确二选一：scanner_false_negative_implemented 需要同时提供写入和投递实现的
    SHA-bound artifact；implementation_missing 始终阻断。派生盲点与登记册仍做双向核对。
    """
    if not path.exists():
        return {}, None
    try:
        payload = path.read_bytes()
        document = yaml.safe_load(payload.decode("utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise SystemExit(
            f"GATE_BLOCK 无法读取盲点登记册 {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise SystemExit(f"GATE_BLOCK 盲点登记册 {path} 必须是 YAML object")
    entries: dict[tuple[str, str], dict] = {}
    for entry in document.get("unresolved_sites") or []:
        key = (str(entry.get("object_id", "")), str(entry.get("dimension", "")))
        if not all(key):
            raise SystemExit(
                "GATE_BLOCK 盲点登记缺少 object_id/dimension，无法绑定派生对象"
            )
        if key in entries:
            raise SystemExit(f"GATE_BLOCK 盲点登记重复：{key}")
        if not entry.get("attested_scope"):
            raise SystemExit(
                f"GATE_BLOCK 盲点登记 {key} 缺 attested_scope："
                "手工事实必须写明依据的搜索范围，否则无法复核"
            )
        classification = str(entry.get("classification") or "")
        if classification not in BLIND_SPOT_CLASSIFICATIONS:
            raise SystemExit(
                f"GATE_BLOCK 盲点登记 {key} 的 classification 必须为 "
                f"{BLIND_SPOT_IMPLEMENTED} 或 {BLIND_SPOT_MISSING}；"
                "只有 attested_scope 不能证明实现存在"
            )
        if classification == BLIND_SPOT_IMPLEMENTED:
            evidence = entry.get("implementation_evidence")
            if not isinstance(evidence, dict):
                raise SystemExit(
                    f"GATE_BLOCK 盲点登记 {key} 声称实现存在但缺 "
                    "implementation_evidence"
                )
            for evidence_kind in BLIND_SPOT_IMPLEMENTATION_EVIDENCE:
                artifacts = evidence.get(evidence_kind)
                if not isinstance(artifacts, list) or not artifacts:
                    raise SystemExit(
                        f"GATE_BLOCK 盲点登记 {key} 声称实现存在但缺 "
                        f"implementation_evidence.{evidence_kind}"
                    )
                for artifact in artifacts:
                    if not isinstance(artifact, dict):
                        raise SystemExit(
                            f"GATE_BLOCK 盲点登记 {key} 的 "
                            f"implementation_evidence.{evidence_kind} 必须为 artifact 列表"
                        )
                    integrity = artifact_integrity_gaps(
                        key[0],
                        "blindspot",
                        "unknown",
                        f"blindspot.{evidence_kind}",
                        artifact,
                    )
                    if integrity:
                        raise SystemExit(
                            f"GATE_BLOCK 盲点登记 {key} 的实现证据无效："
                            f"{integrity[0].detail}"
                        )
                    if not is_production_service_source(str(artifact.get("path") or "")):
                        raise SystemExit(
                            f"GATE_BLOCK 盲点登记 {key} 的 "
                            f"implementation_evidence.{evidence_kind} 必须绑定 "
                            "quwoquan_service/services/** 下的生产 Go/Python 源码，"
                            "不得使用测试、缓存、生成物或任意临时文件"
                        )
        entries[key] = entry
    return entries, hashlib.sha256(payload).hexdigest()


def load_blind_spot_registry(path: Path) -> dict[tuple[str, str], dict]:
    return load_blind_spot_registry_with_digest(path)[0]


def blind_spot_gaps(gaps: list[Gap], registry: dict[tuple[str, str], dict]) -> list[str]:
    """盲点集合双向核对；确认 implementation_missing 的条目仍然硬阻断。"""
    observed = {(gap.object_id, gap.dimension) for gap in gaps}
    problems = []
    for key in sorted(observed - set(registry)):
        problems.append(
            f"新增维度盲点未登记：{key[0]} / {key[1]}。"
            "登记到 object_evidence_blind_spots.yaml（含 attested_scope），"
            "或把判定器扩展到能看见它"
        )
    for key in sorted(set(registry) - observed):
        problems.append(
            f"登记的盲点已不复存在：{key[0]} / {key[1]}。删除该条目，"
            "盲点清单只减不增"
        )
    for key in sorted(observed & set(registry)):
        classification = str(registry[key].get("classification") or "")
        if classification == BLIND_SPOT_MISSING:
            problems.append(
                f"盲点人工核查确认实现缺失：{key[0]} / {key[1]}。"
                "implementation_missing 不能凭 attested_scope 放行；必须补生产实现，"
                "并让 scanner 重新派生为可自动验证的结构性证据"
            )
        elif classification != BLIND_SPOT_IMPLEMENTED:
            problems.append(
                f"盲点登记分类无效：{key[0]} / {key[1]} / {classification!r}"
            )
    return problems

def main() -> int:
    arguments = parse_args()
    graph_path = select_graph_path(arguments)
    graph_path = graph_path.resolve()
    graph, graph_digest = load_graph_with_digest(graph_path)
    gaps = collect_gaps(graph)
    unclassified = unclassified_dimensions(gaps)
    partitions = partition_by_evidence_class(gaps)
    structural = partitions[STRUCTURAL]
    cells = cells_from_gaps(structural)
    registry_path = BLIND_SPOT_REGISTRY.resolve()
    blind_spots, registry_digest = load_blind_spot_registry_with_digest(registry_path)
    blind_spot_problems = blind_spot_gaps(partitions[BLINDSPOT], blind_spots)
    report = write_reports(
        arguments.report_dir,
        graph_path,
        graph_digest,
        registry_path,
        registry_digest,
        graph,
        gaps,
        cells,
    )

    objects = len(graph.get("objects") or [])
    packets = len(graph.get("readinessEvidence") or [])
    stages = Counter(
        entry.get("stage", "unknown") for entry in graph.get("objectReadiness") or []
    )
    print(f"graph={display_path(graph_path)}")
    print(f"graph_sha256={graph_digest}")
    print("structural_policy=strict_zero")
    print(f"objects={objects} evidence_packets={packets}")
    print(
        "stages="
        + " ".join(f"{stage}={count}" for stage, count in sorted(stages.items()))
    )

    if unclassified:
        print(
            "GATE_BLOCK 出现未分层的缺口维度：" + "、".join(unclassified) + "。"
            "新维度必须在 EVIDENCE_CLASS_BY_DIMENSION 里显式写明属结构性、结果还是盲点"
        )
        print(f"report={display_path(report)}")
        return 1

    if blind_spot_problems:
        print("GATE_BLOCK 维度盲点集合与登记册不一致：")
        for problem in blind_spot_problems:
            print(f"  - {problem}")
        print(f"report={display_path(report)}")
        return 1

    print_result_layer(partitions[RESULT])
    print_blind_spots(partitions[BLINDSPOT], blind_spots)

    if structural:
        print_structural_gaps(structural)
        print(f"report={display_path(report)}")
        return 1

    if arguments.require_commercial_readiness:
        if partitions[BLINDSPOT]:
            print(
                "GATE_BLOCK 动态商业 readiness 要求 scanner blindspot 零缺口；"
                "登记过 SHA-bound 实现只能解释静态扫描器误报，不能成为商业准出豁免"
            )
            print_gap_inventory(partitions[BLINDSPOT])
            print(f"report={display_path(report)}")
            return 1
        missing = [
            name
            for name, value in commercial_input_values(arguments).items()
            if value is None
        ]
        if missing:
            dynamic = {
                "status": "invalid_input",
                "commercialReady": False,
                "evaluatorExitCode": 2,
                "closure": None,
                "inputs": {},
                "reason": "missing complete signed readiness inputs: " + ", ".join(missing),
            }
            report = write_reports(
                arguments.report_dir,
                graph_path,
                graph_digest,
                registry_path,
                registry_digest,
                graph,
                gaps,
                cells,
                dynamic,
            )
            print(
                "GATE_BLOCK 动态商业 readiness 输入不完整："
                + "、".join(missing)
            )
            print(f"report={display_path(report)}")
            return 2

        outcome = evaluate_dynamic_readiness(arguments, graph_path, graph_digest)
        report = write_reports(
            arguments.report_dir,
            graph_path,
            graph_digest,
            registry_path,
            registry_digest,
            graph,
            gaps,
            cells,
            outcome.report,
        )
        if outcome.exit_code == 0:
            print("动态商业 readiness：canonical Go evaluator 判定 commercialReady=true")
        elif outcome.exit_code == 1:
            print("GATE_BLOCK 动态商业 readiness：canonical Go evaluator 判定未闭合")
        else:
            print("GATE_BLOCK 动态商业 readiness 输入/协议无效")
        print(f"report={display_path(report)}")
        return outcome.exit_code

    if not structural:
        print("对象 × 层 × 三层测试入口的结构性证据闭合：无缺口"
              "（不代表任何用例已通过；用例结果属结果证据，由 runner 附加）")
        print(f"report={display_path(report)}")
        return 0
    raise AssertionError("structural gaps must have returned above")
