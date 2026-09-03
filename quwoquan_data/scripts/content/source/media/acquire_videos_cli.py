"""Public CLI for explicit professional-video acquisition into CAS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.paths import SOURCE_ACQUISITION_ROOT

ACQUISITION_ROOT = SOURCE_ACQUISITION_ROOT / "video"


def handle_acquire_videos(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or ACQUISITION_ROOT).expanduser().resolve()
    manual_root = (
        Path(args.manual_root).expanduser().resolve()
        if str(args.manual_root or "").strip()
        else None
    )
    try:
        from content.source.professional_video_acquisition import acquire_professional_videos

        receipt, path = acquire_professional_videos(
            Path(args.manifest).expanduser().resolve(),
            manual_root=manual_root,
            output_root=output_root,
        )
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "[task acquire-videos] GATE_BLOCK "
            f"DATA.SOURCE.VIDEO_PROBE_DEPENDENCY_MISSING dependency={exc.name or 'unknown'}"
        ) from exc
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task acquire-videos] GATE_BLOCK {exc}") from exc
    print(json.dumps(
        {**receipt, "receiptRef": path.relative_to(output_root).as_posix()},
        ensure_ascii=False,
        indent=2,
    ))


def register_acquire_videos_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "acquire-videos",
        help="按显式 manifest 取得专业研究视频并写 CAS",
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manual-root")
    parser.add_argument("--output-root")
    parser.set_defaults(handler=handle_acquire_videos)


__all__ = ["handle_acquire_videos", "register_acquire_videos_parser"]
