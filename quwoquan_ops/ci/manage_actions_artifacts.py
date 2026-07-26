#!/usr/bin/env python3
"""审计并清理 GitHub Actions 的短生命周期制品。

Actions artifact 只承载失败诊断，不能作为 release 输入、正式发布
证据或成功 job 间传递。该工具先解析每个 artifact 所属 workflow run，
再按运行结论和保留窗口生成精确删除清单；默认 dry-run，只有传入
``--apply`` 才会逐个 DELETE 已判定为无效或过期的 artifact ID。
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


API_ROOT = "https://api.github.com"
TERMINAL_RUN_CONCLUSIONS = frozenset(
    {"cancelled", "startup_failure", "timed_out", "action_required", "skipped"}
)
AUTOMATIC_BUILD_RECORD_SUFFIX = ".dockerbuild"


@dataclass(frozen=True)
class CleanupDecision:
    artifact_id: int
    name: str
    size_bytes: int
    created_at: str
    expires_at: str | None
    run_id: int | None
    run_conclusion: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "name": self.name,
            "sizeBytes": self.size_bytes,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "runId": self.run_id,
            "runConclusion": self.run_conclusion,
            "reason": self.reason,
        }


def parse_timestamp(raw: object) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise ValueError(f"invalid GitHub timestamp: {raw!r}")
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)


def classify_artifact(
    artifact: dict[str, Any],
    run: dict[str, Any] | None,
    *,
    now: datetime,
    failed_retention_days: int,
    success_retention_days: int,
) -> CleanupDecision | None:
    """Return an exact deletion decision only for lifecycle-expired objects."""

    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int) or artifact_id <= 0:
        raise ValueError("artifact id is required")
    name = str(artifact.get("name") or "").strip()
    if not name:
        raise ValueError(f"artifact {artifact_id} has no name")
    created_at = str(artifact.get("created_at") or "")
    created = parse_timestamp(created_at)
    expires_at = artifact.get("expires_at")
    expires = str(expires_at) if isinstance(expires_at, str) else None
    size_bytes = int(artifact.get("size_in_bytes") or 0)
    workflow_run = artifact.get("workflow_run") or {}
    run_id = workflow_run.get("id")
    normalized_run_id = int(run_id) if isinstance(run_id, int) else None
    conclusion = str((run or {}).get("conclusion") or "").strip().lower() or None

    base = {
        "artifact_id": artifact_id,
        "name": name,
        "size_bytes": size_bytes,
        "created_at": created_at,
        "expires_at": expires,
        "run_id": normalized_run_id,
        "run_conclusion": conclusion,
    }
    if artifact.get("expired") is True:
        return CleanupDecision(reason="github-expired", **base)
    if name.lower().endswith(AUTOMATIC_BUILD_RECORD_SUFFIX):
        # docker/build-push-action build records are not approved failure
        # diagnostics or release evidence. This also cleans any record made
        # before the workflow-level upload switch was introduced.
        return CleanupDecision(reason="invalid-automatic-build-record", **base)
    if conclusion in TERMINAL_RUN_CONCLUSIONS:
        return CleanupDecision(reason=f"invalid-run-{conclusion}", **base)
    if conclusion == "success":
        # 成功路径的可部署输入是 GHCR OCI digest；任何成功 artifact 都是
        # 旧流程遗留或新回归，必须在 workflow_run completed 后立即回收。
        return CleanupDecision(reason="invalid-success-artifact", **base)
    if conclusion == "failure" and created <= now - timedelta(days=failed_retention_days):
        return CleanupDecision(reason="failure-diagnostic-retention-expired", **base)
    return None


class GitHubApi:
    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token
        self._runs: dict[int, dict[str, Any] | None] = {}

    def request(self, method: str, path: str) -> Any:
        request = urllib.request.Request(
            f"{API_ROOT}{path}",
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read()
                break
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return None
                transient = error.code == 429 or 500 <= error.code < 600
                if transient and attempt < 3:
                    time.sleep(2**attempt)
                    continue
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"GitHub API {method} {path} failed: {error.code} {detail}"
                ) from error
            except OSError as error:
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"GitHub API {method} {path} failed: {error}") from error
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"GitHub API {method} {path} returned invalid JSON") from error

    def list_artifacts(self) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.request(
                "GET",
                f"/repos/{self.repository}/actions/artifacts?per_page=100&page={page}",
            )
            if not isinstance(payload, dict):
                raise RuntimeError("GitHub artifact list response is invalid")
            items = payload.get("artifacts")
            if not isinstance(items, list):
                raise RuntimeError("GitHub artifact list has no artifacts array")
            artifacts.extend(item for item in items if isinstance(item, dict))
            if len(items) < 100:
                return artifacts
            page += 1

    def list_run_artifacts(self, run_id: int) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.request(
                "GET",
                f"/repos/{self.repository}/actions/runs/{run_id}/artifacts?per_page=100&page={page}",
            )
            if not isinstance(payload, dict):
                raise RuntimeError("GitHub workflow-run artifact response is invalid")
            items = payload.get("artifacts")
            if not isinstance(items, list):
                raise RuntimeError("GitHub workflow-run artifact response has no artifacts array")
            artifacts.extend(item for item in items if isinstance(item, dict))
            if len(items) < 100:
                return artifacts
            page += 1

    def workflow_run(self, run_id: int) -> dict[str, Any] | None:
        if run_id not in self._runs:
            payload = self.request(
                "GET", f"/repos/{self.repository}/actions/runs/{run_id}"
            )
            self._runs[run_id] = payload if isinstance(payload, dict) else None
        return self._runs[run_id]

    def workflow_runs(self, run_ids: set[int]) -> dict[int, dict[str, Any] | None]:
        """Resolve distinct runs with bounded concurrency and preserve retries."""

        unresolved = sorted(run_id for run_id in run_ids if run_id not in self._runs)
        if unresolved:
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    executor.submit(
                        self.request,
                        "GET",
                        f"/repos/{self.repository}/actions/runs/{run_id}",
                    ): run_id
                    for run_id in unresolved
                }
                for future in as_completed(futures):
                    run_id = futures[future]
                    payload = future.result()
                    self._runs[run_id] = payload if isinstance(payload, dict) else None
        return {run_id: self._runs.get(run_id) for run_id in run_ids}

    def delete_artifact(self, artifact_id: int) -> None:
        self.request("DELETE", f"/repos/{self.repository}/actions/artifacts/{artifact_id}")

    def delete_artifacts(
        self, artifact_ids: list[int]
    ) -> tuple[list[int], list[dict[str, object]]]:
        """Delete an already-reviewed ID list without one slow request blocking it."""

        deleted: list[int] = []
        failures: list[dict[str, object]] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(self.delete_artifact, artifact_id): artifact_id
                for artifact_id in artifact_ids
            }
            for future in as_completed(futures):
                artifact_id = futures[future]
                try:
                    future.result()
                except RuntimeError as error:
                    failures.append({"artifactId": artifact_id, "error": str(error)})
                else:
                    deleted.append(artifact_id)
        return sorted(deleted), sorted(failures, key=lambda item: int(item["artifactId"]))


def build_report(
    api: GitHubApi,
    *,
    now: datetime,
    failed_retention_days: int,
    success_retention_days: int,
) -> tuple[dict[str, Any], list[CleanupDecision]]:
    artifacts = api.list_artifacts()
    run_ids = {
        workflow_run["id"]
        for artifact in artifacts
        for workflow_run in [artifact.get("workflow_run") or {}]
        if isinstance(workflow_run.get("id"), int)
    }
    runs = api.workflow_runs(run_ids)
    decisions: list[CleanupDecision] = []
    unresolved_runs: list[int] = []
    active_bytes = 0
    for artifact in artifacts:
        if artifact.get("expired") is not True:
            active_bytes += int(artifact.get("size_in_bytes") or 0)
        workflow_run = artifact.get("workflow_run") or {}
        run_id = workflow_run.get("id")
        run: dict[str, Any] | None = None
        if isinstance(run_id, int):
            run = runs.get(run_id)
            if run is None:
                unresolved_runs.append(run_id)
        decision = classify_artifact(
            artifact,
            run,
            now=now,
            failed_retention_days=failed_retention_days,
            success_retention_days=success_retention_days,
        )
        if decision is not None:
            decisions.append(decision)
    decisions.sort(key=lambda item: item.artifact_id)
    reasons: dict[str, dict[str, int]] = {}
    for decision in decisions:
        totals = reasons.setdefault(decision.reason, {"count": 0, "bytes": 0})
        totals["count"] += 1
        totals["bytes"] += decision.size_bytes
    report = {
        "schema": "github-actions-artifact-lifecycle-report",
        "repository": api.repository,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "policy": {
            "failedRetentionDays": failed_retention_days,
            "successArtifacts": "invalid-immediately",
            "terminalConclusions": sorted(TERMINAL_RUN_CONCLUSIONS),
        },
        "inventory": {
            "totalArtifacts": len(artifacts),
            "activeArtifacts": sum(1 for item in artifacts if item.get("expired") is not True),
            "activeBytes": active_bytes,
            "unresolvedWorkflowRuns": sorted(set(unresolved_runs)),
        },
        "cleanup": {
            "candidateCount": len(decisions),
            "candidateBytes": sum(item.size_bytes for item in decisions),
            "byReason": reasons,
            "candidates": [item.as_dict() for item in decisions],
        },
    }
    return report, decisions


def build_run_report(
    api: GitHubApi,
    *,
    run_id: int,
    now: datetime,
    failed_retention_days: int,
    success_retention_days: int,
) -> tuple[dict[str, Any], list[CleanupDecision]]:
    """Classify one completed workflow run for immediate event-driven cleanup."""

    run = api.workflow_run(run_id)
    if run is None:
        raise RuntimeError(f"workflow run {run_id} was not found")
    artifacts = api.list_run_artifacts(run_id)
    decisions = [
        decision
        for artifact in artifacts
        if (
            decision := classify_artifact(
                artifact,
                run,
                now=now,
                failed_retention_days=failed_retention_days,
                success_retention_days=success_retention_days,
            )
        )
        is not None
    ]
    decisions.sort(key=lambda item: item.artifact_id)
    reasons: dict[str, dict[str, int]] = {}
    for decision in decisions:
        totals = reasons.setdefault(decision.reason, {"count": 0, "bytes": 0})
        totals["count"] += 1
        totals["bytes"] += decision.size_bytes
    active = [item for item in artifacts if item.get("expired") is not True]
    return (
        {
            "schema": "github-actions-artifact-lifecycle-report",
            "repository": api.repository,
            "generatedAt": now.isoformat().replace("+00:00", "Z"),
            "scope": {"workflowRunId": run_id},
            "policy": {
                "failedRetentionDays": failed_retention_days,
                "successArtifacts": "invalid-immediately",
                "terminalConclusions": sorted(TERMINAL_RUN_CONCLUSIONS),
            },
            "inventory": {
                "totalArtifacts": len(artifacts),
                "activeArtifacts": len(active),
                "activeBytes": sum(int(item.get("size_in_bytes") or 0) for item in active),
                "workflowRunConclusion": str(run.get("conclusion") or "").lower() or None,
            },
            "cleanup": {
                "candidateCount": len(decisions),
                "candidateBytes": sum(item.size_bytes for item in decisions),
                "byReason": reasons,
                "candidates": [item.as_dict() for item in decisions],
            },
        },
        decisions,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--failed-retention-days", type=int, default=7)
    parser.add_argument("--success-retention-days", type=int, default=14)
    parser.add_argument(
        "--run-id",
        type=int,
        default=0,
        help="only audit and reclaim invalid artifacts from one completed workflow run",
    )
    parser.add_argument("--now", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--max-deletions",
        type=int,
        default=0,
        help="apply at most this many reviewed candidates (0 means all)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.failed_retention_days < 1
        or args.success_retention_days < 1
        or args.max_deletions < 0
    ):
        print("retention days must be at least one", file=sys.stderr)
        return 2
    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(f"missing GitHub token in {args.token_env}", file=sys.stderr)
        return 2
    try:
        now = parse_timestamp(args.now) if args.now else datetime.now(UTC)
        api = GitHubApi(args.repository, token)
        if args.run_id:
            report, decisions = build_run_report(
                api,
                run_id=args.run_id,
                now=now,
                failed_retention_days=args.failed_retention_days,
                success_retention_days=args.success_retention_days,
            )
        else:
            report, decisions = build_report(
                api,
                now=now,
                failed_retention_days=args.failed_retention_days,
                success_retention_days=args.success_retention_days,
            )
        if args.apply:
            selected = decisions[: args.max_deletions or None]
            deleted_artifact_ids, delete_failures = api.delete_artifacts(
                [item.artifact_id for item in selected]
            )
            report["cleanup"]["applied"] = True
            report["cleanup"]["selectedCount"] = len(selected)
            report["cleanup"]["deferredCandidateCount"] = len(decisions) - len(selected)
            report["cleanup"]["deletedArtifactIds"] = deleted_artifact_ids
            report["cleanup"]["deleteFailures"] = delete_failures
            remaining = (
                api.list_run_artifacts(args.run_id)
                if args.run_id
                else api.list_artifacts()
            )
            report["postApplyInventory"] = {
                "totalArtifacts": len(remaining),
                "activeArtifacts": sum(
                    1 for item in remaining if item.get("expired") is not True
                ),
                "activeBytes": sum(
                    int(item.get("size_in_bytes") or 0)
                    for item in remaining
                    if item.get("expired") is not True
                ),
            }
            report["cleanup"]["complete"] = (
                not delete_failures and len(selected) == len(decisions)
            )
        else:
            report["cleanup"]["applied"] = False
    except (RuntimeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 2 if args.apply and report["cleanup"].get("deleteFailures") else 0


if __name__ == "__main__":
    raise SystemExit(main())
