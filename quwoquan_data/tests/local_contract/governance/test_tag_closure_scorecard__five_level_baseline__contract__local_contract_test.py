"""标签闭环五级基线的判定契约。

这里锁住四件事：五级的交集语义（任一级缺失都不算 verified）、孤儿三分类与 schema
注释一致、商用判定只在硬性条件不满足时 BLOCK、孤儿棘轮双向收紧（变多要挡，变少要求下调
上限）。另外对真实仓库做结构自洽与悬空引用校验——发布物引用了 taxonomy 里不存在的
tagRef，既召回不到也筛选不到。
"""
from __future__ import annotations

import pytest

from governance.taxonomy import closure_scorecard
from governance.taxonomy.closure_scorecard import (
    AxisRoll,
    Scorecard,
    TagRecord,
    build_report,
    collect_scorecard,
    commercial_verdict,
    gate_violations,
    orphan_breakdown,
    totals,
)


def _record(ref: str, *, channel: str = "", consumers: tuple[str, ...] = ()) -> TagRecord:
    return TagRecord(
        ref=ref,
        axis="/".join(ref.split("/")[:2]),
        collection_channel=channel,
        consumed_by=consumers,
    )


def _card(records: list[TagRecord], published: set[str]) -> Scorecard:
    card = Scorecard()
    card.records = records
    card.published_refs = published
    card.post_count = 1
    return card


def test_verified_requires_collection_supply_and_consumption() -> None:
    full = _record("Topic/摄影/风光摄影", channel="creator_chip", consumers=("recall",))
    no_channel = _record("Topic/自然风光/雪山", consumers=("recall",))
    no_consumer = _record("Topic/摄影/器材/机身类型/手机拍摄", channel="exif")
    no_supply = _record("Topic/地理/行政区/中国", channel="poi", consumers=("recall",))

    card = _card(
        [full, no_channel, no_consumer, no_supply],
        published={full.ref, no_channel.ref, no_consumer.ref},
    )
    total = totals(card)

    assert total.defined == 4
    assert total.collectible == 3
    assert total.published == 3
    assert total.consumed == 3
    # 只有四项齐全的那一个进 verified：三级互不补偿。
    assert total.verified == 1


def test_orphan_breakdown_matches_schema_definition() -> None:
    card = _card(
        [
            _record("Topic/自然风光/雪山"),
            _record("Topic/摄影/器材/机身类型/手机拍摄", channel="exif"),
            _record("Topic/地理/行政区/中国", channel="poi", consumers=("recall",)),
        ],
        published=set(),
    )

    assert orphan_breakdown(card) == {
        "no_collection_channel": 1,
        "collectible_but_unconsumed": 1,
        "consumed_but_unsupplied": 1,
    }


def test_axis_rolls_partition_the_defined_total() -> None:
    card = _card(
        [
            _record("Topic/摄影/风光摄影", channel="creator_chip", consumers=("recall",)),
            _record("Topic/摄影/街头摄影", channel="creator_chip", consumers=("recall",)),
            _record("Format/内容角度/攻略"),
        ],
        published={"Topic/摄影/风光摄影"},
    )
    report = build_report(card)

    assert report.axes["Topic/摄影"].defined == 2
    assert report.axes["Format/内容角度"].defined == 1
    assert sum(roll.defined for roll in report.axes.values()) == report.total.defined


def test_verdict_blocks_when_nothing_runs_end_to_end() -> None:
    verdict = commercial_verdict(
        AxisRoll(defined=5891, collectible=4159, published=5, consumed=4159, verified=0)
    )

    assert verdict.verdict == "BLOCK"
    assert any("verified=0" in reason for reason in verdict.reasons)


def test_verdict_blocks_when_collection_coverage_is_negligible() -> None:
    verdict = commercial_verdict(
        AxisRoll(defined=1000, collectible=50, published=10, consumed=900, verified=5)
    )

    assert verdict.verdict == "BLOCK"
    assert any("collectible 占比" in reason for reason in verdict.reasons)


def test_verdict_ready_once_minimums_hold() -> None:
    verdict = commercial_verdict(
        AxisRoll(defined=1000, collectible=800, published=120, consumed=900, verified=100)
    )

    assert verdict.verdict == "READY"
    assert verdict.reasons == ()


def _orphan_report(orphan_count: int) -> object:
    records = [_record(f"Topic/自然风光/无通道{index}") for index in range(orphan_count)]
    records.append(_record("Topic/摄影/风光摄影", channel="creator_chip", consumers=("recall",)))
    return build_report(_card(records, published={"Topic/摄影/风光摄影"}))


def test_gate_blocks_new_tags_without_a_collection_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(closure_scorecard, "ORPHAN_NO_CHANNEL_CEILING", 2)
    problems = gate_violations(_orphan_report(3))

    assert any("新增了没有采集通道的标签定义" in problem for problem in problems)


def test_gate_demands_the_ceiling_drop_once_channels_are_wired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(closure_scorecard, "ORPHAN_NO_CHANNEL_CEILING", 5)
    problems = gate_violations(_orphan_report(2))

    # 只减不增的另一半：降下来必须同步收紧上限，否则留出的余量可以被悄悄退回。
    assert any("同步下调为 2" in problem for problem in problems)


def test_gate_passes_only_when_the_ceiling_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(closure_scorecard, "ORPHAN_NO_CHANNEL_CEILING", 2)

    assert gate_violations(_orphan_report(2)) == []


def test_gate_blocks_dangling_refs_and_schema_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(closure_scorecard, "ORPHAN_NO_CHANNEL_CEILING", 0)
    card = _card(
        [_record("Topic/摄影/风光摄影", channel="creator_chip", consumers=("recall",))],
        published={"Topic/摄影/风光摄影"},
    )
    card.dangling_published_refs = {"Topic/不存在的轴/幽灵"}
    card.unknown_channels["telepathy"] = 1
    card.unknown_consumers["vibes"] = 2
    problems = gate_violations(build_report(card))

    assert any("Topic/不存在的轴/幽灵" in problem for problem in problems)
    assert any("collectionChannel=telepathy" in problem for problem in problems)
    assert any("consumedBy=vibes" in problem for problem in problems)


def test_repository_orphan_ratchet_is_not_degraded() -> None:
    report = build_report(collect_scorecard())

    assert gate_violations(report) == [], (
        "标签闭环基线已退化，运行 "
        "`python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard --gate` 查看"
    )


def test_repository_scorecard_is_internally_consistent() -> None:
    report = build_report(collect_scorecard())
    total = report.total

    assert total.defined > 0
    # verified 是三级交集，不可能超过任何单级。
    assert total.verified <= min(total.collectible, total.published, total.consumed)
    assert sum(roll.defined for roll in report.axes.values()) == total.defined
    assert len(report.published_refs) == total.published


def test_repository_publishes_no_dangling_tag_refs() -> None:
    report = build_report(collect_scorecard())

    assert report.dangling_refs == (), (
        f"canonical 发布物引用了 taxonomy 不存在的 tagRef：{report.dangling_refs}"
    )


def test_repository_declares_no_values_outside_schema() -> None:
    report = build_report(collect_scorecard())

    assert report.unknown_channels == {}
    assert report.unknown_consumers == {}
