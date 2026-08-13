#!/usr/bin/env python3
"""每个被使用的标签采集通道都必须有生产写入点，且断点数量只减不增。

`_definition.schema.json` 已经把话说死：「没有采集通道的标签是孤儿：永远不会被打上，
也就永远不会参与召回」。但声明一个 `collectionChannel` 只是写下意图——真正决定标签
会不会被打上的，是端侧有没有代码去调用那个通道的解析器。这两件事此前没有任何东西
把它们连起来，结果是 4,159 个标签声明了采集通道，实际一个都没被写上过。

具体断点（本文件 `PRODUCERS` 逐条登记）：

* `poi` 覆盖 4,059 个 `Topic/地理` 节点，解析器 `GeoTagRefResolver` 已实现，但
  发布确认页选中 POI 后只写 `locationPoi`，从不调用它，`Post.geoTagRef` 恒空。
  连锁后果是 `intersection_source.go` 的 `decodeDeclaredVisit` 里区域级同地交集
  分支从未被触发过。
* `creator_chip` 覆盖 60 个节点，历史上端侧没有打标 chip UI；`state.settings.tagRefs`
  只能由正文内联 `@[label](tag:ref)` 填充，那是 semanticMentions 通道，不是 chip。

`exif` 已经接通（`create_page_state.dart` 调用 `extractMediaCaptureMetadata`），已从
基线移除，之后被改回未接通即阻断。`poi`、`creator_chip` 同理（见 PRODUCERS 注记）。

因此本门禁不检查「标签定义得好不好」，只检查一件事：**声明了采集通道，就必须有人
真的去采**。剩余断点进 `UNWIRED_BASELINE`，只减不增：

* 通道被标签使用却没在 `PRODUCERS` 登记 —— 新增通道时忘了想清楚谁来写，阻断。
* 通道不在基线里却未接通 —— 接通后又被改回去，阻断。
* 通道在基线里但已经接通 —— 修好了必须同步把它从基线删掉，否则基线会变成永久豁免。

「已接通」的判定是：生产符号在 `quwoquan_app/lib/**` 中、于定义文件之外被引用，
且不在注释里。只在测试树被引用不算——那恰恰是这三条断点的现状。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_ROOT = ROOT / "quwoquan_data/control_plane/governance/taxonomy"
DEFINITION_SCHEMA = ROOT / "quwoquan_data/schema/governance/_definition.schema.json"
APP_LIB_ROOT = ROOT / "quwoquan_app/lib"


@dataclass(frozen=True)
class ChannelProducer:
    """一条采集通道的生产写入点登记。"""

    channel: str
    # 生产侧必须调用的符号。None 表示该通道连解析器都还没有实现。
    symbol: str | None
    # 符号的全部定义点（抽象声明与实现），相对仓库根。判定接通时必须排除它们：
    # 只有定义点之外的调用才能证明通道真的被生产代码消费。
    defined_in: tuple[str, ...]
    note: str


PRODUCERS: tuple[ChannelProducer, ...] = (
    ChannelProducer(
        channel="poi",
        symbol="GeoTagRefResolver",
        defined_in=(
            "quwoquan_app/lib/service/content_service/content/post/application/geo_tag_ref_resolver.dart",
        ),
        note="发布确认页选中 POI 后必须解析出 Topic/地理/行政区 路径写入 PublishSettings.geoTagRef",
    ),
    ChannelProducer(
        channel="exif",
        symbol="extractMediaCaptureMetadata",
        defined_in=(
            "quwoquan_app/lib/service/content_service/media/media_upload_session/application/public/media_capture_metadata.dart",
            "quwoquan_app/lib/service/content_service/media/media_upload_session/adapters/exif_media_capture_metadata_extractor.dart",
        ),
        note="选中素材后必须解析拍摄事实写入 PublishSettings.captureMetadata",
    ),
    ChannelProducer(
        channel="creator_chip",
        symbol="PublishTagChipPickerPage",
        defined_in=(
            "quwoquan_app/lib/service/content_service/content/post/presentation/publish_tag_chip_picker_page.dart",
        ),
        note="发布确认页打标 chip：创作者主动声明语义标签写入 PublishSettings.tagRefs；"
        "正文内联 mention 属 semanticMentions 通道，不能顶替 chip",
    ),
)

# 当前已知未接通的通道。只减不增：修好一条就必须从这里删掉。
# poi 已接通（create_publish_confirm_sheet.dart 选中 POI 后经 GeoTagRefResolver
# 解析行政区标签写入 PublishSettings.geoTagRef）；creator_chip 已接通
# （create_publish_confirm_sheet.dart 打开 PublishTagChipPickerPage 选中 chip
# 写入 PublishSettings.tagRefs）。任一被改回未接通即阻断。
UNWIRED_BASELINE = frozenset()

_LINE_COMMENT = re.compile(r"^\s*///?")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def declared_channels() -> frozenset[str]:
    """schema 声明的合法采集通道，是通道取值的唯一真相源。"""
    schema = json.loads(DEFINITION_SCHEMA.read_text(encoding="utf-8"))
    values = schema.get("properties", {}).get("collectionChannel", {}).get("enum", [])
    if not values:
        raise SystemExit(f"{DEFINITION_SCHEMA.relative_to(ROOT)} 未声明 collectionChannel 枚举")
    return frozenset(values)


def channels_in_use() -> dict[str, int]:
    """taxonomy 里真实被标签使用的通道及其覆盖标签数。"""
    counts: dict[str, int] = {}
    for definition in TAXONOMY_ROOT.rglob("_definition.json"):
        payload = json.loads(definition.read_text(encoding="utf-8"))
        channel = str(payload.get("collectionChannel") or "").strip()
        if channel:
            counts[channel] = counts.get(channel, 0) + 1
    return counts


def _code_only(text: str) -> str:
    """去掉注释，避免文档注释里提到符号被误判为已接通。"""
    without_blocks = _BLOCK_COMMENT.sub(" ", text)
    return "\n".join(
        line for line in without_blocks.splitlines() if not _LINE_COMMENT.match(line)
    )


def production_references(symbol: str, defined_in: tuple[str, ...]) -> list[str]:
    """符号在 App 生产代码中、定义点之外的引用位置。"""
    excluded = {(ROOT / rel).resolve() for rel in defined_in}
    hits: list[str] = []
    for path in sorted(APP_LIB_ROOT.rglob("*.dart")):
        if path.resolve() in excluded:
            continue
        if symbol in _code_only(path.read_text(encoding="utf-8")):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def stale_definition_paths(producers: tuple[ChannelProducer, ...]) -> list[str]:
    """登记的定义点必须真实存在，否则排除失效、定义点会被误算成生产引用。"""
    issues: list[str] = []
    for producer in producers:
        for rel in producer.defined_in:
            if not (ROOT / rel).is_file():
                issues.append(
                    f"通道 {producer.channel} 登记的定义点不存在：{rel}"
                    "（排除失效会把定义点误判成生产引用，掩盖通道未接通）"
                )
    return issues


def validate(
    schema_channels: frozenset[str],
    used: dict[str, int],
    producers: tuple[ChannelProducer, ...],
    baseline: frozenset[str],
    wired: dict[str, list[str]],
) -> list[str]:
    issues: list[str] = []
    registry = {producer.channel: producer for producer in producers}

    for channel in sorted(registry):
        if channel not in schema_channels:
            issues.append(f"通道 {channel} 已登记生产写入点，但不在 schema 枚举中")

    for channel in sorted(used):
        if channel not in registry:
            issues.append(
                f"通道 {channel} 被 {used[channel]} 个标签使用，但未登记生产写入点："
                "新增采集通道必须同时说明谁负责把标签写到内容或用户上"
            )

    for channel in sorted(baseline):
        if channel not in registry:
            issues.append(f"基线通道 {channel} 未登记生产写入点，基线与登记表已不同源")

    for channel in sorted(registry):
        if channel not in used:
            continue
        references = wired.get(channel, [])
        if references and channel in baseline:
            issues.append(
                f"通道 {channel} 已在生产代码接通（{references[0]} 等 {len(references)} 处），"
                "请从 UNWIRED_BASELINE 删除该条目，避免基线退化成永久豁免"
            )
        if not references and channel not in baseline:
            issues.append(
                f"通道 {channel} 覆盖 {used[channel]} 个标签却没有生产写入点："
                f"{registry[channel].note}"
            )
    return issues


def main() -> int:
    schema_channels = declared_channels()
    used = channels_in_use()
    wired = {
        producer.channel: (
            production_references(producer.symbol, producer.defined_in)
            if producer.symbol
            else []
        )
        for producer in PRODUCERS
    }
    issues = stale_definition_paths(PRODUCERS)
    issues += validate(schema_channels, used, PRODUCERS, UNWIRED_BASELINE, wired)

    if issues:
        print("[verify_tag_collection_wiring] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    unwired = sorted(channel for channel in UNWIRED_BASELINE if channel in used)
    covered = sum(used[channel] for channel in unwired)
    print(
        f"[verify_tag_collection_wiring] OK "
        f"(通道 {len(used)} 条；未接通基线 {len(unwired)} 条覆盖 {covered} 个标签)"
    )
    for channel in unwired:
        print(f"  · {channel}: {used[channel]} 个标签待接通 — {next(p for p in PRODUCERS if p.channel == channel).note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
