#!/usr/bin/env python3
"""验证指定环境 published-release 视频 canary 的完整公共交付面。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.release_video_delivery import (
    DELIVERY_EVIDENCE_SCHEMA,
    ReleaseVideoDeliveryError,
    build_release_video_url,
    load_release_video_binding,
    probe_duration_ms,
    probe_first_frame,
    probe_https_video,
    resolve_readiness_path,
    validate_delivery,
)


FORBIDDEN_RELEASE_CANARY_TOKENS = frozenset(
    {"fixture", "mock", "seed", "test_fixtures", "test-fixture"}
)


def _canonical_release_video_slice_key(raw: str) -> str:
    key = raw.strip().lstrip("/")
    segments = key.split("/")
    if (
        len(segments) < 4
        or segments[0] != "media"
        or segments[1] != "video"
        or segments[2] != "s"
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise ValueError("release playback canary must be a canonical media/video/s/ public slice key")
    lower_key = key.lower()
    if any(token in lower_key for token in FORBIDDEN_RELEASE_CANARY_TOKENS):
        raise ValueError("release playback canary must not reference fixture/mock/seed media")
    return key


def _required_secret_env(name: str) -> None:
    if not os.environ.get(name, "").strip():
        raise ValueError(
            f"required authentication prerequisite is missing: {name}; "
            "do not start prod-hosted Patrol without a controlled test session"
        )


def _required_rollout_stage(name: str) -> str:
    stage = os.environ.get(name, "").strip()
    if stage != "gray-initial":
        raise ValueError(
            f"required prod rollout stage is gray-initial, got {stage or '<missing>'} from {name}"
        )
    return stage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="prod-hosted")
    parser.add_argument(
        "--release-readiness",
        default=os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "").strip(),
        help=(
            "Canonical Data release-readiness.json below QWQ_OUTPUT_ROOT; "
            "defaults to DATA_RELEASE_READINESS_RECEIPT."
        ),
    )
    parser.add_argument(
        "--video-work-id",
        default="",
        help=(
            "Optional release-bound premium video post/work id. If omitted, the "
            "Data receipt must expose exactly one candidate."
        ),
    )
    parser.add_argument(
        "--video-asset-id",
        default=os.environ.get("VIDEO_PLAYBACK_CANARY_ASSET_ID", "").strip(),
    )
    parser.add_argument("--auth-token-env", default="PROD_TEST_AUTH_TOKEN")
    parser.add_argument("--rollout-stage-env", default="PROD_ROLLOUT_STAGE")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        topology = load_environment_topology()
        target = get_target(topology, args.target)
        if args.target == "prod-hosted":
            _required_secret_env(args.auth_token_env)
            stage = _required_rollout_stage(args.rollout_stage_env)
        else:
            stage = "local"
        playback_canary = target.get("playbackCanary")
        if not isinstance(playback_canary, dict) or playback_canary.get(
            "source"
        ) != "published-release":
            raise ValueError(
                "target playbackCanary.source must be published-release"
            )
        environment = str(target.get("env") or "").strip()
        if environment not in {"alpha", "beta", "gamma", "prod"}:
            raise ValueError("target environment is invalid")
        work_id_env = str(playback_canary.get("workIdEnv") or "").strip()
        requested_work_id = str(args.video_work_id or "").strip() or os.environ.get(
            work_id_env or "VIDEO_PLAYBACK_CANARY_WORK_ID",
            "",
        ).strip()
        readiness_path = resolve_readiness_path(args.release_readiness)
        binding = load_release_video_binding(
            readiness_path,
            expected_environment=environment,
            requested_work_id=requested_work_id,
            requested_asset_id=args.video_asset_id,
        )
        key = _canonical_release_video_slice_key(binding["publicSliceKey"])
        slice_key_env = str(playback_canary.get("publicSliceKeyEnv") or "").strip()
        configured_slice_key = os.environ.get(slice_key_env, "").strip()
        if configured_slice_key and _canonical_release_video_slice_key(
            configured_slice_key
        ) != key:
            raise ValueError(
                "configured publicSliceKey drifts from the canonical Data receipt"
            )
        base = str((target.get("publicBases") or {}).get("mediaVideo") or "").rstrip("/")
        parsed_base = urlsplit(base)
        if parsed_base.scheme != "https" or not parsed_base.netloc:
            raise ValueError("mediaVideo authority must be an HTTPS public base")
        url = build_release_video_url(target.get("publicBases") or {}, binding)
        delivery = probe_https_video(
            url,
            expected_bytes=int(binding["expectedBytes"]),
            timeout_seconds=max(1, args.timeout_seconds),
        )
        validate_delivery(
            delivery,
            expected_mime_type=str(binding["expectedMimeType"]),
            expected_bytes=int(binding["expectedBytes"]),
            expected_hash=str(binding["expectedHash"]),
            expected_public_slice_key=key,
        )
        duration_ms = probe_duration_ms(
            url,
            timeout_seconds=max(1, args.timeout_seconds),
        )
        first_frame_decoded = probe_first_frame(
            url,
            timeout_seconds=max(1, args.timeout_seconds),
        )
        if first_frame_decoded is not True:
            raise ValueError("release video decoded first-frame probe did not pass")
    except (ReleaseVideoDeliveryError, ValueError) as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    except (OSError, urllib.error.URLError) as exc:
        print(f"GATE_BLOCK: release video TLS/origin probe failed: {exc}")
        return 2

    report = {
        "schema": DELIVERY_EVIDENCE_SCHEMA,
        "status": "passed",
        "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": environment,
        "target": args.target,
        "rolloutStage": stage,
        "release": {
            "releaseId": binding["releaseId"],
            "sourceOwner": binding["sourceOwner"],
            "manifestDigest": binding["manifestDigest"],
            "mediaManifestDigest": binding["mediaManifestDigest"],
            "importRunId": binding["importRunId"],
            "verifyRunId": binding["verifyRunId"],
            "readinessReceiptRef": binding["readinessReceiptRef"],
        },
        "video": {
            "workId": binding["workId"],
            "postId": binding["postId"],
            "postRef": binding["postRef"],
            "assetId": binding["assetId"],
            "assetVersion": binding["assetVersion"],
            "publicSliceKey": key,
            "publicUrl": url,
            "expectedMimeType": binding["expectedMimeType"],
            "expectedBytes": binding["expectedBytes"],
            "expectedHash": binding["expectedHash"],
        },
        "delivery": delivery,
        "playback": {
            "durationMs": duration_ms,
            "firstFrameDecoded": first_frame_decoded,
        },
        # Kept as typed aliases for the runtime-media T4 archive reader.
        "publicSliceKey": key,
        "videoAuthority": base,
        "rangeStatus": delivery["rangeStatus"],
        "contentType": delivery["mimeType"],
    }
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
