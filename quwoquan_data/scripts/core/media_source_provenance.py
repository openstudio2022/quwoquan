"""素材出处类别裁决：按出处事实判定水印高风险，不看文件名字面。

判据由三个出处事实组成——原始平台、搬运路径、上传者与权利人是否同一主体。
三者都是受版本控制的显式闭集；闭集之外的入站取值落到各自的显式未知成员，
未知成员不等价于任何放行态：它与任一其它风险事实组合时判否，也不能替代
「已声明的低风险平台」。同一出处类别因此得到稳定结论，与命名无关。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

REASON_PREFIX = "watermark_prone_source_provenance"

# 出处事实的显式声明位，与 ``provenance_from_declared_statements`` 的入参一一对应。
# 素材行不写其中任何一个时没有可裁决的出处事实，判否理由取下面这个稳定取值。
# 画面主题一类的描述位不列入：它讲的是画面里有什么，不是谁上传、谁持权、来自哪个
# 平台。把它算作已声明会让「几乎每行都带主题文案」直接绕过下面的判否。
PROVENANCE_STATEMENT_FIELDS: tuple[str, ...] = (
    "creator",
    "credit",
    "uploader",
    "description",
)

UNDECLARED_PROVENANCE_REASON = f"{REASON_PREFIX}:undeclared_source_provenance"


class OriginPlatform(StrEnum):
    """原始平台闭集。"""

    PANORAMIO = "panoramio"
    TUCHONG = "tuchong"
    VCG = "vcg"
    GETTY_IMAGES = "getty_images"
    SHUTTERSTOCK = "shutterstock"
    ALAMY = "alamy"
    DREAMSTIME = "dreamstime"
    FIVE_HUNDRED_PX = "500px"
    FLICKR = "flickr"
    GEOGRAPH = "geograph"
    WIKIMEDIA_COMMONS = "wikimedia_commons"
    RIGHTS_HOLDER_OWN_WORK = "rights_holder_own_work"
    # 闭集之外的入站取值落此成员；它不是放行态。
    UNKNOWN_DECLARED_PLATFORM = "unknown_declared_platform"


class TransportPath(StrEnum):
    """搬运路径闭集。"""

    RIGHTS_HOLDER_DIRECT_UPLOAD = "rights_holder_direct_upload"
    BULK_IMPORT_TOOL = "bulk_import_tool"
    UNKNOWN_DECLARED_TRANSPORT = "unknown_declared_transport"


class RightsHolderAttribution(StrEnum):
    """上传者与权利人关系闭集。"""

    UPLOADER_IS_RIGHTS_HOLDER = "uploader_is_rights_holder"
    THIRD_PARTY_RIGHTS_HOLDER = "third_party_rights_holder"
    UNKNOWN_DECLARED_ATTRIBUTION = "unknown_declared_attribution"


class DerivedModification(StrEnum):
    """CC 协议要求指明的衍生修改闭集。"""

    VIDEO_FRAME_EXTRACTION = "video_frame_extraction"
    CROP = "crop"
    FORMAT_CONVERSION = "format_conversion"


# 水印高风险原始平台闭集：这些平台的原始位图长期带平台角标或图库水印。
WATERMARK_PRONE_ORIGIN_PLATFORMS: frozenset[OriginPlatform] = frozenset(
    {
        OriginPlatform.PANORAMIO,
        OriginPlatform.TUCHONG,
        OriginPlatform.VCG,
        OriginPlatform.GETTY_IMAGES,
        OriginPlatform.SHUTTERSTOCK,
        OriginPlatform.ALAMY,
        OriginPlatform.DREAMSTIME,
        OriginPlatform.FIVE_HUNDRED_PX,
    }
)

# 平台声明别名：只用于解析「声明文本」，不用于文件名或 URL 匹配。
_PLATFORM_DECLARATION_ALIASES: dict[OriginPlatform, tuple[str, ...]] = {
    OriginPlatform.PANORAMIO: ("panoramio",),
    OriginPlatform.TUCHONG: ("tuchong", "图虫"),
    OriginPlatform.VCG: ("vcg", "视觉中国"),
    OriginPlatform.GETTY_IMAGES: ("getty images", "gettyimages"),
    OriginPlatform.SHUTTERSTOCK: ("shutterstock",),
    OriginPlatform.ALAMY: ("alamy",),
    OriginPlatform.DREAMSTIME: ("dreamstime",),
    OriginPlatform.FIVE_HUNDRED_PX: ("500px",),
    OriginPlatform.FLICKR: ("flickr",),
    OriginPlatform.GEOGRAPH: ("geograph",),
    OriginPlatform.WIKIMEDIA_COMMONS: (
        "wikimedia commons",
        "wikimedia contributor",
        "维基",
    ),
    OriginPlatform.RIGHTS_HOLDER_OWN_WORK: ("own work", "self-photographed", "自摄"),
}

# 批量导入工具声明：搬运路径事实，不是命名巧合。
_BULK_IMPORT_DECLARATIONS: tuple[str, ...] = (
    "archive team",
    "transferred from",
    "transfered from",
    "imported from",
    "imported by",
    "batch upload",
    "bulk upload",
    "upload bot",
    "uploadbot",
    "flickrreviewr",
    "bot",
)


@dataclass(frozen=True, slots=True)
class MediaSourceProvenance:
    """一条素材的出处类别。三个事实都必须落在各自闭集内。"""

    origin_platform: OriginPlatform
    transport_path: TransportPath
    rights_holder_attribution: RightsHolderAttribution

    def to_dict(self) -> dict[str, str]:
        return {
            "originPlatform": self.origin_platform.value,
            "transportPath": self.transport_path.value,
            "rightsHolderAttribution": self.rights_holder_attribution.value,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MediaSourceProvenance":
        return cls(
            origin_platform=_closed_member(
                OriginPlatform,
                payload.get("originPlatform"),
                unknown=OriginPlatform.UNKNOWN_DECLARED_PLATFORM,
            ),
            transport_path=_closed_member(
                TransportPath,
                payload.get("transportPath"),
                unknown=TransportPath.UNKNOWN_DECLARED_TRANSPORT,
            ),
            rights_holder_attribution=_closed_member(
                RightsHolderAttribution,
                payload.get("rightsHolderAttribution"),
                unknown=RightsHolderAttribution.UNKNOWN_DECLARED_ATTRIBUTION,
            ),
        )


def _closed_member(enum_type: type[StrEnum], value: object, *, unknown: StrEnum) -> Any:
    """闭集之外的入站取值落显式未知成员，绝不当作放行态。"""

    text = str(value or "").strip()
    if not text:
        return unknown
    try:
        return enum_type(text)
    except ValueError:
        return unknown


def _declared_text(statements: Iterable[object]) -> str:
    return "\n".join(str(value or "").casefold() for value in statements)


def declared_origin_platform(statements: Iterable[object]) -> OriginPlatform:
    """从声明文本解析原始平台；高风险平台优先，未声明落未知成员。"""

    text = _declared_text(statements)
    if not text.strip():
        return OriginPlatform.UNKNOWN_DECLARED_PLATFORM
    ordered = tuple(WATERMARK_PRONE_ORIGIN_PLATFORMS) + tuple(
        platform
        for platform in OriginPlatform
        if platform not in WATERMARK_PRONE_ORIGIN_PLATFORMS
        and platform is not OriginPlatform.UNKNOWN_DECLARED_PLATFORM
    )
    for platform in ordered:
        if any(
            alias in text for alias in _PLATFORM_DECLARATION_ALIASES.get(platform, ())
        ):
            return platform
    return OriginPlatform.UNKNOWN_DECLARED_PLATFORM


def declared_transport_path(statements: Iterable[object]) -> TransportPath:
    """从声明文本解析搬运路径。"""

    text = _declared_text(statements)
    if not text.strip():
        return TransportPath.UNKNOWN_DECLARED_TRANSPORT
    if any(token in text for token in _BULK_IMPORT_DECLARATIONS):
        return TransportPath.BULK_IMPORT_TOOL
    return TransportPath.UNKNOWN_DECLARED_TRANSPORT


def provenance_from_declared_statements(
    *,
    creator: object = "",
    credit: object = "",
    uploader: object = "",
    description: object = "",
) -> MediaSourceProvenance:
    """按 provider 声明的出处事实构造出处类别。

    只读声明字段（作者、出处、上传者、描述），不读文件名或 URL：同一出处
    类别的两张素材因此得到同一结论。
    """

    statements = (creator, credit, uploader, description)
    platform = declared_origin_platform(statements)
    transport = declared_transport_path(statements)
    creator_text = str(creator or "").strip().casefold()
    uploader_text = str(uploader or "").strip().casefold()
    if creator_text and uploader_text and creator_text == uploader_text:
        attribution = RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER
    elif platform is OriginPlatform.RIGHTS_HOLDER_OWN_WORK:
        attribution = RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER
    elif (
        transport is TransportPath.BULK_IMPORT_TOOL
        or platform in WATERMARK_PRONE_ORIGIN_PLATFORMS
    ):
        attribution = RightsHolderAttribution.THIRD_PARTY_RIGHTS_HOLDER
    else:
        attribution = RightsHolderAttribution.UNKNOWN_DECLARED_ATTRIBUTION
    if (
        transport is TransportPath.UNKNOWN_DECLARED_TRANSPORT
        and attribution is RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER
    ):
        transport = TransportPath.RIGHTS_HOLDER_DIRECT_UPLOAD
    return MediaSourceProvenance(
        origin_platform=platform,
        transport_path=transport,
        rights_holder_attribution=attribution,
    )


def watermark_prone_provenance_reason(provenance: MediaSourceProvenance) -> str:
    """出处类别裁决：返回稳定排除理由，放行时返回空串。"""

    if not isinstance(provenance, MediaSourceProvenance):
        raise TypeError("watermark provenance adjudication requires MediaSourceProvenance")
    first_hand = (
        provenance.rights_holder_attribution
        is RightsHolderAttribution.UPLOADER_IS_RIGHTS_HOLDER
    )
    bulk_import = provenance.transport_path is TransportPath.BULK_IMPORT_TOOL
    if provenance.origin_platform in WATERMARK_PRONE_ORIGIN_PLATFORMS and (
        bulk_import or not first_hand
    ):
        return f"{REASON_PREFIX}:{provenance.origin_platform.value}"
    if bulk_import and not first_hand:
        return f"{REASON_PREFIX}:bulk_import_without_first_hand_rights_declaration"
    if bulk_import and provenance.origin_platform is OriginPlatform.UNKNOWN_DECLARED_PLATFORM:
        return f"{REASON_PREFIX}:{OriginPlatform.UNKNOWN_DECLARED_PLATFORM.value}"
    return ""


def declared_provenance_exclusion_reason(row: Mapping[str, Any]) -> str:
    """素材行的出处类别结论，供采集与准入两侧共用同一判据。

    出处事实只从 ``PROVENANCE_STATEMENT_FIELDS`` 这些显式声明位解析，不读 URL
    形态、文件名或托管路径：同一出处类别的两张素材因此得到同一结论。素材行一个
    声明位都没写时判否而不是放行——三个事实此时全落各自的未知成员，而未知成员
    不等价于任何放行态，读侧也不得替写侧补一个从未声明过的取值。
    """

    if not any(
        str(row.get(field) or "").strip() for field in PROVENANCE_STATEMENT_FIELDS
    ):
        return UNDECLARED_PROVENANCE_REASON
    return watermark_prone_provenance_reason(
        provenance_from_declared_statements(
            creator=row.get("creator"),
            credit=row.get("credit"),
            uploader=row.get("uploader"),
            description=row.get("description"),
        )
    )


__all__ = [
    "DerivedModification",
    "MediaSourceProvenance",
    "OriginPlatform",
    "PROVENANCE_STATEMENT_FIELDS",
    "REASON_PREFIX",
    "RightsHolderAttribution",
    "TransportPath",
    "UNDECLARED_PROVENANCE_REASON",
    "WATERMARK_PRONE_ORIGIN_PLATFORMS",
    "declared_origin_platform",
    "declared_provenance_exclusion_reason",
    "declared_transport_path",
    "provenance_from_declared_statements",
    "watermark_prone_provenance_reason",
]
