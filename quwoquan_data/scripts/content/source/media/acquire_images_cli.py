"""Public CLI for explicit professional-image acquisition into CAS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.paths import SOURCE_ACQUISITION_ROOT

ACQUISITION_ROOT = SOURCE_ACQUISITION_ROOT / "image"


def handle_acquire_images(args: argparse.Namespace) -> None:
    from content.source.professional_image_acquisition import acquire_professional_images
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
        help="按显式 manifest 取得专业研究图片并写 CAS",
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manual-root")
    parser.add_argument("--output-root")
    parser.set_defaults(handler=handle_acquire_images)




__all__ = ["handle_acquire_images", "register_acquire_images_parser"]
