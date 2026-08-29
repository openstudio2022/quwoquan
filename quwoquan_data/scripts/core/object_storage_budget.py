"""单对象存储预算的唯一派生点。

预算数值只有一处显式声明：`control_plane/_shared/media_processing.policy.yaml` 的
`objectStorageBudgetBytesByCarrier`。下载截面的单资产判否与 publish 截面的闭包准入
都经本模块取值，两侧因此不可能对同一个对象得出不同预算——这正是「能下载、能过像素门
的候选到 publish 才被拒」那类白跑整条链的成因。

两跳都是查表，没有一步是从取值形态推出来的：
`research lane（来源单元上的显式声明位）-> 发布载体 -> 预算`。
"""
from __future__ import annotations

from core.control_types import ContentType
from core.media_processing_policy import (
    MEDIA_PROCESSING_POLICY,
    OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER,
)

# research lane 决定该来源单元的资产最终落到哪个发布载体。载体名与
# `verify_object_size_budget.object_carrier` 从对象身份派生出的载体名同域，
# 两处必须指向同一张预算表里的同一档。
_PUBLISH_CARRIER_BY_CONTENT_TYPE: dict[ContentType, str] = {
    ContentType.HOMEPAGE: "entity",
    ContentType.ARTICLE: "article",
    ContentType.IMAGE: "image",
    ContentType.VIDEO: "video",
}


def object_storage_budget_bytes(carrier: str) -> int:
    """一个载体的单对象存储预算。

    取值优先级固定为「具名载体档 -> `default` 档」，两档都写在同一个 policy 文件里，
    因此任一生效值都能指回一处显式声明。`default` 缺席在 policy 装配期就已判否，
    这里不存在「表里什么都没有」的分支。
    """

    table = MEDIA_PROCESSING_POLICY.object_storage_budget_bytes_by_carrier
    named = table.get(str(carrier))
    if named is not None:
        return named
    return table[OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER]


def publish_carrier_for_research_lane(research_lane: str) -> str:
    """来源单元声明的 research lane 所对应的发布载体。

    lane 缺席或落在闭集之外一律判否：拿不到载体就拿不到预算，下载截面因此回答不了
    「这个资产能不能发」，而替它选一个载体等于替它选一个预算。
    """

    try:
        content_type = ContentType(str(research_lane))
    except ValueError as exc:
        raise ValueError(
            "source unit declares no publishable research lane "
            f"(researchLane={research_lane!r}); declare one of "
            f"{sorted(item.value for item in ContentType)} so the download "
            "cross-section can read that carrier's object storage budget"
        ) from exc
    return _PUBLISH_CARRIER_BY_CONTENT_TYPE[content_type]


def source_unit_asset_budget_bytes(research_lane: str) -> int:
    """一张来源单元图片必须装进的字节预算。

    publish 侧把「单个资产自身即超过整个对象预算」判为对象级 blocked
    （`SINGLE_ASSET_OVER_BUDGET`），所以下载截面的单资产上限就是该载体的对象预算本身：
    比它宽的放行值会让候选走完创作与评审全程再被拒。
    """

    return object_storage_budget_bytes(
        publish_carrier_for_research_lane(research_lane)
    )


__all__ = [
    "object_storage_budget_bytes",
    "publish_carrier_for_research_lane",
    "source_unit_asset_budget_bytes",
]
