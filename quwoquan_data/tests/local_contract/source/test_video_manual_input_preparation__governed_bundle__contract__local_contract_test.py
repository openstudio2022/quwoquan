from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import pytest
from content.execution.handler import register_parser
from content.source.professional_safety_evidence import file_sha256
from content.source.professional_video_manual_input import (
    DUPLICATE_OUTPUT,
    SOURCE_SHA_DRIFT,
    VideoManualInputPreparationError,
    prepare_video_manual_input,
)
from core.io import read_json


def _write_motion_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10.0,
        (320, 180),
    )
    if not writer.isOpened():
        raise RuntimeError("test MP4 writer did not open")
    try:
        for index in range(100):
            frame = np.full((180, 320, 3), 24, dtype=np.uint8)
            left = (index * 5) % 250
            cv2.rectangle(
                frame,
                (left, 30),
                (left + 70, 150),
                (32, 220, 240),
                thickness=-1,
            )
            writer.write(frame)
    finally:
        writer.release()
    assert path.stat().st_size > 8_000


def _prepare_args(
    source_root: Path,
    output_root: Path,
    *,
    asset_id: str = "dujiangyan-video-sequence008",
    source_ref: str = "source.mp4",
    source_sha256: str | None = None,
) -> dict[str, object]:
    return {
        "source_root": source_root,
        "source_ref": source_ref,
        "source_sha256": source_sha256 or file_sha256(source_root / "source.mp4"),
        "output_root": output_root,
        "asset_id": asset_id,
        "entity_id": "都江堰",
        "observed_entity_id": "都江堰",
        "source_page_url": "https://commons.wikimedia.org/wiki/File:Panda.webm",
        "start_ms": 1_000,
        "duration_ms": 6_000,
        "prepared_at": "2026-08-10T12:00:00Z",
        "operator_id": "contract-operator",
    }


def test_preparation_writes_one_atomic_replayable_bundle(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source = source_root / "source.mp4"
    _write_motion_video(source)
    output_root = tmp_path / "output"

    receipt, receipt_path = prepare_video_manual_input(
        **_prepare_args(source_root, output_root)
    )

    assert receipt_path == output_root / receipt["bundleRef"] / "receipt.json"
    assert receipt["schema"] == (
        "quwoquan_data.professional_video_manual_input_preparation_receipt"
    )
    assert receipt["sourceSha256"] == file_sha256(source)
    assert receipt["videoSha256"] != receipt["sourceSha256"]
    assert receipt["syntheticFrames"] is False
    assert receipt["mediaProbe"]["motionVideo"] is True
    assert receipt["mediaProbe"]["premiumPlayableEligible"] is True
    assert receipt["mediaProbe"]["hasAudio"] is False
    assert "no frame interpolation or synthetic frames" in receipt["transformation"]
    bundle = receipt_path.parent
    assert sorted(path.name for path in bundle.iterdir()) == [
        "contact-sheet.jpg",
        "receipt.json",
        "safety-evidence-skeleton.json",
        "video.mp4",
    ]
    skeleton = read_json(output_root / receipt["safetyEvidenceSkeletonRef"])
    assert skeleton["status"] == "pending"
    assert skeleton["entityId"] == skeleton["observedEntityId"] == "都江堰"
    assert skeleton["sourceContentSha256"] == receipt["sourceSha256"]
    assert skeleton["fileSha256"] == receipt["videoSha256"]
    original_receipt_bytes = receipt_path.read_bytes()

    replay, replay_path = prepare_video_manual_input(
        **{
            **_prepare_args(source_root, output_root),
            "prepared_at": "2026-08-10T13:00:00Z",
            "operator_id": "second-operator",
        }
    )
    assert replay == receipt
    assert replay_path == receipt_path
    assert receipt_path.read_bytes() == original_receipt_bytes
    assert len(list((output_root / "manual-inputs").iterdir())) == 1


def test_source_ref_sha_and_symlink_fail_before_output(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source = source_root / "source.mp4"
    _write_motion_video(source)

    for source_ref in ("../source.mp4", str(source.resolve())):
        output_root = tmp_path / f"output-{len(source_ref)}"
        with pytest.raises(
            VideoManualInputPreparationError,
            match="safe relative reference",
        ):
            prepare_video_manual_input(
                **_prepare_args(source_root, output_root, source_ref=source_ref)
            )
        assert not output_root.exists()

    sha_output = tmp_path / "output-sha"
    with pytest.raises(VideoManualInputPreparationError) as failure:
        prepare_video_manual_input(
            **_prepare_args(
                source_root,
                sha_output,
                source_sha256="sha256:" + "0" * 64,
            )
        )
    assert failure.value.code == SOURCE_SHA_DRIFT
    assert not sha_output.exists()

    linked = source_root / "linked.mp4"
    linked.symlink_to(source.name)
    link_output = tmp_path / "output-link"
    with pytest.raises(
        VideoManualInputPreparationError,
        match="must not traverse a symlink",
    ):
        prepare_video_manual_input(
            **_prepare_args(source_root, link_output, source_ref="linked.mp4")
        )
    assert not link_output.exists()


def test_cross_plan_exact_output_is_rejected_without_partial_bundle(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _write_motion_video(source_root / "source.mp4")
    output_root = tmp_path / "output"
    first, _ = prepare_video_manual_input(
        **_prepare_args(source_root, output_root, asset_id="asset-a")
    )

    with pytest.raises(VideoManualInputPreparationError) as failure:
        prepare_video_manual_input(
            **_prepare_args(source_root, output_root, asset_id="asset-b")
        )
    assert failure.value.code == DUPLICATE_OUTPUT
    bundles = list((output_root / "manual-inputs").iterdir())
    assert len(bundles) == 1
    assert bundles[0].name == first["planDigest"].removeprefix("sha256:")
    assert not list(output_root.glob(".video-manual-input-*"))


def test_task_parser_exposes_only_explicit_governed_inputs() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_parser(subparsers)
    parsed = parser.parse_args(
        [
            "task",
            "prepare-video-manual-input",
            "--source-root",
            "/source",
            "--source-ref",
            "cas/input.mp4",
            "--source-sha256",
            "sha256:" + "a" * 64,
            "--output-root",
            "/output",
            "--asset-id",
            "asset-a",
            "--entity-id",
            "都江堰",
            "--observed-entity-id",
            "都江堰",
            "--source-page-url",
            "https://example.com/source",
            "--start-ms",
            "5000",
            "--duration-ms",
            "10500",
            "--prepared-at",
            "2026-08-10T12:00:00Z",
            "--operator-id",
            "operator-a",
        ]
    )
    assert parsed.task_command == "prepare-video-manual-input"
    assert parsed.source_ref == "cas/input.mp4"
    assert parsed.start_ms == 5_000
    assert parsed.duration_ms == 10_500
