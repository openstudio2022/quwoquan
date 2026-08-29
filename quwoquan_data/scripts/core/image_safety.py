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
import math
import re
import shutil
import struct
import tempfile
import warnings
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Sequence

from core.runtime_policy import active_runtime_policy
from core.image_decode import ImageDecodeFailure, probe_image_path
from core.media_processing_policy import MEDIA_PROCESSING_POLICY
from core.media_source_provenance import (
    REASON_PREFIX,
    WATERMARK_PRONE_ORIGIN_PLATFORMS,
    declared_origin_platform,
)

# ─── 后端探测 ──────────────────────────────────────────────────────
try:  # pragma: no cover - 依赖探测
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    _CV_OK = True
except Exception:  # pragma: no cover
    _CV_OK = False

try:  # pragma: no cover
    from PIL import Image  # type: ignore

    _PIL_OK = True
except ImportError:  # pragma: no cover
    _PIL_OK = False

try:  # pragma: no cover
    import imagehash  # type: ignore

    _HASH_OK = _PIL_OK
except ImportError:  # pragma: no cover
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


def watermark_prone_source_reason(values: Iterable[str]) -> str:
    """Return a deterministic exclusion reason for known watermark-prone origin.

    这是文件身份层的 OCR 补充判据：像素 OCR 仍是主检测器，此处只关闭「角标
    低于置信阈值但文件身份本身写明高风险托管源」这一漏检类。高风险平台闭集
    的唯一真相源是 ``core.media_source_provenance``；出处类别裁决由该模块的
    ``watermark_prone_provenance_reason`` 承担，本函数不做出处类别判定。
    """

    platform = declared_origin_platform(values)
    if platform in WATERMARK_PRONE_ORIGIN_PLATFORMS:
        return f"{REASON_PREFIX}:{platform.value}"
    return ""

# ─── 阈值 ──────────────────────────────────────────────────────────
TEXT_HEAVY_RATIO = 0.16  # OCR 文字框面积占比 >= 此值视为"图中带交叠文字 = 文章"
NEAR_DUP_HAMMING = 5  # pHash 海明距离 <= 此值视为近重复
_OCR_MIN_CONF = 45
_PLACEHOLDER_MAX_EDGE_DELTA = 7.0
OCR_TIMEOUT_SECONDS = active_runtime_policy().ocr_timeout_seconds
MAX_ASSESS_PIXELS = MEDIA_PROCESSING_POLICY.max_assessment_image_pixels
ASSESSMENT_JPEG_QUALITY = MEDIA_PROCESSING_POLICY.assessment_jpeg_quality
MAX_PUBLISHABLE_PIXELS = MEDIA_PROCESSING_POLICY.max_publishable_image_pixels
OCR_MAX_PIXELS = MEDIA_PROCESSING_POLICY.ocr_image_pixels

_ASSESS_CACHE: dict[
    tuple[str, bool, tuple[str, ...], int, int, int],
    ImageVerdict,
] = {}


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


from core.image_safety_backends import (
    _detect_faces,
    _has_watermark,
    _image_dimensions,
    _low_texture_placeholder,
    _ocr_lang,
    _ocr_text_and_ratio,
    is_low_texture_placeholder_graphic,
)


@contextmanager
def _assessment_image(
    path: Path,
    *,
    width: int,
    height: int,
):
    """Yield a bounded disposable CV/OCR copy without mutating source bytes."""
    pixels = width * height
    if pixels <= MAX_ASSESS_PIXELS:
        yield path, ""
        return
    if not _PIL_OK:
        yield None, "assessment_resize_backend_missing"
        return
    scale = math.sqrt(MAX_ASSESS_PIXELS / pixels)
    target_size = (
        max(1, math.floor(width * scale)),
        max(1, math.floor(height * scale)),
    )
    with tempfile.TemporaryDirectory(prefix="qwq-image-assessment-") as temp_dir:
        assessment_path = Path(temp_dir) / "assessment.jpg"
        try:
            with Image.open(path) as image:
                # CV/OCR only need a bounded visual sample. Re-encoding a large
                # photo as PNG is both lossless and disproportionately expensive.
                # Preserve source bytes and use a policy-owned JPEG assessment copy.
                assessment = image.convert("RGB") if image.mode != "RGB" else image
                assessment.thumbnail(target_size, Image.Resampling.LANCZOS)
                assessment.save(
                    assessment_path,
                    format="JPEG",
                    quality=ASSESSMENT_JPEG_QUALITY,
                    optimize=False,
                )
        except (OSError, ValueError):
            yield None, "assessment_resize_failed"
            return
        assessed_width, assessed_height = _image_dimensions(assessment_path) or (0, 0)
        yield (
            assessment_path,
            f"assessment_downscaled:{pixels}->{assessed_width * assessed_height}",
        )


















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
    except OSError:
        content_hash = ""
    reasons: list[str] = []
    cache_key = (
        content_hash,
        bool(require_ocr),
        backends,
        int(MAX_PUBLISHABLE_PIXELS),
        int(MAX_ASSESS_PIXELS),
        int(OCR_MAX_PIXELS),
    )
    if content_hash and cache_key in _ASSESS_CACHE:
        return replace(_ASSESS_CACHE[cache_key], path=str(p))

    probe = probe_image_path(p)
    if not probe.succeeded:
        status = (
            STATUS_UNSAFE
            if probe.failure is ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED
            else STATUS_NEEDS_REVIEW
        )
        verdict = ImageVerdict(
            path=str(p),
            status=status,
            faces=0 if status == STATUS_UNSAFE else -1,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(f"image_decode_{probe.failure.value}",),
            backends=backends,
        )
        if content_hash:
            _ASSESS_CACHE[cache_key] = verdict
        return verdict
    width, height = probe.width, probe.height
    pixels = width * height
    if pixels > MAX_PUBLISHABLE_PIXELS:
        verdict = ImageVerdict(
            path=str(p),
            status=STATUS_UNSAFE,
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(f"image_pixels_too_large:{pixels}>{MAX_PUBLISHABLE_PIXELS}",),
            backends=backends,
        )
        if content_hash:
            _ASSESS_CACHE[cache_key] = verdict
        return verdict

    with _assessment_image(p, width=width, height=height) as (assessment_path, resize_reason):
        if assessment_path is None:
            verdict = ImageVerdict(
                path=str(p),
                status=STATUS_NEEDS_REVIEW,
                faces=-1,
                has_watermark=False,
                text_area_ratio=0.0,
                reasons=(resize_reason,),
                backends=backends,
            )
            if content_hash:
                _ASSESS_CACHE[cache_key] = verdict
            return verdict
        if resize_reason:
            reasons.append(resize_reason)
        if _low_texture_placeholder(assessment_path):
            reasons.append("low_texture_placeholder_graphic")
        faces = _detect_faces(assessment_path)
        if require_ocr:
            ocr_text, text_ratio, ocr_ran = _ocr_text_and_ratio(assessment_path)
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
        "maxPublishablePixels": int(MAX_PUBLISHABLE_PIXELS),
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
    retries and later execution stages can reuse expensive CV/OCR results
    without weakening the safety decision.
    """
    p = Path(path)
    if cache_dir is None:
        return assess_image(p, require_ocr=require_ocr)
    if not p.is_file():
        return assess_image(p, require_ocr=require_ocr)
    try:
        content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
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
            if str(data.get("schema") or "") == "quwoquan.image_safety_verdict_cache":
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
                    "schema": "quwoquan.image_safety_verdict_cache",
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
    source images above the publish contract, and obvious placeholder graphics.
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
    probe = probe_image_path(p)
    if not probe.succeeded:
        status = (
            STATUS_UNSAFE
            if probe.failure is ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED
            else STATUS_NEEDS_REVIEW
        )
        return ImageVerdict(
            path=str(p),
            status=status,
            faces=0 if status == STATUS_UNSAFE else -1,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(f"image_decode_{probe.failure.value}",),
            backends=backends,
        )
    width, height = probe.width, probe.height
    pixels = width * height
    if pixels > MAX_PUBLISHABLE_PIXELS:
        return ImageVerdict(
            path=str(p),
            status=STATUS_UNSAFE,
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(f"image_pixels_too_large:{pixels}>{MAX_PUBLISHABLE_PIXELS}",),
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
from core.image_deduplication import (
    assess_asset_sources,
    assess_images,
    dedupe_image_payloads,
    dedupe_images,
    is_near_duplicate,
)
