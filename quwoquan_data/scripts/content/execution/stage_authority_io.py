"""Stage authority 共用的 exact-binding 与 create-once IO。"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core import paths


class StageAuthorityError(ValueError):
    """协议或输入拒绝，公开 CLI 映射为退出码 2。"""


class StageAuthorityConflict(StageAuthorityError):
    """create-once slot 已存在不同结论，公开 CLI 映射为退出码 3。"""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def execution_root(execution_id: str) -> Path:
    return paths.DATA_EXECUTIONS_ROOT / execution_id


def binding(path: Path, *, scope: str, root: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    base = root.resolve(strict=True)
    try:
        ref = resolved.relative_to(base).as_posix()
    except ValueError as exc:
        raise StageAuthorityError(f"authority ref escapes {scope} root: {path}") from exc
    if path.is_symlink() or not resolved.is_file():
        raise StageAuthorityError(f"authority ref must be a regular non-symlink file: {path}")
    return {"scope": scope, "ref": ref, "digest": sha256(resolved.read_bytes())}


def resolve_binding(execution_id: str, value: Mapping[str, Any]) -> Path:
    if not {"scope", "ref", "digest"} <= set(value) or set(value) - {"scope", "ref", "digest", "environment"}:
        raise StageAuthorityError("exact binding fields must be scope/ref/digest with optional environment")
    scope = str(value.get("scope") or "")
    roots = {"execution": execution_root(execution_id), "output": paths.OUTPUT_ROOT, "repo": paths.REPO_ROOT}
    if scope not in roots:
        raise StageAuthorityError(f"unknown exact binding scope: {scope!r}")
    ref = str(value.get("ref") or "")
    relative = Path(ref)
    if not ref or relative.is_absolute() or ".." in relative.parts:
        raise StageAuthorityError(f"unsafe exact binding ref: {ref!r}")
    try:
        root = roots[scope].resolve(strict=True)
        path = root / relative
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise StageAuthorityError(f"exact binding is missing or unreadable: {scope}:{ref}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise StageAuthorityError(f"exact binding escapes {scope} root: {ref}") from exc
    if path.is_symlink() or not resolved.is_file():
        raise StageAuthorityError(f"exact binding is not a regular file: {scope}:{ref}")
    actual = sha256(resolved.read_bytes())
    if actual != value.get("digest"):
        raise StageAuthorityError(
            f"exact binding digest drift: {scope}:{ref}; expected {value.get('digest')}, got {actual}"
        )
    return resolved


def write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_file() and not path.is_symlink() and path.read_bytes() == encoded:
            return path
        raise StageAuthorityConflict(f"create-once conflict: {path}")
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    temporary.write_bytes(encoded)
    try:
        os.link(temporary, path)
    except FileExistsError:
        if path.is_file() and not path.is_symlink() and path.read_bytes() == encoded:
            return path
        raise StageAuthorityConflict(f"create-once conflict: {path}")
    finally:
        temporary.unlink(missing_ok=True)
    return path


def artifact_ref_allowed(stage: str, ref: str) -> bool:
    parts = Path(ref).parts
    if stage == "0.plan":
        return ref in {"execution_manifest.json", "0.plan/request.json", "0.plan/target_set.json"} or ref.startswith("0.plan/")
    if stage == "sources":
        return ref.startswith("sources/")
    if stage in {"1.download", "2.quality", "3.compose", "4.draft", "5.review"}:
        return stage in parts and parts.index(stage) == len(parts) - 2
    if stage == "publish":
        return ref == "publish_ref.json" or ref.startswith("publish/")
    return False


def artifact_bindings(
    execution_id: str, stage: str, refs: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    root = execution_root(execution_id)
    for item in refs:
        scope = str(item["scope"])
        ref = str(item["ref"])
        if scope != "execution":
            raise StageAuthorityError("artifactRefs must stay inside the execution root")
        if not artifact_ref_allowed(stage, ref):
            raise StageAuthorityError(f"artifactRef is outside {stage} allowlist: {ref}")
        result.append(binding(root / ref, scope="execution", root=root))
    if len({item["ref"] for item in result}) != len(result):
        raise StageAuthorityError("artifactRefs must be unique")
    return result
