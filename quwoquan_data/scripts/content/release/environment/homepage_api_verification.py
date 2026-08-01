"""Verify every imported homepage through an environment public read API."""
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
from content.release.model import DeploymentEnvironment
from content.release.environment.public_api_client import (
    PublicApiClient,
    PublicApiClientError,
)


class HomepageApiVerificationError(ValueError):
    """An API response does not prove the imported homepage is consumable."""


@dataclass(frozen=True)
class HomepageApiCase:
    entity_ref: str
    homepage_id: str
    title: str


@dataclass(frozen=True)
class HomepageDetail:
    homepage_id: str
    title: str
    cover_url: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "HomepageDetail":
        return cls(
            homepage_id=_required_text(payload, "homepageId", endpoint="homepage detail"),
            title=_required_text(payload, "title", endpoint="homepage detail"),
            cover_url=_required_text(payload, "coverUrl", endpoint="homepage detail"),
        )


@dataclass(frozen=True)
class HomepageIntroduction:
    homepage_id: str
    display_name: str
    cover_url: str
    section_count: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "HomepageIntroduction":
        sections = payload.get("sections")
        if not isinstance(sections, list) or not sections:
            raise HomepageApiVerificationError("homepage introduction has no sections")
        return cls(
            homepage_id=_required_text(payload, "homepageId", endpoint="homepage introduction"),
            display_name=_required_text(payload, "displayName", endpoint="homepage introduction"),
            cover_url=_required_text(payload, "coverUrl", endpoint="homepage introduction"),
            section_count=len(sections),
        )


def _read_cases(
    path: Path,
    *,
    environment: DeploymentEnvironment,
    release_id: str,
) -> list[HomepageApiCase]:
    try:
        payload = read_json(path)
        assert_valid(
            payload,
            "release",
            "homepage_verification_case_manifest",
            label="homepage_verification_case_manifest",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise HomepageApiVerificationError(f"homepage verification case manifest is invalid: {exc}") from exc
    if payload.get("releaseId") != release_id:
        raise HomepageApiVerificationError("homepage verification case manifest releaseId mismatch")
    if payload.get("environment") != environment.value:
        raise HomepageApiVerificationError("homepage verification case manifest environment mismatch")
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise HomepageApiVerificationError("homepage verification case manifest cases must be an array")
    cases: list[HomepageApiCase] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise HomepageApiVerificationError(f"homepage verification case {index} must be an object")
        entity_ref = str(row.get("entityRef") or "").strip()
        homepage_id = str(row.get("homepageId") or "").strip()
        title = str(row.get("title") or "").strip()
        if not entity_ref or not homepage_id or not title:
            raise HomepageApiVerificationError(f"homepage verification case {index} has an empty identity")
        cases.append(HomepageApiCase(entity_ref, homepage_id, title))
    if not cases or len({case.entity_ref for case in cases}) != len(cases):
        raise HomepageApiVerificationError("homepage verification case identities are incomplete or duplicated")
    return cases


def _required_text(payload: Mapping[str, Any], field: str, *, endpoint: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HomepageApiVerificationError(f"{endpoint} lacks required {field}")
    return value.strip()


def _verify_case(
    client: PublicApiClient,
    case: HomepageApiCase,
) -> dict[str, Any]:
    homepage_id = quote(case.homepage_id, safe="")
    detail_response = client.get_json(
        f"homepages/{homepage_id}",
        page_id="entity.homepage.detail",
    )
    introduction_response = client.get_json(
        f"homepages/{homepage_id}/introduction",
        page_id="entity.homepage.introduction",
    )
    if detail_response.status != HTTPStatus.OK or introduction_response.status != HTTPStatus.OK:
        raise HomepageApiVerificationError(f"homepage API returned non-200 for {case.entity_ref}")
    detail = HomepageDetail.from_payload(detail_response.payload)
    introduction = HomepageIntroduction.from_payload(introduction_response.payload)
    if detail.homepage_id != case.homepage_id:
        raise HomepageApiVerificationError(f"homepage detail id mismatch for {case.entity_ref}")
    if detail.title != case.title:
        raise HomepageApiVerificationError(f"homepage detail title mismatch for {case.entity_ref}")
    if introduction.homepage_id != case.homepage_id:
        raise HomepageApiVerificationError(f"homepage introduction id mismatch for {case.entity_ref}")
    if introduction.display_name != case.title:
        raise HomepageApiVerificationError(f"homepage introduction title mismatch for {case.entity_ref}")
    if introduction.cover_url != detail.cover_url:
        raise HomepageApiVerificationError(f"homepage cover mismatch between detail and introduction for {case.entity_ref}")
    return {
        "entityRef": case.entity_ref,
        "homepageId": case.homepage_id,
        "title": case.title,
        "detailStatus": detail_response.status,
        "introductionStatus": introduction_response.status,
        "coverUrl": detail.cover_url,
        "sectionCount": introduction.section_count,
    }


def write_homepage_api_verification(
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    run_id: str,
    case_manifest_path: Path,
    output_path: Path,
    api_base_url: str,
    ssl_cafile: str = "",
) -> Path:
    """Call one environment homepage API and write schema-validated evidence."""
    try:
        client = PublicApiClient(
            base_url=api_base_url,
            ssl_cafile=ssl_cafile,
        )
    except PublicApiClientError as exc:
        raise HomepageApiVerificationError(str(exc)) from exc
    cases = _read_cases(
        case_manifest_path,
        environment=environment,
        release_id=release_id,
    )
    try:
        case_ref = case_manifest_path.relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise HomepageApiVerificationError("homepage verification case manifest must be below QWQ_OUTPUT_ROOT") from exc
    try:
        entities = [_verify_case(client, case) for case in cases]
    except PublicApiClientError as exc:
        raise HomepageApiVerificationError(str(exc)) from exc
    payload = {
        "schema": "quwoquan_data.homepage_api_verification",
        "environment": environment.value,
        "releaseId": release_id,
        "runId": run_id,
        "sourceCasesRef": case_ref,
        "apiBaseUrl": api_base_url.rstrip("/"),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "entities": entities,
        "issues": [],
    }
    try:
        assert_valid(
            payload,
            "release",
            "homepage_api_verification",
            label="homepage_api_verification",
        )
    except (TypeError, ValueError) as exc:
        raise HomepageApiVerificationError(str(exc)) from exc
    if output_path.exists():
        raise HomepageApiVerificationError(f"homepage API verification already exists: {output_path}")
    write_json(output_path, payload)
    return output_path


__all__ = [
    "HomepageApiVerificationError",
    "write_homepage_api_verification",
]
