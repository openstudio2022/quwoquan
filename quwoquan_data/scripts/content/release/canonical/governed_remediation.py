"""Finite governed replacement/retirement transaction over an independent publish repository.

This is an object-transaction extension, not a repair manager: prepare freezes one exact
multi-object delta; apply runs it once under the canonical publish lock and rolls back every
materialized path on a pre-receipt failure.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from content.release.canonical.canonical_inventory import apply_inventory_delta, load_or_bootstrap_inventory, write_inventory
from content.release.canonical.content_pool_record import build_canonical_pool_record, latest_pool_record, pool_payload_digest
from content.release.canonical.object_transaction_contract import ObjectTransactionError, _digest_bytes, _digest_file, _json_bytes, _read_json, _tree_digest
from content.release.canonical.object_transaction_delta import apply_forward_delta, revert_applied_delta
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.object_transaction_audit import validate_publish_invariants
from content.release.canonical.pool_cutover_storage import write_once
from core.publish_repository import canonical_files, require_publish_repository
from core.schema import assert_valid
from content.release.canonical.review_rights_binding import validate_content_review_document
from core.semantic_quality_gates import digest as semantic_digest, write_human_decision

SCHEMA = "quwoquan_data.governed_remediation_transaction.v1"
HOME = "entities/地点/中国/北京市/西城区/宗教场所/p0001/历代帝王庙/1"
ARTICLE = "posts/article/历史/p0001/历代帝王庙：南京迁北京与188位怎样入祀/1"


def _fail(code: str, detail: object) -> None:
    raise ObjectTransactionError(f"DATA.REMEDIATION.{code}: {detail}")


def _safe_ref(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or path.as_posix() != value or ".." in path.parts or "\\" in value:
        _fail("REF_INVALID", value)
    return value


def _binding(path: Path, *, tree: bool = False) -> dict[str, str]:
    return {"ref": str(path), "digest": _tree_digest(path) if tree else _digest_file(path)}


def _verify_binding(row: Mapping[str, Any], *, tree: bool = False) -> Path:
    path = Path(str(row.get("ref") or ""))
    if not path.is_absolute() or not (path.is_dir() if tree else path.is_file()):
        _fail("EVIDENCE_MISSING", path)
    actual = _tree_digest(path) if tree else _digest_file(path)
    if actual != row.get("digest"):
        _fail("EVIDENCE_DRIFT", path)
    return path


def _file_rows(root: Path) -> list[dict[str, Any]]:
    return [{"path": p.relative_to(root).as_posix(), "sha256": _digest_file(p), "bytes": p.stat().st_size}
            for p in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())]


def _tree_from_rows(rows: list[dict[str, Any]]) -> str:
    return _digest_bytes(_json_bytes(rows))


def canonical_tree_digest(root: Path) -> str:
    require_publish_repository(root)
    rows = [{"path": p.relative_to(root).as_posix(), "sha256": _digest_file(p), "bytes": p.stat().st_size}
            for p in canonical_files(root)]
    return _tree_from_rows(rows)


def make_article_disposition(*, article_root: Path, recommendation: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _read_json(article_root / "manifest.json")
    revision = dict(recommendation["inputObjectRevision"])
    protocol = dict(recommendation["protocol"])
    reason_codes = list(recommendation["reasonCodes"])
    row = {
        "issueId": semantic_digest({"objectRef": ARTICLE, "code": "ARTICLE.CARRIER_DEVIATION", "protocol": protocol, "objectRevision": revision, "reasonCodes": reason_codes}),
        "objectRef": ARTICLE,
        "sourceDigest": recommendation["r0Digests"]["source"],
        "targetDigest": recommendation["r0Digests"]["object"],
        "detectedType": "ARTICLE.CARRIER_DEVIATION",
        "proposedMapping": None,
        "lossFields": reason_codes,
        "severity": "critical",
        "actor": dict(recommendation["author"] | {"actorId": recommendation["author"]["sessionId"], "actorType": "producer"}) if False else {"actorId": recommendation["author"]["sessionId"], "actorType": "producer"},
        "reason": "；".join(reason_codes) + "；该错误百科改写 Article 不能作为独立作品继续发布",
        "policyVersion": "1.0.0",
        "reviewStatus": "human_decision_pending",
        "outcome": "requires_human_decision",
        "processingDisposition": "blocked_unsafe",
        "protocol": protocol,
        "objectRevision": revision,
    }
    assert manifest["contentId"] == "qwq_data_ffcf7af2d59b1b21e6a25af6"
    assert_valid(row, "content", "semantic_disposition", label="article retirement disposition")
    return row


def record_human_abandon(*, attempt_root: Path, article_root: Path) -> dict[str, Any]:
    recommendation = _read_json(attempt_root / "article/author_recommendation.json")
    issue = make_article_disposition(article_root=article_root, recommendation=recommendation)
    decision_id = "decision-" + semantic_digest({"issueId": issue["issueId"], "decision": "abandon_object"}).split(":", 1)[1][:32]
    decision = {
        "schema": "quwoquan_data.semantic_human_decision", "decisionId": decision_id,
        "issueId": issue["issueId"], "inputDigest": semantic_digest(issue), "decision": "abandon_object",
        "actor": {"actorId": "cursor_user_authorized_operator", "actorType": "human_operator"},
        "reason": "用户明确选择退役错误百科改写 Article；该内容缺少独立 writingIntent 与独立 publish angle。",
        "inputProtocol": issue["protocol"], "inputObjectRevision": issue["objectRevision"],
        "resultProtocol": issue["protocol"], "resultObjectRevision": issue["objectRevision"],
    }
    destination = attempt_root / "article/semantic_human_decision.json"
    status = write_human_decision(destination, decision, issue)
    binding = _binding(destination)
    reviewed = attempt_root / "package.reviewed.index.json"
    governed_index = attempt_root / "package.governed.index.json"
    index = {"schema": "quwoquan_data.remediation_governed_package_index.v1",
             "predecessor": _binding(reviewed), "humanDecision": binding,
             "entries": [_binding(reviewed), binding]}
    if governed_index.exists():
        if governed_index.read_bytes() != _json_bytes(index): _fail("GOVERNED_INDEX_CONFLICT", governed_index)
    else:
        governed_index.write_bytes(_json_bytes(index))
    return {"status": status, "issue": issue, "decision": decision, "binding": binding, "index": _binding(governed_index)}


def _canonical_homepage(*, candidate: Path, old_root: Path, destination: Path, review_receipt: Path) -> None:
    manifest = _read_json(candidate / "manifest.json")
    if manifest.get("entityId") != "entity-temple-of-emperors" or manifest.get("entityRef") != "/entity/travel/beijing/temple-of-emperors":
        _fail("HOMEPAGE_IDENTITY_DRIFT", manifest.get("entityId"))
    if manifest.get("version") != 2 or manifest.get("objectRevision") != {"contentRevision": 2, "sourceRevision": 2, "layoutRevision": 2}:
        _fail("HOMEPAGE_REVISION_INVALID", manifest.get("objectRevision"))
    if manifest.get("protocol") != {"schemaVersion": "1.0.0", "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0"}:
        _fail("HOMEPAGE_PROTOCOL_INVALID", manifest.get("protocol"))
    allowed = {
        "schema","entityId","version","finalContentRef","assets","label","domain","type","executionId","entityRef","geographyMode","tagRefs","geoTagRef",
        "sourceRefs","sourceUrls","primarySource","sourceAttribution","authorId","creatorProfileId","creatorArchetype","creatorProfileDigest","creatorDisclosure",
        "experienceClaimMode","authorQualitySignals","status","semanticDocumentRef","semanticDocumentDigest","semanticCanonicalDigest","semanticFingerprint","semanticParseCoverage",
        "captureCoverage","objectRevision","protocol","sourceRevisionId","qualificationEvidenceRef","qualificationEvidenceDigest","locatorMap"
    }
    manifest = {key: copy.deepcopy(value) for key, value in manifest.items() if key in allowed}
    manifest["status"] = "active"
    old = _read_json(old_root / "manifest.json")
    manifest["authorId"] = old["authorId"]
    manifest["creatorProfileId"] = old["creatorProfileId"]
    for key in ("creatorArchetype","creatorProfileDigest","creatorDisclosure","experienceClaimMode","authorQualitySignals"):
        if key in old: manifest[key] = copy.deepcopy(old[key])
    from content.release.canonical.object_source_identity import source_identity_digest
    from core.source_digest import content_source_revision
    source_digest = _digest_file(candidate.parent / "package.governed.index.json")
    entity_catalog_digest = old["sourceIdentity"]["entityCatalogDigest"]
    source_identity = {"executionId": manifest["executionId"], "sourceDigest": source_digest,
                       "entityCatalogDigest": entity_catalog_digest,
                       "sourceRevision": content_source_revision(source_digest=source_digest, entity_catalog_digest=entity_catalog_digest)}
    source_identity["identityDigest"] = source_identity_digest(source_identity)
    manifest["sourceIdentity"] = source_identity
    review_digest = _digest_file(review_receipt)
    manifest["admission"] = {"processResult":"completed","qualityResult":"passed","rightsResult":"passed",
                             "rightsAuthorityRef": f"{HOME}/content_review.json", "rightsAuthorityDigest": review_digest,
                             "evidenceRef":"content_review.json","evidenceDigest":review_digest}
    destination.mkdir(parents=True)
    for relative in ("page.md", "semantic.document.json", "sources", "media"):
        source = candidate / relative
        target = destination / relative
        shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)
    shutil.copy2(review_receipt, destination / "content_review.json")
    (destination / "manifest.json").write_bytes(_json_bytes(manifest))
    assert_valid(manifest, "publish", "entity", label="governed homepage v2")
    semantic = _read_json(destination / "semantic.document.json")
    if _digest_file(destination / "semantic.document.json") != manifest["semanticDocumentDigest"] or "sha256:" + str(semantic.get("canonicalDigest") or "").removeprefix("sha256:") != manifest["semanticCanonicalDigest"]:
        _fail("SEMANTIC_DIGEST_DRIFT", destination)
    for asset in manifest["assets"]:
        path = destination / _safe_ref(asset["path"])
        if not path.is_file() or path.stat().st_size != asset["bytes"] or _digest_file(path) != asset["sha256"]:
            _fail("MEDIA_DIGEST_DRIFT", asset["assetId"])
    shutil.copytree(old_root / "records", destination / "records")
    record = build_canonical_pool_record(object_root=destination, object_type="homepage", object_ref="travel/beijing/temple-of-emperors")
    if record["recordSequence"] != 2 or record["contentVersion"] != 2:
        _fail("RECORD_SUCCESSOR_INVALID", record)
    (destination / "records/2.json").write_bytes(_json_bytes(record))
    assert latest_pool_record(destination, "homepage")["recordSequence"] == 2


def _ingest(source: Path, blobs: Path) -> dict[str, Any]:
    digest = _digest_file(source); hexed = digest.split(":", 1)[1]
    target = blobs / hexed[:2] / hexed
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists(): shutil.copy2(source, target)
    return {"blobRef": target.relative_to(blobs.parent.parent.parent).as_posix(), "sha256": digest, "bytes": source.stat().st_size}


def _delta(*, publish_root: Path, replacement: Path, run_root: Path, before_inventory: Mapping[str, Any]) -> tuple[dict, dict]:
    blobs = run_root / "delta/blobs/sha256"; entries=[]
    desired = {p.relative_to(replacement).as_posix(): p for p in replacement.rglob("*") if p.is_file()}
    old_home = publish_root / HOME
    for rel, source in sorted(desired.items()):
        dest_text=f"{HOME}/{rel}"; dest=publish_root/dest_text; new=_ingest(source, blobs)
        if dest.is_file():
            if _digest_file(dest)==new["sha256"]: continue
            before=_ingest(dest, blobs); entries.append({"destination":dest_text,"operation":"replace",**new,"beforeBlobRef":before["blobRef"],"beforeSha256":before["sha256"],"beforeBytes":before["bytes"]})
        else: entries.append({"destination":dest_text,"operation":"create",**new})
    for path in sorted(p for p in old_home.rglob("*") if p.is_file()):
        rel=path.relative_to(old_home).as_posix()
        if rel not in desired:
            before=_ingest(path, blobs); entries.append({"destination":f"{HOME}/{rel}","operation":"delete","beforeBlobRef":before["blobRef"],"beforeSha256":before["sha256"],"beforeBytes":before["bytes"]})
    article_root=publish_root/ARTICLE
    for path in sorted(p for p in article_root.rglob("*") if p.is_file()):
        before=_ingest(path, blobs); entries.append({"destination":path.relative_to(publish_root).as_posix(),"operation":"delete","beforeBlobRef":before["blobRef"],"beforeSha256":before["sha256"],"beforeBytes":before["bytes"]})
    entries.sort(key=lambda x:x["destination"])
    after=apply_inventory_delta(before_inventory, entries, publish_root=publish_root)
    manifest={"schema":"quwoquan_data.canonical_transaction_delta","transactionId":run_root.name,"executionId":run_root.name,"targetPrefix":HOME,
              "beforeMerkle":before_inventory["stats"]["merkleRoot"],"afterMerkle":after["stats"]["merkleRoot"],"beforeInventoryDigest":before_inventory["inventoryDigest"],"afterInventoryDigest":after["inventoryDigest"],
              "entries":entries,"createdFileCount":sum(e["operation"]=="create" for e in entries),"replacedFileCount":sum(e["operation"]=="replace" for e in entries),"deletedFileCount":sum(e["operation"]=="delete" for e in entries),"deltaBytes":sum(e.get("bytes",0) for e in entries)}
    unsigned=dict(manifest); manifest["deltaDigest"]=_digest_bytes(_json_bytes(unsigned))
    (run_root/"delta/manifest.json").parent.mkdir(parents=True,exist_ok=True); (run_root/"delta/manifest.json").write_bytes(_json_bytes(manifest))
    return manifest,after


def prepare(*, publish_root: Path, attempt_root: Path, run_root: Path, owner_identity: Mapping[str, str], release_roots: list[Path], environment_bindings: list[Path]) -> dict[str, Any]:
    require_publish_repository(publish_root)
    if run_root.exists(): _fail("OUTPUT_EXISTS", run_root)
    _verify_binding(owner_identity)
    review=attempt_root/"independent-review/canonical-content-review.json"; reviewed=attempt_root/"package.governed.index.json"
    review_doc = _read_json(review)
    manifest = _read_json(attempt_root/"homepage-v2-candidate/manifest.json")
    try:
        validate_content_review_document(
            review_doc, execution_id=str(manifest.get("executionId") or ""),
            object_ref=str(review_doc.get("objectRef") or ""),
            required_asset_refs=tuple(str(row.get("path") or "") for row in manifest.get("assets") or []),
            object_aliases=(), require_approved=True, candidate_root=attempt_root,
        )
    except ObjectTransactionError as exc:
        _fail("REVIEW_INVALID", str(exc))
    identity = review_doc.get("objectIdentity") or {}
    if identity.get("entityId") != manifest.get("entityId") or identity.get("entityRef") != manifest.get("entityRef"):
        _fail("REVIEW_IDENTITY_DRIFT", identity)
    decision=record_human_abandon(attempt_root=attempt_root, article_root=publish_root/ARTICLE)
    run_root.mkdir(parents=True)
    replacement=run_root/"replacement"; _canonical_homepage(candidate=attempt_root/"homepage-v2-candidate",old_root=publish_root/HOME,destination=replacement,review_receipt=review)
    before_inventory=load_or_bootstrap_inventory(publish_root)
    before_tree=canonical_tree_digest(publish_root); article_digest=_tree_digest(publish_root/ARTICLE)
    release_hits=[]
    needles=("qwq_data_ffcf7af2d59b1b21e6a25af6", ARTICLE)
    for root in release_roots:
        if root.exists():
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                try: text=path.read_text(errors="ignore")
                except OSError: continue
                if any(n in text for n in needles): release_hits.append(_binding(path))
    protected=[{"category":"release","binding":_binding(root,tree=True)} for root in release_roots if root.exists()]
    protected += [{"category":"environment_binding","binding":_binding(path)} for path in environment_bindings if path.exists()]
    protected += [{"category":"review","binding":_binding(review)},{"category":"reviewed_index","binding":_binding(reviewed)},{"category":"human_decision","binding":decision["binding"]},{"category":"owner_identity","binding":dict(owner_identity)}]
    delta,after_inventory=_delta(publish_root=publish_root,replacement=replacement,run_root=run_root,before_inventory=before_inventory)
    expected_prefixes=(HOME+"/",ARTICLE+"/")
    unexpected=[e["destination"] for e in delta["entries"] if not e["destination"].startswith(expected_prefixes)]
    if unexpected: _fail("UNEXPECTED_PATH",unexpected)
    archive=run_root/"article.before.tar"
    with tarfile.open(archive,"x") as tar:
        for path in sorted(p for p in (publish_root/ARTICLE).rglob("*") if p.is_file()): tar.add(path,arcname=path.relative_to(publish_root/ARTICLE).as_posix(),recursive=False)
    report={"schema":SCHEMA,"status":"prepared_not_applied","specRef":"canonical-content-identity-recovery#REQ-001/GWT-001/GWT-003","ownerIdentity":dict(owner_identity),"publishRoot":str(publish_root),"homepageRef":HOME,"articleRef":ARTICLE,
            "beforeCanonicalTreeDigest":before_tree,"beforeMerkle":delta["beforeMerkle"],"afterMerkle":delta["afterMerkle"],"deltaDigest":delta["deltaDigest"],"changedPaths":[e["destination"] for e in delta["entries"] if e["operation"]!="delete"],"deletedPaths":[e["destination"] for e in delta["entries"] if e["operation"]=="delete"],
            "homepage":{"entityId":"entity-temple-of-emperors","entityRef":"/entity/travel/beijing/temple-of-emperors","version":2,"recordSequence":2,"payloadDigest":pool_payload_digest(replacement),"treeDigest":_tree_digest(replacement)},
            "article":{"contentId":"qwq_data_ffcf7af2d59b1b21e6a25af6","beforeTreeDigest":article_digest,"decision":decision["binding"],"archive":_binding(archive),"historicalReleaseRefs":release_hits},"protected":protected,"afterInventoryDigest":after_inventory["inventoryDigest"]}
    report["attestationDigest"]=_digest_bytes(_json_bytes(report)); write_once(run_root/"dry-run.json",report)
    return report


def apply(*, run_root: Path, expected_attestation: str) -> dict[str, Any]:
    report=_read_json(run_root/"dry-run.json")
    embedded=report.pop("attestationDigest",None); actual=_digest_bytes(_json_bytes(report)); report["attestationDigest"]=embedded
    if embedded!=expected_attestation or actual!=embedded: _fail("ATTESTATION_DRIFT",run_root)
    publish_root=Path(report["publishRoot"]); require_publish_repository(publish_root)
    for row in report["protected"]: _verify_binding(row["binding"],tree=Path(row["binding"]["ref"]).is_dir())
    if canonical_tree_digest(publish_root)!=report["beforeCanonicalTreeDigest"]: _fail("BEFORE_TREE_DRIFT",publish_root)
    current=load_or_bootstrap_inventory(publish_root)
    if current["stats"]["merkleRoot"]!=report["beforeMerkle"]: _fail("BEFORE_MERKLE_DRIFT",publish_root)
    delta=_read_json(run_root/"delta/manifest.json")
    with canonical_publish_lock(publish_root):
        if canonical_tree_digest(publish_root)!=report["beforeCanonicalTreeDigest"]: _fail("BEFORE_TREE_DRIFT",publish_root)
        applied=apply_forward_delta(publish_root=publish_root,run_root=run_root,manifest=delta)
        try:
            after=apply_inventory_delta(current,delta["entries"],publish_root=publish_root)
            if after["stats"]["merkleRoot"]!=report["afterMerkle"]: _fail("AFTER_MERKLE_DRIFT",publish_root)
            closure=validate_publish_invariants(publish_root)
            if closure["status"]!="passed": _fail("AFTER_CLOSURE_INVALID",closure["issues"][:10])
            home=publish_root/HOME
            if latest_pool_record(home,"homepage")["recordSequence"]!=2 or (publish_root/ARTICLE).exists(): _fail("READBACK_INVALID",publish_root)
            write_inventory(publish_root,after)
        except BaseException:
            revert_applied_delta(publish_root=publish_root,run_root=run_root,entries=applied); raise
    result={"schema":"quwoquan_data.governed_remediation_result.v1","status":"applied","attestationDigest":expected_attestation,"beforeMerkle":report["beforeMerkle"],"afterMerkle":report["afterMerkle"],"homepage":report["homepage"],"article":report["article"],"closure":closure}
    return {"report":result,"evidence":write_once(run_root/"applied.json",result)}
