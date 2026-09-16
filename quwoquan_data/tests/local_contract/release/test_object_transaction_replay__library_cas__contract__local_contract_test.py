# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from content.release.canonical import handler_cli as release_handler
from content.release.canonical import handler_consumers
from content.release.canonical.application import rollback_object_transaction
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _closure_digest,
    _review_binding,
    _tree_digest,
    _verify_package,
    _write_json,
)
from content.release.canonical.post_transaction import build_post_object_transaction_package
from local_contract.release.test_publish_package__self_contained__local_contract_test import (
    _admit_dependencies,
    _package,
)
from content.release.canonical.object_transaction_replay import (
    replay_object_transaction_package,
)
from core.io import read_json
from support.post_object_transaction_fixture import POST_REF, _isolate_creator_avatar_cas


@pytest.fixture
def replay_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    execution, package, publish, transaction_id, _, _ = _package(tmp_path, monkeypatch)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = read_json(manifest_path)
    manifest.update(generator="agent", createdAt="2026-07-18T04:00:00Z", updatedAt="2026-07-18T04:00:00Z")
    for asset in manifest["assets"]:
        asset["collectionPageUrl"] = manifest["sourceUrls"][0]
    _write_json(manifest_path, manifest)
    build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF,
        transaction_id=transaction_id, package_root=package,
    )
    _admit_dependencies(package, publish)
    library = tmp_path / "media-library"
    library.mkdir()
    return dict(replay_id="exact-replay", source_package_root=package,
                media_library_root=library, output_root=tmp_path / "replay-output",
                publish_root=publish)


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _homepage_case(case: dict) -> dict:
    """将已入池无图主页整体迁到现役 review、身份与 revision 契约。"""
    package = case["source_package_root"]
    publish = case["publish_root"]
    object_root = package / "object"
    document = read_json(package / "object_transaction_package.json")
    homepage = next((publish / "entities").rglob("manifest.json")).parent
    shutil.rmtree(object_root)
    shutil.copytree(homepage, object_root)

    logical_ref = "地点/景区/西湖/1"
    review_ref = "entities/" + logical_ref
    manifest_path = object_root / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["entityRef"] = "/entity/" + logical_ref
    for retired in ("distributionDecision", "publicationAdmission", "usageScope", "variantPurpose"):
        manifest.pop(retired, None)
    _write_json(manifest_path, manifest)

    page_body = (object_root / "page.md").read_bytes()
    draft_digest = _sha256(page_body)
    source_document = read_json(object_root / manifest["sourceRefs"][0])
    excerpt = next(row for row in source_document["evidence"] if row["kind"] == "source_excerpt")
    source_body = (object_root / manifest["sourceRefs"][0]).parent.joinpath(excerpt["path"]).read_bytes()
    source_digest = _sha256(source_body)
    assert excerpt["sha256"] == source_digest and excerpt["bytes"] == len(source_body)

    actor = lambda session: {
        "host": "cursor", "modelFamily": "gpt", "sessionId": session,
        "invocation": {"provider": "openai", "model": "gpt-5", "runId": session + "-run"},
    }
    protocol = {
        "schemaVersion": "1.0.0", "dialectVersion": "1.0.0",
        "canonicalizationVersion": "1.0.0",
    }
    revision = {"contentRevision": 1, "sourceRevision": 1, "layoutRevision": 1}
    counts = {"title": 1, "heading": 0, "paragraph": 1, "list": 0,
              "tableLogicalCell": 0, "footnote": 0, "media": 0}
    sequence_digest = _sha256(json.dumps({
        "objectRef": review_ref, "sourceDigest": source_digest,
        "draftDigest": draft_digest, "objectRevision": revision,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    disposition = {
        "issueId": "homepage-semantic-exact", "objectRef": review_ref,
        "sourceDigest": source_digest, "targetDigest": draft_digest,
        "detectedType": "SEMANTIC_EXACT", "proposedMapping": None,
        "lossFields": [], "severity": "info",
        "actor": {"actorId": "homepage-reviewer", "actorType": "independent_reviewer"},
        "reason": "verified fixture homepage preserves the acquired source semantics",
        "policyVersion": "1.0.0", "reviewStatus": "reviewed_confirmed",
        "outcome": "auto_continue", "processingDisposition": "preserved",
        "protocol": protocol, "objectRevision": revision,
    }
    review = {
        "schema": "quwoquan_data.content_review", "stage": "5.review",
        "executionId": document["executionId"], "objectRef": review_ref,
        "decision": "approved", "author": actor("homepage-author"),
        "reviewer": actor("homepage-reviewer"),
        "candidateBindings": {
            "origin": "execution_draft",
            "page": {"ref": "4.draft/page.md", "digest": draft_digest},
            "manifest": None, "semanticDocument": None,
        },
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [], "assetRights": [],
        "semanticReport": {
            "reviewedCarrier": "homepage", "carrierCompatible": True,
            "sources": [{
                "sourceRef": "sources/commons/source.md", "sourceDigest": source_digest,
                "parseStatus": "complete", "dialect": "markdown", "dialectVersion": "1",
                "capabilities": ["title", "paragraph"],
                "sourceCounts": counts, "draftCounts": counts,
                "sourceSequenceDigest": sequence_digest,
                "draftSequenceDigest": sequence_digest,
            }],
            "homepageFidelity": {
                "title": True, "headingTree": True, "paragraphOrder": True,
                "links": True, "nestedLists": True, "tableLogicalGrid": True,
                "footnotes": True, "mediaCaptionOrder": True,
            },
            "issues": [],
        },
        "protocol": protocol, "objectRevision": revision,
        "dispositions": [disposition],
    }
    _write_json(object_root / "content_review.json", review)

    document["publishMediaMode"] = "text_only"
    document["sourcePolicyRevision"] = "encyclopedia-primary"
    document["target"].update(
        objectKind="entities", objectSchema=manifest["schema"], objectRef=logical_ref,
        objectPath=homepage.relative_to(publish).as_posix(),
    )
    document["closure"]["casRefs"] = []
    review_binding = _review_binding(object_root, document)
    document["semanticBinding"] = {
        key: review_binding[key]
        for key in ("protocol", "objectRevision", "dispositionsDigest")
    }
    document["objectClosureDigest"] = _closure_digest(
        object_root=object_root, object_kind="entities", object_ref=logical_ref,
        target_schema=manifest["schema"], source_policy_revision=document["sourcePolicyRevision"],
        closure=document["closure"], cas_rows=[], review=review_binding,
    )
    _write_json(package / "object_transaction_package.json", document)
    _verify_package(package, canonical_root=publish, require_target_absent=False)
    shutil.rmtree(homepage)
    return case


def _library_entry(root: Path, digest: str) -> Path:
    value = digest.removeprefix("sha256:")
    return root / value[:2] / value[2:4] / value


def test_exact_package_replay_cli_binds_explicit_library_and_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: dict[str, object] = {}

    def replay(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {
            "schema": "quwoquan_data.object_transaction_package_replay_result",
            "status": "applied",
        }

    monkeypatch.setattr(handler_consumers, "replay_object_transaction_package", replay)
    parser = argparse.ArgumentParser()
    release_handler.register_parser(
        parser.add_subparsers(dest="command", required=True)
    )
    args = parser.parse_args(
        [
            "release",
            "object-transaction",
            "replay-package",
            "--replay-id",
            "entity-replay",
            "--source-package-root",
            str(tmp_path / "source-package"),
            "--media-library-root",
            str(tmp_path / "library"),
            "--output-root",
            str(tmp_path / "output"),
            "--publish-root",
            str(tmp_path / "publish"),
        ]
    )
    args.handler(args)

    assert observed == {
        "replay_id": "entity-replay",
        "source_package_root": tmp_path / "source-package",
        "media_library_root": tmp_path / "library",
        "output_root": (tmp_path / "output").resolve(),
        "publish_root": (tmp_path / "publish").resolve(),
    }
    assert json.loads(capsys.readouterr().out)["status"] == "applied"


@pytest.mark.parametrize("missing_media", [False, True])
def test_exact_package_replay_restores_media_and_keeps_logical_identity(replay_case, missing_media):
    source_package = replay_case["source_package_root"]
    package = read_json(source_package / "object_transaction_package.json")
    canonical = replay_case["publish_root"] / package["target"]["objectPath"]
    assert package["target"]["objectPath"] == "posts/image/风光/p0001/西湖光影/1"
    for row in package["closure"]["casRefs"]:
        source = source_package / row["sourceRef"]
        target = _library_entry(replay_case["media_library_root"], row["sha256"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if missing_media:
            source.unlink()
    source_digest = _tree_digest(source_package)
    result = replay_object_transaction_package(**replay_case)
    assert result["status"] == "applied"
    assert result["canonicalObjectRef"] == "posts/" + POST_REF
    assert result["poolRecordRepaired"] is False
    assert (canonical / "manifest.json").is_file()
    assert not (replay_case["publish_root"] / "posts" / POST_REF).exists()
    assert _tree_digest(source_package) == source_digest
    assert _tree_digest(canonical) == _tree_digest(Path(result["packageRoot"]) / "object")
    repeated = replay_object_transaction_package(**replay_case)
    assert repeated["idempotent"] is True
    assert repeated["canonicalObjectSha256"] == result["canonicalObjectSha256"]
    rollback = rollback_object_transaction(
        publish_root=replay_case["publish_root"], output_root=replay_case["output_root"],
        transaction_id=package["transactionId"],
    )
    assert rollback["status"] == "rolled_back"
    assert not (canonical / "manifest.json").exists()
    replayed = replay_object_transaction_package(**replay_case)
    assert replayed["status"] == "replayed"
    assert (canonical / "manifest.json").is_file()


def test_exact_package_replay_accepts_verified_empty_homepage(replay_case):
    case = _homepage_case(replay_case)
    package = read_json(case["source_package_root"] / "object_transaction_package.json")
    result = replay_object_transaction_package(**case)
    assert result["status"] == "applied"
    assert result["canonicalObjectRef"] == "entities/地点/景区/西湖/1"
    assert (case["publish_root"] / package["target"]["objectPath"] / "page.md").is_file()
    assert replay_object_transaction_package(**case)["idempotent"] is True


@pytest.mark.parametrize("drift,error", [
    ("missing_cas", "REPLAY_CAS_CLOSURE_MISSING"),
    ("null_cas", "REPLAY_CAS_CLOSURE_MISSING"),
    ("body", "object closure digest mismatch"),
    ("source", "JSON 不可读"),
    ("review", "对象未 review-approved"),
    ("mode", "casRefs"),
])
def test_empty_homepage_still_verifies_complete_package(replay_case, drift, error):
    case = _homepage_case(replay_case)
    root = case["source_package_root"]
    document = read_json(root / "object_transaction_package.json")
    if drift == "missing_cas":
        document["closure"].pop("casRefs")
    elif drift == "null_cas":
        document["closure"]["casRefs"] = None
    elif drift == "mode":
        document["publishMediaMode"] = "not_applicable"
    elif drift == "body":
        (root / "object/page.md").write_text("tampered", encoding="utf-8")
    elif drift == "source":
        (root / "object" / document["closure"]["sourceRefs"][0]).unlink()
    else:
        review_path = root / "object/content_review.json"
        review = read_json(review_path)
        review["decision"] = "rejected"
        _write_json(review_path, review)
    _write_json(root / "object_transaction_package.json", document)
    before = _tree_digest(case["publish_root"])
    with pytest.raises(ObjectTransactionError, match=error):
        replay_object_transaction_package(**case)
    assert _tree_digest(case["publish_root"]) == before


def test_exact_package_replay_rejects_existing_different_target(replay_case):
    package = read_json(replay_case["source_package_root"] / "object_transaction_package.json")
    existing = replay_case["publish_root"] / package["target"]["objectPath"]
    existing.mkdir(parents=True)
    (existing / "manifest.json").write_text('{"different":true}\n', encoding="utf-8")
    before = _tree_digest(existing)
    with pytest.raises(ObjectTransactionError, match="REPLAY_TARGET_CONFLICT"):
        replay_object_transaction_package(**replay_case)
    assert _tree_digest(existing) == before


def test_exact_package_replay_rejects_library_digest_drift_before_mutation(replay_case):
    source_package = replay_case["source_package_root"]
    package = read_json(source_package / "object_transaction_package.json")
    row = package["closure"]["casRefs"][0]
    entry = _library_entry(replay_case["media_library_root"], row["sha256"])
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_bytes(b"tampered")
    (source_package / row["sourceRef"]).unlink()
    with pytest.raises(ObjectTransactionError, match="LIBRARY_HOLDING_DRIFT"):
        replay_object_transaction_package(**replay_case)
    assert not (replay_case["publish_root"] / package["target"]["objectPath"]).exists()


@pytest.mark.parametrize("path", [None, "../outside", "/tmp/outside", "entities/incorrect/1"])
def test_exact_package_replay_rejects_unsafe_or_missing_object_path(replay_case, path):
    source_package = replay_case["source_package_root"]
    document = read_json(source_package / "object_transaction_package.json")
    if path is None:
        document["target"].pop("objectPath")
    else:
        document["target"]["objectPath"] = path
    _write_json(source_package / "object_transaction_package.json", document)
    before = _tree_digest(replay_case["publish_root"])
    with pytest.raises(ObjectTransactionError):
        replay_object_transaction_package(**replay_case)
    assert _tree_digest(replay_case["publish_root"]) == before


def test_exact_package_replay_rejects_changed_source_binding(replay_case):
    replay_object_transaction_package(**replay_case)
    (replay_case["source_package_root"] / "extra.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="REPLAY_CREATE_ONCE_CONFLICT"):
        replay_object_transaction_package(**replay_case)


@pytest.mark.parametrize("drift", ["identity", "bytes", "revision"])
def test_empty_homepage_replay_rejects_identity_bytes_or_revision_drift(replay_case, drift):
    case = _homepage_case(replay_case)
    replay_object_transaction_package(**case)
    root = case["source_package_root"]
    document = read_json(root / "object_transaction_package.json")
    if drift == "identity":
        document["target"]["objectRef"] = "地点/景区/断裂身份/1"
        _write_json(root / "object_transaction_package.json", document)
    elif drift == "bytes":
        (root / "object/page.md").write_bytes(b"# drifted homepage\n")
    else:
        review_path = root / "object/content_review.json"
        review = read_json(review_path)
        review["objectRevision"]["contentRevision"] += 1
        _write_json(review_path, review)
    with pytest.raises(ObjectTransactionError):
        replay_object_transaction_package(**case)
