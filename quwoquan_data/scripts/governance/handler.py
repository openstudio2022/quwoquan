"""qwq-data governance — auditable data governance candidate operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from governance.creators.candidates.review import main as review_candidates_main
from governance.creators.candidates.state import STATUSES


def handle_governance(args: argparse.Namespace) -> None:
    cmd = getattr(args, "governance_command", None)
    if cmd == "creators":
        from content.templates.creator import validate_creators
        from content.templates.registry import TemplateRegistry

        registry = TemplateRegistry.load()
        if args.creators_command == "list":
            for creator_id in sorted(registry.creators):
                print(creator_id)
            return
        if args.creators_command == "avatar":
            from governance.creators.avatar import (
                CreatorAvatarError,
                materialize_creator_avatar,
            )

            try:
                result = materialize_creator_avatar(
                    creator_ref=args.creator_ref,
                    source_object_ref=args.source_object_ref,
                    source_asset_id=args.source_asset_id,
                    confirm_non_identifiable_person=(
                        args.confirm_non_identifiable_person
                    ),
                )
            except CreatorAvatarError as exc:
                raise SystemExit(
                    f"[governance creators avatar] GATE_BLOCK: {exc}"
                ) from exc
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        issues = validate_creators(registry)
        if issues:
            print("[governance creators] FAIL")
            for issue in issues:
                print(f"  - {issue}")
            raise SystemExit(1)
        print(f"[governance creators] OK profiles={len(registry.creators)}")
        return
    if cmd == "taxonomy":
        from governance.taxonomy.handler import handle_taxonomy

        handle_taxonomy(args)
        return
    if cmd == "coverage":
        from governance.coverage.handler import handle_coverage_command

        handle_coverage_command(args)
        return
    if cmd == "media-probe":
        from governance.media_probe import (
            prepare_media_probe_assets,
            validate_media_probe_assets,
        )

        output_root = Path(args.output_root).expanduser().resolve()
        asset_ids = {
            value.strip()
            for value in str(args.asset_ids or "").split(",")
            if value.strip()
        }
        if args.media_probe_command == "prepare":
            result = prepare_media_probe_assets(
                output_root=output_root,
                asset_ids=asset_ids or None,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.media_probe_command == "validate":
            issues = validate_media_probe_assets(
                output_root=output_root,
                asset_ids=asset_ids or None,
            )
            if issues:
                print("[governance media-probe] FAIL")
                for issue in issues:
                    print(f"  - {issue}")
                raise SystemExit(1)
            print("[governance media-probe] OK")
            return
        raise SystemExit("[governance media-probe] subcommand required")
    if cmd == "review-candidates":
        argv: list[str] = []
        if getattr(args, "root", None):
            argv.extend(["--root", str(args.root)])
        if getattr(args, "reviews", None):
            argv.extend(["--reviews", str(args.reviews)])
        if getattr(args, "list_status", None):
            argv.extend(["--list-status", str(args.list_status)])
        if getattr(args, "kind", None):
            argv.extend(["--kind", str(args.kind)])
        raise SystemExit(review_candidates_main(argv))
    raise SystemExit(f"unknown governance command: {cmd}")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("governance", help="Data governance candidate operations")
    sub = p.add_subparsers(dest="governance_command")

    from governance.coverage.handler import register_coverage_parser
    from governance.taxonomy.handler import register_taxonomy_parser

    creators = sub.add_parser(
        "creators", help="Validate or list repository-owned creator profiles"
    )
    creators_sub = creators.add_subparsers(dest="creators_command", required=True)
    creators_sub.add_parser("validate")
    creators_sub.add_parser("list")
    creator_avatar = creators_sub.add_parser(
        "avatar",
        help="Materialize one creator avatar from canonical publish rights evidence",
    )
    creator_avatar.add_argument("--creator-ref", required=True)
    creator_avatar.add_argument(
        "--source-object-ref",
        required=True,
        help="Canonical publish-relative entities/** or posts/** object",
    )
    creator_avatar.add_argument("--source-asset-id", required=True)
    creator_avatar.add_argument(
        "--confirm-non-identifiable-person",
        action="store_true",
        help="Attest that the selected source crop depicts no identifiable person",
    )
    register_taxonomy_parser(sub)
    register_coverage_parser(sub)

    media_probe = sub.add_parser(
        "media-probe",
        help="生成或校验受控视频播放 probe 与 storyboard",
    )
    media_probe_sub = media_probe.add_subparsers(
        dest="media_probe_command",
        required=True,
    )
    for command in ("prepare", "validate"):
        action = media_probe_sub.add_parser(command)
        action.add_argument("--output-root", required=True)
        action.add_argument(
            "--asset-ids",
            help="逗号分隔 assetId；缺省处理 profile 全集",
        )

    review = sub.add_parser(
        "review-candidates", help="Apply or list isolated governance candidate reviews"
    )
    review.add_argument("--root")
    action = review.add_mutually_exclusive_group(required=True)
    action.add_argument("--reviews")
    action.add_argument("--list-status", choices=sorted(STATUSES))
    review.add_argument("--kind")

    p.set_defaults(handler=handle_governance)
