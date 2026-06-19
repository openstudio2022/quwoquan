"""Image rights are asset-level, not source-name level."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from vertical.license import validate_image_rights  # noqa: E402


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
    assert not any("发现源只能作为灵感" in issue for issue in issues)


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
