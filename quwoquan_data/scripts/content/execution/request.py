"""Strongly typed runtime request for one content execution."""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from core.codec import JsonObject, JsonObjectDecodeError
from core.control_types import TargetSelector


@dataclass(frozen=True, slots=True)
class RuntimeExecutionRequest:
    family_ref: str
    region_ref: str
    selector: TargetSelector
    count: int
    topic: str | None
    source_providers: tuple[str, ...]
    homepage_execution_id: str | None
    target_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.family_ref or not self.region_ref:
            raise ValueError("familyRef and regionRef must be non-empty")
        if not isinstance(self.selector, TargetSelector):
            raise ValueError("selector must be TargetSelector")
        if isinstance(self.count, bool) or self.count < 1:
            raise ValueError("count must be a positive integer")
        if any(not provider.strip() for provider in self.source_providers):
            raise ValueError("sourceProviders must contain non-empty provider IDs")
        if tuple(sorted(set(self.source_providers))) != self.source_providers:
            raise ValueError("sourceProviders must be deduplicated and sorted")
        if len(set(self.target_names)) != len(self.target_names):
            raise ValueError("targetNames must be deduplicated")
        if any(not name.strip() for name in self.target_names):
            raise ValueError("targetNames must contain non-empty values")
        if self.target_names and self.count != len(self.target_names):
            raise ValueError("targetNames count must equal count")

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RuntimeExecutionRequest":
        count = getattr(args, "count", None)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SystemExit("[task execute] GATE_BLOCK --count must be a positive integer")
        family_ref = str(getattr(args, "family", "") or "").strip()
        region_ref = str(getattr(args, "region_ref", "") or "").strip().strip("/")
        selector_raw = str(getattr(args, "selector", "") or "").strip()
        if not family_ref or not region_ref:
            raise SystemExit("[task execute] GATE_BLOCK --family and --region-ref are required")
        try:
            selector = TargetSelector(selector_raw)
        except ValueError as exc:
            choices = ", ".join(item.value for item in TargetSelector)
            raise SystemExit(
                f"[task execute] GATE_BLOCK --selector must be one of: {choices}"
            ) from exc
        topic = str(getattr(args, "topic", "") or "").strip() or None
        homepage_execution_id = str(
            getattr(args, "homepage_execution_id", "") or ""
        ).strip() or None
        providers = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in (getattr(args, "source_providers", ()) or ())
                    if str(value).strip()
                }
            )
        )
        target_names = tuple(
            str(value).strip()
            for value in (getattr(args, "target_names", ()) or ())
            if str(value).strip()
        )
        return cls(
            family_ref=family_ref,
            region_ref=region_ref,
            selector=selector,
            count=count,
            topic=topic,
            source_providers=providers,
            homepage_execution_id=homepage_execution_id,
            target_names=target_names,
        )

    @classmethod
    def from_document(cls, value: object) -> "RuntimeExecutionRequest":
        try:
            document = JsonObject.from_value(value, label="execution request")
            expected = {
                "familyRef",
                "regionRef",
                "selector",
                "count",
                "topic",
                "sourceProviders",
                "homepageExecutionId",
                "targetNames",
            }
            if set(document.to_document()) != expected:
                raise JsonObjectDecodeError(
                    "execution request keys must be exactly "
                    + ", ".join(sorted(expected))
                )
            return cls(
                family_ref=document.string("familyRef"),
                region_ref=document.string("regionRef").strip().strip("/"),
                selector=TargetSelector(document.string("selector")),
                count=document.integer("count"),
                topic=document.optional_string("topic"),
                source_providers=document.string_list("sourceProviders"),
                homepage_execution_id=document.optional_string("homepageExecutionId"),
                target_names=document.string_list("targetNames"),
            )
        except (JsonObjectDecodeError, ValueError) as exc:
            raise SystemExit(f"[task execute] GATE_BLOCK invalid frozen request: {exc}") from exc

    def to_document(self) -> dict[str, object]:
        return {
            "familyRef": self.family_ref,
            "regionRef": self.region_ref,
            "selector": self.selector.value,
            "count": self.count,
            "topic": self.topic,
            "sourceProviders": list(self.source_providers),
            "homepageExecutionId": self.homepage_execution_id,
            "targetNames": list(self.target_names),
        }


__all__ = ["RuntimeExecutionRequest"]
