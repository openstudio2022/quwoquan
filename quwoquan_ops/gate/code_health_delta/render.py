"""Markdown projections of candidate and weekly code-health reports.

渲染只读取报告字段，不重算、不改写 terminal；同一份 JSON 在 CLI stdout、Review 输出、
hosted step summary 与 weekly 观测里得到同一段 Markdown。
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterable

_ADVISORY_PREVIEW = 8
_DIRECTION_LABEL = {"improved": "↓ 改善", "worsened": "↑ 恶化", "flat": "= 持平", "n/a": "无历史"}


def _measure(finding: dict[str, Any]) -> str:
    measure = finding.get("measure")
    if isinstance(measure, dict) and measure:
        return ", ".join(f"{key}={value}" for key, value in sorted(measure.items()) if key != "scopes")
    return ""


def _blockers(findings: Iterable[dict[str, Any]]) -> list[str]:
    lines = []
    for finding in findings:
        if finding["terminal"] != "GATE_BLOCK":
            continue
        detail = _measure(finding)
        lines.append(
            f"- `{finding['code']}` `{finding['path']}`"
            + (f" ({detail})" if detail else "")
            + f"\n  - recovery: `{finding.get('recovery', '')}`"
            + f"\n  - findingId: `{finding['findingId']}`"
        )
    return lines


def _advisories(findings: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if finding["terminal"] == "PR_WARN":
            grouped.setdefault(str(finding["code"]), []).append(finding)
    lines = []
    for code in sorted(grouped):
        items = grouped[code]
        lines.append(f"- `{code}` × {len(items)}")
        for finding in items[:_ADVISORY_PREVIEW]:
            symbol = f"::{finding['symbol']}" if finding.get("symbol") else ""
            detail = _measure(finding)
            lines.append(f"  - `{finding['path']}{symbol}`" + (f" ({detail})" if detail else ""))
            lines.append(f"    - findingId: `{finding['findingId']}`")
        if len(items) > _ADVISORY_PREVIEW:
            lines.append(f"  - … 另有 {len(items) - _ADVISORY_PREVIEW} 条，见 report.json")
    return lines


def debt_delta(report: dict[str, Any]) -> dict[str, int]:
    """提取当前告警的新增/恶化计数；不将其称为扣除消除项后的净债务。"""
    findings = report["findings"]
    complex_functions = 0
    for finding in findings:
        if finding["code"] != "CODE_HEALTH.COMPLEXITY_ADVISORY":
            continue
        measure = finding.get("measure") or {}
        complex_functions += 1 if measure.get("previousCyclomatic") is None else 0
    oversized_files = sum(
        1 for finding in findings if finding["code"] == "CODE_HEALTH.NEW_FILE_OVER_BLOCK"
    )
    duplicated_lines = int(report["summary"].get("duplicatedLines", 0))
    return {
        "newComplexFunctions": complex_functions,
        "worsenedFunctions": sum(
            1 for finding in findings
            if finding["code"] == "CODE_HEALTH.COMPLEXITY_ADVISORY"
            and (finding.get("measure") or {}).get("previousCyclomatic") is not None
        ),
        "newOversizedFiles": oversized_files,
        "duplicatedNewLines": duplicated_lines,
    }


def review_skeleton(report: dict[str, Any]) -> str:
    """Pre-filled ``findingReviews`` JSON for ``make calibrate-code-health``; verdict left blank."""
    reviews = [
        {"findingId": finding["findingId"], "verdict": ""}
        for finding in report["findings"]
        if finding["terminal"] in {"PR_WARN", "GATE_BLOCK"}
    ]
    return json.dumps(reviews, ensure_ascii=False, indent=2)


def render_candidate(report: dict[str, Any]) -> str:
    summary = report["summary"]
    categories = report["categorySummary"]
    delta = debt_delta(report)
    lines = [
        f"# Code Health Delta — {report['terminal']}",
        "",
        f"- range: `{report['baseSha'][:12]}..{report['headSha'][:12]}` "
        f"({report['candidateSource']}, mode={report['mode']}, policy={report['policyId']})",
    ]
    resolution = report.get("baseResolution") or {}
    if resolution.get("requested") == "auto":
        lines.append(f"- base: merge-base with `{resolution.get('ref')}`")
    lines.extend([
        f"- changed files: {summary['changedFiles']} (handwritten {summary['handwrittenFiles']}, "
        f"churn {summary['handwrittenChurn']}, structural scopes {len(summary.get('handwrittenScopes', []))})",
    ])
    if report['mode'] == 'full':
        lines.extend([
            f"- new-line duplication: {summary['duplicationPercent']}% "
            f"({summary['duplicatedLines']}/{summary['measuredNewLines']} measured lines)",
            "", "## 债务 delta", "",
            f"- 新增高复杂函数: {delta['newComplexFunctions']:+d}",
            f"- 复杂度恶化函数: {delta['worsenedFunctions']:+d}",
            f"- 重复的新行: {delta['duplicatedNewLines']:+d}",
            "- 上述为新增/恶化信号，不是净债务余额。",
        ])
    else:
        lines.extend([
            "- new-line duplication: unavailable（fast 未测量）",
            "- 复杂度: unavailable（fast 未测量）",
            "", "## 债务 delta", "",
        ])
    lines.extend([f"- 新越过 block 的文件: {delta['newOversizedFiles']:+d}", ""])
    measured_delta = report.get("debtDelta") or {}
    if measured_delta:
        labels = {"introduced": "新增", "worsened": "恶化", "resolved": "消除", "improved": "改善", "unchanged": "持平"}
        lines.append("### 可比较的阈值债务变化（各位置分别判定）")
        for key, label in labels.items():
            lines.append(f"- {label}: {measured_delta['summary'][key]}")
        lines.append(f"- 测量范围: `{measured_delta['scope']}`")
        lines.append(f"- 未测: {', '.join(measured_delta['unmeasured'])}")
        lines.append("")
    coverage = report.get("analysisCoverage") or {}
    if coverage:
        lines.append("### 分析能力边界")
        for status, count in sorted(Counter(coverage["complexity"].values()).items()):
            lines.append(f"- 复杂度 `{status}`: {count} 个路径")
        lines.append(f"- 重复检测: `{coverage['duplication']}`")
        lines.append(f"- 入口检测: `{coverage['repositoryEntry']['scope']}`；不是全仓调用图")
        lines.append("")
    blockers = _blockers(report["findings"])
    lines.append(f"## Blockers ({len(blockers)})")
    lines.append("")
    lines.extend(blockers or ["- 无"])
    lines.append("")
    advisories = _advisories(report["findings"])
    warn_count = sum(1 for item in report["findings"] if item["terminal"] == "PR_WARN")
    lines.append(f"## Advisories ({warn_count})")
    lines.append("")
    lines.extend(advisories or ["- 无"])
    lines.append("")
    lines.append("## 分类")
    lines.append("")
    for name in sorted(categories):
        item = categories[name]
        if item["files"]:
            lines.append(f"- {name}: files={item['files']} +{item['added']} -{item['deleted']}")
    lines.append("")
    lines.append("## findingReviews 骨架（填 verdict 后交给 make calibrate-code-health）")
    lines.append("")
    lines.append("```json")
    lines.append(review_skeleton(report))
    lines.append("```")
    return "\n".join(lines) + "\n"


def _int_or_dash(value: Any) -> str:
    return "-" if value is None else str(value)


def _weekly_measurements(report: dict[str, Any]) -> list[str]:
    lines = [f"- 观察分支: `{report.get('observationBranch') or 'unavailable'}`"]
    for name, measure in sorted((report.get("measurements") or {}).items()):
        lines.append(f"- {name}: `{measure['status']}` ({measure.get('reason', '见 exact evidence')})")
    return lines


def _dead_code_observation(report: dict[str, Any]) -> list[str]:
    reachability = (report.get("measurements") or {}).get("reachability", {})
    if reachability.get("status") == "unavailable":
        return ["## Dead code candidates — unavailable", "", f"- {reachability.get('reason', '未采集 exact 可达性证据')}", ""]
    dead = report.get("deadCodeCandidates", [])
    reasons = Counter(item["reason"] for item in dead)
    return [f"## Dead code candidates ({len(dead)})", "",
            *(f"- {reason}: {count}" for reason, count in sorted(reasons.items())), ""]


def _module_rows(report: dict[str, Any]) -> list[str]:
    weak = {item["ownerScope"]: item for item in report.get("ownerScopeWeakPoints", [])}
    modules = report.get("modules") or {}
    lines = ["| structural scope | tracked files | physical lines | >advisory | >block | complex | cloneLines | dead |",
             "|---|---|---|---|---|---|---|---|"]
    for scope in sorted(set(modules) | set(weak)):
        values = {**weak.get(scope, {}), **modules.get(scope, {})}
        cells = [_int_or_dash(values.get(key)) for key in
                 ("files", "physicalLines", "overAdvisory", "overBlock", "overComplexity", "cloneLines", "deadCandidates")]
        lines.append(f"| `{scope}` | " + " | ".join(cells) + " |")
    return lines


def render_weekly(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Weekly Code Health (report-only)",
        "",
        f"- head: `{report['headSha'][:12]}` window: {report['window']['start'][:10]} → {report['window']['end'][:10]}",
        f"- identity: `{report['identityDigest']}`",
        f"- tracked / handwritten files: {summary['trackedFiles']} / {summary['handwrittenProductionFiles']}",
        "",
        "## 增长趋势（cloc source LOC，first-parent）",
        "",
        "| weeks ago | files | source LOC |",
        "|---|---|---|",
    ]
    for item in report["growthHistory"]:
        lines.append(f"| {item['ageWeeks']} | {_int_or_dash(item['files'])} | {_int_or_dash(item['sourceLoc'])} |")
    lines.append("")
    lines.append("## 分类行数（物理行，非 cloc code）")
    lines.append("")
    for name, item in sorted(report["categories"].items()):
        lines.append(f"- {name}: files={item['files']} lines={item['lines']}")
    lines.append("")
    lines.extend(_weekly_measurements(report))
    lines.append("")
    ratchet = report.get("ratchet") or {}
    lines.append(f"## 棘轮指标（对比上期：{ratchet.get('comparisonStatus', 'insufficient-history')}）")
    lines.append("")
    lines.append("| metric | previous | current | direction |")
    lines.append("|---|---|---|---|")
    metrics = ratchet.get("metrics") or {}
    for name in sorted(metrics):
        item = metrics[name]
        lines.append(
            f"| {name} | {_int_or_dash(item['previous'])} | {_int_or_dash(item['current'])} | "
            f"{_DIRECTION_LABEL.get(item['direction'], item['direction'])} |"
        )
    lines.append("")
    lines.append("## 全模块结构 scope 健康事实")
    lines.append("")
    lines.append("结构 scope 不等同于Feature mutation authority；未测证据不能推导为健康。")
    lines.append("")
    lines.extend(_module_rows(report))
    lines.append("")
    persistence = {
        item["path"]: item["consecutiveWeeksInTopN"]
        for item in (report.get("hotspotPersistence") or {}).get("items", [])
    }
    lines.append(f"## Top hotspots ({len(report['topHotspots'])})")
    lines.append("")
    lines.append("| weeks in top | path | lines | maxCyc | maxCog | changes | churn |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in report["topHotspots"]:
        lines.append(
            f"| {persistence.get(item['path'], 1)} | `{item['path']}` | {item['lines']} | {item['maxCyclomatic']} | "
            f"{item['maxCognitive']} | {item['changeFrequency']} | {item['churn']} |"
        )
    lines.append("")
    lines.extend(_dead_code_observation(report))
    outcomes = report.get("deliveryOutcomes") or {}
    lines.append("## Delivery outcomes")
    lines.append("")
    lines.append(f"- status: `{outcomes.get('status')}` comparison: `{outcomes.get('comparisonStatus')}`")
    lines.append(f"- regression flags: `{json.dumps(outcomes.get('regressionFlags'), sort_keys=True)}`")
    return "\n".join(lines) + "\n"
