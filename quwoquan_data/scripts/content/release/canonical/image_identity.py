"""Canonical image identity projection shared by post transactions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.image_deduplication import perceptual_hash


def canonical_asset_manifest_row(
    raw: Mapping[str, Any],
    *,
    asset_source: Path,
    mime_type: str,
    object_key: str,
) -> dict[str, Any]:
    normalized_mime = str(mime_type or "").strip().lower()
    is_image = (
        str(raw.get("kind") or "").strip() == "image"
        or normalized_mime.startswith("image/")
    )
    row = {
        **raw,
        "objectKey": object_key,
        "mimeType": normalized_mime,
    }
    if is_image:
        row["kind"] = "image"
        row["perceptualHash"] = perceptual_hash(asset_source)
    return row


def _acquired_path(root: Path, ref: str) -> Path:
    from content.execution.receipt_chain import _safe_ref
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    path = root / _safe_ref(ref, label="acquired asset ref")
    if any(value.is_symlink() for value in (path, *path.parents)) or not path.is_file():
        raise ObjectTransactionError(f"DATA.PREFLIGHT.SOURCE_PATH_INVALID: {ref}")
    return path


def _acquired_assets(root: Path, object_ref: str) -> dict[str, dict[str, Any]]:
    from content.execution.receipt_chain import _safe_ref
    from content.release.canonical.object_transaction_contract import ObjectTransactionError, _read_json
    from core.schema import assert_valid
    refs = _read_json(_acquired_path(root, f"{object_ref}/1.download/source_refs.json"))
    assert_valid(refs, "source", "object_source_refs", label="preflight source_refs")
    if refs["executionId"] != root.name or refs["objectRef"] != object_ref:
        raise ObjectTransactionError("DATA.PREFLIGHT.SOURCE_IDENTITY_DRIFT")
    result = {}
    for source in refs["sources"]:
        meta_path = _acquired_source(root, object_ref, source)
        index_ref = (meta_path.parent / "assets/index.json").relative_to(root).as_posix()
        index_path = _acquired_path(root, index_ref)
        for row in _acquired_asset_index(root, object_ref, meta_path, index_path):
            file_name = _safe_ref(row["fileName"], label="acquired fileName")
            ref = (index_path.parent / file_name).relative_to(root).as_posix()
            _acquired_path(root, ref)
            if ref in result and result[ref] != row:
                raise ObjectTransactionError(f"DATA.PREFLIGHT.ASSET_IDENTITY_DRIFT: {ref}")
            result[ref] = row
    return result


def _acquired_asset_index(root: Path, object_ref: str, meta_path: Path, index_path: Path) -> list[dict[str, Any]]:
    from content.release.canonical.object_transaction_contract import ObjectTransactionError, _read_json
    meta, document = _read_json(meta_path), _read_json(index_path)
    rows = document.get("assets")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ObjectTransactionError("DATA.PREFLIGHT.ASSET_INDEX_INVALID")
    if not rows:
        return rows
    receipt_ref = str((meta.get("acquisition") or {}).get("receiptRef") or "")
    receipt = _read_json(_acquired_path(root, f"sources/{receipt_ref}"))
    expected = {"schema": "quwoquan_data.acquire_receipt", "executionId": root.name,
                "targetRef": object_ref, "sourceUnitId": meta["sourceUnitId"], "filePage": meta["canonicalUrl"]}
    keys = ("sourceAssetId", "fileName", "assetRole", "sha256", "bytes", "mimeType")
    if (any(receipt.get(key) != value for key, value in expected.items())
            or receipt.get("assets") != [{key: row.get(key) for key in keys} for row in rows]):
        raise ObjectTransactionError("DATA.PREFLIGHT.ACQUISITION_IDENTITY_DRIFT")
    expected_source = {"acquisitionReceiptRef": receipt_ref, "collectionPageUrl": receipt["filePage"],
                       "sourceUrl": receipt["filePage"], "originalAssetUrl": receipt["directUrl"]}
    observed_sources = [{key: row.get(key) for key in expected_source} for row in rows]
    if observed_sources != [expected_source] * len(rows):
        raise ObjectTransactionError("DATA.PREFLIGHT.ASSET_IDENTITY_DRIFT")
    return rows


def _acquired_source(root: Path, object_ref: str, source: Mapping[str, Any]) -> Path:
    from content.release.canonical.object_transaction_contract import ObjectTransactionError, _read_json, _digest_file
    unit = f"sources/{source['sourceUnitId']}"
    if source["metaRef"] != f"{unit}/meta.json" or source["sourceRef"] != f"{unit}/source.md" or object_ref not in source["targetRefs"]:
        raise ObjectTransactionError("DATA.PREFLIGHT.SOURCE_IDENTITY_DRIFT")
    meta_path = _acquired_path(root, source["metaRef"])
    meta = _read_json(meta_path)
    if meta.get("executionId") != root.name or meta.get("targetRef") != object_ref or meta.get("sourceUnitId") != source["sourceUnitId"]:
        raise ObjectTransactionError("DATA.PREFLIGHT.SOURCE_IDENTITY_DRIFT")
    keys = ("sourcePlanRef", "sourcePlanDigest", "chosenCandidateDigest", "sourceId", "sourceClass")
    if any(meta.get(key) != source[key] for key in keys):
        raise ObjectTransactionError("DATA.PREFLIGHT.SOURCE_IDENTITY_DRIFT")
    plan = _acquired_path(root, source["sourcePlanRef"])
    if _digest_file(plan) != source["sourcePlanDigest"]:
        raise ObjectTransactionError("DATA.PREFLIGHT.SOURCE_PLAN_DRIFT")
    _acquired_path(root, source["sourceRef"])
    return meta_path


def _acquired_targets(root: Path, carrier: str) -> dict[str, dict[str, Any]]:
    from content.execution.task_init import _target_ref
    from content.release.canonical.object_transaction_contract import ObjectTransactionError, _read_json, _digest_file
    from core.schema import assert_valid
    manifest = _read_json(_acquired_path(root, "execution_manifest.json"))
    assert_valid(manifest, "execution", "content_execution_manifest", label="preflight execution_manifest")
    target_path = _acquired_path(root, "0.plan/target_set.json")
    if manifest["executionId"] != root.name or manifest["carrier"] != carrier or _digest_file(target_path) != manifest["targetSet"]["digest"]:
        raise ObjectTransactionError("DATA.PREFLIGHT.TARGET_IDENTITY_DRIFT")
    target_set = _read_json(target_path)
    assert_valid(target_set, "execution", "target_set", label="preflight target_set")
    if target_set["executionId"] != root.name or target_set["carrier"] != carrier:
        raise ObjectTransactionError("DATA.PREFLIGHT.TARGET_IDENTITY_DRIFT")
    pairs = [(_target_ref(row, carrier=carrier), row) for row in target_set["targets"]]
    if [ref for ref, _ in pairs] != target_set["targetRefs"] or len(pairs) != target_set["targetCount"]:
        raise ObjectTransactionError("DATA.PREFLIGHT.TARGET_IDENTITY_DRIFT")
    return dict(pairs)


def acquired_asset_identity_view(*, execution_root: Path, selections: list[dict[str, Any]], carrier: str) -> list[dict[str, Any]]:
    """只读已封存 acquire 的显式资产选择；无草稿、投影写入或准入判断。"""
    from content.execution.identity import parse_execution_id
    from content.execution.receipt_chain import validate_live_receipt_chain
    from content.execution.seal import _validate_acquire_target
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    from core.control_types import carrier_of_target_ref

    root = execution_root.absolute()
    refs = [selection["objectRef"] for selection in selections]
    if not refs or len(set(refs)) != len(refs):
        raise ObjectTransactionError("DATA.PREFLIGHT.TARGET_SELECTION_INVALID")
    if parse_execution_id(root.name).content_type.value != carrier or any(carrier_of_target_ref(ref) != carrier for ref in refs):
        raise ObjectTransactionError("DATA.PREFLIGHT.CARRIER_MISMATCH: 读取 execution 前校验载体")
    targets = _acquired_targets(root, carrier)
    chain = validate_live_receipt_chain(execution_id=root.name, execution_root=root, terminal_verdict="pass")
    acquired = {row["ref"] for row in chain.receipts[0]["resultRefs"]}
    candidates = []
    for selection in selections:
        ref = selection["objectRef"]
        if ref not in targets or f"{ref}/1.download/source_refs.json" not in acquired:
            raise ObjectTransactionError(f"DATA.PREFLIGHT.TARGET_NOT_ACQUIRED: {ref}")
        index = _acquired_assets(root, ref)
        _validate_acquire_target(root, ref)
        assets = _selected_identity_rows(root, selection["assetRefs"], index, carrier)
        entity = "/entity/" + targets[ref]["entityType"] + "/" + targets[ref]["name"]
        manifest = {"contentType": "article" if carrier == "homepage" else carrier, "assets": assets}
        if carrier == "homepage":
            manifest.update(schema="quwoquan_data.entity_object", entityRef=entity)
        else:
            manifest["entityRefs"] = [entity]
        candidates.append({"objectRef": ref, "manifest": manifest})
    return candidates


def _selected_identity_rows(root: Path, refs: list[str], index: Mapping[str, Any], carrier: str) -> list[dict[str, Any]]:
    from content.execution.author_bindings import bind_image_collision, image_collision_destinations
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    if len(set(refs)) != len(refs) or any(ref not in index for ref in refs):
        raise ObjectTransactionError("DATA.PREFLIGHT.ASSET_NOT_ACQUIRED: 使用本对象精确来源引用，不接受别名或另一对象资产")
    roles = sorted(index[ref]["assetRole"] for ref in refs)
    if (carrier != "video" and "video" in roles) or (carrier == "image" and not refs) or (carrier == "video" and roles != ["poster", "video"]):
        raise ObjectTransactionError("DATA.PREFLIGHT.ASSET_SELECTION_INVALID")
    if carrier == "video":
        _acquired_video_pair(root, refs, index)
    collisions = image_collision_destinations(refs) if carrier == "image" else {}
    rows = []
    for ref in refs:
        path = _acquired_path(root, ref)
        row = _acquired_identity_row(index[ref], path)
        bind_image_collision(row, Path("assets") / path.name, collisions.get(ref))
        rows.append(row)
    return rows


def _acquired_video_pair(root: Path, refs: list[str], index: Mapping[str, Any]) -> None:
    from content.release.canonical.object_transaction_contract import ObjectTransactionError, _read_json
    video_ref = next(ref for ref in refs if index[ref]["assetRole"] == "video")
    poster_ref = next(ref for ref in refs if index[ref]["assetRole"] == "poster")
    unit = Path(video_ref).parent.parent
    meta = _read_json(_acquired_path(root, (unit / "meta.json").as_posix()))
    acquisition = meta.get("acquisition") or {}
    expected = (unit / str(acquisition.get("posterAssetRef") or "")).as_posix()
    if (poster_ref != expected or index[poster_ref].get("derivedFromSourceAssetId") != index[video_ref].get("sourceAssetId")
            or index[poster_ref]["sha256"] != acquisition.get("posterContentSha256")):
        raise ObjectTransactionError("DATA.PREFLIGHT.VIDEO_POSTER_BINDING_INVALID: 封面必须是所选视频取得记录绑定的派生资产")


def _acquired_identity_row(raw: Mapping[str, Any], path: Path) -> dict[str, Any]:
    from content.release.canonical.object_transaction_contract import ObjectTransactionError, _digest_file
    digest = _digest_file(path)
    if digest != raw["sha256"] or path.stat().st_size != raw["bytes"]:
        raise ObjectTransactionError(f"DATA.PREFLIGHT.ASSET_DIGEST_DRIFT: {path}")
    row = {"assetId": raw.get("sourceAssetId") or path.stem, "sourceAssetId": raw.get("sourceAssetId"),
           "sha256": digest, "kind": "video" if raw["assetRole"] == "video" else "image",
           "collectionPageUrl": raw["collectionPageUrl"], "originalAssetUrl": raw["originalAssetUrl"],
           "mimeType": raw["mimeType"]}
    if row["kind"] == "image":
        row["perceptualHash"] = perceptual_hash(path)
    return row


__all__ = ["canonical_asset_manifest_row", "acquired_asset_identity_view"]
