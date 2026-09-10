"""Argparse composition for canonical immutable release commands."""
from __future__ import annotations

import argparse



def register_parser(subparsers: argparse._SubParsersAction) -> None:
    from content.release.canonical import handler as owner
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

    from content.release.canonical.offline_snapshot_migration import handle_migrate_offline_source
    migration = commands.add_parser("migrate-offline-source", help="显式一次性转换冻结旧源为独立当前 schema 输入；保留原审核，不写共享 publish")
    for flag in ("selection-file", "source-revision", "publish-root", "executions-root", "author-authority", "output-dir"):
        migration.add_argument("--" + flag, required=True)
    migration.add_argument("--library-root")
    migration.add_argument("--carried-root")
    migration.set_defaults(handler=handle_migrate_offline_source)

    offline = commands.add_parser("export-offline", help="从显式 canonical cohort 派生 Alpha 工程离线包；不发布或激活")
    offline.add_argument("--selection-file", required=True)
    offline.add_argument("--source-revision", required=True)
    offline.add_argument("--publish-root", required=True)
    offline.add_argument("--output-dir", required=True)
    offline.add_argument("--library-root")
    offline.add_argument("--carried-root")
    offline.add_argument("--dart-identity-output", help="生成制品内 manifest 摘要常量的显式路径")
    offline.add_argument("--check", action="store_true", help="只读验证现有导出和制品摘要，不刷新文件")
    offline.set_defaults(handler=owner.handle_export_offline)

    finalize = commands.add_parser(
        "finalize",
        help="一次完成 pool-build、release-integrity 与 create-once producer handoff",
    )
    finalize.add_argument("--release-id", required=True)
    finalize.add_argument("--cohort-file", required=True)
    finalize.add_argument(
        "--milestone",
        choices=("M1", "M10", "M100", "M1000", "M10000"),
        required=True,
    )
    finalize.add_argument("--producer-baseline-revision", required=True)
    finalize.add_argument("--publish-root")
    finalize.add_argument("--release-root")
    finalize.add_argument(
        "--reference-root",
        help="cohort/handoff 版本化副本根（缺省 QWQ_PUBLISH_ROOT/releases）；只是耐久备份，handoff-verify 不读它",
    )
    finalize.set_defaults(handler=owner.handle_release_finalize)

    handoff_verify = commands.add_parser(
        "handoff-verify",
        help="只读重放 producer handoff 内嵌事实并逐项比对 sealed release",
    )
    handoff_verify.add_argument("--release-id", required=True)
    handoff_verify.add_argument("--release-root")
    handoff_verify.add_argument("--expected-repository-id", help="显式约束内容仓身份；离线校验不要求挂载生产仓")
    handoff_verify.set_defaults(handler=owner.handle_handoff_verify)

    pool_query = commands.add_parser(
        "pool-query",
        help="只读列出 canonical 身份占位、资格及依赖：objects 含缺失依赖，occupied 不含；counts 只计 eligible（不做选择）",
    )
    pool_query.add_argument("--target-ref", action="append", default=None, help="只读点名 canonical posts/ 或 entities/ 引用，可重复")
    pool_query.add_argument("--candidate-file", help="只读候选 JSON：{candidates:[{objectRef,manifest}]}，不选择或批准对象")
    pool_query.add_argument("--publish-root")
    pool_query.add_argument("--json", dest="json_output", help="把完整结果写到该路径；stdout 只打印计数")
    pool_query.set_defaults(handler=_load_pool_query)
    _register_pool_cutover(commands)

    acceptance_lease = commands.add_parser(
        "acceptance-lease",
        help="管理 Data-owned 环境验收 lease 的 append-only acquire/revoke 事件",
    )
    lease_actions = acceptance_lease.add_subparsers(
        dest="acceptance_lease_action",
        required=True,
    )
    lease_acquire = lease_actions.add_parser("acquire")
    lease_acquire.add_argument("--env", required=True)
    lease_acquire.add_argument("--release-id", required=True)
    lease_acquire.add_argument("--lease-id", required=True)
    lease_acquire.add_argument("--import-run-id", required=True)
    lease_acquire.add_argument("--verify-run-id", required=True)
    lease_acquire.add_argument("--ttl-seconds", type=int, default=3600)
    lease_acquire.add_argument("--event-id", default="")
    lease_acquire.set_defaults(handler=_load_acceptance_lease)
    lease_revoke = lease_actions.add_parser("revoke")
    lease_revoke.add_argument("--env", required=True)
    lease_revoke.add_argument("--release-id", required=True)
    lease_revoke.add_argument("--lease-id", required=True)
    lease_revoke.add_argument("--acquire-event-ref", required=True)
    lease_revoke.add_argument("--event-id", default="")
    lease_revoke.set_defaults(handler=_load_acceptance_lease)

    lifecycle_exit = commands.add_parser(
        "lifecycle-exit",
        help="从 exact activate/verify/rollback/replay 结果签发 canonical Exit",
    )
    lifecycle_exit.add_argument("--env", required=True)
    lifecycle_exit.add_argument("--original-release-id", required=True)
    lifecycle_exit.add_argument(
        "--original-import-run-id", required=True,
        help="original 成功 activate run；由其 importRunId 重验 prepared apply",
    )
    lifecycle_exit.add_argument("--original-verify-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-to-release-id", required=True)
    lifecycle_exit.add_argument("--rollback-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-verify-run-id", required=True)
    lifecycle_exit.add_argument(
        "--replay-import-run-id", required=True,
        help="same-digest replay 成功 activate run，不接受 prepared apply run",
    )
    lifecycle_exit.add_argument("--replay-verify-run-id", required=True)
    lifecycle_exit.add_argument("--run-id", required=True)
    lifecycle_exit.set_defaults(handler=_load_lifecycle_exit)

    publish_object = commands.add_parser(
        "publish-object",
        help="对一个 approved 对象执行唯一一次原子 canonical 事务（已发布则 exact replay）",
    )
    publish_object.add_argument("--execution-id", required=True)
    publish_object.add_argument("--target-ref", required=True)
    publish_object.set_defaults(handler=owner.handle_publish_object)

    object_transaction = commands.add_parser(
        "object-transaction",
        help="按审计 delta 与 canonical Merkle 管理单一对象事务",
    )
    object_transaction_actions = object_transaction.add_subparsers(
        dest="object_transaction_action",
        required=True,
    )
    object_transaction_rollback = object_transaction_actions.add_parser(
        "rollback",
        help="按精确 inverse delta 回滚一笔已应用对象事务并保留回执",
    )
    object_transaction_rollback.add_argument("--transaction-id", required=True)
    object_transaction_rollback.add_argument("--output-root")
    object_transaction_rollback.add_argument("--publish-root")
    object_transaction_rollback.set_defaults(
        handler=_load_object_transaction_rollback
    )
    object_transaction_replay = object_transaction_actions.add_parser(
        "replay-package",
        help="用显式内容库持仓精确重放一笔已评审的对象事务包",
    )
    object_transaction_replay.add_argument("--replay-id", required=True)
    object_transaction_replay.add_argument("--source-package-root", required=True)
    object_transaction_replay.add_argument("--media-library-root", required=True)
    object_transaction_replay.add_argument("--output-root")
    object_transaction_replay.add_argument("--publish-root")
    object_transaction_replay.set_defaults(
        handler=_load_object_transaction_replay_package
    )

    build_lookups = commands.add_parser(
        "build-lookups",
        help="为 immutable release 生成 create-once first-consumer lookup indexes",
    )
    build_lookups.add_argument("--release-id", required=True)
    build_lookups.add_argument("--publish-root")
    build_lookups.add_argument("--release-root")
    build_lookups.add_argument("--taxonomy-root")
    build_lookups.set_defaults(handler=_load_build_lookup_indexes)

    reset_canonical = commands.add_parser(
        "reset-canonical",
        help="在空基线 full-sync 回执后清空 canonical publish 输出",
    )
    reset_canonical.add_argument("--empty-baseline-release", required=True)
    reset_canonical.add_argument(
        "--env", required=True, help="已应用空基线的目标环境，逗号分隔"
    )
    reset_canonical.set_defaults(handler=_load_reset_canonical)


def _register_pool_cutover(commands) -> None:
    parser = commands.add_parser("pool-cutover", help="显式全池盘点/预验/原子切换；不转换或批准对象，不自动恢复")
    actions = parser.add_subparsers(dest="cutover_action", required=True)
    from content.release.canonical.pool_cutover_inventory import register_parser as register_inventory
    register_inventory(actions)
    snapshot = actions.add_parser("snapshot", help="只读全部占位身份和 exact tree 摘要，stdout 不授予资格")
    snapshot.add_argument("--publish-root", required=True)
    snapshot.set_defaults(handler=_load_pool_cutover)
    for action in ("dry-run", "activate", "inspect", "cleanup"):
        command = actions.add_parser(action)
        command.add_argument("--plan", required=True)
        command.add_argument("--plan-digest", required=True)
        if action != "inspect":
            command.add_argument("--authorization", required=True, help="宿主单独确认的精确授权文件；CLI 不生成授权")
            command.add_argument("--authorization-digest", required=True)
        if action == "dry-run":
            command.add_argument("--evidence-output", required=True, help="全新证据文件的绝对路径；不覆盖")
        elif action == "activate":
            command.add_argument("--dry-run-evidence", required=True)
            command.add_argument("--dry-run-digest", required=True)
        else:
            command.add_argument("--intent", required=True)
            command.add_argument("--intent-digest", required=True)
        command.set_defaults(handler=_load_pool_cutover)


def _cutover_result(args: argparse.Namespace) -> dict:
    from pathlib import Path
    from content.release.canonical import pool_cutover
    if args.cutover_action == "snapshot":
        return pool_cutover.snapshot_pool(Path(args.publish_root))
    common = {"plan_path": Path(args.plan), "expected_plan_digest": args.plan_digest}
    if args.cutover_action != "inspect":
        common["authorization"] = {"ref": args.authorization, "digest": args.authorization_digest}
    if args.cutover_action == "dry-run":
        return pool_cutover.dry_run_pool_cutover(**common, evidence_path=Path(args.evidence_output))
    if args.cutover_action == "activate":
        return pool_cutover.activate_pool_cutover(**common, dry_run_evidence={"ref": args.dry_run_evidence, "digest": args.dry_run_digest})
    common["intent"] = {"ref": args.intent, "digest": args.intent_digest}
    if args.cutover_action == "inspect":
        return pool_cutover.inspect_pool_cutover(**common)
    return pool_cutover.cleanup_pool_cutover(**common)


def _load_pool_cutover(args: argparse.Namespace) -> None:
    import json
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    try:
        result = _cutover_result(args)
    except (ObjectTransactionError, OSError, ValueError) as error:
        # JSON/文件错误也给 exact 诊断；保留下层已有 typed code，不吞提交后须 inspect 的结果。
        code = str(error).split(":", 1)[0]
        if not code.startswith("DATA."):
            code = "DATA.CUTOVER.INPUT_INVALID"
        print(json.dumps({"status": "blocked", "code": code, "message": str(error)}, ensure_ascii=False))
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _load_pool_query(args: argparse.Namespace) -> None:
    import json
    from pathlib import Path
    from content.release.canonical.pool_query import query_pool
    from core.paths import PUBLISH_ROOT

    candidates = []
    if args.candidate_file:
        candidates = json.loads(Path(args.candidate_file).read_text(encoding="utf-8"))["candidates"]
    result = query_pool(Path(args.publish_root or PUBLISH_ROOT), target_refs=args.target_ref, candidates=candidates)
    payload = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.json_output:
        target = Path(args.json_output).expanduser().resolve()
        publish_root = Path(result["publishRoot"])
        if target == publish_root or publish_root in target.parents:
            raise ValueError("pool-query output must not mutate canonical publish")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        print(json.dumps({"schema": result["schema"], "counts": result["counts"], "excludedCount": len(result["excluded"]), "output": str(target)}, ensure_ascii=False))
    else:
        print(payload, end="")


def _load_object_transaction_rollback(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_consumers import (
        handle_object_transaction_rollback,
    )

    handle_object_transaction_rollback(args)


def _load_object_transaction_replay_package(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_consumers import (
        handle_object_transaction_replay_package,
    )

    handle_object_transaction_replay_package(args)


def _load_build_lookup_indexes(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_consumers import handle_build_lookup_indexes

    handle_build_lookup_indexes(args)


def _load_reset_canonical(args: argparse.Namespace) -> None:
    from content.release.canonical.reset import handle_reset_canonical

    handle_reset_canonical(args)


def _load_acceptance_lease(args: argparse.Namespace) -> None:
    from content.release.canonical.acceptance_lease import handle_acceptance_lease

    handle_acceptance_lease(args)


def _load_lifecycle_exit(args: argparse.Namespace) -> None:
    from content.release.canonical.lifecycle_exit import handle_lifecycle_exit

    handle_lifecycle_exit(args)
