#!/usr/bin/env python3
"""Verify the Flutter welcome petal bloom from extracted device-video frames.

Frames must be chronological PNG images cropped to the flower area. The probe
segments the eight canonical petal colors, measures oriented bounds and
centroid motion, and rejects anisotropic squash or the wrong stagger order.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from PIL import Image


PETAL_COLORS: tuple[tuple[int, int, int], ...] = (
    (0xFB, 0x92, 0x3C),
    (0xFD, 0xE0, 0x47),
    (0xA3, 0xE6, 0x35),
    (0x34, 0xD3, 0x99),
    (0x22, 0xD3, 0xEE),
    (0x38, 0xBD, 0xF8),
    (0xA7, 0x8B, 0xFA),
    (0xFB, 0x71, 0x85),
)
GATHERING_ORDER = (7, 6, 5, 4, 3, 2, 1, 0)
BLOOMING_ORDER = (0, 1, 2, 3, 4, 5, 6, 7)
EXPECTED_ASPECT_RATIO = 52 / 94


@dataclass(frozen=True)
class PetalObservation:
    petal_index: int
    pixel_count: int
    centroid_x: float
    centroid_y: float
    center_radius: float
    oriented_minor: float
    oriented_major: float
    aspect_ratio: float
    angle_degrees: float
    frame_displacement: float | None


@dataclass(frozen=True)
class FrameObservation:
    path: str
    center_x: float
    center_y: float
    mean_radius: float
    petals: tuple[PetalObservation, ...]


def _hue_distance(first: float, second: float) -> float:
    delta = abs(first - second)
    return min(delta, 1 - delta)


def _classify_pixel(rgb: tuple[int, int, int]) -> int | None:
    r, g, b = rgb
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if saturation < 0.32 or value < 0.32:
        return None

    best_index: int | None = None
    best_score = float("inf")
    for index, target in enumerate(PETAL_COLORS):
        target_hue, _, _ = colorsys.rgb_to_hsv(
            target[0] / 255,
            target[1] / 255,
            target[2] / 255,
        )
        hue_delta = _hue_distance(hue, target_hue)
        hue_limit = 8 / 360 if index == 5 else 16 / 360
        if hue_delta > hue_limit:
            continue
        rgb_distance = math.sqrt(
            (r - target[0]) ** 2
            + (g - target[1]) ** 2
            + (b - target[2]) ** 2
        )
        if rgb_distance > 145:
            continue
        score = hue_delta * 720 + rgb_distance / 255
        if score < best_score:
            best_index = index
            best_score = score
    return best_index


def _oriented_bounds(
    points: list[tuple[float, float]],
    centroid: tuple[float, float],
) -> tuple[float, float, float]:
    cx, cy = centroid
    xx = yy = xy = 0.0
    for x, y in points:
        dx = x - cx
        dy = y - cy
        xx += dx * dx
        yy += dy * dy
        xy += dx * dy
    count = max(len(points), 1)
    xx /= count
    yy /= count
    xy /= count
    angle = 0.5 * math.atan2(2 * xy, xx - yy)
    major_axis = (math.cos(angle), math.sin(angle))
    minor_axis = (-major_axis[1], major_axis[0])
    major_values = [
        (x - cx) * major_axis[0] + (y - cy) * major_axis[1]
        for x, y in points
    ]
    minor_values = [
        (x - cx) * minor_axis[0] + (y - cy) * minor_axis[1]
        for x, y in points
    ]
    major = max(major_values) - min(major_values) + 1
    minor = max(minor_values) - min(minor_values) + 1
    if minor > major:
        minor, major = major, minor
        angle += math.pi / 2
    return minor, major, math.degrees(angle) % 180


def _flower_center(
    centroids: list[tuple[float, float]],
) -> tuple[float, float]:
    opposing_midpoints = [
        (
            (centroids[index][0] + centroids[index + 4][0]) / 2,
            (centroids[index][1] + centroids[index + 4][1]) / 2,
        )
        for index in range(4)
    ]
    return (
        sum(point[0] for point in opposing_midpoints) / 4,
        sum(point[1] for point in opposing_midpoints) / 4,
    )


def analyze_frame(
    path: Path,
    *,
    previous: FrameObservation | None = None,
    minimum_pixels: int = 24,
) -> FrameObservation:
    image = Image.open(path).convert("RGBA")
    points: list[list[tuple[float, float]]] = [[] for _ in PETAL_COLORS]
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, alpha = image.getpixel((x, y))
            if alpha < 96:
                continue
            petal_index = _classify_pixel((r, g, b))
            if petal_index is not None:
                points[petal_index].append((float(x), float(y)))

    missing = [index for index, values in enumerate(points) if len(values) < minimum_pixels]
    if missing:
        raise ValueError(f"{path}: missing petal pixels for indexes {missing}")

    centroids = [
        (
            sum(point[0] for point in values) / len(values),
            sum(point[1] for point in values) / len(values),
        )
        for values in points
    ]
    center_x, center_y = _flower_center(centroids)
    petals: list[PetalObservation] = []
    for index, values in enumerate(points):
        centroid = centroids[index]
        minor, major, angle = _oriented_bounds(values, centroid)
        previous_centroid = None
        if previous is not None:
            previous_petal = previous.petals[index]
            previous_centroid = (
                previous_petal.centroid_x,
                previous_petal.centroid_y,
            )
        displacement = (
            None
            if previous_centroid is None
            else math.dist(centroid, previous_centroid)
        )
        petals.append(
            PetalObservation(
                petal_index=index,
                pixel_count=len(values),
                centroid_x=round(centroid[0], 4),
                centroid_y=round(centroid[1], 4),
                center_radius=round(math.dist(centroid, (center_x, center_y)), 4),
                oriented_minor=round(minor, 4),
                oriented_major=round(major, 4),
                aspect_ratio=round(minor / major, 6),
                angle_degrees=round(angle, 4),
                frame_displacement=(
                    None if displacement is None else round(displacement, 4)
                ),
            )
        )
    return FrameObservation(
        path=str(path),
        center_x=round(center_x, 4),
        center_y=round(center_y, 4),
        mean_radius=round(
            sum(petal.center_radius for petal in petals) / len(petals),
            4,
        ),
        petals=tuple(petals),
    )


def _crossing_frames(
    frames: list[FrameObservation],
    *,
    start: int,
    end: int,
    rising: bool,
) -> list[int | None]:
    crossings: list[int | None] = []
    for petal_index in range(len(PETAL_COLORS)):
        values = [
            frame.petals[petal_index].center_radius for frame in frames
        ]
        midpoint = (min(values) + max(values)) / 2
        crossing = next(
            (
                index
                for index in range(start, end + 1)
                if (
                    values[index] >= midpoint
                    if rising
                    else values[index] <= midpoint
                )
            ),
            None,
        )
        crossings.append(crossing)
    return crossings


def _ordered_crossings(
    crossings: list[int | None],
    order: Iterable[int],
) -> bool:
    ordered = [crossings[index] for index in order]
    return all(value is not None for value in ordered) and all(
        int(ordered[index]) <= int(ordered[index + 1])
        for index in range(len(ordered) - 1)
    )


def analyze_sequence(
    paths: list[Path],
    *,
    aspect_drift_limit: float = 0.25,
    monotonic_tolerance_px: float = 3.0,
    minimum_wave_spread: float = 0.15,
) -> dict[str, Any]:
    if len(paths) < 6:
        raise ValueError("At least six chronological motion frames are required")
    frames: list[FrameObservation] = []
    for path in paths:
        frames.append(
            analyze_frame(path, previous=frames[-1] if frames else None)
        )

    bud_index = min(range(len(frames)), key=lambda index: frames[index].mean_radius)
    if bud_index == 0 or bud_index == len(frames) - 1:
        raise ValueError("Sequence must include full-open, bud, and final-open frames")

    gather_crossings = _crossing_frames(
        frames,
        start=0,
        end=bud_index,
        rising=False,
    )
    bloom_crossings = _crossing_frames(
        frames,
        start=bud_index,
        end=len(frames) - 1,
        rising=True,
    )
    gather_order_valid = _ordered_crossings(gather_crossings, GATHERING_ORDER)
    bloom_order_valid = _ordered_crossings(bloom_crossings, BLOOMING_ORDER)

    monotonic_violations: list[dict[str, Any]] = []
    for petal_index in range(len(PETAL_COLORS)):
        radii = [frame.petals[petal_index].center_radius for frame in frames]
        for index in range(0, bud_index):
            if radii[index + 1] > radii[index] + monotonic_tolerance_px:
                monotonic_violations.append(
                    {"petalIndex": petal_index, "phase": "gathering", "frame": index}
                )
        for index in range(bud_index, len(frames) - 1):
            if radii[index + 1] < radii[index] - monotonic_tolerance_px:
                monotonic_violations.append(
                    {"petalIndex": petal_index, "phase": "blooming", "frame": index}
                )

    final_aspects = [petal.aspect_ratio for petal in frames[-1].petals]
    frame_median_aspect_drifts = [
        median(
            abs(frame.petals[index].aspect_ratio - final_aspects[index])
            / max(final_aspects[index], 1e-9)
            for index in range(len(PETAL_COLORS))
        )
        for frame in frames
    ]
    max_median_aspect_drift = max(frame_median_aspect_drifts)
    bloom_mid_index = bud_index + max(1, (len(frames) - 1 - bud_index) // 2)
    final_radii = [
        frames[-1].petals[index].center_radius for index in range(len(PETAL_COLORS))
    ]
    mid_factors = [
        frames[bloom_mid_index].petals[index].center_radius / max(final_radii[index], 1)
        for index in range(len(PETAL_COLORS))
    ]
    wave_spread = max(mid_factors) - min(mid_factors)

    passed = (
        gather_order_valid
        and bloom_order_valid
        and not monotonic_violations
        and max_median_aspect_drift <= aspect_drift_limit
        and wave_spread >= minimum_wave_spread
    )
    return {
        "schema": "welcome-motion-frames-report",
        "motionSpecVersion": "petal_bloom_v2",
        "passed": passed,
        "frameCount": len(frames),
        "budFrameIndex": bud_index,
        "gatheringOrder": list(GATHERING_ORDER),
        "gatheringCrossingFrames": gather_crossings,
        "gatheringOrderValid": gather_order_valid,
        "bloomingOrder": list(BLOOMING_ORDER),
        "bloomingCrossingFrames": bloom_crossings,
        "bloomingOrderValid": bloom_order_valid,
        "expectedPathAspectRatio": round(EXPECTED_ASPECT_RATIO, 6),
        "frameMedianAspectRatioDrifts": [
            round(value, 6) for value in frame_median_aspect_drifts
        ],
        "maxMedianAspectRatioDrift": round(max_median_aspect_drift, 6),
        "aspectDriftLimit": aspect_drift_limit,
        "bloomMidWaveSpread": round(wave_spread, 6),
        "minimumWaveSpread": minimum_wave_spread,
        "monotonicViolations": monotonic_violations,
        "frames": [asdict(frame) for frame in frames],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--aspect-drift-limit", type=float, default=0.25)
    parser.add_argument("--monotonic-tolerance-px", type=float, default=3.0)
    parser.add_argument("--minimum-wave-spread", type=float, default=0.15)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = analyze_sequence(
        args.frames,
        aspect_drift_limit=args.aspect_drift_limit,
        monotonic_tolerance_px=args.monotonic_tolerance_px,
        minimum_wave_spread=args.minimum_wave_spread,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
