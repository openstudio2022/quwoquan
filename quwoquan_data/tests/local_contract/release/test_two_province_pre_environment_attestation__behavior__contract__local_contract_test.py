"""Pre-environment two-province attestations must derive from immutable evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.release_layout import attestation_root, payload_file  # noqa: E402
from content.release.canonical import two_province_closure as closure  # noqa: E402


RELEASE_ID = "20260714--travel-homepage-coverage--cn-zhejiang-sichuan--m3-001"
ZHEJIANG_EXECUTION = "20260714--travel-homepage-coverage--cn-zhejiang--m3-001"
SICHUAN_EXECUTION = "20260714--travel-homepage-coverage--cn-sichuan--m3-001"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_execution(root: Path, execution_id: str, entity_type: str, name: str) -> None:
    (root / "0.plan").mkdir(parents=True, exist_ok=True)
    (root / "0.plan" / "execution_spec.yaml").write_text(
        yaml.safe_dump(
            {
                "scope": {
                    "coverageTargets": [
                        {"name": name, "entityType": entity_type, "geoTagRef": "Topic/test"}
                    ]
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_json(
        root / "sources/qualification/result.json",
        {
            "executionId": execution_id,
            "policyRevision": "encyclopedia-primary",
            "verifiedAt": "2026-07-14T00:00:00Z",
            "passed": True,
            "targets": [
                {
                    "name": name,
                    "status": "confirmed",
                    "sourceCatalogRef": f"entities/{entity_type}/{name}/evidence/source_catalog.json",
                    "primarySource": {
                        "sourceKind": "wikipedia",
                        "canonicalUrl": f"https://zh.wikipedia.org/wiki/{name}",
                        "extractor": "wikipedia_api",
                        "snapshotHash": "sha256:" + "a" * 64,
                        "evidenceRef": f"evidence/sources/{name}/meta.json",
                    },
                }
            ],
            "issues": [],
        },
    )


def _fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    release = tmp_path / "releases" / RELEASE_ID
    execution_roots = {
        ZHEJIANG_EXECUTION: tmp_path / "tasks" / ZHEJIANG_EXECUTION,
        SICHUAN_EXECUTION: tmp_path / "tasks" / SICHUAN_EXECUTION,
    }
    _write_execution(execution_roots[ZHEJIANG_EXECUTION], ZHEJIANG_EXECUTION, "地点/景区", "普陀山")
    _write_execution(execution_roots[SICHUAN_EXECUTION], SICHUAN_EXECUTION, "地点/景区", "海螺沟")
    _write_json(
        payload_file(release, "release.json"),
        {
            "schema": "quwoquan_data.release",
            "releaseId": RELEASE_ID,
            "executionIds": [ZHEJIANG_EXECUTION, SICHUAN_EXECUTION],
        },
    )
    _write_json(
        payload_file(release, "desired_state.json"),
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": RELEASE_ID,
            "desiredRefs": {
                "creators": [],
                "entities": ["地点/景区/普陀山", "地点/景区/海螺沟"],
                "posts": [],
            },
        },
    )
    monkeypatch.setattr(closure, "execution_root", lambda execution_id: execution_roots[execution_id])
    monkeypatch.setattr(closure, "execution_readiness_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        closure,
        "homepage_media_completeness_report",
        lambda execution_id: {"executionId": execution_id, "passed": True},
    )
    monkeypatch.setattr(
        closure,
        "expected_entity_refs",
        lambda: {"浙江省": {"地点/景区/普陀山"}, "四川省": {"地点/景区/海螺沟"}},
    )
    return release


def test_two_province_pre_environment_attestation__derives_static_closure__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _fixture(monkeypatch, tmp_path)

    report = closure.build_pre_environment_attestations(release)

    assert report["entityCount"] == 2
    assert report["executionIds"] == [SICHUAN_EXECUTION, ZHEJIANG_EXECUTION]
    coverage = json.loads((attestation_root(release) / "coverage_closure.json").read_text(encoding="utf-8"))
    assert coverage["approvedEntityRefs"] == ["地点/景区/普陀山", "地点/景区/海螺沟"]
    assert not (attestation_root(release) / "importer_api_closure.json").exists()

    repeat = closure.build_pre_environment_attestations(release)

    assert repeat == report
    assert json.loads((attestation_root(release) / "coverage_closure.json").read_text(encoding="utf-8")) == coverage


def test_two_province_pre_environment_attestation__blocks_partial_payload__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _fixture(monkeypatch, tmp_path)
    payload = json.loads(payload_file(release, "desired_state.json").read_text(encoding="utf-8"))
    payload["desiredRefs"]["entities"] = ["地点/景区/普陀山"]
    _write_json(payload_file(release, "desired_state.json"), payload)

    with pytest.raises(closure.TwoProvinceClosureError, match="coverage is incomplete"):
        closure.build_pre_environment_attestations(release)
