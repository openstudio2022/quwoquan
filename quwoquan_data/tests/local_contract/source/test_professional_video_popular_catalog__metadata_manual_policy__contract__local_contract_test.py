from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from content.source.professional_video_catalog_binding import (
    resolve_popular_candidate_binding,
)
from content.source.professional_video_popular_catalog import (
    POPULAR_VIDEO_INVALID,
    POPULAR_VIDEO_SHORTFALL,
    ProfessionalVideoPopularCatalogError,
    build_professional_video_popular_candidate_catalog,
    write_create_once_professional_video_popular_candidate_catalog,
)

IDENTITY = "sha256:" + "1" * 64


def _access() -> dict[str, bool]:
    return {
        "supportedApi": True,
        "cookiesSent": False,
        "loginRequired": False,
        "paywallRequired": False,
        "drmProtected": False,
        "accessControlBypass": False,
    }


def _item(source_id: str, *, score: int, provider: str) -> dict[str, object]:
    return {
        "sourceId": source_id,
        "entityId": "杭州西湖",
        "observedEntityId": "杭州西湖",
        "creator": f"Creator {source_id}",
        "title": f"Popular travel video {source_id}",
        "observedAt": "2026-08-08T09:00:00Z",
        "topic": "travel-landscape",
        "timeBucket": "2026-W32",
        "playCount": score * 100,
        "likeCount": score * 10,
        "commentCount": score,
        "shareCount": score,
        "favoriteCount": score * 2,
    }


def _response(provider: str, *, first: int = 10, second: int = 20) -> dict[str, object]:
    if provider == "bilibili":
        page = "https://www.bilibili.com/video/BV-fixtures"
        api = "https://api.bilibili.com/x/web-interface/archive/stat"
    else:
        page = "https://www.youtube.com/watch?v=fixtures"
        api = "https://www.youtube.com/youtube/v3/videos"
    return {
        "provider": provider,
        "sourcePageUrl": page,
        "apiEvidenceUrl": api,
        "statusCode": 200,
        "contentType": "application/json",
        "accessEvidence": _access(),
        "items": [
            _item(f"{provider}-low", score=first, provider=provider),
            _item(f"{provider}-high", score=second, provider=provider),
        ],
    }


def _write_video(path: Path, *, seed: int, moving: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 180)
    )
    assert writer.isOpened()
    try:
        for index in range(36):
            frame = np.full((180, 320, 3), 20 + seed, dtype=np.uint8)
            left = round(index * 230 / 35) if moving else 50
            cv2.rectangle(frame, (left, 20), (left + 80, 150), (255, 255, 255), -1)
            cv2.putText(
                frame, f"{seed}-{index if moving else 0}", (8, 170),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
            )
            writer.write(frame)
    finally:
        writer.release()
    assert path.stat().st_size > 8_000


def _manual(provider: str, source_id: str, ref: str) -> dict[str, str]:
    page = (
        "https://www.bilibili.com/video/BV-fixtures"
        if provider == "bilibili"
        else "https://www.youtube.com/watch?v=fixtures"
    )
    return {
        "provider": provider,
        "sourceId": source_id,
        "sourcePageUrl": page,
        "manualFileRef": ref,
    }


def _build(root: Path, *, responses: list[dict] | None = None, manifests: list[dict] | None = None) -> dict:
    return build_professional_video_popular_candidate_catalog(
        source_revision=IDENTITY,
        source_digest="sha256:" + "2" * 64,
        entity_catalog_digest="sha256:" + "3" * 64,
        metadata_responses=responses or [_response("bilibili"), _response("youtube")],
        manual_file_manifests=manifests or [],
        evidence_root=root,
    )


def test_popular_catalog_ranks_api_metadata_and_freezes_manual_playable_files(
    tmp_path: Path,
) -> None:
    _write_video(tmp_path / "manual/bilibili.mp4", seed=1)
    _write_video(tmp_path / "manual/youtube.mp4", seed=2)
    manifests = [
        _manual("bilibili", "bilibili-high", "manual/bilibili.mp4"),
        _manual("youtube", "youtube-high", "manual/youtube.mp4"),
    ]
    first = _build(tmp_path, manifests=manifests)
    second = _build(tmp_path, manifests=manifests)

    assert first == second
    assert first["catalogRevision"] == "popular-video-candidates-v1"
    assert first["sourceRevision"] == IDENTITY
    assert first["candidateCount"] == 4
    assert all(row["manualFileRequired"] is True for row in first["candidates"])
    assert all(row["acquisitionStatus"] == "not_acquired" for row in first["candidates"])
    assert all(policy["automaticVideoDownload"] is False for policy in first["providerPolicies"])
    assert all(policy["automaticStreamParsing"] is False for policy in first["providerPolicies"])
    by_id = {(row["provider"], row["sourceId"]): row for row in first["candidates"]}
    high = by_id[("bilibili", "bilibili-high")]
    low = by_id[("bilibili", "bilibili-low")]
    assert high["popularity"]["popularityPercentile"] == 1.0
    assert low["popularity"]["popularityPercentile"] == 0.0
    assert high["popularity"]["comparisonCandidateCount"] == 2
    assert high["manualFileProvided"] is True
    assert high["manualFileSha256"] == "sha256:" + hashlib.sha256(
        (tmp_path / "manual/bilibili.mp4").read_bytes()
    ).hexdigest()
    assert high["manualFileBytes"] == (tmp_path / "manual/bilibili.mp4").stat().st_size
    assert high["mediaProbe"]["playable"] is True
    assert low["manualFileProvided"] is False
    assert low["manualFileRef"] is None

    destination = tmp_path / "frozen" / f"{first['catalogDigest'][7:]}.json"
    assert write_create_once_professional_video_popular_candidate_catalog(
        destination, first
    ) == first
    assert write_create_once_professional_video_popular_candidate_catalog(
        destination, first
    ) == first


def test_popular_catalog_is_identity_and_entity_bound(tmp_path: Path) -> None:
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="must be sha256"):
        build_professional_video_popular_candidate_catalog(
            source_revision="drift",
            source_digest="sha256:" + "2" * 64,
            entity_catalog_digest="sha256:" + "3" * 64,
            metadata_responses=[_response("bilibili")],
            manual_file_manifests=[],
            evidence_root=tmp_path,
        )

    response = _response("bilibili")
    response["items"][0]["observedEntityId"] = "苏州园林"
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="observed entity"):
        _build(tmp_path, responses=[response])


@pytest.mark.parametrize("missing", ["playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"])
def test_popular_catalog_requires_all_five_observed_signals(
    tmp_path: Path, missing: str
) -> None:
    response = _response("bilibili")
    response["items"][0].pop(missing)
    with pytest.raises(ProfessionalVideoPopularCatalogError) as captured:
        _build(tmp_path, responses=[response])
    assert captured.value.code == POPULAR_VIDEO_SHORTFALL
    assert missing in str(captured.value)


def test_popular_catalog_requires_real_comparison_bucket(tmp_path: Path) -> None:
    response = _response("bilibili")
    response["items"] = response["items"][:1]
    with pytest.raises(ProfessionalVideoPopularCatalogError) as captured:
        _build(tmp_path, responses=[response])
    assert captured.value.code == POPULAR_VIDEO_SHORTFALL
    assert "fewer than two" in str(captured.value)


@pytest.mark.parametrize("mutation", ["stream", "cookie", "login", "paywall", "drm"])
def test_popular_catalog_rejects_stream_parsing_and_access_bypass_metadata(
    tmp_path: Path, mutation: str
) -> None:
    response = _response("bilibili")
    if mutation == "stream":
        response["items"][0]["streamUrl"] = "https://example.test/video.mp4"
    elif mutation == "cookie":
        response["accessEvidence"]["cookiesSent"] = True
    elif mutation == "login":
        response["accessEvidence"]["loginRequired"] = True
    elif mutation == "paywall":
        response["accessEvidence"]["paywallRequired"] = True
    elif mutation == "drm":
        response["accessEvidence"]["drmProtected"] = True
    with pytest.raises(ProfessionalVideoPopularCatalogError) as captured:
        _build(tmp_path, responses=[response])
    assert captured.value.code == POPULAR_VIDEO_INVALID


def test_manual_manifest_rejects_missing_symlink_static_and_duplicate_files(
    tmp_path: Path,
) -> None:
    missing = _manual("bilibili", "bilibili-high", "manual/missing.mp4")
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="missing"):
        _build(tmp_path, responses=[_response("bilibili")], manifests=[missing])

    _write_video(tmp_path / "manual/source.mp4", seed=3)
    link = tmp_path / "manual/link.mp4"
    link.symlink_to(tmp_path / "manual/source.mp4")
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="symlink"):
        _build(
            tmp_path,
            responses=[_response("bilibili")],
            manifests=[_manual("bilibili", "bilibili-high", "manual/link.mp4")],
        )

    _write_video(tmp_path / "manual/static.mp4", seed=4, moving=False)
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="not playable motion"):
        _build(
            tmp_path,
            responses=[_response("bilibili")],
            manifests=[_manual("bilibili", "bilibili-high", "manual/static.mp4")],
        )

    duplicate = tmp_path / "manual/duplicate.mp4"
    duplicate.write_bytes((tmp_path / "manual/source.mp4").read_bytes())
    manifests = [
        _manual("bilibili", "bilibili-low", "manual/source.mp4"),
        _manual("bilibili", "bilibili-high", "manual/duplicate.mp4"),
    ]
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="duplicate manual video bytes"):
        _build(tmp_path, responses=[_response("bilibili")], manifests=manifests)


def test_popular_catalog_rejects_metadata_or_manual_source_drift(tmp_path: Path) -> None:
    foreign = _response("bilibili")
    foreign["sourcePageUrl"] = "https://example.test/video/1"
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="host"):
        _build(tmp_path, responses=[foreign])

    _write_video(tmp_path / "manual/video.mp4", seed=5)
    drifted = _manual("bilibili", "bilibili-high", "manual/video.mp4")
    drifted["sourcePageUrl"] = "https://www.bilibili.com/video/other"
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="source page drift"):
        _build(
            tmp_path,
            responses=[_response("bilibili")],
            manifests=[drifted],
        )


def _binding_fixture(tmp_path: Path) -> tuple[dict, dict, Path, Path]:
    manual_root = tmp_path / "manual-root"
    _write_video(manual_root / "popular.mp4", seed=7)
    catalog = _build(
        manual_root,
        responses=[_response("bilibili")],
        manifests=[
            _manual("bilibili", "bilibili-high", "popular.mp4"),
        ],
    )
    catalog_root = tmp_path / "catalog-root"
    catalog_ref = (
        "professional-video-popular-catalogs/"
        f"{catalog['catalogDigest'][7:]}.json"
    )
    destination = catalog_root / catalog_ref
    write_create_once_professional_video_popular_candidate_catalog(destination, catalog)
    candidate = next(
        row for row in catalog["candidates"]
        if row["sourceId"] == "bilibili-high"
    )
    item = {
        "assetId": "popular-video-acquisition",
        "provider": candidate["provider"],
        "entityId": candidate["entityId"],
        "observedEntityId": candidate["observedEntityId"],
        "sourceUrl": candidate["sourcePageUrl"],
        "title": candidate["title"],
        "creator": candidate["creator"],
        "acquisitionPath": "manual_file",
        "manualFile": candidate["manualFileRef"],
        "popularitySignals": {
            **{field: candidate["popularity"][field] for field in (
                "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
            )},
            "observedAt": candidate["observedAt"],
            "provider": candidate["provider"],
            "topic": candidate["topic"],
            "timeBucket": candidate["timeBucket"],
        },
        "popularCandidateId": candidate["candidateId"],
        "popularCatalogRef": catalog_ref,
        "popularCatalogDigest": catalog["catalogDigest"],
        "popularCatalogFileSha256": "sha256:" + hashlib.sha256(
            destination.read_bytes()
        ).hexdigest(),
    }
    return item, candidate, catalog_root, manual_root


def test_popular_catalog_binding_rechecks_relative_path_digest_bytes_and_metadata(
    tmp_path: Path,
) -> None:
    item, candidate, catalog_root, manual_root = _binding_fixture(tmp_path)
    identity = (IDENTITY, "sha256:" + "2" * 64, "sha256:" + "3" * 64)
    assert resolve_popular_candidate_binding(
        item,
        catalog_root=catalog_root,
        manual_root=manual_root,
        expected_identity=identity,
        catalog_cache={},
    ) == candidate

    escaped = {**item, "popularCatalogRef": "../catalog.json"}
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="safe relative"):
        resolve_popular_candidate_binding(
            escaped, catalog_root=catalog_root, manual_root=manual_root,
            expected_identity=identity, catalog_cache={},
        )

    wrong_digest = {**item, "popularCatalogDigest": "sha256:" + "9" * 64}
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="not canonical"):
        resolve_popular_candidate_binding(
            wrong_digest, catalog_root=catalog_root, manual_root=manual_root,
            expected_identity=identity, catalog_cache={},
        )

    drifted = {**item, "title": "Drifted title"}
    with pytest.raises(ValueError, match="metadata drift"):
        resolve_popular_candidate_binding(
            drifted, catalog_root=catalog_root, manual_root=manual_root,
            expected_identity=identity, catalog_cache={},
        )

    (manual_root / "popular.mp4").write_bytes(b"drifted")
    with pytest.raises(ValueError, match="manual bytes binding drift"):
        resolve_popular_candidate_binding(
            item, catalog_root=catalog_root, manual_root=manual_root,
            expected_identity=identity, catalog_cache={},
        )


def test_popular_catalog_binding_rejects_catalog_symlink(tmp_path: Path) -> None:
    item, _candidate, catalog_root, manual_root = _binding_fixture(tmp_path)
    path = catalog_root / item["popularCatalogRef"]
    real = path.with_suffix(".real.json")
    path.rename(real)
    path.symlink_to(real)
    with pytest.raises(ProfessionalVideoPopularCatalogError, match="symlink"):
        resolve_popular_candidate_binding(
            item, catalog_root=catalog_root, manual_root=manual_root,
            expected_identity=(IDENTITY, "sha256:" + "2" * 64, "sha256:" + "3" * 64),
            catalog_cache={},
        )


def test_source_pool_cli_freezes_popular_video_catalog_create_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from content.source.research import handler_cli

    evidence = tmp_path / "evidence"
    _write_video(evidence / "high.mp4", seed=8)
    responses = tmp_path / "responses.json"
    manifests = tmp_path / "manifests.json"
    responses.write_text(
        json.dumps([_response("bilibili")], ensure_ascii=False), encoding="utf-8"
    )
    manifests.write_text(
        json.dumps([
            _manual("bilibili", "bilibili-high", "high.mp4")
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    output_root = tmp_path / "output"
    parser = argparse.ArgumentParser()
    handler_cli.register_parser(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args([
        "source-pool", "freeze-professional-video-catalog",
        "--source-revision", IDENTITY,
        "--source-digest", "sha256:" + "2" * 64,
        "--entity-catalog-digest", "sha256:" + "3" * 64,
        "--metadata-responses", str(responses),
        "--manual-file-manifests", str(manifests),
        "--evidence-root", str(evidence),
        "--output-root", str(output_root),
    ])
    args.handler(args)
    first = json.loads(capsys.readouterr().out)
    args.handler(args)
    second = json.loads(capsys.readouterr().out)
    assert first == second
    destination = output_root / first["catalogRef"]
    assert destination.is_file()
    assert first["catalogFileSha256"] == "sha256:" + hashlib.sha256(
        destination.read_bytes()
    ).hexdigest()
