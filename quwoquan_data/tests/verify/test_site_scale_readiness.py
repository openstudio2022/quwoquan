"""Site-dimensional scale readiness gate tests."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="site_scale_readiness_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from site_supply import core as site_core  # noqa: E402
from site_supply import handler as ss  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from verify.site_scale_readiness import build_site_scale_readiness_report  # noqa: E402


ARTICLE_TEXT = (
    "## 交通与入口\n"
    "九寨沟的行前资料覆盖入口动线、景区交通、核心海子、停留节奏、雨天备选和返程时间。"
    "候选正文说明游客通常需要提前确认预约、门票、观光车和开放状态，旺季还要预留排队缓冲。\n"
    "## 门票与时间\n"
    "内容包含路线取舍、时间安排、地点判断、体验反馈和证据映射，适合进入网站供给线评分。"
    "如果是亲子或老人同行，文本提醒控制徒步强度，优先安排沟口住宿和早进沟。\n"
    "## 路线与风险\n"
    "如果遇到降雨或局部封闭，文本建议保留替代节点，并把补给、返程交通和休息点写入计划。"
    "这些信息足够支持内容计划生成，不依赖裸题扩写，也不把平台口吻带入发布稿。"
)


def test_site_supply_source_registry_follows_repo_when_runtime_root_is_sandboxed():
    old = os.environ.get("QWQ_DATA_ROOT")
    os.environ["QWQ_DATA_ROOT"] = str(_TMP / "sandbox_without_verticals")
    try:
        path = site_core._site_registry_path("travel")
    finally:
        if old is None:
            os.environ.pop("QWQ_DATA_ROOT", None)
        else:
            os.environ["QWQ_DATA_ROOT"] = old

    assert path == DATA_ROOT / "verticals" / "travel" / "sources" / "source_registry.yaml"
    assert path.is_file()


def _make_site_batch(
    batch: str,
    *,
    site_id: str = "qunar_guide",
    objects_per_hour: float,
    handoff_article_count: int = 1,
    released_post_refs: list[str] | None = None,
    token_ledger_count: int = 1,
    first_pass_rate: float = 0.82,
    release_verified: bool = True,
    import_verified: bool = True,
    search_visible: bool = True,
    recommendation_feedback_ready: bool = True,
) -> None:
    url = (
        f"https://zh.wikivoyage.org/wiki/{batch}"
        if site_id == "wikivoyage_zh"
        else f"https://touch.travel.qunar.com/travelbook/note/{batch}"
    )
    frontier = ss.build_site_frontier_packet(
        vertical="travel",
        site_id=site_id,
        batch_id=batch,
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id=site_id,
        batch_id=batch,
        url=url,
        lane="article",
        title=f"{batch} 候选",
        published_at="2026-06-01",
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": batch,
            "runtime": {"siteId": site_id, "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    ss.write_site_fetch_packet(fetch, html_bytes=ARTICLE_TEXT.encode("utf-8"))
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id=site_id,
        batch_id=batch,
        url=url,
        lane="article",
        title=f"{batch} 候选",
        text=ARTICLE_TEXT,
        published_at="2026-06-01",
        entity_mentions=["地点/景区/九寨沟"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id=site_id,
        batch_id=batch,
        objects_per_hour=objects_per_hour,
        first_pass_rate=first_pass_rate,
        token_ledger_count=token_ledger_count,
        release_verified=release_verified,
        import_verified=import_verified,
        search_visible=search_visible,
        recommendation_feedback_ready=recommendation_feedback_ready,
    )
    assert rollup["passed"], rollup
    if handoff_article_count != 1:
        rollup["siteFunnel"]["contentPlanHandoffCount"] = handoff_article_count
        rollup["siteFunnel"]["contentPlanHandoffLaneCounts"] = {"article": handoff_article_count}
    ss.write_site_rollup_report(rollup)
    if release_verified:
        refs = released_post_refs
        if refs is None:
            refs = [f"posts/article/攻略/{batch}-release-001"]
        root = ss.site_supply_root("travel", site_id, batch)
        downstream_path = root / "_shared" / "site_supply_downstream_e2e_report.json"
        write_json(
            downstream_path,
            {
                "schemaVersion": "quwoquan_data.site_supply.downstream_e2e/1",
                "vertical": "travel",
                "siteId": site_id,
                "sourceBatchId": batch,
                "taskId": "旅行/主题/网站供给线/规模准出测试",
                "targetBatch": f"{batch}_publish",
                "env": "gamma",
                "postRefs": refs,
                "plannedPostRefs": refs,
                "releasedPostRefs": refs,
                "plannedPostRefCount": len(refs),
                "releasedPostRefCount": len(refs),
                "checks": {
                    "releaseVerified": True,
                    "importVerified": import_verified,
                    "searchVisible": search_visible,
                    "recommendationFeedbackReady": recommendation_feedback_ready,
                },
                "gate": {"passed": True, "blockers": [], "warnings": []},
            },
        )
        write_json(root / "ship_import" / "stage_result.json", {"outputs": [str(downstream_path)]})


def test_site_scale_readiness_passes_with_complete_evidence_within_registered_capacity():
    _make_site_batch("green", objects_per_hour=5000)
    report = build_site_scale_readiness_report(vertical="travel", batch_id="green", daily_target=5_000)
    assert report["passed"], report["blockers"]
    assert report["aggregate"]["siteCount"] == 1
    assert report["aggregate"]["measuredThroughputObjectsPerHour"] == 5000
    assert report["aggregate"]["registeredMaxPagesPerDay"] == 5000
    assert report["requiredThroughputPerHour"] == 208.3333
    assert report["sites"][0]["articleCommercialAdmission"] == "commercial_release"


def test_site_scale_readiness_aggregates_explicit_batches_across_sites():
    _make_site_batch("multi_qunar", site_id="qunar_guide", objects_per_hour=250)
    _make_site_batch("multi_wikivoyage", site_id="wikivoyage_zh", objects_per_hour=250)
    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id="multi_qunar",
        batch_ids=["multi_qunar", "multi_wikivoyage"],
        daily_target=10_000,
    )
    assert report["passed"], report["blockers"]
    assert report["batchIds"] == ["multi_qunar", "multi_wikivoyage"]
    assert report["aggregate"]["siteCount"] == 2
    assert report["aggregate"]["registeredMaxPagesPerDay"] == 10_000
    assert report["aggregate"]["measuredThroughputObjectsPerHour"] == 500


def test_site_scale_readiness_blocks_daily_target_above_registered_site_capacity():
    _make_site_batch("over_capacity", objects_per_hour=5000)
    report = build_site_scale_readiness_report(vertical="travel", batch_id="over_capacity", daily_target=100_000)
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "requested dailyTarget 100000 exceeds registered raw crawl capacity 5000 maxPagesPerDay" in text


def test_site_scale_readiness_commercial_minimums_use_released_posts_not_handoff():
    _make_site_batch(
        "commercial_release_shortfall",
        objects_per_hour=500,
        handoff_article_count=10,
        released_post_refs=[
            "posts/article/攻略/九寨沟-001",
            "posts/article/攻略/九寨沟-002",
            "posts/article/攻略/九寨沟-003",
            "posts/article/攻略/九寨沟-004",
        ],
    )
    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id="commercial_release_shortfall",
        daily_target=1_000,
        mode="commercial",
        min_lane_counts={"article": 5},
    )
    blockers = "\n".join(report["blockers"])
    assert not report["passed"]
    assert report["aggregate"]["contentPlanHandoffLaneCounts"]["article"] == 10
    assert report["aggregate"]["releasedPostLaneCounts"]["article"] == 4
    assert "releasedPostLaneCounts.article 4 < required 5" in blockers


def test_site_scale_readiness_reads_downstream_report_checks_from_stage_outputs():
    _make_site_batch("downstream_only", objects_per_hour=500)
    root = ss.site_supply_root("travel", "qunar_guide", "downstream_only")
    rollup_path = root / "_shared" / "site_rollup_report.json"
    rollup = read_json(rollup_path)
    rollup["executionReadiness"]["releaseVerified"] = False
    rollup["executionReadiness"]["importVerified"] = False
    rollup["executionReadiness"]["searchVisible"] = False
    rollup["executionReadiness"]["recommendationFeedbackReady"] = False
    write_json(rollup_path, rollup)

    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id="downstream_only",
        daily_target=1_000,
        mode="commercial",
    )
    assert report["passed"], report["blockers"]
    site = report["sites"][0]
    assert site["releaseVerified"] is True
    assert site["importVerified"] is True
    assert site["searchVisible"] is True
    assert site["recommendationFeedbackReady"] is True
    assert site["downstreamE2E"]["reportPaths"]


def test_site_scale_readiness_blocks_low_throughput_and_missing_e2e():
    _make_site_batch(
        "blocked",
        objects_per_hour=100,
        token_ledger_count=0,
        release_verified=False,
        import_verified=False,
        search_visible=False,
        recommendation_feedback_ready=False,
    )
    report = build_site_scale_readiness_report(vertical="travel", batch_id="blocked", daily_target=100_000)
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "TokenLedger evidence missing" in text
    assert "release verification evidence missing" in text
    assert "import evidence missing" in text
    assert "search visibility evidence missing" in text
    assert "recommendation feedback evidence missing" in text
    assert "measured site throughput 100.0000 objects/hour < required 4166.6667 objects/hour" in text


def test_site_scale_readiness_trial_mode_allows_missing_commercial_e2e_but_warns():
    _make_site_batch(
        "trial_mode",
        objects_per_hour=500,
        release_verified=False,
        import_verified=False,
        search_visible=False,
        recommendation_feedback_ready=False,
    )
    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id="trial_mode",
        daily_target=1_000,
        mode="trial",
    )
    assert report["passed"], report["blockers"]
    warnings = "\n".join(report["warnings"])
    assert "trial mode: release verification evidence missing" in warnings
    assert "trial mode: search visibility evidence missing" in warnings


def test_site_scale_readiness_commercial_mode_requires_e2e_evidence():
    _make_site_batch(
        "commercial_missing",
        objects_per_hour=500,
        release_verified=False,
        import_verified=False,
        search_visible=False,
        recommendation_feedback_ready=False,
    )
    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id="commercial_missing",
        daily_target=1_000,
        mode="commercial",
    )
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "release verification evidence missing" in text
    assert "recommendation feedback evidence missing" in text


def test_site_scale_readiness_requires_site_rollup():
    report = build_site_scale_readiness_report(vertical="travel", batch_id="missing", daily_target=100_000)
    assert not report["passed"]
    assert "no site_supply rollup found" in "\n".join(report["blockers"])


def test_site_scale_readiness_stops_at_frontier_when_source_is_not_crawl_allowed():
    batch = "frontier_blocked"
    frontier = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id=batch,
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)

    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id=batch,
        daily_target=10_000,
        mode="trial",
    )
    blockers = "\n".join(report["blockers"])
    warnings = "\n".join(report["warnings"])
    assert not report["passed"]
    assert "ctrip_travelogue: site_frontier gate did not pass" in blockers
    assert "fetchable=false sites cannot enter batch site crawl" in blockers
    assert "measured site throughput" not in blockers
    assert "no content_plan handoff" not in blockers
    assert "TokenLedger evidence missing" not in blockers
    assert "downstream scale readiness was not evaluated" in warnings


def test_site_scale_readiness_accepts_controlled_trial_lane_minimums():
    batch = "controlled_lane_minimums"
    frontier = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id=batch,
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
        admission_mode="controlled_trial",
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    for lane, count in {"article": 5, "image": 2, "video": 1}.items():
        for idx in range(1, count + 1):
            url = f"https://you.ctrip.com/site-trial/{lane}/{idx:03d}.html"
            assets = []
            if lane in {"image", "video"}:
                assets = [{
                    "assetId": f"{lane}_{idx}",
                    "url": f"{url}#asset",
                    "license": "validation_only_not_for_publish",
                    "credit": "携程攻略 controlled trial",
                    "sourceUrl": url,
                    "termsUrl": "https://pages.ctrip.com/webhome/purehtml/cn/memberCenter/regTerm.html",
                    "usageScope": "site_supply_controlled_trial_only",
                    "modelReleaseStatus": "not_required",
                }]
            candidate = ss.build_site_candidate_packet(
                vertical="travel",
                site_id="ctrip_travelogue",
                batch_id=batch,
                url=url,
                lane=lane,
                title=f"{lane} controlled {idx}",
                text=ARTICLE_TEXT if lane == "article" else "",
                published_at="2026-06-01",
                assets=assets,
                entity_mentions=["地点/景区/九寨沟"],
            )
            assert candidate["gate"]["passed"], candidate["gate"]
            ss.write_site_candidate_packet(candidate)
            score = ss.build_site_score_packet(candidate)
            assert score["productionEligible"], score
            ss.write_site_score_packet(score)
            mapped = ss.build_site_map_packet(candidate, score)
            assert mapped["gate"]["passed"], mapped
            ss.write_site_map_packet(mapped)
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id=batch,
        objects_per_hour=500,
        first_pass_rate=0.82,
        token_ledger_count=8,
    )
    assert rollup["passed"], rollup
    ss.write_site_rollup_report(rollup)

    report = build_site_scale_readiness_report(
        vertical="travel",
        batch_id=batch,
        daily_target=1_000,
        mode="trial",
        min_lane_counts={"article": 5, "image": 2, "video": 1},
    )
    assert report["passed"], report["blockers"]
    assert report["aggregate"]["contentPlanHandoffLaneCounts"] == {"article": 5, "image": 2, "video": 1}

    blocked = build_site_scale_readiness_report(
        vertical="travel",
        batch_id=batch,
        daily_target=1_000,
        mode="trial",
        min_lane_counts={"article": 6, "image": 2, "video": 1},
    )
    assert not blocked["passed"]
    assert "contentPlanHandoffLaneCounts.article 5 < required 6" in "\n".join(blocked["blockers"])


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
