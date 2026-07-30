"""Environment API proof must consume release-bound homepage cases exactly."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json  # noqa: E402
from content.release.environment import homepage_api_verification as subject  # noqa: E402
from content.release.model import DeploymentEnvironment  # noqa: E402


def _cases(root: Path, release_id: str, *, environment: DeploymentEnvironment) -> Path:
    path = root / f"env/{environment.value}/runs/data-release" / release_id / "apply-001" / "homepage_verification_cases.json"
    write_json(
        path,
        {
            "schema": "quwoquan_data.homepage_verification_case_manifest",
            "environment": environment.value,
            "releaseId": release_id,
            "runId": "apply-001",
            "importerReportRef": f"env/{environment.value}/runs/data-release/{release_id}/apply-001/homepage-import.json",
            "generatedAt": "2026-07-14T00:00:00Z",
            "cases": [{"entityRef": "地点/景区/测试实体甲", "homepageId": "homepage-putuo", "title": "测试实体甲"}],
        },
    )
    return path


class _PublicApiClientDouble:
    def __init__(self, *, base_url: str) -> None:
        assert base_url.startswith("https://")

    def get_json(self, path: str, *, page_id: str) -> SimpleNamespace:
        if path == "homepages/homepage-putuo":
            assert page_id == "entity.homepage.detail"
            payload = {
                "homepageId": "homepage-putuo",
                "title": "测试实体甲",
                "coverUrl": "https://media.test/putuo.jpg",
            }
        elif path == "homepages/homepage-putuo/introduction":
            assert page_id == "entity.homepage.introduction"
            payload = {
                "homepageId": "homepage-putuo",
                "displayName": "测试实体甲",
                "coverUrl": "https://media.test/putuo.jpg",
                "sections": [{"kind": "overview", "title": "概况"}],
            }
        else:
            return SimpleNamespace(status=404, payload={})
        return SimpleNamespace(status=200, payload=payload)


@pytest.mark.parametrize(
    "environment",
    [
        DeploymentEnvironment.ALPHA,
        DeploymentEnvironment.BETA,
        DeploymentEnvironment.GAMMA,
    ],
)
def test_homepage_api_verification__reads_dynamic_cases__local_contract(
    environment: DeploymentEnvironment,
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "20260714--travel-homepage-coverage--test-release-a--pilot-002"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "PublicApiClient", _PublicApiClientDouble)
    cases = _cases(tmp_path, release_id, environment=environment)
    report = subject.write_homepage_api_verification(
        environment=environment,
        release_id=release_id,
        run_id="api-001",
        case_manifest_path=cases,
        output_path=tmp_path / f"env/{environment.value}/runs/data-release" / release_id / "api-001/homepage-api-verification.json",
        api_base_url="https://api.example.invalid",
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["environment"] == environment.value
    assert payload["entities"][0]["homepageId"] == "homepage-putuo"


def test_homepage_api_verification__rejects_title_drift__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "20260714--travel-homepage-coverage--test-release-a--pilot-002"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(subject, "PublicApiClient", _PublicApiClientDouble)
    cases = _cases(tmp_path, release_id, environment=DeploymentEnvironment.GAMMA)
    with pytest.raises(subject.HomepageApiVerificationError, match="title mismatch"):
        # A stale case manifest must not be able to validate a different API object.
        payload = json.loads(cases.read_text(encoding="utf-8"))
        payload["cases"][0]["title"] = "错误标题"
        cases.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        subject.write_homepage_api_verification(
            environment=DeploymentEnvironment.GAMMA,
            release_id=release_id,
            run_id="api-002",
            case_manifest_path=cases,
            output_path=tmp_path / "env/gamma/runs/data-release" / release_id / "api-002/homepage-api-verification.json",
            api_base_url="https://api.example.invalid",
        )


def test_public_api_client__rejects_non_https_authority__local_contract() -> None:
    with pytest.raises(subject.PublicApiClientError, match="must be HTTPS"):
        subject.PublicApiClient(base_url="http://127.0.0.1:19000")
