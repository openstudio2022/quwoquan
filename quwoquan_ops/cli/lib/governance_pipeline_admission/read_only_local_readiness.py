"""Strict read-only verification for explicit local-readiness receipt bytes."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

from ..evidence_fingerprint import validate_evidence_fingerprint
from ..local_readiness.core import (
    RECEIPT_SCHEMA,
    LEVEL_TO_STATE,
    canonicalize_plan,
    capture_fingerprint,
)
from .contract import ContractError, REPO_ROOT


def _read_regular_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ContractError(f"local readiness receipt could not be opened read-only: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ContractError("local readiness receipt must be one regular single-link file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def verify_explicit_receipt_read_only(
    *,
    level: str,
    receipt_path: Path,
    exact_bytes: bytes,
    paths: list[str],
    mode: str,
    owner_manifest_path: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Verify exact receipt and current source identity without touching readiness state."""
    if level not in {"scope", "release"}:
        raise ContractError("local readiness read-only adapter only accepts scope/release")
    if _read_regular_nofollow(receipt_path) != exact_bytes:
        raise ContractError("local readiness receipt exact bytes changed after bundle assembly")
    try:
        receipt = json.loads(exact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"local readiness receipt JSON invalid: {error}") from error
    if not isinstance(receipt, Mapping):
        raise ContractError("local readiness receipt must be an object")
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("level") != level or receipt.get("status") != "PASS":
        raise ContractError("local readiness receipt is not the required PASS level")
    if receipt.get("readiness") != LEVEL_TO_STATE[level] or receipt.get("input_stable") is not True:
        raise ContractError("local readiness PASS identity/stability invalid")
    plan = receipt.get("plan")
    if not isinstance(plan, dict):
        raise ContractError("local readiness receipt plan missing")
    canonical = canonicalize_plan(plan, repo_root=repo_root)
    if canonical["mode"] != mode or canonical["paths"] != sorted(paths):
        raise ContractError("local readiness receipt scope/mode differs from governance contract")
    if receipt.get("paths") != canonical["paths"] or receipt.get("deferred") != []:
        raise ContractError("local readiness receipt still carries deferred or mismatched paths")
    review = receipt.get("review_admission")
    if not isinstance(review, Mapping) or not isinstance(review.get("paths"), list):
        raise ContractError("local readiness receipt review admission shape invalid")
    admission_paths = [repo_root / str(value) for value in review["paths"]]
    review_path = admission_paths[0] if admission_paths else None
    evidence_paths = admission_paths[1:] if admission_paths else []
    current = capture_fingerprint(
        canonical,
        repo_root=repo_root,
        mode=mode,
        owner_manifest=owner_manifest_path,
        review_consolidation=review_path,
        required_evidence=evidence_paths,
    )
    actual = validate_evidence_fingerprint(receipt.get("fingerprint"))
    if actual["digest"] != current["digest"] or actual["digest_payload"] != current["digest_payload"]:
        raise ContractError("local readiness receipt stale: current source identity changed")
    expected_name = f"{actual['digest'].removeprefix('sha256:')}.json"
    if receipt_path.name != expected_name or receipt_path.parent.name != "by-fingerprint":
        raise ContractError("local readiness receipt path is not fingerprint-indexed")
    return dict(receipt)
