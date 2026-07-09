from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



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
        assert packet["profile"]["articleCommercialAdmission"] == "controlled_trial"
        assert packet["profile"]["controlledTrial"]["validationOnly"] is True
        warning_text = "\n".join(packet["gate"]["warnings"])
        assert "does not grant raw batch crawl" in warning_text

def test_controlled_trial_blocks_publishable_asset_escape_hatch():
    profile = {
        "rawProfilePresent": True,
        "fetchable": False,
        "crawlAllowed": False,
        "domains": ["www.mafengwo.cn"],
        "allowedPaths": ["https://www.mafengwo.cn/i/*"],
        "contentLanes": ["article", "image"],
        "articleCommercialAdmission": "controlled_trial",
        "rightsPolicy": "reference_only",
        "robotsPolicy": "respect_robots_txt",
        "loginPolicy": "public_only",
        "termsUrl": "https://www.mafengwo.cn/",
        "maxPagesPerDay": 0,
        "controlledTrial": {
            "allowed": True,
            "validationOnly": True,
            "rawFetchAllowed": False,
            "publishableAssetsAllowed": True,
        },
    }

    blockers, _warnings = ss._profile_gate(
        profile,
        daily_target=10_000,
        queue_backend="reliabletask",
        time_window={"days": 30},
        admission_mode="controlled_trial",
    )

    assert "controlledTrial.publishableAssetsAllowed cannot be true" in blockers

def test_expanded_travel_reference_sources_are_validation_only():
    expected = {
        "xiaohongshu_travel_reference": "reference_only",
        "toutiao_article_reference": "reference_only",
        "weibo_travel_reference": "reference_only",
        "pinterest_travel_reference": "attribution_no_watermark",
        "tuchong_community_reference": "licensed_candidate",
        "tuchong_stock_authorized": "licensed_asset_required",
    }
    for site_id, rights_policy in expected.items():
        blocked = ss.build_site_frontier_packet(
            vertical="travel",
            site_id=site_id,
            batch_id=f"{site_id}_raw_block",
            daily_target=10_000,
            queue_backend="reliabletask",
            end_date="2026-07-04",
        )
        assert not blocked["gate"]["passed"], blocked["gate"]
        assert blocked["profile"]["fetchable"] is False
        assert blocked["profile"]["crawlAllowed"] is False
        assert blocked["profile"]["rightsPolicy"] == rights_policy
        if site_id in {"xiaohongshu_travel_reference", "toutiao_article_reference", "weibo_travel_reference"}:
            assert blocked["profile"]["articleCommercialAdmission"] == "reference_only"
            assert blocked["profile"]["discoveryStrategy"]["mode"] == "content_search"
        text = "\n".join(blocked["gate"]["blockers"])
        assert "fetchable=false" in text
        assert "crawlAllowed" in text

        trial = ss.build_site_frontier_packet(
            vertical="travel",
            site_id=site_id,
            batch_id=f"{site_id}_controlled",
            daily_target=10_000,
            queue_backend="reliabletask",
            end_date="2026-07-04",
            admission_mode="controlled_trial",
        )
        assert trial["gate"]["passed"], trial["gate"]
        assert trial["profile"]["controlledTrial"]["validationOnly"] is True
        assert trial["profile"]["controlledTrial"]["rawFetchAllowed"] is False
        assert trial["profile"]["controlledTrial"]["publishableAssetsAllowed"] is False
        warning_text = "\n".join(trial["gate"]["warnings"])
        assert "does not grant raw batch crawl" in warning_text

def test_photography_platform_frontier_blocks_raw_crawl_but_allows_controlled_trial():
    for site_id, rights_policy in (("pinterest", "attribution_no_watermark"), ("tuchong", "licensed_candidate")):
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
        if site_id == "pinterest":
            assert blocked["profile"]["discoveryStrategy"]["mode"] == "content_search"
        if site_id == "tuchong":
            assert blocked["profile"]["discoveryStrategy"]["mode"] == "site_listing_scan"
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
    assert "/local/data-runtime/tasks/" not in str(path)
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

def test_controlled_trial_rerollup_uses_candidate_denominator_for_first_pass_rate():
    batch = "controlled_trial_rerollup_first_pass"
    frontier = ss.build_site_frontier_packet(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-07-04",
        admission_mode="controlled_trial",
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    url = ss._trial_url(frontier["profile"], batch_id=batch, lane="image", index=1)
    candidate = ss.build_site_candidate_packet(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        url=url,
        lane="image",
        title="Pinterest 受控图片试跑候选",
        published_at="2026-07-04",
        assets=ss._trial_assets(frontier["profile"], url=url, lane="image", index=1),
        entity_mentions=["地点/景区/结构试跑景区000001"],
        tag_mentions=["Topic/摄影/旅行影像"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score["gate"]
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped["gate"]
    ss.write_site_map_packet(mapped)

    rollup = ss._recomputed_site_rollup_report(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        objects_per_hour=6000,
    )

    assert rollup["passed"], rollup
    assert rollup["siteFunnel"]["fetchCount"] == 0
    assert rollup["siteFunnel"]["candidateCount"] == 1
    assert rollup["executionReadiness"]["firstPassRate"] == 1.0

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
