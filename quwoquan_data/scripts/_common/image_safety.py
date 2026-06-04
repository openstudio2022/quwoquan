"""图片安全/美学评估库(真实 CV)。

后端能力：
- 人脸检测：OpenCV Haar cascade（人物风景常见，检出 -> needs_review 交人工复核，不自动删）。
- 水印/平台文字/文字占比：pytesseract OCR（命中平台名/@handle/版权串 -> unsafe）。
- 近重复：imagehash average_hash 像素级感知哈希。

降级原则（不放水）：关键后端缺失时 status 至少为 needs_review，而非静默判 safe。

本模块是纯逻辑库（非入口），由 media / produce / verify 命令与 content_review 复用。
"""
from __future__ import annotations

import re
import shutil
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


# ─── 后端探测 ──────────────────────────────────────────────────────
try:  # pragma: no cover - 依赖探测
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    _CV_OK = True
except Exception:  # pragma: no cover
    _CV_OK = False

try:  # pragma: no cover
    from PIL import Image  # type: ignore
    import imagehash  # type: ignore

    _HASH_OK = True
except Exception:  # pragma: no cover
    _HASH_OK = False


def _ocr_available() -> bool:
    try:
        import pytesseract  # type: ignore  # noqa: F401
    except Exception:
        return False
    return shutil.which("tesseract") is not None


# ─── 水印/平台/版权词表（与 content_review.PLATFORM_TERMS 对齐的超集）──
PLATFORM_TERMS: tuple[str, ...] = (
    "马蜂窝",
    "携程",
    "小红书",
    "知乎",
    "大众点评",
    "抖音",
    "微博",
    "去哪儿",
    "飞猪",
    "穷游",
    "lonely planet",
    "tripadvisor",
)
WATERMARK_TERMS: tuple[str, ...] = PLATFORM_TERMS + (
    "版权所有",
    "禁止转载",
    "水印",
    "copyright",
    "all rights reserved",
    "©",
    "(c)",
    "摄于",
    "图虫",
    "视觉中国",
    "id:",
)
_HANDLE_RE = re.compile(r"@[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_.]{1,30}")

# ─── 阈值 ──────────────────────────────────────────────────────────
TEXT_HEAVY_RATIO = 0.16  # OCR 文字框面积占比 >= 此值视为"图中带交叠文字 = 文章"
NEAR_DUP_HAMMING = 5  # average_hash 海明距离 <= 此值视为近重复
_OCR_MIN_CONF = 45
_PLACEHOLDER_MAX_EDGE_DELTA = 7.0


STATUS_SAFE = "safe"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_UNSAFE = "unsafe"
STATUS_TEXT_HEAVY = "text_heavy"


@dataclass(frozen=True)
class ImageVerdict:
    path: str
    status: str
    faces: int
    has_watermark: bool
    text_area_ratio: float
    ocr_text: str = ""
    reasons: tuple[str, ...] = field(default_factory=tuple)
    backends: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_text_heavy(self) -> bool:
        return self.text_area_ratio >= TEXT_HEAVY_RATIO

    @property
    def blocks_image_publish(self) -> bool:
        """unsafe / needs_review 都不允许直接进入图文版自动发布。"""
        return self.status in (STATUS_UNSAFE, STATUS_NEEDS_REVIEW)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "status": self.status,
            "faces": self.faces,
            "hasWatermark": self.has_watermark,
            "textAreaRatio": round(self.text_area_ratio, 4),
            "isTextHeavy": self.is_text_heavy,
            "ocrText": self.ocr_text[:200],
            "reasons": list(self.reasons),
            "backends": list(self.backends),
        }


def backend_status() -> dict[str, bool]:
    return {"cv": _CV_OK, "hash": _HASH_OK, "ocr": _ocr_available()}


def _active_backends() -> tuple[str, ...]:
    status = backend_status()
    return tuple(name for name, ok in status.items() if ok)


def _detect_faces(path: Path) -> int:
    if not _CV_OK:
        return -1
    img = cv2.imread(str(path))
    if img is None:
        return -1
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return -1
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(36, 36))
    return int(len(faces))


def _ocr_text_and_ratio(path: Path) -> tuple[str, float, bool]:
    """返回 (ocr_text, text_area_ratio, ocr_ran)。ocr_ran=False 表示未能跑 OCR。"""
    if not _ocr_available() or not _CV_OK:
        return "", 0.0, False
    import pytesseract  # type: ignore

    img = cv2.imread(str(path))
    if img is None:
        return "", 0.0, False
    h, w = img.shape[:2]
    total = float(max(1, h * w))
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    try:
        data = pytesseract.image_to_data(
            rgb,
            lang=_ocr_lang(),
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return "", 0.0, False
    words: list[str] = []
    text_area = 0.0
    n = len(data.get("text", []))
    for i in range(n):
        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = -1.0
        token = str(data["text"][i]).strip()
        if not token or conf < _OCR_MIN_CONF:
            continue
        words.append(token)
        text_area += float(data["width"][i]) * float(data["height"][i])
    return " ".join(words), min(1.0, text_area / total), True


def _ocr_lang() -> str:
    try:
        import pytesseract  # type: ignore

        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    if "chi_sim" in langs:
        return "chi_sim+eng" if "eng" in langs else "chi_sim"
    return "eng"


def _has_watermark(ocr_text: str) -> bool:
    if not ocr_text:
        return False
    lowered = ocr_text.lower()
    for term in WATERMARK_TERMS:
        if term.lower() in lowered:
            return True
    return bool(_HANDLE_RE.search(ocr_text))


def _png_rgb_rows(path: Path) -> tuple[int, int, list[bytes]] | None:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    width = height = 0
    idat = bytearray()
    color_type = -1
    bit_depth = -1
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width <= 0 or height <= 0 or bit_depth != 8 or color_type != 2:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except Exception:
        return None
    stride = width * 3
    rows: list[bytes] = []
    offset = 0
    prev = bytearray(stride)
    for _ in range(height):
        if offset >= len(raw):
            return None
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        if len(row) != stride:
            return None
        if filter_type == 1:
            for i in range(stride):
                row[i] = (row[i] + (row[i - 3] if i >= 3 else 0)) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filter_type != 0:
            return None
        rows.append(bytes(row))
        prev = row
    return width, height, rows


def _low_texture_placeholder(path: Path) -> bool:
    parsed = _png_rgb_rows(path)
    if parsed is None:
        return False
    width, height, rows = parsed
    if width * height < 10000:
        return False
    total_delta = 0
    samples = 0
    for y in range(0, height, max(1, height // 60)):
        row = rows[y]
        for x in range(1, width, max(1, width // 80)):
            i = x * 3
            j = (x - 1) * 3
            total_delta += abs(row[i] - row[j]) + abs(row[i + 1] - row[j + 1]) + abs(row[i + 2] - row[j + 2])
            samples += 3
    if samples == 0:
        return False
    return (total_delta / samples) <= _PLACEHOLDER_MAX_EDGE_DELTA


def is_low_texture_placeholder_graphic(path: str | Path) -> bool:
    return _low_texture_placeholder(Path(path))


def assess_image(path: str | Path) -> ImageVerdict:
    p = Path(path)
    backends = _active_backends()
    if not p.is_file():
        return ImageVerdict(
            path=str(p),
            status=STATUS_NEEDS_REVIEW,
            faces=-1,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=("file_missing",),
            backends=backends,
        )

    reasons: list[str] = []
    if _low_texture_placeholder(p):
        reasons.append("low_texture_placeholder_graphic")
    faces = _detect_faces(p)
    ocr_text, text_ratio, ocr_ran = _ocr_text_and_ratio(p)
    has_watermark = _has_watermark(ocr_text)

    if not _CV_OK:
        reasons.append("cv_backend_missing")
    if not ocr_ran:
        reasons.append("ocr_unavailable")
    if faces > 0:
        reasons.append(f"faces_detected:{faces}")
    if has_watermark:
        reasons.append("watermark_or_platform_text")
    if text_ratio >= TEXT_HEAVY_RATIO:
        reasons.append(f"text_heavy:{round(text_ratio, 3)}")

    # 状态优先级：unsafe > needs_review > text_heavy > safe
    if "low_texture_placeholder_graphic" in reasons:
        status = STATUS_UNSAFE
    elif has_watermark:
        status = STATUS_UNSAFE
    elif faces > 0 or not _CV_OK or not ocr_ran:
        status = STATUS_NEEDS_REVIEW
    elif text_ratio >= TEXT_HEAVY_RATIO:
        status = STATUS_TEXT_HEAVY
    else:
        status = STATUS_SAFE

    return ImageVerdict(
        path=str(p),
        status=status,
        faces=faces,
        has_watermark=has_watermark,
        text_area_ratio=text_ratio,
        ocr_text=ocr_text,
        reasons=tuple(reasons),
        backends=backends,
    )


# ─── 近重复 ────────────────────────────────────────────────────────
def _avg_hash(path: Path):
    if not _HASH_OK:
        return None
    try:
        with Image.open(path) as im:
            return imagehash.average_hash(im.convert("RGB"))
    except Exception:
        return None


def is_near_duplicate(path_a: str | Path, path_b: str | Path, *, threshold: int = NEAR_DUP_HAMMING) -> bool:
    ha = _avg_hash(Path(path_a))
    hb = _avg_hash(Path(path_b))
    if ha is None or hb is None:
        return False
    return bool((ha - hb) <= threshold)


def dedupe_images(paths: Sequence[str | Path], *, threshold: int = NEAR_DUP_HAMMING) -> list[Path]:
    """按感知哈希去重，保留先出现者。哈希后端缺失时退化为按解析路径去重。"""
    kept: list[Path] = []
    kept_hashes: list = []
    seen_resolved: set[str] = set()
    for raw in paths:
        p = Path(raw)
        key = str(p.resolve())
        if key in seen_resolved:
            continue
        seen_resolved.add(key)
        h = _avg_hash(p)
        if h is None:
            kept.append(p)
            continue
        if any((h - kh) <= threshold for kh in kept_hashes):
            continue
        kept.append(p)
        kept_hashes.append(h)
    return kept


def assess_images(paths: Iterable[str | Path]) -> list[ImageVerdict]:
    return [assess_image(p) for p in paths]


def assess_asset_sources(assets: Sequence[dict]) -> dict:
    """对一组 asset 记录（含 sourcePath）做图片体检并聚合。

    返回：{verdicts:[...], unsafe:[...], needsReview:[...], textHeavy:[...],
            duplicateGroups:[[idx...]], backends:{...}, summary:{...}}。
    near-dup 以 sourcePath 的感知哈希在集合内两两比较。
    """
    verdicts: list[dict] = []
    paths: list[Path] = []
    unsafe: list[str] = []
    needs_review: list[str] = []
    text_heavy: list[str] = []
    for asset in assets:
        source = asset.get("sourcePath") if isinstance(asset, dict) else None
        asset_id = str(asset.get("assetId") or asset.get("fileName") or "") if isinstance(asset, dict) else ""
        if not source:
            needs_review.append(asset_id or "<no-source>")
            verdicts.append({"assetId": asset_id, "status": STATUS_NEEDS_REVIEW, "reasons": ["asset_missing_sourcePath"]})
            paths.append(Path("/nonexistent"))
            continue
        verdict = assess_image(source)
        item = verdict.to_dict()
        item["assetId"] = asset_id
        verdicts.append(item)
        paths.append(Path(source))
        if verdict.status == STATUS_UNSAFE:
            unsafe.append(asset_id)
        elif verdict.status == STATUS_NEEDS_REVIEW:
            needs_review.append(asset_id)
        if verdict.is_text_heavy:
            text_heavy.append(asset_id)

    # 集合内近重复分组
    hashes = [_avg_hash(p) for p in paths]
    dup_groups: list[list[int]] = []
    used: set[int] = set()
    for i in range(len(hashes)):
        if i in used or hashes[i] is None:
            continue
        group = [i]
        for j in range(i + 1, len(hashes)):
            if j in used or hashes[j] is None:
                continue
            if (hashes[i] - hashes[j]) <= NEAR_DUP_HAMMING:
                group.append(j)
                used.add(j)
        if len(group) > 1:
            dup_groups.append(group)
            used.update(group)

    return {
        "verdicts": verdicts,
        "unsafe": unsafe,
        "needsReview": needs_review,
        "textHeavy": text_heavy,
        "duplicateGroups": dup_groups,
        "backends": backend_status(),
        "summary": {
            "total": len(verdicts),
            "unsafe": len(unsafe),
            "needsReview": len(needs_review),
            "textHeavy": len(text_heavy),
            "duplicateGroups": len(dup_groups),
        },
    }
