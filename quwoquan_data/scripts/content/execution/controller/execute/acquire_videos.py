"""Public Data CLI binding for professional research-video acquisition."""
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
    stock_provider = str(getattr(args, "stock_provider", "") or "").strip()
    stock_entity = str(getattr(args, "stock_entity", "") or "").strip()
    if bool(stock_provider) != bool(stock_entity):
        raise SystemExit(
            "[task acquire-videos] GATE_BLOCK "
            "--stock-provider and --stock-entity must be provided together"
        )
    if str(args.commons_entity or "").strip() or stock_entity:
        try:
            from content.source.professional_commons_video_input import (
                CommonsVideoInputError,
                acquire_commons_sourced_videos,
                acquire_stock_sourced_videos,
            )
            from content.source.research.auto_plan_video_stock import (
                StockVideoProviderCredentialMissing,
            )

            if stock_provider:
                entity_id = str(args.stock_entity)
                outcomes = acquire_stock_sourced_videos(
                    provider=stock_provider,
                    entity_id=entity_id,
                    entity_aliases=tuple(args.commons_entity_alias or ()),
                    handoff_ref=Path(args.handoff_ref).expanduser().resolve(),
                    output_root=output_root,
                    candidate_limit=int(args.commons_candidate_limit),
                )
            else:
                entity_id = str(args.commons_entity)
                outcomes = acquire_commons_sourced_videos(
                    entity_id=entity_id,
                    entity_aliases=tuple(args.commons_entity_alias or ()),
                    handoff_ref=Path(args.handoff_ref).expanduser().resolve(),
                    output_root=output_root,
                    candidate_limit=int(args.commons_candidate_limit),
                )
        except ModuleNotFoundError as exc:
            dependency = str(exc.name or "unknown")
            raise SystemExit(
                "[task acquire-videos] GATE_BLOCK "
                "DATA.SOURCE.VIDEO_PROBE_DEPENDENCY_MISSING "
                f"dependency={dependency}"
            ) from exc
        except StockVideoProviderCredentialMissing as exc:
            raise SystemExit(f"[task acquire-videos] GATE_BLOCK {exc}") from exc
        except CommonsVideoInputError as exc:
            raise SystemExit(f"[task acquire-videos] GATE_BLOCK {exc}") from exc
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise SystemExit(f"[task acquire-videos] GATE_BLOCK {exc}") from exc
        print(
            json.dumps(
                {
                    "schema": "quwoquan_data.commons_video_acquisition_result",
                    "provider": stock_provider or "wikimedia_commons_video",
                    "entityId": entity_id,
                    "candidateCount": len(outcomes),
                    "acceptedCount": sum(
                        row["distributionDecision"]
                        in {"research_allowed", "commercial_allowed"}
                        for row in outcomes
                    ),
                    "outcomes": outcomes,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    try:
        # Keep CLI registration/bootstrap lightweight.  OpenCV/FFmpeg belong to
        # the actual acquisition probe, not to ``task preflight`` parser setup.
        from content.source.professional_video_acquisition import (
            acquire_professional_videos,
        )

        receipt, path = acquire_professional_videos(
            Path(args.manifest).expanduser().resolve(),
            handoff_ref=Path(args.handoff_ref).expanduser().resolve(),
            manual_root=manual_root,
            output_root=output_root,
        )
    except ModuleNotFoundError as exc:
        dependency = str(exc.name or "unknown")
        raise SystemExit(
            "[task acquire-videos] GATE_BLOCK "
            "DATA.SOURCE.VIDEO_PROBE_DEPENDENCY_MISSING "
            f"dependency={dependency}"
        ) from exc
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task acquire-videos] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**receipt, "receiptRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def register_acquire_videos_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "acquire-videos",
        help="通过公开直链、平台支持 API 或人工文件取得专业研究视频",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest")
    mode.add_argument("--commons-entity")
    mode.add_argument(
        "--stock-entity",
        help="经登记 stock provider 官方 API 取得该实体视频（配合 --stock-provider）",
    )
    parser.add_argument(
        "--stock-provider",
        choices=("pexels_videos", "pixabay_videos"),
        help="governed stock 视频 provider；仅与 --stock-entity 一起使用",
    )
    parser.add_argument("--handoff-ref", required=True)
    parser.add_argument("--manual-root")
    parser.add_argument("--output-root")
    parser.add_argument("--commons-entity-alias", action="append", default=[])
    parser.add_argument("--commons-candidate-limit", type=int, default=1)
    parser.set_defaults(handler=handle_acquire_videos)


__all__ = ["handle_acquire_videos", "register_acquire_videos_parser"]
