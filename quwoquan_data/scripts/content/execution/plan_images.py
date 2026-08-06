"""Public Data CLI binding for professional image discovery planning."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.source.professional_image_discovery import (
    CATALOG_PATH,
    DISCOVERY_ROOT,
    ProfessionalImageDiscoveryError,
    create_professional_image_discovery_plan,
)


def handle_plan_images(args: argparse.Namespace) -> None:
    try:
        plan, path = create_professional_image_discovery_plan(
            entities=args.entity,
            category=args.category,
            season=args.season,
            style=args.style,
            viewpoint=args.viewpoint,
            popularity=args.popularity,
            catalog_path=Path(args.catalog).expanduser().resolve(),
            output_root=Path(args.output_root).expanduser().resolve(),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, ProfessionalImageDiscoveryError) as exc:
        raise SystemExit(f"[task plan-images] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**plan, "planRef": path.as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def register_plan_images_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "plan-images",
        help=(
            "按实体/季节/风格/视角/热度生成 Pinterest 优先、图虫补充、"
            "Wikimedia Commons 开放许可候选的发现计划"
        ),
    )
    parser.add_argument("--entity", action="append", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--viewpoint", required=True)
    parser.add_argument("--popularity", required=True)
    parser.add_argument("--catalog", default=str(CATALOG_PATH))
    parser.add_argument("--output-root", default=str(DISCOVERY_ROOT))
    parser.set_defaults(handler=handle_plan_images)


__all__ = ["handle_plan_images", "register_plan_images_parser"]
