"""homepage 页面图片处置在 `1.download` 截面一次冻结（DEC-029）。

决策的输入闭包在这个截面已经全部就绪：来源单元 `meta.json` 的 `imagePlacements`、
作为枚举真相的下载资产、vertical 的权利政策，以及底稿选出的 `primaryEvidenceRef`。
这里不读任何成稿正文——方向恰恰相反，预排版用本模块的结论把 `[[IMG:fig_NN]]` 插进
底稿，是图片决定正文。

冻结之后，预排版与物化都只消费这份结论，两处都不再调用决策函数。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.page_media import HomepageAssetDisposition, HomepageMediaDisposition

#: 可发布图在 manifest 里的角色与 `assetId` 的角色词表不是一套：assetId 只接受
#: cover/closing/detail，处置则用 cover/inline/related 表达版面语义。
_ASSET_ID_ROLE_BY_DISPOSITION = {
    HomepageAssetDisposition.COVER: "cover",
    HomepageAssetDisposition.INLINE: "detail",
    HomepageAssetDisposition.RELATED: "detail",
}


def publish_disposition(
    index: int,
    image: Mapping[str, Any],
) -> HomepageAssetDisposition:
    """一张可发布图的版面处置，只看来源页事实，不看成稿正文。

    `placementType`、章节锚点与原图注都来自来源单元的 `imagePlacements`，在
    `1.download` 已经落定。正文内嵌要求三者同时成立：来源页把它当正文锚定图、有
    可靠章节锚点、且带非退化的原图注；任一不成立就归相关图片区，因为没有原图注
    的图放进正文只能靠虚构说明文字。
    """
    from core.asset_placement import caption_is_degraded

    if index == 0:
        return HomepageAssetDisposition.COVER
    if str(image.get("placementType") or "").strip() != "inline":
        return HomepageAssetDisposition.RELATED
    if not str(image.get("sectionSlug") or image.get("sectionAnchor") or "").strip():
        return HomepageAssetDisposition.RELATED
    caption = str(image.get("caption") or "")
    file_name = str(image.get("fileName") or "")
    if not caption.strip() or caption_is_degraded(caption, file_name=file_name):
        return HomepageAssetDisposition.RELATED
    return HomepageAssetDisposition.INLINE


def frozen_asset_id(
    execution_id: str,
    name: str,
    image: Mapping[str, Any],
    *,
    disposition: HomepageAssetDisposition,
) -> str:
    """在冻结截面为一张可发布图分配 `assetId`；运行态未就绪即失败，不自造 id。"""
    from content.homepage.homepage_assets import allocate_homepage_asset_id

    asset_id = allocate_homepage_asset_id(
        execution_id,
        name,
        image,
        role=_ASSET_ID_ROLE_BY_DISPOSITION[disposition],
    )
    if not asset_id:
        raise ValueError(
            f"{name}: cannot freeze homepage media without a bound execution sequence"
        )
    return asset_id


def frozen_records(
    execution_id: str,
    name: str,
    publishable: Sequence[Mapping[str, Any]],
    excluded: Sequence[HomepageMediaDisposition],
) -> list[HomepageMediaDisposition]:
    """把一次选择结果转成逐图处置记录，可发布图在此拿到最终 `assetId`。"""
    records = list(excluded)
    for index, image in enumerate(publishable):
        disposition = publish_disposition(index, image)
        records.append(
            HomepageMediaDisposition(
                source_asset_ref=str(image.get("sourceAssetRef") or "").strip(),
                source_asset_id=str(image.get("sourceAssetId") or "").strip(),
                asset_id=frozen_asset_id(
                    execution_id, name, image, disposition=disposition
                ),
                disposition=disposition,
                reason="published",
            )
        )
    return records


def freeze_homepage_media_dispositions(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """冻结一个 homepage 对象的逐图处置与 `assetId`，返回处置文档。

    底稿尚未选出 `primaryEvidenceRef` 时不写任何处置：此时枚举真相还不完整，写一份
    空处置会让「每张下载图恰有一个处置」这条判据在残缺输入上假装成立。
    """
    from content.homepage.homepage import _entity_base_draft
    from content.homepage.homepage_assets import (
        select_homepage_assets,
        write_homepage_media_dispositions,
    )
    from core.paths import execution_entity_object_dir
    from governance.coverage.entity_extract import entity_ref

    base_draft = _entity_base_draft(execution_id, domain, etype, name, aliases=aliases)
    primary_ref = str((base_draft or {}).get("primaryEvidenceRef") or "").strip()
    if not primary_ref:
        return {}
    selection = select_homepage_assets(
        execution_id,
        domain,
        etype,
        name,
        primary_ref=primary_ref,
    )
    return write_homepage_media_dispositions(
        entity_dir=execution_entity_object_dir(execution_id, domain, etype, name),
        execution_id=execution_id,
        object_ref=entity_ref(domain, etype, name),
        records=frozen_records(
            execution_id, name, selection.publishable, selection.excluded
        ),
    )


def frozen_publishable_images(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
) -> list[dict[str, Any]]:
    """按冻结处置取回可发布图，并把处置与 `assetId` 贴回图上。

    这里只做枚举与连接，不做裁决：顺序、角色、id 全部来自 `1.download` 的结论。
    处置说要发布、字节却不在场，是 execution 内部不一致，直接失败而不是悄悄少发
    一张——后者会让「处置与物化同源」这条判据在残缺输出上依然成立。
    """
    from content.source.source_assets import object_image_candidates
    from core.paths import execution_entity_object_dir

    entity_dir = execution_entity_object_dir(execution_id, domain, etype, name)
    rows = load_frozen_dispositions(entity_dir).get("assets") or []
    published = {
        HomepageAssetDisposition.COVER.value,
        HomepageAssetDisposition.INLINE.value,
        HomepageAssetDisposition.RELATED.value,
    }
    by_ref = {
        str(image.get("sourceAssetRef") or "").strip(): image
        for image in object_image_candidates(entity_dir, execution_id)
    }
    images: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        disposition = str(row.get("disposition") or "")
        if disposition not in published:
            continue
        source_asset_ref = str(row.get("sourceAssetRef") or "").strip()
        image = by_ref.get(source_asset_ref)
        if image is None:
            raise ValueError(
                f"{name}: frozen homepage disposition has no downloaded bytes: "
                f"{source_asset_ref}"
            )
        merged = dict(image)
        merged["role"] = disposition
        merged["assetId"] = str(row.get("assetId") or "").strip()
        images.append(merged)
    return images


def load_frozen_dispositions(entity_dir: Path) -> dict[str, Any]:
    """读回冻结处置；缺席返回空 mapping，由调用方决定这是否可继续。"""
    from content.homepage.homepage_assets import MEDIA_DISPOSITIONS_REF
    from core.io import read_json

    path = entity_dir / MEDIA_DISPOSITIONS_REF
    if not path.is_file():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def frozen_disposition_by_source_asset(entity_dir: Path) -> dict[str, dict[str, Any]]:
    """按 `sourceAssetRef` 索引冻结处置，供消费侧逐图对账。"""
    payload = load_frozen_dispositions(entity_dir)
    rows = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ref = str(row.get("sourceAssetRef") or "").strip()
        if ref:
            indexed[ref] = dict(row)
    return indexed


__all__ = [
    "freeze_homepage_media_dispositions",
    "frozen_asset_id",
    "frozen_disposition_by_source_asset",
    "frozen_publishable_images",
    "frozen_records",
    "load_frozen_dispositions",
    "publish_disposition",
]
