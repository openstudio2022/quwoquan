"""Site-dimensional content supply packet/gate contract tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="site_supply_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from site_supply import handler as ss  # noqa: E402


def _cli_env() -> dict[str, str]:
    """site-supply CLI 子进程的显式环境。

    DATA_ROOT 必须指向真实仓库（读 verticals/<v>/sources/source_registry.yaml），
    运行态/发布/committed 根隔离到本测试 tmp。必须显式构造而非继承全局
    os.environ：同一 pytest 进程内其他测试模块（如 test_task_run_pipeline）会在
    import 时把 QWQ_DATA_ROOT 指向各自 tmp，子进程若继承该污染值会在错误的 tmp
    下找不到 source_registry.yaml。
    """
    env = dict(os.environ)
    env["QWQ_DATA_ROOT"] = str(DATA_ROOT)
    env["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
    env["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
    env["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
    return env


ARTICLE_TEXT = (
    "九寨沟两日深度玩法实测：第一天走树正沟，第二天主攻日则沟，节奏从容不赶路。\n\n"
    "## 交通与门票\n"
    "旺季门票169元、观光车90元；从成都出发约8小时车程，建议清晨发车避开拥堵。\n\n"
    "## 核心海子与体验\n"
    "五花海、诺日朗瀑布、长海色彩层次分明，海拔约2000米需注意高反与保暖；"
    "栈道单程约5公里，留足拍摄时间，最打动人的是清晨无人的镜海倒影。\n\n"
    "## 实用提醒\n"
    "景区内禁止无人机，山区午后多阵雨，雨衣比雨伞更实用，全程信息便于规划行程。"
)
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfeA\x82\xa9\x99\x00\x00\x00\x00IEND\xaeB`\x82"
)
TEST_COMMITTED_TASK_ID = "旅行/网站供给线/维基导游/真实运营试跑"


def _write_frontier(batch: str = "b1") -> dict:
    packet = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_frontier_packet(packet)
    return packet


def _write_candidate(batch: str = "b1") -> dict:
    _write_frontier(batch)
    packet = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/123456",
        lane="article",
        title="九寨沟两日玩法",
        text=ARTICLE_TEXT,
        published_at="2026-06-01",
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_candidate_packet(packet)
    return packet


def test_qunar_frontier_passes_and_ctrip_is_blocked():
    qunar = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="frontier_ok",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert qunar["gate"]["passed"], qunar["gate"]
    assert qunar["profile"]["crawlAllowed"] is True
    assert qunar["queuePolicy"]["backend"] == "reliabletask"

    wikivoyage = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="frontier_ok_wikivoyage",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert wikivoyage["gate"]["passed"], wikivoyage["gate"]
    assert wikivoyage["profile"]["crawlAllowed"] is True
    assert wikivoyage["profile"]["extractor"] == "wikipedia_api"

    ctrip = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id="frontier_block",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not ctrip["gate"]["passed"]
    assert ctrip["profile"]["maxDepth"] == 0
    text = "\n".join(ctrip["gate"]["blockers"])
    warning_text = "\n".join(ctrip["gate"]["warnings"])
    assert "fetchable=false" in text
    assert "crawlAllowed" in text
    assert "maxPagesPerDay=0" in warning_text

    mafengwo = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="mafengwo_travelogue",
        batch_id="frontier_block_mafengwo",
        daily_target=100_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not mafengwo["gate"]["passed"]
    assert mafengwo["profile"]["rawProfilePresent"] is True
    assert mafengwo["profile"]["maxDepth"] == 0
    mafengwo_text = "\n".join(mafengwo["gate"]["blockers"])
    mafengwo_warning_text = "\n".join(mafengwo["gate"]["warnings"])
    assert "fetchable=false" in mafengwo_text
    assert "crawlAllowed" in mafengwo_text
    assert "maxPagesPerDay=0" in mafengwo_warning_text


def test_ctrip_mafengwo_controlled_trial_frontier_passes_without_batch_crawl():
    for site_id in ("ctrip_travelogue", "mafengwo_travelogue"):
        packet = ss.build_site_frontier_packet(
            vertical="travel",
            site_id=site_id,
            batch_id=f"{site_id}_controlled",
            daily_target=10_000,
            queue_backend="reliabletask",
            end_date="2026-06-19",
            admission_mode="controlled_trial",
        )
        assert packet["gate"]["passed"], packet["gate"]
        assert packet["admissionMode"] == "controlled_trial"
        assert packet["profile"]["fetchable"] is False
        assert packet["profile"]["crawlAllowed"] is False
        assert packet["profile"]["controlledTrial"]["validationOnly"] is True
        warning_text = "\n".join(packet["gate"]["warnings"])
        assert "does not grant raw batch crawl" in warning_text


def test_photography_platform_frontier_blocks_raw_crawl_but_allows_controlled_trial():
    for site_id, rights_policy in (("pinterest", "discovery_only"), ("tuchong", "licensed_candidate")):
        blocked = ss.build_site_frontier_packet(
            vertical="photography",
            site_id=site_id,
            batch_id=f"{site_id}_raw_block",
            daily_target=10_000,
            queue_backend="reliabletask",
            end_date="2026-06-19",
        )
        assert not blocked["gate"]["passed"], blocked["gate"]
        assert blocked["profile"]["fetchable"] is False
        assert blocked["profile"]["crawlAllowed"] is False
        assert blocked["profile"]["rightsPolicy"] == rights_policy
        text = "\n".join(blocked["gate"]["blockers"])
        assert "fetchable=false" in text
        assert "crawlAllowed" in text

        trial = ss.build_site_frontier_packet(
            vertical="photography",
            site_id=site_id,
            batch_id=f"{site_id}_trial_ok",
            daily_target=10_000,
            queue_backend="reliabletask",
            end_date="2026-06-19",
            admission_mode="controlled_trial",
        )
        assert trial["gate"]["passed"], trial["gate"]
        assert trial["admissionMode"] == "controlled_trial"
        assert trial["profile"]["controlledTrial"]["validationOnly"] is True
        assert trial["profile"]["controlledTrial"]["publishableAssetsAllowed"] is False
        warning_text = "\n".join(trial["gate"]["warnings"])
        assert "does not grant raw batch crawl" in warning_text


def test_trial_command_materializes_multi_lane_controlled_batch_for_ctrip():
    cli = SCRIPTS_ROOT / "cli.py"
    trial = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "trial",
            "--site-id",
            "ctrip_travelogue",
            "--batch",
            "ctrip_multi_lane",
            "--target-count",
            "8",
            "--article-count",
            "5",
            "--image-count",
            "2",
            "--video-count",
            "1",
            "--daily-target",
            "1000",
            "--objects-per-hour",
            "120",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_env(),
    )
    assert trial.returncode == 0, trial.stderr
    payload = json.loads(trial.stdout)
    assert payload["frontier"]["admissionMode"] == "controlled_trial"
    assert payload["siteFunnel"]["candidateCount"] == 8
    assert payload["siteFunnel"]["laneCounts"] == {"article": 5, "image": 2, "video": 1}
    assert payload["siteFunnel"]["contentPlanHandoffLaneCounts"] == {"article": 5, "image": 2, "video": 1}


def test_candidate_score_map_rollup_handoff_isolated_from_entity_runtime():
    candidate = _write_candidate("pipeline_ok")
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["contentPlanHandoff"]["eligible"], mapped
    assert mapped["semanticMentions"]["state"] == "mention_only"
    assert mapped["knowledgeGaps"]["entityHomepageCandidates"] == ["地点/景区/九寨沟"]
    assert mapped["contentPlanHandoff"]["oneSourceOneWork"] is True
    ss.write_site_map_packet(mapped)

    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="pipeline_ok",
        objects_per_hour=5000,
        first_pass_rate=0.82,
        token_ledger_count=1,
        release_verified=True,
        import_verified=True,
        search_visible=True,
        recommendation_feedback_ready=True,
    )
    assert rollup["passed"], rollup
    assert rollup["siteFunnel"]["contentPlanHandoffCount"] == 1
    path = ss.write_site_rollup_report(rollup)
    assert "/site_supply/travel/qunar_guide/pipeline_ok/" in str(path)
    assert "/runtime/tasks/" not in str(path)
    for name in ("stage_result.json", "gate_report.json", "repair_report.json"):
        assert (path.parents[1] / "candidates" / candidate["candidateRef"] / name).is_file()
        assert (path.parents[1] / "scores" / candidate["candidateRef"] / name).is_file()
        assert (path.parents[1] / "map" / candidate["candidateRef"] / name).is_file()


def test_quality_distribution_report_separates_quality_from_commercial_rights():
    candidate = _write_candidate("quality_distribution_ok")
    score = ss.build_site_score_packet(candidate)
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    ss.write_site_map_packet(mapped)

    report = ss.build_site_quality_distribution_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="quality_distribution_ok",
    )
    assert report["gate"]["passed"], report
    assert report["qualityFunnel"]["candidateCount"] == 1
    assert report["qualityFunnel"]["successRate"] == 1.0
    assert sum(report["qualityDistribution"]["buckets"].values()) == 1
    assert report["qualityDistribution"]["buckets"]["marginal"] == 1
    assert report["commercialReadiness"]["ready"] is True
    path = ss.write_site_quality_distribution_report(report)
    assert path.name == "site_quality_distribution_report.json"
    assert (path.parents[1] / "quality_distribution" / "stage_result.json").is_file()


def test_site_map_keeps_unverified_titles_out_of_entity_homepage_gaps():
    packet = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="topic_title_not_entity_gap",
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_frontier_packet(packet)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="topic_title_not_entity_gap",
        url="https://zh.wikivoyage.org/wiki/K-pop",
        lane="article",
        title="K-pop",
        text=ARTICLE_TEXT * 8,
        published_at="2026-06-01",
        entity_mentions=["K-pop"],
        tag_mentions=["Topic/旅行/目的地指南"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    assert mapped["contentPlanHandoff"]["eligible"] is True
    assert mapped["knowledgeGaps"]["entityHomepageCandidates"] == []
    assert mapped["knowledgeGaps"]["unresolvedEntityMentions"] == ["K-pop"]
    assert mapped["knowledgeGaps"]["topicCandidates"] == ["K-pop"]
    assert "unverified entity mentions" in "\n".join(mapped["gate"]["warnings"])


def test_quality_distribution_marks_controlled_image_trial_not_publishable():
    batch = "quality_distribution_image_trial"
    frontier = ss.build_site_frontier_packet(
        vertical="photography",
        site_id="tuchong",
        batch_id=batch,
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
        admission_mode="controlled_trial",
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    url = ss._trial_url(frontier["profile"], batch_id=batch, lane="image", index=1)
    candidate = ss.build_site_candidate_packet(
        vertical="photography",
        site_id="tuchong",
        batch_id=batch,
        url=url,
        lane="image",
        title="图虫受控图片试跑候选",
        published_at="2026-06-19",
        assets=ss._trial_assets(frontier["profile"], url=url, lane="image", index=1),
        entity_mentions=["地点/景区/结构试跑景区000001"],
        tag_mentions=["Topic/摄影/旅行影像"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_quality_distribution_report(
        vertical="photography",
        site_id="tuchong",
        batch_id=batch,
    )
    assert report["gate"]["passed"], report
    assert report["qualityDistribution"]["buckets"]["acceptable"] == 1
    assert report["commercialReadiness"]["ready"] is False
    text = "\n".join(report["commercialReadiness"]["blockers"])
    assert "controlledTrial.validationOnly=true" in text
    assert "publishableAssetsAllowed=false" in text


def test_rollup_blocks_missing_score_before_downstream_handoff():
    candidate = _write_candidate("missing_score")
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="missing_score",
        objects_per_hour=500,
        first_pass_rate=0.82,
        token_ledger_count=1,
    )
    text = "\n".join(rollup["blockers"])
    assert not rollup["passed"]
    assert f"{candidate['candidateRef']}: missing site_score_packet" in text
    assert rollup["siteFunnel"]["stageFailures"]["missing_score"] == 1


def test_rollup_blocks_missing_map_for_production_eligible_score():
    candidate = _write_candidate("missing_map")
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="missing_map",
        objects_per_hour=500,
        first_pass_rate=0.82,
        token_ledger_count=1,
    )
    text = "\n".join(rollup["blockers"])
    assert not rollup["passed"]
    assert f"{candidate['candidateRef']}: missing site_map_packet" in text
    assert rollup["siteFunnel"]["stageFailures"]["missing_map"] == 1


def test_rollup_treats_score_rejection_as_funnel_block_not_site_blocker():
    candidate = _write_candidate("score_rejected")
    score = ss.build_site_score_packet(candidate, duplicate=True)
    assert not score["productionEligible"], score
    ss.write_site_score_packet(score)
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="score_rejected",
        objects_per_hour=500,
        first_pass_rate=0.0,
        token_ledger_count=1,
    )
    assert rollup["passed"], rollup
    assert rollup["siteFunnel"]["stageFailures"]["site_score"] == 1
    assert rollup["siteFunnel"]["blockedCount"] == 1
    assert "site_score gate failed" not in "\n".join(rollup["blockers"])


def test_fetch_stability_classification_does_not_treat_short_text_as_empty_extract():
    packet = {
        "fetch": {"statusCode": 200},
        "gate": {"blockers": ["fetch extracted text is too short (<600 chars)"]},
    }
    assert ss._classify_fetch_packet(packet) == (0, 0, 0, 0)


def test_rollup_blocks_when_handoff_count_is_below_frontier_target():
    candidate = _write_candidate("target_count_miss")
    frontier = ss._frontier_packet("travel", "qunar_guide", "target_count_miss")
    frontier["frontier"]["targetCount"] = 2
    ss.write_site_frontier_packet(frontier)
    score = ss.build_site_score_packet(candidate)
    assert score["productionEligible"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)
    rollup = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="target_count_miss",
        objects_per_hour=500,
        first_pass_rate=1.0,
        token_ledger_count=1,
    )
    assert not rollup["passed"]
    assert "contentPlanHandoffCount 1 < targetCount 2" in "\n".join(rollup["blockers"])


def test_candidate_outside_frontier_domain_is_blocked():
    _write_frontier("bad_domain")
    packet = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="bad_domain",
        url="https://example.com/travelbook/note/123456",
        lane="article",
        title="越界候选",
        text=ARTICLE_TEXT,
        published_at="2026-06-01",
    )
    assert not packet["gate"]["passed"]
    assert "outside site frontier" in "\n".join(packet["gate"]["blockers"])
    score = ss.build_site_score_packet(packet)
    assert not score["productionEligible"]
    assert "candidate gate did not pass" in "\n".join(score["gate"]["blockers"])


def test_site_score_blocks_non_travel_article_topics():
    packet = {
        "schemaVersion": ss.CANDIDATE_SCHEMA,
        "vertical": "travel",
        "siteId": "wikivoyage_zh",
        "batchId": "travel_relevance_gate",
        "candidateRef": "candidate_kpop_topic",
        "canonicalUrl": "https://zh.wikivoyage.org/wiki/K-pop",
        "lane": "article",
        "source": {
            "platform": "维基导游",
            "rightsPolicy": "factual_citation_only",
            "validationOnly": False,
        },
        "title": "K-pop",
        "text": "K-pop 是一种流行音乐文化。" * 120,
        "assets": [],
        "publishedAt": "2026-06-01",
        "gate": {"passed": True},
    }

    score = ss.build_site_score_packet(packet)

    assert not score["productionEligible"]
    assert not score["verticalRelevance"]["passed"]
    assert "travel relevance gate" in "\n".join(score["gate"]["blockers"])


def test_site_score_accepts_travel_relevant_article_topics():
    candidate = _write_candidate("travel_relevance_pass")

    score = ss.build_site_score_packet(candidate)

    assert score["productionEligible"], score
    assert score["verticalRelevance"]["passed"]


def test_site_fetch_packet_materializes_real_fetch_evidence_before_candidate():
    _write_frontier("fetch_ok")
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="fetch_ok",
        url="https://touch.travel.qunar.com/youji/123456",
        lane="article",
        title="九寨沟真实抓取候选",
        published_at="2026-06-01",
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
            "runtime": {"siteId": "qunar_guide", "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    path = ss.write_site_fetch_packet(fetch, html_bytes=ARTICLE_TEXT.encode("utf-8"))
    assert (path.parent / "raw" / "page.html").is_file()
    candidate = ss.build_site_candidate_from_fetch(fetch)
    assert candidate["gate"]["passed"], candidate["gate"]
    assert candidate["candidateRef"] == fetch["candidateRef"]


def test_site_fetch_uses_wiki_url_title_as_extract_title_and_default_mention():
    packet = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="fetch_wiki_title",
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_frontier_packet(packet)
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="fetch_wiki_title",
        url="https://zh.wikivoyage.org/wiki/%E4%B9%9D%E5%AF%A8%E6%B2%9F",
        lane="article",
        entity_mentions=[],
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
            "runtime": {"siteId": "wikivoyage_zh", "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    assert fetch["extraction"]["title"] == "九寨沟"
    assert fetch["semanticMentions"]["entities"] == ["九寨沟"]


def test_site_fetch_candidate_preserves_extracted_assets():
    _write_frontier("fetch_assets")
    asset = {
        "assetId": "asset_fetch_001",
        "url": "https://example-cdn.test/jiuzhaigou.jpg",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Jiuzhaigou.jpg",
        "license": "CC BY-SA 4.0",
        "credit": "Example Photographer",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "usageScope": "wikimedia_commons_open_license_publish_candidate",
        "modelReleaseStatus": "not_required",
        "sourceCollectionId": "wikimedia_commons:jiuzhaigou",
    }
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="fetch_assets",
        url="https://touch.travel.qunar.com/youji/123456",
        lane="article",
        title="九寨沟真实抓取候选",
        published_at="2026-06-01",
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "assets": [asset],
            "sha256": "sha",
            "runtime": {"siteId": "qunar_guide", "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    candidate = ss.build_site_candidate_from_fetch(fetch)
    assert candidate["gate"]["passed"], candidate["gate"]
    assert candidate["assets"][0]["license"] == "CC BY-SA 4.0"
    assert candidate["assets"][0]["sourceCollectionId"] == "wikimedia_commons:jiuzhaigou"


def test_content_plan_bridge_materializes_standard_batch_with_source_assets():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path, batch_root

    batch = "content_plan_bridge"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/bridge001",
        lane="article",
        title="九寨沟两日玩法",
        text=ARTICLE_TEXT * 8,
        published_at="2026-06-01",
        assets=[
            {
                "assetId": "asset_bridge_001",
                "url": "https://example-cdn.test/jiuzhaigou.png",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Jiuzhaigou.png",
                "license": "CC BY-SA 4.0",
                "credit": "Example Photographer",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "wikimedia_commons_open_license_publish_candidate",
                "modelReleaseStatus": "not_required",
                "sourceCollectionId": "wikimedia_commons:jiuzhaigou_bridge",
                "width": 1200,
                "height": 800,
            }
        ],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    original_fetch_image_payload = ss.fetch_image_payload

    def fake_fetch_image_payload(url: str):
        assert url == "https://example-cdn.test/jiuzhaigou.png"
        return {
            "url": url,
            "requestedUrl": url,
            "ext": ".png",
            "bytes": PNG_BYTES,
            "contentType": "image/png",
            "sha256": "sha256:test",
        }

    try:
        ss.fetch_image_payload = fake_fetch_image_payload
        report = ss.build_site_content_plan(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=batch,
            task_id=task_id,
            target_batch=target_batch,
            limit=1,
            allow_partial=False,
        )
    finally:
        ss.fetch_image_payload = original_fetch_image_payload

    assert report["gate"]["passed"], report
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    assert packet["generatedBy"] == "site_supply_content_plan_bridge"
    assert packet["items"][0]["baseSourceRef"].endswith("/source.md")
    root = batch_root(task_id, target_batch)
    assert (root / "entities" / "地点" / "景区" / "九寨沟").is_dir()
    asset_indexes = list(root.glob("entities/**/1.download/sources/*/assets/index.json"))
    assert len(asset_indexes) == 1
    asset = read_json(asset_indexes[0])["assets"][0]
    assert asset["license"] == "CC BY-SA 4.0"
    assert asset["credit"] == "Example Photographer"
    assert asset["termsUrl"].startswith("https://creativecommons.org/")
    assert asset["sourceCollectionId"] == "wikimedia_commons:jiuzhaigou_bridge"


def test_content_plan_bridge_derives_condition_context_from_region_locked_source_terms():
    from _common.content_object import read_brief_object

    batch = "content_plan_condition_context"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_condition_context_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/condition001",
        lane="article",
        title="九寨沟雪山高原玩法",
        text=(ARTICLE_TEXT + "雪山、海拔和高反都需要提前判断。") * 8,
        published_at="2026-06-01",
        assets=[],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        max_images_per_candidate=0,
        allow_partial=False,
    )

    assert report["gate"]["passed"], report
    brief = read_brief_object(task_id, target_batch, candidate["candidateRef"])
    context = brief["conditionContext"]
    region = context["region"]
    assert region["source"] == "site_candidate_evidence"
    assert region["name"] == "高原/高海拔"
    assert {"雪山", "海拔", "高反"}.issubset(set(region["evidenceTerms"]))
    assert region["evidenceRef"].endswith("/source.md")


def test_content_plan_bridge_blocks_short_article_base_draft():
    batch = "content_plan_short_article"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_short_article_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/short001",
        lane="article",
        title="九寨沟短攻略",
        text=ARTICLE_TEXT * 2,
        published_at="2026-06-01",
        assets=[],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        max_images_per_candidate=0,
        allow_partial=True,
    )

    assert not report["gate"]["passed"], report
    skipped = "\n".join(report["skipped"][candidate["candidateRef"]])
    assert "candidate baseDraftText too short for content_plan" in skipped
    assert report["itemCount"] == 0


def test_content_plan_bridge_revalidates_stale_score_works_decision():
    batch = "content_plan_stale_works_score"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_stale_works_score_batch"
    _write_frontier(batch)
    casual_long_text = (
        "这一天主要就是在九寨沟附近随便逛逛拍拍照，天气不错，吃了小吃，"
        "路上也没有特别规划，只是把心情和流水账记下来。"
    ) * 70
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/stale-works",
        lane="article",
        title="九寨沟随手记录",
        text=casual_long_text,
        published_at="2026-06-01",
        assets=[],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    score["productionEligible"] = True
    score["publishRecommendation"] = "publish_candidate"
    score["issues"] = []
    score.pop("worksDecision", None)
    score.pop("worksCarrier", None)
    score.pop("worksSourceTier", None)
    score["gate"] = ss._gate_report("site_score", [], [])
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        max_images_per_candidate=0,
        allow_partial=True,
    )

    assert not report["gate"]["passed"], report
    skipped = "\n".join(report["skipped"][candidate["candidateRef"]])
    assert "works classifier rejected content_plan candidate as 'moment'" in skipped
    assert report["itemCount"] == 0


def test_content_plan_bridge_dedupes_validation_targets_for_same_entity():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path

    batch = "content_plan_duplicate_entity_targets"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_duplicate_entity_targets_batch"
    _write_frontier(batch)
    for idx in range(2):
        candidate = ss.build_site_candidate_packet(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=batch,
            url=f"https://touch.travel.qunar.com/travelbook/note/dup{idx}",
            lane="article",
            title=f"九寨沟真实游记 {idx}",
            text=ARTICLE_TEXT * 8,
            published_at="2026-06-01",
            assets=[],
            entity_mentions=["地点/景区/九寨沟"],
            tag_mentions=["Topic/旅行/玩法/自然风光"],
        )
        assert candidate["gate"]["passed"], candidate["gate"]
        ss.write_site_candidate_packet(candidate)
        score = ss.build_site_score_packet(candidate)
        assert score["gate"]["passed"], score
        ss.write_site_score_packet(score)
        mapped = ss.build_site_map_packet(candidate, score)
        assert mapped["gate"]["passed"], mapped
        ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=2,
        max_images_per_candidate=0,
        allow_partial=False,
    )

    assert report["gate"]["passed"], report
    assert report["itemCount"] == 2
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    assert len(packet["items"]) == 2


def test_content_plan_bridge_blocks_missing_committed_task_spec():
    from _common.paths import batch_content_plan_packet_path

    batch = "content_plan_missing_committed_task"
    task_id = "site_supply_bridge_test/missing_task"
    target_batch = "bridge_missing_task_batch"
    candidate = _write_candidate(batch)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        allow_partial=True,
    )
    assert not report["gate"]["passed"], report
    assert "committed task spec missing" in "\n".join(report["gate"]["blockers"])
    assert not batch_content_plan_packet_path(task_id, target_batch).exists()


def test_downstream_evidence_promotes_ship_import_search_reco_into_rerollup():
    from _common.io import read_json, write_json
    from _common.paths import PUBLISH_ROOT

    source_batch = "downstream_source"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_target"
    candidate = _write_candidate(source_batch)
    score = ss.build_site_score_packet(candidate)
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    ss.write_site_map_packet(mapped)
    initial = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        objects_per_hour=500,
        first_pass_rate=1.0,
        token_ledger_count=1,
    )
    ss.write_site_rollup_report(initial)

    target_root = ss._runtime_batch_root(task_id, target_batch)
    shared = target_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    post_ref = "posts/article/攻略/九寨沟·行前指南/1"
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": source_batch},
            "items": [{"ref": candidate["candidateRef"]}],
        },
    )
    write_json(
        shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                candidate["candidateRef"]: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·行前指南",
                    "seq": 1,
                }
            },
        },
    )

    index_dir = PUBLISH_ROOT / "index" / "posts"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "article__攻略__四川.ndjson").write_text(
        json.dumps({"postRef": post_ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        PUBLISH_ROOT / "sample_bundles" / "gamma.json",
        {
            "schemaVersion": "quwoquan.content_sample_bundle",
            "environment": "gamma",
            "posts": [post_ref],
            "entities": ["地点/景区/九寨沟"],
            "counts": {"posts": 1, "entities": 1},
        },
    )
    release_dir = PUBLISH_ROOT / "env_releases" / "rel_downstream"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_contract = release_dir / "gamma.json"
    consistency = release_dir / "consistency-preflight-gamma.json"
    write_json(release_contract, {"releaseId": "rel_downstream", "environment": "gamma"})
    write_json(consistency, {"status": "passed", "releaseId": "rel_downstream", "environment": "gamma"})
    write_json(
        shared / "ship_report.json",
        {
            "schemaVersion": "quwoquan_data.ship_report/1",
            "taskId": task_id,
            "batchId": target_batch,
            "envs": ["gamma"],
            "importRequested": True,
            "summary": [
                {
                    "env": "gamma",
                    "releaseId": "rel_downstream",
                    "posts": 1,
                    "entities": 1,
                    "releaseContract": str(release_contract),
                    "consistencyReport": str(consistency),
                }
            ],
        },
    )
    write_json(
        shared / "gamma_import_report.json",
        {
            "schemaVersion": "quwoquan.content_import_report.v1",
            "status": "active",
            "environment": "gamma",
            "releaseId": "rel_downstream",
            "counts": {"postsLoaded": 1, "entitiesLoaded": 1, "feedUpserted": 1},
        },
    )

    report = ss.build_downstream_e2e_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
        env="gamma",
    )
    assert report["gate"]["passed"], report
    assert report["checks"]["releaseVerified"] is True
    assert report["checks"]["importVerified"] is True
    assert report["checks"]["searchVisible"] is True
    assert report["checks"]["currentSampleBundleVisible"] is True
    assert report["checks"]["recommendationFeedbackReady"] is True
    path = ss.write_downstream_e2e_report(report)
    assert read_json(path)["schemaVersion"] == ss.DOWNSTREAM_E2E_SCHEMA

    rerollup = ss._recomputed_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
    )
    assert rerollup["executionReadiness"]["releaseVerified"] is True
    assert rerollup["executionReadiness"]["importVerified"] is True
    assert rerollup["executionReadiness"]["searchVisible"] is True
    assert rerollup["executionReadiness"]["recommendationFeedbackReady"] is True


def test_downstream_evidence_appends_stage_outputs_for_multiple_target_batches():
    from _common.io import read_json

    source_batch = "downstream_append_source"
    reports = []
    for target_batch in ("downstream_append_target_a", "downstream_append_target_b"):
        reports.append(
            {
                "schemaVersion": ss.DOWNSTREAM_E2E_SCHEMA,
                "vertical": "travel",
                "siteId": "qunar_guide",
                "sourceBatchId": source_batch,
                "taskId": TEST_COMMITTED_TASK_ID,
                "targetBatch": target_batch,
                "env": "gamma",
                "postRefs": [f"posts/article/攻略/{target_batch}/1"],
                "plannedPostRefs": [f"posts/article/攻略/{target_batch}/1"],
                "releasedPostRefs": [f"posts/article/攻略/{target_batch}/1"],
                "plannedPostRefCount": 1,
                "releasedPostRefCount": 1,
                "droppedBeforeReleaseCount": 0,
                "checks": {
                    "releaseVerified": True,
                    "importVerified": True,
                    "searchVisible": True,
                    "recommendationFeedbackReady": True,
                },
                "importStatus": "active",
                "importCounts": {"postsUpserted": 1, "feedUpserted": 1},
                "evidencePaths": [],
                "gate": ss._gate_report("ship_import", [], []),
                "createdAt": ss.now_iso(),
            }
        )

    paths = [ss.write_downstream_e2e_report(report) for report in reports]
    stage_result = read_json(
        ss.site_supply_root("travel", "qunar_guide", source_batch)
        / "ship_import"
        / "stage_result.json"
    )

    outputs = set(stage_result["outputs"])
    assert str(paths[0]) in outputs
    assert str(paths[1]) in outputs
    assert len([item for item in outputs if item.endswith("site_supply_downstream_e2e_report.json")]) == 2


def test_downstream_evidence_keeps_historical_visibility_when_sample_bundle_changes():
    from _common.io import write_json
    from _common.paths import PUBLISH_ROOT

    source_batch = "downstream_historical_bundle_source"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_historical_bundle_target"
    candidate = _write_candidate(source_batch)
    target_root = ss._runtime_batch_root(task_id, target_batch)
    shared = target_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    post_ref = "posts/article/攻略/九寨沟·历史发布/1"
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": source_batch},
            "items": [{"ref": candidate["candidateRef"]}],
        },
    )
    write_json(
        shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                candidate["candidateRef"]: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·历史发布",
                    "seq": 1,
                }
            },
        },
    )
    index_dir = PUBLISH_ROOT / "index" / "posts"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "article__攻略__九寨沟历史.ndjson").write_text(
        json.dumps({"postRef": post_ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        PUBLISH_ROOT / "sample_bundles" / "gamma.json",
        {
            "schemaVersion": "quwoquan.content_sample_bundle",
            "environment": "gamma",
            "posts": ["posts/article/攻略/other-release/1"],
            "entities": [],
            "counts": {"posts": 1, "entities": 0},
        },
    )
    release_dir = PUBLISH_ROOT / "env_releases" / "rel_downstream_historical"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_contract = release_dir / "gamma.json"
    consistency = release_dir / "consistency-preflight-gamma.json"
    write_json(
        release_contract,
        {
            "releaseId": "rel_downstream_historical",
            "environment": "gamma",
            "desiredRefs": {"posts": [post_ref], "entities": []},
        },
    )
    write_json(consistency, {"status": "passed", "releaseId": "rel_downstream_historical", "environment": "gamma"})
    write_json(
        shared / "ship_report.json",
        {
            "schemaVersion": "quwoquan_data.ship_report/1",
            "taskId": task_id,
            "batchId": target_batch,
            "envs": ["gamma"],
            "importRequested": True,
            "summary": [
                {
                    "env": "gamma",
                    "releaseId": "rel_downstream_historical",
                    "posts": 1,
                    "entities": 0,
                    "releaseContract": str(release_contract),
                    "consistencyReport": str(consistency),
                }
            ],
        },
    )
    write_json(
        shared / "gamma_import_report.json",
        {
            "schemaVersion": "quwoquan.content_import_report.v1",
            "status": "active",
            "environment": "gamma",
            "releaseId": "rel_downstream_historical",
            "counts": {"postsLoaded": 1, "entitiesLoaded": 0, "feedUpserted": 1},
        },
    )

    report = ss.build_downstream_e2e_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
        env="gamma",
    )

    assert report["gate"]["passed"], report
    assert report["checks"]["searchVisible"] is True
    assert report["checks"]["currentSampleBundleVisible"] is False
    assert "current mutable sample bundle" in "\n".join(report["gate"]["warnings"])


def test_downstream_evidence_failed_recheck_does_not_overwrite_existing_pass_report():
    from _common.io import read_json

    source_batch = "downstream_preserve_pass_source"
    target_batch = "downstream_preserve_pass_target"
    passed_report = {
        "schemaVersion": ss.DOWNSTREAM_E2E_SCHEMA,
        "vertical": "travel",
        "siteId": "qunar_guide",
        "sourceBatchId": source_batch,
        "taskId": TEST_COMMITTED_TASK_ID,
        "targetBatch": target_batch,
        "env": "gamma",
        "postRefs": ["posts/article/攻略/pass/1"],
        "plannedPostRefs": ["posts/article/攻略/pass/1"],
        "releasedPostRefs": ["posts/article/攻略/pass/1"],
        "plannedPostRefCount": 1,
        "releasedPostRefCount": 1,
        "droppedBeforeReleaseCount": 0,
        "checks": {"releaseVerified": True, "importVerified": True, "searchVisible": True},
        "importStatus": "active",
        "importCounts": {},
        "evidencePaths": [],
        "gate": ss._gate_report("ship_import", [], []),
        "createdAt": ss.now_iso(),
    }
    pass_path = ss.write_downstream_e2e_report(passed_report)
    failed_report = dict(passed_report)
    failed_report["postRefs"] = []
    failed_report["releasedPostRefCount"] = 0
    failed_report["gate"] = ss._gate_report("ship_import", ["sample bundle gamma missing post ref"], [])

    failed_path = ss.write_downstream_e2e_report(failed_report)

    assert failed_path.name == "site_supply_downstream_e2e_report_last_failed.json"
    assert read_json(pass_path)["gate"]["passed"] is True
    assert read_json(failed_path)["gate"]["passed"] is False


def test_downstream_evidence_uses_release_refs_after_publish_attrition():
    from _common.io import write_json
    from _common.paths import PUBLISH_ROOT

    source_batch = "downstream_attrition_source"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_attrition_target"
    candidate = _write_candidate(source_batch)
    dropped_ref = "site_candidate_dropped_before_release"
    score = ss.build_site_score_packet(candidate)
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    ss.write_site_map_packet(mapped)
    ss.write_site_rollup_report(
        ss.build_site_rollup_report(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=source_batch,
            objects_per_hour=500,
            first_pass_rate=1.0,
            token_ledger_count=1,
        )
    )

    target_root = ss._runtime_batch_root(task_id, target_batch)
    shared = target_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    released_post_ref = "posts/article/攻略/九寨沟·准出稿/1"
    dropped_post_ref = "posts/article/攻略/九寨沟·发布前淘汰稿/1"
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": source_batch},
            "items": [{"ref": candidate["candidateRef"]}, {"ref": dropped_ref}],
        },
    )
    write_json(
        shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                candidate["candidateRef"]: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·准出稿",
                    "seq": 1,
                },
                dropped_ref: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·发布前淘汰稿",
                    "seq": 1,
                },
            },
        },
    )

    index_dir = PUBLISH_ROOT / "index" / "posts"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "article__攻略__九寨沟.ndjson").write_text(
        json.dumps({"postRef": released_post_ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        PUBLISH_ROOT / "sample_bundles" / "gamma.json",
        {
            "schemaVersion": "quwoquan.content_sample_bundle",
            "environment": "gamma",
            "posts": [released_post_ref],
            "entities": [],
            "counts": {"posts": 1, "entities": 0},
        },
    )
    release_dir = PUBLISH_ROOT / "env_releases" / "rel_downstream_attrition"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_contract = release_dir / "gamma.json"
    consistency = release_dir / "consistency-preflight-gamma.json"
    write_json(
        release_contract,
        {
            "releaseId": "rel_downstream_attrition",
            "environment": "gamma",
            "desiredRefs": {"posts": [released_post_ref], "entities": []},
        },
    )
    write_json(consistency, {"status": "passed", "releaseId": "rel_downstream_attrition", "environment": "gamma"})
    write_json(
        shared / "ship_report.json",
        {
            "schemaVersion": "quwoquan_data.ship_report/1",
            "taskId": task_id,
            "batchId": target_batch,
            "envs": ["gamma"],
            "importRequested": True,
            "summary": [
                {
                    "env": "gamma",
                    "releaseId": "rel_downstream_attrition",
                    "posts": 1,
                    "entities": 0,
                    "releaseContract": str(release_contract),
                    "consistencyReport": str(consistency),
                }
            ],
        },
    )
    write_json(
        shared / "gamma_import_report.json",
        {
            "schemaVersion": "quwoquan.content_import_report.v1",
            "status": "active",
            "environment": "gamma",
            "releaseId": "rel_downstream_attrition",
            "counts": {"postsLoaded": 1, "entitiesLoaded": 0, "feedUpserted": 1},
        },
    )

    report = ss.build_downstream_e2e_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
        env="gamma",
    )
    assert report["gate"]["passed"], report
    assert report["plannedPostRefCount"] == 2
    assert report["releasedPostRefCount"] == 1
    assert report["droppedBeforeReleaseCount"] == 1
    assert report["postRefs"] == [released_post_ref]
    assert dropped_post_ref not in report["postRefs"]
    assert report["checks"]["searchVisible"] is True
    assert report["checks"]["recommendationFeedbackReady"] is True


def test_downstream_write_repairs_content_plan_source_site_from_bridge_report():
    from _common.io import read_json, write_json

    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_source_site_repair"
    source_batch = "source_site_bridge_batch"
    shared = ss._runtime_batch_root(task_id, target_batch) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    packet_path = shared / "content_plan_packet.json"
    write_json(
        packet_path,
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "generatedBy": "deterministic_source_ready_planner",
            "items": [{"ref": "九寨沟_planning_consultation"}],
        },
    )
    write_json(
        shared / "site_supply_content_plan_report.json",
        {
            "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
            "vertical": "travel",
            "siteId": "wikivoyage_zh",
            "batchId": source_batch,
            "taskId": task_id,
            "targetBatch": target_batch,
            "gate": {"passed": True},
        },
    )

    repaired = ss.repair_content_plan_source_site_provenance(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
    )

    assert repaired is True
    assert read_json(packet_path)["sourceSite"] == {
        "vertical": "travel",
        "siteId": "wikivoyage_zh",
        "batchId": source_batch,
    }


def test_rerollup_derives_throughput_from_fetch_stage_timestamps():
    from _common.io import write_json

    batch = "throughput_from_stage_results"
    root = ss.site_supply_root("travel", "qunar_guide", batch)
    for ref, created_at in {
        "candidate_a": "2026-06-20T00:00:00+00:00",
        "candidate_b": "2026-06-20T00:01:00+00:00",
    }.items():
        write_json(
            root / "fetches" / ref / "stage_result.json",
            {
                "schemaVersion": ss.STAGE_SCHEMA,
                "stage": "site_fetch",
                "status": "succeeded",
                "createdAt": created_at,
            },
        )

    observed = ss._observed_objects_per_hour_from_stage_results(root)
    assert round(observed, 2) == 120.0


def test_content_plan_bridge_blocks_unverified_raw_entity_for_scenic_type():
    batch = "content_plan_unverified_entity"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_unverified_entity_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/bridge002",
        lane="article",
        title="北京首都国际机场",
        text=ARTICLE_TEXT * 8,
        published_at="2026-06-01",
        assets=[
            {
                "assetId": "asset_bridge_002",
                "url": "https://example-cdn.test/airport.png",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Airport.png",
                "license": "CC BY-SA 4.0",
                "credit": "Example Photographer",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "wikimedia_commons_open_license_publish_candidate",
                "modelReleaseStatus": "not_required",
                "sourceCollectionId": "wikimedia_commons:airport_bridge",
                "width": 1200,
                "height": 800,
            }
        ],
        entity_mentions=["北京首都国际机场"],
        tag_mentions=["Topic/旅行/交通/机场"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    original_fetch_image_payload = ss.fetch_image_payload
    try:
        ss.fetch_image_payload = lambda url: {
            "url": url,
            "requestedUrl": url,
            "ext": ".png",
            "bytes": PNG_BYTES,
            "contentType": "image/png",
            "sha256": "sha256:test",
        }
        report = ss.build_site_content_plan(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=batch,
            task_id=task_id,
            target_batch=target_batch,
            limit=1,
            allow_partial=True,
        )
    finally:
        ss.fetch_image_payload = original_fetch_image_payload

    assert not report["gate"]["passed"], report
    skipped = "\n".join("\n".join(issues) for issues in report["skipped"].values())
    assert "candidate lacks verified 地点/景区 mapping" in skipped


def test_site_fetch_stops_when_frontier_is_not_batch_crawl_allowed():
    frontier = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id="fetch_blocked_ctrip",
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id="fetch_blocked_ctrip",
        url="https://you.ctrip.com/travels/example.html",
        lane="article",
        title="不应进入抓取",
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
        },
    )
    assert not fetch["gate"]["passed"]
    text = "\n".join(fetch["gate"]["blockers"])
    assert "site_frontier gate did not pass" in text


def test_fetch_retry_budget_recovers_transient_empty_body():
    calls = {"count": 0}
    original = ss.fetch_source_payload

    def fake_fetch(url: str, source=None):
        assert source is None
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError(f"fetch failed for {url} (status=200)")
        return {
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
            "runtime": {"siteId": "qunar_guide", "fetchable": True},
        }

    try:
        ss.fetch_source_payload = fake_fetch
        payload, error, attempts = ss._fetch_with_retry(
            "https://touch.travel.qunar.com/youji/123456",
            retry_budget=2,
            retry_delay_seconds=0,
        )
    finally:
        ss.fetch_source_payload = original
    assert error == ""
    assert attempts == 2
    assert payload and payload["statusCode"] == 200


def test_travel_frontier_query_strategy_reuses_task_coverage_terms():
    terms = ss._travel_frontier_query_terms(limit=700)
    assert "成都" in terms
    assert "乐山大佛" in terms or "三星堆博物馆" in terms
    assert "杭州西湖" in terms or "黄山" in terms


def test_travel_frontier_prioritizes_coverage_targets_over_broad_seed_terms():
    terms = ss._travel_frontier_query_terms(limit=700)

    assert "网站供给线" not in terms
    assert "中国" not in terms
    assert "四川省" not in terms
    assert "乐山大佛" in terms or "三星堆博物馆" in terms
    if "黄山" in terms:
        assert terms.index("黄山") < terms.index("北京")
    target_index = min(
        terms.index(term)
        for term in ("乐山大佛", "三星堆博物馆")
        if term in terms
    )
    assert target_index < terms.index("北京")


def test_qunar_search_candidates_preserve_verified_query_entity_mention():
    from download import research_plan

    def fake_curl_json(url: str, timeout: int = 20):
        _ = timeout
        assert "q=%E4%B9%9D%E5%AF%A8%E6%B2%9F" in url
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7890001",
                        "title": "川西亲子自驾",
                        "userName": "tester",
                        "travelRoute": ["成都", "阿坝"],
                        "destCities": ["成都"],
                        "cityName": "成都",
                    }
                ]
            },
        }

    original = research_plan._curl_json
    try:
        research_plan._curl_json = fake_curl_json
        rows = ss._qunar_search_candidates(
            queries=["九寨沟"],
            max_pages=1,
            limit=1,
            window={"from": "2024-06-20", "to": "2026-06-20"},
            request_budget=1,
        )
    finally:
        research_plan._curl_json = original

    assert rows[0]["entityMentions"][0] == "地点/景区/九寨沟"
    assert rows[0]["discovery"]["query"] == "九寨沟"


def test_qunar_search_candidates_report_progress_and_request_timeout():
    from download import research_plan

    seen_timeouts: list[int] = []
    progress_rows: list[dict] = []

    def fake_curl_json(url: str, timeout: int = 20):
        assert "q=%E4%B9%9D%E5%AF%A8%E6%B2%9F" in url
        seen_timeouts.append(timeout)
        return {"ret": False}

    original = research_plan._curl_json
    try:
        research_plan._curl_json = fake_curl_json
        rows = ss._qunar_search_candidates(
            queries=["九寨沟"],
            max_pages=1,
            limit=1,
            window={"from": "2024-06-20", "to": "2026-06-20"},
            request_budget=1,
            request_timeout=6,
            progress_callback=lambda **kwargs: progress_rows.append(dict(kwargs)),
        )
    finally:
        research_plan._curl_json = original

    assert rows == []
    assert seen_timeouts == [6]
    assert progress_rows[0]["status"] == "running"
    assert progress_rows[-1]["status"] == "budget_exhausted"
    assert progress_rows[-1]["requests_used"] == 1


def test_crawl_input_candidates_writes_frontier_discovery_progress():
    batch = "frontier_discovery_progress"
    frontier = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        daily_target=1000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    ss.write_site_frontier_packet(frontier)
    args = type(
        "Args",
        (),
        {
            "vertical": "travel",
            "site_id": "qunar_guide",
            "batch": batch,
            "target_count": 2,
            "discovery_target_count": 2,
            "lane": "article",
            "seed_urls": "",
            "seed_file": None,
            "entity_mentions": "",
            "tag_mentions": "",
            "end_date": "2026-06-19",
            "queries": "九寨沟",
            "query_strategy": "manual",
            "max_search_pages": 1,
            "max_discovery_requests": 3,
            "discovery_request_timeout": 5,
            "discovery_timeout_seconds": 30,
            "min_text_chars": 600,
        },
    )()
    original = ss._qunar_search_candidates

    def fake_qunar_search_candidates(**kwargs):
        kwargs["progress_callback"](
            status="running",
            requests_used=1,
            discovered_count=1,
            query="九寨沟",
            page=1,
            message="fixture progress",
        )
        return [
            {
                "url": "https://touch.travel.qunar.com/youji/fixture1",
                "lane": "article",
                "title": "九寨沟攻略",
            }
        ]

    try:
        ss._qunar_search_candidates = fake_qunar_search_candidates
        rows = ss._crawl_input_candidates(args, frontier)
    finally:
        ss._qunar_search_candidates = original

    assert len(rows) == 1
    progress_path = (
        ss.site_supply_root("travel", "qunar_guide", batch)
        / "site_frontier"
        / "discovery_progress.json"
    )
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress["schemaVersion"] == ss.DISCOVERY_PROGRESS_SCHEMA
    assert progress["status"] == "underfilled"
    assert progress["targetCount"] == 2
    assert progress["discoveryTargetCount"] == 2
    assert progress["discoveredCount"] == 1
    assert progress["requestsUsed"] == 1


def test_mediawiki_frontier_rejects_sparse_subpages():
    assert ss._mediawiki_title_allowed("北京")
    assert not ss._mediawiki_title_allowed("北京/北部郊区")
    assert not ss._mediawiki_title_allowed("Category:北京")
    assert not ss._mediawiki_title_allowed("首页")
    assert not ss._mediawiki_title_allowed("Main Page")
    assert not ss._mediawiki_title_allowed("通州 (消歧义)")
    assert not ss._mediawiki_title_allowed("昔日每月目的地")
    assert ss._mediawiki_url_allowed("https://zh.wikivoyage.org/wiki/%E5%8C%97%E4%BA%AC")
    assert not ss._mediawiki_url_allowed("https://zh.wikivoyage.org/wiki/%E9%A6%96%E9%A1%B5")
    assert ss._mediawiki_search_row_allowed({"ns": 0, "title": "保定", "wordcount": 523, "size": 4769})
    assert not ss._mediawiki_search_row_allowed({"ns": 0, "title": "雄安新区", "wordcount": 35, "size": 1158})
    assert ss._mediawiki_search_row_allowed({"ns": 0, "title": "平武", "wordcount": 200, "size": 2500})
    assert not ss._mediawiki_search_row_allowed(
        {"ns": 0, "title": "平武", "wordcount": 200, "size": 2500},
        min_size_bytes=3000,
    )
    assert ss._mediawiki_title_matches_query_terms("九寨沟风景名胜区", ["九寨沟"])
    assert not ss._mediawiki_title_matches_query_terms("四川", ["九寨沟"])
    assert not ss._mediawiki_title_matches_query_terms("国家5A级旅游景区", ["九寨沟"])


def test_mediawiki_site_index_frontier_uses_allpages_and_filters_sparse_pages():
    from download import research_plan

    calls: list[str] = []

    def fake_curl_json(url: str, timeout: int = 20):
        _ = timeout
        calls.append(url)
        assert "generator=allpages" in url
        return {
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "九寨沟",
                        "length": 8200,
                        "fullurl": "https://zh.wikivoyage.org/wiki/九寨沟",
                    },
                    "2": {
                        "pageid": 2,
                        "title": "北京/海淀",
                        "length": 9000,
                        "fullurl": "https://zh.wikivoyage.org/wiki/北京/海淀",
                    },
                    "3": {
                        "pageid": 3,
                        "title": "短页",
                        "length": 400,
                        "fullurl": "https://zh.wikivoyage.org/wiki/短页",
                    },
                    "4": {
                        "pageid": 4,
                        "title": "黄山",
                        "length": 7200,
                        "fullurl": "https://zh.wikivoyage.org/wiki/黄山",
                    },
                }
            }
        }

    orig = research_plan._curl_json
    try:
        research_plan._curl_json = fake_curl_json
        rows = ss._mediawiki_site_index_candidates(
            host="zh.wikivoyage.org",
            provider="维基导游",
            limit=5,
            request_budget=1,
        )
    finally:
        research_plan._curl_json = orig

    assert len(calls) == 1
    assert [row["title"] for row in rows] == ["九寨沟", "黄山"]
    assert all(row["discovery"]["provider"] == "mediawiki_allpages_api" for row in rows)


def test_mediawiki_search_candidates_preserve_verified_query_entity_mention():
    from download import research_plan

    calls: list[str] = []
    seen_timeouts: list[int] = []
    progress_rows: list[dict] = []

    def fake_curl_json(url: str, timeout: int = 20):
        seen_timeouts.append(timeout)
        calls.append(url)
        assert "list=search" in url
        return {
            "query": {
                "search": [
                    {
                        "pageid": 11,
                        "ns": 0,
                        "title": "九寨沟",
                        "wordcount": 620,
                        "size": 9600,
                    }
                ]
            }
        }

    orig = research_plan._curl_json
    try:
        research_plan._curl_json = fake_curl_json
        rows = ss._mediawiki_search_candidates(
            host="zh.wikivoyage.org",
            provider="维基导游",
            queries=["九寨沟"],
            max_pages=1,
            limit=1,
            request_budget=1,
            title_terms=["九寨沟"],
            request_timeout=7,
            progress_callback=lambda **kwargs: progress_rows.append(dict(kwargs)),
        )
    finally:
        research_plan._curl_json = orig

    assert len(calls) == 1
    assert seen_timeouts == [7]
    assert progress_rows[0]["status"] == "running"
    assert progress_rows[-1]["status"] == "completed"
    assert rows[0]["entityMentions"][0] == "地点/景区/九寨沟"
    assert rows[0]["entityMentions"][1] == "九寨沟"
    assert rows[0]["discovery"]["query"] == "九寨沟"


def test_mediawiki_search_candidates_match_current_query_not_global_terms():
    from urllib.parse import parse_qs, urlparse

    from download import research_plan

    def fake_curl_json(url: str, timeout: int = 20):
        query = parse_qs(urlparse(url).query).get("srsearch", [""])[0]
        assert query in {"黄山风景区", "马鞍山"}
        return {
            "query": {
                "search": [
                    {
                        "pageid": 12,
                        "ns": 0,
                        "title": "马鞍山",
                        "wordcount": 620,
                        "size": 9600,
                    }
                ]
            }
        }

    def fake_resolve(name: str, *, expected_entity_type: str):
        if expected_entity_type != "地点/景区":
            return None
        if name == "黄山风景区":
            return {"entityType": "地点/景区", "name": "黄山风景区"}
        if name == "马鞍山":
            return {"entityType": "地点/景区", "name": "马鞍山"}
        return None

    orig_curl = research_plan._curl_json
    orig_resolve = ss._resolve_known_entity_target
    try:
        research_plan._curl_json = fake_curl_json
        ss._resolve_known_entity_target = fake_resolve
        rows = ss._mediawiki_search_candidates(
            host="zh.wikivoyage.org",
            provider="维基导游",
            queries=["黄山风景区", "马鞍山"],
            max_pages=1,
            limit=1,
            request_budget=2,
            title_terms=["黄山风景区", "马鞍山"],
        )
    finally:
        research_plan._curl_json = orig_curl
        ss._resolve_known_entity_target = orig_resolve

    assert len(rows) == 1
    assert rows[0]["title"] == "马鞍山"
    assert rows[0]["discovery"]["query"] == "马鞍山"
    assert rows[0]["entityMentions"][0] == "地点/景区/马鞍山"
    assert "地点/景区/黄山风景区" not in rows[0]["entityMentions"]


def test_mediawiki_site_index_candidates_report_request_progress():
    from download import research_plan

    progress_rows: list[dict] = []

    def fake_curl_json(url: str, timeout: int = 20):
        assert timeout == 7
        return {
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "九寨沟",
                        "length": 9600,
                        "fullurl": "https://zh.wikivoyage.org/wiki/九寨沟",
                    }
                }
            }
        }

    orig = research_plan._curl_json
    try:
        research_plan._curl_json = fake_curl_json
        rows = ss._mediawiki_site_index_candidates(
            host="zh.wikivoyage.org",
            provider="维基导游",
            limit=1,
            request_budget=2,
            request_timeout=7,
            progress_callback=lambda **kwargs: progress_rows.append(dict(kwargs)),
        )
    finally:
        research_plan._curl_json = orig

    assert len(rows) == 1
    assert progress_rows[0]["status"] == "running"
    assert progress_rows[-1]["status"] == "completed"
    assert progress_rows[-1]["requests_used"] == 1
    assert progress_rows[-1]["discovered_count"] == 1


def test_mediawiki_title_match_rejects_short_parent_title_substrings():
    assert not ss._mediawiki_title_matches_query_terms("上海", ["上海科技馆"])
    assert not ss._mediawiki_title_matches_query_terms("黄山市", ["黄山风景区", "黄山"])
    assert ss._mediawiki_title_matches_query_terms("黄山", ["黄山风景区", "黄山"])
    assert ss._mediawiki_title_matches_query_terms("杭州西湖", ["杭州西湖风景区", "杭州西湖"])


def test_known_entity_target_resolution_prefers_exact_over_suffix_alias():
    target = ss._resolve_known_entity_target("九寨沟", expected_entity_type="地点/景区")
    assert target is not None
    assert target["entityType"] == "地点/景区"
    assert target["name"] == "九寨沟"


def test_known_entity_targets_skip_site_supply_dynamic_placeholders(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="site_supply_dynamic_targets_"))
    original_root = ss.DATA_ROOT
    ss._known_coverage_entity_targets.cache_clear()
    try:
        ss.DATA_ROOT = tmp_path
        dynamic_task = tmp_path / "tasks" / "site_supply_dynamic" / "task.yaml"
        dynamic_task.parent.mkdir(parents=True)
        dynamic_task.write_text(
            "\n".join(
                [
                    "schemaVersion: quwoquan.task.spec",
                    "workflowPolicy:",
                    "  siteSupplyDynamicContentPlan: true",
                    "scope:",
                    "  coverageTargets:",
                    "    - entityType: 地点/景区",
                    "      name: 中国",
                ]
            ),
            encoding="utf-8",
        )
        normal_task = tmp_path / "tasks" / "normal" / "task.yaml"
        normal_task.parent.mkdir(parents=True)
        normal_task.write_text(
            "\n".join(
                [
                    "schemaVersion: quwoquan.task.spec",
                    "scope:",
                    "  coverageTargets:",
                    "    - entityType: 地点/景区",
                    "      name: 九寨沟",
                ]
            ),
            encoding="utf-8",
        )

        targets = ss._known_coverage_entity_targets()
        assert "中国" not in targets
        assert targets["九寨沟"][0]["name"] == "九寨沟"
    finally:
        ss.DATA_ROOT = original_root
        ss._known_coverage_entity_targets.cache_clear()


def test_known_entity_target_resolution_uses_explicit_segment_alias_not_containment():
    original = ss._known_coverage_entity_targets
    target = {
        "name": "云台山－神农山－青天河风景区",
        "entityType": "地点/景区",
        "source": "tasks/example/task.yaml",
    }
    try:
        ss._known_coverage_entity_targets = lambda: {
            "云台山－神农山－青天河风景区": (target,),
            "云台山": (target,),
            "神农山": (target,),
            "上海科技馆": (
                {
                    "name": "上海科技馆",
                    "entityType": "地点/景区",
                    "source": "tasks/example/task.yaml",
                },
            ),
            "上海野生动物园": (
                {
                    "name": "上海野生动物园",
                    "entityType": "地点/景区",
                    "source": "tasks/example/task.yaml",
                },
            ),
        }
        assert ss._resolve_known_entity_target(
            "云台山",
            expected_entity_type="地点/景区",
        ) == target
        assert "云台山" in ss._entity_name_aliases("云台山－神农山－青天河风景区")
        assert "福建土楼" in ss._entity_name_aliases("福建土楼（永定·南靖）旅游景区")
        assert "南靖" not in ss._entity_name_aliases("福建土楼（永定·南靖）旅游景区")
        assert "北京" not in ss._entity_name_aliases("北京（通州）大运河文化旅游景区")
        assert ss._resolve_known_entity_target(
            "上海",
            expected_entity_type="地点/景区",
        ) is None
    finally:
        ss._known_coverage_entity_targets = original


def test_crawl_blocks_at_frontier_when_discovery_underfills_target():
    original = ss._crawl_input_candidates
    args = type(
        "Args",
        (),
        {
            "vertical": "travel",
            "site_id": "qunar_guide",
            "batch": "underfill_frontier",
            "target_count": 2,
            "daily_target": 1000,
            "queue_backend": "reliabletask",
            "lane": "article",
            "end_date": "2026-06-19",
            "max_discovery_requests": 1,
        },
    )()

    try:
        ss._crawl_input_candidates = lambda _args, _frontier: [
            {"url": "https://touch.travel.qunar.com/youji/1", "lane": "article"}
        ]
        with redirect_stdout(StringIO()):
            try:
                ss.handle_crawl(args)
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("handle_crawl should block underfilled discovery")
    finally:
        ss._crawl_input_candidates = original
    frontier = ss._frontier_packet("travel", "qunar_guide", "underfill_frontier")
    assert frontier["gate"]["passed"] is False
    assert "discovery produced 1 URLs" in "\n".join(frontier["gate"]["blockers"])


def test_crawl_rerun_skips_existing_successful_handoff_without_refetch():
    batch = "crawl_resume_existing"
    _write_frontier(batch)
    url = "https://touch.travel.qunar.com/youji/resume001"
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url=url,
        lane="article",
        title="九寨沟重跑幂等候选",
        text=ARTICLE_TEXT * 8,
        published_at="2026-06-01",
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    ss.write_site_map_packet(mapped)

    args = type(
        "Args",
        (),
        {
            "vertical": "travel",
            "site_id": "qunar_guide",
            "batch": batch,
            "target_count": 1,
            "frontier_overfetch_ratio": 1.0,
            "daily_target": 1000,
            "queue_backend": "reliabletask",
            "lane": "article",
            "end_date": "2026-06-19",
            "max_discovery_requests": 1,
            "query_strategy": "manual",
            "frontier_only": False,
            "throttle_seconds": 0,
            "fetch_retry_budget": 0,
            "fetch_retry_delay": 0,
            "min_text_chars": 60,
            "objects_per_hour": 10,
            "token_ledger_count": 1,
            "release_verified": False,
            "import_verified": False,
            "search_visible": False,
            "recommendation_feedback_ready": False,
            "stop_on_first_failure": False,
        },
    )()
    original_candidates = ss._crawl_input_candidates
    original_fetch = ss.fetch_source_payload
    try:
        ss._crawl_input_candidates = lambda _args, _frontier: [{"url": url, "lane": "article"}]
        ss.fetch_source_payload = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("existing successful handoff must not refetch")
        )
        with redirect_stdout(StringIO()):
            ss.handle_crawl(args)
    finally:
        ss._crawl_input_candidates = original_candidates
        ss.fetch_source_payload = original_fetch
    rollup = ss._recomputed_site_rollup_report(vertical="travel", site_id="qunar_guide", batch_id=batch)
    assert rollup["passed"], rollup
    assert rollup["siteFunnel"]["contentPlanHandoffCount"] == 1


def test_trial_command_materializes_hundred_level_structural_batch():
    cli = SCRIPTS_ROOT / "cli.py"
    trial = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "trial",
            "--site-id",
            "qunar_guide",
            "--batch",
            "trial_100",
            "--target-count",
            "100",
            "--daily-target",
            "1000",
            "--objects-per-hour",
            "120",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_env(),
    )
    assert trial.returncode == 0, trial.stderr
    payload = json.loads(trial.stdout)
    assert payload["siteFunnel"]["candidateCount"] == 100
    assert payload["siteFunnel"]["contentPlanHandoffCount"] == 100
    assert payload["siteFunnel"]["stageFailures"]["missing_score"] == 0


def test_cli_site_supply_roundtrip():
    cli = SCRIPTS_ROOT / "cli.py"
    plan = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "plan",
            "--site-id",
            "qunar_guide",
            "--batch",
            "cli_roundtrip",
            "--daily-target",
            "100000",
            "--end-date",
            "2026-06-19",
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_env(),
    )
    assert plan.returncode == 0, plan.stderr
    payload = json.loads(plan.stdout)
    assert payload["schemaVersion"] == "quwoquan.site_supply.site_frontier_packet/1"

    candidate = subprocess.run(
        [
            sys.executable,
            str(cli),
            "site-supply",
            "candidate",
            "--site-id",
            "qunar_guide",
            "--batch",
            "cli_roundtrip",
            "--url",
            "https://touch.travel.qunar.com/travelbook/note/654321",
            "--lane",
            "article",
            "--title",
            "CLI 候选",
            "--text",
            ARTICLE_TEXT,
            "--published-at",
            "2026-06-01",
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_cli_env(),
    )
    assert candidate.returncode == 0, candidate.stderr


_CASUAL_SITE_TEXT = "九寨沟今天天气真好，随手拍了几张照片，特别开心，海子的颜色很美，下次还来玩。"


def _site_works_candidate(*, ref: str, text: str, validation_only: bool, lane: str = "article") -> dict:
    return {
        "schemaVersion": ss.CANDIDATE_SCHEMA,
        "vertical": "travel",
        "siteId": "qunar_guide",
        "batchId": "works_gate_contract",
        "candidateRef": ref,
        "canonicalUrl": f"https://touch.travel.qunar.com/travelbook/note/{ref}",
        "lane": lane,
        "source": {
            "platform": "去哪儿攻略",
            "rightsPolicy": "factual_citation_only",
            "validationOnly": validation_only,
        },
        "title": "九寨沟",
        "text": text,
        "assets": [],
        "publishedAt": "2026-06-01",
        "gate": {"passed": True},
    }


def test_site_score_works_classifier_passes_professional_article():
    """站点线：专业旅行攻略 → worksDecision=work（全站分类入库放行），works 门不阻断。"""
    score = ss.build_site_score_packet(
        _site_works_candidate(ref="works_pro", text=ARTICLE_TEXT, validation_only=False)
    )
    assert score["worksDecision"] == "work"
    assert "works classifier" not in "\n".join(score["gate"]["blockers"])


def test_site_score_works_classifier_blocks_casual_real_candidate():
    """站点线：真实抓取的碎片随记候选 → works 门阻断、不进全站分类入库。"""
    score = ss.build_site_score_packet(
        _site_works_candidate(ref="works_casual", text=_CASUAL_SITE_TEXT, validation_only=False)
    )
    assert score["worksDecision"] != "work"
    assert "works classifier" in "\n".join(score["gate"]["blockers"])
    assert not score["productionEligible"]


def test_site_score_validation_only_candidate_audited_not_blocked_by_works():
    """站点线：受控试跑候选只落审计 worksDecision、works 门不二次阻断（结构试跑合成候选）。"""
    score = ss.build_site_score_packet(
        _site_works_candidate(ref="works_trial", text=_CASUAL_SITE_TEXT, validation_only=True)
    )
    assert score["worksDecision"]
    assert "works classifier" not in "\n".join(score["gate"]["blockers"])


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
