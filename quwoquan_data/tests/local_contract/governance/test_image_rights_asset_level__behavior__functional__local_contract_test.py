"""Image rights are asset-level, not source-name level."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from governance.coverage.license import audit_image_rights as validate_image_rights  # noqa: E402


def test_discovery_platform_is_not_blocked_by_source_name_when_asset_rights_are_complete():
    issues = validate_image_rights(
        {
            "platform": "Pinterest",
            "license": "CC BY 4.0",
            "credit": "Creator",
            "sourceUrl": "https://example.com/original-file",
            "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
            "authorizationProof": "https://example.com/original-file",
            "usageScope": "app_publish",
            "modelReleaseRequired": "false",
            "modelReleaseStatus": "not_required",
        },
        vertical="travel",
    )
    assert issues == []


def test_attribution_no_watermark_payload_passes_with_complete_pinterest_evidence():
    issues = validate_image_rights(
        {
            "platform": "Pinterest",
            "authorizationBasis": "attribution_no_watermark",
            "license": "attribution_no_watermark",
            "credit": "Creator",
            "sourceUrl": "https://images.example.com/jiuzhaigou.jpg",
            "termsUrl": "https://policy.pinterest.com/terms-of-service",
            "authorizationProof": "https://images.example.com/jiuzhaigou.jpg",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "pinUrl": "https://www.pinterest.com/pin/123456/",
            "discoveryUrl": "https://www.pinterest.com/search/pins/?q=jiuzhaigou",
            "originalAssetUrl": "https://images.example.com/jiuzhaigou.jpg",
            "sourceAuthor": "Creator",
            "repostAttribution": "转载自原作者公开 pin",
            "watermarkScan": "no_explicit_watermark",
            "ocrScan": "no_text_detected",
            "collectedAt": "2026-07-05T09:30:00Z",
        },
        vertical="travel",
    )
    assert issues == []


def test_discovery_platform_still_fails_without_asset_rights():
    issues = validate_image_rights(
        {
            "platform": "小红书",
            "sourceUrl": "https://example.com/note",
            "usageScope": "app_publish",
        },
        vertical="travel",
    )
    assert any("missing required field license" in issue for issue in issues)
    assert any("missing required field authorizationProof" in issue for issue in issues)
    assert not any("发现源只能作为灵感" in issue for issue in issues)


def test_tuchong_stock_authorized_payload_requires_authorization_proof():
    issues = validate_image_rights(
        {
            "platform": "图虫创意",
            "license": "photographer_authorized",
            "credit": "Creator",
            "sourceUrl": "https://stock.tuchong.com/image/123",
            "termsUrl": "https://stock.tuchong.com/",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
        },
        vertical="travel",
    )
    assert any("missing required field authorizationProof" in issue for issue in issues)


def test_attribution_no_watermark_requires_scan_and_author_fields():
    issues = validate_image_rights(
        {
            "platform": "Pinterest",
            "authorizationBasis": "attribution_no_watermark",
            "license": "attribution_no_watermark",
            "credit": "Creator",
            "sourceUrl": "https://images.example.com/jiuzhaigou.jpg",
            "termsUrl": "https://policy.pinterest.com/terms-of-service",
            "authorizationProof": "https://images.example.com/jiuzhaigou.jpg",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "pinUrl": "https://www.pinterest.com/pin/123456/",
            "discoveryUrl": "https://www.pinterest.com/search/pins/?q=jiuzhaigou",
            "originalAssetUrl": "https://images.example.com/jiuzhaigou.jpg",
            "watermarkScan": "detected",
            "ocrScan": "detected",
            "collectedAt": "2026-07-05T09:30:00Z",
        },
        vertical="travel",
    )
    assert any("attribution_no_watermark missing sourceAuthor" in issue for issue in issues)
    assert any("attribution_no_watermark missing repostAttribution" in issue for issue in issues)
    assert any("watermarkScan=clear/pass/no_explicit_watermark" in issue for issue in issues)
    assert any("ocrScan=clear/pass/no_text_detected" in issue for issue in issues)


def test_creative_commons_jurisdiction_suffix_normalizes_to_allowed_kind():
    issues = validate_image_rights(
        {
            "platform": "Wikimedia Commons",
            "license": "CC BY-SA 2.5 nl",
            "credit": "Creator",
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/2.5/nl/deed.en",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
        },
        vertical="travel",
    )
    assert issues == []


def test_creative_commons_long_name_normalizes_to_allowed_kind():
    issues = validate_image_rights(
        {
            "platform": "Wikimedia Commons",
            "license": "Creative Commons Attribution-Share Alike 3.0",
            "credit": "Creator",
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/3.0/",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
        },
        vertical="travel",
    )
    assert issues == []


def test_creative_commons_1_0_remains_blocked():
    issues = validate_image_rights(
        {
            "platform": "Wikimedia Commons",
            "license": "CC BY-SA 1.0",
            "credit": "Creator",
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Old.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/1.0/",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Old.jpg",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
        },
        vertical="travel",
    )
    assert any("unsupported license CC BY-SA 1.0" in issue for issue in issues)


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"image rights asset-level tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
