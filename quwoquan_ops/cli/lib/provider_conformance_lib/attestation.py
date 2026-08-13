"""源树状态、Git/摘要身份与 CI 证明权威。

可被测试 patch 的符号（ROOT、_current_commit、current_source_tree_state、
ci_attestation_authority_available）一律经薄入口 `_pc` 在调用时读取，
保持与拆分前单文件相同的 mock.patch 语义。
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
import os
from pathlib import Path
import subprocess
from typing import Any

from quwoquan_ops.cli.lib import provider_conformance as _pc

from .constants import COMMIT_PATTERN, SHA256_PATTERN
from .governance_bindings import _is_non_empty_string

def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def implementation_digest(path: Path) -> str | None:
    """Digest one Adapter source file or its deterministic source closure."""
    try:
        if path.is_file():
            return _digest_bytes(path.read_bytes())
        if not path.is_dir():
            return None
        source_suffixes = {
            ".c",
            ".cc",
            ".go",
            ".h",
            ".html",
            ".java",
            ".js",
            ".kt",
            ".mod",
            ".proto",
            ".py",
            ".rs",
            ".sh",
            ".sql",
            ".sum",
            ".swift",
            ".tmpl",
            ".ts",
        }
        files = sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
            and candidate.suffix in source_suffixes
            and not candidate.name.endswith("_test.go")
            and not any(
                part in {"testdata", "tests", ".git", ".qwq_output"}
                for part in candidate.relative_to(path).parts
            )
        )
        if not files:
            return None
        digest = hashlib.sha256()
        for candidate in files:
            digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"
    except OSError:
        return None


def sign_execution_report(raw: bytes, *, key: str | None = None) -> str:
    """为不可变执行报告生成仅 CI 持有密钥可复核的证明。"""
    signing_key = key or os.environ.get("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", "")
    if not signing_key:
        raise ValueError("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY is required")
    return "hmac-sha256:" + hmac.new(
        signing_key.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()


def current_source_tree_state() -> str:
    """Return clean only when Git proves there are no tracked/untracked changes."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=_pc.ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "dirty"
    return "dirty" if completed.stdout else "clean"


def ci_attestation_authority_available(*, commit: str | None = None) -> bool:
    """Recognize the reviewed GitHub workflow authority, never a local key alone."""
    current_commit = commit or _pc._current_commit()
    reviewed_commit = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT",
        "",
    ).strip()
    return (
        os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
        and os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY",
            "",
        ).strip()
        == "ci"
        and bool(
            os.environ.get(
                "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY",
                "",
            ).strip()
        )
        and current_commit is not None
        and reviewed_commit == current_commit
        and _pc.current_source_tree_state() == "clean"
    )


def evidence_identity(
    *,
    commit: str,
    candidate_receipt_bound: bool,
    candidate_receipt_ref: str = "",
    candidate_receipt_digest: str = "",
) -> dict[str, object]:
    """Derive signed promotability identity from source, candidate and authority."""
    source_tree_state = _pc.current_source_tree_state()
    reviewed = (
        os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
        and os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT",
            "",
        ).strip()
        == commit
    )
    ci_authority = (
        reviewed
        and source_tree_state == "clean"
        and _pc.ci_attestation_authority_available(commit=commit)
    )
    receipt_identity_complete = (
        bool(candidate_receipt_ref)
        and SHA256_PATTERN.fullmatch(candidate_receipt_digest) is not None
    )
    candidate_status = (
        "active_immutable"
        if candidate_receipt_bound and receipt_identity_complete
        else "unverified"
    )
    non_promotable = not (
        source_tree_state == "clean"
        and reviewed
        and candidate_status == "active_immutable"
        and ci_authority
    )
    return {
        "nonPromotable": non_promotable,
        "sourceTreeState": source_tree_state,
        "commitReview": "reviewed" if reviewed else "unreviewed",
        "candidateStatus": candidate_status,
        "candidateReceiptRef": (
            candidate_receipt_ref if candidate_status == "active_immutable" else ""
        ),
        "candidateReceiptDigest": (
            candidate_receipt_digest if candidate_status == "active_immutable" else ""
        ),
        "attestationAuthority": "ci" if ci_authority else "local",
    }


def attest_execution_report(
    raw: bytes,
    *,
    identity: Mapping[str, object],
) -> str:
    """Use CI HMAC only for promotable identity; local evidence gets a checksum."""
    if identity.get("attestationAuthority") == "ci":
        return sign_execution_report(raw)
    return "local-sha256:" + hashlib.sha256(raw).hexdigest()


def evidence_is_promotable(
    item: Mapping[str, Any],
    *,
    require_runtime_authority: bool = True,
) -> bool:
    intrinsic = (
        item.get("nonPromotable") is False
        and item.get("sourceTreeState") == "clean"
        and item.get("commitReview") == "reviewed"
        and item.get("candidateStatus") == "active_immutable"
        and _is_non_empty_string(item.get("candidateReceiptRef"))
        and _digest(item.get("candidateReceiptDigest")) is not None
        and item.get("attestationAuthority") == "ci"
    )
    if not intrinsic or not require_runtime_authority:
        return intrinsic
    commit = _commit_digest(item.get("commit"))
    return commit is not None and _pc.ci_attestation_authority_available(commit=commit)


def _current_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_pc.ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit if COMMIT_PATTERN.fullmatch(commit) else None


def _current_contract_graph_digest() -> str | None:
    path = _pc.ROOT / "quwoquan_service" / "generated" / "contract_graph.json"
    try:
        return _digest_bytes(path.read_bytes()) if path.is_file() else None
    except OSError:
        return None


def _current_adapter_digest(adapter: Mapping[str, Any]) -> str | None:
    implementation_path = adapter.get("implementation_path")
    if not isinstance(implementation_path, str):
        return None
    path = _pc.ROOT / implementation_path
    return implementation_digest(path)


def _digest(value: object) -> str | None:
    return value if isinstance(value, str) and SHA256_PATTERN.fullmatch(value) else None


def _commit_digest(value: object) -> str | None:
    return value if isinstance(value, str) and COMMIT_PATTERN.fullmatch(value) else None
