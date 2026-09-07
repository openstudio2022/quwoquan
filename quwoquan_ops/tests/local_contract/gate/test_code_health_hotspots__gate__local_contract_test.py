"""Owner-scoped hotspot projection for Agent PRE and plan-next.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate import report_code_health_hotspots as hotspots
from quwoquan_ops.gate.code_health_delta.weekly import WEEKLY_SCHEMA


def _report(head: str, end: str, streaks: dict[str, int]) -> dict:
    return {
        "schema": WEEKLY_SCHEMA, "headSha": head, "window": {"end": end}, "observedAt": end,
        "sizeDistribution": {"tiers": [800, 1000, 2000]},
        "topHotspots": [
            {
                "path": path, "ownerScope": path.rsplit("/", 1)[0], "score": 10.0, "lines": 900,
                "maxCyclomatic": 20, "maxCognitive": 30, "cloneLines": 12, "changeFrequency": 4,
            }
            for path in streaks
        ],
        "hotspotPersistence": {
            "historyReports": 3, "topN": 20,
            "items": [
                {"path": path, "ownerScope": path.rsplit("/", 1)[0], "consecutiveWeeksInTopN": weeks}
                for path, weeks in streaks.items()
            ],
        },
        "ownerScopeWeakPoints": [
            {"ownerScope": "quwoquan_ops/gate", "files": 40, "overAdvisory": 3, "overBlock": 0, "overComplexity": 5, "cloneLines": 40, "deadCandidates": 1},
            {"ownerScope": "quwoquan_ops/ci", "files": 30, "overAdvisory": 1, "overBlock": 0, "overComplexity": 2, "cloneLines": 8, "deadCandidates": 0},
        ],
    }


def test_projection_filters_owner_and_flags_two_week_streaks(tmp_path: Path) -> None:
    older = _report("a" * 40, "2026-08-24T00:00:00+00:00", {"quwoquan_ops/gate/x.py": 1})
    newer = _report("b" * 40, "2026-08-31T00:00:00+00:00", {
        "quwoquan_ops/gate/x.py": 2, "quwoquan_ops/gate/y.py": 1, "quwoquan_ops/ci/z.py": 3,
    })
    for name, report in (("older", older), ("newer", newer)):
        target = tmp_path / name / "report.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(report), encoding="utf-8")

    latest = hotspots.latest_local_report(tmp_path)
    assert latest["headSha"] == "b" * 40
    projection = hotspots.project(latest, "quwoquan_ops/gate/")
    assert [item["path"] for item in projection["hotspots"]] == ["quwoquan_ops/gate/x.py", "quwoquan_ops/gate/y.py"]
    assert [item["actionable"] for item in projection["hotspots"]] == [True, False]
    assert projection["actionableCount"] == 1
    assert projection["ownerScopeWeakPoints"] == newer["ownerScopeWeakPoints"][:1]
    assert projection["thresholds"] == {"fileLinesAdvisory": 1000, "fileLinesBlock": 2000}
    text = hotspots.render(projection)
    assert "[ACTIONABLE] quwoquan_ops/gate/x.py weeks=2" in text
    assert "[observe] quwoquan_ops/gate/y.py weeks=1" in text
    assert "quwoquan_ops/ci/z.py" not in text


def test_unavailable_is_typed_and_does_not_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(hotspots, "latest_oci_report", lambda repository: None)
    code = hotspots.main(["--owner", "quwoquan_ops/gate", "--weekly-root", str(tmp_path / "missing"), "--json"])
    assert code == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["status"] == "unavailable"
    assert projection["hotspots"] == [] and projection["actionableCount"] == 0
    assert "no local weekly report" in projection["reason"]
