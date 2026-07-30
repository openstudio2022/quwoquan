"""下载阶段图片格式化：尺寸读取 + 物理多变体（webp/压缩）生成。

唯一变体真相源是 `media_asset_url.IMAGE_VARIANT_PROFILES`（thumbnail/display/cover/full
的宽度、格式、质量）。本模块在 download 阶段据此把每张原图物理压成 webp 变体（仅缩小不放大），
并保留 original。发布阶段 `materialize_release_media` 仍按同一 profile 把变体表达为 CDN 处理
指令——两边消费同一份 profile 定义，不维护第二套尺寸表（R25 抽象克制）。

变体文件落在来源单元 assets 的同名子目录：
    assets/{NNN}_{slug}.{ext}                 # 原图（保 sha 完整性）
    assets/{NNN}_{slug}.variants/thumbnail.webp
    assets/{NNN}_{slug}.variants/display.webp
    assets/{NNN}_{slug}.variants/cover.webp
    assets/{NNN}_{slug}.variants/full.webp
"""

from __future__ import annotations

import hashlib
import io
import warnings
from typing import Any

from core.image_decode import ImageProbe, probe_image_bytes
from core.image_decode import pil_available as decode_pil_available
from core.media_asset_url import IMAGE_VARIANT_POLICY_VERSION, IMAGE_VARIANT_PROFILES
from core.media_processing_policy import MEDIA_PROCESSING_POLICY

try:  # pragma: no cover - 依赖探测
    from PIL import Image  # type: ignore

    _PIL_OK = True
except ImportError:  # pragma: no cover
    _PIL_OK = False

# 仅这些 profile 在 download 阶段物理落地（original 单列；video 的 adaptive 不在此）。
LOCAL_VARIANT_PROFILES = ("thumbnail", "display", "cover", "full")
WEBP_METHOD = MEDIA_PROCESSING_POLICY.webp_method
SQUARE_COVER_PROFILE = "cover"


def pil_available() -> bool:
    return _PIL_OK and decode_pil_available()


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """读图片像素宽高；非图片/解析失败返回 None。"""
    probe = probe_image_bytes(data)
    return (probe.width, probe.height) if probe.succeeded else None


def build_local_variants(data: bytes, *, base_name: str) -> list[dict[str, Any]]:
    """把原图字节压成 webp 多变体（仅缩小）。返回每个变体的元数据 + 字节。

    每项：{profile, fileName, width, height, format, quality, bytes, sha256}。
    fileName 形如 "{base_name}.variants/{profile}.webp"（相对来源单元 assets/）。
    原图小于某 profile 宽度时跳过该 profile（不放大、不虚增带宽）。
    """
    probe: ImageProbe = probe_image_bytes(data)
    if not _PIL_OK or not probe.succeeded:
        return []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                im = im.convert("RGB")
                src_w, src_h = im.width, im.height
                out: list[dict[str, Any]] = []
                for profile in LOCAL_VARIANT_PROFILES:
                    cfg = IMAGE_VARIANT_PROFILES.get(profile)
                    if not cfg:
                        continue
                    target_w = int(cfg["width"])
                    # 仅缩小：原图比目标宽则等比缩放，否则用原尺寸（webp 重编码省带宽）。
                    if src_w > target_w:
                        target_h = max(1, round(src_h * target_w / src_w))
                        resized = im.resize((target_w, target_h), Image.LANCZOS)
                    else:
                        target_w, target_h = src_w, src_h
                        resized = im
                    buf = io.BytesIO()
                    resized.save(
                        buf,
                        format="WEBP",
                        quality=int(cfg["quality"]),
                        method=WEBP_METHOD,
                    )
                    body = buf.getvalue()
                    out.append(
                        {
                            "profile": profile,
                            "fileName": f"{base_name}.variants/{profile}.webp",
                            "width": target_w,
                            "height": target_h,
                            "format": "webp",
                            "quality": int(cfg["quality"]),
                            "bytes": body,
                            "byteSize": len(body),
                            "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
                        }
                    )
                return out
    except (
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
        OSError,
        ValueError,
    ):
        return []


def build_center_square_cover_derivative(data: bytes) -> dict[str, Any] | None:
    """Build one deterministic square derivative from the canonical cover profile.

    The operation is intentionally narrow: decode to RGB, take the integer
    center-square crop, resize with LANCZOS to the existing ``cover`` width and
    encode WebP with the repository-owned quality/method. Sources smaller than
    the cover square are rejected instead of being upscaled.
    """

    probe: ImageProbe = probe_image_bytes(data)
    profile = IMAGE_VARIANT_PROFILES.get(SQUARE_COVER_PROFILE)
    if not _PIL_OK or not probe.succeeded or not profile:
        return None
    target_size = int(profile["width"])
    if min(probe.width, probe.height) < target_size:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                source = source.convert("RGB")
                source_width, source_height = source.size
                square_size = min(source_width, source_height)
                left = (source_width - square_size) // 2
                top = (source_height - square_size) // 2
                crop_box = (left, top, left + square_size, top + square_size)
                square = source.crop(crop_box)
                if square_size != target_size:
                    square = square.resize(
                        (target_size, target_size),
                        Image.Resampling.LANCZOS,
                    )
                output = io.BytesIO()
                square.save(
                    output,
                    format="WEBP",
                    quality=int(profile["quality"]),
                    method=WEBP_METHOD,
                    lossless=False,
                    exact=True,
                )
                body = output.getvalue()
                return {
                    "profile": SQUARE_COVER_PROFILE,
                    "policyVersion": IMAGE_VARIANT_POLICY_VERSION,
                    "sourceWidth": source_width,
                    "sourceHeight": source_height,
                    "cropBox": list(crop_box),
                    "width": target_size,
                    "height": target_size,
                    "colorMode": "RGB",
                    "format": "webp",
                    "mimeType": "image/webp",
                    "quality": int(profile["quality"]),
                    "method": WEBP_METHOD,
                    "bytes": body,
                    "byteSize": len(body),
                    "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
                }
    except (
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
        OSError,
        ValueError,
    ):
        return None


__all__ = [
    "LOCAL_VARIANT_PROFILES",
    "SQUARE_COVER_PROFILE",
    "build_center_square_cover_derivative",
    "build_local_variants",
    "image_dimensions",
    "pil_available",
]
