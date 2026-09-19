# spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md
"""有界读侧准入：能力条件先于数据库 limit，不启动 Mongo。"""
from copy import deepcopy

import pytest

from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store_ranking_reads import MongoCandidateRankingReadOps


class _Cursor(list):
    def sort(self, *_args):
        return self

    def limit(self, count):
        return _Cursor(self[:count])


class _Candidates:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, projection=None):
        self.queries.append(deepcopy(query))
        def matches(row):
            for field, expected in query.items():
                value = row.get(field)
                if not isinstance(expected, dict):
                    if value != expected:
                        return False
                    continue
                if "$in" in expected and value not in expected["$in"]:
                    return False
                if "$nin" in expected and value in expected["$nin"]:
                    return False
                if "$ne" in expected and value == expected["$ne"]:
                    return False
                if "$type" in expected:
                    kind = str if expected["$type"] == "string" else dict
                    if not isinstance(value, kind):
                        return False
            return True
        return _Cursor([deepcopy(row) for row in self.rows if matches(row)])


def _reader():
    reader = MongoCandidateRankingReadOps()
    reader._candidates = _Candidates([
        {"sourcePartition": "ordinary", "scenario": "content_feed", "contentId": f"p-{i}",
         "contentType": "video" if i < 20 else "article", "contentVertical": "travel_photography"}
        for i in range(30)
    ])
    # 故意无 gathering collection；主页读不得依赖或触碰该产品路径。
    return reader


@pytest.mark.parametrize("scenario", ["content_feed", "travel_photography"])
def test_capability_filter_precedes_lane_limits_and_bounded_refill(scenario):
    reader = _reader()
    rows = reader.list_for_ranking(scenario=scenario, limit=4, eligible_content_types=("article",))
    assert len(rows) == 4
    assert all(row["contentType"] == "article" for row in rows)
    assert len({row["contentId"] for row in rows}) == 4
    assert len(reader._candidates.queries) <= 3
    assert all(query["contentType"] == {"$in": ["article"]} for query in reader._candidates.queries)


def test_empty_post_capability_performs_no_post_query():
    reader = _reader()
    assert reader.list_for_ranking(scenario="content_feed", limit=4, eligible_content_types=()) == []
    assert reader._candidates.queries == []


def test_collaborative_filter_precedes_result_limit_inside_fixed_id_budget():
    reader = _reader()
    rows = reader.list_for_ranking_by_content_ids(
        scenario="content_feed", content_ids=tuple(f"p-{i}" for i in range(30)),
        limit=3, eligible_content_types=("article",),
    )
    assert len(rows) == 3
    assert all(row["contentType"] == "article" for row in rows)
    assert len(reader._candidates.queries[0]["contentId"]["$in"]) <= 50


def test_homepage_reader_is_narrow_and_never_reads_gathering():
    reader = _reader()
    reader._candidates.rows.append({
        "sourcePartition": "ordinary", "scenario": "content_feed", "contentId": "p-home",
        "primaryHomepageId": "homepage", "primaryHomepageSnapshot": {"title": "主页"},
    })
    rows = reader.list_homepage_candidates(limit=1)
    assert len(rows) == 1
    assert rows[0]["objectKind"] == "entity_homepage"
    assert rows[0]["primaryHomepageId"] == "homepage"
    assert not hasattr(reader, "list_object_card_candidates")


def test_release_fence_filters_before_combined_limit_and_preserves_binding():
    from generated.recommendation.ranked_recommendation_window.models.request_response import ReleasePinnedQueryFence
    from tests.local_contract.recommendation.recommendation_candidate_index_view.test_release_candidate__local_contract_test import _reader as release_reader
    from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import canonical
    reader, event = release_reader()
    calls = []
    def ordinary(**kwargs):
        calls.append(kwargs)
        return [{"contentId": "ordinary-article", "contentType": "article"}]
    reader.list_for_ranking = ordinary
    fence = ReleasePinnedQueryFence.model_validate({"release": canonical(event.binding.release), "revision": 1})
    # release 中两个 video 在 limit=1 前排除，不应吞掉后续 ordinary article。
    rows = reader.list_release_for_ranking(fence, scenario="content_feed", subject_id="viewer", limit=1, eligible_content_types=("article",))
    assert [row["contentId"] for row in rows] == ["ordinary-article"]
    assert calls[0]["eligible_content_types"] == ("article",)
    assert calls[0]["limit"] == 1
