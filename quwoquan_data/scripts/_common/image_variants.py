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
from typing import Any

from _common.media_asset_url import IMAGE_VARIANT_PROFILES

try:  # pragma: no cover - 依赖探测
    from PIL import Image  # type: ignore

    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False

# 仅这些 profile 在 download 阶段物理落地（original 单列；video 的 adaptive 不在此）。
LOCAL_VARIANT_PROFILES = ("thumbnail", "display", "cover", "full")


def pil_available() -> bool:
    return _PIL_OK


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """读图片像素宽高；非图片/解析失败返回 None。"""
    if not _PIL_OK or not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None


def build_local_variants(data: bytes, *, base_name: str) -> list[dict[str, Any]]:
    """把原图字节压成 webp 多变体（仅缩小）。返回每个变体的元数据 + 字节。

    每项：{profile, fileName, width, height, format, quality, bytes, sha256}。
    fileName 形如 "{base_name}.variants/{profile}.webp"（相对来源单元 assets/）。
    原图小于某 profile 宽度时跳过该 profile（不放大、不虚增带宽）。
    """
    if not _PIL_OK or not data:
        return []
    try:
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
                resized.save(buf, format="WEBP", quality=int(cfg["quality"]), method=6)
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
    except Exception:
        return []


__all__ = [
    "LOCAL_VARIANT_PROFILES",
    "pil_available",
    "image_dimensions",
    "build_local_variants",
]
