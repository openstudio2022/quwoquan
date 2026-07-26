"""Homepage verification cases derive only from an active importer receipt."""
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
from content.release.environment import homepage_verification_cases as subject  # noqa: E402
from content.release.model import DeploymentEnvironment  # noqa: E402


def _release(root: Path) -> Path:
    release = root / "data/releases/20260714--travel-homepage-coverage--test-release-a--pilot-002"
    write_json(
        payload_file(release, "desired_state.json"),
        {
            "releaseId": release.name,
            "desiredRefs": {
                "entities": ["地点/景区/测试实体甲", "地点/自然景观/测试实体乙", "地点/景区/测试实体丙"]
            },
        },
    )
    return release


def _report(release_id: str, *, environment: DeploymentEnvironment) -> dict[str, object]:
    return {
        "releaseId": release_id,
        "env": environment.value,
        "dryRun": False,
        "issues": [],
        "skipped": [],
        "entityRefToHomepageId": {
            "地点/景区/测试实体甲": "homepage-test-a",
            "地点/自然景观/测试实体乙": "homepage-test-b",
            "地点/景区/测试实体丙": "homepage-test-c",
        },
    }


@pytest.mark.parametrize(
    "environment",
    [
        DeploymentEnvironment.ALPHA,
        DeploymentEnvironment.BETA,
        DeploymentEnvironment.GAMMA,
    ],
)
def test_homepage_verification_cases__derive_all_imported_homepages__local_contract(
    environment: DeploymentEnvironment,
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release(tmp_path)
    run = tmp_path / f"env/{environment.value}/runs/data-release" / release.name / "apply-001"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)

    path = subject.write_homepage_verification_case_manifest(
        environment=environment,
        release_root=release,
        run_root=run,
        run_id="apply-001",
        importer_report=_report(release.name, environment=environment),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["environment"] == environment.value
    assert [case["entityRef"] for case in payload["cases"]] == sorted(
        report_entity_ref
        for report_entity_ref in _report(release.name, environment=environment)[
            "entityRefToHomepageId"
        ]
    )
    assert [case["homepageId"] for case in payload["cases"]] == [
        "homepage-test-c",
        "homepage-test-a",
        "homepage-test-b",
    ]
    assert [case["title"] for case in payload["cases"]] == ["测试实体丙", "测试实体甲", "测试实体乙"]


def test_homepage_verification_cases__reject_incomplete_importer_mapping__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release(tmp_path)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    report = _report(release.name, environment=DeploymentEnvironment.GAMMA)
    del report["entityRefToHomepageId"]["地点/景区/测试实体丙"]  # type: ignore[index]

    with pytest.raises(subject.HomepageVerificationCaseError, match="does not exactly close"):
        subject.write_homepage_verification_case_manifest(
            environment=DeploymentEnvironment.GAMMA,
            release_root=release,
            run_root=tmp_path / "env/gamma/runs/data-release" / release.name / "apply-002",
            run_id="apply-002",
            importer_report=report,
        )
