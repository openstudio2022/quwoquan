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
    if cmd == "workstream-baseline":
        from governance.workstream_baseline import (
            WorkstreamBaselineError,
            create_data_workstream_baseline,
        )

        try:
            payload, destination = create_data_workstream_baseline(
                entity_catalog_ref=args.entity_catalog_ref,
                cursor_plan_path=Path(args.cursor_plan),
                protected_paths=tuple(Path(value) for value in args.protect),
                owner_rules=tuple(args.owner_rule),
                scopes=tuple(args.scope),
                output_root=(Path(args.output_root).expanduser().resolve() if args.output_root else None),
                freeze_reason=args.freeze_reason,
            )
        except WorkstreamBaselineError as exc:
            raise SystemExit(f"[governance workstream-baseline] GATE_BLOCK: {exc}") from exc
        print(
            json.dumps(
                {
                    "baselineDigest": payload["baselineDigest"],
                    "protectedEvidenceManifestDigest": payload[
                        "protectedEvidenceManifestDigest"
                    ],
                    "fileOwnershipManifestDigest": payload[
                        "fileOwnershipManifestDigest"
                    ],
                    "path": destination.as_posix(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if cmd == "output-layout-migration":
        from governance.output_layout_migration import (
            OutputLayoutMigrationError,
            apply_output_layout_migration,
            plan_output_layout_migration,
        )

        try:
            if args.output_layout_command == "plan":
                payload, destination = plan_output_layout_migration(
                    data_output_root=Path(args.data_output_root).expanduser().resolve(),
                )
            else:
                payload, destination = apply_output_layout_migration(
                    plan_path=Path(args.plan),
                    plan_digest=args.plan_digest,
                )
        except OutputLayoutMigrationError as exc:
            raise SystemExit(
                f"[governance output-layout-migration] GATE_BLOCK: {exc}"
            ) from exc
        print(
            json.dumps(
                {
                    "documentKind": payload["documentKind"],
                    "planDigest": payload["planDigest"],
                    "status": payload["status"],
                    "path": destination.as_posix(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if cmd == "protect-quarantine":
        from governance.protected_quarantine_evidence import (
            DEFAULT_REASON,
            FORENSIC_DEFAULT_REASON,
            ProtectedQuarantineEvidenceError,
            protect_forensic_quarantine,
            protect_historical_quarantine,
        )

        try:
            if args.provenance == "forensic":
                if args.migration_apply_receipt:
                    raise ProtectedQuarantineEvidenceError(
                        "forensic provenance uses the quarantine's own QUARANTINE.json; "
                        "--migration-apply-receipt is not accepted"
                    )
                payload, destination = protect_forensic_quarantine(
                    quarantine_root=Path(args.quarantine),
                    data_output_root=Path(args.data_output_root).expanduser().resolve(),
                    reason=args.reason or FORENSIC_DEFAULT_REASON,
                )
            else:
                if not args.migration_apply_receipt:
                    raise ProtectedQuarantineEvidenceError(
                        "migration provenance requires --migration-apply-receipt"
                    )
                payload, destination = protect_historical_quarantine(
                    quarantine_root=Path(args.quarantine),
                    migration_apply_receipt=Path(args.migration_apply_receipt),
                    data_output_root=Path(args.data_output_root).expanduser().resolve(),
                    reason=args.reason or DEFAULT_REASON,
                )
        except ProtectedQuarantineEvidenceError as exc:
            raise SystemExit(
                f"[governance protect-quarantine] GATE_BLOCK: {exc}"
            ) from exc
        print(
            json.dumps(
                {
                    "manifestDigest": payload["manifestDigest"],
                    "treeDigest": payload["treeDigest"],
                    "quarantineRef": payload["quarantineRef"],
                    "provenance": payload.get("provenance", "migration"),
                    "status": payload["status"],
                    "path": destination.as_posix(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if cmd == "public-cli-live-import-zero":
        from verify.verify_public_cli_live_import_zero import main as live_import_main

        argv = ["--output", str(args.output)] if args.output else []
        raise SystemExit(live_import_main(argv))
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
    live_import = sub.add_parser(
        "public-cli-live-import-zero",
        help="隔离导入全部 public CLI command modules 并证明旧五家族零加载",
    )
    live_import.add_argument("--output", help="可选 create-once passing receipt 路径")

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

    baseline = sub.add_parser(
        "workstream-baseline",
        help="冻结共享 Data WIP、文件所有权和受保护证据摘要",
    )
    baseline.add_argument("--entity-catalog-ref", required=True)
    baseline.add_argument("--cursor-plan", required=True)
    baseline.add_argument(
        "--protect",
        action="append",
        required=True,
        help="仓内必须保留的 evidence 文件或目录；可重复",
    )
    baseline.add_argument(
        "--owner-rule",
        action="append",
        required=True,
        help="最长前缀匹配的 <repo-prefix>=<owner>；可重复",
    )
    baseline.add_argument(
        "--scope",
        action="append",
        default=[
            "quwoquan_data",
            "specs/feature-tree/discovery-content/object-homepage-coverage-scaling",
        ],
        help="纳入 git worktree 快照的仓库相对路径；可重复",
    )
    baseline.add_argument("--output-root")
    baseline.add_argument(
        "--freeze-reason",
        default="WAIT_CONTENT/GATE_BLOCK",
    )

    output_layout = sub.add_parser(
        "output-layout-migration",
        help="规划或应用旧 Data output namespace 的一次性无损迁移",
    )
    output_layout_sub = output_layout.add_subparsers(
        dest="output_layout_command",
        required=True,
    )
    output_layout_plan = output_layout_sub.add_parser("plan")
    output_layout_plan.add_argument(
        "--data-output-root",
        default=str(Path(".qwq_output/data")),
    )
    output_layout_apply = output_layout_sub.add_parser("apply")
    output_layout_apply.add_argument("--plan", required=True)
    output_layout_apply.add_argument("--plan-digest", required=True)

    protect_quarantine = sub.add_parser(
        "protect-quarantine",
        help="将历史或取证 quarantine 冻结为不可复用的只读证据",
    )
    protect_quarantine.add_argument("--quarantine", required=True)
    protect_quarantine.add_argument(
        "--provenance",
        choices=("migration", "forensic"),
        default="migration",
        help="migration 绑定迁移 apply receipt;forensic 以隔离区自身 QUARANTINE.json 为凭据",
    )
    protect_quarantine.add_argument(
        "--migration-apply-receipt",
        help="provenance=migration 时必填",
    )
    protect_quarantine.add_argument(
        "--data-output-root",
        default=str(Path(".qwq_output/data")),
    )
    protect_quarantine.add_argument(
        "--reason",
        help="缺省按 provenance 使用对应默认理由",
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
