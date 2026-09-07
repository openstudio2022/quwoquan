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


def _window_digests(body: bytes, block_lines: int) -> list[tuple[int, bytes]]:
    """(start index, digest) for every fully non-blank normalized window of one file."""
    lines = _normalized_lines(body)
    digests = []
    for index in range(max(0, len(lines) - block_lines + 1)):
        window = lines[index: index + block_lines]
        if all(window):
            digests.append((index, hashlib.blake2b("\n".join(window).encode(), digest_size=16).digest()))
    return digests


def _clone_facts(blobs: dict[str, bytes], block_lines: int) -> tuple[dict[str, int], int]:
    windows = {path: _window_digests(blobs[path], block_lines) for path in sorted(blobs)}
    first_path: dict[bytes, str] = {}
    cloned_digests: set[bytes] = set()
    for path, items in windows.items():
        for digest in {digest for _, digest in items}:
            if first_path.setdefault(digest, path) != path:
                cloned_digests.add(digest)
    covered_lines: dict[str, set[int]] = defaultdict(set)
    for path, items in windows.items():
        for index, digest in items:
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


def _workflow_runs(pages: object) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for page in pages if isinstance(pages, list) else [pages]:
        page_runs = page.get("workflow_runs") if isinstance(page, dict) else None
        if isinstance(page_runs, list):
            runs.extend(run for run in page_runs if isinstance(run, dict))
    return runs


def _iso(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _summarize_runs(runs: list[dict[str, Any]], start: datetime, stop: datetime) -> dict[str, Any]:
    selected = [
        (run, _iso(run["created_at"])) for run in runs
        if run.get("created_at") and run.get("status") == "completed" and start <= _iso(run["created_at"]) < stop
    ]
    failures = sum(run.get("conclusion") not in {"success", "neutral", "skipped"} for run, _ in selected)
    reruns = sum(int(run.get("run_attempt") or 1) > 1 for run, _ in selected)
    durations = [
        max(0.0, (_iso(run["updated_at"]) - created).total_seconds())
        for run, created in selected if run.get("updated_at")
    ]
    return {
        "completedRuns": len(selected),
        "successRuns": sum(run.get("conclusion") == "success" for run, _ in selected),
        "failedRuns": failures,
        "failureRate": None if not selected else round(failures / len(selected), 4),
        "rerunRate": None if not selected else round(reruns / len(selected), 4),
        "calendarP95Seconds": _percentile(durations, 0.95),
    }


def _regression_flags(current: dict[str, Any], previous: dict[str, Any], limit: float) -> dict[str, bool]:
    return {
        "failureRate": current["failureRate"] > previous["failureRate"] + limit,
        "rerunRate": current["rerunRate"] > previous["rerunRate"] + limit,
        "calendarP95Seconds": (
            current["calendarP95Seconds"] is not None
            and previous["calendarP95Seconds"] not in {None, 0}
            and current["calendarP95Seconds"] > previous["calendarP95Seconds"] * (1 + limit)
        ),
    }


def delivery_outcomes(
    pages: object,
    *,
    end: datetime,
    days: int = 28,
    regression_percent: float = 10.0,
) -> dict[str, Any]:
    if pages is None:
        return {"status": "not-provided", "comparisonStatus": "insufficient-history", "regressionFlags": None}
    runs = _workflow_runs(pages)
    end_utc = end.astimezone(timezone.utc)
    current_start = end_utc - timedelta(days=days)
    current = _summarize_runs(runs, current_start, end_utc)
    previous = _summarize_runs(runs, current_start - timedelta(days=days), current_start)
    comparable = current["completedRuns"] > 0 and previous["completedRuns"] > 0
    return {
        "status": "observed",
        "windowDays": days,
        "current": current,
        "previous": previous,
        "regressionThresholdPercent": regression_percent,
        "comparisonStatus": "comparable" if comparable else "insufficient-history",
        "regressionFlags": _regression_flags(current, previous, regression_percent / 100) if comparable else None,
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 3)


WEEKLY_SCHEMA = "quwoquan.code-health-weekly.v1"

#: 棘轮指标：值越小越好。方向判断只看这些字段，不读 hotspot 排名。
RATCHET_METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overCyclomaticAdvisory", ("complexitySummary", "overCyclomaticAdvisory")),
    ("overCognitiveAdvisory", ("complexitySummary", "overCognitiveAdvisory")),
    ("cloneGroupCount", ("summary", "cloneGroupCount")),
    ("deadCandidateCount", ("summary", "deadCandidateCount")),
)


def _size_distribution(blobs: dict[str, bytes], tiers: list[int]) -> dict[str, int]:
    counts = {f"over{tier}": 0 for tier in tiers}
    lines_over = {f"linesOver{tier}": 0 for tier in tiers}
    for body in blobs.values():
        lines = line_count(body)
        for tier in tiers:
            if lines > tier:
                counts[f"over{tier}"] += 1
                lines_over[f"linesOver{tier}"] += lines - tier
    return {"files": len(blobs), **counts, **lines_over}


def _lookup(report: dict[str, Any], path: tuple[str, ...]) -> int | None:
    value: Any = report
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _ordered_previous(previous_reports: Iterable[dict[str, Any]], current_head: str) -> list[dict[str, Any]]:
    ordered = []
    for report in previous_reports:
        if not isinstance(report, dict) or report.get("schema") != WEEKLY_SCHEMA:
            raise ValueError("previous weekly report schema 非法")
        if report.get("headSha") == current_head:
            continue
        ordered.append(report)
    return sorted(ordered, key=lambda item: str(item["window"]["end"]), reverse=True)


def ratchet_trend(current: dict[str, Any], previous: list[dict[str, Any]], tiers: list[int]) -> dict[str, Any]:
    """Week-over-week direction for every ratchet metric; ``n/a`` when no history exists."""
    last = previous[0] if previous else None
    metrics: dict[str, dict[str, Any]] = {}
    paths: list[tuple[str, tuple[str, ...]]] = list(RATCHET_METRICS)
    for category in ("production", "test"):
        for tier in tiers:
            paths.append((f"{category}.over{tier}", ("sizeDistribution", category, f"over{tier}")))
            paths.append((f"{category}.linesOver{tier}", ("sizeDistribution", category, f"linesOver{tier}")))
    for name, path in paths:
        now = _lookup(current, path)
        before = None if last is None else _lookup(last, path)
        if now is None or before is None:
            direction = "n/a"
        elif now < before:
            direction = "improved"
        elif now > before:
            direction = "worsened"
        else:
            direction = "flat"
        metrics[name] = {"previous": before, "current": now, "direction": direction}
    return {
        "comparisonStatus": "comparable" if last is not None else "insufficient-history",
        "previousHeadSha": None if last is None else last["headSha"],
        "previousWindowEnd": None if last is None else last["window"]["end"],
        "metrics": metrics,
    }


def _iso_week(window_end: str) -> tuple[int, int]:
    calendar = datetime.fromisoformat(window_end).isocalendar()
    return calendar[0], calendar[1]


def _week_index(week: tuple[int, int]) -> int:
    """Monotonic week counter so adjacency survives year boundaries."""
    year, number = week
    return datetime.fromisocalendar(year, number, 1).toordinal() // 7


def _weekly_top_paths(previous: list[dict[str, Any]], current_week: tuple[int, int]) -> list[tuple[int, set[str]]]:
    """Per ISO week (most recent first) the union of Top-N paths; the current week is excluded.

    同一周内多次本地重跑不算多期，否则连续在榜周数会被重复观测虚增，plan-next 会据此
    对噪声开 OPEN。
    """
    by_week: dict[int, set[str]] = defaultdict(set)
    current_index = _week_index(current_week)
    for report in previous:
        index = _week_index(_iso_week(str(report["window"]["end"])))
        if index < current_index:
            by_week[index].update(item["path"] for item in report.get("topHotspots", []))
    return sorted(by_week.items(), reverse=True)


def hotspot_persistence(top: list[dict[str, Any]], previous: list[dict[str, Any]], *, current_window_end: str) -> list[dict[str, Any]]:
    """Consecutive ISO weeks each current hotspot has stayed in the Top-N, counting the current week as 1."""
    current_index = _week_index(_iso_week(current_window_end))
    history = _weekly_top_paths(previous, _iso_week(current_window_end))
    result = []
    for item in top:
        streak = 1
        expected = current_index - 1
        for index, paths in history:
            if index != expected or item["path"] not in paths:
                break
            streak += 1
            expected -= 1
        result.append({"path": item["path"], "ownerScope": item["ownerScope"], "consecutiveWeeksInTopN": streak})
    return result


def owner_scope_weak_points(
    production: dict[str, bytes],
    complexity: dict[str, dict[str, int]],
    clone_lines: dict[str, int],
    dead_candidates: list[dict[str, str]],
    policy: dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Aggregate weak points per owner scope so reviewers see where debt concentrates."""
    advisory = policy["thresholds"]["file_lines"]["advisory"]
    block = policy["thresholds"]["file_lines"]["block"]
    cyclomatic = policy["thresholds"]["complexity"]["cyclomatic_advisory"]
    cognitive = policy["thresholds"]["complexity"]["cognitive_advisory"]
    scopes: dict[str, dict[str, int]] = defaultdict(lambda: {
        "files": 0, "overAdvisory": 0, "overBlock": 0, "overComplexity": 0, "cloneLines": 0, "deadCandidates": 0,
    })
    for path, body in production.items():
        scope = scopes[reuse_scope_key(path)]
        lines = line_count(body)
        scope["files"] += 1
        scope["overAdvisory"] += lines > advisory
        scope["overBlock"] += lines > block
        metric = complexity.get(path, {})
        scope["overComplexity"] += (
            metric.get("maxCyclomatic", 0) > cyclomatic or metric.get("maxCognitive", 0) > cognitive
        )
        scope["cloneLines"] += clone_lines.get(path, 0)
    for item in dead_candidates:
        if item["path"].startswith("<"):
            continue
        scopes[reuse_scope_key(item["path"])]["deadCandidates"] += 1
    ranked = sorted(
        ({"ownerScope": scope, **values} for scope, values in scopes.items()),
        key=lambda item: (
            -item["overBlock"], -item["overAdvisory"], -item["overComplexity"], -item["cloneLines"],
            -item["deadCandidates"], item["ownerScope"],
        ),
    )
    return ranked[:limit]


def _score_hotspots(
    production: dict[str, bytes],
    churn: dict[str, dict[str, int]],
    clone_lines: dict[str, int],
    policy: dict[str, Any],
) -> tuple[dict[str, dict[str, int]], list[dict[str, Any]]]:
    """Per-file complexity facts plus `churn × change-frequency × health` hotspot scores."""
    thresholds = policy["thresholds"]
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
            lines / thresholds["file_lines"]["advisory"],
            maximum_cyclomatic / thresholds["complexity"]["cyclomatic_advisory"],
            maximum_cognitive / thresholds["complexity"]["cognitive_advisory"],
            1.0 + clone_lines.get(path, 0) / max(1, lines),
        )
        score = activity["churn"] * (1.0 + math.log2(1 + activity["changeFrequency"])) * health
        if score:
            hotspots.append({
                "path": path, "ownerScope": reuse_scope_key(path), "score": round(score, 3),
                "healthFactor": round(health, 4), "lines": lines, "cloneLines": clone_lines.get(path, 0),
                **activity, **complexity[path],
            })
    return complexity, hotspots


def _report_identity(
    *, head_sha: str, window: dict[str, Any], policy: dict[str, Any], delivery_run_pages: object, tools: dict[str, Any],
) -> dict[str, str]:
    """身份只绑定输入（head、窗口、policy、实现、delivery 数据、工具），不绑定观测时刻。"""
    policy_digest = canonical_digest(policy)
    implementation_digest = canonical_digest({
        f"quwoquan_ops/gate/code_health_delta/{name}": "sha256:" + hashlib.sha256(
            Path(__file__).with_name(name).read_bytes()
        ).hexdigest()
        for name in ("weekly.py", "metrics.py", "classification.py")
    })
    delivery_outcomes_digest = canonical_digest(delivery_run_pages)
    identity = canonical_digest({
        "headSha": head_sha, "window": window, "policyDigest": policy_digest,
        "implementationDigest": implementation_digest, "deliveryOutcomesDigest": delivery_outcomes_digest,
        "tools": tools,
    })
    return {
        "identityDigest": identity, "policyDigest": policy_digest,
        "implementationDigest": implementation_digest, "deliveryOutcomesDigest": delivery_outcomes_digest,
    }


def _observed_value(observed_at: datetime | None) -> str:
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include timezone")
    return observed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def analyze_weekly(
    repo: Path,
    *,
    head: str,
    policy: dict[str, Any],
    cloc_executable: str = "cloc",
    delivery_run_pages: object = None,
    observed_at: datetime | None = None,
    previous_reports: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    repo = repo.resolve()
    head_sha = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}").strip()
    end = _commit_time(repo, head_sha)
    start = end - timedelta(days=90)
    paths = _tracked_paths(repo, head_sha)
    all_blobs = _clean_current_blobs(repo, head_sha, paths)
    classified = {path: classify_path(path, policy) for path in all_blobs}
    production = {path: body for path, body in all_blobs.items() if classified[path] == "handwritten-production"}
    test_blobs = {path: body for path, body in all_blobs.items() if classified[path] == "test"}
    categories: dict[str, dict[str, int]] = {name: {"files": 0, "lines": 0} for name in policy["source_categories"]}
    for path, body in all_blobs.items():
        categories[classified[path]]["files"] += 1
        categories[classified[path]]["lines"] += line_count(body)
    history = [
        {"ageWeeks": age, "committerDate": _commit_time(repo, sha).isoformat(timespec="seconds"), **_cloc(repo, sha, cloc_executable)}
        for age, sha in _historical_commits(repo, head_sha, end, (13, 4, 1, 0))
    ]
    clone_lines, clone_groups = _clone_facts(production, policy["thresholds"]["duplication"]["block_lines"])
    complexity, hotspots = _score_hotspots(production, _churn(repo, head_sha, start), clone_lines, policy)
    top = sorted(hotspots, key=lambda item: (-item["score"], item["path"]))[: policy["report"]["weekly_top_hotspots"]]
    tools = {"cloc": history[-1]["clocVersion"] if history else "unavailable", "builtinMetrics": 1}
    dead_candidates = _dead_candidates(repo)
    window = {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"), "days": 90}
    observed_value = _observed_value(observed_at)
    tiers = list(policy["report"]["size_observation_tiers"])
    previous = _ordered_previous(previous_reports, head_sha)
    complexity_thresholds = policy["thresholds"]["complexity"]
    report = {
        "schema": WEEKLY_SCHEMA, "terminal": "REPORT_ONLY",
        "headSha": head_sha, "window": window,
        **_report_identity(head_sha=head_sha, window=window, policy=policy, delivery_run_pages=delivery_run_pages, tools=tools),
        "policyId": policy["policy_id"], "observedAt": observed_value,
        "tools": tools,
        "growthHistory": history, "categories": categories,
        "summary": {"trackedFiles": len(paths), "handwrittenProductionFiles": len(production), "cloneGroupCount": clone_groups, "deadCandidateCount": len(dead_candidates)},
        "sizeDistribution": {
            "tiers": tiers,
            "production": _size_distribution(production, tiers),
            "test": _size_distribution(test_blobs, tiers),
        },
        "complexitySummary": {
            "functionCount": sum(item["functions"] for item in complexity.values()),
            "overCyclomaticAdvisory": sum(item["maxCyclomatic"] > complexity_thresholds["cyclomatic_advisory"] for item in complexity.values()),
            "overCognitiveAdvisory": sum(item["maxCognitive"] > complexity_thresholds["cognitive_advisory"] for item in complexity.values()),
        },
        "topHotspots": top, "deadCodeCandidates": dead_candidates,
        "ownerScopeWeakPoints": owner_scope_weak_points(production, complexity, clone_lines, dead_candidates, policy),
        "deliveryOutcomes": delivery_outcomes(
            delivery_run_pages, end=end,
            regression_percent=policy["performance"]["delivery_outcome_regression_percent"],
        ),
        "generatedAt": observed_value,
        "authority": {"blocksPullRequests": False, "createsOwnerOpen": False, "automaticRemediation": False},
    }
    report["ratchet"] = ratchet_trend(report, previous, tiers)
    report["hotspotPersistence"] = {
        "historyReports": len(previous),
        "historyWeeks": len(_weekly_top_paths(previous, _iso_week(window["end"]))),
        "topN": policy["report"]["weekly_top_hotspots"],
        "items": hotspot_persistence(top, previous, current_window_end=window["end"]),
    }
    return report
