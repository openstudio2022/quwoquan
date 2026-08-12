"""Resolve and validate real reads for a milestone App content sample plan."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_DISTRIBUTIONS = {
    "M100": {"homepage": 25, "article": 25, "image": 40, "video": 10},
    "M1000": {"homepage": 25, "article": 25, "image": 25, "video": 25},
}
_SOURCE_READBACKS = {
    "homepage": "entityRefs",
    "article": "feedQueries.typed_article",
    "image": "feedQueries.typed_image",
    "video": "feedQueries.typed_video",
}


def document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_regular_json(path: Path, *, root: Path, label: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    try:
        ref = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value, ref


def _sample_cases(plan: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    raw = plan.get("stratifiedSamples")
    if not isinstance(raw, Mapping):
        raise ValueError("App content UAT milestone sample plan is missing")
    milestone = str(raw.get("milestone") or "").strip()
    expected_distribution = _DISTRIBUTIONS.get(milestone)
    if expected_distribution is None:
        raise ValueError("App content UAT milestone sample plan is unsupported")
    if (
        raw.get("selection") != "lexicographic_prefix_v1"
        or raw.get("sampleCount") != 100
        or raw.get("distribution") != expected_distribution
    ):
        raise ValueError("App content UAT milestone sample policy drifted")
    cases = raw.get("cases")
    if not isinstance(cases, list) or len(cases) != 100:
        raise ValueError("App content UAT milestone requires exactly 100 sample cases")
    normalized: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, Mapping) or set(raw_case) != {
            "sampleId",
            "carrier",
            "sourceReadback",
            "objectId",
            "ordinal",
        }:
            raise ValueError(f"App content UAT sample {index} fields are invalid")
        carrier = str(raw_case.get("carrier") or "").strip()
        sample_id = str(raw_case.get("sampleId") or "").strip()
        object_id = str(raw_case.get("objectId") or "").strip()
        source_readback = str(raw_case.get("sourceReadback") or "").strip()
        ordinal = raw_case.get("ordinal")
        if (
            carrier not in expected_distribution
            or source_readback != _SOURCE_READBACKS[carrier]
            or not sample_id
            or not object_id
            or not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal <= 0
        ):
            raise ValueError(f"App content UAT sample {index} identity is invalid")
        normalized.append(
            {
                "sampleId": sample_id,
                "carrier": carrier,
                "sourceReadback": source_readback,
                "sourceObjectId": object_id,
                "ordinal": ordinal,
            }
        )
    if dict(Counter(case["carrier"] for case in normalized)) != expected_distribution:
        raise ValueError("App content UAT sample distribution drifted")
    for field in ("sampleId", "sourceObjectId"):
        values = [str(case[field]) for case in normalized]
        if len(values) != len(set(values)):
            raise ValueError(f"App content UAT sample {field} values are duplicated")
    return milestone, normalized


def resolve_release_sample_requests(
    *,
    readiness_path: Path,
    app_uat_plan: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    """Resolve plan identities to exact public read identities.

    Homepage samples originate in readiness ``entityRefs``.  The current
    release's homepage API verification is the sole mapping to environment
    ``homepageId`` values; Post sample IDs are already public GetPost IDs.
    """

    root = output_root.expanduser().resolve()
    readiness, readiness_ref = _load_regular_json(
        readiness_path,
        root=root,
        label="App content UAT readiness receipt",
    )
    milestone, cases = _sample_cases(app_uat_plan)
    release_id = str(readiness.get("releaseId") or "").strip()
    if not release_id or app_uat_plan.get("releaseId") != release_id:
        raise ValueError("App content UAT sample plan releaseId drifted")

    homepage_ref = str(readiness.get("homepageApiVerificationRef") or "").strip()
    if not homepage_ref:
        raise ValueError("App content UAT homepage API verification ref is missing")
    homepage_report, observed_homepage_ref = _load_regular_json(
        root / homepage_ref,
        root=root,
        label="App content UAT homepage API verification",
    )
    if observed_homepage_ref != homepage_ref:
        raise ValueError("App content UAT homepage API verification ref drifted")
    if (
        homepage_report.get("schema") != "quwoquan_data.homepage_api_verification"
        or homepage_report.get("releaseId") != release_id
        or homepage_report.get("passed") is not True
        or homepage_report.get("issues") != []
    ):
        raise ValueError("App content UAT homepage API verification is not passed")
    raw_entities = homepage_report.get("entities")
    if not isinstance(raw_entities, list):
        raise ValueError("App content UAT homepage API verification entities are missing")
    homepage_ids: dict[str, str] = {}
    for row in raw_entities:
        if not isinstance(row, Mapping):
            raise ValueError("App content UAT homepage API verification entity is invalid")
        entity_ref = str(row.get("entityRef") or "").strip()
        homepage_id = str(row.get("homepageId") or "").strip()
        if (
            not entity_ref
            or not homepage_id
            or entity_ref in homepage_ids
            or row.get("detailStatus") != 200
            or row.get("introductionStatus") != 200
        ):
            raise ValueError("App content UAT homepage API verification identity drifted")
        homepage_ids[entity_ref] = homepage_id

    samples: list[dict[str, Any]] = []
    for case in cases:
        carrier = str(case["carrier"])
        source_id = str(case["sourceObjectId"])
        read_object_id = homepage_ids.get(source_id, "") if carrier == "homepage" else source_id
        if not read_object_id:
            raise ValueError(f"App content UAT homepage mapping is missing for {source_id}")
        samples.append(
            {
                **case,
                "readObjectId": read_object_id,
                "expectedContentType": "" if carrier == "homepage" else carrier,
            }
        )
    return {
        "releaseId": release_id,
        "milestone": milestone,
        "readinessReceiptRef": readiness_ref,
        "readinessReceiptFileSha256": _file_digest((root / readiness_ref).resolve()),
        "homepageApiVerificationRef": homepage_ref,
        "homepageApiVerificationFileSha256": _file_digest((root / homepage_ref).resolve()),
        "samples": samples,
    }


def validate_release_sample_probe(
    *,
    report: Mapping[str, Any],
    resolved: Mapping[str, Any],
    app_uat_plan_digest: str,
    readiness_receipt_digest: str,
) -> dict[str, Any]:
    """Return compact per-sample evidence only after 100 exact HTTP reads pass."""

    expected = resolved.get("samples")
    if not isinstance(expected, list) or len(expected) != 100:
        raise ValueError("App content UAT resolved sample set is incomplete")
    expected_by_id = {str(row["sampleId"]): row for row in expected if isinstance(row, Mapping)}
    raw_checks = report.get("checks")
    if report.get("status") != "passed" or not isinstance(raw_checks, list):
        raise ValueError("App content UAT release sample probe did not pass")
    checks = [
        row
        for row in raw_checks
        if isinstance(row, Mapping) and row.get("name") == "release_sample"
    ]
    if len(checks) != 100:
        raise ValueError("App content UAT release sample probe did not execute 100 reads")

    evidence: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    for check in checks:
        sample_id = str(check.get("sampleId") or "").strip()
        sample = expected_by_id.get(sample_id)
        if sample is None or sample_id in observed_ids:
            raise ValueError("App content UAT release sample execution identity drifted")
        observed_ids.add(sample_id)
        expected_fields = {
            "carrier": sample["carrier"],
            "sourceObjectId": sample["sourceObjectId"],
            "readObjectId": sample["readObjectId"],
            "expectedContentType": sample["expectedContentType"],
            "returnedObjectId": sample["readObjectId"],
            "returnedContentType": sample["expectedContentType"],
        }
        if (
            check.get("ok") is not True
            or check.get("statusCode") != 200
            or any(check.get(field) != value for field, value in expected_fields.items())
            or not str(check.get("url") or "").strip()
            or not str(check.get("responseDigest") or "").startswith("sha256:")
            or not isinstance(check.get("responseBytes"), int)
            or int(check["responseBytes"]) <= 0
        ):
            raise ValueError(f"App content UAT release sample {sample_id} read evidence drifted")
        evidence.append(
            {
                "sampleId": sample_id,
                "carrier": sample["carrier"],
                "sourceObjectId": sample["sourceObjectId"],
                "readObjectId": sample["readObjectId"],
                "statusCode": 200,
                "returnedObjectId": check["returnedObjectId"],
                "returnedContentType": check["returnedContentType"],
                "responseDigest": check["responseDigest"],
                "responseBytes": check["responseBytes"],
            }
        )
    if observed_ids != set(expected_by_id):
        raise ValueError("App content UAT release sample execution coverage is incomplete")
    distribution = dict(Counter(str(row["carrier"]) for row in evidence))
    milestone = str(resolved.get("milestone") or "")
    if distribution != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT release sample evidence distribution drifted")
    evidence.sort(key=lambda row: str(row["sampleId"]))
    return {
        "milestone": milestone,
        "executedSampleCount": 100,
        "distribution": distribution,
        "appUatPlanDigest": app_uat_plan_digest,
        "readinessReceiptDigest": readiness_receipt_digest,
        "readinessReceiptRef": resolved["readinessReceiptRef"],
        "readinessReceiptFileSha256": resolved["readinessReceiptFileSha256"],
        "homepageApiVerificationRef": resolved["homepageApiVerificationRef"],
        "homepageApiVerificationFileSha256": resolved[
            "homepageApiVerificationFileSha256"
        ],
        "samples": evidence,
    }


__all__ = [
    "document_digest",
    "resolve_release_sample_requests",
    "validate_release_sample_probe",
]
