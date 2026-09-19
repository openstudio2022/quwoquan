from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from content.release.canonical import object_transaction as transaction

from support.media_fixture import admit_media_body

TRANSACTION_ID = "object-one"
RELEASE_ID = "release-one"
SOURCE_POLICY = "encyclopedia-primary"
CREATOR_ID = "creator_a"
TAG_REF = "Topic/旅行"
OBJECT_REF = "travel/test/entity-" + "a" * 64


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def build_canonical(root: Path) -> Path:
    # Only the roots canonical publish may own. There is no `media` root: bodies
    # belong to the content library, and a fixture that pre-creates one would
    # hand every test a tree the real contract already rejects.
    canonical = root / "publish"
    from support.publish_repository_fixture import make_publish_repository
    make_publish_repository(canonical, "object-transaction-fixture")
    for name in ("creators", "entities", "posts"):
        (canonical / name).mkdir(parents=True, exist_ok=True)
    creator = canonical / "creators" / CREATOR_ID
    write_json(
        creator / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": CREATOR_ID,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": [TAG_REF],
            "entityRefs": [],
        },
    )
    write_json(
        creator / "profile.json",
        {
            "creatorId": CREATOR_ID,
            "authorId": CREATOR_ID,
            "version": 1,
            "status": "active",
            "admission": {
                "processResult": "completed",
                "qualityResult": "passed",
                "evidenceRef": "fixture-author-evidence.json",
                "evidenceDigest": "sha256:" + "a" * 64,
            },
        },
    )
    write_json(creator / "assets.refs.json", {"assets": []})
    (creator / "works.refs.ndjson").write_text("", encoding="utf-8")
    return canonical


def _content_review() -> dict:
    protocol = {"schemaVersion": "1.0.0", "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0"}
    revision = {"contentRevision": 1, "sourceRevision": 1, "layoutRevision": 1}
    digest = "sha256:" + "1" * 64
    actor = lambda session: {"host": "cursor", "modelFamily": "gpt", "sessionId": session,
                             "invocation": {"provider": "openai", "model": "gpt-5", "runId": session + "-run"}}
    return {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": "20260711--travel-homepage-coverage--cn-test--pilot-001",
        "objectRef": f"entities/{OBJECT_REF}",
        "decision": "approved",
        "author": actor("author"), "reviewer": actor("reviewer"),
        "candidateBindings": {"origin": "execution_draft", "page": {"ref": "4.draft/page.md", "digest": digest},
                              "manifest": None, "semanticDocument": None},
        "protocol": protocol, "objectRevision": revision,
        "dispositions": [{"issueId": "semantic-exact", "objectRef": f"entities/{OBJECT_REF}",
            "sourceDigest": digest, "targetDigest": digest, "detectedType": "SEMANTIC_EXACT",
            "proposedMapping": None, "lossFields": [], "severity": "info",
            "actor": {"actorId": "reviewer", "actorType": "independent_reviewer"},
            "reason": "fixture preserves reviewed work", "policyVersion": "1.0.0",
            "reviewStatus": "reviewed_confirmed", "outcome": "auto_continue",
            "processingDisposition": "preserved", "protocol": protocol, "objectRevision": revision}],
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [],
        "assetRights": [{
            "assetRef": "sources/fixture/assets/cover.jpg",
            "sourceUrl": "https://upload.wikimedia.org/example.jpg",
            "license": "CC BY-SA 4.0",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "decision": "approved",
            "issues": [],
        }],
    }


def build_package(
    root: Path,
    canonical: Path,
    *,
    entity_extra: dict | None = None,
) -> Path:
    package_root = root / "package"
    object_root = package_root / "object"
    image = package_root / "cas/image.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"licensed-real-image")
    # 采集阶段就把字节交给内容库，封缄闭包时的存储预算准入才解析得到这条引用；
    # 少了这一步，事务包只能靠上一轮跑剩的库内容才封得住。
    digest = admit_media_body(image.read_bytes())
    digest_hex = digest.removeprefix("sha256:")
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
        f"{digest_hex}.jpg"
    )
    carried = object_root / "media/cover.jpg"
    carried.parent.mkdir(parents=True, exist_ok=True)
    carried.write_bytes(image.read_bytes())
    write_json(
        object_root / "manifest.json",
        {
            "schema": "quwoquan_data.entity_object",
            "finalContentRef": "page.md",
            "objectRef": OBJECT_REF,
            "entityRef": f"/entity/{OBJECT_REF}",
            "version": 1,
            "sourceRefs": ["sources/fixture/source.json"],
            "creatorProfileId": CREATOR_ID,
            **(entity_extra or {}),
            "tagRefs": [TAG_REF],
            "assets": [
                {
                    "assetId": "cover",
                    "objectKey": object_key,
                    "path": "media/cover.jpg",
                    "sha256": digest,
                    "bytes": image.stat().st_size,
                    "sourceRefs": ["sources/fixture/source.json"],
                }
            ],
        },
    )
    evidence_body = b"x"
    evidence_path = object_root / "sources/fixture/evidence.html"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(evidence_body)
    write_json(
        object_root / "sources/fixture/source.json",
        {"schema": "quwoquan_data.publish_source", "sourceId": "fixture", "sourceUrl": "https://zh.wikipedia.org/wiki/真实地点",
         "sourceUseMode": "factual_reference_only", "fetchedAt": "2026-07-11T00:00:00Z", "metadata": {}, "assets": [{"assetId": "cover"}],
         "evidence": [{"path": "evidence.html", "sha256": "sha256:" + hashlib.sha256(evidence_body).hexdigest(), "bytes": len(evidence_body), "kind": "source_snapshot"}]},
    )
    (object_root / "page.md").write_text(
        "# 真实地点\n\n真实正文。\n",
        encoding="utf-8",
    )
    write_json(object_root / "content_review.json", _content_review())
    creator_package_ref = Path("creators") / CREATOR_ID
    creator_package_root = package_root / creator_package_ref
    shutil.copytree(canonical / "creators" / CREATOR_ID, creator_package_root)
    closure = {
        "creatorRefs": [CREATOR_ID],
        "creatorObjects": [
            {
                "creatorRef": CREATOR_ID,
                "packageRef": creator_package_ref.as_posix(),
                "treeDigest": transaction._tree_digest(creator_package_root),
            }
        ],
        "tagRefs": [TAG_REF],
        "sourceRefs": ["sources/fixture/source.json"],
        "casRefs": [
            {
                "sourceRef": "object/media/cover.jpg",
                "objectKey": object_key,
                "sha256": digest,
                "bytes": image.stat().st_size,
            }
        ],
    }
    review = {"contentReviewRef": "content_review.json"}
    review_binding = transaction._review_binding(object_root, {"review": review})
    closure_digest = transaction._closure_digest(
        object_root=object_root,
        object_kind="entities",
        object_ref=OBJECT_REF,
        target_schema="quwoquan_data.entity_object",
        source_policy_revision=SOURCE_POLICY,
        closure=closure,
        cas_rows=[dict(closure["casRefs"][0])],
        review=review_binding,
    )
    write_json(
        package_root / "object_transaction_package.json",
        {
            "schema": transaction.PACKAGE_SCHEMA,
            "transactionId": TRANSACTION_ID,
            "executionId": "20260711--travel-homepage-coverage--cn-test--pilot-001",
            "publishMediaMode": "not_applicable",
            "sourcePolicyRevision": SOURCE_POLICY,
            "target": {
                "layoutSchema": transaction.LAYOUT_SCHEMA,
                "objectKind": "entities",
                "objectRef": OBJECT_REF,
                "objectPath": f"entities/{OBJECT_REF}/1",
                "objectSchema": "quwoquan_data.entity_object",
                "packageObjectRef": "object",
            },
            "closure": closure,
            "review": review,
            "semanticBinding": {key: review_binding[key] for key in ("protocol", "objectRevision", "dispositionsDigest")},
            "objectClosureDigest": closure_digest,
        },
    )
    return package_root
