#!/usr/bin/env python3
"""Generate native launch-screen transition assets.

The Flutter welcome screen is the only place that may show the petal mark,
brand title, slogan, and welcome animation. Native launch surfaces only cover
the OS window before Flutter draws its first frame, so they intentionally avoid
mirroring welcome content.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image


APP_DIR = Path(__file__).resolve().parents[2]
ANDROID_RES = APP_DIR / "android" / "app" / "src" / "main" / "res"
IOS_LAUNCH_IMAGESET = (
    APP_DIR
    / "ios"
    / "Runner"
    / "Assets.xcassets"
    / "LaunchImage.imageset"
)
IOS_LAUNCH_TRANSITION_IMAGESET = (
    APP_DIR
    / "ios"
    / "Runner"
    / "Assets.xcassets"
    / "LaunchTransitionBackground.imageset"
)

BRAND_BLUE = (10, 132, 255, 255)
WELCOME_GRADIENT_START = (20, 145, 255, 255)
WELCOME_GRADIENT_END = (21, 84, 209, 255)


def vertical_gradient(size: tuple[int, int]) -> Image.Image:
    width, height = size
    img = Image.new("RGBA", size)
    pixels = img.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        if t < 0.48:
            k = t / 0.48
            c0, c1 = WELCOME_GRADIENT_START, BRAND_BLUE
        else:
            k = (t - 0.48) / 0.52
            c0, c1 = BRAND_BLUE, WELCOME_GRADIENT_END
        color = tuple(round(c0[i] + (c1[i] - c0[i]) * k) for i in range(4))
        for x in range(width):
            pixels[x, y] = color
    return img


def generate_android_splash_icon() -> None:
    densities = {
        "mdpi": 1.0,
        "hdpi": 1.5,
        "xhdpi": 2.0,
        "xxhdpi": 3.0,
        "xxxhdpi": 4.0,
    }
    for density, factor in densities.items():
        out_dir = ANDROID_RES / f"drawable-{density}"
        out_dir.mkdir(parents=True, exist_ok=True)
        size = round(288 * factor)
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        img.save(out_dir / "launch_splash_icon.png")


def generate_ios_launch_overlay() -> None:
    IOS_LAUNCH_IMAGESET.mkdir(parents=True, exist_ok=True)
    sizes = {
        "LaunchImage.png": (393, 852),
        "LaunchImage@2x.png": (786, 1704),
        "LaunchImage@3x.png": (1179, 2556),
    }
    for filename, (width, height) in sizes.items():
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        img.save(IOS_LAUNCH_IMAGESET / filename)


def generate_ios_launch_background() -> None:
    IOS_LAUNCH_TRANSITION_IMAGESET.mkdir(parents=True, exist_ok=True)
    sizes = {
        "LaunchTransitionBackground.png": (393, 852),
        "LaunchTransitionBackground@2x.png": (786, 1704),
        "LaunchTransitionBackground@3x.png": (1179, 2556),
    }
    for filename, size in sizes.items():
        vertical_gradient(size).save(IOS_LAUNCH_TRANSITION_IMAGESET / filename)


def main() -> None:
    generate_android_splash_icon()
    generate_ios_launch_overlay()
    generate_ios_launch_background()


if __name__ == "__main__":
    main()
