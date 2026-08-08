from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from content.source.professional_image_discovery_public import (
    DISCOVERY_RESTRICTED,
    SOURCE_POOL_SHORTFALL,
    ProfessionalImagePublicDiscoveryError,
    build_professional_image_public_candidate_catalog,
    write_professional_image_public_candidate_catalog,
)
from content.source.professional_image_robots_evidence import (
    build_professional_image_robots_evidence,
)


OBSERVED_AT = "2026-08-08T08:00:00Z"


def _plan(tmp_path: Path) -> dict[str, object]:
    plan, _path = create_professional_image_discovery_plan(
        entities=["西湖"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="航拍",
        popularity="热门",
        output_root=tmp_path / "plans",
    )
    return plan


def _access() -> dict[str, bool]:
    return {
        "anonymousRequest": True,
        "cookiesSent": False,
        "credentialsSent": False,
        "loginRequired": False,
        "captchaRequired": False,
        "paywallRequired": False,
        "technicalRestrictionDetected": False,
    }


def _bind_robots(response: dict[str, object], *, body: str | None = None) -> None:
    provider = str(response["provider"])
    response["robotsEvidence"] = build_professional_image_robots_evidence(
        provider=provider,
        robots_url=(
            "https://www.pinterest.com/robots.txt"
            if provider == "pinterest"
            else "https://tuchong.com/robots.txt"
        ),
        robots_body=body or "User-agent: *\nAllow: /\n",
        user_agent="quwoquan-public-discovery/1",
        target_url=str(response["sourcePageUrl"]),
        observed_at=OBSERVED_AT,
    )


def _pinterest_node(
    *,
    identity: str = "123456",
    asset_url: str = "https://i.pinimg.com/originals/aa/bb/cc/west-lake.jpg",
    creator: str = "Aerial Traveler",
    title: str = "West Lake autumn aerial photography",
) -> dict[str, object]:
    return {
        "id": identity,
        "grid_title": title,
        "pinner": {"full_name": creator},
        "images": {"orig": {"url": asset_url, "width": 2400, "height": 1600}},
    }


def _pinterest_response(*nodes: dict[str, object]) -> dict[str, object]:
    payload = {"props": {"initialReduxState": {"pins": list(nodes)}}}
    return {
        "provider": "pinterest",
        "sourcePageUrl": "https://www.pinterest.com/search/pins/?q=west+lake",
        "statusCode": 200,
        "contentType": "text/html; charset=utf-8",
        "body": (
            "<html><head></head><body><script id='__PWS_DATA__' "
            "type='application/json'>"
            + json.dumps(payload)
            + "</script></body></html>"
        ),
        "accessEvidence": _access(),
        "requestHeaders": {"User-Agent": "quwoquan-public-discovery/1"},
    }


def _tuchong_post(
    *,
    post_id: str = "789",
    asset_url: str = "https://photo.tuchong.com/123/f/987654321.jpg",
    creator: str = "江南摄影师",
    title: str = "西湖秋日航拍",
) -> dict[str, object]:
    return {
        "post_id": post_id,
        "url": f"https://tuchong.com/123/{post_id}/",
        "title": title,
        "site": {"name": creator},
        "images": [
            {
                "source": {
                    "url": asset_url,
                    "width": 3000,
                    "height": 2000,
                }
            }
        ],
    }


def _tuchong_response(*posts: dict[str, object]) -> dict[str, object]:
    return {
        "provider": "tuchong",
        "sourcePageUrl": "https://tuchong.com/feeds/recommend/",
        "statusCode": 200,
        "contentType": "application/json",
        "body": json.dumps({"post_list": list(posts)}, ensure_ascii=False),
        "accessEvidence": _access(),
        "requestHeaders": {"Accept": "application/json"},
    }


def _build(
    tmp_path: Path,
    pinterest: dict[str, object],
    tuchong: dict[str, object],
) -> dict[str, object]:
    plan = _plan(tmp_path)
    bound_responses = [copy.deepcopy(pinterest), copy.deepcopy(tuchong)]
    for response in bound_responses:
        provider = response["provider"]
        response["sourcePageUrl"] = next(
            candidate["discoveryUrl"]
            for candidate in plan["candidates"]
            if candidate["provider"] == provider
        )
        _bind_robots(response)
    return build_professional_image_public_candidate_catalog(
        discovery_plan=plan,
        responses=bound_responses,
        observed_at=OBSERVED_AT,
    )


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def test_public_html_and_api_build_versioned_pinterest_first_catalog(
    tmp_path: Path,
) -> None:
    duplicate = _pinterest_node(identity="123457")
    thumbnail = _pinterest_node(
        identity="123458",
        asset_url="https://i.pinimg.com/236x/aa/bb/cc/west-lake.jpg",
    )
    missing_creator = _pinterest_node(identity="123459", creator="")
    non_https = _pinterest_node(
        identity="123460",
        asset_url="http://i.pinimg.com/originals/aa/bb/cc/insecure.jpg",
    )
    catalog = _build(
        tmp_path,
        _pinterest_response(
            _pinterest_node(), duplicate, thumbnail, missing_creator, non_https
        ),
        _tuchong_response(_tuchong_post()),
    )

    assert catalog["catalogRevision"] == "public-professional-image-candidates-v1"
    assert catalog["candidateCount"] == 2
    assert [row["provider"] for row in catalog["providerCounts"]] == [
        "pinterest",
        "tuchong",
    ]
    assert catalog["providerCounts"][0] == {
        "provider": "pinterest",
        "displayName": "Pinterest",
        "priority": 0,
        "plannedAssetCount": 2,
        "responseCount": 1,
        "discoveredAssetCount": 5,
        "acceptedAssetCount": 1,
        "rejectedAssetCount": 4,
        "duplicateAssetCount": 1,
    }
    assert catalog["providerCounts"][1]["acceptedAssetCount"] == 1
    assert all(row["robotsEvidenceDigest"].startswith("sha256:") for row in catalog["sourceResponses"])
    assert {row["reasonCode"] for row in catalog["rejections"]} == {
        "DATA.SOURCE.DUPLICATE_CANDIDATE",
        "DATA.SOURCE.THUMBNAIL_NOT_ORIGINAL",
        "DATA.SOURCE.CREATOR_MISSING",
        "DATA.SOURCE.NON_HTTPS_OR_FOREIGN_ASSET",
    }
    for candidate in catalog["candidates"]:
        assert candidate["sourcePageUrl"].startswith("https://")
        assert candidate["assetUrl"].startswith("https://")
        assert candidate["creator"]
        assert candidate["title"]
        assert candidate["observedAt"] == OBSERVED_AT
        assert candidate["originalAssetCandidate"] is True

    first = write_professional_image_public_candidate_catalog(
        catalog, output_root=tmp_path / "catalogs"
    )
    second = write_professional_image_public_candidate_catalog(
        catalog, output_root=tmp_path / "catalogs"
    )
    assert first == second
    assert json.loads(first.read_text(encoding="utf-8")) == catalog


def test_catalog_deduplicates_same_original_asset(tmp_path: Path) -> None:
    catalog = _build(
        tmp_path,
        _pinterest_response(_pinterest_node(), _pinterest_node(identity="999999")),
        _tuchong_response(_tuchong_post()),
    )

    pinterest = catalog["providerCounts"][0]
    assert pinterest["discoveredAssetCount"] == 2
    assert pinterest["acceptedAssetCount"] == 1
    assert pinterest["duplicateAssetCount"] == 1


@pytest.mark.parametrize(
    ("pinterest", "reason"),
    [
        (_pinterest_response(_pinterest_node(creator="")), "CREATOR_MISSING"),
        (
            _pinterest_response(
                _pinterest_node(
                    asset_url="http://i.pinimg.com/originals/aa/bb/cc/insecure.jpg"
                )
            ),
            "NON_HTTPS_OR_FOREIGN_ASSET",
        ),
        (
            _pinterest_response(
                _pinterest_node(
                    asset_url="https://i.pinimg.com/474x/aa/bb/cc/thumbnail.jpg"
                )
            ),
            "THUMBNAIL_NOT_ORIGINAL",
        ),
    ],
)
def test_invalid_public_candidates_fail_closed_with_typed_pool_shortfall(
    tmp_path: Path,
    pinterest: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(ProfessionalImagePublicDiscoveryError) as captured:
        _build(tmp_path, pinterest, _tuchong_response(_tuchong_post()))

    assert captured.value.code == SOURCE_POOL_SHORTFALL
    assert reason in str(captured.value)


@pytest.mark.parametrize(
    "mutation",
    ["login", "captcha", "cookie", "controlled_status", "challenge_body", "robots_boolean"],
)
def test_restricted_or_non_anonymous_response_is_rejected_before_parse(
    tmp_path: Path, mutation: str
) -> None:
    pinterest = _pinterest_response(_pinterest_node())
    if mutation == "login":
        pinterest["accessEvidence"]["loginRequired"] = True
    elif mutation == "captcha":
        pinterest["accessEvidence"]["captchaRequired"] = True
    elif mutation == "cookie":
        pinterest["requestHeaders"]["Cookie"] = "must-not-be-consumed"
    elif mutation == "controlled_status":
        pinterest["statusCode"] = 403
    elif mutation == "challenge_body":
        pinterest["body"] = "<html><body>captcha challenge</body></html>"
    elif mutation == "robots_boolean":
        pinterest["accessEvidence"]["robotsAllowed"] = True

    with pytest.raises(ProfessionalImagePublicDiscoveryError) as captured:
        _build(tmp_path, pinterest, _tuchong_response(_tuchong_post()))

    assert captured.value.code == DISCOVERY_RESTRICTED


def test_production_pinterest_search_response_is_blocked_by_bound_robots_evidence(
    tmp_path: Path,
) -> None:
    plan = copy.deepcopy(_plan(tmp_path))
    search_url = "https://www.pinterest.com/search/pins/?q=west+lake"
    for candidate in plan["candidates"]:
        if candidate["provider"] == "pinterest":
            candidate["discoveryUrl"] = search_url
    stable = {
        key: plan[key]
        for key in (
            "catalogRef", "catalogDigest", "dimensions", "candidateCount",
            "providerCandidateCounts", "candidates",
        )
    }
    plan["planDigest"] = _digest(stable)
    plan["planId"] = f"professional-image-discovery-{plan['planDigest'][7:23]}"
    pinterest = _pinterest_response(_pinterest_node())
    pinterest["sourcePageUrl"] = search_url
    _bind_robots(
        pinterest,
        body="User-agent: *\nDisallow: /search/\nAllow: /\n",
    )
    tuchong = _tuchong_response(_tuchong_post())
    tuchong["sourcePageUrl"] = next(
        candidate["discoveryUrl"]
        for candidate in plan["candidates"]
        if candidate["provider"] == "tuchong"
    )
    _bind_robots(tuchong, body="User-agent: *\nAllow: /explore/\n")

    with pytest.raises(ProfessionalImagePublicDiscoveryError) as captured:
        build_professional_image_public_candidate_catalog(
            discovery_plan=plan,
            responses=[pinterest, tuchong],
            observed_at=OBSERVED_AT,
        )

    assert captured.value.code == DISCOVERY_RESTRICTED
    assert "robots policy disallows" in str(captured.value)


def test_catalog_writer_rejects_digest_drift(tmp_path: Path) -> None:
    catalog = _build(
        tmp_path,
        _pinterest_response(_pinterest_node()),
        _tuchong_response(_tuchong_post()),
    )
    drifted = copy.deepcopy(catalog)
    drifted["candidates"][0]["creator"] = "mutated"

    with pytest.raises(ProfessionalImagePublicDiscoveryError, match="digest drift"):
        write_professional_image_public_candidate_catalog(
            drifted, output_root=tmp_path / "catalogs"
        )
