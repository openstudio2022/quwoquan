"""Fail-closed provenance repair for canonical objects created before sourceDigest."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Iterable

from core.source_digest import (
    SourceDigestError,
    source_digest_at_git_revision,
)


class CanonicalProvenanceBackfillError(ValueError):
    """A legacy canonical object cannot be proved against one Git revision."""


def backfill_canonical_source_digests(
    *,
    publish_root: Path,
    source_revision: str,
    execution_ids: Iterable[str],
    repo_root: Path,
) -> dict[str, object]:
    """Add the missing sourceDigest only when Git proves the exact legacy inputs.

    This is a one-way data repair, not a compatibility read path.  It never
    overwrites an existing provenance value and requires every changed manifest
    to still equal the supplied immutable Git revision before it is written.
    """
    normalized_ids = tuple(
        sorted({str(item).strip() for item in execution_ids if str(item).strip()})
    )
    if not normalized_ids:
        raise CanonicalProvenanceBackfillError("executionIds 不能为空")
    revision = _resolve_commit(repo_root=repo_root, source_revision=source_revision)
    try:
        source_digest = source_digest_at_git_revision(revision, repo_root=repo_root)
    except SourceDigestError as exc:
        raise CanonicalProvenanceBackfillError(str(exc)) from exc

    candidates = _matching_manifests(
        publish_root=publish_root,
        execution_ids=set(normalized_ids),
    )
    if not candidates:
        raise CanonicalProvenanceBackfillError(
            f"canonical publish 中没有匹配 executionIds 的对象：{','.join(normalized_ids)}"
        )

    expected = source_digest.to_document()
    writes: list[tuple[Path, dict[str, object]]] = []
    unchanged = 0
    for manifest_path, manifest in candidates:
        _assert_manifest_matches_revision(
            repo_root=repo_root,
            revision=revision,
            manifest_path=manifest_path,
        )
        existing = manifest.get("sourceDigest")
        if existing is None:
            writes.append((manifest_path, {**manifest, "sourceDigest": expected}))
            continue
        if existing != expected:
            raise CanonicalProvenanceBackfillError(
                f"拒绝覆盖已有 sourceDigest：{manifest_path}"
            )
        unchanged += 1

    for manifest_path, document in writes:
        _write_json(manifest_path, document)

    return {
        "schema": "quwoquan_data.canonical_provenance_backfill_result",
        "publishRoot": str(publish_root),
        "sourceRevision": revision,
        "sourceDigest": expected,
        "executionIds": list(normalized_ids),
        "updatedCount": len(writes),
        "idempotentCount": unchanged,
        "objectRefs": [
            path.parent.relative_to(publish_root).as_posix()
            for path, _ in candidates
        ],
    }


def _matching_manifests(
    *,
    publish_root: Path,
    execution_ids: set[str],
) -> list[tuple[Path, dict[str, object]]]:
    candidates: list[tuple[Path, dict[str, object]]] = []
    for kind in ("entities", "posts"):
        root = publish_root / kind
        if not root.is_dir():
            continue
        for manifest_path in sorted(root.rglob("manifest.json")):
            manifest = _read_json(manifest_path)
            if str(manifest.get("executionId") or "") in execution_ids:
                candidates.append((manifest_path, manifest))
    return candidates


def _resolve_commit(*, repo_root: Path, source_revision: str) -> str:
    candidate = str(source_revision or "").strip()
    if not candidate:
        raise CanonicalProvenanceBackfillError("source revision 不能为空")
    result = _git(
        repo_root=repo_root,
        arguments=("rev-parse", "--verify", f"{candidate}^{{commit}}"),
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise CanonicalProvenanceBackfillError(
            f"source revision 无法解析为 commit：{candidate}: {detail}"
        )
    return result.stdout.decode("utf-8").strip()


def _assert_manifest_matches_revision(
    *,
    repo_root: Path,
    revision: str,
    manifest_path: Path,
) -> None:
    try:
        relative = manifest_path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise CanonicalProvenanceBackfillError(
            f"canonical manifest 必须位于仓库内：{manifest_path}"
        ) from exc
    historical = _git(
        repo_root=repo_root,
        arguments=("show", f"{revision}:{relative}"),
    )
    if historical.returncode != 0:
        raise CanonicalProvenanceBackfillError(
            f"source revision 不包含 canonical manifest：{relative}"
        )
    try:
        historical_document = json.loads(historical.stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CanonicalProvenanceBackfillError(
            f"source revision 的 canonical manifest 非法：{relative}"
        ) from exc
    current_document = _read_json(manifest_path)
    if not isinstance(historical_document, dict):
        raise CanonicalProvenanceBackfillError(
            f"source revision 的 canonical manifest 必须为 object：{relative}"
        )
    historical_document.pop("sourceDigest", None)
    current_document.pop("sourceDigest", None)
    if current_document != historical_document:
        raise CanonicalProvenanceBackfillError(
            f"canonical manifest 已偏离 source revision，拒绝补写：{relative}"
        )


def _git(*, repo_root: Path, arguments: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ("git", "-C", str(repo_root), *arguments),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise CanonicalProvenanceBackfillError("git 命令不可用") from exc


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalProvenanceBackfillError(
            f"canonical manifest 无法读取：{path}"
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalProvenanceBackfillError(
            f"canonical manifest 必须为 object：{path}"
        )
    return value


def _write_json(path: Path, document: dict[str, object]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "CanonicalProvenanceBackfillError",
    "backfill_canonical_source_digests",
]
