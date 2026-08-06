from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from content.execution.scale_promotion_policy import m100_promotion_thresholds
from content.execution.scale_promotion_store import write_scale_promotion_create_once


def test_lane_scale_promotion_is_atomic_for_concurrent_identical_writers(
    tmp_path,
) -> None:
    path = tmp_path / "video-scale-promotions" / "m100.json"
    payload = {
        "schema": "quwoquan_data.video_scale_promotion",
        "receiptDigest": "sha256:" + "a" * 64,
    }

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(
            executor.map(
                lambda _index: write_scale_promotion_create_once(
                    path,
                    payload,
                    label="video scale promotion",
                ),
                range(64),
            )
        )

    assert results == [path] * 64
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert list(path.parent.glob(".*.tmp")) == []


def test_lane_scale_promotion_rejects_conflict_and_uses_carrier_targets(
    tmp_path,
) -> None:
    path = tmp_path / "video-scale-promotions" / "m100.json"
    write_scale_promotion_create_once(
        path,
        {"receiptDigest": "sha256:" + "a" * 64},
        label="video scale promotion",
    )

    with pytest.raises(ValueError, match="receipt collision"):
        write_scale_promotion_create_once(
            path,
            {"receiptDigest": "sha256:" + "b" * 64},
            label="video scale promotion",
        )

    video = m100_promotion_thresholds("video")
    image = m100_promotion_thresholds("image")
    assert (video.quota, video.candidate_minimum) == (50, 90)
    assert (image.quota, image.candidate_minimum) == (100, 180)
