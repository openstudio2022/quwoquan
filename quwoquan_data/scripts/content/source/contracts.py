"""Typed source-admission values at the external-provider boundary.

Providers and persisted plans are JSON-shaped.  They are decoded here once;
the source, review, and release layers consume immutable values instead of
making control-flow decisions from ad-hoc dictionaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from core.control_types import ContentType
from governance.coverage.license import audit_image_rights


class AcquisitionMode(StrEnum):
    """The reusable discovery strategy for one carrier."""

    ENTITY_DIRECTORY_LOOKUP = "entity_directory_lookup"
    TOPIC_OR_ENTITY_SEARCH = "topic_or_entity_search"
    PROFESSIONAL_MEDIA_CATALOG = "professional_media_catalog"
    VIDEO_CATALOG_SEARCH = "video_catalog_search"


class HomepageAuthorityProvider(StrEnum):
    """Closed encyclopedia providers admitted for an entity homepage."""

    WIKIPEDIA = "wikipedia"
    BAIDU_BAIKE = "baidu_baike"
    TOUTIAO_BAIKE = "toutiao_baike"


class MatchVerdict(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RightsAuditStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class ModelReleaseStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    OBTAINED = "obtained"
    EDITORIAL_ONLY = "editorial_only"


def acquisition_mode_for_lane(lane: ContentType) -> AcquisitionMode:
    """Map carrier semantics to the only allowed reusable acquisition mode."""

    return {
        ContentType.HOMEPAGE: AcquisitionMode.ENTITY_DIRECTORY_LOOKUP,
        ContentType.ARTICLE: AcquisitionMode.TOPIC_OR_ENTITY_SEARCH,
        ContentType.IMAGE: AcquisitionMode.PROFESSIONAL_MEDIA_CATALOG,
        ContentType.VIDEO: AcquisitionMode.VIDEO_CATALOG_SEARCH,
    }[lane]


def _text(value: object) -> str:
    return str(value or "").strip()


def _confidence(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("source matchConfidence must be numeric") from exc
    if not 0.0 <= result <= 1.0:
        raise ValueError("source matchConfidence must be within [0, 1]")
    return result


@dataclass(frozen=True, slots=True)
class QualifiedHomepageSource:
    """The exact primary authority proven before a homepage target is frozen."""

    provider: HomepageAuthorityProvider
    title: str
    url: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("qualified homepage source requires a title")
        if not self.url.startswith("https://"):
            raise ValueError("qualified homepage source requires an https url")

    @property
    def source_id(self) -> str:
        return {
            HomepageAuthorityProvider.WIKIPEDIA: "home_wikipedia",
            HomepageAuthorityProvider.BAIDU_BAIKE: "home_baidu_baike",
            HomepageAuthorityProvider.TOUTIAO_BAIKE: "home_toutiao_baike",
        }[self.provider]

    @property
    def source_kind(self) -> str:
        return self.provider.value

    @property
    def platform(self) -> str:
        return {
            HomepageAuthorityProvider.WIKIPEDIA: "维基百科",
            HomepageAuthorityProvider.BAIDU_BAIKE: "百度百科",
            HomepageAuthorityProvider.TOUTIAO_BAIKE: "快懂百科",
        }[self.provider]

    @property
    def discovery_provider(self) -> str:
        return {
            HomepageAuthorityProvider.WIKIPEDIA: "mediawiki_exact_title",
            HomepageAuthorityProvider.BAIDU_BAIKE: "baidu_baike_html_resolution",
            HomepageAuthorityProvider.TOUTIAO_BAIKE: "toutiao_baike_canonical_resolution",
        }[self.provider]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "QualifiedHomepageSource":
        provider = HomepageAuthorityProvider(_text(raw.get("provider")))
        return cls(
            provider=provider,
            title=_text(raw.get("title")),
            url=_text(raw.get("url")),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider.value,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """A validated, already-admitted external source candidate."""

    source_id: str
    lane: ContentType
    acquisition_mode: AcquisitionMode
    url: str
    title: str
    match_confidence: float
    match_verdict: MatchVerdict
    rejection_reason: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SourceCandidate":
        lane = ContentType(_text(raw.get("researchLane")))
        url = _text(raw.get("url") or raw.get("link"))
        title = _text(raw.get("sourceTitle") or raw.get("title"))
        source_id = _text(raw.get("source_id") or raw.get("sourceId") or raw.get("id"))
        if not source_id:
            raise ValueError("source candidate requires source_id")
        if not url.startswith("https://"):
            raise ValueError("source candidate requires an https url")
        if lane is ContentType.HOMEPAGE and not title:
            raise ValueError("homepage source candidate requires sourceTitle")

        raw_gate = raw.get("candidateGate")
        gate = raw_gate if isinstance(raw_gate, Mapping) else {}
        issues = tuple(_text(item) for item in gate.get("issues") or () if _text(item))
        passed = gate.get("passed")
        verdict = (
            MatchVerdict.REJECTED
            if passed is False or issues
            else MatchVerdict.ACCEPTED
        )
        return cls(
            source_id=source_id,
            lane=lane,
            acquisition_mode=acquisition_mode_for_lane(lane),
            url=url,
            title=title,
            match_confidence=_confidence(raw.get("matchConfidence") or 0.0),
            match_verdict=verdict,
            rejection_reason="; ".join(issues),
        )

    def require_accepted(self) -> None:
        if self.match_verdict is not MatchVerdict.ACCEPTED:
            raise ValueError(
                f"source candidate is rejected: {self.source_id}: {self.rejection_reason}"
            )


@dataclass(frozen=True, slots=True)
class MediaProvenance:
    """One downloaded media item's source and derived rights audit outcome."""

    source_url: str
    title: str
    caption: str
    license_name: str
    creator: str
    rights_audit_status: RightsAuditStatus
    rights_audit_issues: tuple[str, ...]
    model_release_status: ModelReleaseStatus

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any],
        *,
        vertical: str,
    ) -> "MediaProvenance":
        # modelReleaseStatus is a derived admission declaration.  External page
        # adapters do not all carry it, so materialize the policy default before
        # audit rather than recording a stale "missing" issue and adding the
        # default later during canonical projection.
        model_release = (
            _text(raw.get("modelReleaseStatus"))
            or ModelReleaseStatus.NOT_REQUIRED.value
        )
        model_release_status = ModelReleaseStatus(model_release)
        audit_input = {**raw, "modelReleaseStatus": model_release_status.value}
        issues = tuple(
            sorted(
                {
                    _text(issue)
                    for issue in audit_image_rights(audit_input, vertical=vertical)
                    if _text(issue)
                }
            )
        )
        return cls(
            source_url=_text(raw.get("sourceUrl") or raw.get("url")),
            title=_text(raw.get("title") or raw.get("fileTitle")),
            caption=_text(raw.get("caption")),
            license_name=_text(raw.get("license")),
            creator=_text(raw.get("creator") or raw.get("credit") or raw.get("author")),
            rights_audit_status=(
                RightsAuditStatus.VERIFIED
                if not issues
                else RightsAuditStatus.UNVERIFIED
            ),
            rights_audit_issues=issues,
            model_release_status=model_release_status,
        )

    def audit_fields(self) -> dict[str, object]:
        """Return the only persisted audit values; status is never caller-owned."""

        return {
            "rightsAuditStatus": self.rights_audit_status.value,
            "rightsAuditIssues": list(self.rights_audit_issues),
            "modelReleaseStatus": self.model_release_status.value,
        }


__all__ = [
    "AcquisitionMode",
    "HomepageAuthorityProvider",
    "MatchVerdict",
    "MediaProvenance",
    "ModelReleaseStatus",
    "RightsAuditStatus",
    "SourceCandidate",
    "QualifiedHomepageSource",
    "acquisition_mode_for_lane",
]
