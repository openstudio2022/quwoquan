"""Plan and apply the one-time Data output namespace migration."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping

from core.paths import DATA_OUTPUT_ROOT
from core.schema import assert_valid


SCHEMA = "quwoquan_data.data_output_layout_migration"
LEGACY_LAYOUT = (
    ("local/article-source-frontier", "local/workspace/article-source-frontier"),
    ("local/gc", "local/workspace/gc"),
    ("local/release-identity-incidents", "local/workspace/release-identity-incidents"),
    ("local/runtime", "local/workspace/runtime"),
    ("local/source-acquisition", "local/workspace/source-acquisition"),
    ("quarantine", "local/workspace/quarantine"),
)


class OutputLayoutMigrationError(ValueError):
    """The output migration cannot proceed without losing identity."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _tree_identity(
    path: Path,
    *,
    root: Path,
    logical_ref: str | None = None,
) -> dict[str, object]:
    files = (path,) if path.is_file() else tuple(
        child for child in sorted(path.rglob("*")) if child.is_file()
    )
    if not files:
        raise OutputLayoutMigrationError(f"legacy output is empty: {path}")
    digest = hashlib.sha256()
    byte_count = 0
    for child in files:
        body = child.read_bytes()
        byte_count += len(body)
        if logical_ref is None:
            identity_ref = child.relative_to(root)
        elif path.is_file():
            identity_ref = Path(logical_ref)
        else:
            identity_ref = Path(logical_ref) / child.relative_to(path)
        digest.update(identity_ref.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return {
        "fileCount": len(files),
        "byteCount": byte_count,
        "digest": "sha256:" + digest.hexdigest(),
    }


def _write_create_once(path: Path, payload: Mapping[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise OutputLayoutMigrationError(f"create-once conflict: {path}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _migration_root(data_output_root: Path) -> Path:
    return data_output_root / "local" / "cache" / "output-layout-migrations"


def plan_output_layout_migration(
    *,
    data_output_root: Path = DATA_OUTPUT_ROOT,
) -> tuple[dict[str, object], Path]:
    root = data_output_root.expanduser().resolve()
    entries: list[dict[str, object]] = []
    for source_ref, destination_ref in LEGACY_LAYOUT:
        source = root / source_ref
        destination = root / destination_ref
        if not source.exists():
            if destination.exists():
                continue
            continue
        if destination.exists():
            raise OutputLayoutMigrationError(
                f"source and destination both exist: {source_ref} -> {destination_ref}"
            )
        entries.append(
            {
                "sourceRef": source_ref,
                "destinationRef": destination_ref,
                **_tree_identity(source, root=root),
            }
        )
    stable = {
        "dataOutputRoot": root.as_posix(),
        "entries": entries,
        "totalFileCount": sum(int(entry["fileCount"]) for entry in entries),
        "totalByteCount": sum(int(entry["byteCount"]) for entry in entries),
    }
    plan_digest = _canonical_digest(stable)
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "documentKind": "plan",
        "planDigest": plan_digest,
        **stable,
        "recordedAt": _now(),
        "appliedAt": None,
        "status": "planned",
    }
    assert_valid(payload, "governance", "data_output_layout_migration", label=SCHEMA)
    destination = _migration_root(root) / plan_digest.removeprefix("sha256:") / "plan.json"
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("planDigest") != plan_digest:
            raise OutputLayoutMigrationError(f"plan create-once conflict: {destination}")
        return existing, destination
    _write_create_once(destination, payload)
    return payload, destination


@contextmanager
def _migration_lock(root: Path) -> Iterator[None]:
    path = _migration_root(root) / ".apply.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_plan(path: Path, *, expected_digest: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OutputLayoutMigrationError("migration plan must be an object")
    assert_valid(payload, "governance", "data_output_layout_migration", label=SCHEMA)
    if payload.get("documentKind") != "plan" or payload.get("status") != "planned":
        raise OutputLayoutMigrationError("migration apply requires a planned document")
    if payload.get("planDigest") != expected_digest:
        raise OutputLayoutMigrationError("migration plan digest binding mismatch")
    stable = {
        "dataOutputRoot": payload["dataOutputRoot"],
        "entries": payload["entries"],
        "totalFileCount": payload["totalFileCount"],
        "totalByteCount": payload["totalByteCount"],
    }
    if _canonical_digest(stable) != expected_digest:
        raise OutputLayoutMigrationError("migration plan content digest mismatch")
    return payload


def _validate_applied_entries(
    root: Path,
    entries: object,
) -> None:
    if not isinstance(entries, list):
        raise OutputLayoutMigrationError("migration entries must be a list")
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise OutputLayoutMigrationError("migration entry must be an object")
        source = root / str(entry["sourceRef"])
        destination = root / str(entry["destinationRef"])
        if source.exists() or not destination.exists():
            raise OutputLayoutMigrationError(
                f"applied migration path state drift: {entry['sourceRef']}"
            )
        identity = _tree_identity(
            destination,
            root=root,
            logical_ref=str(entry["sourceRef"]),
        )
        expected = {
            "fileCount": entry["fileCount"],
            "byteCount": entry["byteCount"],
            "digest": entry["digest"],
        }
        if identity != expected:
            raise OutputLayoutMigrationError(
                f"applied migration byte identity drift: {entry['destinationRef']}"
            )


def apply_output_layout_migration(
    *,
    plan_path: Path,
    plan_digest: str,
) -> tuple[dict[str, object], Path]:
    plan = _load_plan(plan_path.expanduser().resolve(), expected_digest=plan_digest)
    root = Path(str(plan["dataOutputRoot"])).resolve()
    receipt_path = _migration_root(root) / plan_digest.removeprefix("sha256:") / "apply.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert_valid(receipt, "governance", "data_output_layout_migration", label=SCHEMA)
        _validate_applied_entries(root, receipt["entries"])
        return receipt, receipt_path
    with _migration_lock(root):
        for entry in plan["entries"]:
            source = root / str(entry["sourceRef"])
            destination = root / str(entry["destinationRef"])
            if source.exists() and destination.exists():
                raise OutputLayoutMigrationError(
                    f"source and destination both exist: {entry['sourceRef']}"
                )
            if source.exists():
                if _tree_identity(source, root=root) != {
                    "fileCount": entry["fileCount"],
                    "byteCount": entry["byteCount"],
                    "digest": entry["digest"],
                }:
                    raise OutputLayoutMigrationError(
                        f"legacy output drifted after plan: {entry['sourceRef']}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(source, destination)
            elif not destination.exists():
                raise OutputLayoutMigrationError(
                    f"planned source and destination are both missing: {entry['sourceRef']}"
                )
            # The relative path changes during migration.  Recompute a logical
            # digest using the original source prefix to prove byte identity.
            migrated = _tree_identity(
                destination,
                root=root,
                logical_ref=str(entry["sourceRef"]),
            )
            expected = {
                "fileCount": entry["fileCount"],
                "byteCount": entry["byteCount"],
                "digest": entry["digest"],
            }
            if migrated != expected:
                raise OutputLayoutMigrationError(
                    f"migrated output byte identity drift: {entry['destinationRef']}"
                )
        receipt: dict[str, object] = {
            **plan,
            "documentKind": "apply_receipt",
            "appliedAt": _now(),
            "status": "applied",
        }
        assert_valid(receipt, "governance", "data_output_layout_migration", label=SCHEMA)
        _write_create_once(receipt_path, receipt)
    return receipt, receipt_path


__all__ = [
    "LEGACY_LAYOUT",
    "OutputLayoutMigrationError",
    "apply_output_layout_migration",
    "plan_output_layout_migration",
]
