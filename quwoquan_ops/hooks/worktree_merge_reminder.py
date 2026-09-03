#!/usr/bin/env python3
"""Observe-only worktree reminder with a lightweight post-commit dirty marker.

`post-commit` only runs ``--mode mark-due``: it atomically records that the next
supported session must check, without loading policy/inventory or invoking git.
Cursor/Codex session-start handlers run the bounded full scan only when the
marker or the persisted ``nextAt`` says it is due. Every path is fail-open.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

_CACHE_RELATIVE = Path("env/repo/local/worktree-governance/cache")
_STATE_NAME = "last-reminder.json"
_DUE_NAME = "reminder-due.json"
_STATUS_NAME = "last-scan-status.json"
_SCAN_BUDGET_SECONDS = 20.0
_SCAN_GRACE_SECONDS = 0.5


class _FailOpenParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


@dataclass(frozen=True)
class ScanAttempt:
    payload: dict[str, object] | None
    error: str
    timed_out: bool
    elapsed_ms: int


def _output_root() -> Path:
    return Path(os.environ.get("QWQ_OUTPUT_ROOT", str(ROOT / ".qwq_output")))


def _cache_path(name: str) -> Path:
    return _output_root() / _CACHE_RELATIVE / name


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def load_state() -> dict[str, object]:
    try:
        payload = json.loads(_cache_path(_STATE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def mark_due(*, now: int | None = None) -> None:
    """Atomically dirty the reminder; deliberately does no policy/inventory/git work."""
    moment = int(time.time()) if now is None else now
    _write_json(
        _cache_path(_DUE_NAME),
        {"schemaVersion": 1, "dueAt": moment, "reason": "post-commit"},
    )


def scan_is_due(*, now: int | None = None) -> bool:
    if _cache_path(_DUE_NAME).is_file():
        return True
    next_at = load_state().get("nextAt")
    moment = int(time.time()) if now is None else now
    return not isinstance(next_at, int) or isinstance(next_at, bool) or moment >= next_at


def save_state(*, at: int, overdue_paths: list[str], next_at: int) -> None:
    _write_json(
        _cache_path(_STATE_NAME),
        {"at": at, "nextAt": next_at, "overduePaths": sorted(overdue_paths)},
    )


def _due_token() -> tuple[int, int, int] | None:
    try:
        stat = _cache_path(_DUE_NAME).stat()
    except OSError:
        return None
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def _clear_due_if_unchanged(token: tuple[int, int, int] | None) -> None:
    """Do not erase a post-commit marker atomically replaced during this scan."""
    if token is None or _due_token() != token:
        return
    try:
        _cache_path(_DUE_NAME).unlink()
    except FileNotFoundError:
        pass


def _save_scan_status(
    *, outcome: str, elapsed_ms: int, last_error: str, budget_seconds: float
) -> None:
    try:
        _write_json(
            _cache_path(_STATUS_NAME),
            {
                "schemaVersion": 1,
                "at": int(time.time()),
                "outcome": outcome,
                "elapsedMs": elapsed_ms,
                "budgetMs": int(budget_seconds * 1000),
                "lastError": last_error,
            },
        )
    except OSError:
        pass


def build_message(summary: dict[str, object], *, hooks_ok: bool, policy) -> str:
    lines: list[str] = []
    if not hooks_ok:
        lines.append(
            f"  ! {policy.failure_code('hooks_not_installed')}  "
            "git hooks 未安装，本仓库的提交与推送门禁当前全部失效"
        )
        lines.append(f"    修复：{policy.install_command}")

    identities = summary.get("identities")
    identity_rows = identities if isinstance(identities, list) else []
    for identity in identity_rows:
        drift = identity.get("ownershipDrift")
        drift_rows = drift if isinstance(drift, list) else []
        lines.append(
            f"  - identity={identity.get('branch') or '<detached>'}  "
            f"path={identity.get('path')}  ahead={identity.get('ahead')} "
            f"behind={identity.get('behind')} dirty={identity.get('dirty')} "
            f"工程面漂移={len(drift_rows)}"
        )
        if drift_rows:
            lines.append(
                "    OWNERSHIP_DRIFT: "
                + ", ".join(str(item) for item in drift_rows[:5])
                + (" ..." if len(drift_rows) > 5 else "")
            )

    items = summary.get("items")
    rows = items if isinstance(items, list) else []
    for item in rows:
        marker = "  !" if item.get("overdue") else "  -"
        code = f"{policy.failure_code('unmerged_overdue')}  " if item.get("overdue") else ""
        lines.append(
            f"{marker} {code}{item.get('path')}  滞留 {item.get('staleDays')} 天  "
            f"ahead={item.get('ahead')} behind={item.get('behind')} "
            f"dirty={item.get('dirty')} stash={item.get('stashes')}"
        )
        if item.get("probeError"):
            lines.append(f"    探测失败：{item.get('probeError')}")

    if not lines:
        return ""
    tail = (
        [
            "  处置：长期 lane 在 integration/abort 后 fast-forward resync 到 canonical dev1.0，",
            "  并保留 worktree 供下轮复用；",
            "  clone 或额外废弃副本是否删除仍由人工决定。",
        ]
        if rows
        else []
    )
    return "\n".join(["[worktree] 会话身份与本地工作副本提醒", *lines, *tail])


def collect(policy) -> tuple[dict[str, object], bool, list[str]]:
    import local_worktree_inventory as inventory

    copies = inventory.discover_work_copies(policy=policy)
    summary = inventory.summarize(copies, policy)
    hooks_ok = inventory.hooks_installed(policy=policy)
    items = summary.get("items")
    rows = items if isinstance(items, list) else []
    overdue = [str(row.get("path")) for row in rows if row.get("overdue")]
    return summary, hooks_ok, overdue


def _scan_worker() -> int:
    try:
        import local_worktree_inventory as inventory

        policy = inventory.load_policy()
        summary, hooks_ok, overdue = collect(policy)
        payload: dict[str, object] = {
            "ok": True,
            "message": build_message(summary, hooks_ok=hooks_ok, policy=policy),
            "overduePaths": overdue,
            "intervalHours": policy.reminder_min_interval_hours,
        }
    except Exception as exc:  # noqa: BLE001 - worker failure is data for fail-open parent
        payload = {"ok": False, "error": str(exc)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _run_bounded_scan(*, budget_seconds: float = _SCAN_BUDGET_SECONDS) -> ScanAttempt:
    started = time.monotonic()
    result_path = _cache_path(f".scan-deadline-{os.getpid()}-{time.time_ns()}.json")
    deadline = time.time() + budget_seconds
    command = [
        sys.executable,
        str(ROOT / "quwoquan_ops/gate/lib/process_group_deadline.py"),
        "--deadline-epoch-seconds",
        str(deadline),
        "--grace-seconds",
        str(_SCAN_GRACE_SECONDS),
        "--result-json",
        str(result_path),
        "--",
        sys.executable,
        str(Path(__file__).resolve()),
        "--mode",
        "scan-worker",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        metadata: dict[str, object] = {}
        try:
            value = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                metadata = value
        except (OSError, ValueError):
            pass
        timed_out = completed.returncode == 124 or metadata.get("timedOut") is True
        if timed_out:
            return ScanAttempt(None, "full inventory scan exceeded wall-clock budget", True, elapsed_ms)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"scan worker exited {completed.returncode}"
            return ScanAttempt(None, detail, False, elapsed_ms)
        try:
            payload = json.loads(completed.stdout or "{}")
        except ValueError as exc:
            return ScanAttempt(None, f"scan worker returned invalid JSON: {exc}", False, elapsed_ms)
        if not isinstance(payload, dict):
            return ScanAttempt(None, "scan worker returned non-object JSON", False, elapsed_ms)
        if payload.get("ok") is not True:
            return ScanAttempt(None, str(payload.get("error") or "scan failed"), False, elapsed_ms)
        return ScanAttempt(payload, "", False, elapsed_ms)
    except (OSError, subprocess.SubprocessError) as exc:
        return ScanAttempt(None, str(exc), False, int((time.monotonic() - started) * 1000))
    finally:
        try:
            result_path.unlink()
        except FileNotFoundError:
            pass


def _emit(harness: str, message: str) -> None:
    if harness == "codex":
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}},
                ensure_ascii=False,
            )
        )
    elif harness == "cursor":
        print(json.dumps({"additional_context": message}, ensure_ascii=False))
    else:
        print(message)


def _run_session(harness: str) -> int:
    if not scan_is_due():
        return 0
    due_token = _due_token()
    attempt = _run_bounded_scan()
    if attempt.payload is None:
        outcome = "timeout" if attempt.timed_out else "error"
        _save_scan_status(
            outcome=outcome,
            elapsed_ms=attempt.elapsed_ms,
            last_error=attempt.error,
            budget_seconds=_SCAN_BUDGET_SECONDS,
        )
        _emit(harness, f"[worktree] 提醒扫描未生效（{outcome}）：{attempt.error}；本次会话未被阻断。")
        return 0

    payload = attempt.payload
    overdue = payload.get("overduePaths")
    interval = payload.get("intervalHours")
    if (
        not isinstance(overdue, list)
        or any(not isinstance(item, str) for item in overdue)
        or not isinstance(interval, int)
        or isinstance(interval, bool)
        or interval <= 0
    ):
        error = "scan worker result shape is invalid"
        _save_scan_status(
            outcome="error",
            elapsed_ms=attempt.elapsed_ms,
            last_error=error,
            budget_seconds=_SCAN_BUDGET_SECONDS,
        )
        _emit(harness, f"[worktree] 提醒扫描未生效（error）：{error}；本次会话未被阻断。")
        return 0

    now = int(time.time())
    try:
        save_state(at=now, overdue_paths=overdue, next_at=now + interval * 3600)
        _clear_due_if_unchanged(due_token)
    except OSError as exc:
        error = f"reminder state update failed: {exc}"
        _save_scan_status(
            outcome="error",
            elapsed_ms=attempt.elapsed_ms,
            last_error=error,
            budget_seconds=_SCAN_BUDGET_SECONDS,
        )
        _emit(harness, f"[worktree] 提醒扫描未生效（error）：{error}；本次会话未被阻断。")
        return 0

    _save_scan_status(
        outcome="success",
        elapsed_ms=attempt.elapsed_ms,
        last_error="",
        budget_seconds=_SCAN_BUDGET_SECONDS,
    )
    message = payload.get("message")
    if isinstance(message, str) and message:
        _emit(harness, message)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _FailOpenParser(description=__doc__)
    parser.add_argument("--harness", choices=("git", "cursor", "codex"), default="git")
    parser.add_argument("--reason", choices=("commit", "session"), default="session")
    parser.add_argument("--mode", choices=("scan", "mark-due", "scan-worker"), default="scan")
    try:
        args = parser.parse_args(argv)
        if args.mode == "scan-worker":
            return _scan_worker()
        if args.mode == "mark-due":
            try:
                mark_due()
            except OSError as exc:
                _emit(args.harness, f"[worktree] 未能标记下次会话检查：{exc}；提交未被阻断。")
            return 0
        return _run_session(args.harness)
    except (ValueError, SystemExit) as exc:
        code = getattr(exc, "code", 1)
        if code != 0:
            print(f"[worktree] hook 参数无效：{exc}；本次操作未被阻断。", file=sys.stderr)
        return 0
    except Exception as exc:  # noqa: BLE001 - observe-only hook is always fail-open
        print(f"[worktree] hook 失败：{exc}；本次操作未被阻断。", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
