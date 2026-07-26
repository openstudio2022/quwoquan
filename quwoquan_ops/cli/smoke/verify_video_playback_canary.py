#!/usr/bin/env python3
"""验证 prod-hosted gray-initial 视频播放 canary 的前置条件与媒体 TLS 面。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology


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


def _probe_https_video(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"Range": "bytes=0-1"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), str(response.headers.get("Content-Type") or "")
    except urllib.error.HTTPError as exc:
        return int(exc.code), str(exc.headers.get("Content-Type") or "")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="prod-hosted")
    parser.add_argument(
        "--public-slice-key-env",
        default="",
    )
    parser.add_argument("--auth-token-env", default="PROD_TEST_AUTH_TOKEN")
    parser.add_argument("--rollout-stage-env", default="PROD_ROLLOUT_STAGE")
    parser.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.target != "prod-hosted":
            raise ValueError("release playback canary probe only accepts target prod-hosted")
        _required_secret_env(args.auth_token_env)
        stage = _required_rollout_stage(args.rollout_stage_env)
        topology = load_environment_topology()
        target = get_target(topology, args.target)
        playback_canary = target.get("playbackCanary")
        configured_slice_key_env = (
            str(playback_canary.get("publicSliceKeyEnv") or "").strip()
            if isinstance(playback_canary, dict)
            else ""
        )
        slice_key_env = (
            str(args.public_slice_key_env or "").strip()
            or configured_slice_key_env
            or "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY"
        )
        key = _canonical_release_video_slice_key(
            os.environ.get(slice_key_env, "")
        )
        base = str((target.get("publicBases") or {}).get("mediaVideo") or "").rstrip("/")
        parsed_base = urlsplit(base)
        if parsed_base.scheme != "https" or not parsed_base.netloc:
            raise ValueError("prod-hosted mediaVideo authority must be an HTTPS public base")
        url = f"{base}/{key}"
        status, content_type = _probe_https_video(url)
        if status != 206:
            raise ValueError(f"release video Range probe expected HTTP 206, got {status}")
        if not content_type.lower().startswith("video/"):
            raise ValueError(
                f"release video Range probe expected Content-Type video/*, got {content_type or '<empty>'}"
            )
    except ValueError as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    except (OSError, urllib.error.URLError) as exc:
        print(f"GATE_BLOCK: release video TLS/origin probe failed: {exc}")
        return 2

    report = {
        "status": "passed",
        "target": args.target,
        "rolloutStage": stage,
        "publicSliceKey": key,
        "videoAuthority": base,
        "rangeStatus": status,
        "contentType": content_type,
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
