"""Linear, fail-closed reference graph for canonical Data GC."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content.execution.campaign.external_inputs import (
    PROFESSIONAL_IMAGE_ACQUISITION_KIND,
    PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    payload_digest,
    verify_external_input_refs,
)
from content.execution.campaign.external_inputs import (
    file_digest as external_file_digest,
)
from content.release.canonical.garbage_collection_contract import (
    GC_REFERENCE_GRAPH_SCHEMA,
    file_digest,
    validate_reference_graph,
)
from content.release.canonical.garbage_collection_inventory import (
    protect_quarantine_evidence,
    protect_reconciliation_evidence,
    register_acquisition_inventory,
    register_capsule_inventory,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)
from core.paths import RESEARCH_SCALE_PROMOTIONS_OUTPUT_REF
from core.schema import assert_valid

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


def _typed(code: str, detail: str) -> ObjectTransactionError:
    return ObjectTransactionError(f"GATE_BLOCK DATA.GC.{code}: {detail}")


def _safe_output_ref(output_root: Path, raw: object, *, label: str) -> tuple[str, Path]:
    text = str(raw or "").strip()
    if text.startswith("local/"):
        text = f"data/{text}"
    relative = _safe_rel(text, label=label)
    path = (output_root / relative).resolve()
    resolved_output = output_root.resolve()
    if path == resolved_output or resolved_output not in path.parents:
        raise _typed("REFERENCE_PATH_ESCAPE", f"{label} escapes output root: {raw}")
    if path.is_symlink() or not path.exists():
        raise _typed("REFERENCE_MISSING", f"{label} is missing or a symlink: {text}")
    return relative.as_posix(), path


def _source_ref(path: Path, *, output_root: Path, publish_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(output_root.resolve()).as_posix()
    except ValueError:
        try:
            return "publish/" + resolved.relative_to(publish_root.resolve()).as_posix()
        except ValueError as exc:
            raise _typed(
                "EVIDENCE_ROOT_ESCAPE", f"evidence escapes governed roots: {path}"
            ) from exc


def _capsule_tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".qwq_campaign_capsule.json":
            continue
        if path.is_symlink():
            row = f"L\0{relative}\0{os.readlink(path)}\n"
        elif path.is_file():
            executable = path.stat().st_mode & 0o111
            row = (
                f"F\0{relative}\0{executable:o}\0"
                f"{file_digest(path).removeprefix('sha256:')}\n"
            )
        else:
            continue
        digest.update(row.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


@dataclass(slots=True)
class ReferenceGraph:
    output_root: Path
    publish_root: Path
    tasks: dict[str, Path]
    nodes: dict[str, str] = field(default_factory=dict)
    edges: set[tuple[str, str, str]] = field(default_factory=set)
    protected_execution_reasons: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    protected_artifact_reasons: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    artifacts: dict[str, tuple[Path, str]] = field(default_factory=dict)
    _validated_capsules: set[str] = field(default_factory=set)

    def node(self, ref: str, kind: str) -> None:
        current = self.nodes.get(ref)
        if current is not None and current != kind:
            raise _typed(
                "REFERENCE_KIND_DRIFT",
                f"{ref} is both {current} and {kind}",
            )
        self.nodes[ref] = kind

    def edge(self, source: str, target: str, relation: str) -> None:
        self.edges.add((source, target, relation))

    def artifact(
        self,
        path: Path,
        *,
        kind: str,
        source: str | None = None,
        relation: str | None = None,
        protect_reason: str | None = None,
    ) -> str:
        ref = path.resolve().relative_to(self.output_root.resolve()).as_posix()
        current_node_kind = self.nodes.get(ref)
        if kind == "evidence" and current_node_kind is not None:
            kind = current_node_kind
        elif current_node_kind == "evidence" and kind.endswith("_evidence"):
            self.nodes[ref] = kind
        self.node(ref, kind)
        current = self.artifacts.get(ref)
        if current is not None and current[1] != kind:
            if current[1] == "evidence" and kind.endswith("_evidence"):
                current = (current[0], kind)
            elif kind == "evidence":
                kind = current[1]
            else:
                raise _typed("REFERENCE_KIND_DRIFT", f"artifact kind drift: {ref}")
        self.artifacts[ref] = (path.resolve(), kind)
        if source is not None and relation is not None:
            self.edge(source, ref, relation)
            self.protected_artifact_reasons[ref].add(protect_reason or relation)
        return ref

    def execution(
        self,
        execution_id: str,
        *,
        source: str,
        relation: str,
        known_absent: bool = False,
    ) -> None:
        text = str(execution_id or "").strip()
        if not text:
            raise _typed("REFERENCE_INVALID", "execution reference is empty")
        target = f"data/tasks/{text}"
        self.node(target, "execution" if text in self.tasks else "absent_execution")
        self.edge(source, target, relation)
        if text not in self.tasks:
            if not known_absent:
                raise _typed(
                    "REFERENCE_MISSING",
                    f"execution reference has no task or typed absence proof: {text}",
                )
            return
        task_ref = f"data/tasks/{text}"
        if source == task_ref or source.startswith(task_ref + "/"):
            return
        if source.startswith("data/local/workspace/object-transactions/"):
            # Transaction evidence is collected with, or after, its execution;
            # it is not an independent root that keeps that execution alive.
            return
        self.protected_execution_reasons[text].add(relation)

    def output_reference(
        self,
        raw: object,
        *,
        source: str,
        relation: str,
        kind: str,
    ) -> None:
        ref, path = _safe_output_ref(
            self.output_root,
            raw,
            label=f"{relation} reference",
        )
        if ref == source:
            # A frozen evidence document commonly records its own canonical ref.
            # The source node already proves that path and a self-edge cannot
            # make any otherwise-unreferenced artifact reachable.
            return
        if ref.startswith("data/local/workspace/source-acquisition/"):
            parts = Path(ref).parts
            if "cas" in parts:
                kind = "acquisition_cas"
            elif "receipts" in parts:
                kind = "acquisition_receipt"
            elif "manifests" in parts:
                kind = "acquisition_manifest"
            else:
                kind = "acquisition_evidence"
        if kind == "source_capsule":
            self.validate_capsule(ref, path)
        self.artifact(
            path,
            kind=kind,
            source=source,
            relation=relation,
        )
        parts = Path(ref).parts
        if len(parts) >= 3 and parts[:2] == ("data", "tasks"):
            self.protected_execution_reasons[parts[2]].add(relation)

    def validate_capsule(self, ref: str, path: Path) -> None:
        if ref in self._validated_capsules:
            return
        if not path.is_dir() or path.is_symlink():
            raise _typed(
                "CAPSULE_INVALID", f"capsule is not a regular directory: {ref}"
            )
        manifest_path = path / ".qwq_campaign_capsule.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise _typed("CAPSULE_INVALID", f"capsule manifest is missing: {ref}")
        manifest = _read_json(manifest_path)
        try:
            assert_valid(
                manifest,
                "execution",
                "content_source_capsule",
                label=f"GC source capsule:{ref}",
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise _typed("CAPSULE_INVALID", str(exc)) from exc
        digest = str(manifest.get("capsuleDigest") or "")
        identity = {
            key: value
            for key, value in manifest.items()
            if key not in {"capsuleDigest", "treeDigest"}
        }
        if payload_digest(identity) != digest:
            raise _typed("CAPSULE_INVALID", f"capsule identity digest drift: {ref}")
        if path.name != digest.removeprefix("sha256:"):
            raise _typed("CAPSULE_INVALID", f"capsule path identity drift: {ref}")
        if manifest.get("treeDigest") != _capsule_tree_digest(path):
            raise _typed("CAPSULE_INVALID", f"capsule tree digest drift: {ref}")
        self._validated_capsules.add(ref)

    def document(self) -> dict[str, Any]:
        protected = [
            {
                "ref": ref,
                "kind": self.nodes[ref],
                "reasons": sorted(reasons),
            }
            for ref, reasons in sorted(self.protected_artifact_reasons.items())
            if reasons
        ]
        nodes = [{"ref": ref, "kind": kind} for ref, kind in sorted(self.nodes.items())]
        edges = [
            {"fromRef": source, "toRef": target, "relation": relation}
            for source, target, relation in sorted(self.edges)
        ]
        result = {
            "schema": GC_REFERENCE_GRAPH_SCHEMA,
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "nodes": nodes,
            "edges": edges,
            "protectedArtifactRefs": protected,
            "unresolvedReferenceCount": 0,
            "unresolvedReferences": [],
        }
        validate_reference_graph(result)
        return result


def _known_absent_execution_ids(document: Mapping[str, Any]) -> set[str]:
    absent: set[str] = set()
    stack: list[Any] = [document.get("executionEvidence")]
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            execution_id = str(value.get("executionId") or "").strip()
            if execution_id and value.get("exists") is False:
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
        raise _typed("ACQUISITION_REFERENCE_INVALID", "external input refDigest drift")
    kind = str(row.get("kind") or "")
    if kind not in {
        PROFESSIONAL_IMAGE_ACQUISITION_KIND,
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    }:
        raise _typed(
            "ACQUISITION_REFERENCE_INVALID", f"unknown external input kind: {kind}"
        )
    acquisition_root = (
        graph.output_root / "data/local/workspace/source-acquisition"
    ).resolve()
    try:
        verify_external_input_refs(
            str(row.get("carrier") or ""),
            [row],
            acquisition_root=acquisition_root,
            source_revision=str(row.get("sourceRevision") or ""),
            source_digest=str(row.get("sourceDigest") or ""),
            entity_catalog_digest=str(row.get("entityCatalogDigest") or ""),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise _typed("ACQUISITION_REFERENCE_INVALID", str(exc)) from exc
    root_ref = str(row.get("acquisitionRootRef") or ".")
    kind_root = (acquisition_root / root_ref).resolve()
    for key, artifact_kind, digest_key in (
        ("manifestRef", "acquisition_manifest", "manifestFileDigest"),
        ("receiptRef", "acquisition_receipt", "receiptFileDigest"),
    ):
        relative = _safe_rel(str(row.get(key) or ""), label=key)
        path = kind_root / relative
        if path.is_symlink() or not path.is_file():
            raise _typed("ACQUISITION_REFERENCE_MISSING", f"{key} is missing: {path}")
        if external_file_digest(path) != row.get(digest_key):
            raise _typed("ACQUISITION_REFERENCE_INVALID", f"{digest_key} drift: {path}")
        graph.artifact(
            path,
            kind=artifact_kind,
            source=source,
            relation=f"external_input_{key}",
        )
    for blob in row.get("blobRefs") or []:
        if not isinstance(blob, Mapping):
            raise _typed("ACQUISITION_REFERENCE_INVALID", "blobRef is not an object")
        relative = _safe_rel(str(blob.get("blobRef") or ""), label="blobRef")
        path = kind_root / relative
        if path.is_symlink() or not path.is_file():
            raise _typed("ACQUISITION_REFERENCE_MISSING", f"blob is missing: {path}")
        if external_file_digest(path) != blob.get("contentSha256"):
            raise _typed("ACQUISITION_REFERENCE_INVALID", f"blob digest drift: {path}")
        graph.artifact(
            path,
            kind="acquisition_cas",
            source=source,
            relation="external_input_blob",
        )


def _scan_value(
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
            if key in _EXECUTION_ID_KEYS and isinstance(child, str) and child.strip():
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
                        raise _typed(
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
            _scan_value(
                graph,
                child,
                source=source,
                known_absent=known_absent,
            )
    elif isinstance(value, list):
        for child in value:
            _scan_value(
                graph,
                child,
                source=source,
                known_absent=known_absent,
            )


def _scan_json_file(graph: ReferenceGraph, path: Path, *, kind: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise _typed("EVIDENCE_INVALID", f"JSON evidence is not a regular file: {path}")
    source = _source_ref(
        path,
        output_root=graph.output_root,
        publish_root=graph.publish_root,
    )
    graph.node(source, kind)
    document = _read_json(path)
    known_absent = _known_absent_execution_ids(document)
    _scan_value(graph, document, source=source, known_absent=known_absent)


def _scan_tree(graph: ReferenceGraph, root: Path, *, kind: str) -> None:
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise _typed("EVIDENCE_INVALID", f"evidence root is invalid: {root}")
    for path in sorted(root.rglob("*.json")):
        _scan_json_file(graph, path, kind=kind)


def build_reference_graph(
    *,
    output_root: Path,
    publish_root: Path,
    release_root: Path,
    tasks: dict[str, Path],
) -> ReferenceGraph:
    """Scan every governed evidence root exactly once and fail on broken refs."""

    graph = ReferenceGraph(
        output_root=output_root.resolve(),
        publish_root=publish_root.resolve(),
        tasks=tasks,
    )
    for execution_id, root in tasks.items():
        graph.artifact(root, kind="execution")
        _scan_tree(graph, root, kind="execution_evidence")
        graph.node(f"data/tasks/{execution_id}", "execution")
    _scan_tree(graph, publish_root, kind="canonical_publish_evidence")
    _scan_tree(graph, release_root, kind="immutable_release_evidence")
    for relative, kind in (
        (RESEARCH_SCALE_PROMOTIONS_OUTPUT_REF, "promotion_evidence"),
        ("env", "activation_readiness_evidence"),
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
    ):
        _scan_tree(graph, output_root / relative, kind=kind)
    register_acquisition_inventory(graph, scan_value=_scan_value)
    register_capsule_inventory(graph)
    protect_reconciliation_evidence(graph)
    protect_quarantine_evidence(graph)
    graph.document()
    return graph


__all__ = ["ReferenceGraph", "build_reference_graph"]
