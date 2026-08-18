"""Immutable contracts and persistent budgets for article source discovery."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import fcntl
import json
import os
from pathlib import Path
import threading
from typing import Any, Protocol

from content.source.research.plan_state import _source
from core.data_issue import DataIssue
from core.schema import assert_valid
from core.source_attribution import canonical_source_attribution


EVIDENCE_SCHEMA = "quwoquan.content.article_source_discovery_evidence"
ALLOWED_ADMISSION = "commercial_release"
_PAGE_BUDGET_LOCK = threading.Lock()


def public_article_source_attribution(
    *,
    platform: str,
    canonical_url: str,
    terms_url: str,
    captured_at: str,
) -> dict[str, Any]:
    """Attribution for one registry-admitted public article page.

    The article carrier admits non-encyclopedia sites, so its attribution cannot
    come from the encyclopedia resolver. Every producer of an article base source
    must mint it here, otherwise a source reaches the source unit unattributable
    and its whole entity fails at write time.
    """
    editor = f"{platform}公开页面编辑者"
    return canonical_source_attribution(
        {
            "isOriginal": False,
            "originalCreatorId": None,
            "originalCreatorName": editor,
            "originalCreatorProfileUrl": None,
            "platform": platform,
            "sourcePostUrl": canonical_url,
            "originalAssetUrl": canonical_url,
            "attributionText": f"正文参考来源：{platform}（{editor}）",
            "rightsBasis": "factual_reference_only",
            "commercialAuthorizationStatus": "unverified",
            "publicationAdmission": "research_release",
            "authorizationProofUrl": None,
            "termsUrl": terms_url or None,
            "riskAcceptanceId": None,
            "watermarkStatus": "absent",
            "audioRightsStatus": "no_audio",
            "modelReleaseStatus": "not_required",
            "propertyReleaseStatus": "not_required",
            "collectedAt": captured_at,
            "takedownPolicy": "remove_on_verified_rights_or_source_dispute",
        }
    )


@dataclass(frozen=True, slots=True)
class PublicSearchResult:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class FrontierItem:
    url: str
    title_hint: str
    parent_url: str
    depth: int
    discovery_method: str
    query: str = ""
    expand_only: bool = False
    sitemap: bool = False


class FrontierDecision(StrEnum):
    ACCEPTED = "accepted"
    DISCARDED = "discarded"
    BLOCKED = "blocked"
    EXPANDED = "expanded"


@dataclass(frozen=True, slots=True)
class ArticleFrontierRecord:
    url: str
    canonical_url: str
    parent_url: str
    depth: int
    discovery_method: str
    query: str
    decision: FrontierDecision
    reason: str
    status_code: int = 0
    relevance_score: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "canonicalUrl": self.canonical_url,
            "parentUrl": self.parent_url,
            "depth": self.depth,
            "discoveryMethod": self.discovery_method,
            "query": self.query,
            "decision": self.decision.value,
            "reason": self.reason,
            "statusCode": self.status_code,
            "relevanceScore": round(self.relevance_score, 3),
        }


@dataclass(frozen=True, slots=True)
class ArticleSourceCandidate:
    source_id: str
    site_id: str
    platform: str
    category: str
    canonical_url: str
    title: str
    discovery_method: str
    relevance_score: float
    profile_digest: str
    discovery_query: str = ""

    def as_source(
        self,
        *,
        captured_at: str = "",
        terms_url: str = "",
    ) -> dict[str, object]:
        source = _source(
            source_id=self.source_id,
            platform=self.platform,
            url=self.canonical_url,
            category=self.category,
            discovery_provider=self.discovery_method,
            match_confidence=self.relevance_score,
            evidence_reason=(
                "provider registry admitted public article source discovery; "
                f"site={self.site_id}; policy={self.profile_digest}"
            ),
            source_role="base",
            images=[],
            image_evidence_mode="",
        )
        source["title"] = self.title
        source["publishMediaMode"] = "text_only"
        source["sourceUseMode"] = "factual_reference_only"
        source["articleCommercialAdmission"] = ALLOWED_ADMISSION
        source["articleSiteId"] = self.site_id
        source["sourceDiscoveryProfileDigest"] = self.profile_digest
        source["researchLane"] = "article"
        if captured_at:
            source["sourceAttribution"] = public_article_source_attribution(
                platform=self.platform,
                canonical_url=self.canonical_url,
                terms_url=terms_url,
                captured_at=captured_at,
            )
        return source

    def as_evidence(self) -> dict[str, object]:
        return {
            "sourceId": self.source_id,
            "siteId": self.site_id,
            "canonicalUrl": self.canonical_url,
            "sourceUseMode": "factual_reference_only",
            "discoveryMethod": self.discovery_method,
            "relevanceScore": round(self.relevance_score, 3),
            "title": self.title,
            "query": self.discovery_query,
        }


@dataclass(frozen=True, slots=True)
class ArticleSiteDiscoveryEvidence:
    site_id: str
    rights_policy: str
    robots_policy: str
    terms_url: str
    max_depth: int
    max_pages_per_day: int
    max_requests_per_second: float
    profile_digest: str
    pages_reserved: int
    frontier: tuple[ArticleFrontierRecord, ...]
    issues: tuple[DataIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "siteId": self.site_id,
            "articleCommercialAdmission": ALLOWED_ADMISSION,
            "rightsPolicy": self.rights_policy,
            "robotsPolicy": self.robots_policy,
            "termsUrl": self.terms_url,
            "maxDepth": self.max_depth,
            "maxPagesPerDay": self.max_pages_per_day,
            "maxRequestsPerSecond": round(self.max_requests_per_second, 4),
            "profileDigest": self.profile_digest,
            "pagesReserved": self.pages_reserved,
            "frontier": [record.as_dict() for record in self.frontier],
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class ArticleSourceDiscoveryOutcome:
    entity_id: str
    aliases: tuple[str, ...]
    topics: tuple[str, ...]
    requested_limit: int
    observed_at: str
    frontier_digest: str
    sites: tuple[ArticleSiteDiscoveryEvidence, ...]
    candidates: tuple[ArticleSourceCandidate, ...]

    @property
    def issues(self) -> tuple[DataIssue, ...]:
        return tuple(issue for site in self.sites for issue in site.issues)

    def source_documents(self) -> list[dict[str, object]]:
        terms_by_site = {site.site_id: site.terms_url for site in self.sites}
        return [
            candidate.as_source(
                captured_at=self.observed_at,
                terms_url=terms_by_site.get(candidate.site_id, ""),
            )
            for candidate in self.candidates
        ]

    def as_evidence(self) -> dict[str, object]:
        evidence: dict[str, object] = {
            "schema": EVIDENCE_SCHEMA,
            "entityId": self.entity_id,
            "aliases": list(self.aliases),
            "topics": list(self.topics),
            "requestedLimit": self.requested_limit,
            "observedAt": self.observed_at,
            "frontierDigest": self.frontier_digest,
            "sites": [site.as_dict() for site in self.sites],
            "sources": [candidate.as_evidence() for candidate in self.candidates],
        }
        assert_valid(
            evidence,
            "execution",
            "article_source_discovery_evidence",
            label=f"article_source_discovery:{self.entity_id}",
        )
        return evidence


@dataclass(frozen=True, slots=True)
class PageBudgetReservation:
    allowed: bool
    used_after: int


class DailyPageBudget(Protocol):
    def reserve(
        self,
        site_id: str,
        *,
        day: str,
        max_pages_per_day: int,
    ) -> PageBudgetReservation: ...


class InMemoryDailyPageBudget:
    """Deterministic budget implementation for embedded callers and contracts."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def reserve(
        self,
        site_id: str,
        *,
        day: str,
        max_pages_per_day: int,
    ) -> PageBudgetReservation:
        key = (day, site_id)
        with self._lock:
            used = self._counts.get(key, 0)
            if used >= max_pages_per_day:
                return PageBudgetReservation(False, used)
            used += 1
            self._counts[key] = used
            return PageBudgetReservation(True, used)


class FileDailyPageBudget:
    """Cross-process daily page budget under the disposable Data local root."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            # ``core.paths`` is deliberately reloaded by contract tests that
            # switch disposable roots. Resolve at construction time instead of
            # retaining a stale module-import constant.
            from core import paths

            root = paths.DATA_WORKSPACE_ROOT
        self._root = Path(root) / "article-source-frontier"

    def reserve(
        self,
        site_id: str,
        *,
        day: str,
        max_pages_per_day: int,
    ) -> PageBudgetReservation:
        self._root.mkdir(parents=True, exist_ok=True)
        ledger_path = self._root / f"{day}.json"
        lock_path = self._root / f"{day}.lock"
        with _PAGE_BUDGET_LOCK, lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            payload: dict[str, Any] = {
                "schema": "quwoquan.content.article_frontier_daily_budget",
                "day": day,
                "sites": {},
            }
            if ledger_path.is_file():
                loaded = json.loads(ledger_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict) or loaded.get("day") != day:
                    raise ValueError(f"article frontier daily budget is invalid: {ledger_path}")
                payload = loaded
            sites = payload.setdefault("sites", {})
            if not isinstance(sites, dict):
                raise ValueError(f"article frontier daily budget sites invalid: {ledger_path}")
            used = int(sites.get(site_id) or 0)
            if used >= max_pages_per_day:
                return PageBudgetReservation(False, used)
            used += 1
            sites[site_id] = used
            temporary = ledger_path.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, ledger_path)
            return PageBudgetReservation(True, used)


__all__ = [
    "ALLOWED_ADMISSION",
    "ArticleFrontierRecord",
    "ArticleSiteDiscoveryEvidence",
    "ArticleSourceCandidate",
    "ArticleSourceDiscoveryOutcome",
    "DailyPageBudget",
    "FileDailyPageBudget",
    "FrontierDecision",
    "FrontierItem",
    "InMemoryDailyPageBudget",
    "PageBudgetReservation",
    "PublicSearchResult",
]
