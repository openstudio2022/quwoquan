"""Public Data CLI binding for anonymous image-discovery probes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.source.professional_image_discovery_probe import (
    PROBE_ROOT,
    ProfessionalImageDiscoveryProbeError,
    probe_professional_image_discovery_plan,
)
from core.runtime_policy import active_runtime_policy


def handle_probe_images(args: argparse.Namespace) -> None:
    try:
        receipt, path = probe_professional_image_discovery_plan(
            Path(args.plan),
            output_root=Path(args.output_root),
            timeout_seconds=active_runtime_policy().direct_fetch_timeout_seconds,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, ProfessionalImageDiscoveryProbeError) as exc:
        raise SystemExit(f"[task probe-images] GATE_BLOCK {exc}") from exc
    print(json.dumps({**receipt, "receiptRef": path.as_posix()}, ensure_ascii=False, indent=2))
    if not receipt["overallReady"]:
        raise SystemExit(2)


def register_probe_images_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "probe-images",
        help="匿名探测专业图片发现入口；不登录、不下载作品、不绕过访问控制",
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-root", default=str(PROBE_ROOT))
    parser.set_defaults(handler=handle_probe_images)


__all__ = ["handle_probe_images", "register_probe_images_parser"]
