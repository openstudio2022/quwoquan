"""Four-owner candidate receipts are the only prepared admission proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.environment.importers import OwnerReleaseEvidence, file_byte_digest
from content.release.environment.owner_local_staging_admission import (
    require_owner_local_staging_admission,
)

DIGEST = "sha256:" + "a" * 64


def _document(owner: str) -> dict[str, object]:
    common: dict[str, object] = {
        "schema": f"quwoquan.{owner}_release_candidate_receipt",
        "status": "found",
        "environment": "alpha",
        "sourceOwner": "qwq_data",
        "releaseId": "release-a",
        "manifestDigest": DIGEST,
        "projectionVersion": 1,
        "verifiedAt": "2026-09-06T00:00:00Z",
        "closureDigest": DIGEST,
        "generatedAt": "2026-09-06T00:00:01Z",
    }
    if owner == "content":
        common.pop("closureDigest")
        common.update(
            releaseClass="production", releaseKind="content", mode="sync",
            deletePolicy="tombstone",
            closureDigests={"posts": DIGEST, "facts": DIGEST, "media": DIGEST},
            counts={
                "postsExpected": 1, "postsProjected": 1,
                "outboxExpected": 1, "outboxProjected": 1,
                "mediaExpected": 0, "mediaProjected": 0,
            },
        )
    elif owner == "tag":
        common.update(
            counts={"expected": 1, "projected": 1},
            canonicalDigest=DIGEST, releaseKind="content", tagRefsDigest=DIGEST,
        )
    elif owner == "creator":
        common.update(
            counts={"expected": 1, "projected": 1},
            authorIds=["author-a"],
            profileDigests=[{"creatorId": "creator-a", "authorId": "author-a", "digest": DIGEST}],
        )
    else:
        identity = {name: common.pop(name) for name in ("environment", "sourceOwner", "releaseId", "manifestDigest")}
        common.pop("generatedAt")
        common.update(identity=identity, counts={"expected": 1, "projected": 1}, entityRefMappingDigest=DIGEST)
    return common


def _evidence(root: Path) -> dict[str, OwnerReleaseEvidence]:
    result = {}
    for owner in ("tag", "creator", "homepage", "content"):
        path = root / f"{owner}.json"
        document = _document(owner)
        path.write_text(json.dumps(document) + "\n", encoding="utf-8")
        result[owner] = OwnerReleaseEvidence(document, path, path.name, file_byte_digest(path))
    return result


def _admit(root: Path, evidence: dict[str, OwnerReleaseEvidence]):
    return require_owner_local_staging_admission(
        evidence=evidence, output_root=root, environment="alpha",
        release_id="release-a", manifest_digest=DIGEST,
    )


def test_import_report_cannot_replace_candidate_proof(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    evidence.pop("tag")
    report = tmp_path / "tag-import.json"
    report.write_text('{"schema":"quwoquan.tag_import_report"}\n')
    evidence["tag"] = OwnerReleaseEvidence({}, report, report.name, file_byte_digest(report))
    with pytest.raises(RuntimeError, match="schema"):
        _admit(tmp_path, evidence)


@pytest.mark.parametrize("failure", ["missing", "wrong_tuple", "not_found", "digest_drift", "count"])
def test_four_owner_admission_fails_closed(tmp_path: Path, failure: str) -> None:
    evidence = _evidence(tmp_path)
    if failure == "missing":
        evidence.pop("homepage")
    elif failure == "digest_drift":
        evidence["tag"].path.write_text(evidence["tag"].path.read_text() + " ")
    else:
        owner = "creator"
        document = dict(evidence[owner].document)
        if failure == "wrong_tuple":
            document["releaseId"] = "release-b"
        elif failure == "not_found":
            document = {
                "schema": "quwoquan.creator_release_candidate_receipt", "status": "not_found",
                "environment": "alpha", "sourceOwner": "qwq_data", "releaseId": "release-a",
                "manifestDigest": DIGEST, "generatedAt": "2026-09-06T00:00:01Z",
            }
        else:
            document["counts"] = {"expected": 1, "projected": 0}
        path = evidence[owner].path
        path.write_text(json.dumps(document) + "\n")
        evidence[owner] = OwnerReleaseEvidence(document, path, path.name, file_byte_digest(path))
    with pytest.raises(RuntimeError):
        _admit(tmp_path, evidence)


def test_candidate_symlink_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    original = evidence["tag"].path
    link = tmp_path / "tag-link.json"
    link.symlink_to(original)
    evidence["tag"] = OwnerReleaseEvidence(evidence["tag"].document, link, link.name, evidence["tag"].digest)
    with pytest.raises(RuntimeError, match="symlink"):
        _admit(tmp_path, evidence)


def test_four_exact_receipts_return_structured_refs(tmp_path: Path) -> None:
    proof = _admit(tmp_path, _evidence(tmp_path))
    fields = proof.result_fields()
    assert len(fields) == 8
    assert fields["contentCandidateReceiptDigest"].startswith("sha256:")
