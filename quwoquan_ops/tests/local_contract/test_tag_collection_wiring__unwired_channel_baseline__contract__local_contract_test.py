"""标签采集通道接线门禁的判定契约。

核心是「只减不增」的三个方向：新通道无登记要阻断、基线外未接通要阻断、基线内已接通
也要阻断（否则基线会退化成永久豁免）。另外锁住真实仓库的现状：poi / exif / creator_chip
三条通道确实未接通，且注释里提到符号不算接通。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_tag_collection_wiring.py"

SPEC = importlib.util.spec_from_file_location("tag_collection_wiring", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)

SCHEMA_CHANNELS = frozenset({"exif", "poi", "creator_chip", "review_chip", "onboarding", "pipeline_only"})


def _producer(channel: str, symbol: str | None = "Producer") -> verifier.ChannelProducer:
    return verifier.ChannelProducer(
        channel=channel,
        symbol=symbol,
        defined_in=None if symbol is None else f"lib/{channel}.dart",
        note=f"{channel} 需要生产写入点",
    )


def test_used_channel_without_registered_producer_is_blocked() -> None:
    issues = verifier.validate(
        SCHEMA_CHANNELS,
        {"onboarding": 12},
        (_producer("poi"),),
        frozenset({"poi"}),
        {"poi": []},
    )

    assert any("onboarding" in issue and "未登记生产写入点" in issue for issue in issues)


def test_unwired_channel_outside_baseline_is_blocked() -> None:
    issues = verifier.validate(
        SCHEMA_CHANNELS,
        {"poi": 4059},
        (_producer("poi"),),
        frozenset(),
        {"poi": []},
    )

    assert any("没有生产写入点" in issue for issue in issues)


def test_baseline_entry_must_be_removed_once_wired() -> None:
    issues = verifier.validate(
        SCHEMA_CHANNELS,
        {"poi": 4059},
        (_producer("poi"),),
        frozenset({"poi"}),
        {"poi": ["quwoquan_app/lib/ui/content/entry/widgets/create_publish_confirm_sheet.dart"]},
    )

    assert any("UNWIRED_BASELINE" in issue for issue in issues)


def test_baseline_entry_stays_silent_while_still_unwired() -> None:
    issues = verifier.validate(
        SCHEMA_CHANNELS,
        {"poi": 4059},
        (_producer("poi"),),
        frozenset({"poi"}),
        {"poi": []},
    )

    assert issues == []


def test_producer_outside_schema_enum_is_blocked() -> None:
    issues = verifier.validate(
        SCHEMA_CHANNELS,
        {},
        (_producer("nfc_tap"),),
        frozenset(),
        {"nfc_tap": []},
    )

    assert any("不在 schema 枚举中" in issue for issue in issues)


def test_channel_without_any_implementation_counts_as_unwired() -> None:
    issues = verifier.validate(
        SCHEMA_CHANNELS,
        {"creator_chip": 60},
        (_producer("creator_chip", symbol=None),),
        frozenset(),
        {"creator_chip": []},
    )

    assert any("creator_chip" in issue and "没有生产写入点" in issue for issue in issues)


def test_doc_comment_mention_does_not_count_as_wiring() -> None:
    code = verifier._code_only(
        "\n".join(
            [
                "/// 解析由 GeoTagRefResolver 经 tag-service 完成；",
                "// GeoTagRefResolver 也可能出现在行注释里",
                "/* GeoTagRefResolver 块注释 */",
                "final poi = pickedPoi;",
            ]
        )
    )

    assert "GeoTagRefResolver" not in code
    assert "pickedPoi" in code


def test_repository_channels_are_all_registered() -> None:
    used = verifier.channels_in_use()
    registered = {producer.channel for producer in verifier.PRODUCERS}

    assert used, "taxonomy 必须至少声明一条采集通道"
    assert set(used) <= registered


def test_repository_baseline_channels_are_still_unwired() -> None:
    for producer in verifier.PRODUCERS:
        if producer.channel not in verifier.UNWIRED_BASELINE:
            continue
        references = (
            verifier.production_references(producer.symbol, producer.defined_in)
            if producer.symbol
            else []
        )
        assert references == [], (
            f"{producer.channel} 已接通（{references}），请从 UNWIRED_BASELINE 删除"
        )
