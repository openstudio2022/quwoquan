"""公开 media slice 派生的跨语言用例契约（Python 侧）。

同一份用例文件由 quwoquan_service/runtime/media 的 Go 合约测试同时消费，两侧
必须对每个用例产出逐字节相同的 publicSliceKey。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
REPO_ROOT = DATA_ROOT.parent
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import pytest

from core.media_asset_url import build_public_media_slice_key, is_public_media_slice_key

PARITY_CASES = (
    REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "media"
    / "media_asset"
    / "public_slice_derivation_cases.json"
)


def _cases() -> list[dict[str, object]]:
    document = json.loads(PARITY_CASES.read_text(encoding="utf-8"))
    assert document["schema"] == "content_media_public_slice_derivation_cases"
    cases = document["cases"]
    assert isinstance(cases, list) and cases
    return cases


def test_shared_case_file_names_the_release_media_domain_only():
    document = json.loads(PARITY_CASES.read_text(encoding="utf-8"))
    domain = document["domain"]
    assert domain["kinds"] == ["avatar", "image", "video"]
    assert domain["contentTypes"] == [
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "video/mp4",
        "video/webm",
    ]


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["name"]))
def test_public_slice_derivation_matches_shared_case(case: dict[str, object]):
    observed = build_public_media_slice_key(
        asset_id=str(case["assetId"]),
        kind=str(case["mediaType"]),
        version=int(case["version"]),
        content_type=str(case["contentType"]),
    )
    assert observed == str(case["publicSliceKey"])
    if observed:
        assert is_public_media_slice_key(observed)


def test_structured_post_asset_ids_keep_role_and_sequence_readable():
    observed = build_public_media_slice_key(
        asset_id="峨眉山_cover_金顶云海_313_a1b2c3d4",
        kind="image",
        version=1,
        content_type="image/jpeg",
    )
    assert observed.startswith("media/image/s/asset/cover-313-")
    assert "unicode-" not in observed


def test_distinct_asset_ids_never_share_one_public_slice():
    first = build_public_media_slice_key(
        asset_id="峨眉山_cover_金顶云海_313_a1b2c3d4",
        kind="image",
        version=1,
        content_type="image/jpeg",
    )
    second = build_public_media_slice_key(
        asset_id="峨眉山_cover_洗象池晨雾_313_a1b2c3d4",
        kind="image",
        version=1,
        content_type="image/jpeg",
    )
    assert first and second and first != second
