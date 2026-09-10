"""author 的机械引用绑定：seal 与 publish 共用，不决定内容或执行后继。"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.schema import assert_valid

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


class AuthorBindingError(ValueError):
    """author 声明无法绑定到本对象已取得的事实。"""


def parse_frontmatter(text: str) -> dict[str, Any]:
    """沿用既有 Markdown 语法：key: scalar 与 key: [a, b]，不改写正文。"""

    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    result: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, _sep, raw = line.partition(":")
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            result[key.strip()] = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        else:
            result[key.strip()] = value.strip("'\"")
    return result


def resolve_asset_ref(raw: str, index: Mapping[str, Mapping[str, Any]], *, label: str) -> str:
    """接受 fileName / assets/<fileName> / 完整 sources 引用，结果必须唯一。"""

    value = str(raw or "").strip().strip("/")
    if value in index:
        return value
    tail = value.removeprefix("assets/")
    matches = [ref for ref in index if ref.endswith(f"/assets/{tail}")]
    if len(matches) != 1:
        raise AuthorBindingError(f"{label} assetRef 无法唯一解析到对象资产：{raw!r}")
    return matches[0]


def image_asset_bindings(document: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    """逐图说明按资产身份绑定，拒绝别名重复，输出严格保留 assetRefs 原顺序。"""

    refs = [resolve_asset_ref(raw, index, label="image_work.assetRefs") for raw in document.get("assetRefs") or []]
    if not refs or len(refs) != len(set(refs)):
        raise AuthorBindingError("image_work.assetRefs 必须选择非空且无别名重复的资产")
    raw_captions = document.get("assetCaptions", {})
    if not isinstance(raw_captions, Mapping):
        raise AuthorBindingError("image_work.assetCaptions 必须是引用到非空说明的对象")
    captions: dict[str, str] = {}
    for raw, caption in raw_captions.items():
        ref = resolve_asset_ref(raw, index, label="image_work.assetCaptions")
        if ref not in refs:
            raise AuthorBindingError(f"image_work.assetCaptions 引用了未选资产：{raw!r}")
        if ref in captions:
            raise AuthorBindingError(f"image_work.assetCaptions 别名重复：{raw!r}")
        if not isinstance(caption, str) or not caption.strip():
            raise AuthorBindingError(f"image_work.assetCaptions 说明必须非空：{raw!r}")
        captions[ref] = caption
    return [{"assetRef": ref, "caption": captions.get(ref, str(document.get("caption") or ""))} for ref in refs]


def image_collision_destinations(refs: Sequence[str]) -> dict[str, Path]:
    """仅为同 basename 的 image 资产消歧；完整来源 ref 摘要不依赖输入排序。"""

    counts = Counter(Path(ref).name for ref in refs)
    return {
        ref: Path("assets") / f"{Path(ref).stem}__{hashlib.sha256(ref.encode('utf-8')).hexdigest()}{Path(ref).suffix}"
        for ref in refs if counts[Path(ref).name] > 1
    }


def bind_image_collision(row: dict[str, Any], destination: Path, collision: Path | None) -> Path:
    """只更改冲突文件名与缺稳定 ID 的投影身份，来源/权利字段保持原样。"""

    if collision is None:
        return destination
    row["fileName"] = collision.as_posix()
    row["assetId"] = str(row.get("sourceAssetId") or collision.stem)
    return collision


def homepage_catalog_primary(
    rows: Sequence[Mapping[str, Any]], sources: Sequence[dict[str, Any]], primary_ref: str,
) -> dict[str, Any]:
    """显式引用绑定到同一 catalog 行；未声明沿用原有首百科/首正文来源逻辑。"""

    if primary_ref:
        matches = [source for raw, source in zip(rows, sources) if raw["sourceRef"] == primary_ref]
        if len(matches) != 1:
            raise AuthorBindingError("homepage primarySourceRef 无法唯一绑定 catalog")
        return matches[0]
    primaries = [row for row in sources if row["policyRevision"] == "encyclopedia-primary"]
    primaries = primaries or [row for row in sources if row["sourceKind"] != "image_collection"] or sources
    return primaries[0]


def homepage_source_kind(raw: Mapping[str, Any]) -> tuple[str, str, str]:
    """沿用 canonical 百科种类判据；seal 与显式主源投影只维护同一份闭集。"""

    declared_extractor = (raw.get("meta") or {}).get("extractor")
    identity = " ".join((
        str(raw.get("sourceId") or ""),
        str(raw.get("sourceKind") or ""),
        str((raw.get("meta") or {}).get("sourceClass") or ""),
    )).lower()
    for marker, kind, extractor in (
        ("wikipedia", "wikipedia", "wikipedia_api"),
        ("baidu", "baidu_baike", "baidu_baike_html"),
        ("toutiao", "toutiao_baike", "toutiao_baike_html"),
    ):
        if marker in identity:
            return kind, declared_extractor or extractor, "encyclopedia-primary"
    if any(marker in identity for marker in ("media", "image", "commons")):
        return "image_collection", "image_collection_download", "image-collection-attribution"
    return "web_page", declared_extractor or "html_text", ""


def homepage_primary_source(metadata: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """显式主源必须是本对象取得的百科；未声明返回 None，保留既有投影行为。"""

    try:
        assert_valid(metadata, "content", "homepage_author", label="homepage author")
    except ValueError as exc:
        raise AuthorBindingError(str(exc)) from exc
    if "primarySourceRef" not in metadata:
        encyclopedia_rows = [
            row for row in rows
            if (row.get("sourceClass") or (row.get("meta") or {}).get("sourceClass")) == "encyclopedia"
            and homepage_source_kind(row)[2] == "encyclopedia-primary"
        ]
        if len(encyclopedia_rows) > 1:
            raise AuthorBindingError("homepage 多个百科来源必须显式声明 primarySourceRef")
        return None
    ref = metadata["primarySourceRef"]
    matches = [row for row in rows if row.get("sourceRef") == ref]
    if len(matches) != 1:
        raise AuthorBindingError(f"homepage primarySourceRef 不在本对象已取得来源中或不唯一：{ref!r}")
    primary = matches[0]
    source_class = primary.get("sourceClass") or (primary.get("meta") or {}).get("sourceClass")
    if source_class != "encyclopedia" or homepage_source_kind(primary)[2] != "encyclopedia-primary":
        raise AuthorBindingError(f"homepage primarySourceRef 必须是已取得的百科来源：{ref!r}")
    return primary
