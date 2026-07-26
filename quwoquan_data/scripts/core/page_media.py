"""Typed contracts for source-page images and homepage asset disposition."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class PageImagePlacementType(StrEnum):
    LEAD = "lead"
    INFOBOX_LEAD = "infoboxLead"
    INLINE = "inline"
    GROUP_MEMBER = "groupMember"
    LOCATOR_MAP = "locatorMap"


class HomepageAssetDisposition(StrEnum):
    COVER = "cover"
    INLINE = "inline"
    RELATED = "related"
    POLICY_EXCLUDED = "policyExcluded"
    DUPLICATE_ALIAS = "duplicateAlias"


class PageImageDropCode(StrEnum):
    """Closed terminal outcomes for enumerated images not kept as assets."""

    INVALID_PAYLOAD = "invalid_payload"
    RIGHTS_POLICY = "rights_policy"
    FETCH_FAILURE = "fetch_failure"
    DECODE_POLICY = "decode_policy"
    PIXEL_POLICY = "pixel_policy"
    SAFETY_POLICY = "safety_policy"
    RELEVANCE_POLICY = "relevance_policy"
    DUPLICATE = "duplicate"

    @property
    def is_policy_outcome(self) -> bool:
        return self is not PageImageDropCode.FETCH_FAILURE


@dataclass(frozen=True, slots=True)
class HomepageMediaDisposition:
    """A complete, typed disposition for one enumerated source-page image.

    Final homepage manifests intentionally contain only published assets. This
    record closes the other half of the contract: every downloaded page image
    that is not published must carry one explicit policy or deduplication
    outcome in runtime evidence.
    """

    source_asset_ref: str
    disposition: HomepageAssetDisposition
    reason: str
    source_asset_id: str = ""
    asset_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_asset_ref.strip():
            raise ValueError("HomepageMediaDisposition.source_asset_ref must not be empty")
        if not self.reason.strip():
            raise ValueError("HomepageMediaDisposition.reason must not be empty")
        if self.disposition is HomepageAssetDisposition.POLICY_EXCLUDED and self.asset_id:
            raise ValueError("policyExcluded image must not reference a published asset")

    def as_dict(self) -> dict[str, str]:
        return {
            "sourceAssetRef": self.source_asset_ref,
            "sourceAssetId": self.source_asset_id,
            "disposition": self.disposition.value,
            "assetId": self.asset_id,
            "reason": self.reason,
        }


_DIMENSION_TOKEN_RE = re.compile(
    r"^(?:x\s*)?\d+\s*px$|^\d+\s*[x×]\s*\d+\s*px$",
    re.IGNORECASE,
)
_SUBJECT_NOISE_RE = re.compile(r"[\W_]+", re.UNICODE)


def is_image_dimension_token(value: str) -> bool:
    return bool(_DIMENSION_TOKEN_RE.fullmatch(str(value or "").strip()))


def normalized_subject_key(caption: str, file_title: str = "") -> str:
    """Return a deterministic visual-subject key without model inference."""
    text = str(caption or "").strip()
    if not text or is_image_dimension_token(text):
        text = str(file_title or "").rsplit("/", 1)[-1]
        if ":" in text:
            text = text.split(":", 1)[1]
        text = re.sub(r"\.(?:jpe?g|png|webp|gif|tiff?)$", "", text, flags=re.I)
    text = unicodedata.normalize("NFKC", text).casefold()
    return _SUBJECT_NOISE_RE.sub("", text)


def normalized_subject_core(subject_key: str, *, entity_name: str = "") -> str:
    subject = normalized_subject_key(subject_key)
    entity = normalized_subject_key(entity_name)
    if entity and subject.startswith(entity):
        subject = subject[len(entity) :]
    return re.sub(r"(?:立像|雕像|塑像|像|全景|照片|景观)$", "", subject)


def subject_keys_conflict(left: str, right: str, *, entity_name: str = "") -> bool:
    left_core = normalized_subject_core(left, entity_name=entity_name)
    right_core = normalized_subject_core(right, entity_name=entity_name)
    if not left_core or not right_core:
        return False
    return (
        left_core == right_core
        or (len(left_core) >= 4 and left_core in right_core)
        or (len(right_core) >= 4 and right_core in left_core)
    )


@dataclass(frozen=True, slots=True)
class PageImagePlacement:
    file_title: str
    caption: str
    section_slug: str
    paragraph_index: int
    source_order: int
    placement_type: PageImagePlacementType
    group_id: str = ""
    cover_rank: int = 0
    placeholder_id: str = ""
    subject_key: str = ""
    is_map_like: bool = False

    def __post_init__(self) -> None:
        if not self.file_title.strip():
            raise ValueError("PageImagePlacement.file_title must not be empty")
        if self.paragraph_index < 0 or self.source_order < 0:
            raise ValueError("PageImagePlacement indexes must be non-negative")
        if self.placement_type is PageImagePlacementType.LOCATOR_MAP and self.cover_rank >= 0:
            raise ValueError("locatorMap must have a negative cover rank")
        if self.placement_type is PageImagePlacementType.GROUP_MEMBER and not self.group_id:
            raise ValueError("groupMember must declare group_id")
        if not self.subject_key:
            object.__setattr__(
                self,
                "subject_key",
                normalized_subject_key(self.caption, self.file_title),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "fileName": self.file_title,
            "caption": self.caption,
            "sectionSlug": self.section_slug,
            "paragraphIndex": self.paragraph_index,
            "sourceOrder": self.source_order,
            "placementType": self.placement_type.value,
            "groupId": self.group_id,
            "coverCandidateRank": self.cover_rank,
            "placeholderId": self.placeholder_id,
            "subjectKey": self.subject_key,
            "isMapLike": self.is_map_like,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PageImagePlacement":
        return cls(
            file_title=str(payload.get("fileName") or payload.get("fileTitle") or ""),
            caption=str(payload.get("caption") or ""),
            section_slug=str(payload.get("sectionSlug") or ""),
            paragraph_index=int(payload.get("paragraphIndex") or 0),
            source_order=int(payload.get("sourceOrder") or 0),
            placement_type=PageImagePlacementType(
                str(payload.get("placementType") or PageImagePlacementType.INLINE.value)
            ),
            group_id=str(payload.get("groupId") or ""),
            cover_rank=int(payload.get("coverCandidateRank") or 0),
            placeholder_id=str(payload.get("placeholderId") or ""),
            subject_key=str(payload.get("subjectKey") or ""),
            is_map_like=bool(payload.get("isMapLike")),
        )


@dataclass(frozen=True, slots=True)
class DownloadedPageAsset:
    placement: PageImagePlacement
    content: bytes
    ext: str
    url: str
    requested_url: str
    source_url: str
    content_type: str
    width: int
    height: int
    license_name: str
    credit: str
    terms_url: str
    authorization_proof: str

    def __post_init__(self) -> None:
        if not self.content or not self.url.strip() or self.width <= 0 or self.height <= 0:
            raise ValueError("DownloadedPageAsset requires downloaded image bytes, URL and dimensions")
        if not self.license_name.strip() or not self.authorization_proof.strip():
            raise ValueError("DownloadedPageAsset requires rights evidence")

    def as_dict(self) -> dict[str, Any]:
        return {
            "bytes": self.content,
            "ext": self.ext,
            "url": self.url,
            "requestedUrl": self.requested_url,
            "sourceUrl": self.source_url,
            "contentType": self.content_type,
            "width": self.width,
            "height": self.height,
            "license": self.license_name,
            "credit": self.credit,
            "termsUrl": self.terms_url,
            "authorizationProof": self.authorization_proof,
            "caption": self.placement.caption,
            "placeholderId": self.placement.placeholder_id,
            "placementType": self.placement.placement_type.value,
            "groupId": self.placement.group_id,
            "sectionSlug": self.placement.section_slug,
            "sourceOrder": self.placement.source_order,
            "coverCandidateRank": self.placement.cover_rank,
            "subjectKey": self.placement.subject_key,
            "isMapLike": self.placement.is_map_like,
            "fileTitle": self.placement.file_title,
        }


__all__ = [
    "HomepageAssetDisposition",
    "HomepageMediaDisposition",
    "DownloadedPageAsset",
    "PageImagePlacement",
    "PageImagePlacementType",
    "PageImageDropCode",
    "is_image_dimension_token",
    "normalized_subject_key",
    "normalized_subject_core",
    "subject_keys_conflict",
]
