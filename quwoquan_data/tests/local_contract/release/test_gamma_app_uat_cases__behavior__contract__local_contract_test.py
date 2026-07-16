"""Gamma App UAT cases must derive only from the active homepage importer receipt."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json  # noqa: E402
from core.release_layout import payload_file  # noqa: E402
from content.release.environment import gamma_app_uat_cases as subject  # noqa: E402


def _release(root: Path) -> Path:
    release = root / "data/releases/20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-002"
    write_json(
        payload_file(release, "desired_state.json"),
        {
            "releaseId": release.name,
            "desiredRefs": {
                "entities": ["地点/景区/普陀山", "地点/自然景观/东钱湖", "地点/景区/海螺沟"]
            },
        },
    )
    return release


def _report(release_id: str) -> dict[str, object]:
    return {
        "releaseId": release_id,
        "env": "gamma",
        "dryRun": False,
        "issues": [],
        "skipped": [],
        "entityRefToHomepageId": {
            "地点/景区/普陀山": "homepage-putuo",
            "地点/自然景观/东钱湖": "homepage-dongqian",
            "地点/景区/海螺沟": "homepage-hailuogou",
        },
    }


def test_gamma_app_uat_cases__derive_all_imported_homepages__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release(tmp_path)
    run = tmp_path / "env/gamma/runs/data-release" / release.name / "apply-001"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)

    path = subject.write_gamma_app_uat_case_manifest(
        release_root=release,
        run_root=run,
        run_id="apply-001",
        importer_report=_report(release.name),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [case["homepageId"] for case in payload["cases"]] == [
        "homepage-putuo",
        "homepage-hailuogou",
        "homepage-dongqian",
    ]
    assert [case["title"] for case in payload["cases"]] == ["普陀山", "海螺沟", "东钱湖"]


def test_gamma_app_uat_cases__reject_incomplete_importer_mapping__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release(tmp_path)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    report = _report(release.name)
    del report["entityRefToHomepageId"]["地点/景区/海螺沟"]  # type: ignore[index]

    with pytest.raises(subject.GammaAppUatCaseError, match="does not exactly close"):
        subject.write_gamma_app_uat_case_manifest(
            release_root=release,
            run_root=tmp_path / "env/gamma/runs/data-release" / release.name / "apply-002",
            run_id="apply-002",
            importer_report=report,
        )
