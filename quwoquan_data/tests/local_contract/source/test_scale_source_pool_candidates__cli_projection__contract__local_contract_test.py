from __future__ import annotations

import argparse
import hashlib
import json

import pytest
from content.source.research.scale_source_pool import (
    SOURCE_POOL_CREATE_ONCE_COLLISION,
    SOURCE_POOL_INVALID,
    ScaleSourcePoolError,
)
from content.source.research.scale_source_pool_candidates import (
    build_scale_source_pool_candidates,
    validate_scale_source_pool_candidates,
    write_create_once_scale_source_pool_candidates,
)

IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _source_attribution(carrier: str) -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "source-author",
        "platform": f"{carrier}-source",
        "sourcePostUrl": f"https://source.example/{carrier}",
        "originalAssetUrl": f"https://source.example/{carrier}/asset",
        "attributionText": f"source-author / {carrier}-source",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-08T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
    }


def _candidate(carrier: str) -> dict[str, object]:
    identity = f"{carrier}-1"
    entity_ref = f"/entity/地点/景区/{identity}"
    object_prefix = {
        "homepage": "entities/地点/景区",
        "article": "posts/article",
        "image": "posts/image",
        "video": "posts/video",
    }[carrier]
    value: dict[str, object] = {
        "candidateId": identity,
        "carrier": carrier,
        "objectRef": f"{object_prefix}/{identity}",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "sourceUnitRef": f"evidence/{identity}/source.json",
        "sourceUnitDigest": _digest([carrier, "source"]),
        "sourceUnitFileSha256": _digest([carrier, "source-file"]),
        "provider": "pinterest" if carrier == "image" else "provider",
        "contentSha256": _digest([carrier, "content"]),
        "acquisitionStatus": "acquired",
        "acquisitionRef": f"evidence/{identity}/acquisition.json",
        "acquisitionDigest": _digest([carrier, "acquisition"]),
        "acquisitionFileSha256": _digest([carrier, "acquisition-file"]),
        "rightsStatus": "unverified",
        "distributionDecision": "research_allowed",
        "rightsRef": f"evidence/{identity}/rights.json",
        "rightsDigest": _digest([carrier, "rights"]),
        "rightsFileSha256": _digest([carrier, "rights-file"]),
        "qualityStatus": "passed",
        "qualityRef": f"evidence/{identity}/quality.json",
        "qualityDigest": _digest([carrier, "quality"]),
        "qualityFileSha256": _digest([carrier, "quality-file"]),
        "generated": False,
        "playabilityRef": None,
        "playabilityDigest": None,
        "playabilityFileSha256": None,
        "videoReadiness": None,
    }
    if carrier in {"homepage", "article"}:
        value["sourceReadyEvidenceRootRef"] = "."
        value["sourceAttribution"] = _source_attribution(carrier)
    if carrier == "article":
        value["publishMediaMode"] = "text_only"
    if carrier == "video":
        value.update(
            {
                "playabilityRef": "evidence/video-1/playability.json",
                "playabilityDigest": _digest([carrier, "playability"]),
                "playabilityFileSha256": _digest(
                    [carrier, "playability-file"]
                ),
                "videoReadiness": {
                    "playable": True,
                    "motion": True,
                    "premiumEligible": True,
                    "playCount": 10,
                    "likeCount": 8,
                    "commentCount": 6,
                    "shareCount": 4,
                    "favoriteCount": 2,
                    "observedAt": "2026-08-08T00:00:00Z",
                    "popularityPercentile": 0.9,
                    "comparisonBucket": {
                        "provider": "provider",
                        "topic": "travel",
                        "timeBucket": "2026-08",
                        "candidateCount": 2,
                    },
                },
            }
        )
    return value


def _projection(
    schema: str,
    *,
    candidates: list[dict[str, object]],
) -> dict[str, object]:
    if schema.endswith("homepage_article_projection"):
        stable: dict[str, object] = {
            "schema": schema,
            **IDENTITY,
            "catalogBindings": [
                {
                    "carrier": carrier,
                    "catalogRef": f"catalogs/{carrier}.json",
                    "catalogDigest": _digest([carrier, "catalog"]),
                    "catalogFileSha256": _digest([carrier, "file"]),
                }
                for carrier in ("homepage", "article")
            ],
            "rowCounts": [
                {"carrier": carrier, "candidateCount": 1}
                for carrier in ("homepage", "article")
            ],
            "rows": candidates,
        }
    else:
        stable = {
            "schema": schema,
            "targetScale": "M100",
            **IDENTITY,
            "inputDocuments": [
                {
                    "kind": "media_receipt",
                    "ref": "evidence/media.json",
                    "documentDigest": _digest(["media", "document"]),
                    "fileSha256": _digest(["media", "file"]),
                }
            ],
            "candidateCount": len(candidates),
            "candidates": candidates,
        }
    return {**stable, "projectionDigest": _digest(stable)}


def _projections() -> tuple[dict[str, object], dict[str, object]]:
    return (
        _projection(
            "quwoquan_data.scale_source_pool_homepage_article_projection",
            candidates=[_candidate("homepage"), _candidate("article")],
        ),
        _projection(
            "quwoquan_data.scale_source_pool_image_video_projection",
            candidates=[_candidate("image"), _candidate("video")],
        ),
    )


def _build() -> dict[str, object]:
    homepage_article, image_video = _projections()
    return build_scale_source_pool_candidates(
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        homepage_article_projection=homepage_article,
        image_video_projection=image_video,
    )


def test_four_carrier_projection_is_deterministic_and_plan_consumable(tmp_path):
    first = _build()
    second = _build()
    assert first == second
    assert [row["carrier"] for row in first["candidateCounts"]] == [
        "homepage",
        "article",
        "image",
        "video",
    ]
    assert first["activeCarriers"] == ["homepage", "article", "image", "video"]
    destination = tmp_path / "candidates.json"
    frozen = write_create_once_scale_source_pool_candidates(destination, first)
    assert write_create_once_scale_source_pool_candidates(destination, second) == frozen

    from content.source.research.handler_cli_io import load_candidates

    assert load_candidates(str(destination)) == first["candidates"]


def test_projection_rejects_cross_carrier_identity_and_duplicate_content():
    homepage_article, image_video = _projections()
    image_video["sourceDigest"] = "sha256:" + "d" * 64
    stable = {
        key: value for key, value in image_video.items() if key != "projectionDigest"
    }
    image_video["projectionDigest"] = _digest(stable)
    with pytest.raises(ScaleSourcePoolError) as captured:
        build_scale_source_pool_candidates(
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            homepage_article_projection=homepage_article,
            image_video_projection=image_video,
        )
    assert captured.value.code == SOURCE_POOL_INVALID
    assert "source identity drift" in str(captured.value)

    homepage_article, image_video = _projections()
    image_video["candidates"][0]["contentSha256"] = homepage_article["rows"][0][
        "contentSha256"
    ]
    stable = {
        key: value for key, value in image_video.items() if key != "projectionDigest"
    }
    image_video["projectionDigest"] = _digest(stable)
    with pytest.raises(ScaleSourcePoolError) as captured:
        build_scale_source_pool_candidates(
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            homepage_article_projection=homepage_article,
            image_video_projection=image_video,
        )
    assert "duplicate cross-carrier contentSha256" in str(captured.value)


def test_current_wave_selects_only_active_carriers_without_video_evidence():
    homepage_article, image_video = _projections()
    image_video["candidates"] = [image_video["candidates"][0]]
    image_video["candidateCount"] = 1
    stable = {
        key: value for key, value in image_video.items() if key != "projectionDigest"
    }
    image_video["projectionDigest"] = _digest(stable)

    result = build_scale_source_pool_candidates(
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        homepage_article_projection=homepage_article,
        image_video_projection=image_video,
        active_carriers=("homepage", "article", "image"),
    )

    assert result["activeCarriers"] == ["homepage", "article", "image"]
    assert [row["candidateCount"] for row in result["candidateCounts"]] == [
        1,
        1,
        1,
        0,
    ]
    assert {row["carrier"] for row in result["candidates"]} == {
        "homepage",
        "article",
        "image",
    }
    assert validate_scale_source_pool_candidates(result) == result
    from content.source.research.scale_source_pool import (
        build_scale_source_pool_plan,
        validate_scale_source_pool,
    )

    plan = build_scale_source_pool_plan(
        pool_id="m100-current-wave",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        created_at="2026-08-11T00:00:00Z",
        candidates=result["candidates"],
    )
    validation = validate_scale_source_pool(plan)
    assert [
        row["actualCandidateCount"] for row in validation["candidateCounts"]
    ] == [1, 1, 1, 0]


def test_active_carrier_without_physical_candidate_fails_closed():
    homepage_article, image_video = _projections()
    image_video["candidates"] = [image_video["candidates"][0]]
    image_video["candidateCount"] = 1
    stable = {
        key: value for key, value in image_video.items() if key != "projectionDigest"
    }
    image_video["projectionDigest"] = _digest(stable)

    with pytest.raises(ScaleSourcePoolError, match="every active carrier"):
        build_scale_source_pool_candidates(
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            homepage_article_projection=homepage_article,
            image_video_projection=image_video,
            active_carriers=("homepage", "article", "image", "video"),
        )


def test_create_once_collision_is_typed(tmp_path):
    destination = tmp_path / "candidates.json"
    destination.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ScaleSourcePoolError) as captured:
        write_create_once_scale_source_pool_candidates(destination, _build())
    assert captured.value.code == SOURCE_POOL_CREATE_ONCE_COLLISION


def test_project_candidates_cli_dispatches_both_canonical_projectors(
    monkeypatch,
    tmp_path,
    capsys,
):
    import content.source.research.handler_cli as handler

    homepage_article, image_video = _projections()
    image_video["candidates"] = [image_video["candidates"][0]]
    image_video["candidateCount"] = 1
    stable = {
        key: value for key, value in image_video.items() if key != "projectionDigest"
    }
    image_video["projectionDigest"] = _digest(stable)
    monkeypatch.setattr(
        handler,
        "project_scale_source_pool_homepage_article",
        lambda **_kwargs: homepage_article,
    )
    monkeypatch.setattr(
        handler,
        "project_scale_source_pool_image_video",
        lambda **_kwargs: image_video,
    )
    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    arguments = parser.parse_args(
        [
            "source-pool",
            "project-candidates",
            "--target-scale",
            "M100",
            "--source-revision",
            IDENTITY["sourceRevision"],
            "--source-digest",
            IDENTITY["sourceDigest"],
            "--entity-catalog-digest",
            IDENTITY["entityCatalogDigest"],
            "--entity-catalog-ref",
            "quwoquan_data/reference/travel/entities/china",
            "--evidence-root",
            str(tmp_path),
            "--output-root",
            str(tmp_path / "output"),
            "--active-carrier",
            "homepage",
            "--active-carrier",
            "article",
            "--active-carrier",
            "image",
            "--homepage-catalog-ref",
            "catalogs/homepage.json",
            "--homepage-catalog-digest",
            _digest(["homepage", "catalog"]),
            "--homepage-catalog-file-sha256",
            _digest(["homepage", "file"]),
            "--article-catalog-ref",
            "catalogs/article.json",
            "--article-catalog-digest",
            _digest(["article", "catalog"]),
            "--article-catalog-file-sha256",
            _digest(["article", "file"]),
            "--source-ready-set-ref",
            "source-ready-sets/homepage-article.json",
            "--source-ready-set-digest",
            _digest(["homepage-article", "batch"]),
            "--source-ready-set-file-sha256",
            _digest(["homepage-article", "batch-file"]),
            "--image-catalog-ref",
            "catalogs/image.json",
            "--image-acquisition-ref",
            "acquisition/image.json",
            "--image-review-ref",
            "review/image.json",
        ]
    )
    arguments.handler(arguments)
    receipt = json.loads(capsys.readouterr().out)
    candidate_path = tmp_path / "output" / receipt["candidatesRef"]
    assert candidate_path.is_file()
    assert receipt["activeCarriers"] == ["homepage", "article", "image"]
    assert receipt["candidateCounts"][-1] == {
        "carrier": "video",
        "candidateCount": 0,
    }
    assert validate_scale_source_pool_candidates(
        json.loads(candidate_path.read_text(encoding="utf-8"))
    )["candidatesDigest"] == receipt["candidatesDigest"]
