"""纯文本旧对象的受限离线转换，返回新对象 bytes，不写任何路径。

只接受已验证原 receipt/review/record/source 且无媒体的对象。旧 review 保持原字节，
不创建 execution、reviewer、裁决、授权或 receipt。完整池/package 预验仍是调用方责任。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from content.release.canonical.object_transaction_contract import _digest_bytes, _json_bytes, _read_json, _tree_digest
from content.release.canonical.pool_cutover import _absolute, _relative, _regular_tree, _source_digest
from content.release.canonical.pool_cutover_inventory import _fail, _inspect_content
from core.schema import assert_valid

_SIDECARS = {"assetRefsRef": "asset.refs.json", "creatorRefsRef": "creator.refs.json", "tagRefsRef": "tag.refs.json"}


def _classification(value: dict, key: str, old: set[str], new: str) -> None:
    if value.get(key) not in old | {new}:
        _fail("TEXT_CONVERSION_UNSUPPORTED", f"{key}={value.get(key)!r}")
    value[key] = new


def _attribution(document: dict) -> None:
    attribution = document.get("sourceAttribution")
    if not isinstance(attribution, dict):
        _fail("TEXT_CONVERSION_SOURCE_MISSING", "sourceAttribution")
    _classification(attribution, "publicationAdmission", {"research_release", "commercial_release"}, "production_release")
    if "riskAcceptanceId" in attribution:
        if attribution["riskAcceptanceId"] is not None:
            _fail("TEXT_CONVERSION_UNSUPPORTED", "non-null riskAcceptanceId requires exact adjudication")
        del attribution["riskAcceptanceId"]


def _manifest(original: dict, entity: dict | None) -> dict:
    result = copy.deepcopy(original)
    result["version"] += 1
    _classification(result["admission"], "usageScope", {"research", "commercial"}, "production")
    _attribution(result)
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
    if _source_digest(original) != _source_digest(result):
        _fail("TEXT_CONVERSION_SOURCE_DRIFT", "source identity changed")
    return result


def _text_bytes(root: Path, ref: str, final_ref: str) -> dict[Path, bytes]:
    allowed = {"manifest.json", "content_review.json", "rights.json", "source_catalog.json", final_ref, *_SIDECARS.values()}
    if ref.startswith("entities/"):
        allowed.add("_entity.json")
    result = {}
    for path in _regular_tree(root):
        relative = path.relative_to(root)
        if relative.parts[0] == "_pool":
            continue
        if relative.as_posix() not in allowed:
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
    entity = json.loads(result[Path("_entity.json")]) if ref.startswith("entities/") else None
    if entity is not None:
        _attribution(entity)
        assert_valid(entity, "publish", "entity", label=ref)
        result[Path("_entity.json")] = _json_bytes(entity)
    manifest = _manifest(original, entity)
    result[Path("manifest.json")] = _json_bytes(manifest)
    if entity is None:
        assert_valid(manifest, "content", "post_manifest", label=ref)
    rights = json.loads(result[Path("rights.json")])
    assert_valid(rights, "release", "asset_rights_closure", label=ref)
    if rights["assets"] or rights.get("publishMediaMode") != "text_only":
        _fail("TEXT_CONVERSION_MEDIA_FORBIDDEN", "rights assets")
    # 保留原 review 的每个字节；没有刷新 review digest 或代签 receipt 的分支。
    if result[Path("content_review.json")] != (execution / ref / "5.review/content_review.json").read_bytes():
        _fail("TEXT_CONVERSION_REVIEW_DRIFT", ref)
    digest = _digest_bytes(_json_bytes([{"path": path.as_posix(), "sha256": _digest_bytes(raw), "bytes": len(raw)}
                                      for path, raw in sorted(result.items())]))
    records = [_read_json(p) for p in (root / "_pool/versions").glob("*.json")]
    record = copy.deepcopy(max(records, key=lambda row: row["recordSequence"]))
    record.update(recordSequence=1, contentVersion=manifest["version"], payloadDigest=digest,
                  canonicalObjectDigest=digest, usageScope="production", sourceAttribution=manifest["sourceAttribution"])
    assert_valid(record, "release", "pool_object_record", label=ref)
    result[Path("_pool/versions/1.json")] = _json_bytes(record)
    if _tree_digest(root) != before_digest:
        _fail("POOL_CHANGED_DURING_CONVERSION", ref)
    return result
