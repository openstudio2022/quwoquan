"""图片安全/美学门 contract tests（真实 CV：人脸/水印/OCR/去重 + 降级）。

可直接运行：python3 quwoquan_data/tests/test_image_safety_gate.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402
import cv2  # noqa: E402

from _common import image_safety as I  # noqa: E402

FIXTURE_MEDIA = (
    Path(__file__).resolve().parents[2]
    / "quwoquan_service/contracts/metadata/_shared/test_fixtures/media/media"
)


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
    user_dir = FIXTURE_MEDIA / "background" / "user"
    if not user_dir.is_dir():
        return None
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    for f in sorted(user_dir.rglob("*.jpg")):
        img = cv2.imread(str(f))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if len(cas.detectMultiScale(gray, 1.1, 6, minSize=(36, 36))) > 0:
            return f
    return None


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


def test_watermark_image_is_unsafe():
    v = I.assess_image(_watermark_image())
    assert v.has_watermark is True, v.to_dict()
    assert v.status == I.STATUS_UNSAFE, v.to_dict()
    assert v.blocks_image_publish is True


def test_at_handle_is_unsafe():
    v = I.assess_image(_watermark_image("photo by @alpine_walker"))
    assert v.has_watermark is True, v.to_dict()
    assert v.status == I.STATUS_UNSAFE, v.to_dict()


def test_text_heavy_routes_to_article():
    v = I.assess_image(_text_heavy_image())
    assert v.is_text_heavy is True, v.to_dict()
    assert v.status in (I.STATUS_TEXT_HEAVY, I.STATUS_UNSAFE), v.to_dict()


def test_face_image_needs_review():
    face = _first_face_fixture()
    assert face is not None, "未找到可检出人脸的 fixture（应位于 media/background/user/**）"
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
