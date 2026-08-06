"""Canonical GC document and create-once storage contract."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.schema import assert_valid

GC_PLAN_SCHEMA = "quwoquan_data.canonical_gc_plan"
GC_APPLY_SCHEMA = "quwoquan_data.canonical_gc_apply"
GC_REFERENCE_GRAPH_SCHEMA = "quwoquan_data.canonical_gc_reference_graph"

GC_CANDIDATE_KINDS = frozenset(
    {
        "execution",
        "object_transaction",
        "transaction_staging",
        "source_capsule",
        "executor_bundle",
        "acquisition_receipt",
        "acquisition_manifest",
        "acquisition_cas",
        "acquisition_evidence",
        "acquisition_staging",
    }
)


def json_digest(value: Mapping[str, Any], *, excluded: str) -> str:
    payload = dict(value)
    payload.pop(excluded, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def write_create_once_json(path: Path, value: Mapping[str, Any]) -> bool:
    """Publish a fully-fsynced JSON inode without ever replacing the target."""

    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def validate_reference_graph(document: Mapping[str, Any]) -> None:
    try:
        assert_valid(
            dict(document),
            "governance",
            "canonical_gc_reference_graph",
            label="canonical GC reference graph",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"GATE_BLOCK DATA.GC.REFERENCE_GRAPH_INVALID: {exc}"
        ) from exc
    nodes = document.get("nodes")
    edges = document.get("edges")
    protected = document.get("protectedArtifactRefs")
    if (
        not isinstance(nodes, list)
        or not isinstance(edges, list)
        or not isinstance(protected, list)
    ):
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.GC.REFERENCE_GRAPH_INVALID: graph arrays are invalid"
        )
    node_refs = [str(row.get("ref") or "") for row in nodes if isinstance(row, Mapping)]
    if len(node_refs) != len(nodes) or len(node_refs) != len(set(node_refs)):
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.GC.REFERENCE_GRAPH_INVALID: duplicate graph node"
        )
    known = set(node_refs)
    edge_keys: set[tuple[str, str, str]] = set()
    for row in edges:
        if not isinstance(row, Mapping):
            raise ObjectTransactionError(
                "GATE_BLOCK DATA.GC.REFERENCE_GRAPH_INVALID: edge is not an object"
            )
        key = (
            str(row.get("fromRef") or ""),
            str(row.get("toRef") or ""),
            str(row.get("relation") or ""),
        )
        if key in edge_keys or key[0] not in known or key[1] not in known:
            raise ObjectTransactionError(
                "GATE_BLOCK DATA.GC.REFERENCE_GRAPH_INVALID: graph edge is invalid"
            )
        edge_keys.add(key)
    if (
        document.get("nodeCount") != len(nodes)
        or document.get("edgeCount") != len(edges)
        or document.get("unresolvedReferenceCount") != 0
        or document.get("unresolvedReferences") != []
    ):
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.GC.REFERENCE_GRAPH_INVALID: graph counts drift"
        )


def validate_plan_document(
    plan: Mapping[str, Any],
    *,
    plan_id: str,
    plan_digest: str | None = None,
) -> str:
    try:
        assert_valid(
            dict(plan),
            "governance",
            "canonical_gc_plan",
            label="canonical GC plan",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(f"GATE_BLOCK DATA.GC.PLAN_INVALID: {exc}") from exc
    actual_digest = json_digest(plan, excluded="planDigest")
    candidates = plan.get("candidates")
    assert isinstance(candidates, list)
    candidate_refs: set[str] = set()
    for row in candidates:
        if not isinstance(row, Mapping):
            raise ObjectTransactionError("GC plan candidate is invalid")
        ref = str(row.get("ref") or "")
        if ref in candidate_refs or row.get("kind") not in GC_CANDIDATE_KINDS:
            raise ObjectTransactionError("GC plan candidate identity is invalid")
        candidate_refs.add(ref)
    if (
        plan.get("schema") != GC_PLAN_SCHEMA
        or plan.get("status") != "planned"
        or plan.get("planId") != plan_id
        or plan.get("planDigest") != actual_digest
        or (plan_digest is not None and plan_digest != actual_digest)
        or plan.get("candidateCount") != len(candidates)
        or plan.get("reclaimableBytes")
        != sum(int(row.get("bytes") or 0) for row in candidates)
    ):
        raise ObjectTransactionError("GC plan identity or digest is invalid")
    validate_reference_graph(dict(plan["referenceGraph"]))
    return actual_digest


def validate_apply_receipt(
    receipt: Mapping[str, Any],
    *,
    plan_id: str,
    plan_digest: str,
) -> None:
    try:
        assert_valid(
            dict(receipt),
            "governance",
            "canonical_gc_apply",
            label="canonical GC apply receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"GATE_BLOCK DATA.GC.APPLY_RECEIPT_INVALID: {exc}"
        ) from exc
    quarantined = receipt.get("quarantined")
    if (
        receipt.get("schema") != GC_APPLY_SCHEMA
        or receipt.get("planId") != plan_id
        or receipt.get("planDigest") != plan_digest
        or receipt.get("status") != "applied"
        or not isinstance(quarantined, list)
        or receipt.get("quarantinedCount") != len(quarantined)
        or receipt.get("permanentDeletion") is not False
        or receipt.get("receiptDigest")
        != json_digest(receipt, excluded="receiptDigest")
    ):
        raise ObjectTransactionError("persisted GC apply receipt drift")


def load_regular_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ObjectTransactionError(
            f"GATE_BLOCK {label} is not a regular file: {path}"
        )
    return _read_json(path)


__all__ = [
    "GC_APPLY_SCHEMA",
    "GC_CANDIDATE_KINDS",
    "GC_PLAN_SCHEMA",
    "GC_REFERENCE_GRAPH_SCHEMA",
    "file_digest",
    "json_digest",
    "load_regular_json",
    "validate_apply_receipt",
    "validate_plan_document",
    "validate_reference_graph",
    "write_create_once_json",
]
