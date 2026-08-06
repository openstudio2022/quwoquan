"""Linear-space delta/CAS storage for canonical object transactions.

The canonical publish tree remains the consumer-facing projection.  A transaction
stores only the files that it creates or replaces, addressed by content digest.
Rollback and replay materialize the inverse/forward delta; they never snapshot the
whole publish tree.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ALLOWED_CANONICAL_ROOTS,
    ObjectTransactionError,
    _collect_tag_refs,
    _digest_bytes,
    _digest_file,
    _files,
    _json_bytes,
    _read_json,
    _safe_rel,
    _write_json,
)
from content.release.canonical.canonical_inventory import apply_inventory_delta
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT
from core.schema import assert_valid

DELTA_SCHEMA = "quwoquan_data.canonical_transaction_delta"


def _delta_root(run_root: Path) -> Path:
    return run_root / "delta"


def _blob_ref(digest: str) -> Path:
    hex_digest = digest.removeprefix("sha256:")
    if len(hex_digest) != 64 or any(character not in "0123456789abcdef" for character in hex_digest):
        raise ObjectTransactionError(f"invalid transaction blob digest: {digest}")
    return Path("delta/blobs/sha256") / hex_digest[:2] / hex_digest


def _ingest_blob(*, source: Path, run_root: Path) -> dict[str, Any]:
    if not source.is_file() or source.is_symlink():
        raise ObjectTransactionError(f"transaction delta source is not a regular file: {source}")
    digest = _digest_file(source)
    ref = _blob_ref(digest)
    target = run_root / ref
    size = source.stat().st_size
    if target.is_file():
        if _digest_file(target) != digest or target.stat().st_size != size:
            raise ObjectTransactionError(f"transaction CAS collision: {ref}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        shutil.copy2(source, temporary)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"blobRef": ref.as_posix(), "sha256": digest, "bytes": size}


def _destination(value: str) -> Path:
    relative = _safe_rel(value, label="delta.destination")
    if relative.parts[0] not in ALLOWED_CANONICAL_ROOTS:
        raise ObjectTransactionError(f"delta destination is outside canonical roots: {value}")
    return relative


def _register_source(
    sources: dict[str, tuple[Path, bool]],
    *,
    destination: Path,
    source: Path,
    allow_replace: bool = False,
) -> None:
    key = destination.as_posix()
    previous = sources.get(key)
    if previous is not None:
        previous_source, previous_replace = previous
        if _digest_file(previous_source) != _digest_file(source):
            raise ObjectTransactionError(f"transaction delta destination collision: {key}")
        sources[key] = (previous_source, previous_replace or allow_replace)
        return
    sources[key] = (source, allow_replace)


def _manifest_digest(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("deltaDigest", None)
    return _digest_bytes(_json_bytes(payload))


def build_transaction_delta(
    *,
    publish_root: Path,
    run_root: Path,
    package_root: Path,
    package: Mapping[str, Any],
    before_inventory: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze one audited forward/inverse delta against the fenced inventory."""

    delta_root = _delta_root(run_root)
    if delta_root.exists():
        shutil.rmtree(delta_root)
    run_root.mkdir(parents=True, exist_ok=True)
    sources: dict[str, tuple[Path, bool]] = {}
    try:
        for creator in package["creatorObjects"]:
            creator_ref = _safe_rel(str(creator["creatorRef"]), label="creatorRef")
            creator_root = Path(creator["objectRoot"])
            for source in _files(creator_root):
                _register_source(
                    sources,
                    destination=Path("creators") / creator_ref / source.relative_to(creator_root),
                    source=source,
                )

        object_root = Path(package["objectRoot"])
        object_prefix = (
            Path(str(package["objectKind"]))
            / _safe_rel(str(package["objectRef"]), label="objectRef")
        )
        for source in _files(object_root):
            _register_source(
                sources,
                destination=object_prefix / source.relative_to(object_root),
                source=source,
            )

        for row in package["casRows"]:
            _register_source(
                sources,
                destination=_destination(str(row["objectKey"])),
                source=package_root / _safe_rel(str(row["sourceRef"]), label="cas.sourceRef"),
            )

        taxonomy_root = Path(
            os.environ.get("QWQ_TAGS_ROOT") or CONTROL_PLANE_TAXONOMY_ROOT
        )
        tag_refs = {str(item) for item in package["tagRefs"]}
        for creator in package["creatorObjects"]:
            for source in _files(Path(creator["objectRoot"])):
                if source.suffix == ".json":
                    tag_refs.update(_collect_tag_refs(_read_json(source)))
        for source in _files(object_root):
            if source.suffix == ".json":
                tag_refs.update(_collect_tag_refs(_read_json(source)))
        for tag_ref in sorted(tag_refs):
            relative = _safe_rel(tag_ref, label="tagRef")
            source = taxonomy_root / relative / "_definition.json"
            if not source.is_file():
                raise ObjectTransactionError(f"tag closure is not resolvable: {tag_ref}")
            try:
                assert_valid(
                    _read_json(source),
                    "governance",
                    "_definition",
                    label=f"taxonomy tag {tag_ref}",
                )
            except (ValueError, FileNotFoundError) as exc:
                raise ObjectTransactionError(str(exc)) from exc
            _register_source(
                sources,
                destination=Path("tags") / relative / "_definition.json",
                source=source,
                allow_replace=True,
            )

        entries: list[dict[str, Any]] = []
        for destination_text, (source, allow_replace) in sorted(sources.items()):
            destination = publish_root / _destination(destination_text)
            source_digest = _digest_file(source)
            source_bytes = source.stat().st_size
            if destination.is_file():
                current_digest = _digest_file(destination)
                if current_digest == source_digest:
                    continue
                if not allow_replace:
                    raise ObjectTransactionError(
                        f"canonical destination collision: {destination_text}"
                    )
                desired = _ingest_blob(source=source, run_root=run_root)
                before_blob = _ingest_blob(source=destination, run_root=run_root)
                entries.append(
                    {
                        "destination": destination_text,
                        "operation": "replace",
                        **desired,
                        "beforeBlobRef": before_blob["blobRef"],
                        "beforeSha256": before_blob["sha256"],
                        "beforeBytes": before_blob["bytes"],
                    }
                )
            elif destination.exists():
                raise ObjectTransactionError(
                    f"canonical destination is not a regular file: {destination_text}"
                )
            else:
                desired = _ingest_blob(source=source, run_root=run_root)
                if desired["sha256"] != source_digest or desired["bytes"] != source_bytes:
                    raise ObjectTransactionError(
                        f"transaction CAS ingest drift: {destination_text}"
                    )
                entries.append(
                    {
                        "destination": destination_text,
                        "operation": "create",
                        **desired,
                    }
                )

        after_inventory = apply_inventory_delta(
            before_inventory,
            entries,
            publish_root=publish_root,
        )
        before = before_inventory["stats"]
        after = after_inventory["stats"]

        manifest: dict[str, Any] = {
            "schema": DELTA_SCHEMA,
            "transactionId": str(package["transactionId"]),
            "executionId": str(package["executionId"]),
            "targetPrefix": object_prefix.as_posix(),
            "beforeMerkle": str(before["merkleRoot"]),
            "afterMerkle": str(after["merkleRoot"]),
            "beforeInventoryDigest": str(before_inventory["inventoryDigest"]),
            "afterInventoryDigest": str(after_inventory["inventoryDigest"]),
            "entries": entries,
            "createdFileCount": sum(row["operation"] == "create" for row in entries),
            "replacedFileCount": sum(row["operation"] == "replace" for row in entries),
            "deltaBytes": sum(int(row["bytes"]) for row in entries),
        }
        manifest["deltaDigest"] = _manifest_digest(manifest)
        _write_json(delta_root / "manifest.json", manifest)
        return manifest, after_inventory
    except BaseException:
        shutil.rmtree(delta_root, ignore_errors=True)
        raise


def load_transaction_delta(
    *,
    run_root: Path,
    expected_digest: str | None = None,
) -> dict[str, Any]:
    manifest = _read_json(_delta_root(run_root) / "manifest.json")
    if manifest.get("schema") != DELTA_SCHEMA:
        raise ObjectTransactionError("transaction delta schema mismatch")
    actual_digest = _manifest_digest(manifest)
    if manifest.get("deltaDigest") != actual_digest or (
        expected_digest is not None and expected_digest != actual_digest
    ):
        raise ObjectTransactionError("transaction delta digest mismatch")
    for key in (
        "beforeMerkle",
        "afterMerkle",
        "beforeInventoryDigest",
        "afterInventoryDigest",
    ):
        digest = str(manifest.get(key) or "")
        if len(digest) != 71 or not digest.startswith("sha256:"):
            raise ObjectTransactionError(f"transaction delta {key} is invalid")
    destinations: set[str] = set()
    for raw in manifest.get("entries") or []:
        if not isinstance(raw, dict):
            raise ObjectTransactionError("transaction delta entry is invalid")
        destination = _destination(str(raw.get("destination") or "")).as_posix()
        if destination in destinations:
            raise ObjectTransactionError(f"duplicate transaction delta destination: {destination}")
        destinations.add(destination)
        operation = raw.get("operation")
        if operation not in {"create", "replace"}:
            raise ObjectTransactionError(f"invalid transaction delta operation: {operation}")
        refs = [("blobRef", "sha256", "bytes")]
        if operation == "replace":
            refs.append(("beforeBlobRef", "beforeSha256", "beforeBytes"))
        for ref_key, digest_key, bytes_key in refs:
            blob = run_root / _safe_rel(str(raw.get(ref_key) or ""), label=ref_key)
            declared_bytes = raw.get(bytes_key)
            if (
                not isinstance(declared_bytes, int)
                or isinstance(declared_bytes, bool)
                or declared_bytes < 0
                or not blob.is_file()
                or _digest_file(blob) != raw.get(digest_key)
                or blob.stat().st_size != declared_bytes
            ):
                raise ObjectTransactionError(f"transaction delta blob drift: {blob}")
    return manifest


def _materialize_blob(blob: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.transaction.tmp")
    temporary.unlink(missing_ok=True)
    try:
        try:
            os.link(blob, temporary)
        except OSError:
            shutil.copy2(blob, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _ordered_entries(manifest: Mapping[str, Any], *, reverse: bool) -> list[dict[str, Any]]:
    target = str(manifest.get("targetPrefix") or "").rstrip("/") + "/"
    rows = [dict(row) for row in manifest.get("entries") or []]
    rows.sort(
        key=lambda row: (
            str(row["destination"]).startswith(target),
            str(row["destination"]),
        )
    )
    return list(reversed(rows)) if reverse else rows


def apply_forward_delta(
    *,
    publish_root: Path,
    run_root: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    try:
        for entry in _ordered_entries(manifest, reverse=False):
            destination = publish_root / _destination(str(entry["destination"]))
            if entry["operation"] == "create":
                if destination.exists():
                    raise ObjectTransactionError(
                        f"stale create destination already exists: {entry['destination']}"
                    )
            else:
                if not destination.is_file() or _digest_file(destination) != entry["beforeSha256"]:
                    raise ObjectTransactionError(
                        f"stale replace destination drift: {entry['destination']}"
                    )
            blob = run_root / _safe_rel(str(entry["blobRef"]), label="blobRef")
            _materialize_blob(blob, destination)
            if _digest_file(destination) != entry["sha256"]:
                raise ObjectTransactionError(
                    f"post-materialize digest mismatch: {entry['destination']}"
                )
            applied.append(entry)
        return applied
    except BaseException:
        revert_applied_delta(
            publish_root=publish_root,
            run_root=run_root,
            entries=applied,
        )
        raise


def _prune_empty_parents(path: Path, *, root: Path) -> None:
    current = path.parent
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def revert_applied_delta(
    *,
    publish_root: Path,
    run_root: Path,
    entries: list[dict[str, Any]],
) -> None:
    for entry in reversed(entries):
        destination = publish_root / _destination(str(entry["destination"]))
        if entry["operation"] == "create":
            if destination.is_file() and _digest_file(destination) == entry["sha256"]:
                destination.unlink()
                _prune_empty_parents(destination, root=publish_root)
            elif destination.exists():
                raise ObjectTransactionError(
                    f"cannot revert drifted create destination: {entry['destination']}"
                )
        else:
            if not destination.is_file() or _digest_file(destination) != entry["sha256"]:
                raise ObjectTransactionError(
                    f"cannot revert drifted replace destination: {entry['destination']}"
                )
            before_blob = run_root / _safe_rel(
                str(entry["beforeBlobRef"]),
                label="beforeBlobRef",
            )
            _materialize_blob(before_blob, destination)


def apply_inverse_delta(
    *,
    publish_root: Path,
    run_root: Path,
    manifest: Mapping[str, Any],
) -> None:
    entries = _ordered_entries(manifest, reverse=True)
    reverted: list[dict[str, Any]] = []
    try:
        for entry in entries:
            destination = publish_root / _destination(str(entry["destination"]))
            if not destination.is_file() or _digest_file(destination) != entry["sha256"]:
                raise ObjectTransactionError(
                    f"rollback destination drift: {entry['destination']}"
                )
            if entry["operation"] == "create":
                destination.unlink()
                _prune_empty_parents(destination, root=publish_root)
            else:
                before_blob = run_root / _safe_rel(
                    str(entry["beforeBlobRef"]),
                    label="beforeBlobRef",
                )
                _materialize_blob(before_blob, destination)
            reverted.append(entry)
    except BaseException:
        # Restore the forward state for the subset already reverted.
        for entry in reversed(reverted):
            destination = publish_root / _destination(str(entry["destination"]))
            blob = run_root / _safe_rel(str(entry["blobRef"]), label="blobRef")
            _materialize_blob(blob, destination)
        raise


__all__ = [
    "DELTA_SCHEMA",
    "apply_forward_delta",
    "apply_inverse_delta",
    "build_transaction_delta",
    "load_transaction_delta",
    "revert_applied_delta",
]
