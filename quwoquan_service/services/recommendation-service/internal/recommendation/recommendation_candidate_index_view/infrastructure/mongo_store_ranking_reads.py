"""排序召回读面（``MongoCandidateIndexStore`` mixin）。

拆分自原 ``mongo_store.py``（行数治理）：关注关系读取、场景受众
query 推导、多路有界召回与对象卡候选清单。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ASCENDING, DESCENDING


class MongoCandidateRankingReadOps:
    """召回读操作；集合属性由组合根 ``__init__`` 装配。"""

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
    ) -> list[dict[str, Any]]:
        normalized_scenario = scenario.strip()
        bounded_limit = max(1, min(limit, 500))
        query = self.ranking_query(
            "content_feed" if normalized_scenario == "following" else normalized_scenario
        )
        if normalized_scenario == "following":
            followed = self.following_persona_ids(subject_id)
            if not followed:
                return []
            query["authorId"] = {"$in": list(followed)}
            documents = list(
                self._candidates.find(query)
                .sort([("updatedAt", DESCENDING), ("contentId", ASCENDING)])
                .limit(bounded_limit)
            )
            for document in documents:
                document.setdefault("recallPath", "following_recall")
            return documents
        if normalized_scenario != "content_feed":
            # premium_stream / travel_photography 是路由式单路召回：受众由
            # scenario 过滤器决定，recallPath 归因由 ranker 的既有推导承载。
            return list(
                self._candidates.find(query)
                .sort([("updatedAt", DESCENDING), ("contentId", ASCENDING)])
                .limit(bounded_limit)
            )
        # content_feed 主场景：多路有界召回（fresh + hot），各路独立 limit，
        # 合并按先出现去重；总量不超过 bounded_limit。协同路由 ranker 按
        # FeatureProfile.collaborativeFeatures 经 list_for_ranking_by_content_ids
        # 追加（本层不知道 subject 特征）。
        fresh_limit = max(1, (bounded_limit * 3) // 5)
        hot_limit = max(0, bounded_limit // 4)
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for lane, sort_spec, lane_limit in (
            (
                "explore_recall",
                [("updatedAt", DESCENDING), ("contentId", ASCENDING)],
                fresh_limit,
            ),
            (
                "hot_recall",
                [("likeCount", DESCENDING), ("contentId", ASCENDING)],
                hot_limit,
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
        return merged

    def list_for_ranking_by_content_ids(
        self,
        *,
        scenario: str,
        content_ids: tuple[str, ...],
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """协同召回路：按 contentId 点查候选池（仅返回仍可推荐的候选）。"""
        normalized_ids = tuple(
            dict.fromkeys(value.strip() for value in content_ids if value.strip())
        )
        if not normalized_ids:
            return []
        query = self.ranking_query(scenario)
        query["contentId"] = {"$in": list(normalized_ids[: max(1, min(limit, 50))])}
        documents = list(
            self._candidates.find(query).sort(
                [("updatedAt", DESCENDING), ("contentId", ASCENDING)]
            )
        )
        for document in documents:
            document.setdefault("recallPath", "collaborative_recall")
        return documents

    def list_object_card_candidates(self, *, limit: int = 400) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 400))
        entity_candidates = list(
            self._candidates.find(
                {
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
        gathering_candidates = list(
            self._gathering_candidates.find(
                {"lifecycleStatus": "published"},
                {
                    "_id": 0,
                    "objectKind": 1,
                    "sourceKey": 1,
                    "sourceVersion": 1,
                    "cardDigest": 1,
                    "title": 1,
                    "summary": 1,
                    "coverRef": 1,
                    "tagRefs": 1,
                    "startAt": 1,
                    "endAt": 1,
                    "dateLabel": 1,
                    "placeMode": 1,
                    "coarsePlaceRef": 1,
                    "coarsePlaceLabel": 1,
                    "updatedAt": 1,
                },
            )
            .sort([("updatedAt", DESCENDING), ("sourceKey", ASCENDING)])
            .limit(bounded_limit)
        )

        def order_key(value: Mapping[str, Any]) -> tuple[float, str]:
            updated_at = value.get("updatedAt")
            timestamp = (
                updated_at.timestamp() if isinstance(updated_at, datetime) else 0.0
            )
            identity = str(
                value.get("sourceKey") or value.get("primaryHomepageId") or ""
            )
            return (-timestamp, identity)

        return sorted(
            [*entity_candidates, *gathering_candidates],
            key=order_key,
        )[:bounded_limit]
