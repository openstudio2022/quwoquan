"""对象证据闭合门禁的常量与维度分层表（唯一定义处）。"""
from __future__ import annotations

import re
from pathlib import Path


# 本模块位于 quwoquan_ops/gate/object_evidence_closure/ 下，比原入口深一层，
# 因此仓库根是 parents[3]（原入口为 parents[2]）。
ROOT = Path(__file__).resolve().parents[3]
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

#: 拥有权威状态、因而可能需要事务性发布 seam 的 kind 闭集。与 Go 侧
#: `graph.deriveObjectReadiness` 中要求 `service.store` / 发布 seam 的分支同源。
STATE_OWNER_KINDS = frozenset({"aggregate_root", "process_manager"})
