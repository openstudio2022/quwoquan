"""Weekly 历史对比、hotspot 持续期与 Markdown 渲染只读取报告字段。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t4
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate import report_code_health_weekly
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.gate.code_health_delta.render import debt_delta, render_candidate, render_weekly, review_skeleton
from quwoquan_ops.gate.code_health_delta.weekly import (
    WEEKLY_SCHEMA, analyze_weekly, hotspot_persistence, ratchet_trend,
)
from quwoquan_ops.tests.support.code_health_delta_test_support import commit, init_repo, policy_path, write

OBSERVED = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)


def _fake_cloc(tmp_path: Path) -> Path:
    fake = tmp_path / "cloc"
    fake.write_text(
        "#!/bin/sh\nprintf '%s' '{\"header\":{\"cloc_version\":\"fixture\"},\"SUM\":{\"nFiles\":2,\"blank\":0,\"comment\":0,\"code\":42}}'\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def _weekly(repo: Path, head: str, cloc: Path, previous: list[dict] = ()) -> dict:
    return analyze_weekly(
        repo, head=head, policy=load_policy(policy_path(repo)), cloc_executable=str(cloc),
        observed_at=OBSERVED, previous_reports=list(previous),
    )


def _complex_source(branches: int) -> str:
    body = "\n".join(f"    if value == {index}:\n        total += {index}" for index in range(branches))
    return f"def hot(value):\n    total = 0\n{body}\n    return total\n"


def test_weekly_history_derives_ratchet_direction_and_hotspot_streak(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    cloc = _fake_cloc(tmp_path)
    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(20))
    first_head = commit(repo, "hot module")
    first = _weekly(repo, first_head, cloc)
    assert first["ratchet"]["comparisonStatus"] == "insufficient-history"
    assert first["hotspotPersistence"]["items"][0]["path"] == "quwoquan_ops/ci/hot.py"
    assert first["complexitySummary"]["overCyclomaticAdvisory"] == 1

    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(3))
    second_head = commit(repo, "simplify")
    same_week = _weekly(repo, second_head, cloc, previous=[first])
    metrics = same_week["ratchet"]["metrics"]
    assert same_week["ratchet"]["comparisonStatus"] == "comparable"
    assert same_week["ratchet"]["previousHeadSha"] == first_head
    assert metrics["overCyclomaticAdvisory"] == {"previous": 1, "current": 0, "direction": "improved"}
    assert metrics["cloneGroupCount"]["direction"] == "flat"
    # 同一 ISO 周内的重跑不算多期：连续在榜周数仍为 1，避免本地反复运行虚增热点。
    assert same_week["hotspotPersistence"]["historyWeeks"] == 0
    assert {item["consecutiveWeeksInTopN"] for item in same_week["hotspotPersistence"]["items"]} == {1}

    last_week = _shift_window_end(first, weeks=1)
    second = _weekly(repo, second_head, cloc, previous=[last_week])
    assert second["hotspotPersistence"]["historyWeeks"] == 1
    streak = {item["path"]: item["consecutiveWeeksInTopN"] for item in second["hotspotPersistence"]["items"]}
    assert streak["quwoquan_ops/ci/hot.py"] == 2

    # 与当前 head 相同的历史报告不参与对比；schema 漂移 fail-closed。
    same_head = _weekly(repo, second_head, cloc, previous=[second, first])
    assert same_head["ratchet"]["previousHeadSha"] == first_head
    assert ratchet_trend(second, [], [800])["comparisonStatus"] == "insufficient-history"
    with pytest.raises(ValueError, match="schema"):
        _weekly(repo, second_head, cloc, previous=[{"schema": "other", "window": {"end": "x"}}])


def _shift_window_end(report: dict, *, weeks: int) -> dict:
    shifted = json.loads(json.dumps(report))
    end = datetime.fromisoformat(report["window"]["end"]) - timedelta(weeks=weeks)
    shifted["window"]["end"] = end.isoformat(timespec="seconds")
    return shifted


def test_hotspot_persistence_counts_only_consecutive_iso_weeks() -> None:
    top = [{"path": "a.py", "ownerScope": "s"}, {"path": "b.py", "ownerScope": "s"}, {"path": "c.py", "ownerScope": "s"}]
    current = "2026-09-21T00:00:00+00:00"

    def report(weeks_ago: int, *paths: str) -> dict:
        end = (datetime.fromisoformat(current) - timedelta(weeks=weeks_ago)).isoformat(timespec="seconds")
        return {"schema": WEEKLY_SCHEMA, "window": {"end": end}, "topHotspots": [{"path": path} for path in paths]}

    history = [
        report(1, "a.py"), report(1, "a.py", "c.py"),   # 同一周两次观测只算一期
        report(2, "b.py", "a.py"),                       # b 在两周前出现但上周缺席：不连续
        report(3, "a.py"),
    ]
    items = {item["path"]: item["consecutiveWeeksInTopN"] for item in hotspot_persistence(top, history, current_window_end=current)}
    assert items == {"a.py": 4, "b.py": 1, "c.py": 2}
    # 同周或未来的报告不进入历史。
    assert hotspot_persistence(top, [report(0, "a.py")], current_window_end=current)[0]["consecutiveWeeksInTopN"] == 1


def test_candidate_markdown_leads_with_blockers_and_debt_delta(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    block = load_policy(policy_path(repo))["thresholds"]["file_lines"]["block"]
    write(repo, "quwoquan_ops/ci/huge.py", "value = 1\n" * (block + 1))
    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(20))
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="full")
    markdown = render_candidate(report)
    assert markdown.startswith("# Code Health Delta — GATE_BLOCK")
    assert "`CODE_HEALTH.NEW_FILE_OVER_BLOCK` `quwoquan_ops/ci/huge.py`" in markdown
    assert "recovery: `split_or_reduce_new_file_below_block_threshold`" in markdown
    assert "`CODE_HEALTH.COMPLEXITY_ADVISORY` × 1" in markdown
    assert markdown.index("## Blockers") < markdown.index("## Advisories")
    delta = debt_delta(report)
    assert delta["newOversizedFiles"] == 1 and delta["newComplexFunctions"] == 1
    skeleton = json.loads(review_skeleton(report))
    assert {(item["code"], item["verdict"]) for item in skeleton} >= {
        ("CODE_HEALTH.NEW_FILE_OVER_BLOCK", ""), ("CODE_HEALTH.COMPLEXITY_ADVISORY", ""),
    }
    assert "```json" in markdown


def test_cli_discovers_local_history_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _base = init_repo(tmp_path)
    cloc = _fake_cloc(tmp_path)
    monkeypatch.setattr(report_code_health_weekly, "ROOT", repo)
    policy = load_policy(policy_path(repo))
    weekly_root = repo / policy["report"]["root"] / "weekly"

    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(20))
    first_head = commit(repo, "hot module")
    assert report_code_health_weekly.main(["--head", first_head, "--policy", str(policy_path(repo)), "--cloc", str(cloc)]) == 0
    first_path = next(weekly_root.glob("*/report.json"))
    first = json.loads(first_path.read_text(encoding="utf-8"))
    assert first["ratchet"]["comparisonStatus"] == "insufficient-history"
    # 把首期报告的窗口推到上一周，模拟真实的周度节律。
    first_path.write_text(json.dumps(_shift_window_end(first, weeks=1)), encoding="utf-8")

    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(2))
    second_head = commit(repo, "simplify")
    # 不传 --previous：缺省从本地既有报告发现上期（排除同 head），本地也能看到棘轮方向。
    assert report_code_health_weekly.main(["--head", second_head, "--policy", str(policy_path(repo)), "--cloc", str(cloc)]) == 0
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in weekly_root.glob("*/report.json")]
    second = next(item for item in reports if item["headSha"] == second_head)
    assert second["ratchet"]["comparisonStatus"] == "comparable"
    assert second["ratchet"]["previousHeadSha"] == first_head
    assert second["ratchet"]["metrics"]["overCyclomaticAdvisory"]["direction"] == "improved"
    assert second["hotspotPersistence"]["items"][0]["consecutiveWeeksInTopN"] == 2

    discovered = report_code_health_weekly.discover_local_previous(weekly_root, current_head=second_head)
    assert [json.loads(path.read_text(encoding="utf-8"))["headSha"] for path in discovered] == [first_head]
    assert report_code_health_weekly.discover_local_previous(tmp_path / "missing", current_head=second_head) == []


def test_weekly_markdown_and_cli_write_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo, _base = init_repo(tmp_path)
    cloc = _fake_cloc(tmp_path)
    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(20))
    head = commit(repo, "hot module")
    first = _weekly(repo, head, cloc)
    previous_path = tmp_path / "previous.json"
    previous_path.write_text(json.dumps(first), encoding="utf-8")
    write(repo, "quwoquan_ops/ci/hot.py", _complex_source(2))
    head = commit(repo, "simplify")

    monkeypatch.setattr(report_code_health_weekly, "ROOT", repo)
    output = tmp_path / "report.json"
    summary = tmp_path / "summary.md"
    code = report_code_health_weekly.main([
        "--head", head, "--policy", str(policy_path(repo)), "--cloc", str(cloc),
        "--previous", str(previous_path), "--output", str(output), "--summary-markdown", str(summary),
    ])
    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    markdown = summary.read_text(encoding="utf-8")
    assert markdown == render_weekly(report)
    assert "## 棘轮指标（对比上期：comparable）" in markdown
    assert "| overCyclomaticAdvisory | 1 | 0 | ↓ 改善 |" in markdown
    assert "## Owner scope 薄弱点 Top 5" in markdown
    assert "`quwoquan_ops/ci`" in markdown
    assert "history=1" in capsys.readouterr().out
