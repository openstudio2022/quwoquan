# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from content.execution.planning.discover_image_supported_api_metadata import (
    register_discover_image_supported_api_metadata_parser,
)
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from content.source.professional_image_supported_api_contract import verify_plan
from content.source.professional_image_supported_api_metadata import (
    METADATA_INVALID,
    RATE_LIMITED,
    SOURCE_POOL_SHORTFALL,
    ProfessionalImageSupportedApiMetadataError,
    discover_supported_api_metadata,
)

_D_REVISION = "sha256:" + "1" * 64
_D_SOURCE = "sha256:" + "2" * 64
_D_ENTITY = "sha256:" + "3" * 64
_D_HANDOFF = "sha256:" + "4" * 64
_D_PLAN = (  # sha256("plan")
    "sha256:64879f7d6b960a01909762d911a32d4582c20010c5641ee90278b644a9e3b525"
)
_D_CATALOG = (  # sha256("catalog")
    "sha256:652f55016243bf1b9f1bbea46d5749ef892dbe394e46de9d66ab1aacf0b4af57"
)


def _plan(tmp_path: Path) -> tuple[dict, Path]:
    return create_professional_image_discovery_plan(
        entities=["西湖"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="航拍",
        popularity="热门",
        output_root=tmp_path / "plans",
    )


def _handoff(*, entity_digest: str = _D_ENTITY) -> dict:
    return {
        "handoffId": "m100-image-input",
        "handoffRevision": 1,
        "handoffDigest": _D_HANDOFF,
        "sourceRevision": _D_REVISION,
        "sourceDigest": {"digest": _D_SOURCE},
        "entityCatalogDigest": entity_digest,
    }


def _entity_loader(_path: Path):
    return (
        "quwoquan_data/reference/travel/entities/china",
        _D_ENTITY,
        {
            "西湖": {
                "entityId": "西湖",
                "entityAliases": ["杭州西湖", "西湖"],
            }
        },
    )


def _page(index: int, *, panoramio: bool = False) -> dict:
    title = (
        f"File:Panoramio West Lake {index}.jpg"
        if panoramio
        else f"File:West Lake governed {index}.jpg"
    )
    description = (
        "Imported from Panoramio"
        if panoramio
        else f"West Lake governed landscape {index}"
    )

    def value(text: str) -> dict[str, str]:
        return {"value": text}

    return {
        "pageid": index,
        "title": title,
        "imageinfo": [
            {
                "url": (
                    "https://upload.wikimedia.org/wikipedia/commons/a/ab/"
                    f"west-lake-{index}.jpg"
                ),
                "descriptionurl": (
                    "https://commons.wikimedia.org/wiki/File:West_Lake_"
                    f"governed_{index}.jpg"
                ),
                "width": 1600,
                "height": 1200,
                "extmetadata": {
                    "Artist": value(f"Commons Photographer {index}"),
                    "LicenseShortName": value("CC BY-SA 4.0"),
                    "LicenseUrl": value(
                        "https://creativecommons.org/licenses/by-sa/4.0/"
                    ),
                    "ImageDescription": value(description),
                },
            }
        ],
    }


def _openverse_row(index: int, *, license_slug: str = "by-sa") -> dict:
    asset_id = f"00000000-0000-4000-8000-{index:012d}"
    return {
        "id": asset_id,
        "title": f"西湖 governed landscape {index}",
        "creator": f"Openverse Photographer {index}",
        "license": license_slug,
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "foreign_landing_url": f"https://www.flickr.com/photos/example/{index}",
        "url": f"https://live.staticflickr.com/1/image-{index}.jpg",
        "provider": "flickr",
        "source": "flickr",
        "width": 1600,
        "height": 1200,
        "mature": False,
        "attribution": f"Openverse Photographer {index} · CC BY-SA 4.0",
    }


def _transport(url: str, body: bytes) -> dict:
    host = str(urlparse(url).hostname)
    return {
        "schema": "quwoquan_data.professional_image_https_transport_evidence",
        "admissionRevision": "professional-image-network-admission-v1",
        "admissionMode": "public_dns",
        "requestedUrl": url,
        "finalUrl": url,
        "requestHost": host,
        "finalHost": host,
        "resolvedAddresses": ["203.0.113.8"],
        "peerAddress": "203.0.113.8",
        "tls": {
            "serverHostname": host,
            "version": "TLSv1.3",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "peerCertificateSha256": "sha256:" + "9" * 64,
            "systemTrustVerified": True,
            "hostnameVerified": True,
        },
        "httpStatus": 200,
        "contentType": "application/json",
        "responseBytes": len(body),
        "responseSha256": "sha256:" + hashlib.sha256(body).hexdigest(),
    }


def _fetch_payload(pages: list[dict], calls: list[str]):
    def fetch(url: str) -> dict:
        calls.append(url)
        assert parse_qs(urlparse(url).query)["generator"] == ["search"]
        payload = {"query": {"pages": pages}}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return {
            "bytes": body,
            "payload": payload,
            "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
            "transportEvidence": _transport(url, body),
        }

    return fetch


def _options(tmp_path: Path, *, target: int) -> dict:
    _plan_payload, plan_path = _plan(tmp_path)
    observed_identities: list[dict] = []

    def guard(identity, **_kwargs):
        observed_identities.append(dict(identity))
        assert identity == {
            "sourceRevision": _D_REVISION,
            "sourceDigest": _D_SOURCE,
            "entityCatalogDigest": _D_ENTITY,
        }
        return _handoff()

    return {
        "handoff_ref": tmp_path / "handoff.json",
        "discovery_plan_path": plan_path,
        "entity_catalog_path": tmp_path / "entity-catalog",
        "candidate_target": target,
        "results_per_query": 50,
        "output_root": tmp_path / "output",
        "handoff_loader": lambda _path: _handoff(),
        "identity_guard": guard,
        "entity_loader": _entity_loader,
        "clock": lambda: "2026-08-11T11:00:00Z",
    }


def _checkpoint(output_root: Path, error: ProfessionalImageSupportedApiMetadataError) -> dict:
    return json.loads((output_root / error.receipt_ref).read_text(encoding="utf-8"))


def test_discovery_excludes_eleven_panoramio_and_create_once_replays(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    pages = [_page(index, panoramio=index <= 11) for index in range(1, 42)]
    options = _options(tmp_path, target=30)
    receipt, receipt_path, catalog_path = discover_supported_api_metadata(
        **options, api_fetcher=_fetch_payload(pages, calls)
    )

    assert len(calls) == 1
    assert receipt["status"] == "completed"
    assert receipt["candidateCount"] == 30
    assert receipt["excludedCount"] == 11
    assert receipt["shortfallCount"] == 0
    assert {
        row["failureCode"] for row in receipt["exclusions"]
    } == {"DATA.SOURCE.WATERMARK_BLOCKED"}
    assert catalog_path is not None
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["candidateCount"] == catalog["targetCandidateCount"] == 30
    assert catalog["excludedCount"] == 11
    assert all("panoramio" not in row["fileTitle"].casefold() for row in catalog["candidates"])
    assert all(
        row["sourcePageUrl"].startswith("https://commons.wikimedia.org/")
        and row["originalAssetUrl"].startswith("https://upload.wikimedia.org/")
        and row["creator"]
        and row["license"] == "CC BY-SA 4.0"
        and row["queryId"].startswith("commons-query-")
        for row in catalog["candidates"]
    )

    replay, replay_receipt_path, replay_catalog_path = discover_supported_api_metadata(
        **options,
        api_fetcher=lambda _url: pytest.fail("create-once replay refetched Commons"),
    )
    assert replay["receiptDigest"] == receipt["receiptDigest"]
    assert replay_receipt_path == receipt_path
    assert replay_catalog_path == catalog_path

    catalog_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ProfessionalImageSupportedApiMetadataError) as collision:
        discover_supported_api_metadata(
            **options,
            api_fetcher=lambda _url: pytest.fail("collision path refetched Commons"),
        )
    assert collision.value.code == METADATA_INVALID
    assert "create-once collision" in str(collision.value)


def test_commons_empty_search_is_completed_zero_candidate_query(
    tmp_path: Path,
) -> None:
    options = _options(tmp_path, target=1)
    options["providers"] = ("wikimedia_commons",)
    calls: list[str] = []

    def fetch(url: str) -> dict:
        calls.append(url)
        payload = {"batchcomplete": True}
        body = json.dumps(payload).encode("utf-8")
        return {
            "bytes": body,
            "payload": payload,
            "transportEvidence": _transport(url, body),
        }

    with pytest.raises(ProfessionalImageSupportedApiMetadataError) as captured:
        discover_supported_api_metadata(**options, api_fetcher=fetch)

    assert captured.value.code == SOURCE_POOL_SHORTFALL
    receipt = _checkpoint(options["output_root"], captured.value)
    assert len(calls) == 2
    assert receipt["completedQueryCount"] == 2
    assert receipt["candidateCount"] == 0
    assert receipt["failures"] == []
    assert [row["status"] for row in receipt["items"]] == ["completed", "completed"]


def test_verify_plan_binds_requested_alias_to_metadata_observation() -> None:
    plan = {
        "planId": "plan-alias",
        "planDigest": _D_PLAN,
        "catalogRef": "catalog",
        "catalogDigest": _D_CATALOG,
        "dimensions": {},
        "candidateCount": 1,
        "providerCandidateCounts": [],
        "candidates": [{
            "candidateId": "wikimedia_commons:plan-alias",
            "provider": "wikimedia_commons",
            "entity": "West Lake Hangzhou",
            "acquisitionPaths": ["supported_api"],
        }],
    }
    catalog = {
        "discoveryPlanId": "plan-alias",
        "discoveryPlanDigest": _D_PLAN,
        "candidates": [{
            "candidateId": "wikimedia_commons:asset",
            "discoveryCandidateId": "wikimedia_commons:plan-alias",
            "provider": "wikimedia_commons",
            "entityId": "杭州西湖",
            "observedEntityId": "West Lake Hangzhou",
        }],
    }

    assert verify_plan(plan, catalog, digest=lambda _value: _D_PLAN) == {
        "wikimedia_commons:plan-alias": plan["candidates"][0]
    }


def test_discovery_projects_openverse_asset_identity_and_rights(tmp_path: Path) -> None:
    options = _options(tmp_path, target=2)
    options["providers"] = ("openverse",)
    options["physical_evidence_root"] = tmp_path / "physical-evidence"

    def fetch(url: str) -> dict:
        payload = (
            {"results": [_openverse_row(1), _openverse_row(2)]}
            if "api.openverse.org" in url
            else {"query": {"pages": []}}
        )
        body = json.dumps(payload).encode("utf-8")
        return {
            "bytes": body,
            "payload": payload,
            "transportEvidence": _transport(url, body),
        }

    receipt, receipt_path, catalog_path = discover_supported_api_metadata(
        **options, api_fetcher=fetch
    )
    assert receipt["status"] == "completed"
    assert receipt["requestedProviders"] == ["openverse"]
    assert catalog_path is not None
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["requestedProviders"] == ["openverse"]
    rows = catalog["candidates"]
    assert [row["provider"] for row in rows] == ["openverse", "openverse"]
    assert all(
        row["providerAssetId"].startswith("00000000-")
        and row["upstreamProvider"] == "flickr"
        and row["sourcePageUrl"].startswith("https://www.flickr.com/")
        and row["originalAssetUrl"].startswith("https://live.staticflickr.com/")
        and row["license"] == "CC BY-SA 4.0"
        for row in rows
    )

    replay, replay_receipt_path, replay_catalog_path = discover_supported_api_metadata(
        **options,
        api_fetcher=lambda _url: pytest.fail("create-once replay refetched Openverse"),
    )
    assert replay["receiptDigest"] == receipt["receiptDigest"]
    assert replay_receipt_path == receipt_path
    assert replay_catalog_path == catalog_path



def test_rate_limit_keeps_partial_success_and_resume_fetches_only_missing_query(
    tmp_path: Path,
) -> None:
    options = _options(tmp_path, target=3)
    calls: list[str] = []

    def first_fetch(url: str) -> dict:
        calls.append(url)
        if len(calls) == 1:
            return _fetch_payload([_page(101), _page(102)], [])(url)
        raise urllib.error.HTTPError(url, 429, "rate limited", None, None)

    with pytest.raises(ProfessionalImageSupportedApiMetadataError) as captured:
        discover_supported_api_metadata(**options, api_fetcher=first_fetch)
    assert captured.value.code == SOURCE_POOL_SHORTFALL
    partial = _checkpoint(options["output_root"], captured.value)
    assert partial["status"] == "partial"
    assert partial["candidateCount"] == 2
    assert partial["shortfallCount"] == 1
    assert partial["failures"] == [
        {
            "queryId": partial["failures"][0]["queryId"],
            "failureCode": RATE_LIMITED,
            "retryable": True,
            "detail": "Commons metadata request failed (429)",
        }
    ]

    resumed_calls: list[str] = []
    receipt, _receipt_path, catalog_path = discover_supported_api_metadata(
        **options,
        api_fetcher=_fetch_payload([_page(103)], resumed_calls),
    )
    assert len(resumed_calls) == 1
    assert receipt["status"] == "completed"
    assert receipt["candidateCount"] == 3
    assert receipt["shortfallCount"] == 0
    assert catalog_path is not None


def test_handoff_entity_catalog_drift_blocks_before_provider_call(tmp_path: Path) -> None:
    options = _options(tmp_path, target=1)
    calls: list[str] = []
    options["handoff_loader"] = lambda _path: _handoff(
        entity_digest="sha256:" + "9" * 64
    )
    with pytest.raises(ProfessionalImageSupportedApiMetadataError) as captured:
        discover_supported_api_metadata(
            **options, api_fetcher=_fetch_payload([_page(201)], calls)
        )
    assert captured.value.code == METADATA_INVALID
    assert "differs from current handoff" in str(captured.value)
    assert calls == []


def test_cli_exposes_only_governed_inputs() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    register_discover_image_supported_api_metadata_parser(commands)
    args = parser.parse_args(
        [
            "discover-image-supported-api-metadata",
            "--handoff-ref",
            "/tmp/handoff.json",
            "--discovery-plan",
            "/tmp/plan.json",
            "--entity-catalog",
            "/tmp/entities",
            "--candidate-target",
            "30",
            "--provider",
            "openverse",
        ]
    )
    assert args.candidate_target == 30
    assert args.results_per_query == 50
    assert args.providers == ["openverse"]
    assert not hasattr(args, "operator_verdict")
    assert not hasattr(args, "original_asset")
