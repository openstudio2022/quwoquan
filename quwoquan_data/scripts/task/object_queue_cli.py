"""CLI wiring for object queue commands."""
from __future__ import annotations

import argparse
import json
from typing import Any

from task.object_queue_core import (
    DEFAULT_LEASE_TTL_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_STARTUP_FAILURES,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    SUPPORTED_QUEUE_BACKENDS,
    list_notifications,
)
from task.object_queue_jobs import enqueue_ref_jobs
from task.object_queue_packets import build_lease_packet
from task.object_queue_runtime import (
    acquire_lease,
    complete_job,
    complete_job_with_envelope,
    dead_jobs,
    fail_job,
    queue_summary,
    reap_jobs,
    record_usage,
    renew_lease,
    requeue_refs,
    revive_dead_startup_jobs,
    spillover_dead,
)

def register_object_queue_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("object-queue", help="单篇隔离的 object-stage job 队列（Subagent 并行调度）")
    sub = p.add_subparsers(dest="object_queue_command")

    def _emit(payload: Any) -> None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    pe = sub.add_parser("enqueue", help="把 content_plan_packet 各 ref 入队为 author job")
    pe.add_argument("--task", required=True)
    pe.add_argument("--batch", required=True)
    pe.add_argument("--stage", default="author")
    pe.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    pe.add_argument("--max-wall-clock", type=int, default=DEFAULT_MAX_WALL_CLOCK_SECONDS, help="逐 job 墙钟硬上限（秒，默认 1200=20min）")
    pe.add_argument("--backend", choices=SUPPORTED_QUEUE_BACKENDS, default=None, help="队列后端：local_file 小批；reliabletask 生产桥")

    def _do_enqueue(args: argparse.Namespace) -> None:
        from _common.content_plan import load_content_plan_packet

        packet = load_content_plan_packet(args.task, args.batch) or {}
        items = [
            {
                "ref": i.get("ref"),
                "baseSourceRef": i.get("baseSourceRef"),
                "meta": {
                    "writingIntent": i.get("writingIntent"),
                    "contentType": i.get("contentType") or i.get("carrier"),
                    "authorId": i.get("authorId"),
                    "creatorProfileId": i.get("creatorProfileId"),
                    "creatorArchetype": i.get("creatorArchetype"),
                    "creatorProfileVersion": i.get("creatorProfileVersion"),
                    "creatorDisclosure": i.get("creatorDisclosure"),
                    "experienceClaimMode": i.get("experienceClaimMode"),
                    "authorQualitySignals": i.get("authorQualitySignals"),
                },
            }
            for i in (packet.get("items") or [])
            if i.get("ref")
        ]
        jobs = enqueue_ref_jobs(
            args.task, args.batch, items, args.stage,
            max_attempts=args.max_attempts,
            max_startup_failures=DEFAULT_MAX_STARTUP_FAILURES,
            max_wall_clock_seconds=args.max_wall_clock,
            queue_backend=args.backend,
        )
        _emit({"enqueued": len(jobs), "summary": queue_summary(args.task, args.batch)})

    pe.set_defaults(handler=_do_enqueue)

    pl = sub.add_parser("list", help="队列状态汇总")
    pl.add_argument("--task", required=True)
    pl.add_argument("--batch", required=True)
    pl.set_defaults(handler=lambda a: _emit(queue_summary(a.task, a.batch)))

    pln = sub.add_parser("lease-next", help="租一个可执行 job 并打印 handoff packet（供 Subagent 直接消费）")
    pln.add_argument("--task", required=True)
    pln.add_argument("--batch", required=True)
    pln.add_argument("--worker", required=True)
    pln.add_argument("--stage", default=None)
    pln.add_argument("--ref", default=None, help="只租该 ref（by-leaf / per-ref worker 精确寻址）")
    pln.add_argument("--ttl", type=int, default=DEFAULT_LEASE_TTL_SECONDS, help="lease 租约 TTL（秒），心跳前的可见性超时")

    def _do_lease_next(args: argparse.Namespace) -> None:
        job = acquire_lease(args.task, args.batch, worker=args.worker, stage=args.stage, ref=args.ref, ttl_seconds=args.ttl)
        if job is None:
            _emit({"leased": False, "summary": queue_summary(args.task, args.batch)})
            return
        _emit({"leased": True, "packet": build_lease_packet(job)})

    pln.set_defaults(handler=_do_lease_next)

    pc = sub.add_parser("complete", help="标记 job 成功（需持有 lease）")
    pc.add_argument("--task", required=True)
    pc.add_argument("--batch", required=True)
    pc.add_argument("--job", required=True)
    pc.add_argument("--lease", required=True)
    pc.set_defaults(handler=lambda a: _emit(complete_job(a.task, a.batch, a.job, a.lease)))

    pce = sub.add_parser("complete-envelope", help="校验 AgentResultEnvelope 后标记 job 成功（生产路径）")
    pce.add_argument("--task", required=True)
    pce.add_argument("--batch", required=True)
    pce.add_argument("--job", required=True)
    pce.add_argument("--lease", required=True)
    pce.add_argument("--envelope", required=True, help="AgentResultEnvelope JSON；相对 batch root 或绝对路径")
    pce.add_argument("--workspace-root", default=None, help="校验文件 hash 的根目录；默认 batch root")
    pce.set_defaults(
        handler=lambda a: _emit(
            complete_job_with_envelope(
                a.task,
                a.batch,
                a.job,
                a.lease,
                envelope_path=a.envelope,
                workspace_root=a.workspace_root,
            )
        )
    )

    pf = sub.add_parser("fail", help="标记 job 失败（未超 maxAttempts 退避重取，超出/卡死转 dead）")
    pf.add_argument("--task", required=True)
    pf.add_argument("--batch", required=True)
    pf.add_argument("--job", required=True)
    pf.add_argument("--lease", required=True)
    pf.add_argument("--error", required=True)
    pf.add_argument("--fingerprint", default=None, help="本轮 issues 指纹（断路器识别同 issues 反复修不动）")
    pf.add_argument("--startup-failure", action="store_true", help="startup 等未真正执行场景：累计 startupFailureCount，不消耗内容重试预算")
    pf.set_defaults(
        handler=lambda a: _emit(
            fail_job(
                a.task,
                a.batch,
                a.job,
                a.lease,
                error=a.error,
                fingerprint=a.fingerprint,
                startup_failure=bool(a.startup_failure),
            )
        )
    )

    pu = sub.add_parser("usage", help="累计 token/cost 用量（超预算强制 dead）")
    pu.add_argument("--task", required=True)
    pu.add_argument("--batch", required=True)
    pu.add_argument("--job", required=True)
    pu.add_argument("--lease", required=True)
    pu.add_argument("--tokens", type=int, default=0)
    pu.add_argument("--cost-usd", type=float, default=0.0)
    pu.set_defaults(handler=lambda a: _emit(record_usage(a.task, a.batch, a.job, a.lease, tokens=a.tokens, cost_usd=a.cost_usd)))

    pn = sub.add_parser("notifications", help="列出断路器/超时/预算事件（编排循环订阅）")
    pn.add_argument("--task", required=True)
    pn.add_argument("--batch", required=True)
    pn.set_defaults(handler=lambda a: _emit({"notifications": list_notifications(a.task, a.batch)}))

    ph = sub.add_parser("heartbeat", help="续租（renew lease），长任务周期调用避免被 reaper 回收")
    ph.add_argument("--task", required=True)
    ph.add_argument("--batch", required=True)
    ph.add_argument("--job", required=True)
    ph.add_argument("--lease", required=True)
    ph.add_argument("--ttl", type=int, default=DEFAULT_LEASE_TTL_SECONDS)
    ph.set_defaults(handler=lambda a: _emit(renew_lease(a.task, a.batch, a.job, a.lease, ttl_seconds=a.ttl)))

    pr = sub.add_parser("reap", help="reaper：回收过期 lease（崩溃）+ 强制 timeout 超墙钟 job")
    pr.add_argument("--task", required=True)
    pr.add_argument("--batch", required=True)
    pr.set_defaults(handler=lambda a: _emit(reap_jobs(a.task, a.batch)))

    pd = sub.add_parser("dead-list", help="列出 dead job（转人工修复队列）")
    pd.add_argument("--task", required=True)
    pd.add_argument("--batch", required=True)
    pd.set_defaults(handler=lambda a: _emit({"dead": dead_jobs(a.task, a.batch)}))

    prq = sub.add_parser("requeue", help="把指定 ref 重新入队（同批修复后继续跑）")
    prq.add_argument("--task", required=True)
    prq.add_argument("--batch", required=True)
    prq.add_argument("--stage", default="author")
    prq.add_argument("--refs", required=True, help="逗号分隔的 ref 列表")
    prq.add_argument("--reason", default="manual_repair")

    def _do_requeue(args: argparse.Namespace) -> None:
        refs = [str(item).strip() for item in str(args.refs).split(",") if str(item).strip()]
        if not refs:
            raise SystemExit("object-queue requeue requires at least one ref")
        touched = requeue_refs(args.task, args.batch, refs, args.stage, reason=args.reason)
        _emit({"requeued": touched, "summary": queue_summary(args.task, args.batch)})

    prq.set_defaults(handler=_do_requeue)

    ps = sub.add_parser("spillover", help="把 dead job 溢出到独立修复批（不阻塞当前批）")
    ps.add_argument("--task", required=True)
    ps.add_argument("--batch", required=True)
    ps.add_argument("--target-batch", required=True)
    ps.add_argument("--stage", default=None)
    ps.set_defaults(handler=lambda a: _emit(spillover_dead(a.task, a.batch, target_batch_id=a.target_batch, stage=a.stage)))

    prv = sub.add_parser("revive-startup-dead", help="把仅因 startup failure 而 dead 的 job 恢复为 queued")
    prv.add_argument("--task", required=True)
    prv.add_argument("--batch", required=True)
    prv.add_argument("--stage", default=None)
    prv.add_argument("--refs", default=None, help="逗号分隔，仅恢复指定 ref")
    prv.set_defaults(
        handler=lambda a: _emit(
            revive_dead_startup_jobs(
                a.task,
                a.batch,
                refs=[x.strip() for x in str(a.refs or "").split(",") if x.strip()] or None,
                stage=a.stage,
            )
        )
    )

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "object_queue_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)

__all__ = [name for name in globals() if not name.startswith("__")]
