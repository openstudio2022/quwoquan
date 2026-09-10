# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/design.md#dec-003
"""四域 exact receipt 与完整公开媒体闭包的准入验证。"""

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
releaseKind="content", mode="sync",
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


def _media_release(root: Path, bodies: list[bytes]) -> tuple[Path, dict, str]:
    import hashlib
    from core.io import write_json
    from core.release_layout import payload_digest

    release = root / "release-a"
    assets = [
        {
            "assetId": f"asset-{index}", "kind": "image", "version": 1,
            "contentType": "image/webp", "bytes": len(body),
            "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
            "publicSliceKey": f"media/image/s/asset/asset-{index}/v1/source.webp",
            "ownerRefs": ["posts/article/a"], "rightsSnapshotRefs": ["rights/a"],
        }
        for index, body in enumerate(bodies)
    ]
    manifest = {
        "schema": "quwoquan_data.release_media_manifest", "releaseId": "release-a",
        "sourceOwner": "qwq_data", "assets": assets, "issues": [],
        "counts": {"assets": len(assets), "issues": 0},
    }
    write_json(release / "payload/media_manifest.json", manifest)
    return release, manifest, payload_digest(release)


@pytest.mark.parametrize("failure", [None, "missing_last", "tail_digest", "range", "short", "type"])
def test_full_media_closure_reads_every_asset_and_every_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    from content.release.environment import owner_local_staging_admission as subject
    from content.release.environment.public_api_client import PublicBinaryResponse

    bodies = [b"first", b"middle", b"last-asset-with-tail"]
    release, manifest, digest = _media_release(tmp_path, bodies)
    frozen = (release / "payload/media_manifest.json").read_bytes()
    calls: list[tuple[int, int, int]] = []
    monkeypatch.setattr(subject, "_MEDIA_READ_CHUNK_BYTES", 4)

    def get_bytes(self, url: str, *, byte_range: str, max_bytes: int):
        index = next(i for i, row in enumerate(manifest["assets"]) if url.endswith(row["publicSliceKey"]))
        start, end = map(int, byte_range.removeprefix("bytes=").split("-"))
        calls.append((index, start, end))
        body = bodies[index][start:end + 1]
        status, content_range, content_type = 206, f"bytes {start}-{end}/{len(bodies[index])}", "image/webp"
        if index == 2 and end == len(bodies[index]) - 1:
            if failure == "missing_last":
                status = 404
            elif failure == "tail_digest":
                body = b"X" * len(body)
            elif failure == "range":
                content_range = "bytes 0-0/999"
            elif failure == "short":
                body = body[:-1]
            elif failure == "type":
                content_type = "text/html"
        assert len(body) <= max_bytes
        return PublicBinaryResponse(status, content_type, content_range, body)

    monkeypatch.setattr(subject.PublicApiClient, "get_bytes", get_bytes)
    kwargs = dict(release=release, release_id="release-a", manifest_digest=digest, media_base_url="https://media.example.invalid")
    if failure:
        with pytest.raises(subject.CandidateMediaClosureError, match="GATE_BLOCK"):
            subject.require_candidate_media_readable(**kwargs)
    else:
        subject.require_candidate_media_readable(**kwargs)
    assert {call[0] for call in calls} == {0, 1, 2}
    assert calls[-1][2] == len(bodies[-1]) - 1
    assert (release / "payload/media_manifest.json").read_bytes() == frozen


def test_empty_media_closure_requires_no_network_but_exact_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.release.environment import owner_local_staging_admission as subject

    release, _manifest, digest = _media_release(tmp_path, [])
    monkeypatch.setattr(subject, "PublicApiClient", lambda **kwargs: pytest.fail("empty closure must not access network"))
    subject.require_candidate_media_readable(
        release=release, release_id="release-a", manifest_digest=digest, media_base_url=""
    )
    with pytest.raises(subject.CandidateMediaClosureError):
        subject.require_candidate_media_readable(
            release=release, release_id="release-other", manifest_digest=digest, media_base_url=""
        )
