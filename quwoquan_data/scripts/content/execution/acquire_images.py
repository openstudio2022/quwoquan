"""Public Data CLI binding for professional research-image acquisition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.source.professional_image_acquisition import (
    ACQUISITION_ROOT,
    acquire_professional_images,
)


def handle_acquire_images(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or ACQUISITION_ROOT).expanduser().resolve()
    manual_root = (
        Path(args.manual_root).expanduser().resolve()
        if str(args.manual_root or "").strip()
        else None
    )
    try:
        receipt, path = acquire_professional_images(
            Path(args.manifest).expanduser().resolve(),
            manual_root=manual_root,
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task acquire-images] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**receipt, "receiptRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def register_acquire_images_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "acquire-images",
        help="通过公开直链、平台支持 API 或人工文件取得 Pinterest/图虫研究图片",
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manual-root")
    parser.add_argument("--output-root")
    parser.set_defaults(handler=handle_acquire_images)


__all__ = ["handle_acquire_images", "register_acquire_images_parser"]
