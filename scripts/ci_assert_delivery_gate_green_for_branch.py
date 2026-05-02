#!/usr/bin/env python3
"""
断言指定分支最近一次 push 对应的「03. Delivery Gate」workflow（delivery-gate.yml）已成功完成。

用法（CI/GitHub Actions）：
  GITHUB_REPOSITORY=owner/repo GITHUB_TOKEN=... \\
    python3 scripts/ci_assert_delivery_gate_green_for_branch.py dev1.0

额外说明：必须通过 job 的 head_sha 与分支当前 HEAD 一致，才会判定为绿灯（防止尚未触发 DG 的旧 run 误判）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _request(
    url: str,
    token: str,
    *,
    accept: str = "application/vnd.github+json",
) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_branch_head_sha(owner: str, repo: str, branch: str, token: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    data = _request(url, token)
    sha = data.get("sha")
    if not sha or not isinstance(sha, str):
        raise ValueError(f"commits/{branch} 返回无 sha")
    return sha


def fetch_workflow_runs(
    owner: str,
    repo: str,
    workflow_file: str,
    branch: str,
    token: str,
    per_page: int = 30,
) -> list[dict]:
    q = f"per_page={per_page}&branch={branch}"
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/"
        f"{workflow_file}/runs?{q}"
    )
    data = _request(url, token)
    return data.get("workflow_runs", []) or []


def pick_run_for_head_sha(runs: list[dict], head_sha: str) -> dict | None:
    """API 默认按更新时间倒序；筛出与本分支 HEAD commit 一致的 run。"""
    for r in runs:
        if r.get("head_sha") == head_sha:
            return r
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("branch", help="例如 dev1.0")
    p.add_argument(
        "--workflow-file",
        default="delivery-gate.yml",
        help="Workflow 文件路径（仓库内）",
    )
    p.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="若最新 run 仍在排队/运行，则轮询等待的总秒数（0=不等待，仅断言当前状态）",
    )
    p.add_argument(
        "--poll-interval",
        type=int,
        default=20,
        help="等待时轮询间隔秒数",
    )
    args = p.parse_args()

    repo_full = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo_full or not token:
        print(
            "FAIL: 需要环境变量 GITHUB_REPOSITORY 与 GITHUB_TOKEN（或 GH_TOKEN）。",
            file=sys.stderr,
        )
        return 2

    owner, repo = repo_full.split("/", 1)

    deadline = time.monotonic() + max(0, args.wait_seconds)
    last_err = ""

    while True:
        try:
            head_sha_full = fetch_branch_head_sha(owner, repo, args.branch, token)
        except Exception as exc:  # noqa: BLE001 — 控制台脚本
            print(f"FAIL: 无法解析分支 {args.branch} 的 HEAD: {exc}", file=sys.stderr)
            return 1

        runs = fetch_workflow_runs(
            owner, repo, args.workflow_file, args.branch, token
        )
        latest = pick_run_for_head_sha(runs, head_sha_full)
        if latest is None:
            last_err = (
                f"分支 {args.branch} 当前 HEAD {head_sha_full[:7]} 尚无对应 "
                f"{args.workflow_file} 的 workflow run（或尚未出现在 API 分页内）。"
            )
            if time.monotonic() < deadline:
                print(f"WAIT: {last_err}")
                time.sleep(args.poll_interval)
                continue
            print(f"FAIL: {last_err}", file=sys.stderr)
            return 1

        status = latest.get("status")
        conclusion = latest.get("conclusion")
        run_id = latest.get("id")
        head_sha = (latest.get("head_sha") or "")[:7]
        event = latest.get("event")

        if status != "completed":
            last_err = (
                f"Delivery Gate run {run_id} 尚未结束: status={status} "
                f"(sha={head_sha} event={event})"
            )
            if time.monotonic() < deadline:
                print(f"WAIT: {last_err}")
                time.sleep(args.poll_interval)
                continue
            print(f"FAIL: {last_err}", file=sys.stderr)
            return 1

        if conclusion != "success":
            html_url = latest.get("html_url", "")
            print(
                f"FAIL: Delivery Gate 未通过: conclusion={conclusion} "
                f"run_id={run_id} sha={head_sha} url={html_url}",
                file=sys.stderr,
            )
            return 1

        print(
            f"OK: Delivery Gate 已成功: run_id={run_id} conclusion={conclusion} "
            f"sha={head_sha} event={event}"
        )
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"FAIL: HTTP {e.code}: {body[:500]}", file=sys.stderr)
        raise SystemExit(1)
