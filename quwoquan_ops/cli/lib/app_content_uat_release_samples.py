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
    "M10000": {"homepage": 25, "article": 25, "image": 25, "video": 25},
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
    raw = plan.get("orderedSamples")
    if not isinstance(raw, list) or not raw:
        raise ValueError("App content UAT ReleaseUatSamplePlan orderedSamples are missing")
    release_identity = plan.get("releaseIdentity")
    milestone = (
        str((plan.get("releaseUatSamplePlan") or {}).get("milestone") or "").strip()
        if isinstance(plan.get("releaseUatSamplePlan"), Mapping)
        else ""
    )
    if not milestone and isinstance(release_identity, Mapping):
        milestone = str(release_identity.get("milestone") or "").strip()
    # Milestone is optional for canary plans; distribution is carried by exact rows.
    normalized: list[dict[str, Any]] = []
    for index, raw_case in enumerate(raw):
        if not isinstance(raw_case, Mapping):
            raise ValueError(f"App content UAT sample {index} is invalid")
        carrier = str(raw_case.get("carrier") or "").strip()
        sample_id = str(raw_case.get("sampleId") or "").strip()
        object_id = str(raw_case.get("objectId") or "").strip()
        object_ref = str(raw_case.get("objectRef") or "").strip()
        object_digest = str(raw_case.get("objectDigest") or "").strip()
        if (
            carrier not in _SOURCE_READBACKS
            or not sample_id
            or not object_id
            or not object_ref
            or not object_digest.startswith("sha256:")
        ):
            raise ValueError(f"App content UAT sample {index} identity is invalid")
        normalized.append(
            {
                "sampleId": sample_id,
                "carrier": carrier,
                "sourceObjectId": object_id,
                "objectRef": object_ref,
                "objectDigest": object_digest,
            }
        )
    for field in ("sampleId", "sourceObjectId", "objectRef"):
        values = [str(case[field]) for case in normalized]
        if len(values) != len(set(values)):
            raise ValueError(f"App content UAT sample {field} values are duplicated")
    distribution = dict(Counter(case["carrier"] for case in normalized))
    if milestone and distribution != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT sample distribution drifted")
    return milestone, normalized


def resolve_release_sample_requests(
    *,
    readiness_path: Path,
    app_uat_plan: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    """Resolve plan identities to exact public read identities.

    Homepage samples originate in readiness ``entityRefs`` and resolve through
    the current release's homepage API verification. Post samples originate as
    immutable Data ``contentId`` values and resolve through the import report's
    exact ``contentId``/``postRef``/``postId`` binding; Ops never equates those
    owner-specific identities.
    """

    root = output_root.expanduser().resolve()
    readiness, readiness_ref = _load_regular_json(
        readiness_path,
        root=root,
        label="App content UAT readiness receipt",
    )
    milestone, cases = _sample_cases(app_uat_plan)
    release_id = str(readiness.get("releaseId") or "").strip()
    if (
        not release_id
        or not isinstance(app_uat_plan.get("releaseIdentity"), Mapping)
        or app_uat_plan["releaseIdentity"].get("releaseId") != release_id
    ):
        raise ValueError("App content UAT sample plan releaseId drifted")
    sample_plan_ref = str(app_uat_plan.get("releaseUatSamplePlanRef") or "").strip()
    sample_plan_digest = str(app_uat_plan.get("releaseUatSamplePlanDigest") or "").strip()
    if not sample_plan_ref or not sample_plan_digest.startswith("sha256:"):
        raise ValueError("App content UAT ReleaseUatSamplePlan binding is missing")

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
        for identity in {
            entity_ref,
            entity_ref.strip("/").removeprefix("entity/"),
            entity_ref.strip("/").removeprefix("entities/"),
        }:
            if identity in homepage_ids and homepage_ids[identity] != homepage_id:
                raise ValueError(
                    "App content UAT homepage API verification identity drifted"
                )
            homepage_ids[identity] = homepage_id

    import_ref = str(readiness.get("contentImportReportRef") or "").strip()
    if not import_ref:
        raise ValueError("App content UAT content import report ref is missing")
    import_report, observed_import_ref = _load_regular_json(
        root / import_ref,
        root=root,
        label="App content UAT content import report",
    )
    if observed_import_ref != import_ref:
        raise ValueError("App content UAT content import report ref drifted")
    if (
        import_report.get("schema") != "quwoquan.content_import_report"
        or import_report.get("releaseId") != release_id
        or import_report.get("status") != "imported"
        or import_report.get("manifestDigest") != readiness.get("manifestDigest")
    ):
        raise ValueError("App content UAT content import report is not release-bound")
    raw_bindings = import_report.get("postBindings")
    if not isinstance(raw_bindings, list):
        raise ValueError("App content UAT content import post bindings are missing")
    post_ids = {
        str(value).strip() for value in readiness.get("postIds") or [] if str(value).strip()
    }
    post_bindings: dict[tuple[str, str, str], str] = {}
    observed_post_ids: set[str] = set()
    for index, raw_binding in enumerate(raw_bindings):
        if not isinstance(raw_binding, Mapping):
            raise ValueError(f"App content UAT content import binding {index} is invalid")
        content_id = str(raw_binding.get("contentId") or "").strip()
        post_ref = str(raw_binding.get("postRef") or "").strip()
        post_id = str(raw_binding.get("postId") or "").strip()
        content_type = str(raw_binding.get("contentType") or "").strip()
        key = (content_id, post_ref, content_type)
        if (
            not all(key)
            or not post_id
            or key in post_bindings
            or post_id in observed_post_ids
        ):
            raise ValueError("App content UAT content import binding identity drifted")
        post_bindings[key] = post_id
        observed_post_ids.add(post_id)
    if observed_post_ids != post_ids:
        raise ValueError("App content UAT content import postIds drifted from readiness")

    samples: list[dict[str, Any]] = []
    carrier_ordinals: Counter[str] = Counter()
    for case in cases:
        carrier = str(case["carrier"])
        source_id = str(case["sourceObjectId"])
        carrier_ordinals[carrier] += 1
        if carrier == "homepage":
            normalized_source_id = source_id.strip("/")
            for prefix in ("entities/", "entity/"):
                if normalized_source_id.startswith(prefix):
                    normalized_source_id = normalized_source_id[len(prefix) :]
                    break
            read_object_id = homepage_ids.get(source_id, "") or homepage_ids.get(
                normalized_source_id, ""
            )
        else:
            object_ref = str(case["objectRef"])
            prefix = f"objects/posts/{carrier}/"
            if not object_ref.startswith(prefix):
                raise ValueError(
                    f"App content UAT immutable object ref is invalid for {source_id}"
                )
            post_ref = object_ref.removeprefix("objects/posts/")
            read_object_id = post_bindings.get((source_id, post_ref, carrier), "")
        if not read_object_id:
            raise ValueError(
                f"App content UAT runtime mapping is missing for {source_id}"
            )
        samples.append(
            {
                "sampleId": case["sampleId"],
                "carrier": carrier,
                "sourceReadback": _SOURCE_READBACKS[carrier],
                "sourceObjectId": source_id,
                "objectRef": str(case["objectRef"]),
                "objectDigest": str(case["objectDigest"]),
                "ordinal": carrier_ordinals[carrier],
                "readObjectId": read_object_id,
                "expectedContentType": "" if carrier == "homepage" else carrier,
            }
        )
    return {
        "releaseId": release_id,
        "milestone": milestone,
        "releaseUatSamplePlanRef": sample_plan_ref,
        "releaseUatSamplePlanDigest": sample_plan_digest,
        "readinessReceiptRef": readiness_ref,
        "readinessReceiptFileSha256": _file_digest((root / readiness_ref).resolve()),
        "homepageApiVerificationRef": homepage_ref,
        "homepageApiVerificationFileSha256": _file_digest((root / homepage_ref).resolve()),
        "contentImportReportRef": import_ref,
        "contentImportReportFileSha256": _file_digest((root / import_ref).resolve()),
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
    if not isinstance(expected, list) or not expected:
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
    if len(checks) != len(expected):
        raise ValueError(
            f"App content UAT release sample probe did not execute {len(expected)} reads"
        )

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
    if milestone and distribution != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT release sample evidence distribution drifted")
    evidence.sort(key=lambda row: str(row["sampleId"]))
    return {
        "milestone": milestone,
        "executedSampleCount": len(evidence),
        "distribution": distribution,
        "releaseUatSamplePlanRef": resolved["releaseUatSamplePlanRef"],
        "releaseUatSamplePlanDigest": resolved["releaseUatSamplePlanDigest"],
        "appUatPlanDigest": app_uat_plan_digest,
        "readinessReceiptDigest": readiness_receipt_digest,
        "readinessReceiptRef": resolved["readinessReceiptRef"],
        "readinessReceiptFileSha256": resolved["readinessReceiptFileSha256"],
        "homepageApiVerificationRef": resolved["homepageApiVerificationRef"],
        "homepageApiVerificationFileSha256": resolved[
            "homepageApiVerificationFileSha256"
        ],
        "contentImportReportRef": resolved["contentImportReportRef"],
        "contentImportReportFileSha256": resolved[
            "contentImportReportFileSha256"
        ],
        "samples": evidence,
    }


__all__ = [
    "document_digest",
    "resolve_release_sample_requests",
    "validate_release_sample_probe",
]
