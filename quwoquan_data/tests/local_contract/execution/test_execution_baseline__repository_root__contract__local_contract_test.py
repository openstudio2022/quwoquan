from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from core.paths import REPO_ROOT
from content.execution import baseline


EXECUTION_ID = "20260715--travel-homepage-coverage--cn-zhejiang--canary-001"


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        execution_id=EXECUTION_ID,
        catalog=None,
        spec_doc=None,
        design_doc=None,
        acceptance_doc=None,
        execution_guide=None,
        command_matrix_doc=None,
        catalog_config=None,
        naming_rules=None,
        geo_band_rules=None,
        schema_files=[],
        config_files=[],
        output=None,
    )


def test_execution_baseline_defaults_use_repository_specs_not_data_subtree():
    assert baseline.DEFAULT_SPEC_DOC == REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/spec.md"
    assert baseline.DEFAULT_DESIGN_DOC == REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/design.md"
    assert baseline.DEFAULT_ACCEPTANCE_DOC == REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/acceptance.yaml"
    assert baseline.DEFAULT_EXECUTION_GUIDE.is_file()
    assert baseline.DEFAULT_COMMAND_MATRIX_DOC.is_file()


def test_execution_baseline_missing_input_writes_failed_report_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    execution_spec = tmp_path / "execution_spec.yaml"
    execution_spec.write_text(
        "executionId: " + EXECUTION_ID + "\nscope:\n  coverageTargets:\n    - entityType: 地点\n      name: 测试实体\n",
        encoding="utf-8",
    )
    progress = tmp_path / "execution_progress.json"
    progress.write_text(json.dumps({"executionId": EXECUTION_ID}), encoding="utf-8")
    catalog = tmp_path / "catalog.ndjson"
    catalog.write_text('{"entityId":"地点/测试实体"}\n', encoding="utf-8")
    packet = tmp_path / "baseline_freeze_packet.json"
    report = tmp_path / "baseline_report.json"
    missing = tmp_path / "missing.md"

    monkeypatch.setattr(baseline, "ensure_execution_work_package_layout", lambda _execution_id: tmp_path)
    monkeypatch.setattr(baseline, "execution_spec_path", lambda _execution_id: execution_spec)
    monkeypatch.setattr(baseline, "execution_progress_path", lambda _execution_id: progress)
    monkeypatch.setattr(baseline, "execution_catalog_path", lambda _execution_id: catalog)
    monkeypatch.setattr(baseline, "execution_baseline_freeze_packet_path", lambda _execution_id: packet)
    monkeypatch.setattr(baseline, "execution_shared_path", lambda _execution_id, _name: report)
    monkeypatch.setattr(baseline, "DEFAULT_SPEC_DOC", missing)
    monkeypatch.setattr(baseline, "DEFAULT_DESIGN_DOC", missing)
    monkeypatch.setattr(baseline, "DEFAULT_ACCEPTANCE_DOC", missing)
    monkeypatch.setattr(baseline, "DEFAULT_EXECUTION_GUIDE", missing)
    monkeypatch.setattr(baseline, "DEFAULT_COMMAND_MATRIX_DOC", missing)

    with pytest.raises(SystemExit) as exc_info:
        baseline.handle_baseline(_args())

    assert exc_info.value.code == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert any("spec-doc missing" in issue for issue in payload["issues"])
    assert payload["inputPaths"]["specDocPath"] == str(missing)
    assert not packet.exists()
