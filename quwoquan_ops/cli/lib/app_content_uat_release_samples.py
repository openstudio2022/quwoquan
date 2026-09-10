"""Resolve and validate public reads for an App content sample plan."""
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
    "homepage": "entityRefs", "article": "feedQueries.typed_article",
    "image": "feedQueries.typed_image", "video": "feedQueries.typed_video",
}


def document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_regular_json(path: Path, *, root: Path, label: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    try:
        ref = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    if resolved != path.absolute():
        raise ValueError(f"{label} has a symlinked parent")
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
    sample_plan = plan.get("releaseUatSamplePlan")
    milestone = str(sample_plan.get("milestone") or "").strip() if isinstance(sample_plan, Mapping) else ""
    if not milestone and isinstance(release_identity, Mapping):
        milestone = str(release_identity.get("milestone") or "").strip()
    normalized = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise ValueError(f"App content UAT sample {index} is invalid")
        carrier = str(row.get("carrier") or "").strip()
        values = {key: str(row.get(key) or "").strip() for key in ("sampleId", "objectId", "objectRef", "objectDigest")}
        if carrier not in _SOURCE_READBACKS or not all(values.values()) or not values["objectDigest"].startswith("sha256:"):
            raise ValueError(f"App content UAT sample {index} identity is invalid")
        normalized.append({"carrier": carrier, "sampleId": values["sampleId"], "sourceObjectId": values["objectId"], "objectRef": values["objectRef"], "objectDigest": values["objectDigest"]})
    for field in ("sampleId", "sourceObjectId", "objectRef"):
        values = [row[field] for row in normalized]
        if len(values) != len(set(values)):
            raise ValueError(f"App content UAT sample {field} values are duplicated")
    if milestone and dict(Counter(row["carrier"] for row in normalized)) != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT sample distribution drifted")
    return milestone, normalized


def resolve_release_sample_requests(*, readiness_path: Path, app_uat_plan: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    """以 Data activation→prepared apply 闭包解析真实公开 API 的对象 ID。"""
    from quwoquan_ops.cli.commands.app_preflight_readiness import _resolve_data_prepared_import

    root = output_root.expanduser().resolve()
    readiness, readiness_ref = _load_regular_json(readiness_path, root=root, label="App content UAT readiness receipt")
    from quwoquan_ops.cli.commands.app_preflight_readiness import _validate_data_schema

    _validate_data_schema(readiness, "environment_release_readiness")
    milestone, cases = _sample_cases(app_uat_plan)
    release_id = str(readiness.get("releaseId") or "").strip()
    if not release_id or not isinstance(app_uat_plan.get("releaseIdentity"), Mapping) or app_uat_plan["releaseIdentity"].get("releaseId") != release_id:
        raise ValueError("App content UAT sample plan releaseId drifted")
    sample_plan_ref = str(app_uat_plan.get("releaseUatSamplePlanRef") or "").strip()
    sample_plan_digest = str(app_uat_plan.get("releaseUatSamplePlanDigest") or "").strip()
    if not sample_plan_ref or not sample_plan_digest.startswith("sha256:"):
        raise ValueError("App content UAT ReleaseUatSamplePlan binding is missing")
    homepage_ref = str(readiness.get("homepageApiVerificationRef") or "").strip()
    expected_homepage_ref = f"env/{readiness.get('environment')}/runs/data-release/{release_id}/{readiness.get('verifyRunId')}/homepage-api-verification.json"
    if homepage_ref != expected_homepage_ref:
        raise ValueError("App content UAT homepage API verification ref drifted")
    homepage_report, _ = _load_regular_json(root / homepage_ref, root=root, label="App content UAT homepage API verification")
    expected = {"schema": "quwoquan_data.homepage_api_verification", "environment": readiness.get("environment"), "releaseId": release_id, "runId": readiness.get("verifyRunId"), "passed": True, "issues": []}
    if any(homepage_report.get(k) != v for k, v in expected.items()):
        raise ValueError("App content UAT homepage API verification is not passed")
    raw_entities = homepage_report.get("entities")
    if not isinstance(raw_entities, list):
        raise ValueError("App content UAT homepage API verification entities are missing")
    homepage_ids = {}
    for row in raw_entities:
        if not isinstance(row, Mapping):
            raise ValueError("App content UAT homepage API verification entity is invalid")
        entity_ref, homepage_id = str(row.get("entityRef") or "").strip(), str(row.get("homepageId") or "").strip()
        if not entity_ref or not homepage_id or entity_ref in homepage_ids or row.get("detailStatus") != 200 or row.get("introductionStatus") != 200:
            raise ValueError("App content UAT homepage API verification identity drifted")
        for identity in {entity_ref, entity_ref.strip("/").removeprefix("entity/"), entity_ref.strip("/").removeprefix("entities/")}:
            if identity in homepage_ids and homepage_ids[identity] != homepage_id:
                raise ValueError("App content UAT homepage API verification identity drifted")
            homepage_ids[identity] = homepage_id
    import_path, _ = _resolve_data_prepared_import(readiness, evidence_root=root)
    import_report, import_ref = _load_regular_json(import_path, root=root, label="App content UAT content import report")
    expected = {"schema": "quwoquan.content_import_report", "environment": readiness.get("environment"), "releaseId": release_id, "status": "imported", "manifestDigest": readiness.get("manifestDigest")}
    if any(import_report.get(k) != v for k, v in expected.items()):
        raise ValueError("App content UAT content import report is not release-bound")
    raw_bindings = import_report.get("postBindings")
    if not isinstance(raw_bindings, list):
        raise ValueError("App content UAT content import post bindings are missing")
    post_ids = {str(value).strip() for value in readiness.get("postIds") or [] if str(value).strip()}
    post_bindings, observed_post_ids = {}, set()
    for row in raw_bindings:
        if not isinstance(row, Mapping):
            raise ValueError("App content UAT content import binding is invalid")
        key = tuple(str(row.get(field) or "").strip() for field in ("contentId", "postRef", "contentType"))
        post_id = str(row.get("postId") or "").strip()
        if not all(key) or not post_id or key in post_bindings or post_id in observed_post_ids:
            raise ValueError("App content UAT content import binding identity drifted")
        post_bindings[key] = post_id
        observed_post_ids.add(post_id)
    if observed_post_ids != post_ids:
        raise ValueError("App content UAT content import postIds drifted from readiness")
    samples, ordinals = [], Counter()
    for case in cases:
        carrier, source_id = case["carrier"], case["sourceObjectId"]
        ordinals[carrier] += 1
        if carrier == "homepage":
            normalized = source_id.strip("/").removeprefix("entities/").removeprefix("entity/")
            read_id = homepage_ids.get(source_id, "") or homepage_ids.get(normalized, "")
        else:
            object_ref = case["objectRef"]
            if not object_ref.startswith(f"objects/posts/{carrier}/"):
                raise ValueError(f"App content UAT immutable object ref is invalid for {source_id}")
            read_id = post_bindings.get((source_id, object_ref.removeprefix("objects/posts/"), carrier), "")
        if not read_id:
            raise ValueError(f"App content UAT runtime mapping is missing for {source_id}")
        samples.append({**case, "sourceReadback": _SOURCE_READBACKS[carrier], "ordinal": ordinals[carrier], "readObjectId": read_id, "expectedContentType": "" if carrier == "homepage" else carrier})
    return {
        "releaseId": release_id, "milestone": milestone,
        "releaseUatSamplePlanRef": sample_plan_ref, "releaseUatSamplePlanDigest": sample_plan_digest,
        "readinessReceiptRef": readiness_ref, "readinessReceiptFileSha256": _file_digest(readiness_path),
        "homepageApiVerificationRef": homepage_ref, "homepageApiVerificationFileSha256": _file_digest(root / homepage_ref),
        "contentImportReportRef": import_ref, "contentImportReportFileSha256": _file_digest(import_path),
        "samples": samples,
    }


def validate_release_sample_probe(*, report: Mapping[str, Any], resolved: Mapping[str, Any], app_uat_plan_digest: str, readiness_receipt_digest: str) -> dict[str, Any]:
    """只在每个精确样本真实 HTTP 读回通过后返回紧凑证据。"""
    expected = resolved.get("samples")
    if not isinstance(expected, list) or not expected:
        raise ValueError("App content UAT resolved sample set is incomplete")
    expected_by_id = {str(row["sampleId"]): row for row in expected if isinstance(row, Mapping)}
    raw_checks = report.get("checks")
    if report.get("status") != "passed" or not isinstance(raw_checks, list):
        raise ValueError("App content UAT release sample probe did not pass")
    checks = [row for row in raw_checks if isinstance(row, Mapping) and row.get("name") == "release_sample"]
    if len(checks) != len(expected):
        raise ValueError(f"App content UAT release sample probe did not execute {len(expected)} reads")
    evidence, observed_ids = [], set()
    for check in checks:
        sample_id = str(check.get("sampleId") or "").strip()
        sample = expected_by_id.get(sample_id)
        if sample is None or sample_id in observed_ids:
            raise ValueError("App content UAT release sample execution identity drifted")
        observed_ids.add(sample_id)
        fields = {field: sample[field] for field in ("carrier", "sourceObjectId", "readObjectId", "expectedContentType")}
        fields.update(returnedObjectId=sample["readObjectId"], returnedContentType=sample["expectedContentType"])
        if check.get("ok") is not True or check.get("statusCode") != 200 or any(check.get(k) != v for k, v in fields.items()) or not str(check.get("url") or "").strip() or not str(check.get("responseDigest") or "").startswith("sha256:") or not isinstance(check.get("responseBytes"), int) or check["responseBytes"] <= 0:
            raise ValueError(f"App content UAT release sample {sample_id} read evidence drifted")
        evidence.append({"sampleId": sample_id, "carrier": sample["carrier"], "sourceObjectId": sample["sourceObjectId"], "readObjectId": sample["readObjectId"], "statusCode": 200, **{key: check[key] for key in ("returnedObjectId", "returnedContentType", "responseDigest", "responseBytes")}})
    if observed_ids != set(expected_by_id):
        raise ValueError("App content UAT release sample execution coverage is incomplete")
    distribution = dict(Counter(row["carrier"] for row in evidence))
    milestone = str(resolved.get("milestone") or "")
    if milestone and distribution != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT release sample evidence distribution drifted")
    return {
        "milestone": milestone, "executedSampleCount": len(evidence), "distribution": distribution,
        "appUatPlanDigest": app_uat_plan_digest, "readinessReceiptDigest": readiness_receipt_digest,
        **{key: resolved[key] for key in ("releaseUatSamplePlanRef", "releaseUatSamplePlanDigest", "readinessReceiptRef", "readinessReceiptFileSha256", "homepageApiVerificationRef", "homepageApiVerificationFileSha256", "contentImportReportRef", "contentImportReportFileSha256")},
        "samples": sorted(evidence, key=lambda row: row["sampleId"]),
    }


__all__ = ["document_digest", "resolve_release_sample_requests", "validate_release_sample_probe"]
