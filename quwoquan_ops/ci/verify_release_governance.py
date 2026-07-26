#!/usr/bin/env python3
"""在 GitHub 套餐保护不可用时，仍阻断未评审提交进入生产执行面。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _api_get(repository: str, path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as error:
        raise RuntimeError(f"GitHub governance query failed for {path}: {error}") from error


def verify_release_governance(
    *,
    repository: str,
    git_sha: str,
    manifest_digest: str,
    token: str,
    minimum_approvals: int = 1,
) -> dict[str, Any]:
    if (
        not repository
        or not git_sha
        or not manifest_digest.startswith("sha256:")
        or not token
    ):
        raise RuntimeError(
            "repository, git SHA, manifest digest and GitHub token are required"
        )
    pulls = _api_get(
        repository,
        f"/commits/{urllib.parse.quote(git_sha, safe='')}/pulls",
        token,
    )
    if not isinstance(pulls, list):
        raise RuntimeError("GitHub commit-to-PR response is invalid")
    candidates = [
        pull
        for pull in pulls
        if isinstance(pull, dict)
        and pull.get("merged_at")
        and pull.get("merge_commit_sha") == git_sha
        and ((pull.get("base") or {}).get("ref") == "main")
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "production release commit must be the unique merge result of a reviewed PR to main"
        )
    pull = candidates[0]
    number = int(pull["number"])
    reviews = _api_get(repository, f"/pulls/{number}/reviews?per_page=100", token)
    if not isinstance(reviews, list):
        raise RuntimeError("GitHub PR review response is invalid")
    latest_by_actor: dict[str, str] = {}
    for review in sorted(
        (item for item in reviews if isinstance(item, dict)),
        key=lambda item: str(item.get("submitted_at") or ""),
    ):
        actor = str(((review.get("user") or {}).get("login")) or "").strip()
        state = str(review.get("state") or "").upper()
        if actor:
            latest_by_actor[actor] = state
    author = str(((pull.get("user") or {}).get("login")) or "").strip()
    merger = str(((pull.get("merged_by") or {}).get("login")) or "").strip()
    approvers = sorted(
        actor
        for actor, state in latest_by_actor.items()
        if state == "APPROVED" and actor != author
    )
    if len(approvers) < minimum_approvals:
        raise RuntimeError(
            f"production release requires {minimum_approvals} non-author approval(s), "
            f"found {len(approvers)}"
        )
    principals = {actor for actor in [author, merger, *approvers] if actor}
    if len(principals) < 2:
        raise RuntimeError("production release requires at least two distinct principals")
    return {
        "schema": "prod-release-governance-receipt",
        "repository": repository,
        "gitSha": git_sha,
        "manifestDigest": manifest_digest,
        "pullRequest": number,
        "author": author,
        "mergedBy": merger,
        "approvers": approvers,
        "distinctPrincipals": sorted(principals),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--manifest-digest", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--minimum-approvals", type=int, default=1)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get(args.token_env, "").strip()
    try:
        receipt = verify_release_governance(
            repository=args.repository,
            git_sha=args.git_sha,
            manifest_digest=args.manifest_digest,
            token=token,
            minimum_approvals=args.minimum_approvals,
        )
    except RuntimeError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"OK: PR #{receipt['pullRequest']} release governance verified "
        f"with {len(receipt['approvers'])} approval(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
