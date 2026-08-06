#!/usr/bin/env python3
"""对象 × 层 × 三层测试入口的 readiness 结构性证据闭合门禁。

判定完全来自 metadata 装载与图构建管线派生出的 ContractGraph：
`readinessEvidence` 由 `quwoquan_service/internal/metadata/load` 从受版本控制的物理
路径反推，`objectReadiness.missing` 由 `internal/metadata/graph` 的
`implementationEvidenceReady` / `commercialEvidenceReady` 判定。本门禁只把这些 missing
键展开成「对象 × 层」缺口清单，不重算 readiness 规则，避免出现第二套真相。

本门禁只校验**结构性证据**：实现 seam 与三层测试文件真实存在、且证据以 SHA256 绑定到
确切字节。「无缺口」只意味着实现与验证入口已就位，**不意味着任何测试通过**——用例是否
通过属于结果证据，只能由 runner 附加，静态派生永远不得代替。

两条自有断言（都把负担落回契约本身，而不是放宽 readiness 规则）：

1. 页面消费闭合：有 clientContract 但没有被任何页面 `object_ids` 认领的对象，必须能在
   别的对象的页面里被证明消费（页面 `query_slices` 指向该对象），否则报缺口。
2. 领域事件声明闭合：`implementation.outbox` 的必需性由对象自己声明的领域事件**投递
   语义**派生（见 `ast.ClassifyEventChannel`）。因此有命令的聚合必须**显式表态**：要么
   声明事件，要么写下 `events: []`；连 `events.yaml` 都没有的聚合等于既没声明也没否认，
   会静默拿到发件箱豁免，在这里报缺口。
3. 事件投递语义闭合：`channel` 一旦成为承重字段，未知取值与缺键就不能静默生效。两者都
   已在图里 fail-safe 到「要求可靠发布」这一侧，这里把触发原因作为独立缺口暴露——未知
   取值是取值失控（topic 名、笔误、二义命名），缺 `channel` 键是契约不完整，关闭方式
   不同，所以分成两个维度。

fail-closed：没有 allowlist、没有豁免、没有 warn-only。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "quwoquan_service"
PAGE_OBJECT_CONTRACT = (
    SERVICE_ROOT / "contracts" / "metadata" / "_shared" / "page_object_contract.yaml"
)
RUN_DIR = ROOT / ".qwq_output" / "env" / "repo" / "runs" / "object-evidence-closure"

# missing 键 → 缺口维度。与 graph.implementationEvidenceReady /
# commercialEvidenceReady 产出的键一一对应。
LAYER_BY_MISSING_KEY = {
    "implementation.domain_behavior": "cloud.domain_behavior",
    "implementation.store": "cloud.store",
    # 事务性事件发布 seam 的三条互斥缺口（见 graph.requirePublicationSeam）：判别位缺失、
    # 归属未声明、事务性追加未观测到。关闭方式各不相同，所以维度也必须分开。
    "contract.storage_publication_unannotated": "contract.storage_publication_role_unannotated",
    "contract.storage_publication_undeclared": "contract.storage_publication_undeclared",
    "implementation.outbox": "cloud.outbox",
    "implementation.reader": "cloud.reader",
    "implementation.transport": "cloud.transport",
    "implementation.local_contract": "test.local_contract",
    "implementation.api_integration": "test.api_integration",
    "implementation.app_client": "app.client",
    "implementation.page": "app.page",
    "implementation.operation_coverage": "derivation.operation_coverage",
    "implementation.evidence_provenance": "derivation.evidence_provenance",
    # UAT 入口是结构性证据；四环境是结果证据（只能由 runner 附加）。维度名以此区分，
    # 避免把「入口缺失」读成「用例未通过」。
    "commercial.user_acceptance": "test.user_acceptance_entry",
    "commercial.environment.alpha": "environment.alpha",
    "commercial.environment.beta": "environment.beta",
    "commercial.environment.gamma": "environment.gamma",
    "commercial.environment.prod": "environment.prod",
    "readiness.evidence": "derivation.evidence_packet",
    "readiness.evidence.duplicate": "derivation.evidence_packet_duplicate",
}

EVIDENCE_FIELDS = (
    "domainBehavior",
    "store",
    "outbox",
    "reader",
    "transport",
    "appClient",
    "page",
    "localContract",
    "apiIntegration",
    "userAcceptance",
)


@dataclass(frozen=True)
class Gap:
    object_id: str
    kind: str
    stage: str
    dimension: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "objectId": self.object_id,
            "kind": self.kind,
            "stage": self.stage,
            "dimension": self.dimension,
            "detail": self.detail,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help=(
            "已有 ContractGraph JSON；缺省时用 build_service_contract_view.py + "
            "qwq_contract generate 以真实仓库根重新派生一份"
        ),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=RUN_DIR,
        help="缺口清单输出目录（默认落在 .qwq_output 下，可删除可重建）",
    )
    return parser.parse_args()


def derive_contract_graph(report_dir: Path) -> Path:
    """用与 codegen 同一条管线重新派生 ContractGraph。

    metadata 视图只含 YAML，所以必须显式传 --repo-root，否则 loader 无法派生任何物理
    证据；这一点由 qwq_contract 自身 fail-closed 保证。
    """
    # 契约视图只允许落在 repo local 缓存下（见 build_service_contract_view.py）。
    view = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "local"
        / "object-evidence-closure"
        / "cache"
        / "view"
    )
    graph_path = report_dir / "contract_graph.json"
    report_dir.mkdir(parents=True, exist_ok=True)
    view.parent.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    build_view = subprocess.run(
        [
            sys.executable,
            str(SERVICE_ROOT / "scripts" / "contracts" / "build_service_contract_view.py"),
            "--output",
            str(view),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if build_view.returncode != 0:
        raise SystemExit(
            "GATE_BLOCK 无法构建服务契约视图:\n"
            f"{build_view.stdout}\n{build_view.stderr}"
        )
    generate = subprocess.run(
        [
            "go",
            "run",
            "./tools/qwq_contract",
            "generate",
            "--metadata-dir",
            str(view),
            "--repo-root",
            str(ROOT),
            "--profile",
            "baseline",
            "--output",
            str(graph_path),
        ],
        cwd=SERVICE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if generate.returncode != 0:
        raise SystemExit(
            "GATE_BLOCK 无法派生 ContractGraph:\n"
            f"{generate.stdout}\n{generate.stderr}"
        )
    return graph_path


def load_graph(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取 ContractGraph {path}: {error}") from error


def page_claims_and_consumers() -> tuple[set[str], dict[str, set[str]]]:
    """从页面对象契约派生「被认领对象」与「被页面读路径消费的对象」。"""
    document = yaml.safe_load(PAGE_OBJECT_CONTRACT.read_text(encoding="utf-8")) or {}
    claimed: set[str] = set()
    consumers: dict[str, set[str]] = defaultdict(set)
    for page in document.get("pages") or []:
        page_id = str(page.get("page_id") or "").strip()
        for object_id in page.get("object_ids") or []:
            claimed.add(str(object_id).strip())
        slices = page.get("query_slices")
        if isinstance(slices, str):
            slices = [slices]
        for slice_reference in slices or []:
            if not isinstance(slice_reference, str):
                continue
            owner = slice_owner_object(slice_reference)
            if owner:
                consumers[owner].add(page_id)
    return claimed, consumers


def object_contract_dir(source_path: str) -> Path | None:
    """`<domain>/<context>/<object>/object.yaml` → 该对象在仓库里的契约目录。

    对象契约既可能属于 `services/<svc>`，也可能属于 `control-plane/<plane>`
    （platform_ops context 就在后者），两处都必须扫。
    """
    parts = Path(source_path).parts
    if len(parts) < 4:
        return None
    context, object_name = parts[1], parts[2]
    for parent in ("services", "control-plane"):
        for candidate in sorted((SERVICE_ROOT / parent).glob(
            f"*/contracts/{context}/{object_name}"
        )):
            if candidate.is_dir():
                return candidate
    return None


def slice_owner_object(reference: str) -> str | None:
    """`<object_id>.projection.<slice>` / `<object_id>.aggregate` → 对象 ID。"""
    for separator in (".projection.", ".aggregate", ".entity"):
        if separator in reference:
            owner = reference.split(separator, 1)[0].strip()
            return owner or None
    return None


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
    claimed, consumers = page_claims_and_consumers()

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

        if kind == "aggregate_root" and object_id in command_objects:
            gaps.extend(domain_event_declaration_gaps(object_id, kind, stage, entry))
        gaps.extend(event_channel_gaps(object_id, kind, stage, state))

        packet = evidence_by_object.get(object_id)
        if packet is None:
            if state.get("contractReady"):
                gaps.append(
                    Gap(object_id, kind, stage, "derivation.evidence_packet",
                        "contract-ready 对象没有派生出证据 packet")
                )
            continue
        gaps.extend(artifact_gaps(object_id, kind, stage, packet))
        if object_id in client_contract_objects and object_id not in claimed:
            pages = consumers.get(object_id) or set()
            if not pages:
                gaps.append(
                    Gap(
                        object_id,
                        kind,
                        stage,
                        "page.consumption_unproven",
                        "有 clientContract 但没有被任何页面 object_ids 认领，"
                        "且没有页面 query_slices 证明它在别的对象页面内被消费",
                    )
                )
    return gaps


def publication_gap_detail(key: str, packet: dict | None) -> str:
    """给发布 seam 的三条互斥缺口补上「哪张存储」，让缺口可直接关闭。

    判定不在这里重算：`publicationStores` / `unannotatedStores` 由 loader 从对象自己的
    `storage.yaml` 的 `publication_role` 派生，`outbox` 证据是「存储名 → 写入位置」绑定。
    """
    if packet is None:
        return ""
    if key == "contract.storage_publication_unannotated":
        stores = packet.get("unannotatedStores") or []
        return (
            "存储未标注 publication_role，无法判别哪张是发布 seam："
            f"{', '.join(stores)}；标注后本缺口自动关闭"
        )
    if key == "contract.storage_publication_undeclared":
        return (
            "标注齐全但没有任何存储被标注为 transactional_outbox / "
            "transactional_event_log，与它声明的投递型领域事件相互否定"
        )
    if key == "implementation.outbox":
        declared = packet.get("publicationStores") or []
        proven = {
            artifact.get("storage")
            for artifact in packet.get("outbox") or []
            if artifact.get("storage")
        }
        unproven = [store for store in declared if store not in proven]
        return (
            "声明了发布 seam 但服务内未观测到对它的事务性追加："
            f"{', '.join(unproven or declared)}"
        )
    return ""


def event_channel_gaps(
    object_id: str,
    kind: str,
    stage: str,
    state: dict,
) -> list[Gap]:
    """把图里已 fail-safe 的 `channel` 触发原因显示成缺口。

    判定不在这里重算：`unrecognizedEventChannels` / `eventsWithoutChannel` 由
    `graph.derivePublicationDuties` 按 `ast.ClassifyEventChannel` 派生，这里只渲染。
    """
    gaps: list[Gap] = []
    unrecognized = state.get("unrecognizedEventChannels") or []
    if unrecognized:
        rendered = ", ".join(repr(value) for value in unrecognized)
        gaps.append(
            Gap(
                object_id,
                kind,
                stage,
                "contract.event_channel_unrecognized",
                f"channel 取值不表达投递语义（topic 名 / 笔误 / 二义命名）：{rendered}；"
                "已 fail-safe 到「要求可靠发布」侧，取值收敛后本缺口自动关闭",
            )
        )
    absent = state.get("eventsWithoutChannel") or []
    if absent:
        gaps.append(
            Gap(
                object_id,
                kind,
                stage,
                "contract.event_channel_absent",
                f"事件缺少 channel 键，契约不完整：{', '.join(absent)}；"
                "已 fail-safe 到「要求可靠发布」侧",
            )
        )
    return gaps


def domain_event_declaration_gaps(
    object_id: str,
    kind: str,
    stage: str,
    entry: dict,
) -> list[Gap]:
    """有命令的聚合必须显式表态是否发布领域事件。

    `implementation.outbox` 的必需性来自这份声明，所以「没有 events.yaml」不能等价于
    「声明不发事件」：那会让发件箱要求被静默跳过。写下 `events: []` 是显式否认，可以；
    连文件都不存在则报缺口，由契约 owner 表态。
    """
    contract_dir = object_contract_dir(str(entry.get("sourcePath") or ""))
    if contract_dir is None:
        return [
            Gap(object_id, kind, stage, "contract.domain_events_undeclared",
                f"无法定位契约目录（sourcePath={entry.get('sourcePath')!r}）")
        ]
    if (contract_dir / "events.yaml").is_file():
        return []
    return [
        Gap(
            object_id,
            kind,
            stage,
            "contract.domain_events_undeclared",
            f"{contract_dir.relative_to(ROOT)} 没有 events.yaml：既没声明领域事件也没写下 "
            "`events: []`，会静默跳过 implementation.outbox 要求",
        )
    ]


def artifact_gaps(object_id: str, kind: str, stage: str, packet: dict) -> list[Gap]:
    """证据必须绑定真实文件：路径不存在即为伪造或已漂移的证据。"""
    gaps: list[Gap] = []
    for field in EVIDENCE_FIELDS:
        for artifact in packet.get(field) or []:
            path = str(artifact.get("path") or "")
            if not path or not (ROOT / path).exists():
                gaps.append(
                    Gap(object_id, kind, stage, "derivation.artifact_missing",
                        f"{field} 证据指向不存在的文件 {path!r}")
                )
    for environment in packet.get("environments") or []:
        path = str((environment.get("artifact") or {}).get("path") or "")
        if not path or not (ROOT / path).exists():
            gaps.append(
                Gap(object_id, kind, stage, "derivation.artifact_missing",
                    f"环境 {environment.get('name')} 证据指向不存在的文件 {path!r}")
            )
    return gaps


def write_reports(report_dir: Path, graph: dict, gaps: list[Gap]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stages = Counter(
        entry.get("stage", "unknown") for entry in graph.get("objectReadiness") or []
    )
    payload = {
        "objects": len(graph.get("objects") or []),
        "evidencePackets": len(graph.get("readinessEvidence") or []),
        "stages": dict(sorted(stages.items())),
        "gapsByDimension": dict(
            sorted(Counter(gap.dimension for gap in gaps).items())
        ),
        "gapsByKind": dict(sorted(Counter(gap.kind for gap in gaps).items())),
        "gaps": [gap.as_dict() for gap in gaps],
    }
    report = report_dir / "object_evidence_closure.json"
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    arguments = parse_args()
    graph_path = arguments.graph or derive_contract_graph(arguments.report_dir)
    graph = load_graph(graph_path)
    gaps = collect_gaps(graph)
    report = write_reports(arguments.report_dir, graph, gaps)

    objects = len(graph.get("objects") or [])
    packets = len(graph.get("readinessEvidence") or [])
    stages = Counter(
        entry.get("stage", "unknown") for entry in graph.get("objectReadiness") or []
    )
    print(f"graph={graph_path.relative_to(ROOT) if graph_path.is_relative_to(ROOT) else graph_path}")
    print(f"objects={objects} evidence_packets={packets}")
    print(
        "stages="
        + " ".join(f"{stage}={count}" for stage, count in sorted(stages.items()))
    )
    if not gaps:
        print("对象 × 层 × 三层测试入口的结构性证据闭合：无缺口"
              "（不代表任何用例已通过；用例结果属结果证据，由 runner 附加）")
        print(f"report={report.relative_to(ROOT)}")
        return 0

    by_dimension: dict[str, list[Gap]] = defaultdict(list)
    for gap in gaps:
        by_dimension[gap.dimension].append(gap)
    print(f"GATE_BLOCK 结构性证据闭合缺口 {len(gaps)} 条，覆盖 "
          f"{len({gap.object_id for gap in gaps})} 个对象：")
    for dimension in sorted(by_dimension, key=lambda key: (-len(by_dimension[key]), key)):
        items = by_dimension[dimension]
        kinds = " ".join(
            f"{kind}={count}"
            for kind, count in sorted(Counter(gap.kind for gap in items).items())
        )
        print(f"  {dimension}: {len(items)} 条 [{kinds}]")
        for gap in sorted(items, key=lambda item: item.object_id):
            print(f"    - {gap.object_id} ({gap.kind}, {gap.stage}): {gap.detail}")
    print(f"report={report.relative_to(ROOT)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
