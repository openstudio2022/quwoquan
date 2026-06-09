"""task batch queue / worker pool。"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.paths import RUNTIME_ROOT
from task import run as task_run
from task import store

QUEUE_ROOT = RUNTIME_ROOT / "task_queue"
READY_DIR = QUEUE_ROOT / "ready"
RUNNING_DIR = QUEUE_ROOT / "running"
DONE_DIR = QUEUE_ROOT / "done"
DEAD_DIR = QUEUE_ROOT / "dead"


def _dirs() -> None:
    for path in (READY_DIR, RUNNING_DIR, DONE_DIR, DEAD_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _job_path(job_id: str, state_dir: Path | None = None) -> Path:
    safe = job_id.replace("/", "__")
    return (state_dir or READY_DIR) / f"{safe}.json"


def enqueue(task_id: str, *, batch_id: str, until: str | None = None, max_attempts: int = 2) -> Path:
    _dirs()
    job_id = f"{task_id}::{batch_id}"
    payload = {
        "schemaVersion": "quwoquan.task_queue_job.v1",
        "jobId": job_id,
        "taskId": task_id,
        "batchId": batch_id,
        "until": until or "",
        "attempts": 0,
        "maxAttempts": max_attempts,
        "createdAt": store.now_iso(),
        "updatedAt": store.now_iso(),
    }
    path = _job_path(job_id)
    write_json(path, payload)
    return path


def list_jobs() -> dict[str, list[str]]:
    _dirs()
    return {
        "ready": sorted(p.stem for p in READY_DIR.glob("*.json")),
        "running": sorted(p.stem for p in RUNNING_DIR.glob("*.json")),
        "done": sorted(p.stem for p in DONE_DIR.glob("*.json")),
        "dead": sorted(p.stem for p in DEAD_DIR.glob("*.json")),
    }


def _move(path: Path, target_dir: Path, payload: dict[str, Any]) -> Path:
    target = target_dir / path.name
    payload["updatedAt"] = store.now_iso()
    write_json(target, payload)
    path.unlink(missing_ok=True)
    return target


def _run_one(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    running_path = _move(path, RUNNING_DIR, payload)
    payload["attempts"] = int(payload.get("attempts") or 0) + 1
    try:
        ns = argparse.Namespace(
            task=payload["taskId"],
            batch=payload["batchId"],
            resume=True,
            until=payload.get("until") or None,
            dry_run=False,
        )
        task_run.handle_run(ns)
    except Exception as exc:
        payload["lastError"] = str(exc)
        if payload["attempts"] >= int(payload.get("maxAttempts") or 1):
            _move(running_path, DEAD_DIR, payload)
            return {"jobId": payload["jobId"], "status": "dead", "error": str(exc)}
        _move(running_path, READY_DIR, payload)
        return {"jobId": payload["jobId"], "status": "retry", "error": str(exc)}
    _move(running_path, DONE_DIR, payload)
    return {"jobId": payload["jobId"], "status": "done"}


def run_workers(*, concurrency: int = 2, limit: int | None = None) -> list[dict[str, Any]]:
    _dirs()
    jobs = sorted(READY_DIR.glob("*.json"))
    if limit is not None:
        jobs = jobs[:limit]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(concurrency, 1)) as pool:
        for result in pool.map(_run_one, jobs):
            results.append(result)
    return results


def register_queue_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("queue", help="任务 batch queue / worker pool")
    sub = p.add_subparsers(dest="queue_command")

    pe = sub.add_parser("enqueue", help="入队一个 task run job")
    pe.add_argument("task_id")
    pe.add_argument("--batch", dest="batch_id", required=True)
    pe.add_argument("--until")
    pe.add_argument("--max-attempts", type=int, default=2)
    pe.set_defaults(handler=lambda args: print(f"[task queue] enqueued {enqueue(args.task_id, batch_id=args.batch_id, until=args.until, max_attempts=args.max_attempts)}"))

    pl = sub.add_parser("list", help="列出队列状态")
    pl.set_defaults(handler=lambda _args: print(json.dumps(list_jobs(), ensure_ascii=False, indent=2)))

    pw = sub.add_parser("work", help="启动本地 worker pool")
    pw.add_argument("--concurrency", type=int, default=2)
    pw.add_argument("--limit", type=int)
    pw.set_defaults(handler=lambda args: print(json.dumps(run_workers(concurrency=args.concurrency, limit=args.limit), ensure_ascii=False, indent=2)))

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "queue_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
