"""JSON admission boundary for the formal video lane."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from content.post.article.draft_io import read_draft_meta, read_writing_pack
from core.content_tags import resolved_content_tag_refs
from core.io import read_json
from core.schema import assert_valid
from governance.creators.assignment import creator_from_payload
from content.post.video.source_video import SourcedVideoEvidence


class VideoReviewDecision(StrEnum):
    APPROVED = "approved"
    REVISION_NEEDED = "revision_needed"


def _string(value: object) -> str:
    return str(value or "").strip()


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := _string(item)))


@dataclass(frozen=True, slots=True)
class VideoCreatorAssignment:
    author_id: str
    creator_profile_id: str
    creator_archetype: str
    creator_profile_digest: str
    disclosure_type: str
    disclosure_visible: bool
    disclosure_text: str
    experience_claim_mode: str
    quality_score: float
    fatigue_score: float
    risk_tier: str

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "VideoCreatorAssignment":
        creator = creator_from_payload(payload)
        disclosure = creator.get("creatorDisclosure")
        disclosure_map = disclosure if isinstance(disclosure, Mapping) else {}
        signals = creator.get("authorQualitySignals")
        signal_map = signals if isinstance(signals, Mapping) else {}
        return cls(
            author_id=_string(creator.get("authorId")),
            creator_profile_id=_string(creator.get("creatorProfileId")),
            creator_archetype=_string(creator.get("creatorArchetype")),
            creator_profile_digest=_string(creator.get("creatorProfileDigest")),
            disclosure_type=_string(disclosure_map.get("type")),
            disclosure_visible=disclosure_map.get("visible") is True,
            disclosure_text=_string(disclosure_map.get("displayText")),
            experience_claim_mode=_string(creator.get("experienceClaimMode")),
            quality_score=float(signal_map.get("qualityScore") or 0),
            fatigue_score=float(signal_map.get("fatigueScore") or 0),
            risk_tier=_string(signal_map.get("riskTier")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "authorId": self.author_id,
            "creatorProfileId": self.creator_profile_id,
            "creatorArchetype": self.creator_archetype,
            "creatorProfileDigest": self.creator_profile_digest,
            "creatorDisclosure": {
                "type": self.disclosure_type,
                "visible": self.disclosure_visible,
                "displayText": self.disclosure_text,
            },
            "experienceClaimMode": self.experience_claim_mode,
            "authorQualitySignals": {
                "qualityScore": self.quality_score,
                "fatigueScore": self.fatigue_score,
                "riskTier": self.risk_tier,
            },
        }


@dataclass(frozen=True, slots=True)
class VideoWritingPack:
    ref: str
    title: str
    entity_refs: tuple[str, ...]
    tag_refs: tuple[str, ...]
    template_id: str
    source_video: SourcedVideoEvidence | None
    creator: VideoCreatorAssignment

    @property
    def primary_entity(self) -> str:
        if not self.entity_refs:
            return ""
        return self.entity_refs[0].rstrip("/").rsplit("/", 1)[-1]

    @property
    def source_paths(self) -> tuple[str, ...]:
        return (self.source_video.source_ref,) if self.source_video is not None else ()

    @property
    def source_urls(self) -> tuple[str, ...]:
        return (
            (self.source_video.source_post_url,)
            if self.source_video is not None
            else ()
        )

    @classmethod
    def from_brief(
        cls,
        ref: str,
        payload: Mapping[str, object],
    ) -> tuple["VideoWritingPack", tuple[str, ...]]:
        raw_source_video = payload.get("sourceVideo")
        failures: list[str] = []
        source_video: SourcedVideoEvidence | None = None
        if isinstance(raw_source_video, Mapping):
            source_video, source_video_issues = SourcedVideoEvidence.from_mapping(
                raw_source_video
            )
            failures.extend(source_video_issues)
        else:
            failures.append("sourceVideo must be an admitted sourced video")
        if payload.get("sourceFrames"):
            failures.append("sourceFrames cannot satisfy the video carrier")
        entity_refs = _strings(payload.get("entityRefs"))
        primary = entity_refs[0].rstrip("/").rsplit("/", 1)[-1] if entity_refs else ""
        title = _string(payload.get("titleHint")) or primary
        return (
            cls(
                ref=ref,
                title=title,
                entity_refs=entity_refs,
                tag_refs=tuple(resolved_content_tag_refs(payload, "video")),
                template_id=(
                    _string(payload.get("templateId"))
                    or "travel.entity.short_video"
                ),
                source_video=source_video,
                creator=VideoCreatorAssignment.from_payload(payload),
            ),
            tuple(failures),
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> "VideoWritingPack":
        ref = _string(payload.get("ref"))
        pack, failures = cls.from_brief(ref, payload)
        if failures:
            raise ValueError("; ".join(failures))
        return replace(
            pack,
            title=_string(payload.get("title")) or pack.title,
            tag_refs=_strings(payload.get("tagRefs")),
            template_id=_string(payload.get("templateId")) or pack.template_id,
        )

    def to_dict(self) -> dict[str, object]:
        if self.source_video is None:
            raise ValueError("video writing pack requires sourceVideo")
        source_video = self.source_video.to_dict()
        primary = self.primary_entity
        return {
            "ref": self.ref,
            "kind": "entity",
            "carrier": "video",
            "title": self.title,
            "entityRefs": list(self.entity_refs),
            "tagRefs": list(self.tag_refs),
            "templateId": self.template_id,
            "sourceVideo": source_video,
            "sourceMode": "sourced_video",
            "assetRefs": [source_video["assetRef"]],
            "sourcePaths": list(self.source_paths),
            "sourceUrls": list(self.source_urls),
            "storySpine": {
                "primaryEntity": primary,
                "routeEntities": [primary] if primary else [],
                "beats": [primary],
            },
            **self.creator.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class VideoDraftMeta:
    ref: str
    generator: str
    status: str
    model: str = ""
    agent_run_id: str = ""
    agent_id: str = ""
    cited_source_paths: tuple[str, ...] = ()
    prompt_sha256: str = ""
    writing_pack_sha256: str = ""
    draft_sha256: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "VideoDraftMeta":
        return cls(
            ref=_string(payload.get("ref")),
            generator=_string(payload.get("generator")),
            status=_string(payload.get("status")),
            model=_string(payload.get("model")),
            agent_run_id=_string(payload.get("agentRunId")),
            agent_id=_string(payload.get("agentId")),
            cited_source_paths=_strings(payload.get("citedSourcePaths")),
            prompt_sha256=_string(payload.get("promptSha256")),
            writing_pack_sha256=_string(payload.get("writingPackSha256")),
            draft_sha256=_string(payload.get("draftSha256")),
            created_at=_string(payload.get("createdAt")),
            updated_at=_string(payload.get("updatedAt")),
        )

    @classmethod
    def pending(
        cls,
        *,
        ref: str,
        cited_source_paths: tuple[str, ...],
    ) -> "VideoDraftMeta":
        return cls(
            ref=ref,
            generator="pending",
            status="pending_agent",
            cited_source_paths=cited_source_paths,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "generator": self.generator,
            "status": self.status,
            "model": self.model or None,
            "agentRunId": self.agent_run_id or None,
            "agentId": self.agent_id or None,
            "citedSourcePaths": list(self.cited_source_paths),
            "promptSha256": self.prompt_sha256 or None,
            "writingPackSha256": self.writing_pack_sha256 or None,
            "draftSha256": self.draft_sha256 or None,
            "selfCheck": {
                "status": "passed" if self.status == "completed" else "pending",
                "issues": [],
            },
            "createdAt": self.created_at or None,
            "updatedAt": self.updated_at or None,
        }


@dataclass(frozen=True, slots=True)
class VideoScriptDraft:
    title: str
    caption: str
    script_lines: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "VideoScriptDraft":
        raw = read_json(path)
        assert_valid(raw, "content", "video_script", label=f"video_script:{path}")
        return cls(
            title=_string(raw.get("title")),
            caption=_string(raw.get("caption")),
            script_lines=_strings(raw.get("scriptLines")),
        )


def load_video_writing_pack(execution_id: str, ref: str) -> VideoWritingPack:
    payload = read_writing_pack(execution_id, ref)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{ref}: video writing pack missing")
    return VideoWritingPack.from_mapping(payload)


def load_video_draft_meta(execution_id: str, ref: str) -> VideoDraftMeta:
    payload = read_draft_meta(execution_id, ref)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{ref}: video draft meta missing")
    return VideoDraftMeta.from_mapping(payload)


__all__ = [
    "VideoCreatorAssignment",
    "VideoDraftMeta",
    "VideoReviewDecision",
    "VideoScriptDraft",
    "VideoWritingPack",
    "load_video_draft_meta",
    "load_video_writing_pack",
]
