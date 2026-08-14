#!/usr/bin/env python3
"""App ContractGraph 收口原子链：静止探测 -> graph 重建 -> accept -> codegen-app。

多会话并行开发下，`codegen-contract-graph`、`accept`、`codegen-app` 之间留有
分钟级间隙时，任何并行改动都会让 lock 与 bundle/manifest 漂移，形成人肉追赶
循环。本 CLI 把三步压缩为同一次尝试内的秒级衔接，并且只在工作树静止窗口内
触发，用有限次重试对抗竞争。

安全边界：
- breaking 变更非空且未携带已审阅的批准参数时立即硬停（退出码 3），
  禁止自动批准未审阅的破坏性变更。
- accept 全程使用快照 CAS（--previous-lock-sha256 与
  --expected-current-lock-sha256），并发写入会被 cloud_contract_handoff.py
  拒绝，不会覆盖他人成果。

角色：cli。由根 Makefile `accept-app-contract-handoff-atomic` 调用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_LOCK = REPO_ROOT / "quwoquan_app/tool/cloud_codegen/contract_graph.lock.json"
HANDOFF_CLI = REPO_ROOT / "quwoquan_ops/cli/cloud_contract_handoff.py"
PREVIEW_REPORT = (
    REPO_ROOT / ".qwq_output/env/repo/runs/contract-handoff/atomic_preview.json"
)

# 静止探测范围：契约、实现与测试真相源。生成物与 App 契约包由本链自身写入，
# 必须排除，否则链条会把自己的产物误判为并行改动。
QUIESCE_SCAN_DIRS = (
    "quwoquan_service/services",
    "quwoquan_service/contracts",
    "quwoquan_app/lib",
    "quwoquan_app/test",
)
QUIESCE_EXCLUDES = ("packages/quwoquan_cloud_contracts", "/generated/", ".qwq_output")

EXIT_OK = 0
EXIT_EXHAUSTED = 2
EXIT_BREAKING_UNREVIEWED = 3


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_is_quiet(quiet_seconds: int) -> bool:
    """最近 quiet_seconds 内扫描范围中无非生成物改动。"""
    minutes = max(1, (quiet_seconds + 59) // 60)
    find_cmd = ["find"]
    find_cmd += [str(REPO_ROOT / d) for d in QUIESCE_SCAN_DIRS]
    find_cmd += ["-type", "f", "-mmin", f"-{minutes}"]
    proc = _run(find_cmd)
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        if any(marker in line for marker in QUIESCE_EXCLUDES):
            continue
        print(f"  busy: {line.strip()}")
        return False
    return True


def rebuild_graph() -> bool:
    proc = _run(["make", "-C", "quwoquan_service", "codegen-contract-graph"])
    if proc.returncode != 0:
        print("  graph rebuild failed:")
        print("  " + "\n  ".join(proc.stdout.splitlines()[-3:]))
        print("  " + "\n  ".join(proc.stderr.splitlines()[-3:]))
        return False
    return True


def preview_breaking(snapshot: Path, snapshot_sha: str) -> tuple[bool, list[dict]]:
    """生成预览报告。返回 (成功, breakingChanges)。"""
    PREVIEW_REPORT.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(
        [
            sys.executable,
            str(HANDOFF_CLI),
            "accept",
            "--previous-lock",
            str(snapshot),
            "--previous-lock-sha256",
            snapshot_sha,
            "--preview-report",
            str(PREVIEW_REPORT),
        ]
    )
    if proc.returncode != 0 or not PREVIEW_REPORT.exists():
        print("  preview failed:")
        print("  " + "\n  ".join((proc.stdout + proc.stderr).splitlines()[-3:]))
        return False, []
    report = json.loads(PREVIEW_REPORT.read_text(encoding="utf-8"))
    return True, list(report.get("breakingChanges", []))


def accept_lock(
    snapshot: Path,
    snapshot_sha: str,
    approve_report: str | None,
    approve_report_sha: str | None,
) -> bool:
    cmd = [
        sys.executable,
        str(HANDOFF_CLI),
        "accept",
        "--previous-lock",
        str(snapshot),
        "--previous-lock-sha256",
        snapshot_sha,
        "--expected-current-lock-sha256",
        snapshot_sha,
    ]
    if approve_report:
        cmd += ["--approve-breaking-report", approve_report]
    if approve_report_sha:
        cmd += ["--approve-breaking-report-sha256", approve_report_sha]
    proc = _run(cmd)
    if proc.returncode != 0:
        print("  accept failed:")
        print("  " + "\n  ".join((proc.stdout + proc.stderr).splitlines()[-3:]))
        return False
    print("  " + (proc.stdout.strip().splitlines() or ["accepted"])[-1])
    return True


def codegen_app() -> bool:
    proc = _run(["make", "-C", "quwoquan_service", "codegen-app"])
    if proc.returncode != 0:
        print("  codegen-app failed:")
        print("  " + "\n  ".join((proc.stdout + proc.stderr).splitlines()[-3:]))
        return False
    return True


def verify_lock() -> bool:
    proc = _run([sys.executable, str(HANDOFF_CLI), "verify"])
    print("  " + (proc.stdout.strip().splitlines() or [""])[-1])
    return proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # 默认值按仓库多会话并行的真实繁忙度校准：60 秒静止窗口已足够安全
    # （accept 的快照 CAS 兜底真正的并发冲突），180 秒在繁忙期几乎等不到。
    parser.add_argument("--max-attempts", type=int, default=40)
    parser.add_argument(
        "--quiet-seconds",
        type=int,
        default=60,
        help="触发前要求的工作树静止秒数（按分钟粒度向上取整）",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument(
        "--skip-quiesce",
        action="store_true",
        help="跳过静止探测立即执行一次（已知无并行写入时使用）",
    )
    parser.add_argument(
        "--approve-breaking-report",
        help="已人工审阅的 blocked report 路径（透传给 accept）",
    )
    parser.add_argument(
        "--approve-breaking-report-sha256",
        help="已人工审阅的 blocked report SHA256（透传给 accept）",
    )
    args = parser.parse_args()

    if not CANONICAL_LOCK.exists():
        print(f"FAIL: canonical lock not found: {CANONICAL_LOCK}")
        return EXIT_EXHAUSTED

    tmp_dir = Path(tempfile.mkdtemp(prefix="qwq-handoff-atomic-"))
    snapshot = tmp_dir / "previous_lock_snapshot.json"
    try:
        for attempt in range(1, args.max_attempts + 1):
            print(f"[attempt {attempt}/{args.max_attempts}]")
            if not args.skip_quiesce and not tree_is_quiet(args.quiet_seconds):
                time.sleep(args.poll_seconds)
                continue

            if not rebuild_graph():
                time.sleep(args.poll_seconds)
                continue

            shutil.copyfile(CANONICAL_LOCK, snapshot)
            snapshot_sha = _sha256(snapshot)

            ok, breaking = preview_breaking(snapshot, snapshot_sha)
            if not ok:
                time.sleep(args.poll_seconds)
                continue
            if breaking and not args.approve_breaking_report:
                print("FAIL: 存在未审阅的 breaking 变更，拒绝自动批准：")
                for change in breaking:
                    print(f"  - {json.dumps(change, ensure_ascii=False)}")
                print(
                    "人工审阅后使用 --approve-breaking-report/"
                    "--approve-breaking-report-sha256 重跑。"
                )
                return EXIT_BREAKING_UNREVIEWED

            if not accept_lock(
                snapshot,
                snapshot_sha,
                args.approve_breaking_report,
                args.approve_breaking_report_sha256,
            ):
                time.sleep(args.poll_seconds)
                continue

            if not codegen_app():
                # accept 已落地但 codegen-app 被并行插入打断：下一轮重试会
                # 以新 lock 为基线重新收口，无需回滚。
                time.sleep(args.poll_seconds)
                continue

            if not verify_lock():
                time.sleep(args.poll_seconds)
                continue

            print("PASS: atomic contract handoff chain completed")
            return EXIT_OK

        print("FAIL: attempts exhausted; tree never quiet or chain kept losing races")
        return EXIT_EXHAUSTED
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
