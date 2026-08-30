"""Robots, terms, rate-limit, and backoff enforcement for article crawling."""
from __future__ import annotations

from collections.abc import Mapping
import threading
import time
import urllib.parse
import urllib.robotparser

from content.source.research import network_io
from content.source.research.article_frontier_contract import (
    ArticleFrontierRecord,
    FrontierDecision,
)
from content.source.research.article_frontier_profile import (
    canonicalize_article_url,
)
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.rate_limit import SiteRateLimiter
from core.runtime_policy import active_runtime_policy


def network_issue(site_id: str, url: str, *, message: str) -> DataIssue:
    return data_issue(
        DataIssueCode.NETWORK_UNREACHABLE,
        stage=DataIssueStage.SOURCE_PLAN,
        ref=site_id,
        lane=DataIssueLane.ARTICLE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message=message,
        attributes={"siteId": site_id, "url": url[:240]},
    )


def policy_issue(site_id: str, url: str, *, message: str) -> DataIssue:
    return data_issue(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.SOURCE_GATE,
        ref=site_id,
        lane=DataIssueLane.ARTICLE,
        recovery=DataRecoveryAction.STOP,
        message=message,
        attributes={"siteId": site_id, "url": url[:240]},
    )


def fetch_with_backoff(
    url: str,
    *,
    timeout: int,
    backoff_statuses: frozenset[int],
    limiter: SiteRateLimiter | None = None,
) -> network_io.HttpFetchResult:
    response = network_io.HttpFetchResult(
        returncode=-1,
        status_code=0,
        final_url="",
        body=b"",
    )
    for attempt in range(2):
        if limiter is not None:
            limiter.wait()
        response = network_io.fetch_http(url, timeout=timeout)
        if response.status_code not in backoff_statuses or attempt == 1:
            return response
        retry_delay = max(
            1.0,
            float(active_runtime_policy().curl_retry_delay_seconds),
        )
        time.sleep(retry_delay * (2**attempt))
    return response


def robots_for_url(
    url: str,
    *,
    site_id: str,
    timeout: int,
    backoff_statuses: frozenset[int],
) -> tuple[
    urllib.robotparser.RobotFileParser | None,
    ArticleFrontierRecord,
    DataIssue | None,
]:
    parsed = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit(
        ("https", parsed.netloc, "/robots.txt", "", "")
    )
    response = fetch_with_backoff(
        robots_url,
        timeout=timeout,
        backoff_statuses=backoff_statuses,
    )
    if response.returncode != 0 and response.status_code == 0:
        issue = network_issue(
            site_id,
            robots_url,
            message="robots.txt unavailable because network transport failed",
        )
        return None, ArticleFrontierRecord(
            robots_url,
            "",
            "",
            0,
            "robots_policy",
            "",
            FrontierDecision.BLOCKED,
            issue.code.value,
        ), issue
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    if response.status_code == 404:
        parser.parse(["User-agent: *", "Allow: /"])
        return parser, ArticleFrontierRecord(
            robots_url,
            robots_url,
            "",
            0,
            "robots_policy",
            "",
            FrontierDecision.EXPANDED,
            "robots_not_published_default_allow",
            404,
        ), None
    if not response.ok:
        issue = policy_issue(
            site_id,
            robots_url,
            message=(
                "robots.txt policy could not be verified "
                f"(status={response.status_code})"
            ),
        )
        return None, ArticleFrontierRecord(
            robots_url,
            robots_url,
            "",
            0,
            "robots_policy",
            "",
            FrontierDecision.BLOCKED,
            issue.code.value,
            response.status_code,
        ), issue
    parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
    return parser, ArticleFrontierRecord(
        robots_url,
        canonicalize_article_url(robots_url),
        "",
        0,
        "robots_policy",
        "",
        FrontierDecision.EXPANDED,
        "robots_policy_loaded",
        response.status_code,
    ), None


def terms_precheck(
    site: Mapping[str, object],
    *,
    timeout: int,
    backoff_statuses: frozenset[int],
) -> tuple[ArticleFrontierRecord, DataIssue | None]:
    profile = site["siteCrawlProfile"]
    assert isinstance(profile, Mapping)
    site_id = str(site.get("siteId") or "")
    terms_url = str(profile.get("termsUrl") or "")
    response = fetch_with_backoff(
        terms_url,
        timeout=timeout,
        backoff_statuses=backoff_statuses,
    )
    if response.returncode != 0 and response.status_code == 0:
        issue = network_issue(
            site_id,
            terms_url,
            message="terms policy unavailable because network transport failed",
        )
        return ArticleFrontierRecord(
            terms_url,
            "",
            "",
            0,
            "terms_policy",
            "",
            FrontierDecision.BLOCKED,
            issue.code.value,
        ), issue
    if not response.ok:
        issue = policy_issue(
            site_id,
            terms_url,
            message=(
                "terms policy could not be verified "
                f"(status={response.status_code})"
            ),
        )
        return ArticleFrontierRecord(
            terms_url,
            canonicalize_article_url(terms_url),
            "",
            0,
            "terms_policy",
            "",
            FrontierDecision.BLOCKED,
            issue.code.value,
            response.status_code,
        ), issue
    return ArticleFrontierRecord(
        terms_url,
        canonicalize_article_url(response.final_url or terms_url),
        "",
        0,
        "terms_policy",
        "",
        FrontierDecision.EXPANDED,
        "terms_policy_available",
        response.status_code,
    ), None


__all__ = [
    "fetch_with_backoff",
    "network_issue",
    "policy_issue",
    "robots_for_url",
    "terms_precheck",
]
