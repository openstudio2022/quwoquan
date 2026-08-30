"""Document scanning that discovers every governed reference for Data GC.

Owns the traversal half of the collector: how a stored document names
executions, capsules, bundles, output refs and frozen external inputs. The graph
module owns what is then done with those references. Scanning does not import the
graph, so the dependency stays one-way.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from content.execution.campaign.external_inputs import (
    PROFESSIONAL_IMAGE_ACQUISITION_KIND,
    PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    payload_digest,
)
from content.execution.campaign.external_inputs import file_digest as external_file_digest
from core.paths import RESEARCH_SCALE_PROMOTIONS_OUTPUT_REF
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)

if TYPE_CHECKING:
    from content.release.canonical.garbage_collection_reference_graph import (
        ReferenceGraph,
    )

# 每个受治理证据根及其节点 kind。引用图与墓碑回填都从这里取根，因此「哪些树算治理
# 证据」只有一处写法；两侧各自维护一份清单时，回填会漏掉图会扫的树，从而把可解析的
# 引用误判成永久缺席。
GOVERNED_EVIDENCE_OUTPUT_ROOTS: tuple[tuple[str, str], ...] = (
    (RESEARCH_SCALE_PROMOTIONS_OUTPUT_REF, "promotion_evidence"),
    # 只有四个真实环境的激活与消费回执参与可达性。`env/repo/` 是仓库本地缓存与会话
    # 产物根（AGENTS.md 已把缓存重定向到此），里面的 preflight 报告是观测而不是任何
    # 对象存活的依据；把它算进证据面会让回收器因为读到自己的测试临时目录而无法运行。
    ("env/alpha", "activation_readiness_evidence"),
    ("env/beta", "activation_readiness_evidence"),
    ("env/gamma", "activation_readiness_evidence"),
    ("env/prod", "activation_readiness_evidence"),
    (
        "data/local/workspace/content-campaign-submissions",
        "campaign_reconciliation_evidence",
    ),
    ("data/local/release-identity-recoveries", "identity_recovery_evidence"),
    (
        "data/local/workspace/release-identity-incidents",
        "identity_incident_evidence",
    ),
    ("data/local/reviewed-closure-adoptions", "adoption_evidence"),
    ("data/local/cache/protected-quarantines", "quarantine_receipt_evidence"),
    ("data/local/workspace/object-transactions", "transaction_evidence"),
)

# 治理证据树内部显式声明的非证据段。运行时包 payload 由 release 可重建，不可能是任何
# 对象存活的依据；它同时是 Flutter 资产清单这类非 object JSON 的所在，把它算进证据面
# 会让回收器在读到打包产物时直接判否。
NON_EVIDENCE_PATH_SEGMENTS = frozenset({"mutable-runtime"})


def _is_non_evidence(path: Path) -> bool:
    return not NON_EVIDENCE_PATH_SEGMENTS.isdisjoint(path.parts)

_EXECUTION_ID_KEYS = frozenset(
    {
        "executionId",
        "sourceTaskId",
        "retryOf",
        "rootExecutionId",
        "predecessorRootExecutionId",
    }
)
_EXECUTION_IDS_KEYS = frozenset(
    {
        "executionIds",
        "laneExecutionIds",
        "protectedExecutionIds",
        "upstreamExecutionIds",
        "predecessorExecutionIds",
    }
)

# Acquisition jobs reuse the executionId field but carry their own namespace
# prefix; they name a source acquisition run, never a data/tasks execution.
_ACQUISITION_ID_NAMESPACE = "acquisition:"
_CAPSULE_REF_KEYS = frozenset({"sourceCapsuleRef", "capsuleRef"})
_BUNDLE_REF_KEYS = frozenset({"executorBundleRef"})
_OUTPUT_REF_KEYS = frozenset(
    {
        "quarantineRef",
        "migrationApplyReceiptRef",
        "receiptRef",
        "provenanceRef",
        "resourceSoakEvidenceRef",
        "faultInjectionEvidenceRef",
        "campaignEvidenceRef",
        "researchIsolationVerificationRef",
    }
)

def typed_gc_error(code: str, detail: str) -> ObjectTransactionError:
    return ObjectTransactionError(f"GATE_BLOCK DATA.GC.{code}: {detail}")

def source_ref(path: Path, *, output_root: Path, publish_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(output_root.resolve()).as_posix()
    except ValueError:
        try:
            return "publish/" + resolved.relative_to(publish_root.resolve()).as_posix()
        except ValueError as exc:
            raise typed_gc_error(
                "EVIDENCE_ROOT_ESCAPE", f"evidence escapes governed roots: {path}"
            ) from exc

def known_absent_execution_ids(document: Mapping[str, Any]) -> set[str]:
    absent: set[str] = set()
    stack: list[Any] = [document.get("executionEvidence")]
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            execution_id = str(value.get("executionId") or "").strip()
            # Reconciliation receipts prove a never-materialized execution with
            # executionRootExists, while file bindings use exists. Both are
            # typed absence proofs; accepting only one leaves submission-only
            # abandonment receipts unrecognized.
            if execution_id and (
                value.get("exists") is False
                or value.get("executionRootExists") is False
            ):
                absent.add(execution_id)
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return absent


def _evidence_reason(source: str) -> str:
    if source.startswith("publish/"):
        return "canonical_publish_reference"
    if source.startswith("data/releases/"):
        return "immutable_release_reference"
    if source.startswith(f"{RESEARCH_SCALE_PROMOTIONS_OUTPUT_REF}/"):
        return "promotion_evidence"
    if source.startswith("env/"):
        return "activation_readiness_evidence"
    if "/release-identity-recoveries/" in source:
        return "release_identity_recovery"
    if "/release-identity-incidents/" in source:
        return "release_identity_incident"
    if "/reviewed-closure-adoptions/" in source:
        return "reviewed_closure_adoption"
    if "/content-campaign-submissions/" in source:
        return "campaign_submission_reconciliation"
    if "/_shared/reconciliation/" in source:
        return "execution_reconciliation_evidence"
    return "evidence_reference"


def _external_input(
    graph: ReferenceGraph,
    row: Mapping[str, Any],
    *,
    source: str,
) -> None:
    stable = {key: value for key, value in row.items() if key != "refDigest"}
    if row.get("refDigest") != payload_digest(stable):
        raise typed_gc_error("ACQUISITION_REFERENCE_INVALID", "external input refDigest drift")
    kind = str(row.get("kind") or "")
    if kind not in {
        PROFESSIONAL_IMAGE_ACQUISITION_KIND,
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    }:
        raise typed_gc_error(
            "ACQUISITION_REFERENCE_INVALID", f"unknown external input kind: {kind}"
        )
    acquisition_root = (
        graph.output_root / "data/local/workspace/source-acquisition"
    ).resolve()
    # Reachability and tamper detection are all the collector needs: the row's
    # own refDigest above, plus the per-file digests below. Re-resolving the
    # descriptor against the current manifest schema is the runtime's job of
    # rejecting substituted frozen inputs; applying it here would make the
    # collector unable to protect any evidence produced before a schema change,
    # including published objects whose manifests are digest-locked and
    # therefore cannot be migrated.
    root_ref = str(row.get("acquisitionRootRef") or ".")
    kind_root = (acquisition_root / root_ref).resolve()
    for key, artifact_kind, digest_key in (
        ("manifestRef", "acquisition_manifest", "manifestFileDigest"),
        ("receiptRef", "acquisition_receipt", "receiptFileDigest"),
    ):
        relative = _safe_rel(str(row.get(key) or ""), label=key)
        path = kind_root / relative
        if path.is_symlink() or not path.is_file():
            raise typed_gc_error("ACQUISITION_REFERENCE_MISSING", f"{key} is missing: {path}")
        if external_file_digest(path) != row.get(digest_key):
            raise typed_gc_error("ACQUISITION_REFERENCE_INVALID", f"{digest_key} drift: {path}")
        graph.artifact(
            path,
            kind=artifact_kind,
            source=source,
            relation=f"external_input_{key}",
        )
    for blob in row.get("blobRefs") or []:
        if not isinstance(blob, Mapping):
            raise typed_gc_error("ACQUISITION_REFERENCE_INVALID", "blobRef is not an object")
        relative = _safe_rel(str(blob.get("blobRef") or ""), label="blobRef")
        path = kind_root / relative
        if path.is_symlink() or not path.is_file():
            raise typed_gc_error("ACQUISITION_REFERENCE_MISSING", f"blob is missing: {path}")
        if external_file_digest(path) != blob.get("contentSha256"):
            raise typed_gc_error("ACQUISITION_REFERENCE_INVALID", f"blob digest drift: {path}")
        graph.artifact(
            path,
            kind="acquisition_cas",
            source=source,
            relation="external_input_blob",
        )


def scan_value(
    graph: ReferenceGraph,
    value: Any,
    *,
    source: str,
    known_absent: set[str],
) -> None:
    if isinstance(value, Mapping):
        if value.get("schema") == "quwoquan_data.campaign_external_input_ref":
            _external_input(graph, value, source=source)
        for key, child in value.items():
            if (
                key in _EXECUTION_ID_KEYS
                and isinstance(child, str)
                and child.strip()
                and not child.startswith(_ACQUISITION_ID_NAMESPACE)
            ):
                relation = (
                    "retry_ancestor" if key == "retryOf" else _evidence_reason(source)
                )
                graph.execution(
                    child,
                    source=source,
                    relation=relation,
                    known_absent=child in known_absent,
                )
            elif key in _EXECUTION_IDS_KEYS and isinstance(child, list):
                for execution_id in child:
                    if not isinstance(execution_id, str) or not execution_id.strip():
                        raise typed_gc_error(
                            "REFERENCE_INVALID",
                            f"{key} contains an invalid executionId",
                        )
                    graph.execution(
                        execution_id,
                        source=source,
                        relation=_evidence_reason(source),
                        known_absent=execution_id in known_absent,
                    )
            elif key in _CAPSULE_REF_KEYS and isinstance(child, str) and child.strip():
                graph.output_reference(
                    child,
                    source=source,
                    relation="source_capsule_reference",
                    kind="source_capsule",
                )
            elif key in _BUNDLE_REF_KEYS and isinstance(child, str) and child.strip():
                graph.output_reference(
                    child,
                    source=source,
                    relation="executor_bundle_reference",
                    kind="executor_bundle",
                )
            elif (key in _OUTPUT_REF_KEYS or key.endswith("Ref")) and isinstance(
                child, str
            ):
                text = child.strip()
                if text.startswith(("data/", "env/", "local/")):
                    graph.output_reference(
                        text,
                        source=source,
                        relation=f"output_{key}",
                        kind=(
                            "protected_quarantine"
                            if key == "quarantineRef"
                            else "evidence"
                        ),
                    )
            scan_value(
                graph,
                child,
                source=source,
                known_absent=known_absent,
            )
    elif isinstance(value, list):
        for child in value:
            scan_value(
                graph,
                child,
                source=source,
                known_absent=known_absent,
            )


def scan_json_file(graph: ReferenceGraph, path: Path, *, kind: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise typed_gc_error("EVIDENCE_INVALID", f"JSON evidence is not a regular file: {path}")
    source = source_ref(
        path,
        output_root=graph.output_root,
        publish_root=graph.publish_root,
    )
    graph.node(source, kind)
    document = _read_json(path)
    known_absent = known_absent_execution_ids(document)
    scan_value(graph, document, source=source, known_absent=known_absent)


def scan_tree(graph: ReferenceGraph, root: Path, *, kind: str) -> None:
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise typed_gc_error("EVIDENCE_INVALID", f"evidence root is invalid: {root}")
    for path in sorted(root.rglob("*.json")):
        if _is_non_evidence(path):
            continue
        scan_json_file(graph, path, kind=kind)


def collect_absent_execution_proofs(output_root: Path) -> set[str]:
    """Read every campaign reconciliation receipt for typed absence proofs."""
    proofs: set[str] = set()
    root = output_root / "data/local/workspace/content-campaign-submissions"
    if not root.is_dir() or root.is_symlink():
        return proofs
    for receipt in sorted(root.glob("*/reconciliation/*.json")):
        if receipt.is_symlink() or not receipt.is_file():
            continue
        document = _read_json(receipt)
        if isinstance(document, Mapping):
            proofs |= known_absent_execution_ids(document)
    return proofs

def _reference_sites(
    value: Any,
    *,
    source: str,
    sites: dict[str, set[tuple[str, str]]],
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (
                key in _EXECUTION_ID_KEYS
                and isinstance(child, str)
                and child.strip()
                and not child.startswith(_ACQUISITION_ID_NAMESPACE)
            ):
                relation = (
                    "retry_ancestor" if key == "retryOf" else _evidence_reason(source)
                )
                sites.setdefault(child.strip(), set()).add((source, relation))
            elif key in _EXECUTION_IDS_KEYS and isinstance(child, list):
                for execution_id in child:
                    if isinstance(execution_id, str) and execution_id.strip():
                        sites.setdefault(execution_id.strip(), set()).add(
                            (source, _evidence_reason(source))
                        )
            _reference_sites(child, source=source, sites=sites)
    elif isinstance(value, list):
        for child in value:
            _reference_sites(child, source=source, sites=sites)


def collect_execution_reference_sites(
    *,
    output_root: Path,
    publish_root: Path,
    release_root: Path,
) -> dict[str, set[tuple[str, str]]]:
    """Report which governed documents name each execution, without judging it.

    Deliberately does not fail on an unresolvable id: this is the read the
    tombstone backfill needs precisely because `build_reference_graph` cannot get
    that far — it fails closed on the very references the backfill exists to give
    a terminal state.
    """

    sites: dict[str, set[tuple[str, str]]] = {}
    roots = [publish_root, release_root]
    roots.extend(output_root / relative for relative, _kind in GOVERNED_EVIDENCE_OUTPUT_ROOTS)
    roots.append(output_root / "data/tasks")
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for path in sorted(root.rglob("*.json")):
            if path.is_symlink() or not path.is_file() or _is_non_evidence(path):
                continue
            source = source_ref(
                path,
                output_root=output_root,
                publish_root=publish_root,
            )
            _reference_sites(_read_json(path), source=source, sites=sites)
    return sites


__all__ = [
    "GOVERNED_EVIDENCE_OUTPUT_ROOTS",
    "NON_EVIDENCE_PATH_SEGMENTS",
    "collect_absent_execution_proofs",
    "collect_execution_reference_sites",
    "known_absent_execution_ids",
    "scan_json_file",
    "scan_tree",
    "scan_value",
    "source_ref",
    "typed_gc_error",
]
