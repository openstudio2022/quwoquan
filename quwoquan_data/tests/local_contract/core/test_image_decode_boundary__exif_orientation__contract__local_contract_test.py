# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t6
"""local_contract：图片边界报告的像素几何必须是交付端呈现的几何。

现场缺陷：一张 9472×2336 的横向全景图（Commons 原图，EXIF Orientation=6）被
`assets/index.json` 记成 2336×9472。`Image.size` 只报存储栅格，读侧不看 EXIF 就会把
横图记成极端竖图，此后相关性判定、封面候选、有效交付宽度与字节预算全部按转置后的几何
得出结论。重编码会丢弃 EXIF，因此派生体必须先旋转再编码，否则派生体几何与它自己声明的
源几何互相矛盾。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.image_decode import probe_image_bytes, probe_image_path  # noqa: E402
from core.image_variants import (  # noqa: E402
    build_local_variants,
    derive_budget_compliant_variant,
)

# EXIF Orientation=6 表示「顺时针旋转 90° 后为正」，即存储栅格宽高与显示宽高互换。
_ORIENTATION_ROTATE_90_CW = 6
_ORIENTATION_TAG = 274


def _landscape_panorama_stored_rotated(width: int, height: int) -> bytes:
    """构造一张显示为 width×height 横向全景、但栅格按竖向存储的真实 JPEG。"""

    raster = Image.new("RGB", (height, width), color=(12, 90, 140))
    exif = raster.getexif()
    exif[_ORIENTATION_TAG] = _ORIENTATION_ROTATE_90_CW
    buffer = io.BytesIO()
    raster.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_probe_reports_display_geometry_not_stored_raster_geometry(tmp_path: Path):
    payload = _landscape_panorama_stored_rotated(2400, 600)

    # 前提成立：这张图的栅格确实是竖的，转置只能由 EXIF 判出而不是由尺寸猜出。
    with Image.open(io.BytesIO(payload)) as raw:
        assert raw.size == (600, 2400)
        assert raw.getexif().get(_ORIENTATION_TAG) == _ORIENTATION_ROTATE_90_CW

    probe = probe_image_bytes(payload)
    assert probe.succeeded
    assert (probe.width, probe.height) == (2400, 600)

    # 路径入口与字节入口是同一个边界，不能只有一侧看 EXIF。
    on_disk = tmp_path / "panorama.jpg"
    on_disk.write_bytes(payload)
    assert (probe_image_path(on_disk).width, probe_image_path(on_disk).height) == (
        2400,
        600,
    )


def test_probe_leaves_geometry_alone_when_exif_declares_no_rotation():
    """无旋转声明时不得擅自互换宽高：转置只跟随显式声明。"""

    buffer = io.BytesIO()
    Image.new("RGB", (2400, 600), color=(12, 90, 140)).save(buffer, format="JPEG")
    probe = probe_image_bytes(buffer.getvalue())
    assert (probe.width, probe.height) == (2400, 600)


def test_derived_bodies_are_rotated_before_encoding():
    """重编码丢 EXIF，因此派生体的几何必须与边界报告的源几何同向。"""

    payload = _landscape_panorama_stored_rotated(2400, 600)

    for variant in build_local_variants(payload, base_name="panorama"):
        assert variant["width"] > variant["height"]
        with Image.open(io.BytesIO(variant["bytes"])) as encoded:
            assert encoded.size == (variant["width"], variant["height"])

    derived = derive_budget_compliant_variant(payload, budget_bytes=64 * 1024)
    assert derived is not None
    assert (derived["sourceWidth"], derived["sourceHeight"]) == (2400, 600)
    assert derived["width"] > derived["height"]
    with Image.open(io.BytesIO(derived["bytes"])) as encoded:
        assert encoded.size == (derived["width"], derived["height"])
