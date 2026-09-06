#!/usr/bin/env python3
"""Plan, run, inspect, work, and verify local readiness receipts."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.evidence_fingerprint import normalize_repo_relative_path  # noqa: E402
from lib.local_readiness import (  # noqa: E402
    LocalReadinessError,
    inspect_state,
    plan_readiness,
    run_readiness,
    verify_receipt,
    worker_once,
)
from lib.local_readiness.core import enqueue_paths, parse_push_updates, push_paths, staged_paths, workspace_paths  # noqa: E402


def _json(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _updates(path: str) -> list[dict[str, str]]:
    if not path:
        return []
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    updates = parse_push_updates(text)
    if not updates:
        raise LocalReadinessError("push updates 为空或格式非法")
    return updates


def _inputs(args: argparse.Namespace) -> tuple[list[str], str, list[dict[str, str]]]:
    updates = _updates(getattr(args, "push_updates", ""))
    if updates:
        paths = push_paths(ROOT, updates)
        if not paths:
            raise LocalReadinessError("push updates 无可验证 changed paths，拒绝空范围 readiness")
        return paths, "push", updates
    if getattr(args, "staged", False):
        paths = staged_paths(ROOT)
        if not paths:
            raise LocalReadinessError("staged 范围为空")
        return paths, "staged", []
    explicit = list(getattr(args, "path", []) or [])
    if getattr(args, "commit", False):
        paths = explicit or push_paths(
            ROOT,
            parse_push_updates(
                f"refs/heads/dev1.0 {subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()} refs/heads/dev1.0 {'0' * 40}\n"
            ),
        )
        if not paths:
            raise LocalReadinessError("commit 范围为空")
        return paths, "commit", []
    paths = explicit or workspace_paths(ROOT)
    if not paths:
        raise LocalReadinessError("workspace 范围为空")
    return paths, "workspace", []


def _optional_path(value: str) -> Path | None:
    return Path(value) if value else None


def _owner(args: argparse.Namespace) -> Path | None:
    if getattr(args, "owner_manifest", ""):
        raise LocalReadinessError("IDENTITY.MIGRATION_REQUIRED: --owner-manifest 已退役")
    return _optional_path(getattr(args, "owner_identity", ""))


def _candidate(args: argparse.Namespace) -> Path | None:
    return _optional_path(getattr(args, "candidate_evidence", ""))


def _review(args: argparse.Namespace) -> tuple[Path | None, list[Path]]:
    consolidation = getattr(args, "review_consolidation", "") or os.environ.get("QWQ_LOCAL_READINESS_REVIEW_CONSOLIDATION", "")
    raw_evidence = list(getattr(args, "required_evidence", []) or [])
    if not raw_evidence:
        raw_evidence = [item for item in os.environ.get("QWQ_LOCAL_READINESS_REQUIRED_EVIDENCE", "").split(os.pathsep) if item]
    return _optional_path(consolidation), [Path(item) for item in raw_evidence]


def _build(level: str, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, str]], Path | None, list[Path]]:
    paths, mode, updates = _inputs(args)
    consolidation, evidence = _review(args)
    return (
        plan_readiness(
            level=level,
            paths=paths,
            mode=mode,
            owner_manifest=_owner(args),
            candidate_evidence=_candidate(args),
            push_updates=updates,
            review_consolidation=consolidation,
            required_evidence=evidence,
        ),
        updates,
        consolidation,
        evidence,
    )


def command_plan(args: argparse.Namespace) -> int:
    plan, _updates_value, _consolidation, _evidence = _build(args.level, args)
    _json(plan)
    return 0


def command_run(args: argparse.Namespace) -> int:
    updates = _updates(args.push_updates)
    consolidation, evidence = _review(args)
    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    else:
        plan, updates, consolidation, evidence = _build(args.level, args)
    receipt = run_readiness(
        plan,
        owner_manifest=_owner(args),
        candidate_evidence=_candidate(args),
        push_updates=updates,
        review_consolidation=consolidation,
        required_evidence=evidence,
    )
    _json(receipt)
    return 0 if receipt["status"] == "PASS" else 1


def command_enqueue(args: argparse.Namespace) -> int:
    paths = list(args.path or [])
    if not paths:
        raise LocalReadinessError("explicit enqueue 路径为空")
    _json(enqueue_paths(paths, reason=args.reason))
    return 0


def command_produce(args: argparse.Namespace) -> int:
    plan, updates, consolidation, evidence = _build(args.command, args)
    receipt = run_readiness(
        plan,
        owner_manifest=_owner(args),
        candidate_evidence=_candidate(args),
        push_updates=updates,
        review_consolidation=consolidation,
        required_evidence=evidence,
    )
    _json(receipt)
    return 0 if receipt["status"] == "PASS" else 1


def command_verify(args: argparse.Namespace) -> int:
    paths, mode, updates = _inputs(args)
    receipt = verify_receipt(
        level=args.level,
        paths=paths,
        mode=mode,
        owner_manifest=_owner(args),
        candidate_evidence=_candidate(args),
        push_updates=updates,
        receipt_path=Path(args.receipt) if args.receipt else None,
    )
    _json({"status": "PASS", "facts": receipt["facts"], "fingerprint": receipt["fingerprint"]["ref"]})
    return 0


def _managed_pytest_runtime() -> Path:
    candidates = [
        Path(sys.executable),
        Path(os.environ.get("QWQ_PYTHON_CACHE_ROOT", str(Path.home() / ".cache/quwoquan/python-envs"))) / "quwoquan-data/bin/python3",
        Path(os.environ.get("QWQ_PYTHON_CACHE_ROOT", str(Path.home() / ".cache/quwoquan/python-envs"))) / "quwoquan-data/bin/python",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        proc = subprocess.run([str(candidate), "-c", "import pytest"], cwd=ROOT, capture_output=True, check=False)
        if proc.returncode == 0:
            return candidate
    raise LocalReadinessError("未找到仓库受管且包含 pytest 的 Python runtime")


def command_managed_pytest(args: argparse.Namespace) -> int:
    if not args.test_path:
        raise LocalReadinessError("managed-pytest 不接受空测试集合")
    paths = [normalize_repo_relative_path(path, ROOT) for path in args.test_path]
    for path in paths:
        if not path.startswith(("quwoquan_ops/tests/", "quwoquan_data/tests/", "quwoquan_app/test/")):
            raise LocalReadinessError(f"managed-pytest path 非受管测试路径: {path}")
    runtime = _managed_pytest_runtime()
    cache = ROOT / ".qwq_output/env/repo/local/tests/cache/pytest-local-readiness"
    proc = subprocess.run([str(runtime), "-B", "-m", "pytest", "-q", "-o", f"cache_dir={cache}", *paths], cwd=ROOT, check=False)
    return proc.returncode


_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9/+_.-]{24,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
)
_PII_PATTERNS = (
    # 手机号两侧排除十六进制字符：sha256/digest 里任意 11 位数字子串（如 "18916601719eac…"）
    # 不是号码；否则 contract_graph.json 这类生成物每次刷新都会被误判为直接 PII。
    re.compile(rb"(?<![0-9A-Fa-f])1[3-9][0-9]{9}(?![0-9A-Fa-f])"),
    # 邮箱域名不能把静态资源的 @2x.png / @3x.png 像素密度后缀当成邮箱。
    re.compile(rb"[A-Za-z0-9._%+-]+@(?=[A-Za-z])[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)


def _cleanup_portal_outputs(portal: Path) -> None:
    import shutil

    for relative in ("dist", ".test-dist"):
        candidate = portal / relative
        if candidate.is_dir():
            shutil.rmtree(candidate)
    for candidate in portal.glob("*.tsbuildinfo"):
        candidate.unlink(missing_ok=True)
    for name in ("vite.config.js", "vite.config.d.ts"):
        (portal / name).unlink(missing_ok=True)


def command_managed_portal_test(_args: argparse.Namespace) -> int:
    portal = ROOT / "quwoquan_ops/portal"
    try:
        return subprocess.run(["npm", "--prefix", str(portal), "test"], cwd=ROOT, check=False).returncode
    finally:
        _cleanup_portal_outputs(portal)


def command_managed_portal_build(_args: argparse.Namespace) -> int:
    portal = ROOT / "quwoquan_ops/portal"
    try:
        with tempfile.TemporaryDirectory(prefix="qwq-local-readiness-portal-") as directory:
            env = os.environ.copy()
            env.update({"QWQ_DEPLOY_WORK_ROOT": directory, "QWQ_DEPLOY_TARGET": "prod-hosted"})
            return subprocess.run(["npm", "--prefix", str(portal), "run", "build"], cwd=ROOT, env=env, check=False).returncode
    finally:
        _cleanup_portal_outputs(portal)


def _staged_governance(paths: list[str]) -> None:
    generated_markers = ("/generated/", ".generated.", ".g.dart", ".g.go")
    generated = [path for path in paths if any(marker in path for marker in generated_markers)]
    if generated:
        authoring = [path for path in paths if "/generated/" not in path and not path.endswith((".g.dart", ".g.go"))]
        if not authoring:
            raise LocalReadinessError("staged generated boundary rejects generated-only changes")


def _unstaged_paths(repo_root: Path, staged: list[str]) -> set[str]:
    output = subprocess.run(
        [
            "git", "diff", "--name-status", "-z", "--find-renames",
            "--diff-filter=ACDMRTUXB",
        ],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if output.returncode != 0:
        raise LocalReadinessError(
            output.stderr.decode("utf-8", errors="replace").strip()
            or "无法读取 unstaged path 集合"
        )
    from lib.local_readiness.core import _parse_name_status_z

    paths: set[str] = set()
    for entry in _parse_name_status_z(output.stdout, repo_root):
        paths.add(str(entry["source"]))
        if entry["destination"]:
            paths.add(str(entry["destination"]))
    if staged:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", *staged],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if untracked.returncode != 0:
            raise LocalReadinessError(
                untracked.stderr.decode("utf-8", errors="replace").strip()
                or "无法读取 staged path 的 untracked overlap"
            )
        paths.update(
            normalize_repo_relative_path(raw.decode("utf-8"), repo_root)
            for raw in untracked.stdout.split(b"\0")
            if raw
        )
    return paths


def _assert_no_staged_unstaged_overlap(paths: list[str]) -> None:
    overlap = sorted(set(paths) & _unstaged_paths(ROOT, paths))
    if overlap:
        raise LocalReadinessError(
            "LOCAL_READINESS.STAGED_UNSTAGED_OVERLAP: staged path 仍有 unstaged "
            "bytes，提交边界不代表当前 worktree 已覆盖：" + ", ".join(overlap)
        )


def command_staged_boundary(_args: argparse.Namespace) -> int:
    paths = staged_paths(ROOT)
    if not paths:
        raise LocalReadinessError("staged boundary 范围为空")
    _assert_no_staged_unstaged_overlap(paths)
    _staged_governance(paths)
    branch = subprocess.run(
        [
            sys.executable,
            "-B",
            "quwoquan_ops/gate/verify_git_branch_policy.py",
            "--local-commit",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if branch.returncode != 0:
        raise LocalReadinessError("staged branch policy failed")
    for path in paths:
        blob = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True, check=False)
        if blob.returncode != 0:  # deleted/rename source has no index blob
            continue
        if any(pattern.search(blob.stdout) for pattern in _SECRET_PATTERNS):
            raise LocalReadinessError(f"staged secret material detected: {path}")
        pii_matches = [match.group(0).decode("utf-8", errors="replace") for pattern in _PII_PATTERNS for match in pattern.finditer(blob.stdout)]
        pii_matches = [value for value in pii_matches if not value.lower().endswith(("@example.invalid", "@example.com", "@example.org"))]
        if pii_matches:
            raise LocalReadinessError(f"staged direct PII detected: {path}")
    return 0


def _common(parser: argparse.ArgumentParser, *, allow_plan: bool = False) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--staged", action="store_true")
    modes.add_argument("--commit", action="store_true")
    modes.add_argument("--push-updates", default="")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--owner-identity", default="")
    parser.add_argument("--candidate-evidence", default="")
    parser.add_argument("--owner-manifest", default="", help=argparse.SUPPRESS)
    parser.add_argument("--review-consolidation", default="")
    parser.add_argument("--required-evidence", action="append", default=[])
    if allow_plan:
        parser.add_argument("--plan", default="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, prog="local-readiness")
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan")
    plan.add_argument("--level", choices=("fast", "scope", "release"), required=True)
    _common(plan)
    plan.set_defaults(handler=command_plan)

    run = commands.add_parser("run")
    run.add_argument("--level", choices=("fast", "scope", "release"), required=True)
    _common(run, allow_plan=True)
    run.set_defaults(handler=command_run)

    for name in ("fast", "scope", "release"):
        produce = commands.add_parser(name)
        _common(produce)
        produce.set_defaults(handler=command_produce)

    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("--path", action="append", required=True)
    enqueue.add_argument("--reason", default="explicit_cli")
    enqueue.set_defaults(handler=command_enqueue)

    inspect = commands.add_parser("inspect")
    inspect.set_defaults(handler=lambda _args: (_json(inspect_state()) or 0))

    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true", required=True)
    worker.add_argument("--debounce-seconds", type=float, default=None)
    worker.set_defaults(handler=lambda args: (_json(result := worker_once(debounce_seconds=args.debounce_seconds)) or (0 if result["status"] in {"PASS", "IDLE", "BACKING_OFF"} else 1)))

    verify = commands.add_parser("verify")
    verify.add_argument("--level", choices=("fast", "scope", "release"), required=True)
    verify.add_argument("--receipt", default="")
    _common(verify)
    verify.set_defaults(handler=command_verify)

    managed = commands.add_parser("managed-pytest", help=argparse.SUPPRESS)
    managed.add_argument("test_path", nargs="+")
    managed.set_defaults(handler=command_managed_pytest)

    portal_test = commands.add_parser("managed-portal-test", help=argparse.SUPPRESS)
    portal_test.set_defaults(handler=command_managed_portal_test)

    portal_build = commands.add_parser("managed-portal-build", help=argparse.SUPPRESS)
    portal_build.set_defaults(handler=command_managed_portal_build)

    boundary = commands.add_parser("staged-boundary", help=argparse.SUPPRESS)
    boundary.set_defaults(handler=command_staged_boundary)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (LocalReadinessError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"local-readiness: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
