"""Discover GC-managed capsules, acquisition artifacts, and protected evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from content.execution.execution_supersession import (
    load_execution_supersession_receipt,
)
from content.release.canonical.garbage_collection_contract import file_digest
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)
from content.source.professional_image_acquisition import (
    load_professional_image_acquisition_receipt,
)
from content.source.professional_video_receipt import (
    load_professional_video_acquisition_receipt,
)
from core.schema import assert_valid
from governance.protected_quarantine_evidence import (
    load_protected_quarantine_receipts,
)

if TYPE_CHECKING:
    from content.release.canonical.garbage_collection_reference_graph import (
        ReferenceGraph,
    )


def _typed(code: str, detail: str) -> ObjectTransactionError:
    return ObjectTransactionError(f"GATE_BLOCK DATA.GC.{code}: {detail}")


def _source_ref(path: Path, *, output_root: Path, publish_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(output_root.resolve()).as_posix()
    except ValueError:
        try:
            return "publish/" + resolved.relative_to(publish_root.resolve()).as_posix()
        except ValueError as exc:
            raise _typed(
                "EVIDENCE_ROOT_ESCAPE",
                f"evidence escapes governed roots: {path}",
            ) from exc


def register_acquisition_inventory(
    graph: ReferenceGraph,
    *,
    scan_value: Callable[..., None],
) -> None:
    root = graph.output_root / "data/local/workspace/source-acquisition"
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise _typed(
            "ACQUISITION_ROOT_INVALID",
            f"acquisition root is invalid: {root}",
        )
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise _typed(
                "ACQUISITION_ROOT_INVALID",
                f"acquisition symlink is forbidden: {path}",
            )
        relative = path.relative_to(root)
        staging_ancestor = next(
            (
                part
                for part in relative.parts
                if part.startswith(("professional-image-", "professional-video-"))
            ),
            None,
        )
        if staging_ancestor is not None and path.name != staging_ancestor:
            continue
        if path.is_dir():
            if path.name.startswith(("professional-image-", "professional-video-")):
                graph.artifact(path, kind="acquisition_staging")
            continue
        parts = relative.parts
        if path.suffix == ".json":
            document = _read_json(path)
            schema = str(document.get("schema") or "")
            if "receipts" in parts:
                kind = "acquisition_receipt"
                receipt_root = root / "video" if parts[0] == "video" else root
                try:
                    # The collector reads receipts long after acquisition, so a
                    # unit whose bodies were all reclaimed is a normal input
                    # rather than a defect. A partly reclaimed unit still fails.
                    if parts[0] == "video":
                        document = load_professional_video_acquisition_receipt(
                            path.relative_to(root / "video").as_posix(),
                            root=root / "video",
                            require_bodies=False,
                        )
                    else:
                        document = load_professional_image_acquisition_receipt(
                            path.relative_to(root).as_posix(),
                            root=root,
                            require_bodies=False,
                        )
                except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
                    raise _typed("ACQUISITION_RECEIPT_INVALID", str(exc)) from exc
            elif "manifests" in parts:
                kind = "acquisition_manifest"
                schema_name = (
                    "professional_video_acquisition_manifest"
                    if schema == "quwoquan_data.professional_video_acquisition_manifest"
                    else "professional_image_acquisition_manifest"
                )
                try:
                    assert_valid(
                        document,
                        "source",
                        schema_name,
                        label=f"GC acquisition manifest:{path}",
                    )
                except (FileNotFoundError, TypeError, ValueError) as exc:
                    raise _typed("ACQUISITION_MANIFEST_INVALID", str(exc)) from exc
            else:
                kind = "acquisition_evidence"
            source = graph.artifact(path, kind=kind)
            if kind == "acquisition_receipt":
                for asset in document.get("assets") or []:
                    if not isinstance(asset, Mapping):
                        raise _typed(
                            "ACQUISITION_RECEIPT_INVALID",
                            f"asset row is invalid: {path}",
                        )
                    asset_ref = str(asset.get("assetRef") or "").strip()
                    if not asset_ref:
                        continue
                    blob = receipt_root / _safe_rel(
                        asset_ref,
                        label="acquisition receipt assetRef",
                    )
                    if blob.is_symlink():
                        raise _typed(
                            "ACQUISITION_REFERENCE_MISSING",
                            f"receipt CAS blob is a symlink: {blob}",
                        )
                    if not blob.is_file():
                        # The receipt above already validated as a tombstone, so
                        # the body is reclaimed rather than lost. Recording the
                        # absence as a node keeps the receipt's claim visible in
                        # the graph without resurrecting a byte the collector
                        # deliberately released.
                        blob_ref = _source_ref(
                            blob,
                            output_root=graph.output_root,
                            publish_root=graph.publish_root,
                        )
                        graph.node(blob_ref, "absent_acquisition_body")
                        graph.edge(source, blob_ref, "acquisition_receipt_blob")
                        continue
                    graph.artifact(
                        blob,
                        kind="acquisition_cas",
                        source=source,
                        relation="acquisition_receipt_blob",
                    )
                discovery_ref = str(document.get("discoveryPlanRef") or "").strip()
                if discovery_ref:
                    discovery = receipt_root / _safe_rel(
                        discovery_ref,
                        label="acquisition receipt discoveryPlanRef",
                    )
                    if discovery.is_symlink() or not discovery.is_file():
                        raise _typed(
                            "ACQUISITION_REFERENCE_MISSING",
                            f"receipt discovery plan is missing: {discovery}",
                        )
                    graph.artifact(
                        discovery,
                        kind="acquisition_evidence",
                        source=source,
                        relation="acquisition_receipt_discovery_plan",
                    )
            scan_value(graph, document, source=source, known_absent=set())
            continue
        if "cas" in parts:
            digest = path.stem
            if len(digest) != 64 or file_digest(path) != f"sha256:{digest}":
                raise _typed("ACQUISITION_CAS_INVALID", f"CAS digest drift: {path}")
            graph.artifact(path, kind="acquisition_cas")


def register_capsule_inventory(graph: ReferenceGraph) -> None:
    root = (
        graph.output_root
        / "data/local/cache/content-campaign-workspaces/content-addressed-capsules"
    )
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise _typed("CAPSULE_INVALID", f"capsule root is invalid: {root}")
    for path in sorted(root.iterdir()):
        if path.name.startswith(".") and path.name.endswith(".lock"):
            continue
        if path.is_symlink() or not path.is_dir():
            raise _typed("CAPSULE_INVALID", f"unknown capsule entry: {path}")
        ref = path.relative_to(graph.output_root).as_posix()
        graph.validate_capsule(ref, path)
        graph.artifact(path, kind="source_capsule")


def protect_reconciliation_evidence(graph: ReferenceGraph) -> None:
    for execution_id, root in graph.tasks.items():
        reconciliation_root = root / "_shared/reconciliation"
        if reconciliation_root.exists() and (
            reconciliation_root.is_symlink() or not reconciliation_root.is_dir()
        ):
            raise _typed(
                "RECONCILIATION_EVIDENCE_INVALID",
                f"reconciliation root is invalid: {reconciliation_root}",
            )
        reconciliation_receipts = (
            sorted(reconciliation_root.glob("*.json"))
            if reconciliation_root.is_dir()
            else []
        )
        if reconciliation_receipts:
            graph.protected_execution_reasons[execution_id].add(
                "execution_reconciliation_evidence"
            )
        try:
            receipt = load_execution_supersession_receipt(root)
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise _typed("SUPERSESSION_EVIDENCE_INVALID", str(exc)) from exc
        if receipt is None:
            continue
        _document, path = receipt
        source = _source_ref(
            path,
            output_root=graph.output_root,
            publish_root=graph.publish_root,
        )
        graph.node(source, "supersession_evidence")
        graph.protected_execution_reasons[execution_id].add("supersession_evidence")


def protect_quarantine_evidence(graph: ReferenceGraph) -> None:
    protected, issues = load_protected_quarantine_receipts(
        data_output_root=graph.output_root / "data"
    )
    if issues:
        raise _typed("QUARANTINE_EVIDENCE_INVALID", "; ".join(issues))
    for path in sorted(protected):
        graph.artifact(path, kind="protected_quarantine")
        ref = path.relative_to(graph.output_root).as_posix()
        graph.protected_artifact_reasons[ref].add("protected_quarantine_evidence")


__all__ = [
    "protect_quarantine_evidence",
    "protect_reconciliation_evidence",
    "register_acquisition_inventory",
    "register_capsule_inventory",
]
