"""纯文本旧对象的受限离线转换，返回新对象 bytes，不写任何路径。

只接受已验证原 receipt/review/record/source 且无媒体的对象。successor review 仅在存在
闭集旧分类时机械删字段；不创建 execution、reviewer、裁决、授权或 receipt。完整池/package 预验仍是调用方责任。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from content.release.canonical.object_transaction_contract import _digest_bytes, _json_bytes, _read_json, _tree_digest
from content.release.canonical.pool_cutover import _absolute, _relative, _regular_tree, _source_digest
from content.release.canonical.pool_cutover_inventory import (
    _convert_asset_classification, _fail, _inspect_content, _remove_retired_classification, convert_review_document,
)
from core.schema import assert_valid

_SIDECARS = {"assetRefsRef": "asset.refs.json", "creatorRefsRef": "creator.refs.json", "tagRefsRef": "tag.refs.json"}


def _attribution(document: dict, path: str) -> None:
    attribution = document.get("sourceAttribution")
    if not isinstance(attribution, dict):
        _fail("TEXT_CONVERSION_SOURCE_MISSING", "sourceAttribution")
    _remove_retired_classification(
        attribution, "publicationAdmission", {"research_release", "commercial_release"},
        f"{path}.sourceAttribution.publicationAdmission",
    )
    if "riskAcceptanceId" in attribution:
        if attribution["riskAcceptanceId"] is not None:
            _fail("TEXT_CONVERSION_UNSUPPORTED", "non-null riskAcceptanceId requires exact adjudication")
        del attribution["riskAcceptanceId"]


def _manifest(original: dict, entity: dict | None) -> dict:
    result = copy.deepcopy(original)
    result["version"] += 1
    _remove_retired_classification(result["admission"], "usageScope", {"research", "commercial"},
                                   "manifest.admission.usageScope")
    _remove_retired_classification(result, "variantPurpose", {"original", "commercial_variant"},
                                   "manifest.variantPurpose")
    _attribution(result, "manifest")
    _convert_asset_classification(result.get("assets"), "manifest.assets")
    for key, expected in _SIDECARS.items():
        if key in result and result.pop(key) != expected:
            _fail("TEXT_CONVERSION_UNSUPPORTED", key)
    if entity is not None:
        result["contentType"] = "homepage"
        # 原旁车投影来自同一冻结 entity，不从当前控制面选择人物或标签。
        for key in ("creatorProfileId", "tagRefs"):
            if key not in entity:
                _fail("TEXT_CONVERSION_ENTITY_BINDING_MISSING", key)
            if key in result and result[key] != entity[key]:
                _fail("TEXT_CONVERSION_ENTITY_BINDING_DRIFT", key)
            result[key] = copy.deepcopy(entity[key])
    source_predecessor = copy.deepcopy(original)
    _attribution(source_predecessor, "predecessor")
    _convert_asset_classification(source_predecessor.get("assets"), "predecessor.assets")
    if _source_digest(source_predecessor) != _source_digest(result):
        _fail("TEXT_CONVERSION_SOURCE_DRIFT", "source identity changed")
    return result


def _text_bytes(root: Path, ref: str, final_ref: str) -> dict[Path, bytes]:
    allowed = {"manifest.json", "content_review.json", "rights.json", "source_catalog.json", final_ref, *_SIDECARS.values()}
    if ref.startswith("entities/"):
        allowed.add("_entity.json")
    result = {}
    for path in _regular_tree(root):
        relative = path.relative_to(root)
        if relative.parts[0] in {"_pool", "records"}:
            continue
        is_source_evidence = relative.parts[0] == "sources"
        if relative.as_posix() not in allowed and not is_source_evidence:
            _fail("TEXT_CONVERSION_UNSUPPORTED", relative)
        if relative.as_posix() not in _SIDECARS.values():
            result[relative] = path.read_bytes()
    return result


def convert_text_object(*, object_root: Path, execution_root: Path, object_ref: str) -> dict[Path, bytes]:
    """从当前原字节重新核验，不消费 inventory 的 candidate 标签作为资格。"""
    root = _absolute(object_root, kind="tree")
    execution = _absolute(execution_root, kind="tree")
    before_digest = _tree_digest(root)
    ref = _relative(object_ref)
    original = _read_json(root / "manifest.json")
    if (not ref.startswith(("entities/", "posts/article/"))
            or original.get("assets") != [] or original.get("publishMediaMode") != "text_only"):
        _fail("TEXT_CONVERSION_MEDIA_FORBIDDEN", ref)
    _inspect_content(root, execution, ref, original, {})
    result = _text_bytes(root, ref, original["finalContentRef"])
    entity = original if ref.startswith("entities/") else None
    manifest = _manifest(original, entity)
    result[Path("manifest.json")] = _json_bytes(manifest)
    if entity is None:
        assert_valid(manifest, "content", "post_manifest", label=ref)
    rights_path = Path("rights.json")
    rights = json.loads(result[rights_path]) if rights_path in result else {
        "schema": "quwoquan_data.asset_rights_closure",
        "publishMediaMode": "text_only",
        "assets": [],
    }
    _convert_asset_classification(rights.get("assets"), "rights.assets")
    assert_valid(rights, "release", "asset_rights_closure", label=ref)
    if rights["assets"] or rights.get("publishMediaMode") != "text_only":
        _fail("TEXT_CONVERSION_MEDIA_FORBIDDEN", "rights assets")
    # rights.json 是旧 sidecar；只用于 conversion 输入校验，不写入现役单 manifest 包。
    result.pop(rights_path, None)
    # 旧 review 已由原 receipt/execution exact bytes 验真；successor 只机械删分类，不产生新判断。
    original_review = json.loads(result[Path("content_review.json")])
    result[Path("content_review.json")] = _json_bytes(convert_review_document(original_review))
    review_digest = _digest_bytes(result[Path("content_review.json")])
    manifest["admission"].update(evidenceDigest=review_digest, rightsAuthorityDigest=review_digest)
    result[Path("manifest.json")] = _json_bytes(manifest)
    digest = _digest_bytes(_json_bytes([{"path": path.as_posix(), "sha256": _digest_bytes(raw), "bytes": len(raw)}
                                      for path, raw in sorted(result.items())]))
    records = [_read_json(p) for p in (root / "records").glob("*.json")]
    record = copy.deepcopy(max(records, key=lambda row: row["recordSequence"]))
    _remove_retired_classification(record, "usageScope", {"research", "commercial"}, "record.usageScope")
    record.update(recordSequence=1, contentVersion=manifest["version"], payloadDigest=digest,
                  canonicalObjectDigest=digest, sourceAttribution=manifest["sourceAttribution"],
                  evidenceDigest=review_digest, rightsAuthorityDigest=review_digest)
    assert_valid(record, "release", "pool_object_record", label=ref)
    result[Path("records/1.json")] = _json_bytes(record)
    if _tree_digest(root) != before_digest:
        _fail("POOL_CHANGED_DURING_CONVERSION", ref)
    return result
