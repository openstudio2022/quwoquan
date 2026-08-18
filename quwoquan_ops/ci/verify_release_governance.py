#!/usr/bin/env python3
"""在 GitHub 套餐保护不可用时，仍阻断未评审提交进入生产执行面。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import validate_manifest
from quwoquan_ops.gate.verify_git_branch_policy import load_policy


GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


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
        raise RuntimeError(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE: GitHub governance query failed "
            f"for {path}: {error}"
        ) from error


def verify_release_governance(
    *,
    repository: str,
    git_sha: str,
    artifact_digest: str = "",
    token: str,
    workflow_ref: str,
    workflow_run_id: str = "",
    workflow_run_attempt: str = "",
    minimum_approvals: int = 1,
) -> dict[str, Any]:
    if (
        not repository
        or not GIT_SHA_PATTERN.fullmatch(git_sha)
        or (artifact_digest and not SHA256_PATTERN.fullmatch(artifact_digest))
        or not token
    ):
        raise RuntimeError(
            "repository, exact Git SHA and GitHub token are required; any artifact "
            "digest must be exact sha256"
        )
    branch_policy = load_policy()
    expected_workflow_ref = (
        f"{repository}/{branch_policy.production_workflow}@refs/heads/"
        f"{branch_policy.release_branch}"
    )
    if workflow_ref != expected_workflow_ref:
        raise RuntimeError(
            "production release governance must execute from the canonical main "
            f"workflow definition; expected {expected_workflow_ref!r}, got "
            f"{workflow_ref!r}"
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
        and (
            (pull.get("base") or {}).get("ref")
            == branch_policy.release_branch
        )
        and (
            (pull.get("head") or {}).get("ref")
            == branch_policy.integration_branch
        )
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "production release commit must be the unique merge result of the "
            f"{branch_policy.integration_branch} -> {branch_policy.release_branch} "
            "promotion PR"
        )
    pull = candidates[0]
    number = int(pull["number"])
    if not workflow_run_id.isdigit() or not workflow_run_attempt.isdigit():
        raise RuntimeError(
            "production source admission requires exact hosted workflow run and attempt"
        )
    current_run_id = int(workflow_run_id)
    current_run_attempt = int(workflow_run_attempt)
    if current_run_id < 1 or current_run_attempt < 1:
        raise RuntimeError(
            "production source admission requires positive workflow run and attempt"
        )
    current_run = _api_get(
        repository,
        f"/actions/runs/{current_run_id}/attempts/{current_run_attempt}",
        token,
    )
    if (
        not isinstance(current_run, dict)
        or current_run.get("id") != current_run_id
        or current_run.get("run_attempt") != current_run_attempt
        or current_run.get("head_sha") != git_sha
        or current_run.get("head_branch") != branch_policy.release_branch
        or current_run.get("path") != branch_policy.production_workflow
        or current_run.get("event") not in {"push", "workflow_dispatch"}
        or current_run.get("status") not in {"queued", "in_progress", "completed"}
        or str(((current_run.get("repository") or {}).get("full_name")) or "")
        != repository
        or not str(((current_run.get("actor") or {}).get("login")) or "")
        or not str(((current_run.get("triggering_actor") or {}).get("login")) or "")
        or not isinstance(current_run.get("workflow_id"), int)
        or current_run["workflow_id"] < 1
    ):
        raise RuntimeError(
            "production source admission is not bound to the current canonical hosted workflow attempt"
        )
    repository_state = _api_get(repository, "", token)
    if (
        not isinstance(repository_state, dict)
        or repository_state.get("full_name") != repository
        or repository_state.get("default_branch") != branch_policy.release_branch
        or repository_state.get("delete_branch_on_merge") is not True
    ):
        raise RuntimeError(
            "hosted repository identity/default branch/auto-delete authority is invalid"
        )
    head_repository = str(
        ((((pull.get("head") or {}).get("repo") or {}).get("full_name"))) or ""
    ).strip()
    if head_repository != repository:
        raise RuntimeError(
            "production promotion head must belong to the governed repository"
        )
    promotion_head_oid = str((pull.get("head") or {}).get("sha") or "")
    if not GIT_SHA_PATTERN.fullmatch(promotion_head_oid):
        raise RuntimeError("production promotion head must be an exact Git SHA")

    commit_object = _api_get(repository, f"/git/commits/{git_sha}", token)
    if not isinstance(commit_object, dict) or commit_object.get("sha") != git_sha:
        raise RuntimeError("production source is not the exact hosted commit object")
    parent_oids = {
        str(parent.get("sha") or "")
        for parent in commit_object.get("parents", [])
        if isinstance(parent, dict)
    }
    if promotion_head_oid not in parent_oids:
        raise RuntimeError(
            "production merge commit is not bound to the exact promotion head"
        )
    main_ref = _api_get(
        repository,
        f"/git/ref/heads/{urllib.parse.quote(branch_policy.release_branch, safe='')}",
        token,
    )
    main_object = (main_ref or {}).get("object") if isinstance(main_ref, dict) else None
    main_oid = str((main_object or {}).get("sha") or "")
    if (
        not GIT_SHA_PATTERN.fullmatch(main_oid)
        or str((main_object or {}).get("type") or "") != "commit"
    ):
        raise RuntimeError("trusted main ref does not resolve to an exact commit")
    comparison = _api_get(
        repository,
        f"/compare/{git_sha}...{main_oid}",
        token,
    )
    merge_base_oid = str(
        ((comparison or {}).get("merge_base_commit") or {}).get("sha") or ""
    ) if isinstance(comparison, dict) else ""
    if (
        not isinstance(comparison, dict)
        or comparison.get("status") not in {"ahead", "identical"}
        or merge_base_oid != git_sha
    ):
        raise RuntimeError(
            "production source commit is not provably reachable from trusted main"
        )

    reviews = _api_get(repository, f"/pulls/{number}/reviews?per_page=100", token)
    if not isinstance(reviews, list):
        raise RuntimeError("GitHub PR review response is invalid")
    latest_by_actor: dict[str, str] = {}
    for review in sorted(
        (
            item
            for item in reviews
            if isinstance(item, dict)
            and item.get("commit_id") == promotion_head_oid
        ),
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
    check_payload = _api_get(
        repository,
        f"/commits/{promotion_head_oid}/check-runs?filter=latest&per_page=100",
        token,
    )
    check_runs = (
        check_payload.get("check_runs") if isinstance(check_payload, dict) else None
    )
    if not isinstance(check_runs, list):
        raise RuntimeError("GitHub check-runs response is invalid")
    checks_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in check_runs:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            checks_by_name.setdefault(name, []).append(item)
    verified_checks: list[dict[str, Any]] = []
    for required_check in branch_policy.required_promotion_checks:
        matches = checks_by_name.get(required_check.name, [])
        if matches and not any(
            check.get("head_sha") == promotion_head_oid
            and check.get("status") == "completed"
            and check.get("conclusion") == "success"
            for check in matches
        ):
            raise RuntimeError(
                f"required promotion check {required_check.name!r} is not successful for exact SHA"
            )
        canonical_matches: list[dict[str, Any]] = []
        for check in matches:
            if (
                check.get("head_sha") != promotion_head_oid
                or check.get("status") != "completed"
                or check.get("conclusion") != "success"
            ):
                continue
            app = check.get("app") or {}
            check_suite = check.get("check_suite") or {}
            if (
                not isinstance(app, dict)
                or app.get("slug") != "github-actions"
                or not isinstance(check_suite, dict)
            ):
                continue
            details_url = str(check.get("details_url") or "")
            details_match = re.fullmatch(
                rf"https://github\.com/{re.escape(repository)}/actions/runs/(\d+)/job/\d+",
                details_url,
            )
            if details_match is None:
                continue
            required_run_id = int(details_match.group(1))
            try:
                check_run_id = int(check.get("id") or 0)
                check_suite_id = int(check_suite.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if check_run_id < 1 or check_suite_id < 1:
                continue
            workflow_run = _api_get(
                repository,
                f"/actions/runs/{required_run_id}",
                token,
            )
            workflow_pull_numbers = (
                {
                    int(item["number"])
                    for item in (workflow_run.get("pull_requests") or [])
                    if isinstance(item, dict)
                    and str(item.get("number") or "").isdigit()
                }
                if isinstance(workflow_run, dict)
                else set()
            )
            if (
                not isinstance(workflow_run, dict)
                or workflow_run.get("id") != required_run_id
                or workflow_run.get("event") != "pull_request"
                or workflow_run.get("head_sha") != promotion_head_oid
                or workflow_run.get("status") != "completed"
                or workflow_run.get("conclusion") != "success"
                or workflow_run.get("path") != required_check.workflow
                or number not in workflow_pull_numbers
                or str(
                    ((workflow_run.get("repository") or {}).get("full_name"))
                    or ""
                )
                != repository
                or not isinstance(workflow_run.get("run_attempt"), int)
                or int(workflow_run["run_attempt"]) < 1
                or not str(((workflow_run.get("actor") or {}).get("login")) or "")
            ):
                continue
            canonical_matches.append(
                {
                    "name": required_check.name,
                    "workflow": required_check.workflow,
                    "runId": required_run_id,
                    "runAttempt": int(workflow_run["run_attempt"]),
                    "checkRunId": check_run_id,
                    "checkSuiteId": check_suite_id,
                }
            )
        if len(canonical_matches) != 1:
            raise RuntimeError(
                f"required promotion check {required_check.name!r} must bind exactly one canonical workflow run for PR #{number}; found {len(canonical_matches)}"
            )
        verified_checks.append(canonical_matches[0])
    receipt = {
        "schema": (
            "prod-release-governance-receipt"
            if artifact_digest
            else "prod-source-governance-receipt"
        ),
        "repository": repository,
        "gitSha": git_sha,
        "pullRequest": number,
        "promotionHead": branch_policy.integration_branch,
        "promotionHeadOid": promotion_head_oid,
        "promotionBase": branch_policy.release_branch,
        "mainOid": main_oid,
        "workflowRef": workflow_ref,
        "workflowRunId": current_run_id,
        "workflowRunAttempt": current_run_attempt,
        "workflowActor": str((current_run["actor"] or {})["login"]),
        "workflowTriggeringActor": str(
            (current_run["triggering_actor"] or {})["login"]
        ),
        "hostedDefaultBranch": branch_policy.release_branch,
        "hostedDeleteBranchOnMerge": True,
        "hostedProtectionVerified": False,
        "requiredChecks": verified_checks,
        "author": author,
        "mergedBy": merger,
        "approvers": approvers,
        "distinctPrincipals": sorted(principals),
        "verifiedAt": dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if artifact_digest:
        receipt["artifactDigest"] = artifact_digest
    digest_payload = {
        key: value
        for key, value in receipt.items()
        if key not in {"verifiedAt", "evidenceDigest"}
    }
    receipt["evidenceDigest"] = "sha256:" + hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--artifact-digest", default="")
    parser.add_argument("--release-manifest", type=Path)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--minimum-approvals", type=int, default=1)
    parser.add_argument("--workflow-ref", default=os.environ.get("GITHUB_WORKFLOW_REF", ""))
    parser.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument(
        "--workflow-run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "")
    )
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get(args.token_env, "").strip()
    try:
        git_sha = args.git_sha
        artifact_digest = args.artifact_digest
        if args.release_manifest is not None:
            manifest = json.loads(
                args.release_manifest.read_text(encoding="utf-8")
            )
            if not isinstance(manifest, dict):
                raise RuntimeError("release evidence manifest must be an object")
            try:
                validate_manifest(
                    manifest,
                    allowed_statuses={"candidate-ready", "deployable", "released"},
                )
            except ValueError as error:
                raise RuntimeError(
                    f"release evidence manifest is invalid: {error}"
                ) from error
            source = manifest.get("source") or {}
            derived_sha = str(source.get("gitSha") or "")
            derived_digest = str(manifest.get("artifactDigest") or "")
            if git_sha and git_sha != derived_sha:
                raise RuntimeError("release governance git SHA disagrees with manifest")
            if artifact_digest and artifact_digest != derived_digest:
                raise RuntimeError(
                    "release governance digest disagrees with manifest"
                )
            git_sha = derived_sha
            artifact_digest = derived_digest
        receipt = verify_release_governance(
            repository=args.repository,
            git_sha=git_sha,
            artifact_digest=artifact_digest,
            token=token,
            workflow_ref=args.workflow_ref,
            workflow_run_id=args.workflow_run_id,
            workflow_run_attempt=args.workflow_run_attempt,
            minimum_approvals=args.minimum_approvals,
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
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
