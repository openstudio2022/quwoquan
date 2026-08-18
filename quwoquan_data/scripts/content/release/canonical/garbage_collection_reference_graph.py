"""Linear, fail-closed reference graph for canonical Data GC."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.campaign.capsule_seal import capsule_tree_digest
from content.execution.campaign.external_inputs import payload_digest
from content.release.canonical.garbage_collection_contract import (
    GC_REFERENCE_GRAPH_SCHEMA,
    validate_reference_graph,
)
from content.release.canonical.garbage_collection_inventory import (
    protect_quarantine_evidence,
    protect_reconciliation_evidence,
    register_acquisition_inventory,
    register_capsule_inventory,
)
from content.release.canonical.garbage_collection_reference_scan import (
    collect_absent_execution_proofs as _collect_absent_execution_proofs,
    scan_tree as _scan_tree,
    scan_value as _scan_value,
    typed_gc_error as _typed,
)
from content.release.canonical.media_retention_policy import (
    MediaRetentionDecision,
    MediaRetentionPolicy,
    reclaimable_library_entries,
)
from content.release.canonical.object_transaction_contract import _read_json, _safe_rel
from core.content_library import MEDIA_KIND, library_cas_path
from core.paths import RESEARCH_SCALE_PROMOTIONS_OUTPUT_REF
from core.release_layout import MEDIA_DIR, release_holdings
from core.schema import assert_valid

_RECLAIMABLE_CACHE_ROOT = "data/local/cache/"
_ACQUISITION_ROOT = "data/local/workspace/source-acquisition/"
# Acquisition splits into two populations with opposite retention rules, along
# the same line the inventory already reads: a document records what was fetched
# under which rights and cannot be rebuilt, while a fetched body is a staging
# copy of bytes the content library owns once an object adopts them. Retaining
# both under one rule is what made acquisition grow without bound.
_ACQUISITION_RETAINED_SUFFIX = ".json"


def _is_reclaimable_ref(ref: str) -> bool:
    """Report whether a dangling reference is a normal post-collection state."""

    if ref.startswith(_RECLAIMABLE_CACHE_ROOT):
        return True
    if not ref.startswith(_ACQUISITION_ROOT):
        return False
    return not ref.endswith(_ACQUISITION_RETAINED_SUFFIX)




def _safe_output_ref(output_root: Path, raw: object, *, label: str) -> tuple[str, Path | None]:
    text = str(raw or "").strip()
    if text.startswith("local/"):
        text = f"data/{text}"
    relative = _safe_rel(text, label=label)
    path = (output_root / relative).resolve()
    resolved_output = output_root.resolve()
    if path == resolved_output or resolved_output not in path.parents:
        raise _typed("REFERENCE_PATH_ESCAPE", f"{label} escapes output root: {raw}")
    if path.is_symlink():
        raise _typed("REFERENCE_MISSING", f"{label} is missing or a symlink: {text}")
    ref = relative.as_posix()
    if not path.exists():
        # Everything under a reclaimable root is a rebuildable derivative:
        # source capsules, observer binaries, campaign workspaces, and the
        # acquisition bodies whose bytes the content library now owns. Evidence
        # that carries publish_ref is retained indefinitely while its derived
        # entries are reclaimed, so a dangling reference to one is a normal
        # terminal state. Treating it as fatal would make the collector unable
        # to run precisely because earlier collection succeeded.
        if not _is_reclaimable_ref(ref):
            raise _typed("REFERENCE_MISSING", f"{label} is missing or a symlink: {text}")
        return ref, None
    return ref, path



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
    # Reconciliation receipts prove which executions never materialized. That is
    # a global fact about the pipeline, not a property of whichever document
    # happens to mention the id, so it is collected once and shared.
    absent_execution_proofs: set[str] = field(default_factory=set)
    # Media bodies are owned once by the content library, so reachability of a
    # body is a property of its digest rather than of any one path that
    # references it. Retention reads this to decide per body, never per path.
    library_holdings: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    _validated_capsules: set[str] = field(default_factory=set)

    def node(self, ref: str, kind: str) -> None:
        current = self.nodes.get(ref)
        if current is not None and current != kind:
            # "evidence" is the generic kind that any specific *_evidence kind
            # refines. Which one is observed first depends on scan order, so
            # both directions must converge on the specific kind instead of
            # being reported as drift.
            if current == "evidence" and kind.endswith("_evidence"):
                pass
            elif kind == "evidence" and current.endswith("_evidence"):
                kind = current
            else:
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
            if not known_absent and text not in self.absent_execution_proofs:
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
        if path is None:
            self.node(ref, "absent_cache_artifact")
            self.edge(source, ref, relation)
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
        if manifest.get("treeDigest") != capsule_tree_digest(path):
            raise _typed("CAPSULE_INVALID", f"capsule tree digest drift: {ref}")
        self._validated_capsules.add(ref)

    def hold_library_entry(self, digest: str, *, ref: str) -> None:
        """Record that ``ref`` reaches one library body, addressed by digest."""
        text = str(digest or "").strip()
        if not text:
            raise _typed("REFERENCE_INVALID", f"library holding has no digest: {ref}")
        self.library_holdings[text].add(ref)

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



def _register_release_holdings(graph: ReferenceGraph, release_root: Path) -> None:
    """Bind every immutable release to the library bodies it holds.

    A release is the proof that a body is ingested, so this is also what makes an
    acquisition original eligible for tiered reclaim: until some release holds
    the digest, the acquisition workspace is still the only thing that has it.
    """
    if not release_root.is_dir() or release_root.is_symlink():
        return
    for release in sorted(release_root.iterdir()):
        if release.is_symlink() or not release.is_dir():
            continue
        for relative, digest, _size in release_holdings(release):
            graph.hold_library_entry(
                digest,
                ref=f"{release.name}/{MEDIA_DIR}/{relative}",
            )


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
    graph.absent_execution_proofs.update(
        _collect_absent_execution_proofs(output_root.resolve())
    )
    for execution_id, root in tasks.items():
        graph.artifact(root, kind="execution")
        _scan_tree(graph, root, kind="execution_evidence")
        graph.node(f"data/tasks/{execution_id}", "execution")
    _scan_tree(graph, publish_root, kind="canonical_publish_evidence")
    _scan_tree(graph, release_root, kind="immutable_release_evidence")
    _register_release_holdings(graph, release_root)
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


def reclaimable_media_entries(
    graph: ReferenceGraph,
    *,
    now: datetime,
    policy: MediaRetentionPolicy | None = None,
) -> tuple[MediaRetentionDecision, ...]:
    """Return the library bodies the collector may reclaim under tiered retention.

    Deliberately a query over the finished graph rather than a field of the GC
    plan: the plan is the immutable record of what the collector decided about
    executions, while retention is re-evaluated against the clock on every run and
    would otherwise freeze a time-dependent answer into an immutable document.

    Entry mtime is the ingestion instant because a library entry is written once
    and then read-only, so its mtime cannot drift away from admission.
    """
    ingested_at: dict[str, datetime] = {}
    for digest in graph.library_holdings:
        entry = library_cas_path(MEDIA_KIND, digest)
        if not entry.is_file():
            continue
        ingested_at[digest] = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
    return reclaimable_library_entries(
        references_by_digest=graph.library_holdings,
        ingested_at_by_digest=ingested_at,
        now=now,
        policy=policy,
    )


__all__ = ["ReferenceGraph", "build_reference_graph", "reclaimable_media_entries"]
