"""Durable create-once store for explicit canonical handoff references."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .agent_governance_contract import validate_required_fields
from .evidence_fingerprint import canonical_json_bytes
from .objective_execution import secure_storage

HANDOFF_REF_VERSION = "handoff-ref-v1"
HANDOFF_IDENTITY_VERSION = "handoff-identity-v1"
_REF_RE = re.compile(
    r"^handoff-ref-v1:(sha256:[0-9a-f]{64}):(sha256:[0-9a-f]{64})$"
)
_IDENTITY_FIELDS = (
    "intent",
    "triggers",
    "artifacts",
    "pending_dispositions",
    "downstream",
    "human_decision_ref",
    "human_decision_projection",
    "owner_identity_ref",
    "candidate_evidence_ref",
    "review_plan_ref",
    "evidence_receipt_refs",
    "reviewer_result_refs",
    "review_consolidation_ref",
    "recovery_token",
)


class HandoffStoreError(ValueError):
    """Typed persistent handoff storage failure."""

    code = "HANDOFF.STORE_INVALID"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")
        self.detail = detail


class HandoffStoreConflict(HandoffStoreError):
    """The stable handoff identity was already published with other bytes."""

    code = "HANDOFF.CREATE_ONCE_CONFLICT"


class HandoffStoreUnsafe(HandoffStoreError):
    """The authoritative store or published entry is not descriptor-safe."""

    code = "HANDOFF.STORE_UNSAFE"


class HandoffArtifactError(HandoffStoreError):
    """One authoritative handoff artifact cannot be resolved exactly."""

    code = "HANDOFF.ARTIFACT_INVALID"


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def git_common_dir(repo_root: Path) -> Path:
    """Resolve Git's common directory without environment-variable truth."""

    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    raw = result.stdout.strip()
    if result.returncode != 0 or not raw or "\x00" in raw:
        raise HandoffStoreUnsafe("无法解析 current git common-dir")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return Path(os.path.abspath(candidate))


def authoritative_root(repo_root: Path) -> Path:
    """Return the git-internal ignored authoritative handoff root."""

    return git_common_dir(repo_root) / "qwq-state" / "handoffs"


def identity_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in _IDENTITY_FIELDS if field not in payload]
    if missing:
        raise HandoffStoreError(f"handoff identity 缺字段：{missing}")
    return {field: payload[field] for field in _IDENTITY_FIELDS}


def identity_digest(payload: Mapping[str, Any]) -> str:
    return _sha256(canonical_json_bytes(identity_payload(payload)))


def bind_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Bind a stable identity before exact payload bytes are published."""

    payload["handoff_identity"] = {
        "serialization_version": HANDOFF_IDENTITY_VERSION,
        "digest": identity_digest(payload),
    }
    return payload


def _parse_ref(handoff_ref: str) -> tuple[str, str]:
    if not isinstance(handoff_ref, str):
        raise HandoffStoreError("handoff ref 必须为字符串")
    match = _REF_RE.fullmatch(handoff_ref)
    if match is None:
        raise HandoffStoreError("handoff ref 格式非法")
    return match.group(1), match.group(2)


def _entry_name(identity: str) -> str:
    return identity.removeprefix("sha256:") + ".json"


def validate_ref_bytes(handoff_ref: str, exact_bytes: bytes) -> dict[str, Any]:
    """Validate a portable artifact by explicit ref, without clone inventory."""

    identity, byte_digest = _parse_ref(handoff_ref)
    if _sha256(exact_bytes) != byte_digest:
        raise HandoffStoreConflict("handoff ref 与 exact bytes 不一致")
    try:
        payload = json.loads(exact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HandoffStoreError(f"published handoff JSON 非法：{error}") from error
    if not isinstance(payload, dict):
        raise HandoffStoreError("published handoff 必须为 JSON object")
    try:
        validate_required_fields(payload, "handoff_manifest")
    except (TypeError, ValueError) as error:
        raise HandoffStoreError(str(error)) from error
    if canonical_json_bytes(payload) != exact_bytes:
        raise HandoffStoreError("published handoff 必须为 canonical JSON exact bytes")
    binding = payload.get("handoff_identity")
    if binding != {
        "serialization_version": HANDOFF_IDENTITY_VERSION,
        "digest": identity,
    }:
        raise HandoffStoreConflict("published handoff identity binding 与 ref 不一致")
    if identity_digest(payload) != identity:
        raise HandoffStoreConflict("published handoff identity bytes 已漂移")
    return payload


def _read_existing(root_fd: int, name: str) -> bytes | None:
    try:
        descriptor = secure_storage.open_regular_at(
            root_fd, name, "published handoff", os.geteuid()
        )
    except secure_storage.StorageError as error:
        cause = error.__cause__
        if isinstance(cause, OSError) and cause.errno == 2:
            return None
        raise
    try:
        return secure_storage.read_all(descriptor, "published handoff")
    finally:
        os.close(descriptor)


def publish(payload: Mapping[str, Any], *, repo_root: Path) -> tuple[str, bytes]:
    """Publish canonical bytes once; exact replay is idempotent, drift conflicts."""

    mutable = dict(payload)
    binding = mutable.get("handoff_identity")
    expected_identity = identity_digest(mutable)
    if binding != {
        "serialization_version": HANDOFF_IDENTITY_VERSION,
        "digest": expected_identity,
    }:
        raise HandoffStoreError("handoff identity 尚未正确绑定")
    exact_bytes = canonical_json_bytes(mutable)
    handoff_ref = f"{HANDOFF_REF_VERSION}:{expected_identity}:{_sha256(exact_bytes)}"
    name = _entry_name(expected_identity)
    root_fd: int | None = None
    staging_fd: int | None = None
    staging_name = ""
    published = False
    try:
        root_fd, _ = secure_storage._open_canonical_root(
            authoritative_root(repo_root), create=True, owner_uid=os.geteuid()
        )
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        existing = _read_existing(root_fd, name)
        if existing is not None:
            if existing != exact_bytes:
                raise HandoffStoreConflict(
                    f"identity {expected_identity} 已绑定不同 exact bytes"
                )
            validate_ref_bytes(handoff_ref, existing)
            return handoff_ref, existing
        staging_fd, staging_name = secure_storage._create_private(root_fd, "handoff")
        secure_storage._write_complete(staging_fd, exact_bytes, None)
        secure_storage._fsync(staging_fd, "handoff staging file")
        secure_storage.exclusive_publish_at(root_fd, staging_name, name)
        published = True
        secure_storage._fsync(root_fd, "handoff authoritative directory")
        stored = _read_existing(root_fd, name)
        if stored != exact_bytes:
            raise HandoffStoreUnsafe("published handoff exact bytes 复读失败")
        validate_ref_bytes(handoff_ref, stored)
        return handoff_ref, stored
    except HandoffStoreError:
        raise
    except (OSError, secure_storage.StorageError) as error:
        raise HandoffStoreUnsafe(str(error)) from error
    finally:
        if staging_fd is not None:
            try:
                os.close(staging_fd)
            except OSError:
                pass
        if root_fd is not None:
            if staging_name and not published:
                try:
                    os.unlink(staging_name, dir_fd=root_fd)
                    secure_storage._fsync(root_fd, "handoff staging cleanup")
                except (FileNotFoundError, OSError, secure_storage.StorageError):
                    pass
            os.close(root_fd)


def read(handoff_ref: str, *, repo_root: Path) -> bytes:
    """Read exactly one explicitly named authoritative handoff."""

    identity, _byte_digest = _parse_ref(handoff_ref)
    root_fd: int | None = None
    try:
        root_fd, _ = secure_storage._open_canonical_root(
            authoritative_root(repo_root), create=False, owner_uid=os.geteuid()
        )
        exact = _read_existing(root_fd, _entry_name(identity))
        if exact is None:
            raise HandoffStoreError("explicit handoff ref 不存在")
        validate_ref_bytes(handoff_ref, exact)
        return exact
    except HandoffStoreError:
        raise
    except (OSError, secure_storage.StorageError) as error:
        raise HandoffStoreUnsafe(str(error)) from error
    finally:
        if root_fd is not None:
            os.close(root_fd)


def resolve_unique_artifact(
    payload: Mapping[str, Any],
    *,
    repo_root: Path,
    filename: str,
    schema: str,
) -> tuple[str, Path, bytes, str]:
    """Resolve exactly one regular repo artifact and bind its exact bytes.

    ``artifacts`` remains the existing portable string-list interface.  The
    artifact's own canonical schema is its type discriminator; no parallel
    registry or compatibility path is introduced here.
    """

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise HandoffArtifactError("handoff artifacts 必须为列表")
    matches: list[tuple[str, Path, bytes, str]] = []
    for raw_ref in artifacts:
        if not isinstance(raw_ref, str) or not raw_ref:
            raise HandoffArtifactError("handoff artifact ref 必须为非空字符串")
        ref = raw_ref.replace("\\", "/")
        candidate = Path(ref)
        if (
            candidate.is_absolute()
            or ref != candidate.as_posix()
            or candidate.name != filename
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            continue
        path = repo_root / candidate
        try:
            root = repo_root.resolve(strict=True)
            parent = path.parent.resolve(strict=True)
        except OSError as error:
            raise HandoffArtifactError(f"artifact ref 无法解析：{ref}: {error}") from error
        if parent != root and root not in parent.parents:
            raise HandoffArtifactError(f"artifact ref 越出仓库：{ref}")
        if path.is_symlink() or not path.is_file():
            raise HandoffArtifactError(f"artifact 必须为普通非 symlink 文件：{ref}")
        raw = path.read_bytes()
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HandoffArtifactError(f"artifact JSON 非法：{ref}") from error
        if isinstance(document, dict) and document.get("schema") == schema:
            digest = _sha256(raw)
            if path.read_bytes() != raw:
                raise HandoffArtifactError(f"artifact exact bytes 在读取期间漂移：{ref}")
            matches.append((ref, path, raw, digest))
    if len(matches) != 1:
        raise HandoffArtifactError(
            f"authority 必须恰好定位一个 {schema} artifact，实际={len(matches)}"
        )
    return matches[0]
