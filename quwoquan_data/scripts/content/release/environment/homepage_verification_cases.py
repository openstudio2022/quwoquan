"""Derive release-bound homepage verification cases from an importer receipt."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid
from content.release.model import DeploymentEnvironment


class HomepageVerificationCaseError(ValueError):
    """The importer receipt cannot prove a consumable homepage case set."""


@dataclass(frozen=True)
class HomepageVerificationCase:
    entity_ref: str
    homepage_id: str
    title: str

    def as_payload(self) -> dict[str, str]:
        return {
            "entityRef": self.entity_ref,
            "homepageId": self.homepage_id,
            "title": self.title,
        }


def _expected_entity_refs(release_root: Path) -> set[str]:
    desired = read_json(payload_file(release_root, "desired_state.json"))
    refs = desired.get("desiredRefs") if isinstance(desired.get("desiredRefs"), Mapping) else {}
    entities = refs.get("entities") if isinstance(refs, Mapping) else []
    if not isinstance(entities, list):
        raise HomepageVerificationCaseError("release desired entity refs must be an array")
    normalized = {str(value).strip() for value in entities if str(value).strip()}
    if not normalized:
        raise HomepageVerificationCaseError("release has no entity refs for homepage verification")
    return normalized


def _title_for_entity_ref(entity_ref: str) -> str:
    _prefix, separator, title = entity_ref.rpartition("/")
    if not separator or not title.strip():
        raise HomepageVerificationCaseError(f"invalid entity ref for homepage verification: {entity_ref!r}")
    return title.strip()


def _cases_from_importer_report(
    importer_report: Mapping[str, Any],
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    expected_entity_refs: set[str],
) -> list[HomepageVerificationCase]:
    if importer_report.get("releaseId") != release_id:
        raise HomepageVerificationCaseError("homepage importer report releaseId mismatch")
    if importer_report.get("env") != environment.value:
        raise HomepageVerificationCaseError("homepage importer report environment mismatch")
    if importer_report.get("dryRun") is not False:
        raise HomepageVerificationCaseError("homepage importer report must be an active import")
    if importer_report.get("issues") or importer_report.get("skipped"):
        raise HomepageVerificationCaseError("homepage importer report contains issues or skipped entries")
    raw_mapping = importer_report.get("entityRefToHomepageId")
    if not isinstance(raw_mapping, Mapping):
        raise HomepageVerificationCaseError("homepage importer report lacks entityRefToHomepageId")
    mapping = {str(key).strip(): str(value).strip() for key, value in raw_mapping.items()}
    if set(mapping) != expected_entity_refs or any(not value for value in mapping.values()):
        raise HomepageVerificationCaseError("homepage importer entityRefToHomepageId does not exactly close desired entities")
    return [
        HomepageVerificationCase(
            entity_ref=entity_ref,
            homepage_id=mapping[entity_ref],
            title=_title_for_entity_ref(entity_ref),
        )
        for entity_ref in sorted(expected_entity_refs)
    ]


def write_homepage_verification_case_manifest(
    *,
    environment: DeploymentEnvironment,
    release_root: Path,
    run_root: Path,
    run_id: str,
    importer_report: Mapping[str, Any],
) -> Path:
    """Write one immutable case manifest for an active environment import."""
    if environment is DeploymentEnvironment.ALPHA:
        raise HomepageVerificationCaseError("alpha is projection-only and cannot create imported homepage cases")
    release_id = release_root.name
    cases = _cases_from_importer_report(
        importer_report,
        environment=environment,
        release_id=release_id,
        expected_entity_refs=_expected_entity_refs(release_root),
    )
    try:
        importer_ref = (run_root / "homepage-import.json").relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise HomepageVerificationCaseError("environment run root must be below QWQ_OUTPUT_ROOT") from exc
    payload = {
        "schema": "quwoquan_data.homepage_verification_case_manifest",
        "environment": environment.value,
        "releaseId": release_id,
        "runId": run_id,
        "importerReportRef": importer_ref,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cases": [case.as_payload() for case in cases],
    }
    try:
        assert_valid(
            payload,
            "release",
            "homepage_verification_case_manifest",
            label="homepage_verification_case_manifest",
        )
    except (TypeError, ValueError) as exc:
        raise HomepageVerificationCaseError(str(exc)) from exc
    output = run_root / "homepage_verification_cases.json"
    if output.exists():
        raise HomepageVerificationCaseError(f"homepage verification case manifest already exists: {output}")
    write_json(output, payload)
    return output


__all__ = [
    "HomepageVerificationCase",
    "HomepageVerificationCaseError",
    "write_homepage_verification_case_manifest",
]
