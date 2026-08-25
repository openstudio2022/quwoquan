"""截图分析：前景占比、品牌蓝底、系统 splash 图标与异常帧判定。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any


def _pillow() -> tuple[Any, Any]:
    """按需取 Pillow。

    本包的 ``__init__`` 全量 re-export，顶层导入 Pillow 会让每个只需要日志解析的
    调用方（例如 launcher supervisor）都硬依赖它，在未安装的环境整体起不来。
    只有真机首帧截图分析需要 Pillow，因此推迟到实际使用点。
    """
    try:
        from PIL import Image, ImageStat
    except ImportError as error:
        raise RuntimeError(
            "DEVICE.STARTUP_FIRST_FRAME.pillow_absent: "
            "截图分析需要 quwoquan_data/requirements.txt 声明的 Pillow"
        ) from error
    return Image, ImageStat


@dataclass(frozen=True)
class ScreenshotAnalysis:
    path: str
    offset_ms: int | None
    foreground_ratio: float
    stddev_avg: float
    median_rgb: tuple[int, int, int]
    plain_background: bool
    blue_background: bool
    branded_or_content_visible: bool
    system_splash_icon: bool = False

    @property
    def brand_transition_visible(self) -> bool:
        return self.blue_background or self.branded_or_content_visible

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "offsetMs": self.offset_ms,
            "foregroundRatio": round(self.foreground_ratio, 5),
            "stddevAvg": round(self.stddev_avg, 3),
            "medianRgb": list(self.median_rgb),
            "plainBackground": self.plain_background,
            "blueBackground": self.blue_background,
            "brandedOrContentVisible": self.branded_or_content_visible,
            "systemSplashIcon": self.system_splash_icon,
            "brandTransitionVisible": self.brand_transition_visible,
        }


def analyze_screenshot(path: Path, offset_ms: int | None = None) -> ScreenshotAnalysis:
    pil_image, pil_image_stat = _pillow()
    image = pil_image.open(path).convert("RGB")
    width, height = image.size
    crop = image.crop(
        (
            round(width * 0.14),
            round(height * 0.14),
            round(width * 0.86),
            round(height * 0.86),
        )
    )
    get_pixels = getattr(crop, "get_flattened_data", None)
    pixels = list(get_pixels() if get_pixels is not None else crop.getdata())
    median_rgb = tuple(int(median(channel)) for channel in zip(*pixels))
    foreground = 0
    for r, g, b in pixels:
        distance = (
            (r - median_rgb[0]) ** 2
            + (g - median_rgb[1]) ** 2
            + (b - median_rgb[2]) ** 2
        ) ** 0.5
        if distance > 34:
            foreground += 1
    foreground_ratio = foreground / max(len(pixels), 1)
    stddev = pil_image_stat.Stat(crop).stddev
    stddev_avg = sum(stddev) / max(len(stddev), 1)
    near_white_background = min(median_rgb) >= 250
    brand_blue_base = (
        median_rgb[0] <= 40
        and 90 <= median_rgb[1] <= 170
        and median_rgb[2] >= 210
    )
    # Android 12 renders a large, centered adaptive app icon over its blue
    # system splash. It is not the native flower composition, even though its
    # high foreground ratio could otherwise look like branded content.
    system_splash_icon = brand_blue_base and foreground_ratio >= 0.25
    branded_or_content_visible = not system_splash_icon and (
        foreground_ratio >= 0.18
        or (
            stddev_avg >= 14.0
            and foreground_ratio >= 0.08
            and not near_white_background
        )
    )
    blue_background = (
        not branded_or_content_visible and brand_blue_base
    )
    brand_transition_visible = blue_background or branded_or_content_visible
    return ScreenshotAnalysis(
        path=str(path),
        offset_ms=offset_ms,
        foreground_ratio=foreground_ratio,
        stddev_avg=stddev_avg,
        median_rgb=median_rgb,
        plain_background=not brand_transition_visible,
        blue_background=blue_background,
        branded_or_content_visible=branded_or_content_visible,
        system_splash_icon=system_splash_icon,
    )


def resolve_first_visible_ms(
    analyses: list[ScreenshotAnalysis],
    budget_ms: int,
    *,
    require_branded: bool,
) -> int | None:
    predicate = (
        (lambda item: item.branded_or_content_visible)
        if require_branded
        else (lambda item: item.brand_transition_visible)
    )
    return next(
        (
            item.offset_ms
            for item in analyses
            if predicate(item)
            and item.offset_ms is not None
            and item.offset_ms <= budget_ms
        ),
        None,
    )


def resolve_android_first_visible_ms(
    analyses: list[ScreenshotAnalysis],
    *,
    renderer_first_frame_ms: int | None,
    require_branded: bool,
) -> int | None:
    """Combine renderer timing with a later screenshot brand witness.

    `adb exec-out screencap` can block an emulator compositor for longer than a
    sampling interval. Once a screenshot has observed the branded welcome,
    the renderer's first-frame signal is the more accurate visible timestamp;
    it prevents the probe itself from manufacturing a missed 2-second sample.
    """
    screenshot_first = resolve_first_visible_ms(
        analyses,
        budget_ms=10**9,
        require_branded=require_branded,
    )
    if screenshot_first is None:
        return None
    if renderer_first_frame_ms is None:
        return screenshot_first
    return min(screenshot_first, renderer_first_frame_ms)


def first_branded_offset_ms(analyses: list[ScreenshotAnalysis]) -> int | None:
    return next(
        (
            item.offset_ms
            for item in analyses
            if item.branded_or_content_visible and item.offset_ms is not None
        ),
        None,
    )


def detect_prolonged_system_blue(
    analyses: list[ScreenshotAnalysis],
    *,
    transition_budget_ms: int,
) -> bool:
    """Fail when pure Android 12 system blue outlives the OS transition budget.

    The launcher SplashScreen may briefly show brand-blue + app icon. That is
    not the welcome page. Once the transition budget elapses, any still-pure
    blue frame before branded petals/content appears is a probe failure.
    """
    first_branded = first_branded_offset_ms(analyses)
    for item in analyses:
        if item.offset_ms is None:
            continue
        if item.offset_ms < transition_budget_ms:
            continue
        if not item.blue_background or item.branded_or_content_visible:
            continue
        if first_branded is None or item.offset_ms < first_branded:
            return True
    return False


def detect_repeated_splash(
    analyses: list[ScreenshotAnalysis],
    log: str,
) -> bool:
    """Fail when Gate→Main reintroduces a second system/native splash.

    Evidence is either duplicate Gate static-frame logs (handoff restart) or a
    screenshot regression back to pure OS blue after branded content was seen.
    """
    static_frame_hits = log.count("android_gate_static_frame_drawn") + log.count(
        "android_gate_static_frame_draw_timeout"
    )
    if static_frame_hits > 1:
        return True
    saw_branded = False
    for item in sorted(
        analyses,
        key=lambda entry: entry.offset_ms if entry.offset_ms is not None else -1,
    ):
        if item.branded_or_content_visible:
            saw_branded = True
            continue
        if (
            saw_branded
            and item.blue_background
            and not item.branded_or_content_visible
        ):
            return True
    return False


def detect_native_static_petal_mismatch(
    analyses: list[ScreenshotAnalysis],
    *,
    compare_after_ms: int,
    safe_terminal_reached: bool = False,
) -> bool:
    """Fail when late frames stay on plain/OS blue instead of flower brand.

    After the Gate static brand frame and Flutter welcome should be visible,
    a pure-blue or plain background means native static and final petals
    diverged or the branded surface never painted. A normal router Shell may
    legitimately have its own (for example white) background after the welcome
    terminal event, so post-terminal frames are not launch-frame evidence.
    """
    if safe_terminal_reached:
        return False
    late = [
        item
        for item in analyses
        if item.offset_ms is not None and item.offset_ms >= compare_after_ms
    ]
    if not late:
        return False
    return any(
        (item.blue_background or item.plain_background)
        and not item.branded_or_content_visible
        for item in late
    )
