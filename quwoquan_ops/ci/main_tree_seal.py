#!/usr/bin/env python3
"""Seal an admitted synthetic tree to the exact main merge tree.

This validator never rebuilds artifacts.  It appends a create-once main-tree
identity only when the reviewed synthetic tree equals the final main tree and
the immutable release composition is already qualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_TREE = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
SCHEMA = "quwoquan.main_tree_seal.v1"


def canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_main_tree_seal(*, manifest: Mapping[str, Any], synthetic_tree_digest: str,
                         main_merge_sha: str, main_tree_digest: str,
                         promotion_receipt: Mapping[str, str]) -> dict[str, Any]:
    if manifest.get("status") != "qualified":
        raise ValueError("MAIN.SEAL.CANDIDATE_NOT_QUALIFIED")
    composition = str(manifest.get("releaseCompositionId") or "")
    evidence_set = str(manifest.get("evidenceSetDigest") or "")
    artifact = str(manifest.get("artifactDigest") or "")
    source = manifest.get("source")
    if any(_DIGEST.fullmatch(value) is None for value in (composition, evidence_set, artifact)):
        raise ValueError("MAIN.SEAL.CANDIDATE_IDENTITY_INVALID")
    if not isinstance(source, Mapping) or source.get("treeDigest") != synthetic_tree_digest:
        raise ValueError("MAIN.SEAL.SYNTHETIC_TREE_DRIFT")
    if _TREE.fullmatch(synthetic_tree_digest) is None or main_tree_digest != synthetic_tree_digest:
        raise ValueError("MAIN.SEAL.FINAL_TREE_DRIFT")
    if _GIT_SHA.fullmatch(main_merge_sha) is None:
        raise ValueError("MAIN.SEAL.MERGE_SHA_INVALID")
    if not isinstance(promotion_receipt, Mapping) or set(promotion_receipt) != {"ref", "digest"}:
        raise ValueError("MAIN.SEAL.PROMOTION_RECEIPT_INVALID")
    if _DIGEST.fullmatch(str(promotion_receipt.get("digest") or "")) is None or not str(promotion_receipt.get("ref") or ""):
        raise ValueError("MAIN.SEAL.PROMOTION_RECEIPT_INVALID")
    payload = {
        "schema": SCHEMA, "releaseCompositionId": composition,
        "evidenceSetDigest": evidence_set, "qualificationArtifactDigest": artifact,
        "syntheticTreeDigest": synthetic_tree_digest, "mainMergeSha": main_merge_sha,
        "mainTreeDigest": main_tree_digest, "promotionReceipt": dict(promotion_receipt),
    }
    return {**payload, "sealDigest": canonical_digest(payload)}


def write_create_once(path: Path, value: Mapping[str, Any]) -> Path:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("MAIN.SEAL.CREATE_ONCE_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(descriptor, json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--synthetic-tree-digest", required=True)
    parser.add_argument("--main-merge-sha", required=True)
    parser.add_argument("--main-tree-digest", required=True)
    parser.add_argument("--promotion-receipt-ref", required=True)
    parser.add_argument("--promotion-receipt-digest", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    seal = build_main_tree_seal(
        manifest=manifest, synthetic_tree_digest=args.synthetic_tree_digest,
        main_merge_sha=args.main_merge_sha, main_tree_digest=args.main_tree_digest,
        promotion_receipt={"ref": args.promotion_receipt_ref, "digest": args.promotion_receipt_digest},
    )
    write_create_once(args.output.resolve(), seal)
    print(seal["sealDigest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
