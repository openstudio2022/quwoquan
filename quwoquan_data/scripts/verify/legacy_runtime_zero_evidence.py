"""Create-once package/runtime zero-legacy-entry evidence producer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from verify.legacy_runtime_entries import SCANNED_ROOTS, scan_legacy_runtime_entries

SCHEMA = "quwoquan_data.legacy_runtime_zero_evidence"
_DIGEST_RE = re.compile(r"sha256:[a-f0-9]{64}")


class LegacyRuntimeZeroEvidenceError(ValueError):
    """The scan is blocked or the create-once evidence identity collided."""


def _fingerprint(value: object) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise LegacyRuntimeZeroEvidenceError(
            "sourceFingerprint must be an explicit canonical sha256 digest"
        )
    return value


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"


def _read_regular_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LegacyRuntimeZeroEvidenceError(
                f"create-once evidence target is not a regular file: {path}"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def scan_package_runtime_zero_evidence(
    *, repo_root: Path, source_fingerprint: str
) -> dict[str, Any]:
    fingerprint = _fingerprint(source_fingerprint)
    scan = scan_legacy_runtime_entries(Path(repo_root))
    if scan.scan_errors:
        raise LegacyRuntimeZeroEvidenceError(
            "package/runtime scan is blocked: " + "; ".join(scan.scan_errors)
        )
    legacy_refs = list(scan.legacy_entry_refs)
    return {
        "schema": SCHEMA,
        "sourceFingerprint": fingerprint,
        "scannedRoots": list(SCANNED_ROOTS),
        "legacyEntryRefs": legacy_refs,
        "verdict": "pass" if not legacy_refs else "blocked",
    }


def create_package_runtime_zero_evidence(
    *, repo_root: Path, source_fingerprint: str, output: Path
) -> tuple[dict[str, Any], Path]:
    document = scan_package_runtime_zero_evidence(
        repo_root=repo_root,
        source_fingerprint=source_fingerprint,
    )
    if document["verdict"] != "pass":
        raise LegacyRuntimeZeroEvidenceError(
            "legacy package/runtime refs remain: "
            + ", ".join(str(value) for value in document["legacyEntryRefs"])
        )
    destination = Path(output)
    body = _canonical_bytes(document)
    temporary = ""
    try:
        if destination.is_symlink():
            raise LegacyRuntimeZeroEvidenceError(
                f"create-once evidence target is a symbolic link: {destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        parent = destination.parent.resolve(strict=True)
        parent_metadata = parent.stat()
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise LegacyRuntimeZeroEvidenceError(
                f"create-once evidence parent is not a directory: {destination.parent}"
            )
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            existing = _read_regular_nofollow(destination)
            if existing != body:
                raise LegacyRuntimeZeroEvidenceError(
                    f"create-once evidence id collision: {destination}"
                ) from None
            return document, destination
    except LegacyRuntimeZeroEvidenceError:
        raise
    except OSError as exc:
        raise LegacyRuntimeZeroEvidenceError(
            f"create-once evidence cannot be written safely: {destination}: {exc}"
        ) from exc
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return document, destination


def exact_byte_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(_read_regular_nofollow(Path(path))).hexdigest()


def _blocked_cli(exc: LegacyRuntimeZeroEvidenceError) -> None:
    print(
        json.dumps(
            {"schema": SCHEMA, "verdict": "blocked", "error": str(exc)},
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(1)


def _handle_scan(args: argparse.Namespace) -> None:
    try:
        document = scan_package_runtime_zero_evidence(
            repo_root=Path(args.repo_root),
            source_fingerprint=str(args.source_fingerprint),
        )
    except LegacyRuntimeZeroEvidenceError as exc:
        _blocked_cli(exc)
    print(json.dumps(document, ensure_ascii=False, indent=2))
    if document["verdict"] != "pass":
        raise SystemExit(1)


def _handle_create(args: argparse.Namespace) -> None:
    try:
        document, path = create_package_runtime_zero_evidence(
            repo_root=Path(args.repo_root),
            source_fingerprint=str(args.source_fingerprint),
            output=Path(args.output),
        )
    except LegacyRuntimeZeroEvidenceError as exc:
        _blocked_cli(exc)
    print(
        json.dumps(
            {
                **document,
                "evidenceRef": str(path),
                "exactByteDigest": exact_byte_digest(path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_legacy_runtime_zero_evidence_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "legacy-runtime-zero-evidence",
        help="只读扫描 App/Service/Ops/.github，并仅在零旧入口时创建 exact evidence",
    )
    actions = parser.add_subparsers(dest="legacy_runtime_zero_action", required=True)
    for name, handler in (("scan", _handle_scan), ("create", _handle_create)):
        action = actions.add_parser(name)
        action.add_argument("--source-fingerprint", required=True)
        action.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
        if name == "create":
            action.add_argument("--output", required=True)
        action.set_defaults(handler=handler)


__all__ = [
    "LegacyRuntimeZeroEvidenceError",
    "SCHEMA",
    "create_package_runtime_zero_evidence",
    "exact_byte_digest",
    "register_legacy_runtime_zero_evidence_parser",
    "scan_package_runtime_zero_evidence",
]
