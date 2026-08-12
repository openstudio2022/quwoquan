"""handoff packet 与出口门 contract tests（single ref gate + batch reducer gate）。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_handoff__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.execution.controller.execute import handoff
from core.runtime_policy import active_runtime_policy  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

ARTICLE_EXECUTION_ID = "20260711--travel-article-handoff--test-region-a--pilot-902"
IMAGE_EXECUTION_ID = "20260711--travel-image-handoff--test-region-a--pilot-902"


def _stub_execution_model(monkeypatch) -> None:
    monkeypatch.setattr(
        handoff,
        "execution_model_pair_for_execution",
        lambda _execution_id: SimpleNamespace(
            author=SimpleNamespace(
                provider=SimpleNamespace(value="cursor_sdk"),
                model_id="composer",
            )
        ),
    )


def test_author_job_packet_isolation_and_exit_gates(monkeypatch):
    _stub_execution_model(monkeypatch)
    build_execution_fixture(ARTICLE_EXECUTION_ID)
    brief = {"writingIntent": "planning_consultation", "baseSourceRef": "sources/a.md", "carrier": "article"}
    pack = {
        "title": "三沟联线攻略",
        "assets": [{"assetId": "a1", "entityName": "神山", "imageLayout": "inline"}],
        "mustIncludeFacts": ["海拔3800m"],
        "bannedRegisterTerms": ["看展"],
    }
    packet = handoff.build_author_job_packet(
        execution_id=ARTICLE_EXECUTION_ID,
        ref="r1",
        brief=brief,
        writing_pack=pack,
        prompt_rel="4.draft/prompt.md",
    )
    assert packet["schema"] == "quwoquan_data.author_job_packet"
    assert packet["ref"] == "r1"
    assert packet["writingIntent"] == "planning_consultation"
    assert packet["baseSourceRef"] == "sources/a.md"
    assert "single-ref" in packet["isolation"]
    assert "imageReferenceClosure" in packet["exitGates"]
    assert packet["assets"][0]["assetId"] == "a1"
    # 执行合约 5 要素必须随 packet 下发
    assert handoff.execution_contract_issues(packet.get("executionContract")) == []
    assert "5.review/repair_report.json" in packet["executionContract"]["inputs"]


def test_image_author_job_packet_is_compact_and_image_scoped(monkeypatch):
    _stub_execution_model(monkeypatch)
    build_execution_fixture(IMAGE_EXECUTION_ID)
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
    packet = handoff.build_author_job_packet(
        execution_id=IMAGE_EXECUTION_ID,
        ref="r_img",
        brief=brief,
        writing_pack=pack,
        prompt_rel="4.draft/prompt.md",
    )
    assert packet["schema"] == "quwoquan_data.author_job_packet"
    assert packet["captionPolicy"]["captionMaxChars"] == 300
    assert "imageGate" in packet["exitGates"]
    assert "writingIntentConsistency" not in packet["exitGates"]
    assert (
        packet["executionContract"]["budget"]["maxWallClockSeconds"]
        == active_runtime_policy().queue_max_wall_clock_seconds
    )
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
        {"ref": "r1", "article": "独特的过程体验一二三四五。 asset://a1", "writingIntent": "decision_experience", "baseSourceRef": "sources/shared.md", "articleMediaMode": "illustrated", "articleMediaIssue": ""},
        {"ref": "r2", "article": "完全不同的攻略步骤与顺序。 asset://a2", "writingIntent": "planning_consultation", "baseSourceRef": "sources/shared.md", "articleMediaMode": "illustrated", "articleMediaIssue": ""},
    ]
    gate = handoff.build_execution_reducer_gate(payload)
    assert gate["passed"] is False
    assert "sources/shared.md" in gate["sourceReuse"]
    assert set(gate["affectedRefs"]) == {"r1", "r2"}
    assert gate["intentDistribution"]["decision_experience"] == 1


def test_batch_reducer_passes_for_distinct_refs():
    payload = [
        {"ref": "r1", "article": "先坐车到景区，再步行上山，最后回城。 asset://a1", "writingIntent": "planning_consultation", "baseSourceRef": "sources/a.md", "articleMediaMode": "illustrated", "articleMediaIssue": ""},
        {"ref": "r2", "article": "上午走老街，下午看博物馆，傍晚吃完再回酒店。 asset://a2", "writingIntent": "post_trip_journal", "baseSourceRef": "sources/b.md", "articleMediaMode": "illustrated", "articleMediaIssue": ""},
    ]
    gate = handoff.build_execution_reducer_gate(payload)
    assert gate["passed"] is True, gate["issues"]
    assert gate["affectedRefs"] == []


def test_batch_reducer_reports_typed_article_media_coverage_without_blocking(
    monkeypatch,
):
    monkeypatch.setattr(
        handoff.qg,
        "skeleton_similarity_issues",
        lambda _article, _peers: [],
    )
    payload = [
        {
            "ref": f"illustrated-{index}",
            "article": f"独立正文 {index}",
            "writingIntent": "planning_consultation",
            "baseSourceRef": f"sources/{index}/source.md",
            "articleMediaMode": "illustrated",
            "articleMediaIssue": "",
        }
        for index in range(9)
    ]
    payload.append(
        {
            "ref": "text-only-allowed",
            "article": "纯文字正文",
            "writingIntent": "post_trip_journal",
            "baseSourceRef": "sources/text/source.md",
            "articleMediaMode": "text_only",
            "articleMediaIssue": "",
        }
    )
    passed = handoff.build_execution_reducer_gate(payload)
    assert passed["passed"] is True
    assert passed["imageCoverage"]["illustratedRate"] == 0.9
    assert passed["imageCoverage"]["textOnlyRate"] == 0.1

    payload.append(
        {
            "ref": "text-only-excess",
            "article": "另一篇纯文字正文",
            "writingIntent": "decision_experience",
            "baseSourceRef": "sources/text-two/source.md",
            "articleMediaMode": "text_only",
            "articleMediaIssue": "",
        }
    )
    reported = handoff.build_execution_reducer_gate(payload)
    assert reported["passed"] is True
    assert reported["affectedRefs"] == []
    assert reported["imageCoverage"] == {
        "articleCount": 11,
        "illustratedCount": 9,
        "textOnlyCount": 2,
        "illustratedRate": 0.818182,
        "textOnlyRate": 0.181818,
        "modesByRef": {
            **{f"illustrated-{index}": "illustrated" for index in range(9)},
            "text-only-allowed": "text_only",
            "text-only-excess": "text_only",
        },
    }


def test_batch_reducer_rejects_missing_typed_article_media_closure():
    gate = handoff.build_execution_reducer_gate(
        [
            {
                "ref": "missing-media",
                "article": "正文",
                "writingIntent": "planning_consultation",
                "baseSourceRef": "sources/base/source.md",
                "articleMediaMode": "",
                "articleMediaIssue": "mediaClosure is missing",
            }
        ]
    )
    assert gate["passed"] is False
    assert gate["affectedRefs"] == ["missing-media"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"handoff tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
