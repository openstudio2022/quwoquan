"""Create-once pre-author binding for one illustrated article source unit."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.image_safety import assess_image_publish_prefilter
from core.io import read_json
from core.paths import execution_root
from core.schema import assert_valid
from governance.coverage.distribution import asset_contract_missing_fields

from content.execution.runtime_contract import canonical_sha256, file_sha256
from content.execution.workspace import (
    execution_manifest_path,
    load_frozen_execution_manifest,
)

FREEZE_SCHEMA = "quwoquan_data.article_source_unit_freeze"


class ArticleSourceUnitFreezeError(ValueError):
    """Fail-closed article source snapshot error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"GATE_BLOCK DATA.ARTICLE.SOURCE_UNIT_{code}: {detail}")
        self.code = code


def _typed(code: str, detail: str) -> ArticleSourceUnitFreezeError:
    return ArticleSourceUnitFreezeError(code, detail)


def _safe_execution_ref(root: Path, path: Path, *, label: str) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise _typed("PATH_ESCAPE", f"{label} escapes execution root")
    return resolved.relative_to(resolved_root).as_posix()


def _document(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise _typed("MISSING", f"{label} is missing: {path}")
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise _typed("INVALID", f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise _typed("INVALID", f"{label} must be one JSON object")
    return payload


def _asset_snapshot(
    *,
    root: Path,
    source_dir: Path,
    rows: Sequence[Mapping[str, Any]],
    asset_refs: Sequence[str],
) -> list[dict[str, Any]]:
    if len(asset_refs) < 2 or len(set(asset_refs)) != len(asset_refs):
        raise _typed(
            "ILLUSTRATION_SHORTFALL",
            "illustrated article requires unique cover and body asset refs",
        )
    row_by_ref: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        file_name = str(row.get("fileName") or "").strip()
        if not file_name:
            continue
        ref = _safe_execution_ref(
            root,
            source_dir / "assets" / file_name,
            label="article source asset",
        )
        if ref in row_by_ref:
            raise _typed("ASSET_AMBIGUOUS", f"duplicate source asset ref: {ref}")
        row_by_ref[ref] = row

    snapshots: list[dict[str, Any]] = []
    for index, raw_ref in enumerate(asset_refs):
        asset_ref = str(raw_ref or "").strip()
        row = row_by_ref.get(asset_ref)
        if row is None:
            raise _typed("ASSET_UNDECLARED", f"asset is absent from index: {asset_ref}")
        asset_path = (root / asset_ref).resolve()
        expected_parent = (source_dir / "assets").resolve()
        if expected_parent not in asset_path.parents or not asset_path.is_file():
            raise _typed("PATH_ESCAPE", f"article asset escapes source unit: {asset_ref}")
        observed_sha = file_sha256(asset_path)
        declared_sha = str(row.get("contentSha256") or row.get("sha256") or "")
        if declared_sha != observed_sha:
            raise _typed("DIGEST_DRIFT", f"asset digest drift: {asset_ref}")
        missing = asset_contract_missing_fields(row)
        if missing:
            raise _typed(
                "ADMISSION_INCOMPLETE",
                f"{asset_ref} missing {', '.join(missing)}",
            )
        verdict = assess_image_publish_prefilter(asset_path)
        if verdict.blocks_image_publish:
            reason = "/".join(verdict.reasons) or verdict.status
            raise _typed("QUALITY_BLOCKED", f"{asset_ref}: {reason}")
        snapshots.append(
            {
                "role": "cover" if index == 0 else "body",
                "assetRef": asset_ref,
                "contentSha256": observed_sha,
                "sourceUrl": str(row["sourceUrl"]),
                "platform": str(row["platform"]),
                "creator": str(row.get("creator") or row.get("credit")),
                "capturedAt": str(row["capturedAt"]),
                "license": str(row["license"]),
                "termsUrl": str(row.get("termsUrl") or ""),
                "authorizationProof": str(row.get("authorizationProof") or ""),
                "authorizationRequired": bool(row["authorizationRequired"]),
                "rightsStatus": str(row["rightsStatus"]),
                "rightsIssues": list(row["rightsIssues"]),
                "acquisitionStatus": str(row["acquisitionStatus"]),
                "distributionDecision": str(row["distributionDecision"]),
                "admission": {
                    "qualityStatus": "passed",
                    "safetyStatus": "passed",
                    "sameSourceUnit": True,
                },
            }
        )
    return snapshots


def _stable_snapshot(
    *,
    execution_id: str,
    source_dir: Path,
    asset_refs: Sequence[str],
    execution_root_path: Path | None = None,
) -> dict[str, Any]:
    root = (execution_root_path or execution_root(execution_id)).resolve()
    resolved_source_dir = source_dir.resolve()
    source_parent = (root / "sources").resolve()
    if source_parent not in resolved_source_dir.parents:
        raise _typed("PATH_ESCAPE", "article source unit must be below execution sources/")
    manifest = load_frozen_execution_manifest(execution_id)
    manifest_path = execution_manifest_path(execution_id)
    if execution_root_path is not None:
        manifest_path = root / "execution_manifest.json"
    meta_path = resolved_source_dir / "meta.json"
    source_path = resolved_source_dir / "source.md"
    index_path = resolved_source_dir / "assets/index.json"
    meta = _document(meta_path, label="article source unit manifest")
    index = _document(index_path, label="article source unit asset index")
    rows = [row for row in index.get("assets") or [] if isinstance(row, Mapping)]
    source_unit_id = str(meta.get("sourceUnitId") or "").strip()
    if (
        not source_unit_id
        or "/" in source_unit_id
        or resolved_source_dir.name != source_unit_id
        or meta.get("executionId") != execution_id
        or meta.get("executionBinding") != "frozen"
        or meta.get("researchLane") != "article"
        or meta.get("sourceUseMode") == "blocked"
        or meta.get("rightsMode") == "blocked"
    ):
        raise _typed("IDENTITY_DRIFT", "article source unit execution/rights identity is invalid")
    source_ref = _safe_execution_ref(root, source_path, label="article source")
    source_unit_ref = Path(source_ref).parent.as_posix()
    if (
        meta.get("sourceRef") != source_ref
        or meta.get("sourceUnitRef") != source_unit_ref
        or int(meta.get("assetCount") or -1) != len(rows)
    ):
        raise _typed("IDENTITY_DRIFT", "source manifest refs/assetCount drift")
    if not source_path.is_file() or not source_path.read_text(encoding="utf-8").strip():
        raise _typed("MISSING", "article source.md is empty")
    assets = _asset_snapshot(
        root=root,
        source_dir=resolved_source_dir,
        rows=rows,
        asset_refs=asset_refs,
    )
    source_digest = manifest.get("sourceDigest")
    source_digest = source_digest if isinstance(source_digest, Mapping) else {}
    return {
        "schema": FREEZE_SCHEMA,
        "executionId": execution_id,
        "executionManifestRef": "execution_manifest.json",
        "executionManifestSha256": file_sha256(manifest_path),
        "executionSourceDigest": str(source_digest.get("digest") or ""),
        "sourceUnitId": source_unit_id,
        "sourceUnitRef": source_unit_ref,
        "sourceManifestRef": _safe_execution_ref(root, meta_path, label="source manifest"),
        "sourceManifestSha256": file_sha256(meta_path),
        "sourceRef": source_ref,
        "sourceSha256": file_sha256(source_path),
        "assetIndexRef": _safe_execution_ref(root, index_path, label="asset index"),
        "assetIndexSha256": file_sha256(index_path),
        "assets": assets,
    }


def _create_once(path: Path, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = _document(path, label="article source unit freeze")
            if existing != dict(payload):
                raise _typed("CREATE_ONCE_COLLISION", str(path))
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def write_article_source_unit_freeze(
    *,
    execution_id: str,
    source_dir: Path,
    asset_refs: Sequence[str],
    execution_root_path: Path | None = None,
) -> dict[str, str]:
    """Freeze exact same-source cover/body bytes before semantic authoring."""
    root = (execution_root_path or execution_root(execution_id)).resolve()
    stable = _stable_snapshot(
        execution_id=execution_id,
        source_dir=source_dir,
        asset_refs=asset_refs,
        execution_root_path=execution_root_path,
    )
    document = {**stable, "freezeDigest": canonical_sha256(stable)}
    try:
        assert_valid(
            document,
            "content",
            "article_source_unit_freeze",
            label=f"article source unit freeze:{stable['sourceUnitId']}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _typed("INVALID", str(exc)) from exc
    destination = (
        root
        / "0.plan/article_source_unit_freezes"
        / f"{stable['sourceUnitId']}.json"
    )
    _create_once(destination, document)
    return {
        "receiptRef": destination.relative_to(root).as_posix(),
        "freezeDigest": str(document["freezeDigest"]),
        "sourceUnitId": str(stable["sourceUnitId"]),
        "sourceUnitRef": str(stable["sourceUnitRef"]),
        "executionSourceDigest": str(stable["executionSourceDigest"]),
    }


def validate_article_source_unit_freeze(
    binding: Mapping[str, Any],
    *,
    execution_id: str,
    execution_root_path: Path | None = None,
) -> dict[str, str]:
    """Re-derive all hashes immediately before the author job is emitted."""
    root = (execution_root_path or execution_root(execution_id)).resolve()
    raw_ref = Path(str(binding.get("receiptRef") or ""))
    if raw_ref.is_absolute() or ".." in raw_ref.parts:
        raise _typed("PATH_ESCAPE", "article source freeze receiptRef is unsafe")
    receipt_path = (root / raw_ref).resolve()
    if root not in receipt_path.parents:
        raise _typed("PATH_ESCAPE", "article source freeze receipt escapes execution")
    receipt = _document(receipt_path, label="article source unit freeze")
    try:
        assert_valid(
            receipt,
            "content",
            "article_source_unit_freeze",
            label="article source unit freeze",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _typed("INVALID", str(exc)) from exc
    stable = {key: value for key, value in receipt.items() if key != "freezeDigest"}
    if receipt.get("freezeDigest") != canonical_sha256(stable):
        raise _typed("DIGEST_DRIFT", "article source freeze digest drift")
    current = _stable_snapshot(
        execution_id=execution_id,
        source_dir=root / str(receipt["sourceUnitRef"]),
        asset_refs=[str(row["assetRef"]) for row in receipt["assets"]],
        execution_root_path=execution_root_path,
    )
    if current != stable:
        raise _typed("DIGEST_DRIFT", "article source unit changed after freeze")
    expected = {
        "receiptRef": raw_ref.as_posix(),
        "freezeDigest": str(receipt["freezeDigest"]),
        "sourceUnitId": str(receipt["sourceUnitId"]),
        "sourceUnitRef": str(receipt["sourceUnitRef"]),
        "executionSourceDigest": str(receipt["executionSourceDigest"]),
    }
    if dict(binding) != expected:
        raise _typed("IDENTITY_DRIFT", "article source freeze binding drift")
    return expected


__all__ = [
    "ArticleSourceUnitFreezeError",
    "validate_article_source_unit_freeze",
    "write_article_source_unit_freeze",
]
