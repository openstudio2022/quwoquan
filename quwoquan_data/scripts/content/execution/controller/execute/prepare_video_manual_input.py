"""Public Data CLI binding for governed manual-video preparation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def handle_prepare_video_manual_input(args: argparse.Namespace) -> None:
    try:
        from content.source.professional_video_manual_input import (
            prepare_video_manual_input,
        )

        output_root = Path(args.output_root).expanduser()
        receipt, path = prepare_video_manual_input(
            source_root=Path(args.source_root).expanduser(),
            source_ref=str(args.source_ref),
            source_sha256=str(args.source_sha256),
            output_root=output_root,
            asset_id=str(args.asset_id),
            entity_id=str(args.entity_id),
            observed_entity_id=str(args.observed_entity_id),
            source_page_url=str(args.source_page_url),
            start_ms=int(args.start_ms),
            duration_ms=int(args.duration_ms),
            prepared_at=str(args.prepared_at),
            operator_id=str(args.operator_id),
        )
    except ModuleNotFoundError as exc:
        dependency = str(exc.name or "unknown")
        raise SystemExit(
            "[task prepare-video-manual-input] GATE_BLOCK "
            "DATA.SOURCE.VIDEO_PROBE_DEPENDENCY_MISSING "
            f"dependency={dependency}"
        ) from exc
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[task prepare-video-manual-input] GATE_BLOCK {exc}"
        ) from exc
    resolved_root = output_root.resolve()
    print(
        json.dumps(
            {**receipt, "receiptRef": path.relative_to(resolved_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def register_prepare_video_manual_input_parser(
    sub: argparse._SubParsersAction,
) -> None:
    parser = sub.add_parser(
        "prepare-video-manual-input",
        help="从显式 source ref/SHA 原子准备人工视频、contact sheet 与安全证据骨架",
    )
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--observed-entity-id", required=True)
    parser.add_argument("--source-page-url", required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--duration-ms", type=int, required=True)
    parser.add_argument("--prepared-at", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.set_defaults(handler=handle_prepare_video_manual_input)


__all__ = [
    "handle_prepare_video_manual_input",
    "register_prepare_video_manual_input_parser",
]
