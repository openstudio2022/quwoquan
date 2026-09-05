# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from content.release.canonical import producer_release_handoff as handoff
from core.control_types import RECEIPT_STAGE_SEQUENCE


def _canonical(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _asset_bindings(object_ref: str) -> list[dict[str, object]]:
    carrier = "homepage" if object_ref.startswith("entities/") else object_ref.split("/", 2)[1]
    if carrier == "article":
        return []
    digest = "sha256:" + "c" * 64
    return [{
        "assetId": "cover",
        "objectKey": "media/objects/sha256/cc/cc/" + "c" * 64 + ".jpg",
        "sha256": digest,
        "sourceAssetRefs": ["sources/fixture/assets/cover.jpg"],
        "acquisitionReceiptRefs": ["receipts/fixture-image-acquisition.json"],
    }]


def _object_identity(object_ref: str) -> dict[str, object]:
    carrier = "homepage" if object_ref.startswith("entities/") else object_ref.split("/", 2)[1]
    projected_ref = object_ref.split("/", 1)[1]
    object_id = "id-" + hashlib.sha256(object_ref.encode()).hexdigest()[:12]
    return {
        "objectRef": object_ref,
        "projectedRef": projected_ref,
        "objectType": "homepage" if carrier == "homepage" else "content",
        "objectId": object_id,
        "carrier": carrier,
        "canonicalDigest": "sha256:" + hashlib.sha256(("canonical:" + object_ref).encode()).hexdigest(),
        "selectionDigest": "sha256:" + hashlib.sha256(("selection:" + object_ref).encode()).hexdigest(),
        "libraryDigest": handoff.canonical_digest(_asset_bindings(object_ref)),
    }


def _query_document(object_ref: str) -> dict[str, object]:
    fact = _object_identity(object_ref)
    identity: dict[str, object] = {
        "objectType": fact["objectType"], "objectId": fact["objectId"],
        "objectRef": fact["projectedRef"], "carrier": fact["carrier"],
        "contentVersion": 1, "recordSequence": 1,
    }
    if fact["objectType"] == "content":
        identity["authorId"] = "author-1"
    return {
        "schema": "quwoquan_data.content_pool_handoff_query",
        "projectorVersion": "content_pool_handoff_v1",
        "specRef": "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-008",
        "identity": identity,
        "lifecycle": {"status": "active"},
        "admission": {"processResult": "completed", "qualityResult": "passed", "eligibilityResult": "passed", "rightsResult": "passed", "rightsAuthorityRef": "rights-authority.json", "rightsAuthorityDigest": "sha256:" + "2" * 64, "evidenceRef": "evidence.json", "evidenceDigest": "sha256:" + "1" * 64},
        "scope": {"usageScope": "research", "variantPurpose": "not_applicable" if fact["objectType"] == "homepage" else "original"},
        "digests": {"payloadDigest": fact["canonicalDigest"], "canonicalObjectDigest": fact["canonicalDigest"], "selectionIdentityDigest": fact["selectionDigest"]},
        "refs": {"canonicalObjectRef": object_ref, "manifestRef": f"{object_ref}/manifest.json", "poolRecordRef": f"{object_ref}/_pool/versions/1.json"},
        "contentLibrary": {
            "holder": "content_library",
            "bindingDigest": fact["libraryDigest"],
            "bindings": _asset_bindings(object_ref),
            **(
                {"bindingRef": f"{object_ref}/asset.refs.json"}
                if _asset_bindings(object_ref)
                else {}
            ),
        },
    }


class Query:
    def __init__(self, object_ref: str):
        self.object_ref = object_ref

    def as_document(self) -> dict[str, object]:
        prefix = "entities/" if self.object_ref.startswith("地点/") else "posts/"
        return _query_document(prefix + self.object_ref)


def _init_git(repo: Path) -> str:
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    for rel in handoff._PRODUCER_CONTRACT_PATHS:
        path = repo / rel
        if Path(rel).suffix:
            _canonical(path, {"contract": rel})
        else:
            _canonical(path / "contract.json", {"contract": rel})
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _write_execution_chain(output: Path, execution_id: str, cohort_binding: dict[str, str], header_binding: dict[str, str]) -> Path:
    root = output / "data/tasks" / execution_id
    predecessor = None
    for sequence, stage in enumerate(RECEIPT_STAGE_SEQUENCE, start=1):
        stage_name = stage.value
        name = f"{sequence:03d}-{stage_name}.json"
        input_refs = [cohort_binding] if sequence == 9 else []
        submitted_input = {"inputRefs": [{"scope": row["scope"], "ref": row["ref"]} for row in input_refs]}
        open_doc = {
            "schema": "quwoquan_data.stage_open_request", "executionId": execution_id,
            "stage": stage_name, "sequence": sequence, "predecessor": predecessor,
            "input": {"digest": "sha256:" + hashlib.sha256((json.dumps(submitted_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()},
            "submittedInput": submitted_input,
            "inputRefs": input_refs,
        }
        open_path = _canonical(root / "_shared/stage-open" / name, open_doc)
        result = _canonical(root / stage_name / "result.json", {"stage": stage_name, "executionId": execution_id})
        result_binding = {"scope": "execution", "ref": result.relative_to(root).as_posix(), "digest": _digest(result)}
        results = [result_binding, header_binding] if sequence == 9 else [result_binding]
        close = {
            "actor": {"host": "cursor", "modelFamily": "gpt", "sessionId": f"session-{sequence}", "invocation": None},
            "verdict": "pass", "typedIssues": [],
            "resultRefs": [{"scope": row["scope"], "ref": row["ref"]} for row in results],
            "verifierFacts": [{"name": "fixture", "status": "passed", "command": "pytest fixture", "exitCode": 0, "observedAt": "2026-09-05T00:00:00Z", "evidenceRef": {"scope": "execution", "ref": result_binding["ref"]}, "evidenceDigest": result_binding["digest"]}],
        }
        close_digest = "sha256:" + hashlib.sha256((json.dumps(close, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
        receipt = {
            "schema": "quwoquan_data.stage_receipt", "executionId": execution_id,
            "stage": stage_name, "sequence": sequence, "predecessor": predecessor,
            "openRequest": {"scope": "execution", "ref": f"_shared/stage-open/{name}", "digest": _digest(open_path)},
            "closeInput": {"digest": close_digest}, "submittedClose": close,
            "actor": close["actor"], "verdict": "pass", "typedIssues": [],
            "inputRefs": input_refs, "resultRefs": results, "verifierFacts": close["verifierFacts"],
        }
        receipt_path = _canonical(root / "_shared/receipts" / name, receipt)
        predecessor = {"scope": "execution", "ref": f"_shared/receipts/{name}", "digest": _digest(receipt_path)}
    return receipt_path


@pytest.fixture
def terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"; output = tmp_path / "output"; publish = repo / "publish"; releases = output / "data/releases"
    revision = _init_git(repo)
    execution_ids = [f"2026090{index}--travel-{carrier}-handoff--china--pilot-001" for index, carrier in enumerate(("homepage", "article", "image", "video"), start=1)]
    release_id = "m1-release-001"
    cohort = {
        "schema": "quwoquan_data.release_cohort", "releaseClass": "research", "milestone": "M1",
        "producerBaselineRevision": revision,
        "objectRefs": ["entities/地点/景区/西湖", "posts/article/攻略/西湖/1", "posts/image/画报/西湖/1", "posts/video/体验/西湖/1"],
        "expectedCarrierCounts": {"homepage": 1, "article": 1, "image": 1, "video": 1},
    }
    cohort_path = _canonical(output / "inputs/cohort.json", cohort)
    cohort_binding = {"scope": "output", "ref": "inputs/cohort.json", "digest": _digest(cohort_path)}
    release_dir = releases / release_id
    contents = []
    for object_ref in cohort["objectRefs"]:
        fact = _object_identity(object_ref)
        if fact["objectType"] == "content":
            contents.append({
                "contentId": fact["objectId"], "version": 1,
                "postRef": fact["projectedRef"],
                "selectionIdentityDigest": fact["selectionDigest"],
                "canonicalObjectDigest": fact["canonicalDigest"],
                "contentLibraryBindingDigest": fact["libraryDigest"],
            })
    header = {
        "schema": "quwoquan_data.release", "releaseId": release_id, "executionIds": execution_ids,
        "releaseClass": "research", "productLifecycleState": "research",
        "milestone": "M1", "milestoneTargets": dict(cohort["expectedCarrierCounts"]),
        "counts": {**cohort["expectedCarrierCounts"], "total": 4}, "canonicalMerkle": "sha256:" + "a" * 64,
        "contents": contents,
    }
    header_path = _canonical(release_dir / "payload/release.json", header)
    header_binding = {"scope": "output", "ref": f"data/releases/{release_id}/payload/release.json", "digest": _digest(header_path)}
    desired = {"schema": "quwoquan_data.release_desired_state", "releaseId": release_id, "desiredRefs": {"creators": [], "entities": ["地点/景区/西湖"], "posts": ["article/攻略/西湖/1", "image/画报/西湖/1", "video/体验/西湖/1"], "tags": []}}
    _canonical(release_dir / "payload/desired_state.json", desired)
    _canonical(release_dir / "payload/index/objects.json", {"schema": "quwoquan_data.release_object_index", **desired["desiredRefs"]})
    _canonical(release_dir / "payload/sample_bundle.json", {"schema": "quwoquan_data.release_sample_bundle", **desired["desiredRefs"]})
    for object_ref in cohort["objectRefs"]:
        fact = _object_identity(object_ref)
        manifest_id = "entityId" if fact["objectType"] == "homepage" else "contentId"
        sealed_object = release_dir / "payload/objects" / object_ref
        content_review = {
            "schema": "quwoquan_data.content_review",
            "stage": "5.review",
            "executionId": execution_ids[cohort["objectRefs"].index(object_ref)],
            "objectRef": object_ref,
            "decision": "approved",
            "draft": {
                "ref": (
                    "4.draft/page.md"
                    if fact["objectType"] == "homepage"
                    else {
                        "article": "4.draft/draft.article.md",
                        "image": "4.draft/image_work.json",
                        "video": "4.draft/video_script.json",
                    }[fact["carrier"]]
                ),
                "digest": "sha256:" + "d" * 64,
            },
            "dimensions": [
                {"name": "content-quality", "decision": "approved", "issues": []}
            ],
            "blockingIssues": [],
            "assetRights": [],
        }
        manifest = {
            manifest_id: fact["objectId"], "version": 1,
            "executionId": content_review["executionId"], "assets": [],
            "admission": {"usageScope": "research"},
        }
        if fact["objectType"] == "content":
            manifest.update(contentType=fact["carrier"], variantPurpose="original")
            if fact["carrier"] == "article":
                manifest["publishMediaMode"] = "text_only"
        else:
            manifest.update(entityRef=f"/entity/{fact['projectedRef']}")
        if fact["carrier"] != "article":
            manifest["assetRefsRef"] = "asset.refs.json"
            manifest["assets"] = [{
                "assetId": "cover", "sourceAssetRef": "sources/fixture/assets/cover.jpg"
            }]
            _canonical(
                sealed_object / "asset.refs.json",
                {"assets": _asset_bindings(object_ref)},
            )
            content_review["assetRights"] = [{
                "assetRef": "sources/fixture/assets/cover.jpg", "sourceUrl": "https://example.test/cover.jpg",
                "license": "CC BY 4.0", "termsUrl": "https://example.test/terms",
                "authorizationProof": "https://example.test/proof", "usageScope": "research",
                "decision": "approved", "issues": [],
            }]
            _canonical(
                sealed_object / "rights_snapshots/cover.json",
                {
                    "schema": "quwoquan_data.asset_rights_snapshot",
                    "executionId": content_review["executionId"],
                    "assetId": "cover",
                    "manifestAsset": manifest["assets"][0],
                    "sourceAsset": {
                        "sourceUrl": "https://example.test/cover.jpg",
                        "license": "CC BY 4.0",
                        "termsUrl": "https://example.test/terms",
                        "authorizationProof": "https://example.test/proof",
                    },
                },
            )
        review_path = _canonical(sealed_object / "content_review.json", content_review)
        review_digest = _digest(review_path)
        manifest["admission"].update(
            rightsResult="passed",
            rightsAuthorityRef=f"{object_ref}/content_review.json",
            rightsAuthorityDigest=review_digest,
            evidenceRef="content_review.json",
            evidenceDigest=review_digest,
        )
        _canonical(sealed_object / "manifest.json", manifest)
        _canonical(
            sealed_object / "_pool/versions/1.json",
            {
                "objectType": fact["objectType"], "objectId": fact["objectId"],
                "objectRef": fact["projectedRef"], "recordSequence": 1,
                "contentVersion": 1, "payloadDigest": fact["canonicalDigest"],
                "canonicalObjectDigest": fact["canonicalDigest"], "usageScope": "research",
                "rightsResult": "passed", "rightsAuthorityRef": f"{object_ref}/content_review.json",
                "rightsAuthorityDigest": review_digest, "evidenceRef": "content_review.json",
                "evidenceDigest": review_digest,
            },
        )
    for execution_id in execution_ids:
        _write_execution_chain(output, execution_id, cohort_binding, header_binding)
    monkeypatch.setattr(handoff, "validate_release_header", lambda value, **_kwargs: value)
    real_assert_valid = handoff.assert_valid
    monkeypatch.setattr(
        handoff,
        "assert_valid",
        lambda value, namespace, name, **kwargs: (
            value
            if namespace == "release" and name == "release_header"
            else real_assert_valid(value, namespace, name, **kwargs)
        ),
    )
    monkeypatch.setattr(handoff, "objects_merkle", lambda _root: header["canonicalMerkle"])
    monkeypatch.setattr(handoff, "verify_release_holdings", lambda _root: ())
    monkeypatch.setattr(handoff, "payload_digest", lambda _root: "sha256:" + "5" * 64)
    projector_calls: list[Path] = []
    def live_projector(*, publish_root: Path, object_ref: str, **_kwargs):
        projector_calls.append(publish_root)
        assert publish_root == publish
        query = Query(object_ref)
        document = query.as_document()
        sealed_ref = ("entities/" if object_ref.startswith("地点/") else "posts/") + object_ref
        sealed_object = release_dir / "payload/objects" / sealed_ref
        record = json.loads((sealed_object / "_pool/versions/1.json").read_text())
        document["admission"].update({key: record[key] for key in (
            "rightsResult", "rightsAuthorityRef", "rightsAuthorityDigest", "evidenceRef", "evidenceDigest"
        )})
        class FrozenQuery:
            def as_document(self):
                return document
        return FrozenQuery()
    monkeypatch.setattr(handoff, "project_content_pool_handoff", live_projector)
    return repo, output, publish, releases, revision, release_id, cohort_path, execution_ids, projector_calls


def _write_handoff(fixture):
    repo, output, publish, releases, revision, release_id, cohort, _execution_ids, _calls = fixture
    return handoff.write_producer_release_handoff(release_id=release_id, cohort_file=cohort, milestone="M1", producer_baseline_revision=revision, repo_root=repo, output_root=output, publish_root=publish, release_root=releases)


def test_terminal_handoff_binds_four_complete_chains_embeds_queries_and_replays(terminal) -> None:
    document, path, replayed = _write_handoff(terminal)
    assert replayed is False
    assert document["executionIds"] == terminal[-2]
    assert [row["executionId"] for row in document["producerReleaseReceipts"]] == terminal[-2]
    assert terminal[-1] == [terminal[2]] * 4
    assert all(row["queryDigest"] == handoff.canonical_digest(row["queryDocument"]) for row in document["contentPoolObjects"])
    terminal[-1].clear()
    same, same_path, replayed = _write_handoff(terminal)
    assert replayed is True and same == document and same_path == path
    assert terminal[-1] == []
    assert handoff.read_producer_release_handoff(path, repo_root=terminal[0], output_root=terminal[1], release_root=terminal[3]) == document


def test_writer_accepts_matching_header_and_cohort_release_class(terminal) -> None:
    document, _path, replayed = _write_handoff(terminal)
    assert replayed is False
    assert document["explicitCohort"]["document"]["releaseClass"] == "research"
    header = json.loads(
        (terminal[3] / terminal[5] / "payload/release.json").read_text(
            encoding="utf-8"
        )
    )
    assert header["releaseClass"] == header["productLifecycleState"] == "research"


def test_writer_rejects_header_release_class_drift(terminal) -> None:
    header_path = terminal[3] / terminal[5] / "payload/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.update(releaseClass="commercial", productLifecycleState="commercial")
    _canonical(header_path, header)

    with pytest.raises(
        handoff.ProducerReleaseHandoffError,
        match="HANDOFF_RELEASE_CLASS_DRIFT",
    ):
        _write_handoff(terminal)


@pytest.mark.parametrize(
    ("updates", "error_code"),
    [
        (
            {"releaseClass": "commercial", "productLifecycleState": "commercial"},
            "HANDOFF_RELEASE_CLASS_DRIFT",
        ),
        (
            {"productLifecycleState": "commercial"},
            "HANDOFF_RELEASE_LIFECYCLE_DRIFT",
        ),
    ],
)
def test_reader_rejects_header_release_class_or_lifecycle_drift(
    terminal, updates: dict[str, str], error_code: str
) -> None:
    document, _path, _ = _write_handoff(terminal)
    header_path = terminal[3] / terminal[5] / "payload/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.update(updates)
    _canonical(header_path, header)

    with pytest.raises(handoff.ProducerReleaseHandoffError, match=error_code):
        handoff.validate_producer_release_handoff(
            document,
            repo_root=terminal[0],
            output_root=terminal[1],
            release_root=terminal[3],
        )


def test_terminal_handoff_rejects_cohort_missing_from_release_open(terminal) -> None:
    execution_id = terminal[-2][0]
    open_path = terminal[1] / f"data/tasks/{execution_id}/_shared/stage-open/009-release.json"
    opened = json.loads(open_path.read_text())
    opened["inputRefs"] = []
    _canonical(open_path, opened)
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="COHORT_OPEN_UNBOUND|EXECUTION_CHAIN_INVALID|DIGEST_DRIFT"):
        _write_handoff(terminal)


def test_terminal_handoff_rejects_receipt_result_drift(terminal) -> None:
    execution_id = terminal[-2][1]
    receipt = terminal[1] / f"data/tasks/{execution_id}/_shared/receipts/009-release.json"
    value = json.loads(receipt.read_text())
    value["resultRefs"][-1]["digest"] = "sha256:" + "0" * 64
    _canonical(receipt, value)
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="DIGEST_DRIFT"):
        _write_handoff(terminal)


def test_reader_does_not_depend_on_live_publish_git_or_policy(
    terminal, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, path, _ = _write_handoff(terminal)
    monkeypatch.setattr(
        handoff,
        "project_content_pool_handoff",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("reader called live projector")),
    )
    monkeypatch.setattr(
        handoff,
        "_git",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("reader called git")),
    )
    monkeypatch.setattr(
        handoff,
        "load_content_distribution_policy",
        lambda: (_ for _ in ()).throw(AssertionError("reader called current policy")),
    )
    shutil.rmtree(terminal[1] / "data/tasks")
    terminal[6].unlink()
    shutil.rmtree(terminal[2], ignore_errors=True)
    shutil.rmtree(terminal[0] / ".git")
    assert handoff.read_producer_release_handoff(
        path,
        repo_root=terminal[0],
        output_root=terminal[1],
        release_root=terminal[3],
    ) == document


def test_reader_rejects_embedded_cohort_digest_tamper(terminal) -> None:
    document, _path, _ = _write_handoff(terminal)
    drift = json.loads(json.dumps(document))
    drift["explicitCohort"]["document"]["expectedCarrierCounts"]["article"] = 2
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="DIGEST_DRIFT"):
        handoff.validate_producer_release_handoff(
            drift, repo_root=terminal[0], output_root=terminal[1], release_root=terminal[3]
        )


def test_reader_rejects_embedded_query_and_header_identity_drift(terminal) -> None:
    document, _path, _ = _write_handoff(terminal)
    query_drift = json.loads(json.dumps(document))
    query_drift["contentPoolObjects"][1]["queryDocument"]["refs"]["canonicalObjectRef"] = "posts/article/other"
    query_drift["contentPoolObjects"][1]["queryDigest"] = handoff.canonical_digest(
        query_drift["contentPoolObjects"][1]["queryDocument"]
    )
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="POOL_IDENTITY_DRIFT"):
        handoff.validate_producer_release_handoff(
            query_drift, repo_root=terminal[0], output_root=terminal[1], release_root=terminal[3]
        )

    header_identity_drift = json.loads(json.dumps(document))
    header_identity_drift["contentPoolObjects"][1]["queryDocument"]["digests"]["selectionIdentityDigest"] = "sha256:" + "0" * 64
    header_identity_drift["contentPoolObjects"][1]["queryDigest"] = handoff.canonical_digest(
        header_identity_drift["contentPoolObjects"][1]["queryDocument"]
    )
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="POOL_IDENTITY_DRIFT"):
        handoff.validate_producer_release_handoff(
            header_identity_drift, repo_root=terminal[0], output_root=terminal[1], release_root=terminal[3]
        )


@pytest.mark.parametrize(
    "section",
    ("openRequests", "receipts", "frozenReferences"),
)
def test_reader_rejects_embedded_receipt_chain_tamper(terminal, section: str) -> None:
    document, _path, _ = _write_handoff(terminal)
    drift = json.loads(json.dumps(document))
    chain = drift["receiptChains"][0]
    if section == "openRequests":
        chain[section][0]["input"]["digest"] = "sha256:" + "0" * 64
    elif section == "receipts":
        chain[section][0]["closeInput"]["digest"] = "sha256:" + "0" * 64
    else:
        drift["frozenReferences"][0]["contentBase64"] = "dGFtcGVyZWQ="
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="EXECUTION_CHAIN_INVALID"):
        handoff.validate_producer_release_handoff(
            drift, repo_root=terminal[0], output_root=terminal[1], release_root=terminal[3]
        )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("admission", "rightsAuthorityDigest", "sha256:" + "0" * 64),
        ("admission", "evidenceDigest", "sha256:" + "0" * 64),
        ("scope", "usageScope", "commercial"),
    ],
)
def test_reader_rejects_sealed_query_rights_and_scope_drift(
    terminal, section: str, field: str, value: str
) -> None:
    document, _path, _ = _write_handoff(terminal)
    drift = json.loads(json.dumps(document))
    drift["contentPoolObjects"][0]["queryDocument"][section][field] = value
    drift["contentPoolObjects"][0]["queryDigest"] = handoff.canonical_digest(
        drift["contentPoolObjects"][0]["queryDocument"]
    )
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="POOL_(RIGHTS|IDENTITY)_DRIFT"):
        handoff.validate_producer_release_handoff(
            drift,
            repo_root=terminal[0],
            output_root=terminal[1],
            release_root=terminal[3],
        )


def test_writer_rejects_noncommercial_scope_for_commercial_cohort(terminal) -> None:
    cohort = json.loads(terminal[6].read_text(encoding="utf-8"))
    cohort["releaseClass"] = "commercial"
    cohort_path = _canonical(terminal[1] / "inputs/commercial-cohort.json", cohort)
    header_path = terminal[3] / terminal[5] / "payload/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.update(releaseClass="commercial", productLifecycleState="commercial")
    _canonical(header_path, header)
    old_cohort = terminal[6]
    old_binding = {
        "scope": "output", "ref": "inputs/cohort.json", "digest": _digest(old_cohort)
    }
    new_binding = {
        "scope": "output", "ref": "inputs/commercial-cohort.json", "digest": _digest(cohort_path)
    }
    for execution_id in terminal[-2]:
        open_path = terminal[1] / f"data/tasks/{execution_id}/_shared/stage-open/009-release.json"
        opened = json.loads(open_path.read_text(encoding="utf-8"))
        opened["inputRefs"] = [new_binding if row == old_binding else row for row in opened["inputRefs"]]
        opened["submittedInput"]["inputRefs"] = [
            {"scope": row["scope"], "ref": row["ref"]} for row in opened["inputRefs"]
        ]
        opened["input"]["digest"] = handoff._digest(handoff._canonical_bytes(opened["submittedInput"]))
        _canonical(open_path, opened)
        receipt_path = terminal[1] / f"data/tasks/{execution_id}/_shared/receipts/009-release.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["openRequest"]["digest"] = _digest(open_path)
        receipt["inputRefs"] = list(opened["inputRefs"])
        for result_ref in receipt["resultRefs"]:
            if result_ref["ref"] == f"data/releases/{terminal[5]}/payload/release.json":
                result_ref["digest"] = _digest(header_path)
        _canonical(receipt_path, receipt)
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="COMMERCIAL_SCOPE_INVALID"):
        handoff.write_producer_release_handoff(
            release_id=terminal[5], cohort_file=cohort_path, milestone="M1",
            producer_baseline_revision=terminal[4], repo_root=terminal[0],
            output_root=terminal[1], publish_root=terminal[2], release_root=terminal[3],
        )


def test_reader_rejects_sealed_asset_binding_drift(terminal) -> None:
    document, _path, _ = _write_handoff(terminal)
    drift = json.loads(json.dumps(document))
    row = next(
        item for item in drift["contentPoolObjects"] if item["carrier"] == "image"
    )
    row["queryDocument"]["contentLibrary"]["bindings"][0]["sourceAssetRefs"] = [
        "sources/tampered/assets/cover.jpg"
    ]
    row["queryDigest"] = handoff.canonical_digest(row["queryDocument"])
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="POOL_BINDING_DRIFT"):
        handoff.validate_producer_release_handoff(
            drift,
            repo_root=terminal[0],
            output_root=terminal[1],
            release_root=terminal[3],
        )


def test_commercial_handoff_rejects_noncommercial_query_scope(terminal) -> None:
    document, _path, _ = _write_handoff(terminal)
    row = document["contentPoolObjects"][0]
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="COMMERCIAL_SCOPE_INVALID"):
        handoff._validate_query_against_sealed(
            row=row,
            object_ref=row["objectRef"],
            sealed_root=terminal[3] / terminal[5] / "payload/objects",
            header=json.loads(
                (terminal[3] / terminal[5] / "payload/release.json").read_text(
                    encoding="utf-8"
                )
            ),
            release_class="commercial",
        )


def test_reader_rejects_canonical_content_review_tamper(terminal) -> None:
    document, _path, _ = _write_handoff(terminal)
    review_path = (
        terminal[3]
        / terminal[5]
        / "payload/objects/entities/地点/景区/西湖/content_review.json"
    )
    tampered = json.loads(review_path.read_text(encoding="utf-8"))
    tampered["assetRights"][0]["sourceUrl"] = "https://example.test/tampered.jpg"
    _canonical(review_path, tampered)
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="POOL_RIGHTS_DRIFT"):
        handoff.validate_producer_release_handoff(
            document,
            repo_root=terminal[0],
            output_root=terminal[1],
            release_root=terminal[3],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evidenceRef", "other_review.json"),
        ("evidenceDigest", "sha256:" + "0" * 64),
        ("rightsAuthorityRef", "entities/地点/景区/西湖/other_review.json"),
        ("rightsAuthorityDigest", "sha256:" + "0" * 64),
    ),
)
def test_reader_rejects_content_review_ref_digest_drift(
    terminal, field: str, value: str
) -> None:
    document, _path, _ = _write_handoff(terminal)
    drift = json.loads(json.dumps(document))
    row = drift["contentPoolObjects"][0]
    row["queryDocument"]["admission"][field] = value
    row["queryDigest"] = handoff.canonical_digest(row["queryDocument"])
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="POOL_RIGHTS_DRIFT"):
        handoff.validate_producer_release_handoff(
            drift,
            repo_root=terminal[0],
            output_root=terminal[1],
            release_root=terminal[3],
        )


def test_reader_rejects_content_review_source_hard_fact_drift(terminal) -> None:
    document, _path, _ = _write_handoff(terminal)
    review_path = (
        terminal[3]
        / terminal[5]
        / "payload/objects/entities/地点/景区/西湖/content_review.json"
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["assetRights"][0]["license"] = "CC BY-SA 4.0"
    _canonical(review_path, review)
    review_digest = _digest(review_path)
    object_root = review_path.parent
    manifest_path = object_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["admission"]["rightsAuthorityDigest"] = review_digest
    manifest["admission"]["evidenceDigest"] = review_digest
    _canonical(manifest_path, manifest)
    pool_path = object_root / "_pool/versions/1.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    pool["rightsAuthorityDigest"] = review_digest
    pool["evidenceDigest"] = review_digest
    _canonical(pool_path, pool)
    row = document["contentPoolObjects"][0]
    row["queryDocument"]["admission"]["rightsAuthorityDigest"] = review_digest
    row["queryDocument"]["admission"]["evidenceDigest"] = review_digest
    row["queryDigest"] = handoff.canonical_digest(row["queryDocument"])

    with pytest.raises(
        handoff.ProducerReleaseHandoffError,
        match="content_review source rights facts drift",
    ):
        handoff.validate_producer_release_handoff(
            document,
            repo_root=terminal[0],
            output_root=terminal[1],
            release_root=terminal[3],
        )


def test_sealed_release_rejects_unsafe_ref_and_parent_symlink(terminal, tmp_path: Path) -> None:
    release_dir = terminal[3] / terminal[5]
    desired = {
        "schema": "quwoquan_data.release_desired_state", "releaseId": terminal[5],
        "desiredRefs": {"creators": ["../escape"], "entities": [], "posts": [], "tags": []},
    }
    with pytest.raises(handoff.ObjectTransactionError, match="SEALED_REF_INVALID"):
        handoff.validate_sealed_release_structure(release_dir=release_dir, desired=desired)

    outside = tmp_path / "outside"
    outside.mkdir()
    index_path = release_dir / "payload/index/objects.json"
    index_path.unlink()
    index_path.parent.rmdir()
    index_path.parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(handoff.ObjectTransactionError, match="SEALED_ARTIFACT_SYMLINK"):
        handoff.validate_sealed_release_structure(
            release_dir=release_dir,
            desired=json.loads((release_dir / "payload/desired_state.json").read_text()),
        )


def test_historical_reader_and_exact_replay_ignore_future_contract_revision(terminal) -> None:
    document, path, _ = _write_handoff(terminal)
    terminal[-1].clear()
    contract = terminal[0] / handoff._PRODUCER_CONTRACT_PATHS[0]
    _canonical(contract, {"contract": "next-revision"})
    subprocess.run(["git", "add", str(contract.relative_to(terminal[0]))], cwd=terminal[0], check=True)
    subprocess.run(["git", "commit", "-qm", "next contract"], cwd=terminal[0], check=True)

    assert handoff.read_producer_release_handoff(
        path, repo_root=terminal[0], output_root=terminal[1], release_root=terminal[3]
    ) == document
    same, same_path, replayed = _write_handoff(terminal)
    assert replayed is True and same == document and same_path == path
    assert terminal[-1] == []


def test_new_handoff_rejects_current_contract_baseline_drift(terminal) -> None:
    contract = terminal[0] / handoff._PRODUCER_CONTRACT_PATHS[0]
    _canonical(contract, {"contract": "drift"})
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="BASELINE_DRIFT"):
        _write_handoff(terminal)


def test_new_handoff_rejects_producer_release_schema_drift(terminal) -> None:
    schema = terminal[0] / (
        "quwoquan_data/schema/release/producer_release_handoff.schema.json"
    )
    _canonical(schema, {"contract": "producer schema drift"})

    with pytest.raises(handoff.ProducerReleaseHandoffError, match="BASELINE_DRIFT"):
        _write_handoff(terminal)


def test_producer_baseline_paths_exclude_consumer_and_broad_script_roots() -> None:
    paths = set(handoff._PRODUCER_CONTRACT_PATHS)

    assert "quwoquan_data/scripts/core" not in paths
    assert all((Path(__file__).resolve().parents[4] / item).is_file() for item in paths)
    assert "quwoquan_data/scripts/verify" not in paths
    assert not any("/release/environment" in item for item in paths)
    assert not any("import_report" in item for item in paths)
    assert not any("uat" in item.lower() for item in paths)
    assert not any("recommendation-service" in item for item in paths)
    assert not any(item.endswith("/ui_config.yaml") for item in paths)
    assert (
        "quwoquan_service/services/content-service/contracts/media/media_asset/"
        "image_variant_policy.yaml"
    ) in paths


def test_producer_handoff_schema_has_no_consumer_fields() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schema/release/producer_release_handoff.schema.json"
    )
    serialized = schema_path.read_text(encoding="utf-8")

    for forbidden in (
        "targetEnvironment",
        "samplePlan",
        "samplingAuthority",
        "importReport",
        "activation",
        "readback",
        "appUat",
        "eaf",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "consumer_schema",
    [
        "quwoquan_data/schema/release/import_report.schema.json",
        "quwoquan_data/schema/release/environment_release_result.schema.json",
    ],
)
def test_new_handoff_ignores_environment_consumer_schema_drift(
    terminal, consumer_schema: str
) -> None:
    schema = terminal[0] / consumer_schema
    _canonical(schema, {"contract": "consumer schema drift"})

    document, path, replayed = _write_handoff(terminal)

    assert replayed is False
    assert document["schema"] == "quwoquan_data.producer_release_handoff"
    assert path.is_file()


def test_new_handoff_ignores_environment_consumer_implementation_drift(terminal) -> None:
    implementation = terminal[0] / (
        "quwoquan_data/scripts/content/release/environment/consumer.py"
    )
    implementation.parent.mkdir(parents=True, exist_ok=True)
    implementation.write_text("CONSUMER = 'changed'\n", encoding="utf-8")

    document, path, replayed = _write_handoff(terminal)

    assert replayed is False
    assert document["schema"] == "quwoquan_data.producer_release_handoff"
    assert path.is_file()


def test_terminal_handoff_rejects_create_once_conflict(terminal) -> None:
    _document, path, _ = _write_handoff(terminal)
    path.write_text("{}\n")
    with pytest.raises(handoff.ProducerReleaseHandoffError, match="CREATE_ONCE_CONFLICT"):
        _write_handoff(terminal)
