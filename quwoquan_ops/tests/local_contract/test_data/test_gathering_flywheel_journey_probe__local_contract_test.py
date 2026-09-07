# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[4]
PROBE_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/circle-service/smoke"
    / "run_gathering_flywheel_journey_probe.py"
)
SPEC = importlib.util.spec_from_file_location("gathering_flywheel_journey_probe", PROBE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load gathering flywheel journey probe")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def test_ops_case_result_binds_candidate_without_app_uat_release_fields(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    report_path = evidence_root / "env/alpha/runs/gathering/report.json"
    report_path.parent.mkdir(parents=True)
    report = {
        "status": "passed",
        "failureCategory": "",
        "startedAt": "2026-09-05T20:00:00Z",
        "endedAt": "2026-09-05T20:01:00Z",
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")

    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    contract_graph = candidate_dir / "contract_graph.json"
    contract_graph.write_text(
        json.dumps({"sources": [{"path": "circle/gathering/operations.yaml", "sha256": "1" * 64}]}),
        encoding="utf-8",
    )
    manifest = {
        "sourceRevision": "a" * 40,
        "packageDigest": _digest("b"),
        "configurationDigest": _digest("c"),
        "release": {
            "candidate": {
                "releaseDigest": _digest("d"),
                "releaseId": "release-should-not-enter-ops-case-result",
            }
        },
    }
    snapshot = {
        "baselineId": _digest("e"),
        "candidateDir": str(candidate_dir),
    }

    original_output_root = PROBE.output_root
    PROBE.output_root = lambda: evidence_root
    try:
        case_path = PROBE._write_case_result(
            SimpleNamespace(env="alpha"),
            report,
            report_path=report_path,
            snapshot=snapshot,
            manifest=manifest,
            contract_graph=contract_graph,
        )
    finally:
        PROBE.output_root = original_output_root

    result = json.loads(case_path.read_text(encoding="utf-8"))
    assert result["producer"] == "ops"
    assert result["layer"] == "environment_acceptance"
    assert result["specRef"] == (
        "specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008"
    )
    assert result["candidateDigest"] == manifest["packageDigest"]
    assert "releaseDigest" not in result
    assert "releaseId" not in result
    assert "deviceRegistered" not in result
