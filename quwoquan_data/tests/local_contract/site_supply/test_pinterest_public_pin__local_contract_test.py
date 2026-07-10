from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from _common.image_safety import ImageVerdict, STATUS_SAFE, STATUS_UNSAFE
from _common.io import read_json, write_json
from site_supply import pinterest_public_pin as pinmod


_TMP = Path(tempfile.mkdtemp(prefix="pinterest_public_pin_"))

_SAMPLE_HTML = """
<html>
  <head>
    <title>Shadow Lake sunrise | Pinterest</title>
    <meta property="og:image" content="https://i.pinimg.com/736x/aa/bb/cc/shadow-lake.jpg" />
    <meta property="og:title" content="Shadow Lake sunrise | Pinterest" />
    <meta property="description" content="Morning light over Shadow Lake." />
    <meta property="pinterestapp:source" content="https://example.com/photos/shadow-lake" />
    <meta property="og:see_also" content="https://example.com/photos/shadow-lake" />
    <meta property="pinterestapp:pinner" content="https://www.pinterest.com/nikkiparsons/" />
    <meta property="pinterestapp:pinboard" content="https://www.pinterest.com/nikkiparsons/scenic-lakes/" />
    <meta property="og:updated_time" content="2026-07-05T10:00:00.000Z" />
  </head>
  <body>
    <script type="application/json">
      {
        "originPinner": {"fullName": "Nikki Parsons", "username": "devacalder"},
        "pinner": {"fullName": "Cassie Smit", "username": "cassiensmit"},
        "board": {"name": "Scenic Lakes"},
        "gridTitle": "Shadow Lake sunrise",
        "description": "Morning light over Shadow Lake.",
        "createdAt": "Sun, 05 Jul 2026 10:00:00 +0000"
      }
    </script>
  </body>
</html>
""".strip()

_SAMPLE_HTML_NO_SOURCE_WITH_ORIGINAL = """
<html>
  <head>
    <title>Snow mountain landscape | Pinterest</title>
    <meta property="og:image" content="https://i.pinimg.com/736x/4a/75/a2/4a75a22db68ccd154470da698ac8fd50.jpg" />
    <meta property="og:title" content="Snow mountain landscape | Pinterest" />
    <meta property="description" content="Crisp snow peaks and cold blue sky." />
    <meta property="pinterestapp:pinner" content="https://www.pinterest.com/soniaalonso/" />
  </head>
  <body>
    <script type="application/json">
      {
        "pinner": {"fullName": "Sonia Alonso", "username": "soniaalonso"},
        "originPinner": {"fullName": "Sonia Alonso", "username": "soniaalonso"},
        "board": {"name": "Snow Mountains"},
        "gridTitle": "Snow mountain landscape",
        "description": "Crisp snow peaks and cold blue sky.",
        "imageLargeUrl": "https://i.pinimg.com/1200x/4a/75/a2/4a75a22db68ccd154470da698ac8fd50.jpg",
        "images_orig": {"url": "https://i.pinimg.com/originals/4a/75/a2/4a75a22db68ccd154470da698ac8fd50.jpg"}
      }
    </script>
  </body>
</html>
""".strip()


def _seed_file(name: str, rows: list[dict]) -> Path:
    path = _TMP / f"{name}.json"
    write_json(path, {"assets": rows})
    return path


def _fake_download(download_url: str, *, asset_id: str, download_root: Path) -> dict:
    asset_path = download_root / "assets" / f"{asset_id}.jpg"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"jpeg-bytes")
    return {
        "localPath": str(asset_path),
        "sha256": f"sha-{asset_id}",
        "byteSize": len(b"jpeg-bytes"),
        "mimeType": "image/jpeg",
        "width": 1800,
        "height": 1200,
    }


def _safe_verdict(path: Path, *, cache_dir: Path) -> ImageVerdict:  # noqa: ARG001
    return ImageVerdict(
        path=str(path),
        status=STATUS_SAFE,
        faces=0,
        has_watermark=False,
        text_area_ratio=0.0,
        ocr_text="",
        reasons=(),
        backends=("cv", "ocr"),
    )


def _unsafe_verdict(path: Path, *, cache_dir: Path) -> ImageVerdict:  # noqa: ARG001
    return ImageVerdict(
        path=str(path),
        status=STATUS_UNSAFE,
        faces=0,
        has_watermark=True,
        text_area_ratio=0.0,
        ocr_text="tripadvisor",
        reasons=("watermark_or_platform_text",),
        backends=("cv", "ocr"),
    )


def test_build_pinterest_public_pin_manifest_harvests_publishable_asset(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pinmod, "_fetch_public_pin_html", lambda url: _SAMPLE_HTML)
    monkeypatch.setattr(pinmod, "_download_pin_asset", _fake_download)
    monkeypatch.setattr(pinmod, "_assess_local_image", _safe_verdict)
    monkeypatch.setattr(pinmod, "_extract_source_page_author", lambda source_url: ("", ""))

    input_path = _seed_file(
        "harvest_ok",
        [
            {
                "pinUrl": "https://www.pinterest.com/pin/123456789012345678/",
                "entityRef": "地点/景区/九寨沟",
                "tags": ["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
            }
        ],
    )
    output_path = tmp_path / "manifest.json"

    report = pinmod.build_pinterest_public_pin_manifest(
        input_path=input_path,
        output_path=output_path,
        download_root=tmp_path / "download_root",
        default_tags=["Topic/旅行/玩法/自然风光"],
        default_entity_ref="地点/景区/九寨沟",
    )

    manifest = read_json(output_path)
    asset = manifest["assets"][0]
    assert report["funnel"]["requested"] == 1
    assert report["funnel"]["harvested"] == 1
    assert report["funnel"]["publishable"] == 1
    assert asset["pinUrl"] == "https://www.pinterest.com/pin/123456789012345678/"
    assert asset["sourceUrl"] == "https://example.com/photos/shadow-lake"
    assert asset["originalAssetUrl"] == "https://i.pinimg.com/736x/aa/bb/cc/shadow-lake.jpg"
    assert asset["downloadUrl"] == "https://i.pinimg.com/736x/aa/bb/cc/shadow-lake.jpg"
    assert asset["sourceAuthor"] == "Nikki Parsons"
    assert asset["credit"] == "Nikki Parsons"
    assert asset["authorEvidence"] == "origin_pinner_full_name"
    assert asset["watermarkScan"] == "no_explicit_watermark"
    assert asset["ocrScan"] == "no_text_detected"
    assert asset["modelReleaseStatus"] == "not_required"
    assert asset["sourceCollectionId"] == "pin_123456789012345678"
    assert asset["collectionPageUrl"] == "https://www.pinterest.com/nikkiparsons/scenic-lakes/"
    assert asset["sourceCollectionTitle"] == "Scenic Lakes"
    assert asset["publishable"] is True
    assert "https://example.com/photos/shadow-lake" in asset["repostAttribution"]
    assert Path(asset["localPath"]).is_file()
    assert set(asset["tags"]) == {
        "Topic/旅行/玩法/自然风光",
        "Topic/摄影/风光摄影",
        "Entity/地点/景区",
    }
    report_path = output_path.with_name("manifest_report.json")
    assert report_path.is_file()


def test_build_pinterest_public_pin_manifest_filters_non_publishable_assets(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pinmod, "_fetch_public_pin_html", lambda url: _SAMPLE_HTML)
    monkeypatch.setattr(pinmod, "_download_pin_asset", _fake_download)
    monkeypatch.setattr(pinmod, "_assess_local_image", _unsafe_verdict)
    monkeypatch.setattr(pinmod, "_extract_source_page_author", lambda source_url: ("", ""))

    input_path = _seed_file(
        "harvest_reject",
        [
            {
                "pinUrl": "https://www.pinterest.com/pin/876543210987654321/",
                "entityRef": "地点/景区/九寨沟",
                "tags": ["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
            }
        ],
    )
    output_path = tmp_path / "manifest.json"

    report = pinmod.build_pinterest_public_pin_manifest(
        input_path=input_path,
        output_path=output_path,
        download_root=tmp_path / "download_root",
        publishable_only=True,
        default_entity_ref="地点/景区/九寨沟",
        default_tags=["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
    )

    manifest = read_json(output_path)
    assert manifest["assets"] == []
    assert report["funnel"]["requested"] == 1
    assert report["funnel"]["harvested"] == 0
    assert report["funnel"]["rejected"] == 1
    assert "not publishable" in " ".join(report["rejectedPins"][0]["issues"])


def test_handle_harvest_pinterest_pins_supports_text_seed_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pinmod, "_fetch_public_pin_html", lambda url: _SAMPLE_HTML)
    monkeypatch.setattr(pinmod, "_download_pin_asset", _fake_download)
    monkeypatch.setattr(pinmod, "_assess_local_image", _safe_verdict)
    monkeypatch.setattr(pinmod, "_extract_source_page_author", lambda source_url: ("", ""))

    input_path = tmp_path / "pins.txt"
    input_path.write_text("https://www.pinterest.com/pin/234567890123456789/\n", encoding="utf-8")
    output_path = tmp_path / "manifest.json"
    args = argparse.Namespace(
        vertical="photography",
        site_id="pinterest",
        input=str(input_path),
        output=str(output_path),
        download_root=str(tmp_path / "download_root"),
        default_tags="Topic/旅行/玩法/自然风光,Topic/摄影/风光摄影,Entity/地点/景区",
        default_entity_ref="地点/景区/九寨沟",
        default_topic_ref="",
        usage_scope="commercial",
        publishable_only=False,
        sleep_seconds=0.0,
        limit=0,
    )

    pinmod.handle_harvest_pinterest_pins(args)

    manifest = read_json(output_path)
    assert len(manifest["assets"]) == 1
    assert manifest["assets"][0]["pinUrl"] == "https://www.pinterest.com/pin/234567890123456789/"


def test_source_page_author_probe_overrides_pinner_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pinmod, "_fetch_public_pin_html", lambda url: _SAMPLE_HTML)
    monkeypatch.setattr(pinmod, "_download_pin_asset", _fake_download)
    monkeypatch.setattr(pinmod, "_assess_local_image", _safe_verdict)
    monkeypatch.setattr(
        pinmod,
        "_extract_source_page_author",
        lambda source_url: ("Vincent Ting", "source_page_text_author"),
    )

    input_path = _seed_file(
        "harvest_source_author_probe",
        [
            {
                "pinUrl": "https://www.pinterest.com/pin/410601691007838238/",
                "entityRef": "地点/景区/九寨沟",
                "tags": ["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
            }
        ],
    )
    output_path = tmp_path / "manifest.json"

    pinmod.build_pinterest_public_pin_manifest(
        input_path=input_path,
        output_path=output_path,
        download_root=tmp_path / "download_root",
        default_entity_ref="地点/景区/九寨沟",
        default_tags=["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影", "Entity/地点/景区"],
    )

    manifest = read_json(output_path)
    asset = manifest["assets"][0]
    assert asset["sourceAuthor"] == "Vincent Ting"
    assert asset["authorEvidence"] == "source_page_text_author"


def test_build_pinterest_public_pin_manifest_uses_original_image_and_pin_fallback_source(monkeypatch, tmp_path: Path):
    captured: dict[str, str] = {}

    def _capture_download(download_url: str, *, asset_id: str, download_root: Path) -> dict:
        captured["downloadUrl"] = download_url
        return _fake_download(download_url, asset_id=asset_id, download_root=download_root)

    monkeypatch.setattr(pinmod, "_fetch_public_pin_html", lambda url: _SAMPLE_HTML_NO_SOURCE_WITH_ORIGINAL)
    monkeypatch.setattr(pinmod, "_download_pin_asset", _capture_download)
    monkeypatch.setattr(pinmod, "_assess_local_image", _safe_verdict)
    monkeypatch.setattr(pinmod, "_extract_source_page_author", lambda source_url: ("", ""))

    input_path = _seed_file(
        "harvest_original_image_pin_fallback",
        [
            {
                "pinUrl": "https://www.pinterest.com/pin/1047649932085880408/",
                "entityRef": "主题/摄影/风光摄影",
                "tags": ["Topic/摄影/风光摄影", "Topic/旅行/玩法/自然风光"],
            }
        ],
    )
    output_path = tmp_path / "manifest.json"

    report = pinmod.build_pinterest_public_pin_manifest(
        input_path=input_path,
        output_path=output_path,
        download_root=tmp_path / "download_root",
        default_entity_ref="主题/摄影/风光摄影",
        default_tags=["Topic/摄影/风光摄影", "Topic/旅行/玩法/自然风光"],
    )

    manifest = read_json(output_path)
    asset = manifest["assets"][0]
    assert report["funnel"]["harvested"] == 1
    assert captured["downloadUrl"] == "https://i.pinimg.com/originals/4a/75/a2/4a75a22db68ccd154470da698ac8fd50.jpg"
    assert asset["downloadUrl"] == captured["downloadUrl"]
    assert asset["originalAssetUrl"] == captured["downloadUrl"]
    assert asset["sourceUrl"] == "https://www.pinterest.com/pin/1047649932085880408/"
    assert asset["linkedSourceUrl"] == "https://www.pinterest.com/pin/1047649932085880408/"
    assert asset["sourceAuthor"] == "Sonia Alonso"
    assert asset["authorEvidence"] == "origin_pinner_full_name"
