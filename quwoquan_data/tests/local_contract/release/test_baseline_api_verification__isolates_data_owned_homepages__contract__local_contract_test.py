from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import read_json, write_json
from content.release.environment import baseline_api_verification as verification
from content.release.environment.public_api_client import PublicApiResponse
from content.release.model import DeploymentEnvironment


class _PublicApiClient:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def get_json(
        self,
        path: str,
        *,
        query: dict[str, str] | None = None,
    ) -> PublicApiResponse:
        if path == "homepages/search":
            assert query == {"status": "published", "limit": "1"}
            return PublicApiResponse(
                status=200,
                payload={"items": [{"homepageId": "fixture-homepage", "title": "保留主页"}]},
            )
        if path == "homepages/homepage-old":
            return PublicApiResponse(status=410, payload={"code": "ENTITY.USER.homepage_offline"})
        if path == "homepages/fixture-homepage":
            return PublicApiResponse(
                status=200,
                payload={"homepageId": "fixture-homepage", "title": "保留主页"},
            )
        raise AssertionError(f"unexpected API path: {path}")


def _import_report(path: Path) -> None:
    write_json(
        path,
        {
            "releaseId": "baseline-release",
            "env": "gamma",
            "dryRun": False,
            "sourceOwner": "qwq_data",
            "mode": "sync",
            "issues": [],
            "skipped": [],
            "projected": 0,
            "entityRefToHomepageId": {},
            "offlined": ["homepage-old"],
        },
    )


def test_empty_baseline_verifies_offlined_and_preserved_homepages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_report = tmp_path / "env/gamma/runs/data-release/baseline-release/import/homepage-import.json"
    output = tmp_path / "env/gamma/runs/data-release/baseline-release/verify/baseline-api-verification.json"
    _import_report(import_report)
    monkeypatch.setattr(verification, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(verification, "PublicApiClient", _PublicApiClient)

    verification.write_baseline_api_verification(
        environment=DeploymentEnvironment.GAMMA,
        release_id="baseline-release",
        run_id="verify",
        importer_report_path=import_report,
        output_path=output,
        api_base_url="https://gamma-api.test",
        insecure_tls=True,
        resolve_host="127.0.0.1",
    )

    payload = read_json(output)
    assert payload["passed"] is True
    assert payload["offlined"] == [{"homepageId": "homepage-old", "status": 410}]
    assert payload["preserved"] == {
        "homepageId": "fixture-homepage",
        "title": "保留主页",
        "status": 200,
    }


def test_empty_baseline_allows_a_clean_environment_without_a_witness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EmptyPublicApiClient(_PublicApiClient):
        def get_json(
            self,
            path: str,
            *,
            query: dict[str, str] | None = None,
        ) -> PublicApiResponse:
            if path == "homepages/search":
                assert query == {"status": "published", "limit": "1"}
                return PublicApiResponse(status=200, payload={"items": []})
            return super().get_json(path, query=query)

    import_report = tmp_path / "env/alpha/runs/data-release/baseline-release/import/homepage-import.json"
    output = tmp_path / "env/alpha/runs/data-release/baseline-release/verify/baseline-api-verification.json"
    _import_report(import_report)
    payload = read_json(import_report)
    payload["env"] = "alpha"
    write_json(import_report, payload)
    monkeypatch.setattr(verification, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(verification, "PublicApiClient", _EmptyPublicApiClient)

    verification.write_baseline_api_verification(
        environment=DeploymentEnvironment.ALPHA,
        release_id="baseline-release",
        run_id="verify",
        importer_report_path=import_report,
        output_path=output,
        api_base_url="https://alpha-api.test",
        insecure_tls=True,
        resolve_host="127.0.0.1",
    )

    assert read_json(output)["preserved"] is None
