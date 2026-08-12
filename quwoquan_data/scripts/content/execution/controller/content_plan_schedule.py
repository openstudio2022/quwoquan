"""Creator assignment and deterministic publication scheduling for content plans."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping

from content.templates.registry import TemplateRegistry
from governance.creators.assignment import resolve_registry_creator_assignment


@dataclass
class ContentPlanScheduler:
    execution_id: str
    region: str
    daily_object_target: int
    registry: TemplateRegistry
    creator_day_counts: dict[str, Counter[int]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    day_object_counts: Counter[int] = field(default_factory=Counter)

    @classmethod
    def load(
        cls,
        *,
        execution_id: str,
        region: str,
        daily_object_target: int,
    ) -> "ContentPlanScheduler":
        if daily_object_target < 1:
            raise ValueError("daily_object_target must be positive")
        registry = TemplateRegistry.load()
        if not registry.creators:
            raise ValueError("creator registry must not be empty")
        return cls(execution_id, region, daily_object_target, registry)

    def assign(
        self,
        *,
        carrier: str,
        target: str,
        intent: str = "",
        topic_tag_refs: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        tags = (
            ["Topic/旅行", f"Topic/地理/行政区/中国/{self.region}"]
            if self.region
            else ["Topic/旅行"]
        )
        if carrier == "image":
            tags.append("Topic/旅行/玩法/摄影旅拍")
        tags.extend(str(ref) for ref in topic_tag_refs if str(ref).strip())
        tags = list(dict.fromkeys(tags))
        return resolve_registry_creator_assignment(
            {"carrier": carrier, "vertical": "travel", "creatorPersona": {}},
            carrier=carrier,
            tag_refs=tags,
            region=self.region or None,
            vertical="travel",
            seed=(
                f"{self.execution_id}|{self.execution_id}|{target}|{intent}|{carrier}"
            ),
            preferred_archetype="",
            selection_mode="spread",
            registry=self.registry,
        )

    def schedule(self, creator_assignment: Mapping[str, Any]) -> dict[str, Any]:
        creator_id = str(creator_assignment.get("creatorProfileId") or "").strip()
        if creator_id not in self.registry.creators:
            raise ValueError(f"creator assignment is not registered: {creator_id!r}")
        cadence = self.registry.creators[creator_id].get("publishCadence")
        if not isinstance(cadence, Mapping):
            raise ValueError(f"creator publishCadence is missing: {creator_id}")
        creator_daily_limit = int(cadence.get("maxDailyPosts") or 0)
        if creator_daily_limit < 1:
            raise ValueError(f"creator publishCadence.maxDailyPosts is invalid: {creator_id}")

        day = 0
        while (
            self.creator_day_counts[creator_id][day] >= creator_daily_limit
            or self.day_object_counts[day] >= self.daily_object_target
        ):
            day += 1
        slot = self.day_object_counts[day]
        self.creator_day_counts[creator_id][day] += 1
        self.day_object_counts[day] += 1
        return {
            "mode": "deterministic_creator_day_spread",
            "dayOffset": day,
            "slotIndex": slot,
            "targetDailyObjects": self.daily_object_target,
            "maxDailyPostsPerCreator": creator_daily_limit,
        }


__all__ = ["ContentPlanScheduler"]
