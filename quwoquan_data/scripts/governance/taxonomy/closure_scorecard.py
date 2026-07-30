"""标签闭环基线：defined / collectible / published / consumed / verified 五级计量。

`stats.py` 回答「定义了多少标签」，本模块回答「这些标签有没有在真实链路上发挥作用」。
两者不重叠：前者是规模，后者是效力。

五级定义直接来自 `schema/governance/_definition.schema.json` 已经写死的语义——
`collectionChannel` 注释「没有采集通道的标签是孤儿：永远不会被打上，也就永远不会参与召回」，
`consumedBy` 注释「采集到但无人消费的标签同样是孤儿」。契约早就把孤儿说清楚了，缺的只是
把它算出来。因此这里刻意不新造判定口径：

  L1 defined     节点存在（`_definition.json`）
  L2 collectible 声明了 `collectionChannel`，即存在把它写到内容/用户上的通道
  L3 published   canonical `publish/posts/**/manifest.json` 的 `tagRefs` 里真实出现过
  L4 consumed    声明了 `consumedBy`，即下游召回/排序/交集/搜索筛选会读它
  L5 verified    L2 ∧ L3 ∧ L4，三者同时成立才算端到端跑通

L3 只认 canonical 发布物，不认 taxonomy 自身的交叉引用（`sameAsRefs`）：标签之间互指
不构成内容供给。L5 用交集而不是加权分，是因为任一级断掉，这个标签对用户就是零价值——
有采集无消费是白采，有消费无供给是空转，三者不可互相补偿。

采集通道与消费方的合法取值从 schema 读取而不是在此复制一份，出现 schema 之外的取值
按 `unknown_*` 单独报出，避免这里变成第二真相源。

用法:
  python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard
  python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard --json
  python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard --axis Topic/摄影
  python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard --gate
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field

from core.paths import CONTROL_PLANE_TAXONOMY_ROOT, PUBLISH_ROOT, SCHEMA_ROOT

TAXONOMY_ROOT = CONTROL_PLANE_TAXONOMY_ROOT
POSTS_ROOT = PUBLISH_ROOT / "posts"
DEFINITION_SCHEMA = SCHEMA_ROOT / "governance" / "_definition.schema.json"

# 商用判定阈值。刻意设成「能证明链路活着」的最低线而不是理想值：这些数字回答的是
# 「标签体系当前能不能支撑商用」，不是「标签体系做得好不好」。
MIN_VERIFIED_TAGS = 1
MIN_PUBLISHED_TAGS = 1
MIN_COLLECTIBLE_RATIO = 0.10

# 孤儿棘轮：没有采集通道的标签数只减不增。商用判定短期内不可能翻绿（verified 需要真实内容供给），
# 所以它挡不住「继续扩定义」这个具体动作；这条线才挡得住——新增一个零采集声明的叶子就会抬高本数。
# 接通一批后必须同步下调，把上限留成余量等于让棘轮失效。
ORPHAN_NO_CHANNEL_CEILING = 1732


@dataclass(frozen=True)
class TagRecord:
    """一个标签节点在五级模型里的落位。"""

    ref: str
    axis: str
    collection_channel: str
    consumed_by: tuple[str, ...]

    @property
    def collectible(self) -> bool:
        return bool(self.collection_channel)

    @property
    def consumed(self) -> bool:
        return bool(self.consumed_by)


@dataclass
class AxisRoll:
    """单条语义轴（group/dimension）上的五级计数。"""

    defined: int = 0
    collectible: int = 0
    published: int = 0
    consumed: int = 0
    verified: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "defined": self.defined,
            "collectible": self.collectible,
            "published": self.published,
            "consumed": self.consumed,
            "verified": self.verified,
        }


@dataclass
class Scorecard:
    """一次扫描的原始事实，判定与汇总都由它派生。"""

    records: list[TagRecord] = field(default_factory=list)
    published_refs: set[str] = field(default_factory=set)
    dangling_published_refs: set[str] = field(default_factory=set)
    post_count: int = 0
    unknown_channels: Counter = field(default_factory=Counter)
    unknown_consumers: Counter = field(default_factory=Counter)


@dataclass(frozen=True)
class Verdict:
    verdict: str
    reasons: tuple[str, ...]
    collectible_ratio: float
    verified_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "collectibleRatio": round(self.collectible_ratio, 4),
            "verifiedRatio": round(self.verified_ratio, 6),
        }


@dataclass(frozen=True)
class Report:
    total: AxisRoll
    axes: dict[str, AxisRoll]
    post_count: int
    published_refs: tuple[str, ...]
    dangling_refs: tuple[str, ...]
    orphans: dict[str, int]
    unknown_channels: dict[str, int]
    unknown_consumers: dict[str, int]
    commercial: Verdict

    def as_dict(self) -> dict[str, object]:
        return {
            "totals": self.total.as_dict(),
            "postCount": self.post_count,
            "distinctPublishedRefs": list(self.published_refs),
            "danglingPublishedRefs": list(self.dangling_refs),
            "orphans": self.orphans,
            "unknownCollectionChannels": self.unknown_channels,
            "unknownConsumers": self.unknown_consumers,
            "axes": {axis: roll.as_dict() for axis, roll in sorted(self.axes.items())},
            "commercial": self.commercial.as_dict(),
        }


def _load_schema_enums() -> tuple[frozenset[str], frozenset[str]]:
    """采集通道与消费方的合法取值以 schema 为唯一真相源。"""
    if not DEFINITION_SCHEMA.exists():
        raise SystemExit(f"[closure-scorecard] 缺少定义 schema：{DEFINITION_SCHEMA}")
    schema = json.loads(DEFINITION_SCHEMA.read_text(encoding="utf-8"))
    properties = schema.get("properties", {})
    channels = properties.get("collectionChannel", {}).get("enum", [])
    consumers = properties.get("consumedBy", {}).get("items", {}).get("enum", [])
    if not channels or not consumers:
        raise SystemExit(
            "[closure-scorecard] schema 未声明 collectionChannel/consumedBy 枚举，无法计量闭环"
        )
    return frozenset(channels), frozenset(consumers)


def _axis_of(ref: str) -> str:
    """语义轴 = group/dimension 两段。单段节点（分组根）以自身为轴。"""
    parts = ref.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else ref


def _collect_published_refs() -> tuple[set[str], int]:
    """canonical 发布物实际使用的 tagRef 与作品数。"""
    refs: set[str] = set()
    posts = 0
    if not POSTS_ROOT.exists():
        return refs, posts
    for manifest_path in sorted(POSTS_ROOT.rglob("manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"[closure-scorecard] 发布清单解析失败 {manifest_path}: {exc}") from exc
        posts += 1
        for ref in manifest.get("tagRefs") or []:
            cleaned = str(ref).strip()
            if cleaned:
                refs.add(cleaned)
    return refs, posts


def collect_scorecard() -> Scorecard:
    known_channels, known_consumers = _load_schema_enums()
    card = Scorecard()
    if not TAXONOMY_ROOT.exists():
        raise SystemExit(f"[closure-scorecard] taxonomy 根不存在：{TAXONOMY_ROOT}")

    defined_refs: set[str] = set()
    for definition_path in sorted(TAXONOMY_ROOT.rglob("_definition.json")):
        ref = definition_path.parent.relative_to(TAXONOMY_ROOT).as_posix()
        try:
            payload = json.loads(definition_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"[closure-scorecard] 标签定义解析失败 {definition_path}: {exc}") from exc

        channel = str(payload.get("collectionChannel") or "").strip()
        if channel and channel not in known_channels:
            card.unknown_channels[channel] += 1
        raw_consumers = payload.get("consumedBy") or []
        consumers: list[str] = []
        for consumer in raw_consumers:
            cleaned = str(consumer).strip()
            if not cleaned:
                continue
            if cleaned not in known_consumers:
                card.unknown_consumers[cleaned] += 1
            consumers.append(cleaned)

        defined_refs.add(ref)
        card.records.append(
            TagRecord(
                ref=ref,
                axis=_axis_of(ref),
                collection_channel=channel,
                consumed_by=tuple(consumers),
            )
        )

    published, post_count = _collect_published_refs()
    card.post_count = post_count
    card.published_refs = published & defined_refs
    # 发布物引用了 taxonomy 里不存在的 ref：这是悬空引用，既不能召回也不能筛选。
    card.dangling_published_refs = published - defined_refs
    return card


def roll_up(card: Scorecard) -> dict[str, AxisRoll]:
    rolls: dict[str, AxisRoll] = {}
    for record in card.records:
        roll = rolls.setdefault(record.axis, AxisRoll())
        roll.defined += 1
        is_published = record.ref in card.published_refs
        if record.collectible:
            roll.collectible += 1
        if is_published:
            roll.published += 1
        if record.consumed:
            roll.consumed += 1
        if record.collectible and record.consumed and is_published:
            roll.verified += 1
    return rolls


def totals(card: Scorecard) -> AxisRoll:
    total = AxisRoll()
    for record in card.records:
        total.defined += 1
        is_published = record.ref in card.published_refs
        if record.collectible:
            total.collectible += 1
        if is_published:
            total.published += 1
        if record.consumed:
            total.consumed += 1
        if record.collectible and record.consumed and is_published:
            total.verified += 1
    return total


def orphan_breakdown(card: Scorecard) -> dict[str, int]:
    """按 schema 自己的孤儿定义拆分。"""
    no_channel = 0
    no_consumer = 0
    declared_unsupplied = 0
    for record in card.records:
        if not record.collectible:
            no_channel += 1
        elif not record.consumed:
            no_consumer += 1
        if record.consumed and record.ref not in card.published_refs:
            declared_unsupplied += 1
    return {
        "no_collection_channel": no_channel,
        "collectible_but_unconsumed": no_consumer,
        "consumed_but_unsupplied": declared_unsupplied,
    }


def commercial_verdict(total: AxisRoll) -> Verdict:
    """商用判定：任一硬性条件不满足即 BLOCK。"""
    reasons: list[str] = []
    collectible_ratio = total.collectible / total.defined if total.defined else 0.0
    verified_ratio = total.verified / total.defined if total.defined else 0.0

    if total.verified < MIN_VERIFIED_TAGS:
        reasons.append(
            f"verified={total.verified} < {MIN_VERIFIED_TAGS}："
            "没有任何标签同时具备采集通道、真实内容供给与消费方，全链路未跑通"
        )
    if total.published < MIN_PUBLISHED_TAGS:
        reasons.append(
            f"published={total.published} < {MIN_PUBLISHED_TAGS}：canonical 内容未使用任何标签"
        )
    if collectible_ratio < MIN_COLLECTIBLE_RATIO:
        reasons.append(
            f"collectible 占比 {collectible_ratio:.1%} < {MIN_COLLECTIBLE_RATIO:.0%}："
            "绝大多数标签没有采集通道，扩定义不会转化为可用信号"
        )

    return Verdict(
        verdict="BLOCK" if reasons else "READY",
        reasons=tuple(reasons),
        collectible_ratio=collectible_ratio,
        verified_ratio=verified_ratio,
    )


def build_report(card: Scorecard) -> Report:
    total = totals(card)
    return Report(
        total=total,
        axes=roll_up(card),
        post_count=card.post_count,
        published_refs=tuple(sorted(card.published_refs)),
        dangling_refs=tuple(sorted(card.dangling_published_refs)),
        orphans=orphan_breakdown(card),
        unknown_channels=dict(card.unknown_channels),
        unknown_consumers=dict(card.unknown_consumers),
        commercial=commercial_verdict(total),
    )


def gate_violations(report: Report) -> list[str]:
    """门禁只校验「不可退化」，不校验「是否达标」。

    达标（verified > 0）取决于内容供给，不是一次代码改动能满足的，写进门禁只会让它长期红着
    然后被绕过。这里挡的是三类确定性退化：孤儿变多、发布物引用不存在的标签、取值漂出 schema。
    """
    problems: list[str] = []
    orphans = report.orphans["no_collection_channel"]
    if orphans > ORPHAN_NO_CHANNEL_CEILING:
        problems.append(
            f"无采集通道的标签 {orphans} > 上限 {ORPHAN_NO_CHANNEL_CEILING}："
            "新增了没有采集通道的标签定义。先给它接采集通道，或不要新增。"
        )
    elif orphans < ORPHAN_NO_CHANNEL_CEILING:
        problems.append(
            f"无采集通道的标签已降到 {orphans}，请把 ORPHAN_NO_CHANNEL_CEILING 同步下调为 {orphans}，"
            "否则棘轮会留出可回退的余量"
        )
    for ref in report.dangling_refs:
        problems.append(f"发布物引用了 taxonomy 中不存在的 tagRef：{ref}")
    for value, count in sorted(report.unknown_channels.items()):
        problems.append(f"collectionChannel={value} 不在 schema 枚举内（{count} 处）")
    for value, count in sorted(report.unknown_consumers.items()):
        problems.append(f"consumedBy={value} 不在 schema 枚举内（{count} 处）")
    return problems


def _run_gate(report: Report) -> None:
    problems = gate_violations(report)
    if problems:
        print("GATE_BLOCK: 标签闭环基线退化")
        for problem in problems:
            print(f"  ✗ {problem}")
        raise SystemExit(1)
    total = report.total
    print(
        "OK: 标签闭环基线未退化"
        f"（defined={total.defined} collectible={total.collectible} "
        f"published={total.published} consumed={total.consumed} verified={total.verified}；"
        f"无采集通道 {report.orphans['no_collection_channel']}）"
    )
    if report.commercial.verdict != "READY":
        print(f"  提示：商用判定仍为 {report.commercial.verdict}，见 OPEN-002")


def _print_text(report: Report, axis_filter: str | None) -> None:
    total = report.total.as_dict()
    defined = report.total.defined or 1

    print("=" * 68)
    print("标签闭环基线  defined / collectible / published / consumed / verified")
    print("=" * 68)
    for level in ("defined", "collectible", "published", "consumed", "verified"):
        count = total[level]
        print(f"  {level:<12} {count:>6}  ({count / defined:6.2%})")

    print(f"\ncanonical 作品数: {report.post_count}")
    print(f"内容实际使用的不同 tagRef: {len(report.published_refs)}")
    for ref in report.published_refs:
        print(f"  · {ref}")
    if report.dangling_refs:
        print(f"\n悬空引用（发布物引用了 taxonomy 不存在的 ref）: {len(report.dangling_refs)}")
        for ref in report.dangling_refs:
            print(f"  ! {ref}")

    print("\n孤儿拆分（口径见 _definition.schema.json）:")
    print(f"  无采集通道                  {report.orphans['no_collection_channel']:>6}")
    print(f"  有采集但无消费方            {report.orphans['collectible_but_unconsumed']:>6}")
    print(f"  有消费声明但零内容供给      {report.orphans['consumed_but_unsupplied']:>6}")

    if report.unknown_channels or report.unknown_consumers:
        print("\nschema 之外的取值（疑似漂移）:")
        for value, count in sorted(report.unknown_channels.items()):
            print(f"  collectionChannel={value} × {count}")
        for value, count in sorted(report.unknown_consumers.items()):
            print(f"  consumedBy={value} × {count}")

    print("\n按语义轴（按 defined 降序；verified>0 的轴标 *）:")
    print(f"  {'轴':<24} {'defined':>8}{'collect':>9}{'publish':>9}{'consume':>9}{'verify':>8}")
    for axis, roll in sorted(report.axes.items(), key=lambda item: -item[1].defined):
        if axis_filter and axis != axis_filter:
            continue
        mark = "*" if roll.verified else " "
        print(
            f"{mark} {axis:<24} {roll.defined:>8}{roll.collectible:>9}"
            f"{roll.published:>9}{roll.consumed:>9}{roll.verified:>8}"
        )

    print(f"\n商用判定: {report.commercial.verdict}")
    for reason in report.commercial.reasons:
        print(f"  ✗ {reason}")
    if not report.commercial.reasons:
        print("  ✓ 五级基线满足商用最低线")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="标签闭环五级基线")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--axis", help="只打印指定语义轴，如 Topic/摄影")
    parser.add_argument("--gate", action="store_true", help="以门禁模式运行：基线退化即非零退出")
    args = parser.parse_args(argv)

    report = build_report(collect_scorecard())
    if args.gate:
        _run_gate(report)
        return
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return
    _print_text(report, args.axis)
