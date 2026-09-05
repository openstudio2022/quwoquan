"""Weekly report-only growth, hotspot, clone, reachability, and delivery outcomes."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from quwoquan_ops.ci.impact_planner_core import canonical_digest

from .classification import classify_path
from .metrics import function_metrics, line_count, reuse_scope_key


def _run(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run([*args], cwd=repo, capture_output=True, text=text, check=False)
    if completed.returncode:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise ValueError(stderr.strip() or f"command failed: {args}")
    return completed.stdout


def _git(repo: Path, *args: str) -> str:
    return str(_run(repo, "git", *args))


def _tracked_paths(repo: Path, head: str) -> list[str]:
    raw = _run(repo, "git", "ls-tree", "-r", "--name-only", "-z", head, text=False)
    assert isinstance(raw, bytes)
    return sorted((item.decode("utf-8") for item in raw.split(b"\0") if item), key=lambda value: value.encode("utf-8"))


def _clean_current_blobs(repo: Path, head: str, paths: Iterable[str]) -> dict[str, bytes]:
    if _git(repo, "rev-parse", "HEAD").strip() != head:
        raise ValueError("weekly analysis requires head to equal checked-out HEAD")
    if _git(repo, "status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("weekly analysis requires a clean tracked candidate")
    result: dict[str, bytes] = {}
    for path in paths:
        candidate = repo / path
        if candidate.is_file() and not candidate.is_symlink():
            result[path] = candidate.read_bytes()
    return result


def _commit_time(repo: Path, head: str) -> datetime:
    value = datetime.fromisoformat(_git(repo, "show", "-s", "--format=%cI", head).strip())
    if value.tzinfo is None:
        raise ValueError("head committer date must include timezone")
    return value


def _historical_commits(repo: Path, head: str, end: datetime, weeks: Iterable[int]) -> list[tuple[int, str]]:
    values = []
    for age in weeks:
        before = (end - timedelta(weeks=age)).isoformat()
        sha = _git(repo, "rev-list", "--first-parent", "-1", f"--before={before}", head).strip()
        if sha and (not values or values[-1][1] != sha):
            values.append((age, sha))
    return values


def _cloc(repo: Path, sha: str, executable: str) -> dict[str, Any]:
    raw = _run(repo, executable, "--git", sha, "--skip-uniqueness", "--timeout=0", "--json", "--quiet")
    payload = json.loads(str(raw))
    summary = payload.get("SUM")
    if not isinstance(summary, dict):
        raise ValueError(f"cloc output for {sha} lacks SUM")
    header = payload.get("header") or {}
    return {
        "sha": sha,
        "files": int(summary.get("nFiles", 0)),
        "blank": int(summary.get("blank", 0)),
        "comment": int(summary.get("comment", 0)),
        "sourceLoc": int(summary.get("code", 0)),
        "clocVersion": str(header.get("cloc_version", "unknown")),
        "countDuplicatePaths": True,
    }


def _numstat(repo: Path, base: str | None, head: str) -> list[tuple[str, int, int]]:
    args = ["diff", "--numstat", "-z", "--no-renames"]
    if base:
        args.extend([base, head])
    else:
        args.extend([f"{head}^{{tree}}"])
    raw = _run(repo, "git", *args, text=False)
    assert isinstance(raw, bytes)
    result = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        added, deleted, path = record.split(b"\t", 2)
        result.append((path.decode("utf-8"), 0 if added == b"-" else int(added), 0 if deleted == b"-" else int(deleted)))
    return result


def _churn(repo: Path, head: str, start: datetime) -> dict[str, dict[str, int]]:
    commits = _git(repo, "rev-list", "--first-parent", f"--since={start.isoformat()}", head).splitlines()
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"added": 0, "deleted": 0, "churn": 0, "changeFrequency": 0})
    for commit in commits:
        parents = _git(repo, "rev-list", "--parents", "-n", "1", commit).split()
        base = parents[1] if len(parents) > 1 else None
        touched: set[str] = set()
        for path, added, deleted in _numstat(repo, base, commit):
            item = totals[path]
            item["added"] += added
            item["deleted"] += deleted
            item["churn"] += added + deleted
            touched.add(path)
        for path in touched:
            totals[path]["changeFrequency"] += 1
    return dict(totals)


def _normalized_lines(body: bytes) -> list[str]:
    import re
    values = []
    for line in body.decode("utf-8", "replace").splitlines():
        value = re.sub(r"\s+", " ", line.strip())
        values.append("" if not value or value.startswith(("#", "//", "/*", "*")) else value)
    return values


def _clone_facts(blobs: dict[str, bytes], block_lines: int) -> tuple[dict[str, int], int]:
    first_path: dict[bytes, str] = {}
    cloned_digests: set[bytes] = set()
    for path in sorted(blobs):
        lines = _normalized_lines(blobs[path])
        seen_in_file: set[bytes] = set()
        for index in range(max(0, len(lines) - block_lines + 1)):
            window = lines[index : index + block_lines]
            if not all(window):
                continue
            digest = hashlib.blake2b("\n".join(window).encode(), digest_size=16).digest()
            if digest in seen_in_file:
                continue
            seen_in_file.add(digest)
            source = first_path.setdefault(digest, path)
            if source != path:
                cloned_digests.add(digest)

    covered_lines: dict[str, set[int]] = defaultdict(set)
    for path in sorted(blobs):
        lines = _normalized_lines(blobs[path])
        for index in range(max(0, len(lines) - block_lines + 1)):
            window = lines[index : index + block_lines]
            if not all(window):
                continue
            digest = hashlib.blake2b("\n".join(window).encode(), digest_size=16).digest()
            if digest in cloned_digests:
                covered_lines[path].update(range(index, index + block_lines))
    return {path: len(lines) for path, lines in covered_lines.items()}, len(cloned_digests)


def _dead_candidates(repo: Path) -> list[dict[str, str]]:
    try:
        from quwoquan_ops.gate.python_script_governance.report import derive_report
        report = derive_report(repo, ("app", "service", "ops", "data"))
        return [
            {"path": item["path"], "reason": "python-script-governance-orphan-candidate"}
            for item in report.get("scripts", [])
            if item.get("orphanCandidate")
        ]
    except Exception as exc:  # report-only keeps typed unavailable evidence
        return [{"path": "<unavailable>", "reason": f"python-script-governance:{type(exc).__name__}"}]


def delivery_outcomes(
    pages: object,
    *,
    end: datetime,
    days: int = 28,
    regression_percent: float = 10.0,
) -> dict[str, Any]:
    if pages is None:
        return {
            "status": "not-provided",
            "comparisonStatus": "insufficient-history",
            "regressionFlags": None,
        }
    page_list = pages if isinstance(pages, list) else [pages]
    runs: list[dict[str, Any]] = []
    for page in page_list:
        if not isinstance(page, dict):
            continue
        page_runs = page.get("workflow_runs") or []
        if isinstance(page_runs, list):
            runs.extend(run for run in page_runs if isinstance(run, dict))
    current_start = end.astimezone(timezone.utc) - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    def summarize(start: datetime, stop: datetime) -> dict[str, Any]:
        selected = []
        for run in runs:
            created_raw = run.get("created_at")
            if not created_raw:
                continue
            created = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            if start <= created < stop and run.get("status") == "completed":
                selected.append((run, created))
        successes = sum(run.get("conclusion") == "success" for run, _ in selected)
        failures = sum(run.get("conclusion") not in {"success", "neutral", "skipped"} for run, _ in selected)
        reruns = sum(int(run.get("run_attempt") or 1) > 1 for run, _ in selected)
        durations = []
        for run, created in selected:
            updated_raw = run.get("updated_at")
            if updated_raw:
                updated = datetime.fromisoformat(str(updated_raw).replace("Z", "+00:00"))
                durations.append(max(0.0, (updated - created).total_seconds()))
        return {
            "completedRuns": len(selected), "successRuns": successes, "failedRuns": failures,
            "failureRate": None if not selected else round(failures / len(selected), 4),
            "rerunRate": None if not selected else round(reruns / len(selected), 4),
            "calendarP95Seconds": _percentile(durations, 0.95),
        }

    current = summarize(current_start, end.astimezone(timezone.utc))
    previous = summarize(previous_start, current_start)
    result: dict[str, Any] = {
        "status": "observed",
        "windowDays": days,
        "current": current,
        "previous": previous,
        "regressionThresholdPercent": regression_percent,
    }
    if current["completedRuns"] == 0 or previous["completedRuns"] == 0:
        result["comparisonStatus"] = "insufficient-history"
        result["regressionFlags"] = None
        return result

    limit = regression_percent / 100
    result["comparisonStatus"] = "comparable"
    result["regressionFlags"] = {
        "failureRate": current["failureRate"] > previous["failureRate"] + limit,
        "rerunRate": current["rerunRate"] > previous["rerunRate"] + limit,
        "calendarP95Seconds": (
            current["calendarP95Seconds"] is not None
            and previous["calendarP95Seconds"] not in {None, 0}
            and current["calendarP95Seconds"] > previous["calendarP95Seconds"] * (1 + limit)
        ),
    }
    return result


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 3)


def analyze_weekly(
    repo: Path,
    *,
    head: str,
    policy: dict[str, Any],
    cloc_executable: str = "cloc",
    delivery_run_pages: object = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    head_sha = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}").strip()
    end = _commit_time(repo, head_sha)
    start = end - timedelta(days=90)
    paths = _tracked_paths(repo, head_sha)
    all_blobs = _clean_current_blobs(repo, head_sha, paths)
    production = {path: body for path, body in all_blobs.items() if classify_path(path, policy) == "handwritten-production"}
    categories: dict[str, dict[str, int]] = {name: {"files": 0, "lines": 0} for name in policy["source_categories"]}
    for path, body in all_blobs.items():
        category = classify_path(path, policy)
        categories[category]["files"] += 1
        categories[category]["lines"] += line_count(body)
    history = [
        {"ageWeeks": age, "committerDate": _commit_time(repo, sha).isoformat(timespec="seconds"), **_cloc(repo, sha, cloc_executable)}
        for age, sha in _historical_commits(repo, head_sha, end, (13, 4, 1, 0))
    ]
    churn = _churn(repo, head_sha, start)
    clone_lines, clone_groups = _clone_facts(production, policy["thresholds"]["duplication"]["block_lines"])
    complexity: dict[str, dict[str, int]] = {}
    hotspots = []
    for path, body in production.items():
        functions = function_metrics(path, body)
        maximum_cyclomatic = max((item.cyclomatic for item in functions), default=0)
        maximum_cognitive = max((item.cognitive for item in functions), default=0)
        lines = line_count(body)
        complexity[path] = {"functions": len(functions), "maxCyclomatic": maximum_cyclomatic, "maxCognitive": maximum_cognitive}
        activity = churn.get(path, {"added": 0, "deleted": 0, "churn": 0, "changeFrequency": 0})
        health = max(
            1.0,
            lines / policy["thresholds"]["file_lines"]["advisory"],
            maximum_cyclomatic / policy["thresholds"]["complexity"]["cyclomatic_advisory"],
            maximum_cognitive / policy["thresholds"]["complexity"]["cognitive_advisory"],
            1.0 + clone_lines.get(path, 0) / max(1, lines),
        )
        score = activity["churn"] * (1.0 + math.log2(1 + activity["changeFrequency"])) * health
        if score:
            hotspots.append({
                "path": path, "ownerScope": reuse_scope_key(path), "score": round(score, 3),
                "healthFactor": round(health, 4), "lines": lines, "cloneLines": clone_lines.get(path, 0),
                **activity, **complexity[path],
            })
    top = sorted(hotspots, key=lambda item: (-item["score"], item["path"]))[: policy["report"]["weekly_top_hotspots"]]
    tools = {"cloc": history[-1]["clocVersion"] if history else "unavailable", "builtinMetrics": 1}
    dead_candidates = _dead_candidates(repo)
    outcome = delivery_outcomes(
        delivery_run_pages,
        end=end,
        regression_percent=policy["performance"]["delivery_outcome_regression_percent"],
    )
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include timezone")
    observed_value = observed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    window = {
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "days": 90,
    }
    policy_digest = canonical_digest(policy)
    implementation_digest = canonical_digest({
        f"quwoquan_ops/gate/code_health_delta/{name}": "sha256:" + hashlib.sha256(
            Path(__file__).with_name(name).read_bytes()
        ).hexdigest()
        for name in ("weekly.py", "metrics.py", "classification.py")
    })
    delivery_outcomes_digest = canonical_digest(delivery_run_pages)
    identity = canonical_digest({
        "headSha": head_sha,
        "window": window,
        "policyDigest": policy_digest,
        "implementationDigest": implementation_digest,
        "deliveryOutcomesDigest": delivery_outcomes_digest,
        "observedAt": observed_value,
        "tools": tools,
    })
    return {
        "schema": "quwoquan.code-health-weekly.v1", "terminal": "REPORT_ONLY",
        "headSha": head_sha, "window": window,
        "identityDigest": identity, "policyId": policy["policy_id"],
        "policyDigest": policy_digest, "implementationDigest": implementation_digest,
        "deliveryOutcomesDigest": delivery_outcomes_digest, "observedAt": observed_value,
        "tools": tools,
        "growthHistory": history, "categories": categories,
        "summary": {"trackedFiles": len(paths), "handwrittenProductionFiles": len(production), "cloneGroupCount": clone_groups, "deadCandidateCount": len(dead_candidates)},
        "complexitySummary": {
            "functionCount": sum(item["functions"] for item in complexity.values()),
            "overCyclomaticAdvisory": sum(item["maxCyclomatic"] > policy["thresholds"]["complexity"]["cyclomatic_advisory"] for item in complexity.values()),
            "overCognitiveAdvisory": sum(item["maxCognitive"] > policy["thresholds"]["complexity"]["cognitive_advisory"] for item in complexity.values()),
        },
        "topHotspots": top, "deadCodeCandidates": dead_candidates,
        "deliveryOutcomes": outcome,
        "generatedAt": observed_value,
        "authority": {"blocksPullRequests": False, "createsOwnerOpen": False, "automaticRemediation": False},
    }
