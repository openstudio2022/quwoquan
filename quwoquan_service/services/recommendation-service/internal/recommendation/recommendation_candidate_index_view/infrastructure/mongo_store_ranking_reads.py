"""排序召回读面（``MongoCandidateIndexStore`` mixin）。

拆分自原 ``mongo_store.py``（行数治理）：关注关系读取、场景受众
query 推导、多路有界召回与对象卡候选清单。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING


class MongoCandidateRankingReadOps:
    """召回读操作；集合属性由组合根 ``__init__`` 装配。"""

    # 召回默认时序：updatedAt 倒序，contentId 升序打破同刻并列以保证稳定分页。
    _RECENT_SORT = (("updatedAt", DESCENDING), ("contentId", ASCENDING))

    def following_persona_ids(self, source_persona_id: str) -> tuple[str, ...]:
        normalized_source = source_persona_id.strip()
        if not normalized_source:
            raise ValueError("following source persona identity is required")
        return tuple(
            str(document.get("targetPersonaId") or "").strip()
            for document in self._persona_relationships.find(
                {
                    "sourcePersonaId": normalized_source,
                    "following": True,
                    "blocked": {"$ne": True},
                },
                {"targetPersonaId": 1},
            ).sort("targetPersonaId", ASCENDING)
            if str(document.get("targetPersonaId") or "").strip()
        )

    @staticmethod
    def ranking_query(
        scenario: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_scenario = scenario.strip()
        query: dict[str, Any] = {
            "sourcePartition": "ordinary",
            "scenario": "content_feed",
            "accountRestricted": {"$ne": True},
        }
        if normalized_scenario == "premium_stream":
            query["premiumEligible"] = True
            query["premiumExpiresAt"] = {"$gt": now or datetime.now(timezone.utc)}
        elif normalized_scenario == "travel_photography":
            query["contentVertical"] = "travel_photography"
        elif normalized_scenario != "content_feed":
            raise ValueError("unsupported recommendation ranking scenario")
        return query

    def list_for_ranking(
        self,
        *,
        scenario: str,
        subject_id: str = "",
        limit: int = 500,
        eligible_content_types: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_scenario = scenario.strip()
        bounded_limit = max(1, min(limit, 500))
        query = self.ranking_query(
            "content_feed" if normalized_scenario == "following" else normalized_scenario
        )
        if not self._apply_presentation_filter(query, eligible_content_types):
            return []
        if normalized_scenario == "following":
            followed = self.following_persona_ids(subject_id)
            if not followed:
                return []
            query["authorId"] = {"$in": list(followed)}
            documents = self._recent_lane(query, bounded_limit)
            for document in documents:
                document.setdefault("recallPath", "following_recall")
            return documents
        if normalized_scenario != "content_feed":
            # premium_stream / travel_photography 是路由式单路召回：受众由
            # scenario 过滤器决定，recallPath 归因由 ranker 的既有推导承载。
            return self._recent_lane(query, bounded_limit)
        return self._content_feed_lanes(query, bounded_limit, eligible_content_types)

    def _recent_lane(self, query, limit) -> list[dict[str, Any]]:
        return list(self._candidates.find(query).sort(self._RECENT_SORT).limit(limit))

    def _content_feed_lanes(
        self,
        query: dict[str, Any],
        bounded_limit: int,
        eligible_content_types: tuple[str, ...] | None,
    ) -> list[dict[str, Any]]:
        # content_feed 主场景：多路有界召回（fresh + hot），各路独立 limit，
        # 合并按先出现去重；总量不超过 bounded_limit。协同路由 ranker 按
        # FeatureProfile.collaborativeFeatures 经 list_for_ranking_by_content_ids
        # 追加（本层不知道 subject 特征）。
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for lane, sort_spec, lane_limit in (
            ("explore_recall", self._RECENT_SORT, max(1, (bounded_limit * 3) // 5)),
            (
                "hot_recall",
                (("likeCount", DESCENDING), ("contentId", ASCENDING)),
                max(0, bounded_limit // 4),
            ),
        ):
            if lane_limit <= 0:
                continue
            for document in (
                self._candidates.find(query).sort(sort_spec).limit(lane_limit)
            ):
                content_id = str(document.get("contentId") or "").strip()
                if not content_id or content_id in seen:
                    continue
                seen.add(content_id)
                document.setdefault("recallPath", lane)
                merged.append(document)
                if len(merged) >= bounded_limit:
                    return merged
        if eligible_content_types is not None:
            self._refill_presentable(query, merged, seen, bounded_limit)
        return merged

    @staticmethod
    def _apply_presentation_filter(query, eligible_content_types):
        if eligible_content_types is None:
            return True
        query["contentType"] = {"$in": list(eligible_content_types)}
        return bool(eligible_content_types)

    def _refill_presentable(self, query, merged, seen, limit):
        if len(merged) >= limit:
            return
        # 最多一次定额补查；能力过滤仍在 limit 前，不扩大池或引入无界循环。
        refill_query = {**query, "contentId": {"$nin": list(seen)}}
        for document in self._recent_lane(refill_query, limit - len(merged)):
            document.setdefault("recallPath", "explore_recall")
            merged.append(document)

    def list_for_ranking_by_content_ids(
        self,
        *,
        scenario: str,
        content_ids: tuple[str, ...],
        limit: int = 50,
        eligible_content_types: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """协同召回路：按 contentId 点查候选池（仅返回仍可推荐的候选）。"""
        normalized_ids = tuple(
            dict.fromkeys(value.strip() for value in content_ids if value.strip())
        )
        if not normalized_ids:
            return []
        query = self.ranking_query(scenario)
        if not self._apply_presentation_filter(query, eligible_content_types):
            return []
        query["contentId"] = {"$in": list(normalized_ids[:50])}
        documents = self._recent_lane(query, max(1, min(limit, 50)))
        for document in documents:
            document.setdefault("recallPath", "collaborative_recall")
        return documents

    def list_homepage_candidates(self, *, limit: int = 400) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 400))
        entity_candidates = list(
            self._candidates.find(
                {
                    "sourcePartition": "ordinary",
                    "scenario": "content_feed",
                    "accountRestricted": {"$ne": True},
                    "primaryHomepageId": {"$type": "string", "$ne": ""},
                    "primaryHomepageSnapshot": {"$type": "object"},
                },
                {
                    "_id": 0,
                    "primaryHomepageId": 1,
                    "primaryHomepageSnapshot": 1,
                    "updatedAt": 1,
                },
            )
            .sort([("updatedAt", DESCENDING), ("primaryHomepageId", ASCENDING)])
            .limit(bounded_limit)
        )
        for candidate in entity_candidates:
            candidate["objectKind"] = "entity_homepage"
        return entity_candidates
