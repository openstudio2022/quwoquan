"""把一个已准入 registry 作者显式物化到 canonical 仓；不创作、不审核。"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import yaml

from content.release.canonical import creator_projection
from content.release.canonical.content_pool_record import is_pool_record_admitted, latest_pool_record
from content.release.canonical.creator_avatar_quality import creator_avatar_quality_issues
from content.release.canonical.object_transaction_contract import ObjectTransactionError, _digest_bytes, _safe_id, _tree_digest
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT, PUBLISH_ROOT
from core.publish_repository import repository_sidecar_root, require_publish_repository
from core.schema import assert_valid


class CreatorMaterializationError(ValueError):
    """作者原件、依赖闭包或 create-or-same 身份无法证明。"""


def _local_file(root: Path, ref: str) -> Path:
    relative = Path(ref)
    if (not ref or relative.is_absolute() or relative.as_posix() != ref
            or ".." in relative.parts or "\\" in ref):
        raise CreatorMaterializationError(f"DATA.CREATOR.PATH_INVALID: {ref}")
    path = root / relative
    for entry in (root, *(root / Path(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1))):
        if entry.is_symlink():
            raise CreatorMaterializationError(f"DATA.CREATOR.SYMLINK: {entry}")
    if not path.is_file():
        raise CreatorMaterializationError(f"DATA.CREATOR.EVIDENCE_MISSING: {path}")
    return path


def _admitted_inputs(creator_ref: str, pool: Path) -> tuple[dict, dict[Path, bytes]]:
    source = creator_projection._creator_profile_path(creator_ref, creator_pool_root=pool)
    source = _local_file(pool, source.relative_to(pool).as_posix())
    source_bytes = source.read_bytes()
    profile = yaml.safe_load(source_bytes)
    assert_valid(profile, "content", "creator_profile", label=creator_ref)
    admission = profile["admission"]
    authority = _local_file(pool, admission["evidenceRef"])
    authority_bytes = authority.read_bytes()
    evidence = json.loads(authority_bytes)
    assert_valid(evidence, "content", "author_admission_evidence", label=str(authority))
    if (profile["status"] != "active"
            or admission["processResult"] != evidence["processResult"]
            or admission["qualityResult"] != evidence["qualityResult"]
            or admission["evidenceDigest"] != _digest_bytes(authority_bytes)
            or not profile["authorId"] or profile["authorId"] not in evidence["authorIds"]):
        raise CreatorMaterializationError(f"DATA.CREATOR.AUTHOR_AUTHORITY_DRIFT: {creator_ref}")
    avatar = profile.get("avatarAsset")
    if not isinstance(avatar, dict):
        raise CreatorMaterializationError(f"DATA.CREATOR.AVATAR_MISSING: {creator_ref}")
    avatar_evidence = _local_file(pool, avatar["evidenceRef"])
    return profile, {source: source_bytes, authority: authority_bytes, avatar_evidence: avatar_evidence.read_bytes()}


def _assert_target(root: Path, target: Path) -> None:
    creators = root / "creators"
    for entry in (creators, target):
        if entry.is_symlink():
            raise CreatorMaterializationError(f"DATA.CREATOR.SYMLINK: {entry}")
        if entry.exists() and not entry.is_dir():
            raise CreatorMaterializationError(f"DATA.CREATOR.CONFLICT: {entry}")
    if target.is_dir():
        for entry in target.rglob("*"):
            mode = entry.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise CreatorMaterializationError(f"DATA.CREATOR.CONFLICT: {entry}")


def _project_admitted(creator_ref: str, staging: Path, pool: Path) -> str:
    profile, originals = _admitted_inputs(creator_ref, pool)
    projected = staging / "creators" / creator_ref
    creator_projection.project_creator_object(creator_ref, projected, creator_pool_root=pool)
    # 作者准入仍由 registry 原件拥有；随体复制原字节，不合成 author record。
    evidence_ref = profile["admission"]["evidenceRef"]
    evidence = projected / evidence_ref
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open("xb") as handle:
        handle.write(originals[pool / evidence_ref])
    issues = creator_avatar_quality_issues(staging, creator_refs=[creator_ref])
    if issues or not is_pool_record_admitted(latest_pool_record(projected, "author")):
        raise CreatorMaterializationError(f"DATA.CREATOR.PROJECTION_INVALID: {creator_ref}: {issues}")
    # 投影使用现有 writer 的读取接口；提交前证明它看到的仍是同一份输入。
    current_profile, current_originals = _admitted_inputs(creator_ref, pool)
    if profile != current_profile or originals != current_originals:
        raise CreatorMaterializationError(f"DATA.CREATOR.INPUT_DRIFT: {creator_ref}")
    return _tree_digest(projected)


def materialize_creator(*, creator_ref: str) -> dict[str, object]:
    """单阶段、零网络、共享锁内 create-or-same；不同目标永不替换。"""
    try:
        normalized = _safe_id(creator_ref, label="creatorRef")
        if normalized != creator_ref:
            raise CreatorMaterializationError("DATA.CREATOR.EXACT_REF_REQUIRED")
        root = PUBLISH_ROOT.expanduser().absolute()
        identity = require_publish_repository(root)
        with canonical_publish_lock(root):
            if require_publish_repository(root) != identity:
                raise CreatorMaterializationError("DATA.REPOSITORY.IDENTITY_MISMATCH")
            target = root / "creators" / creator_ref
            _assert_target(root, target)
            sidecar = repository_sidecar_root(root)
            sidecar.mkdir(parents=True, exist_ok=True)
            # 与目标同仓同卷；临时包不进入 canonical inventory，不新增事务台账。
            with tempfile.TemporaryDirectory(prefix="creator-materialize-", dir=sidecar) as temporary:
                staging = Path(temporary)
                digest = _project_admitted(creator_ref, staging, CONTROL_PLANE_CREATOR_POOL_ROOT)
                _assert_target(root, target)
                if require_publish_repository(root) != identity:
                    raise CreatorMaterializationError("DATA.REPOSITORY.IDENTITY_MISMATCH")
                if target.exists():
                    if _tree_digest(target) != digest:
                        raise CreatorMaterializationError(f"DATA.CREATOR.CONFLICT: {creator_ref}")
                    status = "same"
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(staging / "creators" / creator_ref, target)
                    status = "created"
            return {"status": status, "creatorRef": creator_ref,
                    "objectRef": f"creators/{creator_ref}",
                    "repositoryId": identity["repositoryId"], "treeDigest": digest}
    except CreatorMaterializationError:
        raise
    except (OSError, ValueError, TypeError, ObjectTransactionError, yaml.YAMLError) as exc:
        raise CreatorMaterializationError(f"DATA.CREATOR.MATERIALIZE_BLOCKED: {exc}") from exc
