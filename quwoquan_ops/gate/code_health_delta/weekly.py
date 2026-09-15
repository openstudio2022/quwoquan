"""Weekly report-only growth, hotspot, clone, reachability, and delivery outcomes."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import tempfile
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from quwoquan_ops.ci.impact_planner_core import canonical_digest

from .classification import (
    classify_path, generated_provenance, generated_output_declarations, generated_classification_report,
)
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


def _commit_blobs(repo: Path, head: str, paths: Iterable[str]) -> dict[str, bytes]:
    """分批读取 exact commit 对象；既不读取工作树字节，也不移动 HEAD/index。"""
    selected = list(paths)
    result: dict[str, bytes] = {}
    for start in range(0, len(selected), 64):
        batch = selected[start:start + 64]
        completed = subprocess.run(
            ["git", "cat-file", "--batch"], cwd=repo,
            input="".join(f"{head}:{path}\n" for path in batch).encode(), capture_output=True, check=True,
        )
        cursor = 0
        for path in batch:
            end = completed.stdout.index(b"\n", cursor)
            header = completed.stdout[cursor:end].split()
            if len(header) != 3 or header[1] != b"blob":
                raise ValueError(f"exact blob unavailable: {head}:{path}")
            size = int(header[2])
            cursor = end + 1
            result[path] = completed.stdout[cursor:cursor + size]
            cursor += size + 1
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


def _classification_policy(repo: Path, sha: str, policy: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    rules = policy["classification"]
    sources = set(rules.get("generated_exact_sources", {}).values())
    sources.update(item["path"] for item in rules.get("generated_manifests", []))
    authoring = _authoring_policy(policy)
    tracked = set(paths)
    blobs = _commit_blobs(repo, sha, sorted(sources.intersection(tracked)))
    declarations = generated_output_declarations(authoring, blobs.get)
    outputs = set(declarations)
    # 两阶段都绑定同一 sha；声明缺失输出只返回 None，不借工作树或旧提交补齐。
    blobs.update(_commit_blobs(repo, sha, sorted((outputs & tracked) - blobs.keys())))
    source_digests = {path: "sha256:" + hashlib.sha256(blobs[path]).hexdigest() if path in blobs else None
                      for path in sorted(sources | outputs)}
    statuses: dict[str, Any] = {}
    provenance = generated_provenance(authoring, blobs.get, statuses=statuses)
    return {**authoring, "_generated_provenance": provenance, "_generated_statuses": statuses,
            "_generated_sources_digest": canonical_digest(source_digests)}


def _cloc(repo: Path, sha: str, executable: str, policy: dict[str, Any]) -> dict[str, Any]:
    # cloc 对所有历史点使用同一 canonical 输入范围，避免覆盖率源码与内容输出误伤。
    tracked = _tracked_paths(repo, sha)
    classification_policy = _classification_policy(repo, sha, policy, tracked)
    paths = [path for path in tracked
             if classify_path(path, classification_policy) in {"handwritten-production", "test"}]
    cache = repo / ".qwq_output/env/repo/local/code-health"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cloc-input-", dir=cache) as directory:
        root = Path(directory)
        materialized = []
        for offset in range(0, len(paths), 32):
            for path, body in _commit_blobs(repo, sha, paths[offset:offset + 32]).items():
                target = root / "source" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                materialized.append(str(target))
        manifest = root / "paths.txt"
        manifest.write_text("\n".join(materialized) + "\n", encoding="utf-8")
        config = root / "cloc-options.txt"
        config.write_text("", encoding="utf-8")
        raw = _run(repo, executable, "--skip-uniqueness", "--timeout=0", "--json", "--quiet",
                   f"--list-file={manifest}", f"--config={config}")
    payload = json.loads(str(raw))
    summary = payload.get("SUM")
    if not isinstance(summary, dict):
        raise ValueError(f"cloc output for {sha} lacks SUM")
    header = payload.get("header") or {}
    return {
        "sha": sha,
        "generatedSourcesDigest": classification_policy["_generated_sources_digest"],
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
        args = ["diff-tree", "--root", "--no-commit-id", "-r", "--numstat", "-z", "--no-renames", head]
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
    if pages is None or (isinstance(pages, dict) and pages.get("status") == "unavailable"):
        return {"status": "unavailable", "reason": "delivery-evidence-not-provided",
                "comparisonStatus": "insufficient-history", "regressionFlags": None}
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


def _ordered_previous(previous_reports: Iterable[dict[str, Any]], current_head: str, *, observation_branch: str | None = None) -> list[dict[str, Any]]:
    ordered = []
    for report in previous_reports:
        if not isinstance(report, dict) or report.get("schema") != WEEKLY_SCHEMA:
            raise ValueError("previous weekly report schema 非法")
        if report.get("headSha") == current_head or report.get("observationBranch") != observation_branch:
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
    limit: int | None = None,
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
            (metric.get("maxCyclomatic") or 0) > cyclomatic or (metric.get("maxCognitive") or 0) > cognitive
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


def _file_complexity(path: str, body: bytes) -> dict[str, Any]:
    import ast
    suffix = Path(path).suffix
    status = "available" if suffix == ".py" else "partial" if suffix in {".go", ".dart", ".java", ".ts", ".tsx", ".js", ".jsx"} else "unavailable"
    if suffix == ".py":
        try:
            ast.parse(body.decode("utf-8"))
        except (SyntaxError, UnicodeError):
            status = "unavailable"
    functions = function_metrics(path, body) if status != "unavailable" else []
    result = {"functions": len(functions), "maxCyclomatic": max((item.cyclomatic for item in functions), default=0),
              "maxCognitive": max((item.cognitive for item in functions), default=0)}
    if status == "unavailable":
        result = {key: None for key in result}
    return {**result, "status": status, "analyzer": "python-ast" if suffix == ".py" else "brace-heuristic-partial"}


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
        complexity[path] = _file_complexity(path, body)
        maximum_cyclomatic = complexity[path]["maxCyclomatic"] or 0
        maximum_cognitive = complexity[path]["maxCognitive"] or 0
        lines = line_count(body)
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


LANGUAGES = {".py": "Python", ".go": "Go", ".dart": "Dart", ".ts": "TypeScript", ".tsx": "TypeScript",
             ".js": "JavaScript", ".jsx": "JavaScript", ".swift": "Swift", ".java": "Java", ".kt": "Kotlin",
             ".kts": "Kotlin", ".sh": "Shell", ".md": "Markdown", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML"}


def aggregate_file_facts(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """所有维度只聚合同一逐文件物理行事实，不与 cloc code 混算。"""
    result: dict[str, Any] = {}
    for dimension, key in (("categories", "category"), ("languages", "language"), ("modules", "moduleScope")):
        rows: dict[str, dict[str, Any]] = {}
        for fact in facts:
            row = rows.setdefault(fact[key], {"files": 0, "physicalLines": 0})
            row["files"] += 1
            row["physicalLines"] += fact["physicalLines"]
            if dimension == "modules":
                row["scopeKind"] = "structural"
                row["owner"] = {"status": "unavailable", "reason": "exact-feature-owner-not-provided"}
        result[dimension] = rows
    total = {"files": len(facts), "physicalLines": sum(item["physicalLines"] for item in facts)}
    for dimension in ("categories", "languages", "modules"):
        if any(sum(row[key] for row in result[dimension].values()) != value for key, value in total.items()):
            raise ValueError(f"weekly aggregation conservation failed: {dimension}")
    result["conservation"] = {"status": "available", "matched": True, **total}
    return result


def _optional_evidence(evidence: object, head: str) -> dict[str, Any]:
    # 接收外部已有 exact 证据，不从代码规模推测 coverage 或 architecture 健康。
    if not isinstance(evidence, dict):
        return {"status": "unavailable", "reason": "exact-evidence-not-provided"}
    if evidence.get("headSha") != head or not evidence.get("exactRef"):
        return {"status": "unavailable", "reason": "evidence-head-or-exact-ref-mismatch"}
    return {"status": "supplied-unverified", "evidence": evidence, "authority": "none",
            "reason": "self-reported-head-and-ref-not-resolved-or-verified"}


def _growth_history(repo: Path, head: str, end: datetime, executable: str, policy: dict[str, Any], fast: bool) -> list[dict[str, Any]]:
    history = []
    for age in (13, 4, 1, 0):
        commits = _historical_commits(repo, head, end, (age,))
        row: dict[str, Any] = {"ageWeeks": age, "status": "unavailable", "files": None, "sourceLoc": None,
                               "inputCategories": ["handwritten-production", "test"], "countDuplicatePaths": True,
                               "sourceLocScope": MEASUREMENT_SPEC["sourceLoc"], "legacyScopeComparable": False}
        if fast or not commits:
            row["reason"] = "fast-not-measured" if fast else "historical-commit-missing"
        else:
            sha = commits[0][1]
            row.update(sha=sha, committerDate=_commit_time(repo, sha).isoformat(timespec="seconds"))
            try:
                row.update(_cloc(repo, sha, executable, policy), status="available")
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                row["reason"] = f"cloc-unavailable:{type(exc).__name__}"
        history.append(row)
    return history


MEASUREMENT_SPEC = {
    "schema": "quwoquan.weekly-measurement.v2",
    "physicalLines": "all-tracked-blob-text-lines; binary-not-applicable; includes-vendor",
    "sourceLoc": "cloc-code; canonical-handwritten-production-and-test-only; duplicate-paths-counted",
    "sourceLocLegacyComparable": False,
    "clocOptions": ["--skip-uniqueness", "--timeout=0", "--json", "--quiet", "exact-blob-list", "empty-config"],
    "classification": "authoring-policy-plus-per-commit-generated-source-and-output-blobs; manifest-sha256-v2",
    "history": "first-parent-committer-date; 90-day-churn",
}


def _authoring_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """运行时派生键不属于 authoring policy，不能把工作树 provenance 带进身份。"""
    return {key: value for key, value in policy.items() if not key.startswith("_")}


def _comparable_history(current: dict, previous: list[dict]) -> tuple[list[dict], dict]:
    keys = ("observationBranch", "mode", "policyDigest", "implementationDigest", "toolchainDigest", "measurementSpecDigest")
    accepted, excluded = [], []
    for report in previous:
        reasons = [key for key in keys if key not in report or report[key] != current.get(key)]
        if reasons:
            excluded.append({"headSha": report.get("headSha"), "reasons": reasons})
        else:
            accepted.append(report)
    status = "comparable" if accepted else "incomparable" if excluded else "insufficient-history"
    return accepted, {"status": status, "excluded": excluded, "acceptedReports": len(accepted),
                      "snapshotIdentityRequiredEqual": False}


def _report_identity(
    *, head_sha: str, window: dict[str, Any], policy: dict[str, Any], delivery_run_pages: object, tools: dict[str, Any],
    observation_branch: str | None = None, evidence: object = None, mode: str = "full",
    generated_sources_digest: str | None = None,
) -> dict[str, str]:
    """身份只绑定输入（head、窗口、policy、实现、delivery 数据、工具），不绑定观测时刻。"""
    policy_digest = canonical_digest(_authoring_policy(policy))
    implementation_digest = canonical_digest({
        f"quwoquan_ops/gate/code_health_delta/{name}": "sha256:" + hashlib.sha256(
            Path(__file__).with_name(name).read_bytes()
        ).hexdigest()
        for name in ("weekly.py", "metrics.py", "classification.py", "policy.py")
    })
    toolchain_digest = canonical_digest(tools)
    measurement_spec_digest = canonical_digest(MEASUREMENT_SPEC)
    delivery_outcomes_digest = canonical_digest(delivery_run_pages)
    identity = canonical_digest({
        "headSha": head_sha, "window": window, "policyDigest": policy_digest,
        "implementationDigest": implementation_digest, "deliveryOutcomesDigest": delivery_outcomes_digest,
        "tools": tools, "observationBranch": observation_branch, "evidence": evidence, "mode": mode,
        "measurementSpecDigest": measurement_spec_digest, "generatedSourcesDigest": generated_sources_digest,
    })
    return {
        "identityDigest": identity, "policyDigest": policy_digest,
        "implementationDigest": implementation_digest, "deliveryOutcomesDigest": delivery_outcomes_digest,
        "toolchainDigest": toolchain_digest, "measurementSpecDigest": measurement_spec_digest,
        "generatedSourcesDigest": generated_sources_digest,
    }


def _observed_value(observed_at: datetime | None) -> str:
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include timezone")
    return observed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _complexity_status(metrics: Iterable[dict[str, Any]]) -> str:
    statuses = {item["status"] for item in metrics}
    if not statuses or statuses == {"unavailable"}:
        return "unavailable"
    return "available" if statuses == {"available"} else "partial"


def _source_facts(repo: Path, head: str, paths: list[str], policy: dict[str, Any]) -> tuple[list, dict, dict, str, dict]:
    classification_policy = _classification_policy(repo, head, policy, paths)
    production: dict[str, bytes] = {}
    tests: dict[str, bytes] = {}
    facts = []
    for offset in range(0, len(paths), 16):
        for path, body in _commit_blobs(repo, head, paths[offset:offset + 16]).items():
            category = classify_path(path, classification_policy)
            binary = b"\0" in body[:8192]
            facts.append({"path": path, "category": category, "language": LANGUAGES.get(Path(path).suffix, "Other"),
                          "moduleScope": reuse_scope_key(path), "physicalLines": 0 if binary else line_count(body),
                          "physicalLinesStatus": "not-applicable-binary" if binary else "available", "bytes": len(body)})
            if not binary and category == "handwritten-production":
                production[path] = body
            elif not binary and category == "test":
                tests[path] = body
    return (facts, production, tests, classification_policy["_generated_sources_digest"],
            generated_classification_report(classification_policy, paths))


def _attach_owner_evidence(modules: dict, measurement: dict) -> None:
    if measurement["status"] != "supplied-unverified":
        return
    owners = measurement["evidence"].get("modules", {})
    if not isinstance(owners, dict):
        return
    for scope, row in modules.items():
        evidence = owners.get(scope)
        if isinstance(evidence, dict) and evidence.get("ownerIdentityRef") and evidence.get("resolvedOwner"):
            row["owner"] = {"status": "supplied-unverified", "authority": "none",
                            "reason": "owner-ref-not-resolved-or-verified", "suppliedEvidence": evidence}


def _measurement_states(supplied: dict, head: str, mode: str, complexity: dict) -> dict:
    result = {name: _optional_evidence(supplied.get(name), head)
              for name in ("coverage", "architecture", "reachability", "owner")}
    for name in ("duplication", "hotspots", "complexity"):
        result[name] = {"status": "unavailable" if mode == "fast" else "available",
                        "reason": "fast-not-measured" if mode == "fast" else "builtin-observation"}
    result["complexity"].update(files=complexity, status=_complexity_status(complexity.values()))
    return result


def _decorate_weak_points(rows: list, modules: dict, complexity: dict, mode: str) -> None:
    for row in rows:
        row.update(scopeKind="structural", owner=modules[row["ownerScope"]]["owner"], deadCandidates=None)
        scoped = [item for path, item in complexity.items() if reuse_scope_key(path) == row["ownerScope"]]
        row["complexityStatus"] = _complexity_status(scoped)
        if row["complexityStatus"] == "unavailable":
            row["overComplexity"] = None
        if mode == "fast":
            row["cloneLines"] = None


def _complexity_summary(complexity: dict, thresholds: dict, production_count: int) -> dict:
    status = _complexity_status(complexity.values())
    result = {
        "functionCount": sum(item["functions"] or 0 for item in complexity.values()),
        "overCyclomaticAdvisory": sum((item["maxCyclomatic"] or 0) > thresholds["cyclomatic_advisory"] for item in complexity.values()),
        "overCognitiveAdvisory": sum((item["maxCognitive"] or 0) > thresholds["cognitive_advisory"] for item in complexity.values()),
    }
    if status == "unavailable":
        result = {key: None for key in result}
    return {**result, "status": status,
            "unavailableFiles": production_count - sum(item["status"] != "unavailable" for item in complexity.values())}


def analyze_weekly(
    repo: Path,
    *,
    head: str,
    policy: dict[str, Any],
    cloc_executable: str = "cloc",
    delivery_run_pages: object = None,
    observed_at: datetime | None = None,
    previous_reports: Iterable[dict[str, Any]] = (),
    observation_branch: str | None = None,
    mode: str = "full",
    existing_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    head_sha = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}").strip()
    end = _commit_time(repo, head_sha)
    start = end - timedelta(days=90)
    paths = _tracked_paths(repo, head_sha)
    if mode not in {"full", "fast"}:
        raise ValueError("weekly mode must be full or fast")
    policy = _authoring_policy(policy)
    file_facts, production, test_blobs, sources_digest, generated_classification = _source_facts(repo, head_sha, paths, policy)
    aggregates = aggregate_file_facts(file_facts)
    history = _growth_history(repo, head_sha, end, cloc_executable, policy, mode == "fast")
    clone_lines, clone_groups = ({}, None) if mode == "fast" else _clone_facts(production, policy["thresholds"]["duplication"]["block_lines"])
    complexity, hotspots = ({}, []) if mode == "fast" else _score_hotspots(production, _churn(repo, head_sha, start), clone_lines, policy)
    top = sorted(hotspots, key=lambda item: (-item["score"], item["path"]))[: policy["report"]["weekly_top_hotspots"]]
    tools = {"cloc": history[-1].get("clocVersion", "unavailable"), "builtinMetrics": 1,
             "python": list(sys.version_info[:3]), "git": _git(repo, "--version").strip()}
    # 现有治理扫描读取工作树，不能冒充此 exact commit 的可达性证据。
    dead_candidates: list[dict[str, str]] = []
    supplied = existing_evidence or {}
    measurements = _measurement_states(supplied, head_sha, mode, complexity)
    _attach_owner_evidence(aggregates["modules"], measurements["owner"])
    for fact in file_facts:
        fact["complexity"] = complexity.get(fact["path"], {"status": "unavailable", "reason": "fast-or-nonproduction-not-measured"})
    window = {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"), "days": 90}
    observed_value = _observed_value(observed_at)
    tiers = list(policy["report"]["size_observation_tiers"])
    previous = _ordered_previous(previous_reports, head_sha, observation_branch=observation_branch)
    complexity_thresholds = policy["thresholds"]["complexity"]
    report = {
        "schema": WEEKLY_SCHEMA, "terminal": "REPORT_ONLY",
        "headSha": head_sha, "window": window, "observationBranch": observation_branch, "mode": mode,
        "inputScope": {"kind": "exact-git-commit-blobs", "headSha": head_sha, "worktreeBytesIncluded": False,
                       "trackedPaths": len(paths), "measurementMode": mode},
        "fileFacts": file_facts, **aggregates, "measurements": measurements,
        "generatedClassification": generated_classification,
        **_report_identity(head_sha=head_sha, window=window, policy=policy, delivery_run_pages=delivery_run_pages, tools=tools,
                           observation_branch=observation_branch, evidence=supplied, mode=mode,
                           generated_sources_digest=sources_digest),
        "measurementSpec": MEASUREMENT_SPEC,
        "policyId": policy["policy_id"], "observedAt": observed_value,
        "tools": tools,
        "growthHistory": history,
        "summary": {"trackedFiles": len(paths), "handwrittenProductionFiles": len(production), "cloneGroupCount": clone_groups, "deadCandidateCount": None},
        "sizeDistribution": {
            "tiers": tiers,
            "production": _size_distribution(production, tiers),
            "test": _size_distribution(test_blobs, tiers),
        },
        "complexitySummary": _complexity_summary(complexity, complexity_thresholds, len(production)),
        "topHotspots": top, "deadCodeCandidates": dead_candidates,
        "ownerScopeWeakPoints": owner_scope_weak_points(production, complexity, clone_lines, dead_candidates, policy),
        "deliveryOutcomes": delivery_outcomes(
            delivery_run_pages, end=end,
            regression_percent=policy["performance"]["delivery_outcome_regression_percent"],
        ),
        "generatedAt": observed_value,
        "authority": {"blocksPullRequests": False, "createsOwnerOpen": False, "automaticRemediation": False},
    }
    report["categories"] = {name: {**row, "lines": row["physicalLines"]} for name, row in aggregates["categories"].items()}
    _decorate_weak_points(report["ownerScopeWeakPoints"], aggregates["modules"], complexity, mode)
    previous, comparison = _comparable_history(report, previous)
    report["historyComparison"] = comparison
    report["ratchet"] = ratchet_trend(report, previous, tiers)
    report["ratchet"]["comparisonStatus"] = comparison["status"]
    report["ratchet"]["incomparableReports"] = comparison["excluded"]
    report["hotspotPersistence"] = {
        "historyReports": len(previous),
        "historyWeeks": len(_weekly_top_paths(previous, _iso_week(window["end"]))),
        "topN": policy["report"]["weekly_top_hotspots"],
        "items": hotspot_persistence(top, previous, current_window_end=window["end"]),
    }
    return report
