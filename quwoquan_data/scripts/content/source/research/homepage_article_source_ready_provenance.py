"""Verify source-ready provenance bindings without owning batch orchestration."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NoReturn

from content.source.research.homepage_article_seed_selection import (
    load_homepage_article_seed_selection,
)


def verify_source_ready_provenance(
    root: Path,
    provenance: Mapping[str, Any],
    *,
    label: str,
    load_json_file: Callable[..., tuple[dict[str, Any], Path]],
    safe_file: Callable[..., Path],
    file_sha256: Callable[[Path], str],
    reject: Callable[[str], NoReturn],
) -> None:
    """Verify coverage, identity-free seed hints, and physical evidence refs."""

    coverage_binding = {
        "ref": provenance.get("coverageProjectionRef"),
        "fileSha256": provenance.get("coverageProjectionFileSha256"),
        "digest": provenance.get("coverageProjectionDigest"),
    }
    coverage, _ = load_json_file(
        root, coverage_binding, label=f"{label}.coverage"
    )
    digest_values = {
        str(coverage.get(field) or "")
        for field in ("projectionDigest", "documentDigest", "receiptDigest")
    }
    if str(coverage_binding["digest"]) not in digest_values:
        reject(f"{label}.coverage digest is not bound by the document")

    seed_binding = {
        "ref": provenance.get("seedSelectionRef"),
        "fileSha256": provenance.get("seedSelectionFileSha256"),
        "digest": provenance.get("seedSelectionDigest"),
    }
    seed_path = safe_file(root, seed_binding["ref"], label=f"{label}.seedSelection")
    if file_sha256(seed_path) != seed_binding["fileSha256"]:
        reject(f"{label}.seedSelection fileSha256 drift")
    try:
        seed_selection = load_homepage_article_seed_selection(seed_path)
    except ValueError as exc:
        reject(f"{label}.seedSelection is invalid: {exc}")
    if seed_selection["selectionDigest"] != seed_binding["digest"]:
        reject(f"{label}.seedSelection digest drift")
    matching_seeds = [
        row
        for row in seed_selection["seeds"]
        if isinstance(row, Mapping)
        and row.get("seedId") == provenance.get("seedId")
        and row.get("seedOrigin") == provenance.get("seedOrigin")
        and row.get("coverageKey") == provenance.get("coverageKey")
    ]
    if len(matching_seeds) != 1:
        reject(f"{label}.exact seed is not seed-selection-bound")
    seed = matching_seeds[0]
    baseline = seed.get("historicalBaseline")
    comparison = provenance.get("historicalComparison")
    if seed.get("seedOrigin") == "historical_capsule_hint":
        if not isinstance(baseline, Mapping) or not isinstance(comparison, Mapping):
            reject(f"{label}.historical capsule comparison is missing")
        if (
            baseline.get("candidateId") != comparison.get("candidateId")
            or baseline.get("bodyContentSha256")
            != comparison.get("bodyContentSha256")
        ):
            reject(f"{label}.historical capsule comparison is not seed-bound")
    elif comparison is not None:
        reject(f"{label}.current seed has manufactured historical comparison")

    evidence_bindings = [
        {
            "ref": provenance.get("discoveryEvidenceRef"),
            "fileSha256": provenance.get("discoveryEvidenceFileSha256"),
        }
    ]
    for field in (
        "acquisitionEvidenceRefs",
        "rightsEvidenceRefs",
        "qualityEvidenceRefs",
    ):
        rows = provenance.get(field)
        if isinstance(rows, list):
            evidence_bindings.extend(
                dict(row) for row in rows if isinstance(row, Mapping)
            )
    for index, binding in enumerate(evidence_bindings):
        path = safe_file(root, binding.get("ref"), label=f"{label}.evidence[{index}]")
        if file_sha256(path) != binding.get("fileSha256"):
            reject(f"{label}.evidence[{index}] fileSha256 drift")


__all__ = ["verify_source_ready_provenance"]
