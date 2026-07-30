"""Verify an empty baseline removes data-owned homepages without harming others."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT
from core.schema import assert_valid
from content.release.environment.public_api_client import PublicApiClient, PublicApiClientError
from content.release.model import DataSourceOwner, DeploymentEnvironment, ImportMode


class BaselineApiVerificationError(ValueError):
    """The environment does not prove an isolated empty-baseline transition."""


@dataclass(frozen=True)
class OfflinedHomepageEvidence:
    homepage_id: str
    status: int

    def as_payload(self) -> dict[str, Any]:
        return {"homepageId": self.homepage_id, "status": self.status}


def _offlined_homepage_ids(
    importer_report: Mapping[str, Any],
    *,
    environment: DeploymentEnvironment,
    release_id: str,
) -> tuple[str, ...]:
    if (
        importer_report.get("releaseId") != release_id
        or importer_report.get("env") != environment.value
        or importer_report.get("dryRun") is not False
        or importer_report.get("sourceOwner") != DataSourceOwner.QWQ_DATA
        or importer_report.get("mode") != ImportMode.SYNC
        or importer_report.get("issues")
        or importer_report.get("skipped")
        or importer_report.get("projected") != 0
        or importer_report.get("entityRefToHomepageId") != {}
    ):
        raise BaselineApiVerificationError("homepage importer report is not an isolated empty-baseline sync")
    raw_ids = importer_report.get("offlined")
    if not isinstance(raw_ids, list):
        raise BaselineApiVerificationError("homepage importer report offlined must be an array")
    normalized = tuple(str(value).strip() for value in raw_ids if str(value).strip())
    if len(normalized) != len(raw_ids) or len(set(normalized)) != len(normalized):
        raise BaselineApiVerificationError("homepage importer report offlined identities are invalid")
    return normalized


def write_baseline_api_verification(
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    run_id: str,
    importer_report_path: Path,
    output_path: Path,
    api_base_url: str,
) -> Path:
    try:
        importer_ref = importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise BaselineApiVerificationError("baseline importer report must be below QWQ_OUTPUT_ROOT") from exc
    importer_report = read_json(importer_report_path)
    offlined_ids = _offlined_homepage_ids(
        importer_report,
        environment=environment,
        release_id=release_id,
    )
    try:
        client = PublicApiClient(
            base_url=api_base_url,
        )
        offlined = []
        for homepage_id in offlined_ids:
            response = client.get_json(
                f"homepages/{quote(homepage_id, safe='')}",
                page_id="entity.homepage.detail",
            )
            if response.status != HTTPStatus.GONE:
                raise BaselineApiVerificationError(
                    f"offlined homepage {homepage_id} returned HTTP {response.status}, expected 410"
                )
            offlined.append(OfflinedHomepageEvidence(homepage_id, response.status))
        search = client.get_json(
            "homepages/search",
            page_id="entity.homepage.search",
            query={"status": "published", "limit": "1"},
        )
        items = search.payload.get("items")
        if search.status != HTTPStatus.OK or not isinstance(items, list):
            raise BaselineApiVerificationError("baseline homepage search did not return a valid collection")
        preserved: dict[str, Any] | None = None
        if items:
            witness = items[0]
            if not isinstance(witness, Mapping):
                raise BaselineApiVerificationError("preserved homepage witness is not an object")
            witness_id = str(witness.get("homepageId") or "").strip()
            witness_title = str(witness.get("title") or "").strip()
            if not witness_id or not witness_title or witness_id in offlined_ids:
                raise BaselineApiVerificationError("preserved homepage witness identity is invalid")
            detail = client.get_json(
                f"homepages/{quote(witness_id, safe='')}",
                page_id="entity.homepage.detail",
            )
            if detail.status != HTTPStatus.OK or str(detail.payload.get("homepageId") or "").strip() != witness_id:
                raise BaselineApiVerificationError("preserved homepage witness is not readable through detail API")
            preserved = {
                "homepageId": witness_id,
                "title": witness_title,
                "status": detail.status,
            }
    except PublicApiClientError as exc:
        raise BaselineApiVerificationError(str(exc)) from exc
    payload = {
        "schema": "quwoquan_data.baseline_api_verification",
        "environment": environment.value,
        "releaseId": release_id,
        "runId": run_id,
        "sourceImporterReportRef": importer_ref,
        "apiBaseUrl": api_base_url.rstrip("/"),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "offlined": [item.as_payload() for item in offlined],
        "preserved": preserved,
        "issues": [],
    }
    try:
        assert_valid(payload, "release", "baseline_api_verification", label="baseline_api_verification")
    except (TypeError, ValueError) as exc:
        raise BaselineApiVerificationError(str(exc)) from exc
    if output_path.exists():
        raise BaselineApiVerificationError(f"baseline API verification already exists: {output_path}")
    write_json(output_path, payload)
    return output_path


__all__ = ["BaselineApiVerificationError", "write_baseline_api_verification"]
