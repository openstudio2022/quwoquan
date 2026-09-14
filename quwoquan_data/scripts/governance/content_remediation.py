"""从已校验 fidelity audit 最终 typed issues 生成隔离的 remediation request。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

AUDIT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema/governance/content_fidelity_audit.schema.json"


class ContentRemediationError(ValueError):
    """输入契约、路径或 create-once 冲突。"""


def _canonical(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _serialized(document: Mapping[str, object]) -> bytes:
    return _canonical(document) + b"\n"


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _validate_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(c in "0123456789abcdef" for c in value[7:])


def _read_manifest(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ContentRemediationError("DATA.REMEDIATION.AUDIT_MANIFEST_INVALID")
    try:
        document = json.loads(path.read_bytes())
        schema = json.loads(AUDIT_SCHEMA_PATH.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentRemediationError("DATA.REMEDIATION.AUDIT_MANIFEST_INVALID") from exc
    expected_schema = schema.get("properties", {}).get("schema", {}).get("const")
    if not isinstance(document, dict) or document.get("schema") != expected_schema:
        raise ContentRemediationError(
            f"DATA.REMEDIATION.AUDIT_SCHEMA_UNSUPPORTED: expected={expected_schema} actual={document.get('schema') if isinstance(document, dict) else None}"
        )
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda error: tuple(error.absolute_path))
    if errors:
        location = "/".join(str(value) for value in errors[0].absolute_path) or "$"
        raise ContentRemediationError(f"DATA.REMEDIATION.AUDIT_SCHEMA_INVALID: {location}: {errors[0].message}")
    declared = document.get("baselineDigest")
    core = {key: value for key, value in document.items() if key != "baselineDigest"}
    actual = _digest(_canonical(core))
    if not _validate_digest(declared) or declared != actual:
        raise ContentRemediationError(f"DATA.REMEDIATION.BASELINE_DIGEST_DRIFT: declared={declared} actual={actual}")
    return document


def _normalized_filters(values: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(sorted({value.strip() for value in (values or ()) if value.strip()}))


def _severity_vocabulary() -> tuple[str, ...]:
    try:
        schema = json.loads(AUDIT_SCHEMA_PATH.read_bytes())
        values = schema["$defs"]["issue"]["properties"]["severity"]["enum"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ContentRemediationError("DATA.REMEDIATION.AUDIT_SEVERITY_CONTRACT_INVALID") from exc
    if not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values):
        raise ContentRemediationError("DATA.REMEDIATION.AUDIT_SEVERITY_CONTRACT_INVALID")
    return tuple(values)


def _semantic_queue_refs(document: dict) -> set[str]:
    queue = document.get("semanticReviewQueue") or []
    if not isinstance(queue, list):
        raise ContentRemediationError("DATA.REMEDIATION.SEMANTIC_REVIEW_QUEUE_INVALID")
    refs = set()
    for row in queue:
        if not isinstance(row, dict) or not isinstance(row.get("objectRef"), str) or not row["objectRef"]:
            raise ContentRemediationError("DATA.REMEDIATION.SEMANTIC_REVIEW_QUEUE_INVALID")
        refs.add(row["objectRef"])
    return refs


def _object_rows(document: dict) -> dict[str, dict]:
    rows = {}
    for row in document["objects"]:
        ref, identity, digests, codes = row.get("objectRef"), row.get("identity"), row.get("digests"), row.get("issueCodes")
        if not isinstance(ref, str) or not ref or ref.startswith("/") or ".." in Path(ref).parts:
            raise ContentRemediationError("DATA.REMEDIATION.OBJECT_REF_INVALID")
        if ref in rows:
            raise ContentRemediationError("DATA.REMEDIATION.DUPLICATE_OBJECT_REF")
        if not isinstance(identity, dict):
            raise ContentRemediationError("DATA.REMEDIATION.OBJECT_IDENTITY_INVALID")
        version = identity.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise ContentRemediationError(f"DATA.REMEDIATION.TARGET_VERSION_NOT_INTEGER: {ref}")
        if not isinstance(digests, dict) or not digests or not all(isinstance(key, str) and key and _validate_digest(value) for key, value in digests.items()):
            raise ContentRemediationError("DATA.REMEDIATION.ORIGINAL_DIGESTS_INVALID")
        if not isinstance(codes, list) or any(not isinstance(code, str) or not code for code in codes):
            raise ContentRemediationError("DATA.REMEDIATION.OBJECT_ISSUE_CODES_INVALID")
        rows[ref] = {"objectRef": ref, "version": version, "digests": dict(sorted(digests.items())), "issueCodes": set(codes)}
    return rows


def _final_issues(document: dict, objects: dict[str, dict], severities: tuple[str, ...]) -> dict[str, list[dict]]:
    # semanticReviewQueue 是待复核范围，不是 typed issue；同一对象即使在 queue 中，
    # 其独立存在于 issues[] 的确定机械 issue 仍可生成 remediation request。
    _semantic_queue_refs(document)
    joined: dict[str, list[dict]] = {}
    seen = set()
    for issue in document["issues"]:
        ref, code, severity, facts = (issue.get(key) for key in ("objectRef", "code", "severity", "facts"))
        if ref not in objects:
            raise ContentRemediationError(f"DATA.REMEDIATION.ISSUE_OBJECT_NOT_FOUND: {ref}")
        if code not in objects[ref]["issueCodes"]:
            raise ContentRemediationError(f"DATA.REMEDIATION.ISSUE_JOIN_DRIFT: {ref}:{code}")
        if severity not in severities or not isinstance(facts, dict):
            raise ContentRemediationError("DATA.REMEDIATION.TYPED_ISSUE_INVALID")
        key = (ref, code)
        if key in seen:
            raise ContentRemediationError(f"DATA.REMEDIATION.DUPLICATE_TYPED_ISSUE: {ref}:{code}")
        seen.add(key)
        joined.setdefault(ref, []).append({"code": code, "severity": severity, "facts": facts})
    for ref, row in objects.items():
        if row["issueCodes"] != {issue["code"] for issue in joined.get(ref, [])}:
            raise ContentRemediationError(f"DATA.REMEDIATION.OBJECT_ISSUE_CODES_DRIFT: {ref}")
    return joined


def _request(audit_ref: str, baseline_digest: str, row: dict, issues: list[dict], severity_order: tuple[str, ...]) -> dict:
    codes = sorted({issue["code"] for issue in issues})
    severities = sorted({issue["severity"] for issue in issues}, key=severity_order.index)
    identity = {"baselineDigest": baseline_digest, "objectRef": row["objectRef"], "version": row["version"], "digests": row["digests"], "issueCodes": codes}
    request_id = "content-remediation-" + hashlib.sha256(_canonical(identity)).hexdigest()[:32]
    retire_codes = sorted({issue["code"] for issue in issues if issue["severity"] == "high"})
    return {
        "schema": "quwoquan_data.content_remediation_request.v1", "requestId": request_id,
        "status": "awaiting_execution", "audit": {"manifestRef": audit_ref, "baselineDigest": baseline_digest},
        "original": {"objectRef": row["objectRef"], "version": row["version"], "digests": row["digests"]},
        "targetVersion": row["version"] + 1, "issueCodes": codes, "issueSeverities": severities,
        "requirements": {"sourceRevisionReacquire": "required", "mappingGate": "required", "independentReviewGate": "required", "canonicalPublishAllowed": False},
        "retireCandidate": {"suggested": bool(retire_codes), "executionAllowed": False, "reasonIssueCodes": retire_codes},
    }


def _write_same_or_create(path: Path, body: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if path.is_file() and not path.is_symlink() and path.read_bytes() == body:
            return False
        raise ContentRemediationError(f"DATA.REMEDIATION.CREATE_ONCE_CONFLICT: {path}")
    with os.fdopen(fd, "wb") as handle:
        handle.write(body); handle.flush(); os.fsync(handle.fileno())
    return True


def generate_remediation_requests(*, audit_manifest: Path, output_root: Path, issue_codes: Iterable[str] | None = None, severities: Iterable[str] | None = None) -> dict:
    """只在显式 output root 写 request/result；不读取或修改 canonical publish。"""
    audit_manifest, output_root = audit_manifest.resolve(), output_root.resolve()
    code_filter, severity_filter = _normalized_filters(issue_codes), _normalized_filters(severities)
    severity_order = _severity_vocabulary()
    if set(severity_filter) - set(severity_order):
        raise ContentRemediationError("DATA.REMEDIATION.SEVERITY_FILTER_INVALID")
    audit_root = audit_manifest.parent
    if output_root == audit_root or output_root in audit_manifest.parents or audit_root in output_root.parents:
        raise ContentRemediationError("DATA.REMEDIATION.OUTPUT_ROOT_NOT_INDEPENDENT")
    document = _read_manifest(audit_manifest)
    objects = _object_rows(document)
    joined = _final_issues(document, objects, severity_order)
    requests, selected_issues = [], 0
    for ref, row in objects.items():
        matching = [issue for issue in joined.get(ref, []) if (not code_filter or issue["code"] in code_filter) and (not severity_filter or issue["severity"] in severity_filter)]
        if matching:
            selected_issues += len(matching)
            requests.append(_request(audit_manifest.as_posix(), document["baselineDigest"], row, matching, severity_order))
    requests.sort(key=lambda value: (value["original"]["objectRef"], value["requestId"]))
    refs, request_bodies = [], []
    for request in requests:
        body = _serialized(request); ref = f"requests/{request['requestId']}.json"
        request_bodies.append((output_root / ref, body))
        refs.append({"requestId": request["requestId"], "objectRef": request["original"]["objectRef"], "requestRef": ref, "requestDigest": _digest(body)})
    base_result = {
        "schema": "quwoquan_data.content_remediation_result.v1", "status": "no_matching_issues" if not requests else "requests_created",
        "audit": {"manifestRef": audit_manifest.as_posix(), "baselineDigest": document["baselineDigest"]},
        "filters": {"issueCodes": list(code_filter), "severities": list(severity_filter)},
        "counts": {"auditedObjects": len(objects), "selectedObjects": len(requests), "selectedIssues": selected_issues,
                   "semanticReviewPendingObjects": len(_semantic_queue_refs(document))},
        "requests": refs, "effects": {"originalObjectsModified": False, "canonicalPublishInvoked": False, "retirementExecuted": False, "authorOrReviewerAsserted": False},
    }
    result_path = output_root / "content_remediation_result.json"
    expected = request_bodies + [(result_path, _serialized(base_result))]
    if all(path.is_file() and not path.is_symlink() and path.read_bytes() == body for path, body in expected):
        return dict(base_result, status="same_replay")
    for path, body in expected:
        if path.exists() and (not path.is_file() or path.is_symlink() or path.read_bytes() != body):
            raise ContentRemediationError(f"DATA.REMEDIATION.CREATE_ONCE_CONFLICT: {path}")
    created = []
    try:
        for target, body in expected:
            if _write_same_or_create(target, body): created.append(target)
    except Exception:
        for target in reversed(created): target.unlink(missing_ok=True)
        raise
    return base_result


def handle_content_remediation(args) -> None:
    try:
        result = generate_remediation_requests(audit_manifest=Path(args.audit_manifest), output_root=Path(args.output_root), issue_codes=args.issue_code, severities=args.severity)
    except ContentRemediationError as exc:
        raise SystemExit(f"[governance content-remediation] GATE_BLOCK: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
