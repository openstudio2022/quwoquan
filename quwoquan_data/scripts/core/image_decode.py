"""Typed and warning-free image metadata probing for untrusted media bytes."""
from __future__ import annotations

import io
import math
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.media_processing_policy import MEDIA_PROCESSING_POLICY

try:  # pragma: no cover - dependency detection
    from PIL import Image, ImageOps, UnidentifiedImageError  # type: ignore

    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]
    UnidentifiedImageError = OSError  # type: ignore[assignment,misc]
    _PIL_AVAILABLE = False

# 源栅格像素上限只在 media_processing.policy.yaml 声明一次。PIL 自带的解压炸弹阈值
# （默认约 1.79 亿）在这里对齐到同一个数，否则全景接片会在策略允许的范围内被 PIL
# 先行判否，形成一条策略文件里看不见的第二阈值。
MAX_SOURCE_PIXELS = MEDIA_PROCESSING_POLICY.max_source_pixels
if _PIL_AVAILABLE:
    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS


class ImageDecodeFailure(StrEnum):
    EMPTY = "empty"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    UNREADABLE = "unreadable"
    PIXEL_LIMIT_EXCEEDED = "pixel_limit_exceeded"


# EXIF Orientation（TIFF tag 274）。取值 5..8 含 90° 旋转，其存储栅格的宽高与显示
# 宽高互换。`Image.size` 只报存储栅格，因此一张 EXIF 声明旋转的横向全景图会被读成
# 极端竖图，进而让相关性、封面候选、交付宽度与字节预算全部按转置后的几何判定。
# 交付端（浏览器、Flutter、CDN）都按 EXIF 呈现，故本边界统一报显示几何。
_EXIF_ORIENTATION_TAG = 274
_EXIF_ORIENTATIONS_SWAPPING_AXES = frozenset({5, 6, 7, 8})


def _header_resident_orientation(image) -> int | None:
    """读文件头里已解析出的 EXIF Orientation；需要解码像素才能拿到时返回 None。

    这个边界的价值就在于不解码像素——它要在超限或损坏的输入上给出 typed 结论。
    但 ``PngImageFile.getexif()`` 在 ``info`` 里没有 exif 时会回退到整帧 ``load()``，
    于是一个只有 IHDR 的超限 PNG 会被解码一次并把「像素超限」变成「不可读」。
    因此只在 EXIF 随文件头在场时取方向：JPEG/WebP 的 APP1 落在 ``info['exif']``，
    TIFF 落在 ``tag_v2``，两者都不需要解码。
    """

    if "exif" not in image.info and not hasattr(image, "tag_v2"):
        return None
    orientation = image.getexif().get(_EXIF_ORIENTATION_TAG)
    return orientation if isinstance(orientation, int) else None


@dataclass(frozen=True, slots=True)
class ImageProbe:
    width: int = 0
    height: int = 0
    mime_type: str = ""
    failure: ImageDecodeFailure | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure is None

    @property
    def pixels(self) -> int:
        return self.width * self.height


def pil_available() -> bool:
    return _PIL_AVAILABLE


def _probe(stream: io.BytesIO | Path) -> ImageProbe:
    if not _PIL_AVAILABLE:
        return ImageProbe(failure=ImageDecodeFailure.BACKEND_UNAVAILABLE)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                width, height = image.size
                mime_type = str(Image.MIME.get(image.format or "") or "")
                if (
                    _header_resident_orientation(image)
                    in _EXIF_ORIENTATIONS_SWAPPING_AXES
                ):
                    width, height = height, width
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return ImageProbe(failure=ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED)
    except (UnidentifiedImageError, OSError, ValueError):
        return ImageProbe(failure=ImageDecodeFailure.UNREADABLE)
    if width < 1 or height < 1 or not mime_type.startswith("image/"):
        return ImageProbe(failure=ImageDecodeFailure.UNREADABLE)
    # PIL 的全局阈值可被进程内其它代码改写；策略值在这里再判一次，结论只依赖策略。
    if width * height > MAX_SOURCE_PIXELS:
        return ImageProbe(failure=ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED)
    return ImageProbe(width=int(width), height=int(height), mime_type=mime_type)


def probe_image_bytes(data: bytes) -> ImageProbe:
    if not data:
        return ImageProbe(failure=ImageDecodeFailure.EMPTY)
    return _probe(io.BytesIO(data))


def probe_image_path(path: str | Path) -> ImageProbe:
    candidate = Path(path)
    if not candidate.is_file():
        return ImageProbe(failure=ImageDecodeFailure.UNREADABLE)
    return _probe(candidate)


def oriented_raster(image):
    """Return the raster rotated into the orientation this boundary reports.

    Re-encoding drops EXIF, so any derived body must be rotated before encoding
    or it would contradict the geometry ``probe_image_*`` reported for its source.
    Call this before ``convert``: ``convert`` returns a new image whose EXIF the
    transpose can no longer read.
    """

    return ImageOps.exif_transpose(image) or image


def draft_to_display_width(image, *, probe: ImageProbe, target_width: int) -> None:
    """在解码前把 JPEG 请求到「不小于目标交付宽度」的最小 DCT 缩放档。

    全景接片动辄数亿像素，整幅解压再缩放会让派生一张 1920 宽的交付体占用数 GiB
    内存。libjpeg 能在解码时按 1/2、1/4、1/8 直接出小栅格，``Image.draft`` 保证结果
    不小于请求尺寸，之后的 LANCZOS 只做最多 2× 的收尾缩放，画质与整幅路径一致。
    非 JPEG 编码没有这条捷径，``draft`` 是空操作，仍走整幅解码（由
    ``MAX_SOURCE_PIXELS`` 兜底）。请求尺寸按存储栅格给出：EXIF 旋转让显示几何与存储
    几何互换，而 ``draft`` 只认存储几何。必须在任何会触发 ``load`` 的调用之前调用。
    """

    if target_width >= probe.width:
        return
    scale = target_width / probe.width
    stored_width, stored_height = image.size
    image.draft(
        image.mode,
        (
            max(1, math.ceil(stored_width * scale)),
            max(1, math.ceil(stored_height * scale)),
        ),
    )


__all__ = [
    "MAX_SOURCE_PIXELS",
    "ImageDecodeFailure",
    "ImageProbe",
    "draft_to_display_width",
    "oriented_raster",
    "pil_available",
    "probe_image_bytes",
    "probe_image_path",
]
