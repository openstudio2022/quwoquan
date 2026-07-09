from __future__ import annotations

from pathlib import Path

from _common.io import read_json, write_json
from support.site_supply_fixtures import *  # noqa: F401,F403
from verify.site_scale_readiness import build_site_scale_readiness_report


def _authorized_asset(collection: str, index: int, **overrides) -> dict:
    asset_id = f"{collection}-{index:03d}"
    row = {
        "assetId": asset_id,
        "sourceUrl": f"https://stock.tuchong.com/image/{asset_id}",
        "downloadUrl": f"https://cdn.tuchong.com/image/{asset_id}.jpg",
        "title": f"九寨沟图虫授权摄影作品 {index}",
        "creator": "图虫授权摄影师",
        "credit": "图虫授权摄影师 / 图虫创意",
        "license": "stock_authorized",
        "termsUrl": "https://stock.tuchong.com/",
        "usageScope": "commercial",
        "authorizationProof": f"https://stock.tuchong.com/order/proof/{asset_id}",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "sourceCollectionId": collection,
        "sourceCollectionTitle": f"九寨沟图虫创意授权组图 {collection}",
        "collectionPageUrl": f"https://stock.tuchong.com/collection/{collection}",
        "tags": ["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
        "entityRef": "地点/景区/九寨沟",
        "width": 1800,
        "height": 1200,
        "publishedAt": "2026-07-04",
        "entityMatch": "strong",
    }
    row.update(overrides)
    return row


def _manifest(batch: str, rows: list[dict]) -> Path:
    path = _TMP / f"{batch}_authorized_assets.json"
    write_json(path, {"assets": rows})
    return path


def _write_test_image(path: Path) -> Path:
    import hashlib

    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(path.as_posix().encode("utf-8")).digest()
    Image.new("RGB", (1800, 1200), color=(digest[0], digest[1], digest[2])).save(path, format="JPEG")
    return path


def _photographer_asset(collection: str, index: int, local_path: Path | None = None, **overrides) -> dict:
    asset_id = f"{collection}-{index:03d}"
    row = {
        "assetId": asset_id,
        "sourceUrl": f"https://photographers.example/works/{asset_id}",
        "localPath": str(local_path) if local_path else "",
        "title": f"川西摄影师授权作品 {index}",
        "creator": "签约摄影师 A",
        "credit": "签约摄影师 A / 摄影师授权池",
        "license": "photographer_authorized",
        "termsUrl": "https://photographers.example/terms/authorized-pool",
        "usageScope": "commercial",
        "authorizationProof": f"https://photographers.example/proofs/{asset_id}",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "sourceCollectionId": collection,
        "sourceCollectionTitle": f"川西授权摄影组图 {collection}",
        "collectionPageUrl": f"https://photographers.example/collections/{collection}",
        "tags": ["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
        "entityRef": "地点/景区/九寨沟",
        "publishedAt": "2026-07-04",
        "entityMatch": "strong",
    }
    row.update(overrides)
    return row


def _pinterest_asset(collection: str, index: int, local_path: Path | None = None, **overrides) -> dict:
    asset_id = f"{collection}-{index:03d}"
    row = {
        "assetId": asset_id,
        "pinUrl": f"https://www.pinterest.com/pin/{asset_id}/",
        "discoveryUrl": f"https://www.pinterest.com/search/pins/?q={collection}",
        "originalAssetUrl": f"https://img.example.com/pinterest/{asset_id}.jpg",
        "downloadUrl": f"https://img.example.com/pinterest/{asset_id}.jpg",
        "localPath": str(local_path) if local_path else "",
        "title": f"九寨沟 Pinterest 风景摄影作品 {index}",
        "sourceAuthor": "Pinterest原作者A",
        "credit": "Pinterest原作者A",
        "repostAttribution": "转载自原作者公开 pin，保留 pinUrl 与 originalAssetUrl",
        "watermarkScan": "no_explicit_watermark",
        "ocrScan": "no_text_detected",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "sourceCollectionId": collection,
        "sourceCollectionTitle": f"九寨沟 Pinterest 公开图组 {collection}",
        "collectionPageUrl": f"https://www.pinterest.com/board/{collection}/",
        "tags": ["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
        "entityRef": "地点/景区/九寨沟",
        "publishedAt": "2026-07-05",
        "collectedAt": "2026-07-05T09:30:00Z",
        "entityMatch": "strong",
    }
    row.update(overrides)
    return row


def test_tuchong_community_cannot_use_authorized_ingest_escape_hatch():
    frontier = ss.build_site_frontier_packet(
        vertical="photography",
        site_id="tuchong",
        batch_id="tuchong_community_licensed_block",
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-07-04",
        admission_mode="licensed_asset_ingest",
    )

    assert not frontier["gate"]["passed"]
    text = "\n".join(frontier["gate"]["blockers"])
    assert "licensed_asset_ingest requires rightsPolicy" in text
    assert "licensed_asset_ingest requires fetchMode=licensed_api or manual_authorization" in text


def test_photographer_authorized_pool_ingests_local_assets_with_byte_evidence(tmp_path: Path):
    batch = "photographer_authorized_pool_ok"
    rows = []
    for collection in ("jiuzhaigou-pool-a", "jiuzhaigou-pool-b"):
        for index in range(1, 5):
            image_path = _write_test_image(tmp_path / collection / f"{index}.jpg")
            rows.append(_photographer_asset(collection, index, image_path))

    report = ss.build_authorized_asset_ingest_report(
        vertical="photography",
        site_id="photographer_authorized_pool",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=2,
        min_raw_count=8,
        min_qualified_count=8,
        daily_target=1_000,
        end_date="2026-07-04",
        objects_per_hour=240,
        token_ledger_count=2,
        download_assets=True,
    )

    assert report["gate"]["passed"], report
    assert report["thresholds"]["downloadAssets"] is True
    assert report["funnel"]["rawDiscovered"] == 8
    assert report["funnel"]["qualified"] == 8
    assert report["funnel"]["qualifiedImageWorks"] == 2
    root = ss.site_supply_root("photography", "photographer_authorized_pool", batch)
    candidates = list((root / "candidates").glob("*/site_candidate_packet.json"))
    assert candidates
    candidate = read_json(candidates[0])
    asset = candidate["assets"][0]
    assert asset["platform"] == "摄影师授权池"
    assert asset["sha256"]
    assert asset["byteSize"] > 0
    assert asset["mimeType"] == "image/jpeg"
    assert Path(asset["sourcePath"]).is_file()
    assert candidate["canonicalUrl"].startswith("https://authorized.assets.quwoquan.local/collections/")


def test_photographer_authorized_pool_blocks_tuchong_community_publish_url(tmp_path: Path):
    batch = "photographer_authorized_pool_tuchong_community_url"
    image_path = _write_test_image(tmp_path / "one.jpg")
    rows = [
        _photographer_asset(
            "jiuzhaigou-community-block",
            index,
            image_path if index == 1 else _write_test_image(tmp_path / f"{index}.jpg"),
            sourceUrl=f"https://tuchong.com/123/{index}",
        )
        for index in range(1, 5)
    ]

    report = ss.build_authorized_asset_ingest_report(
        vertical="photography",
        site_id="photographer_authorized_pool",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=1,
        min_raw_count=1,
        min_qualified_count=1,
        daily_target=1_000,
        end_date="2026-07-04",
        objects_per_hour=120,
        download_assets=True,
    )

    text = "\n".join(" ".join(item["reasons"]) for item in report["rejectedAssets"])
    assert not report["gate"]["passed"]
    assert "sourceUrl cannot be a Tuchong community publish asset URL" in text


def test_photographer_authorized_pool_rejects_missing_file_and_duplicate_sha(tmp_path: Path):
    batch = "photographer_authorized_pool_bad_assets"
    duplicate_path = _write_test_image(tmp_path / "duplicate.jpg")
    rows = [
        _photographer_asset("jiuzhaigou-bad", 1, None),
        _photographer_asset("jiuzhaigou-bad", 2, tmp_path / "missing.jpg"),
        _photographer_asset("jiuzhaigou-bad", 3, duplicate_path),
        _photographer_asset("jiuzhaigou-bad", 4, duplicate_path),
    ]

    report = ss.build_authorized_asset_ingest_report(
        vertical="photography",
        site_id="photographer_authorized_pool",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=1,
        min_raw_count=1,
        min_qualified_count=1,
        daily_target=1_000,
        end_date="2026-07-04",
        objects_per_hour=120,
        download_assets=True,
    )

    text = "\n".join(" ".join(item["reasons"]) for item in report["rejectedAssets"])
    assert not report["gate"]["passed"]
    assert "one of downloadUrl or localPath is required" in text
    assert "localPath does not exist" in text
    assert "duplicate authorized asset key sha256=" in text


def test_tuchong_stock_authorized_ingest_builds_image_works_and_commercial_readiness():
    batch = "tuchong_authorized_imageworks_ok"
    rows = [
        _authorized_asset("jiuzhaigou-a", index)
        for index in range(1, 5)
    ] + [
        _authorized_asset("jiuzhaigou-b", index)
        for index in range(1, 5)
    ]
    report = ss.build_authorized_asset_ingest_report(
        vertical="photography",
        site_id="tuchong_stock_authorized",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=2,
        min_raw_count=8,
        min_qualified_count=8,
        daily_target=1_000,
        end_date="2026-07-04",
        objects_per_hour=240,
        token_ledger_count=2,
    )

    assert report["gate"]["passed"], report
    assert report["thresholds"]["minAssetsPerImageWork"] == 4
    assert report["funnel"]["rawDiscovered"] == 8
    assert report["funnel"]["qualified"] == 8
    assert report["funnel"]["qualifiedImageWorks"] == 2
    assert report["funnel"]["picked"] == 2

    root = ss.site_supply_root("photography", "tuchong_stock_authorized", batch)
    downstream_path = root / "_shared" / "site_supply_downstream_e2e_report.json"
    refs = [
        "posts/image/图虫创意/jiuzhaigou-a",
        "posts/image/图虫创意/jiuzhaigou-b",
    ]
    write_json(
        downstream_path,
        {
            "schemaVersion": "quwoquan_data.site_supply.downstream_e2e/1",
            "vertical": "photography",
            "siteId": "tuchong_stock_authorized",
            "sourceBatchId": batch,
            "taskId": "摄影/图虫创意/授权图片作品/百级验证",
            "targetBatch": "tuchong_image_100_prod",
            "env": "gamma",
            "plannedPostRefs": refs,
            "releasedPostRefs": refs,
            "plannedPostRefCount": len(refs),
            "releasedPostRefCount": len(refs),
            "checks": {
                "releaseVerified": True,
                "importVerified": True,
                "searchVisible": True,
                "recommendationFeedbackReady": True,
            },
            "gate": {"passed": True, "blockers": [], "warnings": []},
        },
    )
    write_json(root / "ship_import" / "stage_result.json", {"outputs": [str(downstream_path)]})

    readiness = build_site_scale_readiness_report(
        vertical="photography",
        site_id="tuchong_stock_authorized",
        batch_id=batch,
        daily_target=1_000,
        mode="commercial",
        min_lane_counts={"image": 2},
    )

    assert readiness["passed"], readiness["blockers"]
    assert readiness["aggregate"]["contentPlanHandoffLaneCounts"] == {"image": 2}
    assert readiness["aggregate"]["releasedPostLaneCounts"] == {"image": 2}
    assert readiness["aggregate"]["rawCapacitySiteCount"] == 0


def test_tuchong_stock_authorized_ingest_rejects_missing_rights_and_bad_assets():
    batch = "tuchong_authorized_imageworks_reject"
    rows = [
        _authorized_asset("jiuzhaigou-bad", 1, authorizationProof=""),
        _authorized_asset("jiuzhaigou-bad", 2, termsUrl=""),
        _authorized_asset("jiuzhaigou-bad", 3, usageScope="internal_reference"),
        _authorized_asset("jiuzhaigou-bad", 4, watermarkDetected=True, width=640, height=360),
    ]

    report = ss.build_authorized_asset_ingest_report(
        vertical="photography",
        site_id="tuchong_stock_authorized",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=1,
        min_raw_count=1,
        min_qualified_count=1,
        daily_target=1_000,
        end_date="2026-07-04",
        objects_per_hour=120,
    )

    text = "\n".join(" ".join(item["reasons"]) for item in report["rejectedAssets"])
    assert not report["gate"]["passed"]
    assert report["funnel"]["qualified"] == 0
    assert "missing authorized asset fields ['authorizationProof']" in text
    assert "missing authorized asset fields ['termsUrl']" in text
    assert "usageScope must be app_publish or commercial" in text
    assert "watermark/platform mark detected" in text


def test_tuchong_stock_authorized_ingest_gate_blocks_missing_manifest():
    report = ss.build_authorized_asset_ingest_report(
        vertical="photography",
        site_id="tuchong_stock_authorized",
        batch_id="tuchong_authorized_manifest_missing",
        manifest_path=_TMP / "missing_tuchong_authorized_assets.json",
        target_count=1,
        min_raw_count=1,
        min_qualified_count=1,
        daily_target=1_000,
        end_date="2026-07-04",
        objects_per_hour=120,
    )

    assert not report["gate"]["passed"]
    assert "authorized asset manifest missing" in "\n".join(report["gate"]["blockers"])


def test_pinterest_attributed_ingest_builds_image_works_and_commercial_readiness(tmp_path: Path):
    batch = "pinterest_attributed_imageworks_ok"
    site_id = "pinterest"
    rows = []
    for collection in ("jiuzhaigou-pin-a", "jiuzhaigou-pin-b"):
        image_path = _write_test_image(tmp_path / collection / "1.jpg")
        rows.append(_pinterest_asset(collection, 1, image_path))

    report = ss.build_attributed_asset_ingest_report(
        vertical="photography",
        site_id=site_id,
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=2,
        min_raw_count=2,
        min_qualified_count=2,
        daily_target=1_000,
        end_date="2026-07-05",
        objects_per_hour=240,
        token_ledger_count=2,
        download_assets=False,
    )

    assert report["gate"]["passed"], report
    assert report["thresholds"]["minAssetsPerImageWork"] == 1
    assert report["funnel"]["qualified"] == 2
    assert report["funnel"]["qualifiedImageWorks"] == 2
    root = ss.site_supply_root("photography", site_id, batch)
    candidates = list((root / "candidates").glob("*/site_candidate_packet.json"))
    assert candidates
    candidate = read_json(candidates[0])
    asset = candidate["assets"][0]
    assert asset["platform"] == "Pinterest"
    assert asset["authorizationBasis"] == "attribution_no_watermark"
    assert asset["pinUrl"].startswith("https://www.pinterest.com/pin/")
    assert asset["watermarkScan"] == "no_explicit_watermark"

    downstream_path = root / "_shared" / "site_supply_downstream_e2e_report.json"
    refs = [
        "posts/image/Pinterest/jiuzhaigou-pin-a",
        "posts/image/Pinterest/jiuzhaigou-pin-b",
    ]
    write_json(
        downstream_path,
        {
            "schemaVersion": "quwoquan_data.site_supply.downstream_e2e/1",
            "vertical": "photography",
            "siteId": site_id,
            "sourceBatchId": batch,
            "taskId": "摄影/Pinterest/归因图片作品/百级验证",
            "targetBatch": "pinterest_image_100_prod",
            "env": "gamma",
            "plannedPostRefs": refs,
            "releasedPostRefs": refs,
            "plannedPostRefCount": len(refs),
            "releasedPostRefCount": len(refs),
            "checks": {
                "releaseVerified": True,
                "importVerified": True,
                "searchVisible": True,
                "recommendationFeedbackReady": True,
            },
            "gate": {"passed": True, "blockers": [], "warnings": []},
        },
    )
    write_json(root / "ship_import" / "stage_result.json", {"outputs": [str(downstream_path)]})
    readiness = build_site_scale_readiness_report(
        vertical="photography",
        site_id=site_id,
        batch_id=batch,
        daily_target=1_000,
        mode="commercial",
        min_lane_counts={"image": 2},
    )
    assert readiness["passed"], readiness["blockers"]
    assert readiness["aggregate"]["releasedPostLaneCounts"] == {"image": 2}


def test_pinterest_attributed_ingest_accepts_locale_subdomain_pin_urls(tmp_path: Path):
    batch = "pinterest_attributed_locale_domains_ok"
    rows = [
        _pinterest_asset(
            "jiuzhaigou-pin-fr",
            1,
            _write_test_image(tmp_path / "fr" / "1.jpg"),
            pinUrl="https://fr.pinterest.com/pin/257408934935752856/",
            collectionPageUrl="https://fr.pinterest.com/pin-builder/jiuzhaigou-fr/",
        ),
        _pinterest_asset(
            "jiuzhaigou-pin-in",
            1,
            _write_test_image(tmp_path / "in" / "1.jpg"),
            pinUrl="https://in.pinterest.com/pin/23995810510606012/",
            collectionPageUrl="https://in.pinterest.com/pin-builder/jiuzhaigou-in/",
        ),
    ]

    report = ss.build_attributed_asset_ingest_report(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=2,
        min_raw_count=2,
        min_qualified_count=2,
        daily_target=1_000,
        end_date="2026-07-05",
        objects_per_hour=240,
        download_assets=False,
    )

    assert report["gate"]["passed"], report
    assert report["funnel"]["qualified"] == 2
    root = ss.site_supply_root("photography", "pinterest", batch)
    candidates = list((root / "candidates").glob("*/site_candidate_packet.json"))
    assert len(candidates) == 2
    pin_urls = sorted(read_json(path)["assets"][0]["pinUrl"] for path in candidates)
    assert pin_urls == [
        "https://fr.pinterest.com/pin/257408934935752856/",
        "https://in.pinterest.com/pin/23995810510606012/",
    ]


def test_pinterest_attributed_ingest_keeps_distinct_pins_on_same_board(tmp_path: Path):
    batch = "pinterest_attributed_same_board_ok"
    shared_board = "https://www.pinterest.com/avr0957/parfait/"
    rows = [
        _pinterest_asset(
            "pin_140806234820407",
            1,
            _write_test_image(tmp_path / "same-board" / "1.jpg"),
            pinUrl="https://www.pinterest.com/pin/140806234820407/",
            collectionPageUrl=shared_board,
        ),
        _pinterest_asset(
            "pin_140806234660858",
            1,
            _write_test_image(tmp_path / "same-board" / "2.jpg"),
            pinUrl="https://www.pinterest.com/pin/140806234660858/",
            collectionPageUrl=shared_board,
        ),
    ]

    report = ss.build_attributed_asset_ingest_report(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=2,
        min_raw_count=2,
        min_qualified_count=2,
        daily_target=1_000,
        end_date="2026-07-05",
        objects_per_hour=240,
        download_assets=False,
    )

    assert report["gate"]["passed"], report
    assert report["funnel"]["picked"] == 2
    root = ss.site_supply_root("photography", "pinterest", batch)
    candidates = list((root / "candidates").glob("*/site_candidate_packet.json"))
    assert len(candidates) == 2
    canonical_urls = sorted(read_json(path)["canonicalUrl"] for path in candidates)
    assert canonical_urls == [
        "https://www.pinterest.com/pin/140806234660858/",
        "https://www.pinterest.com/pin/140806234820407/",
    ]


def test_pinterest_attributed_ingest_rejects_missing_attribution_evidence(tmp_path: Path):
    batch = "pinterest_attributed_imageworks_reject"
    site_id = "pinterest"
    image_path = _write_test_image(tmp_path / "bad.jpg")
    rows = [
        _pinterest_asset("jiuzhaigou-pin-bad", 1, image_path, watermarkScan=""),
        _pinterest_asset("jiuzhaigou-pin-bad", 2, image_path, ocrScan=""),
        _pinterest_asset("jiuzhaigou-pin-bad", 3, image_path, sourceAuthor=""),
        _pinterest_asset("jiuzhaigou-pin-bad", 4, image_path, repostAttribution=""),
    ]

    report = ss.build_attributed_asset_ingest_report(
        vertical="photography",
        site_id=site_id,
        batch_id=batch,
        manifest_path=_manifest(batch, rows),
        target_count=1,
        min_raw_count=1,
        min_qualified_count=1,
        daily_target=1_000,
        end_date="2026-07-05",
        objects_per_hour=120,
        download_assets=False,
    )

    text = "\n".join(" ".join(item["reasons"]) for item in report["rejectedAssets"])
    assert not report["gate"]["passed"]
    assert "missing attributed asset fields ['watermarkScan']" in text
    assert "missing attributed asset fields ['ocrScan']" in text
    assert "missing attributed asset fields ['sourceAuthor']" in text
    assert "missing attributed asset fields ['repostAttribution']" in text
