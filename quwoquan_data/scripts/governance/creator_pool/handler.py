"""qwq-data governance creator-pool subcommands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common.creator_pool.batch_policy import default_target_for_batch
from governance.creator_pool.plan import run_plan
from governance.creator_pool.diversify import run_diversify
from governance.creator_pool.acquire import run_acquire
from governance.creator_pool.score import run_score
from governance.creator_pool.enrich import run_enrich
from governance.creator_pool.materialize import run_materialize
from governance.creator_pool.validate import run_validate
from governance.creator_pool.seed import run_seed
from governance.creator_pool.merge_user_fixtures import run_merge_user_fixtures
from governance.creator_pool.merge_user_pool import run_merge_user_pool
from governance.creator_pool.workflow import run_workflow
from _common.io import read_json
from _common.paths import creator_pool_shared_dir


def handle_creator_pool(args: argparse.Namespace) -> None:
    cmd = args.creator_pool_command
    vertical = args.vertical
    batch = args.batch
    if cmd == "plan":
        result = run_plan(
            vertical=vertical,
            batch_id=batch,
            target=int(args.target),
            fixture=Path(args.fixture) if getattr(args, "fixture", None) else None,
        )
        print(json.dumps({"planned": result.get("targetCount")}, ensure_ascii=False))
        return
    if cmd == "diversify":
        print(json.dumps(run_diversify(vertical=vertical, batch_id=batch), ensure_ascii=False))
        return
    if cmd == "merge-user-fixtures":
        print(json.dumps(run_merge_user_fixtures(vertical=vertical, batch_id=batch, dry_run=bool(args.dry_run)), ensure_ascii=False))
        return
    if cmd == "merge-user-pool":
        print(
            json.dumps(
                run_merge_user_pool(
                    vertical=vertical,
                    batch_id=batch,
                    include_current_user_slot=bool(getattr(args, "include_current_user_slot", True)),
                    dry_run=bool(args.dry_run),
                ),
                ensure_ascii=False,
            )
        )
        return
    if cmd == "retire-legacy-prefab-users":
        from governance.creator_pool.retire_legacy_prefab_users import run_retire_legacy_prefab_users

        raise SystemExit(run_retire_legacy_prefab_users(apply=bool(getattr(args, "apply", False))))
    if cmd == "acquire":
        print(json.dumps(run_acquire(vertical=vertical, batch_id=batch), ensure_ascii=False))
        return
    if cmd == "score":
        print(json.dumps(run_score(vertical=vertical, batch_id=batch), ensure_ascii=False))
        return
    if cmd == "enrich":
        print(json.dumps(run_enrich(vertical=vertical, batch_id=batch), ensure_ascii=False))
        return
    if cmd == "materialize":
        print(json.dumps(run_materialize(vertical=vertical, batch_id=batch, dry_run=bool(args.dry_run)), ensure_ascii=False))
        return
    if cmd == "validate":
        print(json.dumps(run_validate(vertical=vertical, batch_id=batch), ensure_ascii=False))
        return
    if cmd == "seed":
        print(json.dumps(run_seed(vertical=vertical, batch_id=batch, env=args.env, dry_run=bool(args.dry_run)), ensure_ascii=False))
        return
    if cmd == "workflow":
        result = run_workflow(
            vertical=vertical,
            batch_id=batch,
            target=int(args.target or 0),
            through=args.through,
            dry_run=bool(args.dry_run),
            fixture=getattr(args, "fixture", None),
            env=args.env,
        )
        print(json.dumps(result, ensure_ascii=False))
        return
    if cmd == "bind-content":
        from governance.creator_pool.content_bind import build_creator_content, write_creator_content_seed

        if bool(getattr(args, "dry_run", False)):
            payload = build_creator_content(batch_id=batch)
            print(json.dumps({"distinctAuthors": payload["distinctAuthors"], "posts": len(payload["posts"]), "dryRun": True}, ensure_ascii=False))
            return
        path = write_creator_content_seed(batch_id=batch)
        print(json.dumps({"wrote": path}, ensure_ascii=False))
        return
    if cmd == "rollout-dryrun":
        from governance.creator_pool.content_rollout import build_prod_rollout_dryrun, write_prod_rollout_dryrun

        if bool(getattr(args, "dry_run", False)):
            report = build_prod_rollout_dryrun(batch_id=batch)
            print(json.dumps({"decision": report["decision"], "stages": len(report["rolloutStages"]), "dryRun": True}, ensure_ascii=False))
            return
        path = write_prod_rollout_dryrun(batch_id=batch)
        print(json.dumps({"wrote": path}, ensure_ascii=False))
        return
    if cmd == "publish-creators":
        from governance.creator_pool.publish_creators import run_publish_creators

        result = run_publish_creators(
            vertical=vertical,
            batch_id=batch,
            target=int(args.target),
            out=Path(args.out) if getattr(args, "out", None) else None,
            mode=args.mode,
            dry_run=bool(args.dry_run),
        )
        print(json.dumps(result, ensure_ascii=False))
        return
    if cmd == "report":
        shared = creator_pool_shared_dir(vertical, batch)
        rollup = shared / "creator_rollup_report.json"
        if not rollup.is_file():
            print("[creator-pool report] missing rollup", file=sys.stderr)
            raise SystemExit(1)
        print(json.dumps(read_json(rollup), ensure_ascii=False, indent=2))
        return
    raise SystemExit(f"unknown creator-pool command: {cmd}")


def register_creator_pool_parser(sub: argparse._SubParsersAction) -> None:
    cp = sub.add_parser("creator-pool", help="Batch AI creator pool pipeline")
    cp_sub = cp.add_subparsers(dest="creator_pool_command", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--vertical", default="travel")
        p.add_argument("--batch", required=True)

    p_plan = cp_sub.add_parser("plan", help="Plan creator pool batch")
    _common(p_plan)
    p_plan.add_argument("--target", type=int, required=True)
    p_plan.add_argument("--fixture", help="Fixture directory for dry-run")
    p_plan.set_defaults(handler=handle_creator_pool)

    for name in ("acquire", "score", "enrich", "diversify"):
        p = cp_sub.add_parser(name)
        _common(p)
        p.set_defaults(handler=handle_creator_pool)

    p_mat = cp_sub.add_parser("materialize")
    _common(p_mat)
    p_mat.add_argument("--dry-run", action="store_true")
    p_mat.set_defaults(handler=handle_creator_pool)

    p_val = cp_sub.add_parser("validate")
    _common(p_val)
    p_val.set_defaults(handler=handle_creator_pool)

    p_seed = cp_sub.add_parser("seed")
    _common(p_seed)
    p_seed.add_argument("--env", default="alpha", choices=["alpha", "beta", "gamma"])
    p_seed.add_argument("--dry-run", action="store_true")
    p_seed.set_defaults(handler=handle_creator_pool)

    p_wf = cp_sub.add_parser("workflow")
    wf_sub = p_wf.add_subparsers(dest="workflow_command", required=True)
    p_run = wf_sub.add_parser("run")
    _common(p_run)
    p_run.add_argument("--target", type=int, default=0)
    p_run.add_argument("--through", default="validate", choices=["plan", "acquire", "score", "diversify", "enrich", "materialize", "validate", "seed"])
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--fixture")
    p_run.add_argument("--env", default="alpha")
    p_run.set_defaults(handler=handle_creator_pool, creator_pool_command="workflow")

    p_merge = cp_sub.add_parser("merge-user-fixtures")
    _common(p_merge)
    p_merge.add_argument("--dry-run", action="store_true")
    p_merge.set_defaults(handler=handle_creator_pool)

    p_pool = cp_sub.add_parser("merge-user-pool", help="Merge creator slice into canonical 1k user_pool creator slice + manifest")
    _common(p_pool)
    p_pool.add_argument("--include-current-user-slot", action="store_true", default=True)
    p_pool.add_argument("--no-include-current-user-slot", action="store_false", dest="include_current_user_slot")
    p_pool.add_argument("--dry-run", action="store_true")
    p_pool.set_defaults(handler=handle_creator_pool)

    p_retire = cp_sub.add_parser("retire-legacy-prefab-users", help="T4 legacy prefab user retire (dry-run by default)")
    _common(p_retire)
    p_retire.add_argument("--apply", action="store_true")
    p_retire.set_defaults(handler=handle_creator_pool)

    p_bind = cp_sub.add_parser("bind-content", help="Route a representative article/image/video subset to batch creators via match_creator")
    _common(p_bind)
    p_bind.add_argument("--dry-run", action="store_true")
    p_bind.set_defaults(handler=handle_creator_pool)

    p_rollout = cp_sub.add_parser("rollout-dryrun", help="Emit prod rollout dry-run evidence for creator-authored content (no prod-gray)")
    _common(p_rollout)
    p_rollout.add_argument("--dry-run", action="store_true")
    p_rollout.set_defaults(handler=handle_creator_pool)

    p_publish = cp_sub.add_parser("publish-creators", help="Project an approved creator batch into publish/creators")
    _common(p_publish)
    p_publish.add_argument("--target", type=int, default=default_target_for_batch("travel_photo_1k_v1"))
    p_publish.add_argument("--out", default=None, help="Output root, default quwoquan_data/publish/creators")
    p_publish.add_argument("--mode", default="commercial", choices=["trial", "commercial"])
    p_publish.add_argument("--dry-run", action="store_true")
    p_publish.set_defaults(handler=handle_creator_pool)

    p_report = cp_sub.add_parser("report")
    _common(p_report)
    p_report.set_defaults(handler=handle_creator_pool)
