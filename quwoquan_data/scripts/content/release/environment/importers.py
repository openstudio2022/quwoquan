"""Release-bound service importer execution and report validation."""
from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import REPO_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid
from content.release.model import DeletePolicy, ImportMode


_IMPORT_REPORT_SCHEMAS = {
    "quwoquan.content_import_report": "import_report",
    "quwoquan_service.homepage_import_report": "homepage_import_report",
}


def assert_import_report_contract(
    report: Mapping[str, Any] | Path,
    *,
    source: Path | None = None,
    expected_release_id: str | None = None,
) -> dict[str, Any]:
    if isinstance(report, Path):
        source = report
        report = read_json(report)
    if not isinstance(report, Mapping):
        raise ValueError(f"import report 必须是对象：{source or '<memory>'}")
    payload = dict(report)
    schema = str(payload.get("schema") or "")
    schema_name = _IMPORT_REPORT_SCHEMAS.get(schema)
    if not schema_name:
        raise SystemExit(
            f"[ship] 未登记 Schema import report：{schema or '<missing>'} "
            f"({source or '<memory>'})"
        )
    assert_valid(
        payload,
        "release",
        schema_name,
        label=f"import_report:{source or '<memory>'}",
    )
    if expected_release_id is not None and str(payload.get("releaseId") or "") != expected_release_id:
        raise RuntimeError(
            f"import report releaseId 不一致：expected={expected_release_id} "
            f"actual={payload.get('releaseId')}"
        )
    return payload


def run_content_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    media_base_url: str,
    dry_run: bool,
    mode: ImportMode = ImportMode.UPSERT,
    delete_policy: DeletePolicy = DeletePolicy.NONE,
) -> None:
    report_path = run / "import.json"
    command = [
        "go",
        "run",
        "./services/content-service/cmd/import",
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--media-base-url",
        media_base_url,
        "--env",
        env,
        "--mode",
        mode,
        "--delete-policy",
        delete_policy,
        "--report",
        str(report_path),
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT / "quwoquan_service",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"[ship] importer failed: exit={result.returncode}")
    assert_import_report_contract(report_path, expected_release_id=release.name)


def run_homepage_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    media_base_url: str,
    dry_run: bool,
    mode: ImportMode,
) -> dict[str, Any]:
    report_path = run / "homepage-import.json"
    command = [
        "go",
        "run",
        "./cmd/homepage-import",
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--media-base-url",
        media_base_url,
        "--env",
        env,
        "--mode",
        mode,
        "--report",
        str(report_path),
    ]
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT / "quwoquan_service" / "services" / "entity-service",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"[ship] homepage importer failed: exit={result.returncode}")
    report = assert_import_report_contract(
        report_path,
        expected_release_id=release.name,
    )
    desired = read_json(payload_file(release, "desired_state.json"))
    expected = set(desired.get("desiredRefs", {}).get("entities", []))
    imported = set(report.get("entityRefToHomepageId", {}))
    missing = sorted(expected - imported) if not dry_run else []
    projected_mismatch = int(report.get("projected", -1)) != len(expected)
    if report.get("issues") or report.get("skipped") or missing:
        raise SystemExit(
            "[ship] homepage importer closure failed: "
            f"issues={len(report.get('issues', []))} "
            f"skipped={len(report.get('skipped', []))} missing={missing[:5]}"
        )
    if projected_mismatch:
        raise SystemExit(
            "[ship] homepage importer projection mismatch: "
            f"expected={len(expected)} projected={report.get('projected')}"
        )
    return report


__all__ = [
    "assert_import_report_contract",
    "run_content_importer",
    "run_homepage_importer",
]
