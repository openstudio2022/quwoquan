"""handoff packet 与出口门 contract tests（single ref gate + batch reducer gate）。

可直接运行：python3 quwoquan_data/tests/local_contract/common/test_handoff__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common import handoff  # noqa: E402


def test_author_job_packet_isolation_and_exit_gates():
    brief = {"writingIntent": "planning_consultation", "baseSourceRef": "sources/a.md", "carrier": "article"}
    pack = {
        "title": "三沟联线攻略",
        "assets": [{"assetId": "a1", "entityName": "神山", "imageLayout": "inline"}],
        "mustIncludeFacts": ["海拔3800m"],
        "bannedRegisterTerms": ["看展"],
    }
    packet = handoff.build_author_job_packet(ref="r1", brief=brief, writing_pack=pack, prompt_rel="4.draft/prompt.md")
    assert packet["schemaVersion"] == "quwoquan_data.author_job_packet"
    assert packet["ref"] == "r1"
    assert packet["writingIntent"] == "planning_consultation"
    assert packet["baseSourceRef"] == "sources/a.md"
    assert "single-ref" in packet["isolation"]
    assert "imageReferenceClosure" in packet["exitGates"]
    assert packet["assets"][0]["assetId"] == "a1"
    # 执行合约 5 要素必须随 packet 下发
    assert handoff.execution_contract_issues(packet.get("executionContract")) == []
    assert "5.review/repair_report.json" in packet["executionContract"]["inputs"]


def test_image_author_job_packet_is_compact_and_image_scoped():
    brief = {"carrier": "image", "titleHint": "湖面晨光"}
    pack = {
        "title": "湖面晨光",
        "carrier": "image",
        "creativeBrief": {"readerPromise": "看清这一组图的光线重点"},
        "captionPolicy": {"titleMaxChars": 80, "captionMaxChars": 300},
        "sourcePaths": ["sources/image/source.md"],
        "assets": [
            {
                "assetId": "img1",
                "caption": "晨光照在湖面",
                "sourceCollectionId": "collection-a",
                "creator": "摄影师",
                "license": "CC BY 4.0",
            }
        ],
    }
    packet = handoff.build_author_job_packet(ref="r_img", brief=brief, writing_pack=pack, prompt_rel="4.draft/prompt.md")
    assert packet["schemaVersion"] == "quwoquan_data.author_job_packet"
    assert packet["captionPolicy"]["captionMaxChars"] == 300
    assert "imageGate" in packet["exitGates"]
    assert "writingIntentConsistency" not in packet["exitGates"]
    assert packet["executionContract"]["budget"]["maxWallClockSeconds"] == 420
    assert "3.compose/writing_pack.json" not in packet["executionContract"]["inputs"]


def test_execution_contract_requires_five_elements():
    # 完整合约通过
    ok = handoff.build_execution_contract()
    assert handoff.execution_contract_issues(ok) == []
    assert "read_ref_packet" in ok["permissions"]  # 最小工具集 allow-list
    # 缺任一要素即拦截
    for key in handoff.EXECUTION_CONTRACT_KEYS:
        broken = dict(ok)
        broken[key] = [] if key != "budget" else {}
        assert handoff.execution_contract_issues(broken), f"missing {key} must be flagged"
    assert handoff.execution_contract_issues(None) == ["executionContract: missing"]


def test_ref_review_gate_blocks_without_self_check():
    gate = handoff.build_ref_review_gate(
        ref="r1",
        article="# 攻略\n\n第一步：到成都。第二步：转车。注意事项：高反。 asset://a1",
        writing_intent="planning_consultation",
        assets=[{"assetId": "a1"}],
        carrier="article",
        route_node_count=0,
        banned_register_terms=[],
        cited_source_refs=["s/1"],
        reject_source_refs=[],
        self_check_present=False,
        review_decision="approved",
    )
    assert gate["passed"] is False
    assert any("self_check" in i for i in gate["issues"])


def test_ref_review_gate_pass():
    gate = handoff.build_ref_review_gate(
        ref="r1",
        article="# 攻略\n\n先到成都再转车，行程顺序清晰。怎么去：自驾或大巴均可。门票需提前预约，开放时间有限。建议避开旺季，注意高反。 asset://a1",
        writing_intent="planning_consultation",
        assets=[{"assetId": "a1"}],
        carrier="article",
        route_node_count=0,
        banned_register_terms=[],
        cited_source_refs=["s/1"],
        reject_source_refs=["s/9"],
        self_check_present=True,
        review_decision="approved",
    )
    assert gate["passed"] is True, gate["issues"]


def test_batch_reducer_flags_source_reuse():
    payload = [
        {"ref": "r1", "article": "独特的过程体验一二三四五。 asset://a1", "writingIntent": "decision_experience", "baseSourceRef": "sources/shared.md"},
        {"ref": "r2", "article": "完全不同的攻略步骤与顺序。 asset://a2", "writingIntent": "planning_consultation", "baseSourceRef": "sources/shared.md"},
    ]
    gate = handoff.build_batch_reducer_gate(payload)
    assert gate["passed"] is False
    assert "sources/shared.md" in gate["sourceReuse"]
    assert set(gate["affectedRefs"]) == {"r1", "r2"}
    assert gate["intentDistribution"]["decision_experience"] == 1


def test_batch_reducer_passes_for_distinct_refs():
    payload = [
        {"ref": "r1", "article": "先坐车到景区，再步行上山，最后回城。 asset://a1", "writingIntent": "planning_consultation", "baseSourceRef": "sources/a.md"},
        {"ref": "r2", "article": "上午走老街，下午看博物馆，傍晚吃完再回酒店。 asset://a2", "writingIntent": "post_trip_journal", "baseSourceRef": "sources/b.md"},
    ]
    gate = handoff.build_batch_reducer_gate(payload)
    assert gate["passed"] is True, gate["issues"]
    assert gate["affectedRefs"] == []


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"handoff tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
