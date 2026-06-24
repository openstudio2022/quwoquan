from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



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

