"""Derive Gamma App UAT cases from one verified homepage importer receipt."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid


class GammaAppUatCaseError(ValueError):
    """The importer receipt cannot prove a consumable homepage UAT case set."""


@dataclass(frozen=True)
class GammaHomepageUatCase:
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
        raise GammaAppUatCaseError("release desired entity refs must be an array")
    normalized = {str(value).strip() for value in entities if str(value).strip()}
    if not normalized:
        raise GammaAppUatCaseError("release has no entity refs for homepage App UAT")
    return normalized


def _title_for_entity_ref(entity_ref: str) -> str:
    _prefix, separator, title = entity_ref.rpartition("/")
    if not separator or not title.strip():
        raise GammaAppUatCaseError(f"invalid entity ref for App UAT: {entity_ref!r}")
    return title.strip()


def _cases_from_importer_report(
    importer_report: Mapping[str, Any],
    *,
    release_id: str,
    expected_entity_refs: set[str],
) -> list[GammaHomepageUatCase]:
    if importer_report.get("releaseId") != release_id:
        raise GammaAppUatCaseError("homepage importer report releaseId mismatch")
    if importer_report.get("env") != "gamma":
        raise GammaAppUatCaseError("homepage importer report must be from gamma")
    if importer_report.get("dryRun") is not False:
        raise GammaAppUatCaseError("homepage importer report must be an active Gamma import")
    if importer_report.get("issues") or importer_report.get("skipped"):
        raise GammaAppUatCaseError("homepage importer report contains issues or skipped entries")
    raw_mapping = importer_report.get("entityRefToHomepageId")
    if not isinstance(raw_mapping, Mapping):
        raise GammaAppUatCaseError("homepage importer report lacks entityRefToHomepageId")
    mapping = {str(key).strip(): str(value).strip() for key, value in raw_mapping.items()}
    if set(mapping) != expected_entity_refs or any(not value for value in mapping.values()):
        raise GammaAppUatCaseError("homepage importer entityRefToHomepageId does not exactly close desired entities")
    return [
        GammaHomepageUatCase(
            entity_ref=entity_ref,
            homepage_id=mapping[entity_ref],
            title=_title_for_entity_ref(entity_ref),
        )
        for entity_ref in sorted(expected_entity_refs)
    ]


def write_gamma_app_uat_case_manifest(
    *,
    release_root: Path,
    run_root: Path,
    run_id: str,
    importer_report: Mapping[str, Any],
) -> Path:
    """Write the one runtime UAT case manifest for an active Gamma homepage import."""
    release_id = release_root.name
    cases = _cases_from_importer_report(
        importer_report,
        release_id=release_id,
        expected_entity_refs=_expected_entity_refs(release_root),
    )
    try:
        importer_ref = (run_root / "homepage-import.json").relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise GammaAppUatCaseError("Gamma run root must be below QWQ_OUTPUT_ROOT") from exc
    payload = {
        "schemaVersion": "quwoquan_data.gamma_app_uat_case_manifest/1",
        "environment": "gamma",
        "releaseId": release_id,
        "runId": run_id,
        "importerReportRef": importer_ref,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cases": [case.as_payload() for case in cases],
    }
    try:
        assert_valid(payload, "release", "gamma_app_uat_case_manifest", label="gamma_app_uat_case_manifest")
    except (TypeError, ValueError) as exc:
        raise GammaAppUatCaseError(str(exc)) from exc
    output = run_root / "app_uat_cases.json"
    if output.exists():
        raise GammaAppUatCaseError(f"Gamma App UAT case manifest already exists: {output}")
    write_json(output, payload)
    return output


__all__ = [
    "GammaAppUatCaseError",
    "GammaHomepageUatCase",
    "write_gamma_app_uat_case_manifest",
]
