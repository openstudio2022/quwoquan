"""图片安全/美学评估库(真实 CV)。

后端能力：
- 人脸检测：OpenCV Haar cascade（人物风景常见，检出 -> needs_review 交人工复核，不自动删）。
- 水印/平台文字/文字占比：pytesseract OCR（命中平台名/@handle/版权串 -> unsafe）。
- 近重复：imagehash pHash 感知哈希。

降级原则（不放水）：关键后端缺失时 status 至少为 needs_review，而非静默判 safe。

本模块是纯逻辑库（非入口），由 media / post / verify 命令与 content_review 复用。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import warnings
import zlib
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Sequence

from core.runtime_policy import active_runtime_policy

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
    except OSError:
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
    "图虫",
    "视觉中国",
    "id:",
)
COPYRIGHT_SYMBOL_TERMS: tuple[str, ...] = ("©", "(c)")
RIGHTS_CONTEXT_TERMS: tuple[str, ...] = (
    "copyright",
    "all rights reserved",
    "版权所有",
    "禁止转载",
    "保留所有权利",
    "未经授权",
    "转载",
    "授权",
    "作者",
    "摄影",
    "photo by",
    "photographer",
)
_HANDLE_RE = re.compile(r"@[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_.]{1,30}")


class WatermarkProneSourceMarker(StrEnum):
    """Stable provenance markers whose original images commonly retain marks.

    This is a source-provenance safety rule, not a rights judgement. A Commons
    re-host can be correctly licensed while its original bitmap still carries a
    retired platform watermark, so the two checks cannot substitute for each
    other.
    """

    PANORAMIO = "panoramio"


def watermark_prone_source_reason(values: Iterable[str]) -> str:
    """Return a deterministic exclusion reason for known watermark-prone origin.

    Pixel OCR remains the primary detector. This provenance guard closes the
    documented false-negative class where small corner overlays are below OCR's
    confidence threshold but the original file identity explicitly records its
    watermark-prone hosting origin.
    """

    normalized = "\n".join(str(value or "").casefold() for value in values)
    for marker in WatermarkProneSourceMarker:
        if marker.value in normalized:
            return f"watermark_prone_source_provenance:{marker.value}"
    return ""

# ─── 阈值 ──────────────────────────────────────────────────────────
TEXT_HEAVY_RATIO = 0.16  # OCR 文字框面积占比 >= 此值视为"图中带交叠文字 = 文章"
NEAR_DUP_HAMMING = 5  # pHash 海明距离 <= 此值视为近重复
_OCR_MIN_CONF = 45
_PLACEHOLDER_MAX_EDGE_DELTA = 7.0
OCR_TIMEOUT_SECONDS = active_runtime_policy().ocr_timeout_seconds
MAX_ASSESS_PIXELS = max(1_000_000, int(os.environ.get("QWQ_IMAGE_MAX_ASSESS_PIXELS", "50000000")))
OCR_MAX_PIXELS = max(300_000, int(os.environ.get("QWQ_IMAGE_OCR_MAX_PIXELS", "2000000")))

_ASSESS_CACHE: dict[tuple[str, bool, tuple[str, ...], int, int], ImageVerdict] = {}


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

    @classmethod
    def from_dict(cls, data: dict, *, path: str = "") -> "ImageVerdict":
        return cls(
            path=path or str(data.get("path") or ""),
            status=str(data.get("status") or STATUS_NEEDS_REVIEW),
            faces=int(data.get("faces") if data.get("faces") is not None else -1),
            has_watermark=bool(data.get("hasWatermark")),
            text_area_ratio=float(data.get("textAreaRatio") or 0.0),
            ocr_text=str(data.get("ocrText") or ""),
            reasons=tuple(str(item) for item in (data.get("reasons") or [])),
            backends=tuple(str(item) for item in (data.get("backends") or [])),
        )


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
    min_face = max(48, round(min(gray.shape[:2]) * 0.08))
    candidates = cascade.detectMultiScale(
        gray,
        scaleFactor=1.12,
        minNeighbors=8,
        minSize=(min_face, min_face),
    )
    eye_path = cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
    eye_cascade = cv2.CascadeClassifier(eye_path)
    if eye_cascade.empty():
        return -1
    confirmed = 0
    for x, y, width, height in candidates:
        upper_face = gray[y:y + max(1, round(height * 0.65)), x:x + width]
        eyes = eye_cascade.detectMultiScale(
            upper_face,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(max(12, width // 8), max(8, height // 10)),
        )
        if len(eyes) > 0:
            confirmed += 1
    return confirmed


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    if not _HASH_OK:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as im:
                return int(im.width), int(im.height)
    except Exception:
        return None


def _ocr_text_and_ratio(path: Path) -> tuple[str, float, bool]:
    """返回 (ocr_text, text_area_ratio, ocr_ran)。ocr_ran=False 表示未能跑 OCR。"""
    if not _ocr_available() or not _CV_OK:
        return "", 0.0, False
    import pytesseract  # type: ignore

    img = cv2.imread(str(path))
    if img is None:
        return "", 0.0, False
    h, w = img.shape[:2]
    total_pixels = max(1, h * w)
    if total_pixels > OCR_MAX_PIXELS:
        scale = (float(OCR_MAX_PIXELS) / float(total_pixels)) ** 0.5
        img = cv2.resize(
            img,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
        h, w = img.shape[:2]
    total = float(max(1, h * w))
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    try:
        data = pytesseract.image_to_data(
            rgb,
            lang=_ocr_lang(),
            output_type=pytesseract.Output.DICT,
            timeout=OCR_TIMEOUT_SECONDS,
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
    # OCR often misreads scenic signboards, exhibit plaques, currency marks, or
    # punctuation as a bare copyright symbol. A symbol alone is not a publish
    # blocker; it becomes a watermark/copyright signal only with rights context.
    if any(term in lowered for term in COPYRIGHT_SYMBOL_TERMS) and any(
        term.lower() in lowered for term in RIGHTS_CONTEXT_TERMS
    ):
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


def assess_image(path: str | Path, *, require_ocr: bool = True) -> ImageVerdict:
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
    try:
        content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        content_hash = ""
    reasons: list[str] = []
    cache_key = (content_hash, bool(require_ocr), backends, int(MAX_ASSESS_PIXELS), int(OCR_MAX_PIXELS))
    if content_hash and cache_key in _ASSESS_CACHE:
        return replace(_ASSESS_CACHE[cache_key], path=str(p))

    dims = _image_dimensions(p)
    if dims is None:
        verdict = ImageVerdict(
            path=str(p),
            status=STATUS_NEEDS_REVIEW,
            faces=-1,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=("image_dimensions_unreadable",),
            backends=backends,
        )
        if content_hash:
            _ASSESS_CACHE[cache_key] = verdict
        return verdict
    width, height = dims
    pixels = width * height
    if pixels > MAX_ASSESS_PIXELS:
        verdict = ImageVerdict(
            path=str(p),
            status=STATUS_UNSAFE,
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(f"image_pixels_too_large:{pixels}>{MAX_ASSESS_PIXELS}",),
            backends=backends,
        )
        if content_hash:
            _ASSESS_CACHE[cache_key] = verdict
        return verdict

    if _low_texture_placeholder(p):
        reasons.append("low_texture_placeholder_graphic")
    faces = _detect_faces(p)
    if require_ocr:
        ocr_text, text_ratio, ocr_ran = _ocr_text_and_ratio(p)
    else:
        ocr_text, text_ratio, ocr_ran = "", 0.0, True
        reasons.append("ocr_skipped_trusted_open_license_source")
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

    verdict = ImageVerdict(
        path=str(p),
        status=status,
        faces=faces,
        has_watermark=has_watermark,
        text_area_ratio=text_ratio,
        ocr_text=ocr_text,
        reasons=tuple(reasons),
        backends=backends,
    )
    if content_hash:
        _ASSESS_CACHE[cache_key] = verdict
    return verdict


def _persistent_cache_key(content_hash: str, *, require_ocr: bool, backends: tuple[str, ...]) -> str:
    payload = {
        "contentHash": content_hash,
        "requireOcr": bool(require_ocr),
        "backends": list(backends),
        "maxAssessPixels": int(MAX_ASSESS_PIXELS),
        "ocrMaxPixels": int(OCR_MAX_PIXELS),
        "ocrTimeoutSeconds": int(OCR_TIMEOUT_SECONDS),
        "textHeavyRatio": float(TEXT_HEAVY_RATIO),
        "ocrMinConf": int(_OCR_MIN_CONF),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _persistent_cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / key[:2] / f"{key}.json"


def assess_image_cached(
    path: str | Path,
    *,
    cache_dir: str | Path | None = None,
    require_ocr: bool = True,
) -> ImageVerdict:
    """Assess image with a process-independent sha256 cache.

    The cache stores verdicts keyed by image bytes and active gate settings, so
    retries and later workflow stages can reuse expensive CV/OCR results
    without weakening the safety decision.
    """
    p = Path(path)
    if cache_dir is None:
        return assess_image(p, require_ocr=require_ocr)
    if not p.is_file():
        return assess_image(p, require_ocr=require_ocr)
    try:
        content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return assess_image(p, require_ocr=require_ocr)
    if not content_hash:
        return assess_image(p, require_ocr=require_ocr)
    backends = _active_backends()
    cache_path = _persistent_cache_path(
        Path(cache_dir),
        _persistent_cache_key(content_hash, require_ocr=require_ocr, backends=backends),
    )
    if cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if str(data.get("schemaVersion") or "") == "quwoquan.image_safety_verdict_cache":
                return ImageVerdict.from_dict(data.get("verdict") or {}, path=str(p))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            # A stale or partial cache entry is disposable; the image is
            # reassessed below and the cache is atomically replaced.
            cache_path.unlink(missing_ok=True)
    verdict = assess_image(p, require_ocr=require_ocr)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "schemaVersion": "quwoquan.image_safety_verdict_cache",
                    "contentHash": content_hash,
                    "requireOcr": bool(require_ocr),
                    "verdict": verdict.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError):
        # Cache persistence is an optimization. The freshly computed verdict
        # remains authoritative for this invocation.
        return verdict
    return verdict


def assess_image_publish_prefilter(path: str | Path) -> ImageVerdict:
    """Fast structural gate for source candidate planning.

    This intentionally avoids OCR and face detection. Heavy checks run later on
    selected assets during compose/review/media gates. The prefilter only blocks
    conditions that are cheap and never publishable: missing/unreadable files,
    oversized originals, and obvious placeholder graphics.
    """
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
    dims = _image_dimensions(p)
    if dims is None:
        return ImageVerdict(
            path=str(p),
            status=STATUS_NEEDS_REVIEW,
            faces=-1,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=("image_dimensions_unreadable",),
            backends=backends,
        )
    width, height = dims
    pixels = width * height
    if pixels > MAX_ASSESS_PIXELS:
        return ImageVerdict(
            path=str(p),
            status=STATUS_UNSAFE,
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(f"image_pixels_too_large:{pixels}>{MAX_ASSESS_PIXELS}",),
            backends=backends,
        )
    if _low_texture_placeholder(p):
        return ImageVerdict(
            path=str(p),
            status=STATUS_UNSAFE,
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=("low_texture_placeholder_graphic",),
            backends=backends,
        )
    return ImageVerdict(
        path=str(p),
        status=STATUS_SAFE,
        faces=0,
        has_watermark=False,
        text_area_ratio=0.0,
        reasons=(),
        backends=backends,
    )


# ─── 近重复 ────────────────────────────────────────────────────────
def _avg_hash(path: Path):
    if not _HASH_OK:
        return None
    try:
        with Image.open(path) as im:
            return imagehash.phash(im.convert("RGB"))
    except Exception:
        return None


def is_near_duplicate(path_a: str | Path, path_b: str | Path, *, threshold: int = NEAR_DUP_HAMMING) -> bool:
    ha = _avg_hash(Path(path_a))
    hb = _avg_hash(Path(path_b))
    if ha is None or hb is None:
        return False
    return bool((ha - hb) <= threshold)


def _avg_hash_bytes(data: bytes):
    if not _HASH_OK or not data:
        return None
    import io

    try:
        with Image.open(io.BytesIO(data)) as im:
            return imagehash.phash(im.convert("RGB"))
    except Exception:
        return None


def dedupe_image_payloads(
    payloads: Sequence[dict], *, threshold: int = NEAR_DUP_HAMMING
) -> tuple[list[dict], list[int]]:
    """对内存图片字节按感知哈希去重（下载落盘前），保留先出现者。

    每项需含 "bytes"。返回 (保留项, 被判重复的原索引列表)。
    哈希后端缺失时退化为按 sha256/字节恒等去重，绝不放水成「全保留」。
    """
    kept: list[dict] = []
    kept_hashes: list = []
    seen_sha: set[str] = set()
    dup_indices: list[int] = []
    for idx, payload in enumerate(payloads):
        data = payload.get("bytes") if isinstance(payload, dict) else None
        if not data:
            continue
        sha = payload.get("sha256") or hashlib.sha256(data).hexdigest()
        if sha in seen_sha:
            dup_indices.append(idx)
            continue
        h = _avg_hash_bytes(data)
        if h is not None and any((h - kh) <= threshold for kh in kept_hashes):
            dup_indices.append(idx)
            continue
        seen_sha.add(sha)
        if h is not None:
            kept_hashes.append(h)
        kept.append(payload)
    return kept, dup_indices


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
