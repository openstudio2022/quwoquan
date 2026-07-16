"""图片安全/美学门 contract tests（真实 CV：人脸/水印/OCR/去重 + 降级）。

可直接运行：python3 quwoquan_data/tests/local_contract/homepage/test_image_safety_gate__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from core import image_safety as I  # noqa: E402

FIXTURE_MEDIA = (
    DATA_ROOT.parent
    / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/media"
)
FACE_FIXTURE = FIXTURE_MEDIA / "avatar/user/fixture_user_article/v1/avatar.png"


_TMP_DIR = Path(tempfile.mkdtemp(prefix="img_safety_test_"))
_WRITE_SEQ = [0]


def _write(img: np.ndarray, suffix: str = ".jpg") -> Path:
    _WRITE_SEQ[0] += 1
    p = _TMP_DIR / f"img_{_WRITE_SEQ[0]:03d}{suffix}"
    cv2.imwrite(str(p), img)
    return p


def _clean_image() -> Path:
    img = np.zeros((400, 600, 3), np.uint8)
    for x in range(600):
        img[:, x] = ((x) % 256, (x * 2) % 256, (x * 3) % 256)
    return _write(img)


def _watermark_image(text: str = "Copyright tripadvisor 2026") -> Path:
    img = np.full((400, 600, 3), 255, np.uint8)
    cv2.putText(img, text, (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)
    return _write(img)


def _text_heavy_image() -> Path:
    img = np.full((400, 600, 3), 255, np.uint8)
    for y in range(40, 400, 32):
        cv2.putText(img, "the quick brown fox jumps over lazy dog", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    return _write(img)


def _first_face_fixture() -> Path | None:
    return FACE_FIXTURE if FACE_FIXTURE.is_file() else None


def test_backends_present():
    status = I.backend_status()
    assert status["cv"] is True, "OpenCV 后端必须可用"
    assert status["hash"] is True, "imagehash 后端必须可用"
    assert status["ocr"] is True, "tesseract OCR 后端必须可用（绿色路径要求）"


def test_clean_image_is_safe():
    v = I.assess_image(_clean_image())
    assert v.status == I.STATUS_SAFE, v.to_dict()
    assert v.faces == 0
    assert v.has_watermark is False


def test_image_safety_persistent_cache_reuses_verdict_for_same_bytes():
    first = _clean_image()
    second = _TMP_DIR / "same-bytes-copy.jpg"
    second.write_bytes(first.read_bytes())
    cache_dir = _TMP_DIR / "safety-cache"

    first_verdict = I.assess_image_cached(first, cache_dir=cache_dir)
    second_verdict = I.assess_image_cached(second, cache_dir=cache_dir)

    assert list(cache_dir.rglob("*.json")), "persistent verdict cache must be written"
    assert second_verdict.path == str(second)
    assert second_verdict.status == first_verdict.status
    assert second_verdict.reasons == first_verdict.reasons


def test_watermark_image_is_unsafe():
    v = I.assess_image(_watermark_image())
    assert v.has_watermark is True, v.to_dict()
    assert v.status == I.STATUS_UNSAFE, v.to_dict()
    assert v.blocks_image_publish is True


def test_at_handle_is_unsafe():
    v = I.assess_image(_watermark_image("photo by @alpine_walker"))
    assert v.has_watermark is True, v.to_dict()
    assert v.status == I.STATUS_UNSAFE, v.to_dict()


def test_bare_copyright_symbol_without_rights_context_is_not_watermark():
    assert I._has_watermark("严复 故居 中华人民共和国 国务院 8:30—22:00 © RMB") is False


def test_copyright_symbol_with_rights_context_is_watermark():
    assert I._has_watermark("© Alice all rights reserved") is True


def test_watermark_prone_original_provenance_is_policy_excluded_when_ocr_is_inconclusive():
    reason = I.watermark_prone_source_reason(
        (
            "https://commons.wikimedia.org/wiki/File:Putuo_-_panoramio.jpg",
            "https://zh.wikipedia.org/wiki/普陀山",
        )
    )

    assert reason == "watermark_prone_source_provenance:panoramio"
    assert I.watermark_prone_source_reason(("https://commons.wikimedia.org/wiki/File:Clean.jpg",)) == ""


def test_text_heavy_routes_to_article():
    v = I.assess_image(_text_heavy_image())
    assert v.is_text_heavy is True, v.to_dict()
    assert v.status in (I.STATUS_TEXT_HEAVY, I.STATUS_UNSAFE), v.to_dict()


def test_oversized_image_is_blocked_before_heavy_cv_ocr():
    img = np.zeros((120, 120, 3), np.uint8)
    p = _write(img, ".png")
    old_limit = I.MAX_ASSESS_PIXELS
    try:
        I.MAX_ASSESS_PIXELS = 10_000
        v = I.assess_image(p)
    finally:
        I.MAX_ASSESS_PIXELS = old_limit
    assert v.status == I.STATUS_UNSAFE, v.to_dict()
    assert any(reason.startswith("image_pixels_too_large:") for reason in v.reasons), v.to_dict()


def test_publish_prefilter_blocks_oversized_and_unreadable_images():
    img = np.zeros((120, 120, 3), np.uint8)
    oversized = _write(img, ".png")
    unreadable = _TMP_DIR / "unreadable.jpg"
    unreadable.write_bytes(b"not-an-image")
    old_limit = I.MAX_ASSESS_PIXELS
    try:
        I.MAX_ASSESS_PIXELS = 10_000
        oversized_verdict = I.assess_image_publish_prefilter(oversized)
    finally:
        I.MAX_ASSESS_PIXELS = old_limit
    unreadable_verdict = I.assess_image_publish_prefilter(unreadable)

    assert oversized_verdict.status == I.STATUS_UNSAFE, oversized_verdict.to_dict()
    assert any(
        reason.startswith("image_pixels_too_large:")
        for reason in oversized_verdict.reasons
    ), oversized_verdict.to_dict()
    assert unreadable_verdict.status == I.STATUS_NEEDS_REVIEW, unreadable_verdict.to_dict()
    assert "image_dimensions_unreadable" in unreadable_verdict.reasons


def test_face_image_needs_review():
    face = _first_face_fixture()
    assert face is not None, f"缺少仓库固定人脸 fixture: {FACE_FIXTURE}"
    v = I.assess_image(face)
    assert v.faces > 0, v.to_dict()
    # 含人脸的图：水印命中则 unsafe，否则 needs_review；两者都不允许自动图文发布
    assert v.blocks_image_publish is True, v.to_dict()
    if not v.has_watermark:
        assert v.status == I.STATUS_NEEDS_REVIEW, v.to_dict()


def test_near_duplicate_dedupe():
    img = np.zeros((300, 300, 3), np.uint8)
    img[:, :150] = (40, 90, 160)
    a = _write(img, ".png")
    b = _write(img, ".png")  # 同像素副本（PNG 无损，确定性）
    distinct = np.zeros((300, 300, 3), np.uint8)
    distinct[:150, :] = (200, 30, 30)
    c = _write(distinct, ".png")
    assert I.is_near_duplicate(a, b) is True
    assert I.is_near_duplicate(a, c) is False
    kept = I.dedupe_images([a, b, c])
    assert len(kept) == 2, [str(p) for p in kept]


def test_dependency_missing_degrades_to_needs_review():
    """关键后端缺失时不得静默放过：应判 needs_review（宁可拦）。"""
    clean = _clean_image()
    saved = I._CV_OK
    try:
        I._CV_OK = False  # 模拟 CV 后端缺失
        v = I.assess_image(clean)
        assert v.status == I.STATUS_NEEDS_REVIEW, v.to_dict()
        assert "cv_backend_missing" in v.reasons
    finally:
        I._CV_OK = saved


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"image safety gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
