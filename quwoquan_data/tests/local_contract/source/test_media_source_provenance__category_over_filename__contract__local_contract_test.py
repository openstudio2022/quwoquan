# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t6
"""水印高风险按出处类别裁决，同一类出处结论稳定，与文件名无关。

实测缺陷形态：一张文件名含 `panoramio` 的图被排除，而另一张出处同类
（第三方图库经 Archive Team 批量导入 Commons、导入工具写入、描述在导入中
损坏）但文件名干净的图放行，只有人工独立评审才拦下。判据改为按「上传者与
权利人是否同一主体」「是否经批量导入工具搬运」「原始平台是否属水印高风险
闭集」三个出处事实裁决后，两张必须得到同一结论。
"""
from __future__ import annotations

from content.source.research.homepage_article_source_ready_assets import (
    provenance_admissible_image_rows,
)
from core.media_source_provenance import (
    WATERMARK_PRONE_ORIGIN_PLATFORMS,
    MediaSourceProvenance,
    OriginPlatform,
    RightsHolderAttribution,
    TransportPath,
    declared_provenance_exclusion_reason,
    provenance_from_declared_statements,
    watermark_prone_provenance_reason,
)

CC_TERMS = "https://creativecommons.org/licenses/by-sa/4.0/"


def _row(*, file_name: str, creator: str, credit: str, description: str = "") -> dict[str, str]:
    return {
        "url": f"https://upload.wikimedia.org/{file_name}",
        "sourceUrl": f"https://commons.wikimedia.org/wiki/File:{file_name}",
        "license": "CC BY-SA 4.0",
        "termsUrl": CC_TERMS,
        "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{file_name}",
        "creator": creator,
        "credit": credit,
        "description": description,
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
    }


def test_same_provenance_category_with_different_file_names_gets_one_conclusion() -> None:
    """两张出处同类但文件名不同的素材必须得到同一结论。"""

    named = _row(
        file_name="Qingcheng_-_panoramio_(3).jpg",
        creator="Panoramio upload bot",
        credit="Transferred from Panoramio by Archive Team",
    )
    unnamed = _row(
        file_name="Leshan_Giant_Buddha_cover.jpg",
        creator="Panoramio upload bot",
        credit="Transferred from Panoramio by Archive Team",
        description="description damaged during import",
    )

    reason = declared_provenance_exclusion_reason(named)
    assert reason == "watermark_prone_source_provenance:panoramio"
    assert declared_provenance_exclusion_reason(unnamed) == reason
    assert provenance_admissible_image_rows([named, unnamed]) == []


def test_bulk_import_without_first_hand_rights_declaration_is_excluded() -> None:
    """经批量导入工具搬运且权利人未第一手声明即排除，平台未声明也不放行。"""

    row = _row(
        file_name="Dujiangyan_weir_cover.jpg",
        creator="ImportBot",
        credit="Imported from a third-party stock library by Archive Team",
        description="description damaged during import",
    )
    provenance = provenance_from_declared_statements(
        creator=row["creator"],
        credit=row["credit"],
        description=row["description"],
    )

    assert provenance.transport_path is TransportPath.BULK_IMPORT_TOOL
    assert (
        provenance.rights_holder_attribution
        is RightsHolderAttribution.THIRD_PARTY_RIGHTS_HOLDER
    )
    assert declared_provenance_exclusion_reason(row) == (
        "watermark_prone_source_provenance:"
        "bulk_import_without_first_hand_rights_declaration"
    )
    assert provenance_admissible_image_rows([row]) == []


def test_first_hand_rights_holder_upload_stays_admissible() -> None:
    """权利人自己直接上传的素材不因命名巧合被误伤。"""

    row = _row(
        file_name="Qingcheng_panoramio_lookalike.jpg",
        creator="Zhang San",
        credit="Own work",
    )
    provenance = provenance_from_declared_statements(
        creator=row["creator"], credit=row["credit"]
    )

    assert (
        provenance.rights_holder_attribution
        is RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER
    )
    assert provenance.transport_path is TransportPath.RIGHTS_HOLDER_DIRECT_UPLOAD
    assert declared_provenance_exclusion_reason(row) == ""
    assert provenance_admissible_image_rows([row]) == [row]


def test_a_platform_outside_the_closed_set_lands_on_the_declared_unknown_member() -> None:
    """闭集之外的入站取值落显式未知成员，未知不等价于放行态。"""

    provenance = provenance_from_declared_statements(
        creator="ImportBot",
        credit="Imported by a batch upload tool from an unlisted platform",
    )

    assert provenance.origin_platform is OriginPlatform.UNKNOWN_DECLARED_PLATFORM
    assert OriginPlatform.UNKNOWN_DECLARED_PLATFORM not in (
        WATERMARK_PRONE_ORIGIN_PLATFORMS
    )
    assert watermark_prone_provenance_reason(provenance) != ""


def test_unknown_platform_alone_does_not_manufacture_an_exclusion() -> None:
    """未知平台自身不是排除理由；它只是不能替代已声明的低风险平台。"""

    provenance = MediaSourceProvenance(
        origin_platform=OriginPlatform.UNKNOWN_DECLARED_PLATFORM,
        transport_path=TransportPath.RIGHTS_HOLDER_DIRECT_UPLOAD,
        rights_holder_attribution=RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER,
    )

    assert watermark_prone_provenance_reason(provenance) == ""


def test_high_risk_platform_is_excluded_even_when_the_uploader_claims_the_rights() -> None:
    """高风险平台经批量导入搬运时，仅凭上传者自述也不足以放行。"""

    provenance = MediaSourceProvenance(
        origin_platform=OriginPlatform.PANORAMIO,
        transport_path=TransportPath.BULK_IMPORT_TOOL,
        rights_holder_attribution=RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER,
    )

    assert watermark_prone_provenance_reason(provenance) == (
        "watermark_prone_source_provenance:panoramio"
    )


def test_provenance_facts_round_trip_through_their_closed_sets() -> None:
    """三个出处事实都是闭集成员，落盘与回读同义。"""

    provenance = provenance_from_declared_statements(
        creator="Panoramio upload bot",
        credit="Transferred from Panoramio by Archive Team",
    )
    payload = provenance.to_dict()

    assert payload == {
        "originPlatform": "panoramio",
        "transportPath": "bulk_import_tool",
        "rightsHolderAttribution": "third_party_rights_holder",
    }
    assert MediaSourceProvenance.from_mapping(payload) == provenance
    assert MediaSourceProvenance.from_mapping(
        {**payload, "originPlatform": "not-a-member"}
    ).origin_platform is OriginPlatform.UNKNOWN_DECLARED_PLATFORM
