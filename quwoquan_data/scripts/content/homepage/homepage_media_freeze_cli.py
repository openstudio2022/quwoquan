"""`task freeze-homepage-media`: freeze page-image decisions at `1.download`.

The command consumes only candidate-backed task-init truth: `0.plan/request.json` and
`0.plan/target_set.json`.  It never falls back to the retired execution spec.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from typing import Any


def _frozen_execution_plan(execution_id: str) -> tuple[str, list[dict[str, Any]]]:
    from core.io import read_json
    from core.paths import execution_root

    root = execution_root(execution_id)
    request = read_json(root / "0.plan/request.json")
    target_set = read_json(root / "0.plan/target_set.json")
    if not isinstance(request, Mapping) or request.get("executionId") != execution_id:
        raise ValueError("frozen request identity mismatch")
    carrier = str(request.get("carrier") or "").strip()
    if carrier not in {"homepage", "article", "image", "video"}:
        raise ValueError("frozen request carrier is invalid")
    if not isinstance(target_set, Mapping) or target_set.get("executionId") != execution_id:
        raise ValueError("frozen target_set identity mismatch")
    targets = target_set.get("targets")
    if not isinstance(targets, list) or not targets or not all(isinstance(row, Mapping) for row in targets):
        raise ValueError("frozen target_set targets are invalid")
    if int(target_set.get("targetCount") or 0) != len(targets):
        raise ValueError("frozen target_set targetCount drift")
    return carrier, [dict(row) for row in targets]


def _handle_freeze_homepage_media(args: argparse.Namespace) -> None:
    from content.execution.runtime_state import write_execution_runtime_state
    from content.homepage.homepage_media_freeze import (
        freeze_homepage_media_dispositions,
        freeze_image_media_dispositions,
    )
    from governance.coverage.entity_extract import require_domain_etype

    execution_id = str(args.execution_id).strip()
    try:
        carrier, targets = _frozen_execution_plan(execution_id)
        if carrier not in {"homepage", "image"}:
            raise ValueError(
                f"carrier={carrier} has no image-disposition freeze action; "
                "video with no downloaded images has zero disposition obligations"
            )
        write_execution_runtime_state(execution_id, command="homepage")
        frozen = 0
        for target in targets:
            name = str(target.get("name") or "").strip()
            if carrier == "homepage":
                entity_type = str(target.get("entityType") or "").strip()
                domain, etype = require_domain_etype(
                    entity_type,
                    context=f"homepage media freeze for execution={execution_id}",
                )
                payload = freeze_homepage_media_dispositions(
                    execution_id,
                    domain,
                    etype,
                    name,
                    aliases=tuple(str(value) for value in target.get("aliases") or ()),
                )
                if not payload:
                    print(f"{name}: no base draft yet; nothing to freeze")
                    continue
            else:
                payload = freeze_image_media_dispositions(execution_id, target)
            frozen += 1
            print(f"{name}: {len(payload.get('assets') or [])} dispositions frozen")
    except (OSError, TypeError, ValueError) as exc:
        print(f"freeze-homepage-media rejected: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"frozen {frozen}/{len(targets)} {carrier} object(s)")


def register_freeze_homepage_media_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "freeze-homepage-media",
        help="1.download 收口：一次冻结 homepage/image 逐图处置与 assetId（create-once）",
    )
    parser.add_argument("--execution-id", required=True)
    parser.set_defaults(handler=_handle_freeze_homepage_media)


__all__ = ["register_freeze_homepage_media_parser"]
