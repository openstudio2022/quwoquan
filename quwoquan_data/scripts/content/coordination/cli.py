"""协作内核薄 CLI：参数解析后直接调用 Python API，并输出单个 JSON。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .store import CoordinationError, CoordinationStore


def _document(value: str) -> Any:
    if value.lstrip().startswith(("{", "[")):
        return json.loads(value)
    return json.loads(Path(value).read_text(encoding="utf-8"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="content-coordination")
    root.add_argument("--db", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    context = commands.add_parser("bind-context")
    context.add_argument("iteration_id"); context.add_argument("deployment_id")
    context.add_argument("--task-ref", required=True); context.add_argument("--task-digest", required=True)
    context.add_argument("--roots", type=_document, required=True); context.add_argument("--actor", type=_document, required=True)
    context.add_argument("--expected-digest")
    batch = commands.add_parser("claim-batch")
    batch.add_argument("--tokens", type=_document, required=True)
    batch.add_argument("--execution-id", required=True); batch.add_argument("--actor", type=_document, required=True)
    batch.add_argument("--nonce", required=True); batch.add_argument("--task-digest", required=True)
    batch.add_argument("--review", action="store_true")
    iteration = commands.add_parser("register-iteration")
    iteration.add_argument("iteration_id"); iteration.add_argument("authorization_ref")
    deployment = commands.add_parser("register-deployment")
    deployment.add_argument("iteration_id"); deployment.add_argument("deployment_id"); deployment.add_argument("--roles", required=True, type=_document); deployment.add_argument("--instance-id"); deployment.add_argument("--account-identity-ref"); deployment.add_argument("--resource-reservation-ref")
    shard = commands.add_parser("register-shard")
    shard.add_argument("iteration_id"); shard.add_argument("shard_id"); shard.add_argument("name"); shard.add_argument("scope_ref"); shard.add_argument("order", type=int); shard.add_argument("--targets", required=True, type=_document); shard.add_argument("--authorized-team")
    rename = commands.add_parser("rename-shard")
    rename.add_argument("iteration_id"); rename.add_argument("shard_id"); rename.add_argument("new_name")
    claim = commands.add_parser("claim")
    claim.add_argument("iteration_id"); claim.add_argument("team"); claim.add_argument("idempotency_key"); claim.add_argument("--shard-id"); claim.add_argument("--deployment-id")
    drain = commands.add_parser("begin-drain")
    drain.add_argument("iteration_id"); drain.add_argument("shard_id"); drain.add_argument("owner"); drain.add_argument("generation", type=int); drain.add_argument("idempotency_key")
    release = commands.add_parser("release")
    release.add_argument("iteration_id"); release.add_argument("shard_id"); release.add_argument("owner"); release.add_argument("generation", type=int); release.add_argument("idempotency_key"); release.add_argument("--handoff-ref", required=True); release.add_argument("--handoff-digest"); release.add_argument("--remaining", action="store_true")
    for name, ref_name in (("block", "fact_ref"), ("recover", "recovery_ref")):
        item = commands.add_parser(name); item.add_argument("iteration_id"); item.add_argument("shard_id"); item.add_argument("owner"); item.add_argument("generation", type=int); item.add_argument("idempotency_key"); item.add_argument(f"--{ref_name.replace('_','-')}", required=True); item.add_argument("--fact-digest")
    checkpoint = commands.add_parser("append-checkpoint")
    checkpoint.add_argument("iteration_id"); checkpoint.add_argument("fact_ref"); checkpoint.add_argument("fact_digest"); checkpoint.add_argument("source_type"); checkpoint.add_argument("--payload", type=_document, default={}); checkpoint.add_argument("--occurred-at"); checkpoint.add_argument("--shard-id"); checkpoint.add_argument("--deployment-id")
    status = commands.add_parser("status"); status.add_argument("iteration_id")
    timeline = commands.add_parser("timeline"); timeline.add_argument("iteration_id"); timeline.add_argument("--shard-id"); timeline.add_argument("--deployment-id"); timeline.add_argument("--after-sequence", type=int, default=0); timeline.add_argument("--limit", type=int)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = CoordinationStore(args.db)
    try:
        if args.command == "init": result: Any = {"path": str(store.initialize())}
        elif args.command == "bind-context":
            from .runtime import actor_key
            result = store.bind_context(args.iteration_id, args.deployment_id, task_ref=args.task_ref, task_digest=args.task_digest, roots=args.roots, actor=actor_key(args.actor), expected_digest=args.expected_digest)
        elif args.command == "claim-batch":
            from .runtime import actor_key
            from .fence import WriteFenceToken
            values = args.tokens if isinstance(args.tokens, list) else [args.tokens]
            result = store.claim_batch([WriteFenceToken(**value) for value in values], execution_id=args.execution_id, actor=actor_key(args.actor), nonce=args.nonce, task_digest=args.task_digest, review=args.review)
        elif args.command == "register-iteration": result = store.register_iteration(args.iteration_id, args.authorization_ref)
        elif args.command == "register-deployment": result = store.register_deployment(args.iteration_id, args.deployment_id, args.roles, instance_id=args.instance_id, account_identity_ref=args.account_identity_ref, resource_reservation_ref=args.resource_reservation_ref)
        elif args.command == "register-shard": result = store.register_shard(args.iteration_id, args.shard_id, args.name, args.scope_ref, args.order, args.targets, authorized_team=args.authorized_team)
        elif args.command == "rename-shard": result = store.rename_shard(args.iteration_id, args.shard_id, args.new_name)
        elif args.command == "claim": result = store.claim(args.iteration_id, args.team, args.idempotency_key, shard_id=args.shard_id, deployment_id=args.deployment_id)
        elif args.command == "begin-drain": result = store.begin_drain(args.iteration_id, args.shard_id, args.owner, args.generation, args.idempotency_key)
        elif args.command == "release": result = store.release(args.iteration_id, args.shard_id, args.owner, args.generation, args.idempotency_key, handoff_ref=args.handoff_ref, handoff_digest=args.handoff_digest, remaining=args.remaining)
        elif args.command == "block": result = store.block(args.iteration_id, args.shard_id, args.owner, args.generation, args.idempotency_key, fact_ref=args.fact_ref, fact_digest=args.fact_digest)
        elif args.command == "recover": result = store.recover(args.iteration_id, args.shard_id, args.owner, args.generation, args.idempotency_key, recovery_ref=args.recovery_ref, fact_digest=args.fact_digest)
        elif args.command == "append-checkpoint": result = store.append_checkpoint(args.iteration_id, fact_ref=args.fact_ref, fact_digest=args.fact_digest, source_type=args.source_type, occurred_at=args.occurred_at, payload=args.payload, shard_id=args.shard_id, deployment_id=args.deployment_id)
        elif args.command == "status": result = store.status(args.iteration_id)
        else: result = store.timeline(args.iteration_id, shard_id=args.shard_id, deployment_id=args.deployment_id, after_sequence=args.after_sequence, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (CoordinationError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": {"code": exc.code if isinstance(exc, CoordinationError) else "COORDINATION.INVALID_ARGUMENT", "message": str(exc)}}, ensure_ascii=False, sort_keys=True))
        return 2


def _run_namespace(args: argparse.Namespace) -> None:
    arguments = list(args.coordination_args)
    raise SystemExit(main((["--db", str(args.db)] if args.db else []) + arguments))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    command = subparsers.add_parser("coordination", help="内容生产分片认领、交接与只读时间线")
    command.add_argument("--db", type=Path)
    command.add_argument("coordination_args", nargs=argparse.REMAINDER)
    command.set_defaults(handler=_run_namespace)
