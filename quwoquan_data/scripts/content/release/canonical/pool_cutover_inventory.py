"""显式离线迁移盘点与纯值转换；不接入 publisher，不写池、媒体或旧证据。

候选不是 admitted，也不是 migrate/delete 裁决。review 转换只改旧机械分类，不签发
新 reviewer、receipt 或授权；使用者仍必须验证原链、内容/来源/媒体和完整新 staging。
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

from content.execution.receipt_chain import _independent_actors, validate_live_receipt_chain
from content.release.canonical.content_pool_record import pool_payload_digest
from content.release.canonical.object_source_identity import validate_object_source_identity
from content.release.canonical.object_transaction_contract import _digest_bytes, _digest_file, _json_bytes, _read_json
from content.release.canonical.pool_cutover import _absolute, _relative, snapshot_pool
from content.release.canonical.review_rights_binding import required_review_asset_refs, validate_content_review_document
from core.schema import assert_valid

_PREFIX = "DATA.CUTOVER.INVENTORY."


def _fail(code: str, detail: object) -> None:
    raise ValueError(f"{_PREFIX}{code}: {detail}")


def _file(root: Path, ref: str) -> Path:
    return _absolute(root / _relative(ref), kind="file")


def _evidence(path: Path) -> dict:
    return {"ref": str(path), "digest": _digest_file(path)}


def convert_review_document(original: dict) -> dict:
    """仅转录机械 usageScope；纯值结果本身绝不是独立 review authority。"""
    converted = copy.deepcopy(original)
    for row in converted.get("assetRights", []):
        if row.get("usageScope") not in {"research", "commercial", "production"}:
            _fail("REVIEW_SCOPE_UNSUPPORTED", row.get("usageScope"))
        row["usageScope"] = "production"
    assert_valid(converted, "content", "content_review", label="offline converted review")
    return converted


def convert_creator_profile(original: dict, authority_path: Path) -> dict:
    """复用现有作者准入原件；只增加 profile 版本，不改人物、头像或资格。"""
    authority = _absolute(authority_path, kind="file")
    document = _read_json(authority)
    assert_valid(document, "content", "author_admission_evidence", label=str(authority))
    admission = original.get("admission") or {}
    if (admission.get("evidenceDigest") != _digest_file(authority)
            or original.get("authorId") not in document["authorIds"]
            or admission.get("processResult") != "completed"
            or admission.get("qualityResult") != "passed"):
        _fail("AUTHOR_AUTHORITY_DRIFT", original.get("authorId"))
    version = original.get("version")
    if type(version) is not int or version < 1:
        _fail("ORIGINAL_IDENTITY_INVALID", original.get("authorId"))
    result = copy.deepcopy(original)
    result["version"] = version + 1
    return result


def _chain(execution: Path, cache: dict):
    key = str(execution)
    if key not in cache:
        try:
            value = validate_live_receipt_chain(execution_id=execution.name, execution_root=execution,
                                               expected_count=3, terminal_verdict="pass")
            _independent_actors(value.receipts[1]["actor"], value.receipts[2]["actor"])
            cache[key] = value
        except (OSError, ValueError, TypeError) as exc:
            cache[key] = str(exc)
    result = cache[key]
    if isinstance(result, str):
        _fail("ORIGINAL_CHAIN_INVALID", result)
    return result


def _bound(chain, sequence: int, ref: str, digest: str) -> None:
    binding = {"scope": "execution", "ref": ref, "digest": digest}
    if sum(row == binding for row in chain.receipts[sequence - 1]["resultRefs"]) != 1:
        _fail("ORIGINAL_REVIEW_BINDING_DRIFT", ref)


def _review_evidence(root: Path, execution: Path, ref: str, manifest: dict, cache: dict) -> tuple[dict, dict]:
    review_path = _file(root, "content_review.json")
    review = _read_json(review_path)
    if (manifest.get("executionId") != execution.name or review.get("executionId") != execution.name
            or review.get("objectRef") != ref):
        _fail("ORIGINAL_REVIEW_BINDING_DRIFT", ref)
    _chain(execution, cache)
    if review_path.read_bytes() != _file(execution, ref + "/5.review/content_review.json").read_bytes():
        _fail("ORIGINAL_REVIEW_BINDING_DRIFT", ref)
    return _execution_review(execution, ref, cache)


def _execution_review(execution: Path, ref: str, cache: dict) -> tuple[dict, dict]:
    chain = _chain(execution, cache)
    review_path = _file(execution, ref + "/5.review/content_review.json")
    review = _read_json(review_path)
    if review.get("executionId") != execution.name or review.get("objectRef") != ref:
        _fail("ORIGINAL_REVIEW_BINDING_DRIFT", ref)
    digest = _digest_file(review_path)
    _bound(chain, 3, ref + "/5.review/content_review.json", digest)
    converted = convert_review_document(review)
    draft_ref = ref + "/" + _relative(review["draft"]["ref"])
    draft_path = _file(execution, draft_ref)
    draft_digest = _digest_file(draft_path)
    if draft_digest != review["draft"]["digest"]:
        _fail("ORIGINAL_DRAFT_DRIFT", ref)
    _bound(chain, 2, draft_ref, draft_digest)
    if converted["decision"] != "approved":
        _fail("ORIGINAL_REVIEW_NOT_APPROVED", ref)
    return converted, {"reviewDigest": digest, "convertedReviewDigest": _digest_bytes(_json_bytes(converted)),
                       "review": _evidence(review_path), "draft": _evidence(draft_path),
                       "author": chain.receipts[1]["actor"], "reviewer": chain.receipts[2]["actor"],
                       "receipts": [_evidence(execution / f"_shared/receipts/{i:03d}-{stage}.json")
                                    for i, stage in enumerate(("1.download", "4.draft", "5.review"), 1)]}


def _record_history(root: Path, ref: str, manifest: dict) -> list[dict]:
    rows = [_read_json(_absolute(p, kind="file")) for p in sorted((root / "_pool/versions").glob("*.json"))]
    if not rows:
        _fail("ORIGINAL_RECORD_MISSING", ref)
    identity = manifest.get("entityId" if ref.startswith("entities/") else "contentId")
    version = manifest.get("version")
    if not identity or type(version) is not int or version < 1:
        _fail("ORIGINAL_IDENTITY_INVALID", ref)
    for row in rows:
        if (row.get("objectId") != identity or row.get("contentVersion") != version
                or row.get("objectRef") != ref.split("/", 1)[1] or type(row.get("recordSequence")) is not int):
            _fail("ORIGINAL_IDENTITY_INVALID", ref)
    rows.sort(key=lambda row: row["recordSequence"])
    if [row["recordSequence"] for row in rows] != list(range(1, len(rows) + 1)):
        _fail("ORIGINAL_RECORD_SEQUENCE_INVALID", ref)
    return rows


def _records(root: Path, ref: str, manifest: dict, review: dict) -> dict:
    latest = _record_history(root, ref, manifest)[-1]
    if latest.get("payloadDigest") != pool_payload_digest(root):
        _fail("ORIGINAL_PAYLOAD_DRIFT", ref)
    digest = _digest_file(root / "content_review.json")
    admission = manifest.get("admission") or {}
    authority_fields = {"processResult": "completed", "qualityResult": "passed", "evidenceRef": "content_review.json",
                        "evidenceDigest": digest, "rightsResult": "passed", "rightsAuthorityRef": ref + "/content_review.json",
                        "rightsAuthorityDigest": digest}
    if any(admission.get(key) != value for key, value in authority_fields.items()):
        _fail("ORIGINAL_RECORD_AUTHORITY_INVALID", ref)
    expected = {"status": "active", "processResult": "completed", "qualityResult": "passed",
                "eligibilityResult": "passed", "evidenceRef": "content_review.json", "evidenceDigest": digest,
                "rightsResult": "passed", "rightsAuthorityRef": ref + "/content_review.json", "rightsAuthorityDigest": digest}
    if any(latest.get(key) != value for key, value in expected.items()):
        _fail("ORIGINAL_RECORD_AUTHORITY_INVALID", ref)
    identity_document = validate_object_source_identity(manifest)
    if latest.get("sourceIdentity") != identity_document or latest.get("sourceAttribution") != manifest.get("sourceAttribution"):
        _fail("ORIGINAL_SOURCE_IDENTITY_DRIFT", ref)
    if review["executionId"] != identity_document["executionId"]:
        _fail("ORIGINAL_REVIEW_BINDING_DRIFT", ref)
    return latest


def _source_index(index_path: Path, execution: Path, assets: dict) -> list:
    if not index_path.exists():
        return []
    index_path = _absolute(index_path, kind="file")
    for asset in _read_json(index_path).get("assets", []):
        asset_ref = (index_path.parent / _relative(asset["fileName"])).relative_to(execution).as_posix()
        if asset_ref in assets and assets[asset_ref] != asset:
            _fail("ORIGINAL_SOURCE_ASSET_DUPLICATE", asset_ref)
        assets[asset_ref] = asset
    return [_evidence(index_path)]


def _sources(execution: Path, ref: str, cache: dict) -> tuple[list, dict]:
    source_refs = _file(execution, ref + "/1.download/source_refs.json")
    document = _read_json(source_refs)
    if document.get("executionId") != execution.name or document.get("objectRef") != ref:
        _fail("ORIGINAL_SOURCE_IDENTITY_DRIFT", ref)
    _bound(_chain(execution, cache), 1, ref + "/1.download/source_refs.json", _digest_file(source_refs))
    evidence, assets = [_evidence(source_refs)], {}
    for row in document["sources"]:
        meta_path = _file(execution, row["metaRef"])
        source_path = _file(execution, row["sourceRef"])
        meta = _read_json(meta_path)
        plan_path = _file(execution, row["sourcePlanRef"])
        if (meta.get("executionId") != execution.name or meta.get("chosenCandidateDigest") != row.get("chosenCandidateDigest")
                or meta.get("sourceMarkdownSha256") != _digest_file(source_path)
                or _digest_file(plan_path) != row.get("sourcePlanDigest")):
            _fail("ORIGINAL_SOURCE_BYTES_DRIFT", row["sourceRef"])
        evidence.extend(_evidence(p) for p in (meta_path, source_path, plan_path))
        evidence.extend(_source_index(meta_path.parent / "assets/index.json", execution, assets))
    if not document["sources"]:
        _fail("ORIGINAL_SOURCE_MISSING", ref)
    return evidence, assets


def _inspect_content(root: Path, execution: Path, ref: str, manifest: dict, cache: dict) -> dict:
    converted, authority = _review_evidence(root, execution, ref, manifest, cache)
    _records(root, ref, manifest, converted)
    source_evidence, assets = _sources(execution, ref, cache)
    validate_content_review_document(converted, execution_id=execution.name, object_ref=ref,
                                    required_asset_refs=required_review_asset_refs(manifest, object_kind=ref.split("/")[0]),
                                    source_assets=assets, require_approved=True)
    draft = _file(execution, ref + "/" + converted["draft"]["ref"])
    text = draft.suffix == ".md"
    if text and _file(root, manifest["finalContentRef"]).read_bytes() != draft.read_bytes():
        _fail("ORIGINAL_REVIEWED_SURFACE_DRIFT", ref)
    return {"classification": "text_surface_mechanical_candidate" if text else "review_preserved_media_projection_required",
            "originalReviewAuthority": authority, "sourceEvidence": source_evidence,
            "remainingGates": ["new_manifest_rights_record_package_conversion", "complete_staging_dependency_and_identity_closure",
                               "exact_media_holder_bytes_not_checked"] + ([] if text else ["reviewed_json_surface_projection_not_checked"])}


def _issue(exc: Exception) -> dict:
    message = str(exc)
    code, separator, detail = message.partition(": ")
    if not separator or not code.startswith(_PREFIX):
        code, detail = _PREFIX + "ORIGINAL_EVIDENCE_INVALID", message
    return {"code": code, "detail": detail}


def _inspect_object(root: Path, ref: str, executions_root: Path, author_authority: Path, cache: dict) -> dict:
    if ref.startswith("creators/"):
        profile = _read_json(_file(root, "profile.json"))
        successor = convert_creator_profile(profile, author_authority)
        return {"classification": "creator_mechanical_candidate", "successorProfile": successor,
                "originalAuthorAuthority": _evidence(author_authority), "remainingGates": ["avatar_bytes_and_profile_closure_not_checked"]}
    manifest = _read_json(_file(root, "manifest.json"))
    execution_id = str((manifest.get("sourceIdentity") or {}).get("executionId") or "")
    if not execution_id or "/" in execution_id or execution_id in {".", ".."}:
        _fail("ORIGINAL_EXECUTION_IDENTITY_MISSING", ref)
    return {"executionId": execution_id, "mediaMode": manifest.get("publishMediaMode"),
            "assetCount": len(manifest.get("assets", [])),
            **_inspect_content(root, executions_root / execution_id, ref, manifest, cache)}


def _carrier(ref: str) -> str:
    if ref.startswith("creators/"):
        return "creator"
    return "homepage" if ref.startswith("entities/") else ref.split("/")[1]


def inventory_pool(*, publish_root: Path, executions_root: Path, author_authority: Path) -> dict:
    """原 byte/authority 的有限只读清单；不裁决、不读取媒体 payload、不写 sidecar。"""
    pool = _absolute(publish_root, kind="tree")
    snapshot = snapshot_pool(pool)
    refs = {row["objectRef"] for row in snapshot["objects"]}
    objects, cache = [], {}
    for before in snapshot["objects"]:
        ref, root = before["objectRef"], pool / before["objectRef"]
        row: dict[str, Any] = {"objectRef": ref, "before": before, "issues": [],
                              "missingDependencyRefs": sorted(set(before["dependencyRefs"]) - refs)}
        try:
            row.update(_inspect_object(root, ref, executions_root, author_authority, cache))
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            row.update(classification="requires_author_review_or_evidence_recovery", issues=[_issue(exc)])
        objects.append(row)
    if snapshot_pool(pool) != snapshot:
        _fail("POOL_CHANGED_DURING_INVENTORY", pool)
    return {"schema": "quwoquan_data.pool_cutover_inventory.v1", "purpose": "offline_inventory_not_admission_or_decision",
            "beforeDigest": snapshot["treeDigest"], "objects": objects,
            "counts": {"occupied": len(objects), "classification": dict(Counter(r["classification"] for r in objects)),
                       "carrier": dict(Counter(_carrier(r["objectRef"]) for r in objects)),
                       "firstBlocker": dict(Counter(r["issues"][0]["code"] for r in objects if r["issues"])),
                       "withAbsentDependency": sum(bool(r["missingDependencyRefs"]) for r in objects)}}


def text_conversion_inventory(report: dict, publish_root: Path, executions_root: Path) -> dict:
    """可重复的全量纯内存转换检查；输出摘要，不落盘 successor 或生成裁决。"""
    from content.release.canonical.pool_cutover_text_conversion import convert_text_object
    rows = []
    for row in report["objects"]:
        if row["classification"] != "text_surface_mechanical_candidate" or row["mediaMode"] != "text_only":
            continue
        ref = row["objectRef"]
        try:
            converted = convert_text_object(object_root=publish_root / ref,
                                            execution_root=executions_root / row["executionId"], object_ref=ref)
            rows.append({"objectRef": ref, "status": "converted_in_memory", "files": len(converted),
                         "manifestDigest": _digest_bytes(converted[Path("manifest.json")]),
                         "recordDigest": _digest_bytes(converted[Path("_pool/versions/1.json")])})
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            rows.append({"objectRef": ref, "status": "blocked", "issue": _issue(exc)})
    return {"counts": dict(Counter(row["status"] for row in rows)), "objects": rows}


def _optional_evidence(path: Path) -> dict:
    return {**_evidence(_absolute(path, kind="file")), "exists": True} if path.exists() else {"ref": str(path), "exists": False}


def _review_copies(roots: list[Path], refs: set[str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {ref: [] for ref in refs}
    for root in roots:
        for path in sorted(root.glob("*/payload/objects/**/content_review.json")):
            review = _read_json(_absolute(path, kind="file"))
            if review.get("objectRef") in result:
                result[review["objectRef"]].append({**_evidence(path), "executionId": review.get("executionId"),
                                                  "role": "archive_copy_not_receipt_authority"})
    return result


def _archived_chain_facts(chain: dict, frozen: dict, path: Path) -> dict:
    receipts = chain.get("receipts", [])
    by_stage = {row["stage"]: row for row in receipts}
    result = {"executionId": chain["executionId"], "handoff": _evidence(path),
              "stages": [row["stage"] for row in receipts], "status": "archive_metadata_only",
              "notProven": ["historical_schema_and_full_protocol", "source_and_media_bytes", "current_staging_admission"]}
    try:
        author, review = by_stage["4.draft"], by_stage["5.review"]
        _independent_actors(author["actor"], review["actor"])
        predecessor = None
        for ordinal, receipt in enumerate(receipts, 1):
            if (receipt["sequence"] != ordinal or receipt["executionId"] != chain["executionId"]
                    or receipt.get("predecessor") != predecessor):
                _fail("ARCHIVED_CHAIN_LINK_DRIFT", chain["executionId"])
            predecessor = {"scope": "execution", "ref": f"_shared/receipts/{ordinal:03d}-{receipt['stage']}.json",
                           "digest": _digest_bytes(_json_bytes(receipt))}
        result.update(author=author["actor"], reviewer=review["actor"], status="independent_actor_and_predecessor_bytes_verified")
        result["reviewBindings"] = [{**{key: binding[key] for key in ("scope", "ref", "digest")},
                                    "embeddedBytesPresent": (binding["scope"], binding["ref"], binding["digest"]) in frozen}
                                   for binding in review.get("resultRefs", [])]
    except (ValueError, KeyError, TypeError) as exc:
        result.update(status="blocked", issue=_issue(exc))
    return result


def _archive_handoffs(roots: list[Path]) -> list[dict]:
    result = []
    for root in roots:
        for path in sorted(root.glob("*/producer_release_handoff.json")):
            document = _read_json(_absolute(path, kind="file"))
            frozen = {}
            for row in document.get("frozenReferences", []):
                raw = base64.b64decode(row["contentBase64"], validate=True)
                if _digest_bytes(raw) != row["digest"]:
                    _fail("ARCHIVED_BYTES_DRIFT", path)
                frozen[row["scope"], row["ref"], row["digest"]] = raw
            result.extend(_archived_chain_facts(chain, frozen, path) for chain in document.get("receiptChains", []))
    return result


def _alternative_review(execution: Path, ref: str, original_root: Path, cache: dict) -> dict:
    result = {"executionId": execution.name, "executionRef": str(execution)}
    try:
        review, evidence = _execution_review(execution, ref, cache)
        sources, assets = _sources(execution, ref, cache)
        validate_content_review_document(review, execution_id=execution.name, object_ref=ref,
                                        required_asset_refs=[row["assetRef"] for row in review["assetRights"]],
                                        source_assets=assets, require_approved=True)
        manifest = _read_json(original_root / "manifest.json")
        draft = _file(execution, ref + "/" + review["draft"]["ref"])
        final = original_root / str(manifest.get("finalContentRef") or "")
        same = draft.read_bytes() == final.read_bytes() if draft.suffix == ".md" and final.is_file() else None
        from content.release.canonical.pool_cutover import _source_digest
        surface = _optional_evidence(execution / ref / "manifest.json")
        source_match = (_source_digest(manifest) == _source_digest(_read_json(execution / ref / "manifest.json"))
                        if surface["exists"] else None)
        result.update(status="independent_chain_verified_not_migration_admission", reviewAuthority=evidence,
                      sourceEvidence=sources, canonicalTextMatchesReviewedDraft=same, projectedManifest=surface,
                      sourceFactsMatchCurrentCanonical=source_match,
                      sameOriginalExecution=execution.name == manifest.get("executionId"))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        result.update(status="blocked", issue=_issue(exc))
    return result


def _legacy_evidence(root: Path, execution: Path, ref: str) -> list[dict]:
    result = []
    for name in ("attestation.json", "evidence_index.json"):
        path = root / name
        if not path.exists():
            continue
        document = _read_json(_absolute(path, kind="file"))
        row = {**_evidence(path), "role": "legacy_audit_not_current_authority", "executionId": document.get("executionId")}
        if name == "evidence_index.json":
            row["indexedEvidence"] = [{"expectedDigest": item.get("sha256"),
                                      **_optional_evidence(execution / ref / _relative(item["ref"]))}
                                     for item in document.get("evidence", [])]
        result.append(row)
    return result


def _recovery_row(row: dict, pool: Path, tasks: Path, executions: list[Path], archives: dict, cache: dict) -> dict:
    ref, root = row["objectRef"], pool / row["objectRef"]
    manifest = _read_json(root / "manifest.json")
    execution_id = manifest.get("sourceIdentity", {}).get("executionId", "")
    execution = tasks / _relative(execution_id)
    records = [_read_json(path) for path in sorted((root / "_pool/versions").glob("*.json"))]
    record = max(records, key=lambda item: item["recordSequence"])
    review = _optional_evidence(root / "content_review.json")
    alternatives = [_alternative_review(candidate, ref, root, cache) for candidate in executions
                    if (candidate / ref / "5.review/content_review.json").is_file()]
    verified = [item for item in alternatives if item["status"] == "independent_chain_verified_not_migration_admission"]
    return {"objectRef": ref, "before": row["before"], "firstIssues": row["issues"],
            "originalExecutionRef": str(execution), "originalExecutionExists": execution.is_dir(),
            "originalExecutionId": execution_id, "manifestExecutionId": manifest.get("executionId"),
            "canonicalReview": review, "manifestReviewDigest": manifest.get("admission", {}).get("evidenceDigest"),
            "recordPayloadMatches": record.get("payloadDigest") == pool_payload_digest(root),
            "recordRightsResult": record.get("rightsResult"), "recordSequence": record["recordSequence"],
            "legacyAudit": _legacy_evidence(root, execution, ref), "archiveReviewCopies": archives[ref],
            "availableExecutionReviews": alternatives,
            "recoveryFact": "verified_review_available_requires_identity_and_source_adjudication" if verified
                            else "no_verified_chain_in_declared_search_scope",
            "notProven": ["original_authority_recovery", "new_package_and_identity_transition", "media_bytes"],
            "missingDependencyRefs": row["missingDependencyRefs"]}


def dependency_closure(report: dict, candidate_refs: set[str]) -> dict:
    rows = {row["objectRef"]: row for row in report["objects"]}
    remaining = set(candidate_refs)
    rounds = []
    while True:
        blocked = [{"objectRef": ref, "dependencyRefs": sorted(set(rows[ref]["before"]["dependencyRefs"]) - remaining)}
                   for ref in sorted(remaining) if set(rows[ref]["before"]["dependencyRefs"]) - remaining]
        if not blocked:
            break
        rounds.append(blocked)
        remaining.difference_update(row["objectRef"] for row in blocked)
    return {"purpose": "dependency_arithmetic_not_admission_or_delete_decision", "inputCount": len(candidate_refs),
            "closedCount": len(remaining), "closedObjectRefs": sorted(remaining), "pruningRounds": rounds}


def _asset_rows(report: dict, pool: Path) -> list[dict]:
    from content.release.canonical.canonical_image_inventory import _source_binding
    result = []
    for row in report["objects"]:
        ref = row["objectRef"]
        if ref.startswith("creators/"):
            continue
        manifest = _read_json(pool / ref / "manifest.json")
        for ordinal, asset in enumerate(manifest.get("assets", [])):
            page, binding = _source_binding(asset)
            result.append({"objectRef": ref, "ordinal": ordinal, "assetId": asset.get("assetId"),
                           "sha256": asset.get("sha256"), "sourcePage": page, "sourceBinding": binding,
                           "perceptualHash": asset.get("perceptualHash"), "kind": asset.get("kind"),
                           "imagePost": ref.startswith("posts/image/"), "contentId": manifest.get("contentId"),
                           "version": manifest.get("version"), "manifestPath": ref + "/manifest.json"})
    return result


def _asset_groups(rows: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if row.get(key):
            groups.setdefault(row[key], []).append(row)
    return [{key: value, "members": members} for value, members in sorted(groups.items())
            if len(members) > 1]


def asset_identity_facts(report: dict, pool: Path) -> dict:
    from content.release.canonical.canonical_image_inventory import _conflict
    rows = _asset_rows(report, pool)
    id_groups = _asset_groups(rows, "assetId")
    drifts = [group for group in id_groups if len({(r["sha256"], r["sourceBinding"]) for r in group["members"]}) > 1]
    image_rows = [row for row in rows if row["perceptualHash"] and len(row["perceptualHash"]) == 16]
    conflicts = []
    for index, row in enumerate(image_rows):
        for peer in image_rows[:index]:
            issue = _conflict(row, peer, path=row["manifestPath"])
            if issue:
                conflicts.append({"code": issue.split(":", 1)[0], "left": row, "right": peer})
    return {"purpose": "declared_metadata_facts_not_media_verification_or_retirement_decision", "assetReferences": len(rows),
            "assetIdBindingDriftGroups": drifts, "sharedSha256Groups": _asset_groups(rows, "sha256"),
            "imagePostSourceWorkGroups": _asset_groups([r for r in rows if r["imagePost"]], "sourcePage"),
            "existingImageConflictRules": conflicts,
            "perceptualHashMissing": [r for r in rows if r["kind"] != "video" and not r["perceptualHash"]],
            "notChecked": ["holder_bytes", "missing_phash_not_recomputed", "source_pages_without_declared_url"]}


def media_review_compatibility(report: dict, pool: Path) -> dict:
    results = []
    for row in report["objects"]:
        if row["issues"] or row["objectRef"].startswith("creators/"):
            continue
        path = pool / row["objectRef"] / "content_review.json"
        review = _read_json(path)
        try:
            assert_valid(review, "content", "content_review", label=row["objectRef"])
            result = {"status": "original_review_bytes_current_schema_valid"}
        except ValueError as exc:
            result = {"status": "original_review_bytes_current_schema_invalid", "detail": str(exc)}
        results.append({"objectRef": row["objectRef"], "review": _evidence(path), **result})
    return {"counts": dict(Counter(row["status"] for row in results)), "objects": results,
            "constraint": "changed review bytes cannot retain original receipt digest; no migration authority created"}


def _recovery_facts(report: dict, pool: Path, tasks: Path, executions: list[Path], archive_roots: list[Path]) -> list[dict]:
    blocked = [row for row in report["objects"] if row["issues"] and not row["objectRef"].startswith("creators/")]
    archives = _review_copies(archive_roots, {row["objectRef"] for row in blocked})
    cache: dict = {}
    recovery = [_recovery_row(row, pool, tasks, executions, archives, cache) for row in blocked]
    archived_chains = _archive_handoffs(archive_roots)
    for row in recovery:
        row["archivedReceiptChains"] = [chain for chain in archived_chains if chain["executionId"] == row["originalExecutionId"]]
        if row["archivedReceiptChains"]:
            row["recoveryFact"] = "archived_chain_present_requires_original_protocol_verification"
        row["canonicalReviewBoundByArchivedReceipt"] = any(
            binding["scope"] == "execution" and binding["ref"] == row["objectRef"] + "/5.review/content_review.json"
            and binding["digest"] == row["canonicalReview"].get("digest") and binding["embeddedBytesPresent"]
            for chain in row["archivedReceiptChains"] for binding in chain.get("reviewBindings", []))
    return recovery


def _dependency_facts(report: dict, text: dict) -> dict:
    creators = {row["objectRef"] for row in report["objects"] if row["classification"] == "creator_mechanical_candidate"}
    converted = {row["objectRef"] for row in text["objects"] if row["status"] == "converted_in_memory"} | creators
    candidates = {row["objectRef"] for row in report["objects"] if not row["issues"]}
    dependencies = [{"objectRef": row["objectRef"], "classification": row["classification"],
                     "dependencyRefs": row["before"]["dependencyRefs"], "executionId": row.get("executionId")}
                    for row in report["objects"] if row["before"]["dependencyRefs"]]
    return {"dependencyEdges": dependencies, "textCandidateClosure": dependency_closure(report, converted),
            "authorityCandidateClosure": dependency_closure(report, candidates)}


def feasibility_report(*, publish_root: Path, executions_root: Path, author_authority: Path, archive_roots: list[Path]) -> dict:
    """有界实物查证报告；不恢复旧文件、不决定迁移/删除、不产生新池。"""
    pool = _absolute(publish_root, kind="tree")
    tasks = _absolute(executions_root, kind="tree")
    archives = [_absolute(root, kind="tree") for root in archive_roots]
    report = inventory_pool(publish_root=pool, executions_root=tasks, author_authority=author_authority)
    executions = sorted(path.parent for path in tasks.glob("*/execution_manifest.json"))
    recovery = _recovery_facts(report, pool, tasks, executions, archives)
    text = text_conversion_inventory(report, pool, tasks)
    report.update(recovery=recovery, textConversion=text, **_dependency_facts(report, text),
                  creatorRecovery=[row for row in report["objects"] if row["issues"] and row["objectRef"].startswith("creators/")],
                  mediaReviewCompatibility=media_review_compatibility(report, pool),
                  assetIdentityFacts=asset_identity_facts(report, pool),
                  searchScope={"executionsRoot": str(tasks), "executionRoots": [str(path) for path in executions],
                               "archiveRoots": [str(path) for path in archives], "exhaustiveOutsideDeclaredRoots": False})
    if snapshot_pool(pool)["treeDigest"] != report["beforeDigest"]:
        _fail("POOL_CHANGED_DURING_INVENTORY", pool)
    report["recoveryCounts"] = dict(Counter(row["recoveryFact"] for row in recovery))
    report["recoveryObjectSets"] = {fact: sorted(row["objectRef"] for row in recovery if row["recoveryFact"] == fact)
                                    for fact in sorted(report["recoveryCounts"])}
    report["implementationEvidence"] = [_evidence(Path(__file__).resolve()),
                                        _evidence(Path(__file__).with_name("pool_cutover_text_conversion.py").resolve())]
    report["stagingValidatorEvidence"] = _evidence(Path(__file__).with_name("pool_cutover.py").resolve())
    return report


def write_inventory_report(report: dict, destination: Path) -> dict:
    """只允许显式工作区单文件create-once，拒绝覆盖、符号链接与保护根。"""
    from core import paths
    from content.release.canonical.pool_cutover import _separate
    workspace = paths.DATA_LOCAL_ROOT / "workspace/unified-cutover"
    _absolute(workspace, kind="tree")
    for protected in (paths.PUBLISH_ROOT, paths.RELEASE_ROOT, paths.LIBRARY_ROOT, paths.carried_media_root()):
        _separate(workspace.resolve(), protected.resolve())
    target = destination.absolute()
    if target.parent != workspace or target.suffix != ".json" or target.is_symlink():
        _fail("REPORT_PATH_FORBIDDEN", target)
    raw = _json_bytes(report)
    if len(raw) > 16 * 1024 * 1024:
        _fail("REPORT_SIZE_LIMIT", len(raw))
    with target.open("xb") as handle:
        handle.write(raw)
    return {"reportRef": str(target), "digest": _digest_bytes(raw), "bytes": len(raw), "purpose": report["purpose"]}


def register_parser(actions: argparse._SubParsersAction) -> None:
    parser = actions.add_parser("inventory", help="显式只读原件盘点；不迁移或签发准入")
    parser.add_argument("--publish-root", required=True, type=Path)
    parser.add_argument("--executions-root", required=True, type=Path)
    parser.add_argument("--author-authority", required=True, type=Path)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--check-text-conversion", action="store_true", help="纯内存核验无媒体对象转换，不写 staging")
    parser.add_argument("--archive-root", action="append", default=[], type=Path, help="显式只读release根；启用恢复/依赖/资产事实盘点")
    parser.add_argument("--report-path", type=Path, help="仅在unified-cutover工作区create-once输出报告")
    parser.set_defaults(handler=handle_inventory)


def handle_inventory(args: argparse.Namespace) -> None:
    inputs = dict(publish_root=args.publish_root, executions_root=args.executions_root, author_authority=args.author_authority)
    result = feasibility_report(**inputs, archive_roots=args.archive_root) if args.archive_root else inventory_pool(**inputs)
    if args.check_text_conversion and "textConversion" not in result:
        result["textConversion"] = text_conversion_inventory(result, args.publish_root, args.executions_root)
    if args.report_path:
        print(json.dumps(write_inventory_report(result, args.report_path), ensure_ascii=False))
        return
    if args.summary:
        result.pop("objects")
        if "textConversion" in result:
            result["textConversion"].pop("objects")
    print(json.dumps(result, ensure_ascii=False, indent=2))
