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
   保证**派生（见 `ast.ClassifyEventDelivery`）。因此有命令的聚合必须**显式表态**：要么
   声明事件，要么写下 `events: []`；连 `events.yaml` 都没有的聚合等于既没声明也没否认，
   会静默拿到发件箱豁免，在这里报缺口。

曾经这里还有第三条「事件投递语义闭合」，把 `channel` 的未知取值与缺键当独立缺口暴露。
它是**没有值域**时的补偿：那时 topic 名、笔误和机制名混在同一个字段里，只能靠 fail-safe
留痕让失控可见。`channel` 拆成受控 `delivery_semantics` 与自由 `topic` 之后，取值域由
`_schemas/events.schema.json` 的 enum 与 required 直接强制，两类情况都在 schema 层就无法
通过，维度随之关闭——这正是当时写在缺口文案里的「取值收敛后本缺口自动关闭」。

结构缺口已进入严格零值模式：任何 STRUCTURAL 维度只要实测大于 0 就直接
BLOCK。历史棘轮基线已退役，既不提供刷新入口，也不允许通过重建基线为缺口发放额度。
`commercial.result_bundle` 和四环境回执仍是 RESULT 证据：它们必须在可信 runner 中完成，
静态结构门只报告、不伪造动态 PASS。

fail-closed：没有 allowlist、没有豁免、没有 warn-only。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
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
READINESS_METADATA_DIR = SERVICE_ROOT / "contracts" / "metadata"
READINESS_EVALUATOR_PACKAGE = "./tools/evaluate_readiness"
READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS = 120
READINESS_EVALUATOR_RUN_TIMEOUT_SECONDS = 120
# 证据分层。分层依据写在这里而不是靠维度名约定：同一个键改判哪一层必须改这张表，
# 改动因此会出现在 diff 里。
#
#   STRUCTURAL：源码与契约里可静态判定的事实（实现 seam、三层测试入口、页面认领）。
#     它有确定的关闭动作，缺就是缺，因此 fail-closed 并串进 gate_repo.sh。
#   RESULT：需要真实环境跑出来才存在的回执（四环境部署/巡检证据）。静态派生永远拿不到，
#     把它做成阻断条件等于用一条永远为假的条件锁住全仓，所以只报告不阻断。
#   BLINDSPOT：判定器**明知自己看不见**的地方（Go AST 跟不动的跨函数句柄注入、
#     Python 实现、扫描范围外的共享 dispatcher）。它既不是达标也不是缺口：报成缺口会让人
#     去补一份本来就存在的实现，静默判达标则等于假装看见。盲点条目必须在
#     `object_evidence_blind_spots.yaml` 里登记并分类；只有写入与投递都由 SHA-bound artifact
#     证明的 scanner false-negative 可放行，implementation_missing 与未登记项都直接 BLOCK。
STRUCTURAL = "structural"
RESULT = "result"
BLINDSPOT = "blindspot"

# `userAcceptance` 按事实归结构性入口：它表达「有没有 UAT 入口文件」，不是「UAT 过了」。
# UAT 回执属结果证据，当前没有承载字段，这是规格线在补的真缺口，不得用入口冒充。
EVIDENCE_CLASS_BY_DIMENSION = {
    "cloud.domain_behavior": STRUCTURAL,
    "cloud.store": STRUCTURAL,
    "cloud.outbox": STRUCTURAL,
    "cloud.publication_delivery": STRUCTURAL,
    "cloud.reader": STRUCTURAL,
    "cloud.transport": STRUCTURAL,
    "cloud.external_implementation": STRUCTURAL,
    "contract.storage_publication_role_unannotated": STRUCTURAL,
    "contract.storage_publication_undeclared": STRUCTURAL,
    "contract.storage_declaration_missing": STRUCTURAL,
    "contract.domain_events_undeclared": STRUCTURAL,
    "test.local_contract": STRUCTURAL,
    "test.api_integration": STRUCTURAL,
    "test.user_acceptance_entry": STRUCTURAL,
    "ops.environment_acceptance_entry": STRUCTURAL,
    "ops.rollback_runner_entry": STRUCTURAL,
    "ops.replay_runner_entry": STRUCTURAL,
    "app.client": STRUCTURAL,
    "app.page": STRUCTURAL,
    "page.consumption_unproven": STRUCTURAL,
    "app.unconsumed_contract": STRUCTURAL,
    "derivation.operation_coverage": STRUCTURAL,
    "derivation.evidence_provenance": STRUCTURAL,
    "derivation.evidence_packet": STRUCTURAL,
    "derivation.evidence_packet_duplicate": STRUCTURAL,
    "derivation.readiness_missing": STRUCTURAL,
    "derivation.artifact_missing": STRUCTURAL,
    "derivation.artifact_digest": STRUCTURAL,
    "commercial.result_bundle": RESULT,
    "blindspot.publication_write_tracking": BLINDSPOT,
    "blindspot.publication_delivery_tracking": BLINDSPOT,
    "blindspot.python_store_invisible": BLINDSPOT,
}

BLIND_SPOT_REGISTRY = (
    ROOT / "quwoquan_ops" / "policies" / "gates" / "object_evidence_blind_spots.yaml"
)
BLIND_SPOT_IMPLEMENTED = "scanner_false_negative_implemented"
BLIND_SPOT_MISSING = "implementation_missing"
BLIND_SPOT_CLASSIFICATIONS = {BLIND_SPOT_IMPLEMENTED, BLIND_SPOT_MISSING}
BLIND_SPOT_IMPLEMENTATION_EVIDENCE = (
    "publication_write",
    "publication_delivery",
)
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
DART_NON_CODE_RE = re.compile(
    r"//[^\n]*"
    r"|/\*.*?\*/"
    r"|'''.*?'''"
    r'|""".*?"""'
    r"|r?'(?:\\.|[^'\\])*'"
    r'|r?"(?:\\.|[^"\\])*"',
    re.DOTALL,
)
REPORT_GRAPH_FIELD = "contractGraph"
REPORT_BLIND_SPOT_REGISTRY_FIELD = "blindSpotRegistry"

# missing 键 → 缺口维度。与 graph.implementationEvidenceReady /
# commercialEvidenceReady 产出的键一一对应。
LAYER_BY_MISSING_KEY = {
    "implementation.service.domain": "cloud.domain_behavior",
    "implementation.service.store": "cloud.store",
    # 事务性事件发布 seam 的三条互斥缺口（见 graph.requirePublicationSeam）：判别位缺失、
    # 归属未声明、事务性追加未观测到。关闭方式各不相同，所以维度也必须分开。
    "contract.storage_publication_unannotated": "contract.storage_publication_role_unannotated",
    "contract.storage_publication_undeclared": "contract.storage_publication_undeclared",
    "implementation.outbox": "cloud.outbox",
    "implementation.publication_delivery": "cloud.publication_delivery",
    # 反方向：有事务性写入但全仓无声明位。它与「声明了但没观测到写入」修法不同
    # （补声明 vs 补实现），所以必须是独立维度，合成一条会让其中一侧永远看不见。
    "contract.storage_declaration_missing": "contract.storage_declaration_missing",
    # 判定器看不见的地方，按盲点登记而不是按缺口阻断。
    "blindspot.publication_write_tracking": "blindspot.publication_write_tracking",
    "blindspot.publication_delivery_tracking": "blindspot.publication_delivery_tracking",
    "blindspot.python_store_invisible": "blindspot.python_store_invisible",
    "implementation.service.reader": "cloud.reader",
    "implementation.service.transport": "cloud.transport",
    # external_reference 只要求 store / transport 任一实现边界；不能把二选一
    # 缺口伪装成其中某一条单轨缺口，因此使用独立结构维度。
    "implementation.service.store_or_transport": "cloud.external_implementation",
    # Canonical producer-separated App evidence keys.  These are source/test
    # entrypoints, not runner results, so they remain strict structural gaps.
    "implementation.app.application": "app.client",
    "implementation.app.adapters": "app.client",
    "implementation.app.local_contract": "test.local_contract",
    "implementation.app.api_integration": "test.api_integration",
    "implementation.app.presentation": "app.page",
    "implementation.app.user_acceptance": "test.user_acceptance_entry",
    "implementation.service.local_contract": "test.local_contract",
    "implementation.service.api_integration": "test.api_integration",
    "implementation.ops.environment_acceptance": "ops.environment_acceptance_entry",
    "implementation.ops.rollback_runner": "ops.rollback_runner_entry",
    "implementation.ops.replay_runner": "ops.replay_runner_entry",
    "implementation.operation_coverage": "derivation.operation_coverage",
    "implementation.evidence_provenance": "derivation.evidence_provenance",
    # UAT 入口是结构性证据；四环境是结果证据（只能由 runner 附加）。维度名以此区分，
    # 避免把「入口缺失」读成「用例未通过」。
    "commercial.result_bundle": "commercial.result_bundle",
    "readiness.evidence": "derivation.evidence_packet",
    "readiness.evidence.duplicate": "derivation.evidence_packet_duplicate",
}

ARTIFACT_EVIDENCE_FIELDS = (
    ("service", "domain"),
    ("service", "store"),
    ("service", "reader"),
    ("service", "transport"),
    ("service", "localContract"),
    ("service", "apiIntegration"),
    ("app", "domain"),
    ("app", "application"),
    ("app", "adapters"),
    ("app", "presentation"),
    ("app", "localContract"),
    ("app", "apiIntegration"),
    ("app", "userAcceptance"),
    ("ops", "environmentAcceptance"),
    ("ops", "rollbackRunner"),
    ("ops", "replayRunner"),
)
STORAGE_EVIDENCE_FIELDS = (
    ("service", "outbox"),
)

# ObjectReadinessEvidence 的 canonical JSON shape 与 ast/model.go 的 typed
# producer-separated schema 一一对应。这里不重新定义 readiness 判定，只拒绝旧扁平 packet
# 或缺字段 packet 被 `.get(..., [])` 静默解释为“没有证据”。新增 producer 字段必须先同步
# typed schema 与本门禁，不能靠 unknown-key 宽松读取形成第二条证据路径。
PRODUCER_ARTIFACT_FIELDS = {
    "service": (
        "domain",
        "store",
        "reader",
        "transport",
        "localContract",
        "apiIntegration",
    ),
    "app": (
        "domain",
        "application",
        "adapters",
        "presentation",
        "localContract",
        "apiIntegration",
        "userAcceptance",
    ),
    "ops": (
        "environmentAcceptance",
        "rollbackRunner",
        "replayRunner",
    ),
}
PRODUCER_STORAGE_FIELDS = {"service": ("outbox",)}
PRODUCER_BOOLEAN_FIELDS = {"app": ("pageParticipant", "pageOwned")}
PACKET_STRING_LIST_FIELDS = (
    "operationIds",
    "publicationStores",
    "deliveryStores",
    "unannotatedStores",
    "unresolvedPublicationWrites",
    "unresolvedPublicationDelivery",
    "undeclaredStorageWrites",
)
PACKET_OPTIONAL_FIELDS = {
    "publicationStores",
    "deliveryStores",
    "publicationDelivery",
    "unannotatedStores",
    "unresolvedPublicationWrites",
    "unresolvedPublicationDelivery",
    "undeclaredStorageWrites",
    "pythonImplementation",
}
PACKET_REQUIRED_FIELDS = {
    "objectId",
    "operationIds",
    "service",
    "app",
    "ops",
    "sourcePath",
}
PACKET_ALLOWED_FIELDS = PACKET_REQUIRED_FIELDS | PACKET_OPTIONAL_FIELDS
LEGACY_FLATTENED_EVIDENCE_FIELDS = {
    "domain",
    "domainBehavior",
    "store",
    "outbox",
    "reader",
    "transport",
    "localContract",
    "apiIntegration",
    "application",
    "adapters",
    "presentation",
    "userAcceptance",
    "appClient",
    "page",
    "environmentAcceptance",
    "rollbackRunner",
    "replayRunner",
}


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


@dataclass(frozen=True)
class DynamicEvaluation:
    exit_code: int
    report: dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help=(
            "显式判定的 ContractGraph JSON（主要供契约测试/已绑定 artifact 使用）；"
            "缺省从当前工作树现场派生，不复用可能陈旧的 committed graph"
        ),
    )
    parser.add_argument(
        "--derive",
        action="store_true",
        help=(
            "改用 build_service_contract_view.py + qwq_contract generate 以真实仓库根"
            "现场派生一份图（需要 Go 工具链，约 30 秒）"
        ),
    )
    parser.add_argument(
        "--require-commercial-readiness",
        action="store_true",
        help=(
            "结构证据严格为零后，以六项完整 trust input 直接调用 canonical Go "
            "evaluator；缺项或协议错误返回 2"
        ),
    )
    parser.add_argument(
        "--readiness-bundle",
        type=Path,
        default=None,
        help="untrusted ReadinessResultBundle JSON; trust comes from signed receipts",
    )
    parser.add_argument(
        "--signed-current-snapshot",
        type=Path,
        default=None,
        help="package-bound Ed25519 SignedCurrentSnapshot JSON",
    )
    parser.add_argument(
        "--snapshot-keyring",
        type=Path,
        default=None,
        help="trusted snapshot authority public-key keyring JSON",
    )
    parser.add_argument(
        "--runner-keyring",
        type=Path,
        default=None,
        help="trusted runner public-key keyring JSON",
    )
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=None,
        help="restricted root containing detached-signed readiness receipts",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=None,
        help="restricted content-addressed readiness evidence root",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=RUN_DIR,
        help="缺口清单输出目录（默认落在 .qwq_output 下，可删除可重建）",
    )
    arguments = parser.parse_args()
    if arguments.derive and arguments.graph is not None:
        parser.error("--derive 与 --graph 互斥：判定源必须唯一")
    commercial_values = commercial_input_values(arguments)
    if any(value is not None for value in commercial_values.values()) and not (
        arguments.require_commercial_readiness
    ):
        parser.error(
            "dynamic readiness inputs require --require-commercial-readiness"
        )
    return arguments


def commercial_input_values(arguments: argparse.Namespace) -> dict[str, Path | None]:
    return {
        "resultBundle": getattr(arguments, "readiness_bundle", None),
        "signedCurrentSnapshot": getattr(
            arguments, "signed_current_snapshot", None
        ),
        "snapshotKeyring": getattr(arguments, "snapshot_keyring", None),
        "runnerKeyring": getattr(arguments, "runner_keyring", None),
        "receiptRoot": getattr(arguments, "receipt_root", None),
        "evidenceRoot": getattr(arguments, "evidence_root", None),
    }


def select_graph_path(arguments: argparse.Namespace) -> Path:
    """选择唯一判定图。

    required gate 缺省必须从当前受管源码现场派生；否则单独运行本门时，
    陈旧 generated graph 会把 scanner/合同改动隐藏成假绿。只有显式 `--graph` 才允许评估
    调用者已精确绑定的图字节。
    """
    if arguments.graph is not None:
        return Path(arguments.graph)
    return derive_contract_graph(Path(arguments.report_dir))


def derive_contract_graph(report_dir: Path) -> Path:
    """用与 codegen 同一条管线重新派生 ContractGraph。

    metadata 视图只含 YAML，所以必须显式传 --repo-root，否则 loader 无法派生任何物理
    证据；这一点由 qwq_contract 自身 fail-closed 保证。
    """
    # 契约视图与派生图都只能落在 repo-local 可重建缓存，并且必须逐次隔离。
    # build_service_contract_view 会重建目标目录；共享固定 view 会让两个 gate
    # 互相删除 symlink 树。共享固定 graph 也会让一方在 load 前读到另一方覆盖的
    # 字节，所以两者必须处于同一个唯一 derive work root。
    cache_root = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "local"
        / "object-evidence-closure"
        / "cache"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix="derive-", dir=cache_root))
    view = work_root / "view"
    graph_path = work_root / "contract_graph.json"
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


def display_path(path: Path) -> str:
    """仓内路径显示为相对路径；仓外路径（测试临时目录）原样保留。"""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_readiness_input(path: Path) -> dict[str, str | int]:
    """绑定商业判定输入的当前字节；目录按相对路径 + 文件字节确定性摘要。

    receipt/evidence root 是 evaluator 的受限查找边界，不是单个文件。这里不解释
    其中内容，只保证报告能精确指向本次执行看到的整棵普通文件树。symlink 与特殊文件
    一律拒绝，避免摘要与 Go resolver 实际读取的对象不一致。
    """
    if path.is_symlink():
        raise ValueError(f"input must not be a symlink: {path}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"input does not exist or cannot be resolved: {path}: {error}") from error
    if resolved.is_file():
        return {
            "path": display_path(resolved),
            "kind": "file",
            "sha256": sha256_file(resolved),
            "fileCount": 1,
        }
    if not resolved.is_dir():
        raise ValueError(f"input must be a regular file or directory: {path}")

    digest = hashlib.sha256()
    file_count = 0
    for candidate in sorted(resolved.rglob("*"), key=lambda value: value.as_posix()):
        if candidate.is_symlink():
            raise ValueError(f"input tree must not contain symlinks: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ValueError(f"input tree contains a special file: {candidate}")
        relative = candidate.relative_to(resolved).as_posix().encode("utf-8")
        payload = candidate.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        file_count += 1
    return {
        "path": display_path(resolved),
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "fileCount": file_count,
    }


def readiness_input_bindings(arguments: argparse.Namespace) -> dict[str, dict]:
    bindings: dict[str, dict] = {}
    for name, path in commercial_input_values(arguments).items():
        if path is None:
            raise ValueError(f"missing commercial readiness input: {name}")
        bindings[name] = digest_readiness_input(Path(path))
    return bindings


def verify_readiness_input_bindings(
    arguments: argparse.Namespace,
    expected: dict[str, dict],
) -> None:
    actual = readiness_input_bindings(arguments)
    if actual != expected:
        raise ValueError(
            "commercial readiness inputs changed during evaluation: "
            f"expected={expected!r} actual={actual!r}"
        )


def decode_single_json_document(stdout: str) -> dict:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    decoder = json.JSONDecoder(object_pairs_hook=reject_duplicate_keys)
    try:
        payload, offset = decoder.raw_decode(stdout.lstrip())
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"readiness evaluator emitted invalid JSON: {error}") from error
    consumed_prefix = len(stdout) - len(stdout.lstrip())
    if stdout[consumed_prefix + offset :].strip():
        raise ValueError("readiness evaluator emitted multiple JSON documents")
    if not isinstance(payload, dict):
        raise ValueError("readiness evaluator JSON must be an object")
    return payload


def build_readiness_evaluator(work_root: Path) -> tuple[Path, str]:
    binary = work_root / "evaluate_readiness"
    environment = {**os.environ, "GOFLAGS": "-mod=readonly"}
    try:
        completed = subprocess.run(
            [
                "go",
                "build",
                "-trimpath",
                "-o",
                str(binary),
                READINESS_EVALUATOR_PACKAGE,
            ],
            cwd=SERVICE_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"cannot build readiness evaluator: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:2000]
        raise ValueError(f"cannot build readiness evaluator: {detail}")
    if not binary.is_file() or binary.is_symlink():
        raise ValueError("readiness evaluator build did not produce a regular binary")
    return binary, sha256_file(binary)


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


def _shape_block(location: str, detail: str) -> None:
    raise SystemExit(
        "GATE_BLOCK ContractGraph readinessEvidence 不是 canonical "
        f"producer-separated packet：{location} {detail}"
    )


def _validate_string_list(value: object, location: str) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        _shape_block(location, "必须是非空字符串组成的 list")


def _validate_artifact_shape(value: object, location: str) -> None:
    if not isinstance(value, dict):
        _shape_block(location, "必须是 Artifact {path, sha256}")
    if set(value) != {"path", "sha256"}:
        _shape_block(
            location,
            "必须且只能包含 path/sha256；EvidenceArtifact 不承载 storage 或兼容字段",
        )
    path_text = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path_text, str) or not path_text.strip():
        _shape_block(f"{location}.path", "必须是非空 repository-relative 字符串")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        _shape_block(f"{location}.sha256", "必须是 64 位小写十六进制摘要")


def _validate_artifact_list(value: object, location: str) -> None:
    if not isinstance(value, list):
        _shape_block(location, "必须是 Artifact list")
    for index, artifact in enumerate(value):
        _validate_artifact_shape(artifact, f"{location}[{index}]")


def _validate_storage_evidence_shape(value: object, location: str) -> None:
    if not isinstance(value, dict):
        _shape_block(location, "必须是 StorageEvidence {storage, artifact}")
    if set(value) != {"storage", "artifact"}:
        _shape_block(
            location,
            "必须且只能包含 storage/artifact；旧扁平 storage/path/sha256 不可复用",
        )
    storage = value.get("storage")
    if not isinstance(storage, str) or not storage.strip():
        _shape_block(f"{location}.storage", "必须是非空字符串")
    _validate_artifact_shape(value.get("artifact"), f"{location}.artifact")


def _validate_storage_evidence_list(value: object, location: str) -> None:
    if not isinstance(value, list):
        _shape_block(location, "必须是 StorageEvidence list")
    for index, evidence in enumerate(value):
        _validate_storage_evidence_shape(evidence, f"{location}[{index}]")


def _validate_producer_shape(packet: dict, producer: str, location: str) -> None:
    value = packet.get(producer)
    if not isinstance(value, dict):
        _shape_block(f"{location}.{producer}", "必须是 map")
    expected = (
        set(PRODUCER_ARTIFACT_FIELDS.get(producer, ()))
        | set(PRODUCER_STORAGE_FIELDS.get(producer, ()))
        | set(PRODUCER_BOOLEAN_FIELDS.get(producer, ()))
    )
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing or unexpected:
        _shape_block(
            f"{location}.{producer}",
            f"字段不闭合（missing={missing}, unexpected={unexpected}）",
        )
    for field in PRODUCER_ARTIFACT_FIELDS.get(producer, ()):
        _validate_artifact_list(value[field], f"{location}.{producer}.{field}")
    for field in PRODUCER_STORAGE_FIELDS.get(producer, ()):
        _validate_storage_evidence_list(
            value[field], f"{location}.{producer}.{field}"
        )
    for field in PRODUCER_BOOLEAN_FIELDS.get(producer, ()):
        if not isinstance(value[field], bool):
            _shape_block(f"{location}.{producer}.{field}", "必须是 bool")


def validate_contract_graph_shape(graph: object) -> None:
    """拒绝旧扁平证据和不完整 producer maps，避免缺字段被解释成空证据。"""
    if not isinstance(graph, dict):
        _shape_block("ContractGraph", "必须是 JSON object")
    packets = graph.get("readinessEvidence")
    if not isinstance(packets, list):
        _shape_block("readinessEvidence", "必须是 list")
    for index, packet in enumerate(packets):
        location = f"readinessEvidence[{index}]"
        if not isinstance(packet, dict):
            _shape_block(location, "必须是 object")
        legacy = sorted(set(packet) & LEGACY_FLATTENED_EVIDENCE_FIELDS)
        if legacy:
            _shape_block(
                location,
                f"包含旧扁平证据字段 {legacy}；证据必须归入 service/app/ops",
            )
        missing = sorted(PACKET_REQUIRED_FIELDS - set(packet))
        unexpected = sorted(set(packet) - PACKET_ALLOWED_FIELDS)
        if missing or unexpected:
            _shape_block(
                location,
                f"字段不闭合（missing={missing}, unexpected={unexpected}）",
            )
        for field in ("objectId", "sourcePath"):
            value = packet[field]
            if not isinstance(value, str) or not value.strip():
                _shape_block(f"{location}.{field}", "必须是非空字符串")
        for field in PACKET_STRING_LIST_FIELDS:
            if field in packet:
                _validate_string_list(packet[field], f"{location}.{field}")
        if "pythonImplementation" in packet and not isinstance(
            packet["pythonImplementation"], bool
        ):
            _shape_block(f"{location}.pythonImplementation", "必须是 bool")
        for producer in ("service", "app", "ops"):
            _validate_producer_shape(packet, producer, location)
        if "publicationDelivery" in packet:
            _validate_storage_evidence_list(
                packet["publicationDelivery"], f"{location}.publicationDelivery"
            )


def load_graph_with_digest(path: Path) -> tuple[dict, str]:
    """一次读取图字节并绑定摘要，避免解析内容与 report identity 来自两次读取。"""
    try:
        payload = path.read_bytes()
        graph = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取 ContractGraph {path}: {error}") from error
    validate_contract_graph_shape(graph)
    return graph, hashlib.sha256(payload).hexdigest()


def load_graph(path: Path) -> dict:
    return load_graph_with_digest(path)[0]


def verify_graph_digest(path: Path, expected: str) -> None:
    """报告落盘前后都复核输入图；运行中漂移不得产生可复用 PASS report。"""
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise SystemExit(f"GATE_BLOCK 无法复核 ContractGraph {path}: {error}") from error
    if actual != expected:
        raise SystemExit(
            "GATE_BLOCK ContractGraph 在对象证据判定期间发生漂移："
            f"expected={expected} actual={actual} path={display_path(path)}"
        )


def validate_report_graph_binding(report: Path, graph_path: Path) -> None:
    """一次性 report 必须精确绑定本次读取的 graph path 与原始字节摘要。"""
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取对象证据报告 {report}: {error}") from error
    binding = document.get(REPORT_GRAPH_FIELD)
    if not isinstance(binding, dict):
        raise SystemExit(
            f"GATE_BLOCK 对象证据报告缺少 {REPORT_GRAPH_FIELD}.path/sha256，"
            "未绑定输入 ContractGraph 的报告不得复用"
        )
    reported_path = str(binding.get("path") or "")
    reported_digest = str(binding.get("sha256") or "")
    if reported_path != display_path(graph_path):
        raise SystemExit(
            "GATE_BLOCK 对象证据报告绑定了另一份 ContractGraph："
            f"report={reported_path!r} actual={display_path(graph_path)!r}"
        )
    if not SHA256_PATTERN.fullmatch(reported_digest):
        raise SystemExit(
            f"GATE_BLOCK 对象证据报告缺少合法 {REPORT_GRAPH_FIELD}.sha256"
        )
    try:
        actual_digest = sha256_file(graph_path)
    except OSError as error:
        raise SystemExit(
            f"GATE_BLOCK 无法复核报告绑定的 ContractGraph {graph_path}: {error}"
        ) from error
    if actual_digest != reported_digest:
        raise SystemExit(
            "GATE_BLOCK 对象证据报告与 ContractGraph 摘要不一致："
            f"report={reported_digest} actual={actual_digest}"
        )


def _report_input_binding(path: Path, digest: str | None) -> dict[str, str]:
    if digest is None:
        return {"path": display_path(path), "status": "absent"}
    return {"path": display_path(path), "sha256": digest}


def verify_optional_input_digest(
    path: Path, expected: str | None, label: str
) -> None:
    """复核 policy input 在判定期间没有出现、消失或换字节。"""
    if expected is None:
        if path.exists():
            raise SystemExit(
                f"GATE_BLOCK {label} 在对象证据判定期间从 absent 变为存在："
                f"path={display_path(path)}"
            )
        return
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise SystemExit(
            f"GATE_BLOCK 无法复核 {label} {path}: {error}"
        ) from error
    if actual != expected:
        raise SystemExit(
            f"GATE_BLOCK {label} 在对象证据判定期间发生漂移："
            f"expected={expected} actual={actual} path={display_path(path)}"
        )


def validate_report_policy_bindings(
    report: Path,
    registry_path: Path,
    registry_digest: str | None,
) -> None:
    """report 必须绑定本次实际消费的 blindspot registry 字节。"""
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"GATE_BLOCK 无法读取对象证据报告 {report}: {error}") from error
    expected = {
        REPORT_BLIND_SPOT_REGISTRY_FIELD: _report_input_binding(
            registry_path, registry_digest
        ),
    }
    for field, binding in expected.items():
        if document.get(field) != binding:
            raise SystemExit(
                f"GATE_BLOCK 对象证据报告的 {field} 输入绑定不一致："
                f"report={document.get(field)!r} expected={binding!r}"
            )
    verify_optional_input_digest(registry_path, registry_digest, "盲点登记册")


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

    runtime_consumers = _runtime_execution_consumers(
        document.get("runtime_execution"),
        operations=operations,
        known_objects=objects,
        claimed=claimed,
    )
    return claimed, query_consumers, command_consumers, runtime_consumers


def _without_dart_non_code(source: str) -> str:
    """剥离注释与字符串，避免用注释/常量伪造 production evidence。"""

    def replace(match: re.Match[str]) -> str:
        newline_count = match.group(0).count("\n")
        return "\n" * newline_count if newline_count else " "

    return DART_NON_CODE_RE.sub(replace, source)


def _runtime_execution_consumers(
    raw_entries: object,
    *,
    operations: dict[str, dict],
    known_objects: set[str],
    claimed: set[str],
) -> dict[str, set[str]]:
    """Validate explicit non-page App execution chains and return object owners."""
    if raw_entries is None:
        return {}
    if not isinstance(raw_entries, list):
        raise SystemExit("GATE_BLOCK runtime_execution 必须是列表")

    result: dict[str, set[str]] = defaultdict(set)
    seen_objects: set[str] = set()
    app_root = ROOT / "quwoquan_app"
    for index, raw_entry in enumerate(raw_entries):
        location = f"runtime_execution[{index}]"
        if not isinstance(raw_entry, dict):
            raise SystemExit(f"GATE_BLOCK {location} 必须是 mapping")
        if set(raw_entry) != {"object_id", "operation_ids", "production_evidence"}:
            raise SystemExit(
                f"GATE_BLOCK {location} 字段必须精确为 object_id / operation_ids / "
                "production_evidence"
            )
        object_id = str(raw_entry.get("object_id") or "").strip()
        if not object_id or object_id in seen_objects:
            raise SystemExit(f"GATE_BLOCK {location} object_id 为空或重复: {object_id!r}")
        seen_objects.add(object_id)
        if object_id not in known_objects:
            continue
        if object_id in claimed:
            raise SystemExit(
                f"GATE_BLOCK {location} {object_id} 已是 page participant，"
                "不得再以 runtime_execution 双轨关闭"
            )

        operation_ids = raw_entry.get("operation_ids")
        if (
            not isinstance(operation_ids, list)
            or not operation_ids
            or any(not isinstance(value, str) or not value.strip() for value in operation_ids)
            or len(operation_ids) != len(set(operation_ids))
        ):
            raise SystemExit(
                f"GATE_BLOCK {location}.operation_ids 必须是非空不重复字符串列表"
            )
        bound_operations: list[dict] = []
        for operation_id in operation_ids:
            operation_id = operation_id.strip()
            operation = operations.get(operation_id)
            if (
                operation is None
                or not operation.get("clientContract")
                or operation.get("objectId") != object_id
            ):
                raise SystemExit(
                    f"GATE_BLOCK {location} operation 不存在、非 App clientContract "
                    f"或对象不匹配: {operation_id}"
                )
            bound_operations.append(operation)

        evidence = raw_entry.get("production_evidence")
        if not isinstance(evidence, list) or len(evidence) < 2:
            raise SystemExit(
                f"GATE_BLOCK {location}.production_evidence 至少需要 adapter/binding "
                "与真实 execution owner 两个生产文件"
            )
        source_chunks: list[str] = []
        execution_owner_found = False
        seen_paths: set[str] = set()
        for evidence_index, raw_evidence in enumerate(evidence):
            evidence_location = f"{location}.production_evidence[{evidence_index}]"
            if not isinstance(raw_evidence, dict) or set(raw_evidence) != {"path", "symbols"}:
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location} 字段必须精确为 path / symbols"
                )
            relative = str(raw_evidence.get("path") or "").strip()
            symbols = raw_evidence.get("symbols")
            if (
                not relative.startswith("lib/")
                or not relative.endswith(".dart")
                or "/generated/" in relative
                or relative in seen_paths
            ):
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.path 必须是唯一非 generated App "
                    f"production Dart: {relative!r}"
                )
            seen_paths.add(relative)
            absolute = (app_root / relative).resolve()
            try:
                absolute.relative_to((app_root / "lib").resolve())
            except ValueError as error:
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.path 越出 App lib: {relative}"
                ) from error
            if not absolute.is_file():
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.path 不存在: {relative}"
                )
            if (
                not isinstance(symbols, list)
                or not symbols
                or any(not isinstance(symbol, str) or not symbol.strip() for symbol in symbols)
                or len(symbols) != len(set(symbols))
            ):
                raise SystemExit(
                    f"GATE_BLOCK {evidence_location}.symbols 必须是非空不重复字符串列表"
                )
            source = _without_dart_non_code(
                absolute.read_text(encoding="utf-8", errors="ignore")
            )
            for symbol in symbols:
                if not re.search(rf"\b{re.escape(symbol.strip())}\b", source):
                    raise SystemExit(
                        f"GATE_BLOCK {evidence_location} 未消费声明 symbol "
                        f"{symbol!r}: {relative}"
                    )
            source_chunks.append(source)
            if "/adapters/" not in relative and not relative.startswith("lib/runtime/di/"):
                execution_owner_found = True
        if not execution_owner_found:
            raise SystemExit(
                f"GATE_BLOCK {location} 只有 adapter/DI，没有可验证 production "
                "runtime/background execution owner"
            )

        combined_source = "\n".join(source_chunks)
        for operation in bound_operations:
            tokens = {
                str(operation.get(field) or "").strip()
                for field in ("localId", "requestEntity", "facadeMethod")
                if str(operation.get(field) or "").strip()
            }
            # localId may be embedded in a canonical generated identifier, e.g.
            # `realtimeConnectionWebSocketUpgrade`; operation binding therefore
            # uses an exact case-sensitive substring while evidence symbols above
            # still require identifier boundaries.
            if not tokens or not any(token in combined_source for token in tokens):
                raise SystemExit(
                    f"GATE_BLOCK {location} production evidence 未绑定 operation "
                    f"{operation.get('id')} 的 localId/requestEntity/facadeMethod"
                )
        result[object_id].update(str(value).strip() for value in operation_ids)
    return result


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


def slice_owner_object(reference: str, known_objects: set[str] | None = None) -> str | None:
    """`<object_id>.projection.<slice>` / `<object_id>.aggregate` → 对象 ID。"""
    reference = reference.strip()
    if known_objects is not None and reference in known_objects:
        return reference
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
        unproven = [
            store
            for store in declared
            if store not in bound_storages(packet, "service", "outbox")
        ]
        return (
            "声明了发布 seam 但服务内未观测到持有事务句柄的函数对它写入："
            f"{', '.join(unproven or declared)}"
        )
    if key == "implementation.publication_delivery":
        declared = packet.get("deliveryStores") or []
        undelivered = [
            store
            for store in declared
            if store not in bound_storages(packet, "", "publicationDelivery")
        ]
        return (
            "发件箱有事务性追加但没有任何投递实现（没有代码读取它并推进进度）："
            f"{', '.join(undelivered or declared)}"
        )
    if key == "contract.storage_declaration_missing":
        return (
            "对象实现树里事务性写入了全仓无人声明的关系："
            f"{', '.join(packet.get('undeclaredStorageWrites') or [])}"
        )
    if key == "blindspot.publication_write_tracking":
        return (
            "关系名在服务里被绑定过，但写入发生在 Go AST 跟不动的位置（构造参数注入的"
            "句柄 / 调用方传入的事务上下文）："
            f"{', '.join(packet.get('unresolvedPublicationWrites') or [])}"
        )
    if key == "blindspot.publication_delivery_tracking":
        return (
            "投递实现在扫描范围之外（表名参数化地交给共享 dispatcher）："
            f"{', '.join(packet.get('unresolvedPublicationDelivery') or [])}"
        )
    if key == "blindspot.python_store_invisible":
        return "实现树含 Python 生产代码，Go AST 对它完全不可见"
    return ""


def bound_storages(packet: dict, producer: str, field: str) -> set[str]:
    evidence = packet.get(producer) or {} if producer else packet
    return {
        artifact.get("storage")
        for artifact in evidence.get(field) or []
        if artifact.get("storage")
    }


#: 拥有权威状态、因而可能需要事务性发布 seam 的 kind 闭集。与 Go 侧
#: `graph.deriveObjectReadiness` 中要求 `service.store` / 发布 seam 的分支同源。
STATE_OWNER_KINDS = frozenset({"aggregate_root", "process_manager"})


def domain_event_declaration_gaps(
    object_id: str,
    kind: str,
    stage: str,
    entry: dict,
) -> list[Gap]:
    """有命令的状态所有者（聚合根 / 长流程编排器）必须显式表态是否发布领域事件。

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


def evidence_class(dimension: str) -> str:
    """维度的证据层。未登记的维度按结构性处理并在主流程里 BLOCK：新维度必须显式分层，
    默认落进「不阻断」那侧会让新缺口悄悄消失。"""
    return EVIDENCE_CLASS_BY_DIMENSION.get(dimension, STRUCTURAL)


def partition_by_evidence_class(gaps: list[Gap]) -> dict[str, list[Gap]]:
    partitions: dict[str, list[Gap]] = {STRUCTURAL: [], RESULT: [], BLINDSPOT: []}
    for gap in gaps:
        partitions[evidence_class(gap.dimension)].append(gap)
    return partitions


def unclassified_dimensions(gaps: list[Gap]) -> list[str]:
    return sorted(
        {
            gap.dimension
            for gap in gaps
            if gap.dimension not in EVIDENCE_CLASS_BY_DIMENSION
        }
    )


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


def cells_from_gaps(gaps: list[Gap]) -> dict[str, dict[str, int]]:
    """缺口 → 「维度 × 对象 kind」计数格。棘轮的比对单位。"""
    counter: Counter[tuple[str, str]] = Counter(
        (gap.dimension, gap.kind) for gap in gaps
    )
    cells: dict[str, dict[str, int]] = defaultdict(dict)
    for (dimension, kind), count in counter.items():
        cells[dimension][kind] = count
    return {
        dimension: dict(sorted(kinds.items()))
        for dimension, kinds in sorted(cells.items())
    }


def write_reports(
    report_dir: Path,
    graph_path: Path,
    graph_digest: str,
    registry_path: Path,
    registry_digest: str | None,
    graph: dict,
    gaps: list[Gap],
    cells: dict[str, dict[str, int]],
    dynamic_readiness: dict | None = None,
) -> Path:
    verify_graph_digest(graph_path, graph_digest)
    verify_optional_input_digest(registry_path, registry_digest, "盲点登记册")
    report_dir.mkdir(parents=True, exist_ok=True)
    stages = Counter(
        entry.get("stage", "unknown") for entry in graph.get("objectReadiness") or []
    )
    payload = {
        REPORT_GRAPH_FIELD: {
            "path": display_path(graph_path),
            "sha256": graph_digest,
        },
        REPORT_BLIND_SPOT_REGISTRY_FIELD: _report_input_binding(
            registry_path, registry_digest
        ),
        "objects": len(graph.get("objects") or []),
        "evidencePackets": len(graph.get("readinessEvidence") or []),
        "stages": dict(sorted(stages.items())),
        "gapsByDimension": dict(
            sorted(Counter(gap.dimension for gap in gaps).items())
        ),
        "gapsByKind": dict(sorted(Counter(gap.kind for gap in gaps).items())),
        "gapsByDimensionKind": cells,
        "structuralPolicy": {
            "mode": "strict_zero",
            "allowedGapCount": 0,
        },
        "dynamicReadiness": dynamic_readiness or {
            "status": "not_evaluated",
            "commercialReady": False,
            "resultBundle": None,
            "reason": (
                "commercial evaluation was not requested; static structure never "
                "implies a trusted readiness result"
            ),
        },
        "gaps": [gap.as_dict() for gap in gaps],
    }
    report = report_dir / "object_evidence_closure.json"
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    validate_report_graph_binding(report, graph_path)
    validate_report_policy_bindings(
        report,
        registry_path,
        registry_digest,
    )
    return report


def print_gap_inventory(gaps: list[Gap]) -> None:
    by_dimension: dict[str, list[Gap]] = defaultdict(list)
    for gap in gaps:
        by_dimension[gap.dimension].append(gap)
    for dimension in sorted(by_dimension, key=lambda key: (-len(by_dimension[key]), key)):
        items = by_dimension[dimension]
        kinds = " ".join(
            f"{kind}={count}"
            for kind, count in sorted(Counter(gap.kind for gap in items).items())
        )
        print(f"  {dimension}: {len(items)} 条 [{kinds}]")


def print_result_layer(gaps: list[Gap]) -> None:
    """结果证据只报告不阻断：它要真实环境跑出来才存在，静态派生拿不到。"""
    if not gaps:
        return
    print(
        f"结果证据（不阻断）{len(gaps)} 条：需要真实环境运行才能产出，"
        "由 runner / stackctl 附加，静态派生永远拿不到"
    )
    print_gap_inventory(gaps)


def print_blind_spots(gaps: list[Gap], registry: dict[tuple[str, str], dict]) -> None:
    """维度盲点必须可见；只有 SHA-bound 证明实现存在的 scanner false-negative 可放行。"""
    if not gaps:
        return
    print(f"维度盲点（已登记 {len(registry)} 条）{len(gaps)} 条：")
    for gap in sorted(gaps, key=lambda entry: (entry.dimension, entry.object_id)):
        entry = registry.get((gap.object_id, gap.dimension)) or {}
        attested = entry.get("attested_scope", "未登记")
        classification = entry.get("classification", "未登记")
        print(f"  {gap.dimension} / {gap.object_id}: {gap.detail}")
        print(f"    classification: {classification}")
        print(f"    attested_scope: {attested}")


def print_structural_gaps(gaps: list[Gap]) -> None:
    print(
        f"GATE_BLOCK STRUCTURAL 严格零值要求未满足：{len(gaps)} 条缺口，"
        f"覆盖 {len({gap.object_id for gap in gaps})} 个对象"
    )
    print_gap_inventory(gaps)
    for gap in sorted(gaps, key=lambda entry: (entry.dimension, entry.object_id)):
        print(
            f"    - {gap.dimension} / {gap.object_id} ({gap.kind}, {gap.stage}): "
            f"{gap.detail}"
        )
    print(
        "修复路径：按对象补齐实现 seam、精确 runner/marker 与三层测试入口，"
        "或撤回引入缺口的改动。门禁不读取任何基线，"
        "禁止为结构缺口发放额度。"
    )


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


if __name__ == "__main__":
    sys.exit(main())
