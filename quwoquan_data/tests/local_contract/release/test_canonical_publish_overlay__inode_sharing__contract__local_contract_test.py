"""canonical publish 是 delta blob 的 overlay：共享 inode，且永不原地改写。

publish 树的每个文件都由不可变事务 blob 硬链接而来，因此「只新增、从不原地改写」
不是一句注释而是回滚与幂等重放的前提：一旦有人原地改写 publish 文件，同一个 inode
上的不可变事务证据会被静默篡改，而所有 digest 仍然自洽。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from content.release.canonical.application import (
    apply_object_transaction,
    rollback_object_transaction,
)
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction_audit import audit_object_transaction
from support import object_transaction_fixtures as shared_fixtures
from support.media_fixture import admit_media_body, tiny_png_bytes
from support.object_transaction_fixtures import TRANSACTION_ID

_ENTITY_REF = "地点/中国/浙江省/杭州市/西湖区/景区/真实地点/1"
_ENTITY_PATH = "entities/地点/中国/浙江省/杭州市/西湖区/景区/p0001/真实地点/1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _build_canonical(root: Path) -> Path:
    publish = shared_fixtures.build_canonical(root)
    (publish / ".git").mkdir(exist_ok=True)
    _write_json(
        publish / "repository.json",
        {
            "schema": "quwoquan_data.publish_repository.v2",
            "repositoryId": "canonical-publish-overlay-test",
            "layoutVersion": 2,
        },
    )
    return publish


def _build_package(root: Path, publish: Path) -> Path:
    """将共享输入收窄投影为现役 logical identity 与 layout-v2 package。"""
    previous_ref = shared_fixtures.OBJECT_REF
    previous_closure_digest = shared_fixtures.transaction._closure_digest
    shared_fixtures.OBJECT_REF = _ENTITY_REF
    shared_fixtures.transaction._closure_digest = lambda **_kwargs: "pending"
    try:
        package = shared_fixtures.build_package(root, publish)
    finally:
        shared_fixtures.OBJECT_REF = previous_ref
        shared_fixtures.transaction._closure_digest = previous_closure_digest

    object_root = package / "object"
    (object_root / "_entity.json").unlink()
    for retired in ("evidence", "evidence_index.json"):
        target = object_root / retired
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)

    media_body = tiny_png_bytes()
    (package / "cas/image.png").write_bytes(media_body)
    admit_media_body(media_body)
    media = object_root / "media/cover.png"
    media.parent.mkdir(parents=True)
    media.write_bytes(media_body)
    media_digest = "sha256:" + _digest(media)
    evidence = b"fixture source evidence\n"
    evidence_path = object_root / "sources/s001/evidence.txt"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_bytes(evidence)
    source_ref = "sources/s001/source.json"
    source_url = "https://zh.wikipedia.org/wiki/真实地点"
    _write_json(
        object_root / source_ref,
        {
            "schema": "quwoquan_data.publish_source",
            "sourceId": "s001",
            "sourceUrl": source_url,
            "sourceUseMode": "licensed_adaptation",
            "fetchedAt": "2026-07-11T00:00:00Z",
            "metadata": {},
            "assets": [{"assetId": "cover"}],
            "evidence": [
                {
                    "path": "evidence.txt",
                    "sha256": "sha256:" + hashlib.sha256(evidence).hexdigest(),
                    "bytes": len(evidence),
                    "kind": "source_snapshot",
                }
            ],
        },
    )

    digest_hex = media_digest.removeprefix("sha256:")
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/"
        f"{digest_hex}.png"
    )
    manifest = {
        "schema": "quwoquan_data.entity_object",
        "entityId": "entity:canonical-publish-overlay-test",
        "entityRef": "/entity/" + _ENTITY_REF,
        "version": 1,
        "label": "真实地点",
        "domain": "地点",
        "type": "景区",
        "executionId": "20260711--travel-homepage-coverage--cn-test--pilot-001",
        "geographyMode": "administrative",
        "geoTagRef": "Topic/地理/行政区/中国/浙江省/杭州市/西湖区",
        "tagRefs": [shared_fixtures.TAG_REF],
        "primarySource": {
            "sourceKind": "wikipedia",
            "entityName": "真实地点",
            "extractor": "wikipedia_api",
            "canonicalUrl": source_url,
            "sourceUrl": source_url,
            "title": "真实地点",
            "fetchedAt": "2026-07-11T00:00:00Z",
            "snapshotHash": "sha256:" + "1" * 64,
            "policyRevision": shared_fixtures.SOURCE_POLICY,
            "sourceUseMode": "licensed_adaptation",
        },
        "sourceUrls": [source_url],
        "sourceAttribution": {},
        "sourceRefs": [source_ref],
        "finalContentRef": "page.md",
        "publishMediaMode": "not_applicable",
        "creatorProfileId": shared_fixtures.CREATOR_ID,
        "assets": [
            {
                "assetId": "cover",
                "kind": "image",
                "path": "media/cover.png",
                "objectKey": object_key,
                "sha256": media_digest,
                "bytes": media.stat().st_size,
                "mimeType": "image/png",
                "sourceRefs": [source_ref],
            }
        ],
    }
    _write_json(object_root / "manifest.json", manifest)

    package_document = json.loads(
        (package / "object_transaction_package.json").read_text(encoding="utf-8")
    )
    package_document["target"].update(
        objectRef=_ENTITY_REF,
        objectPath=_ENTITY_PATH,
    )
    package_document["closure"].pop("sourceCatalogRef", None)
    package_document["closure"].pop("rightsRef", None)
    package_document["closure"]["sourceRefs"] = [source_ref]
    package_document["closure"]["casRefs"] = [
        {
            "sourceRef": "object/media/cover.png",
            "objectKey": object_key,
            "sha256": media_digest,
            "bytes": media.stat().st_size,
        }
    ]
    review = {"contentReviewRef": "content_review.json"}
    review_binding = shared_fixtures.transaction._review_binding(
        object_root, {"review": review}
    )
    package_document["semanticBinding"] = {
        key: review_binding[key]
        for key in ("protocol", "objectRevision", "dispositionsDigest")
    }
    package_document["objectClosureDigest"] = (
        shared_fixtures.transaction._closure_digest(
            object_root=object_root,
            object_kind="entities",
            object_ref=_ENTITY_REF,
            target_schema="quwoquan_data.entity_object",
            source_policy_revision=shared_fixtures.SOURCE_POLICY,
            closure=package_document["closure"],
            cas_rows=[dict(package_document["closure"]["casRefs"][0])],
            review=review_binding,
        )
    )
    _write_json(package / "object_transaction_package.json", package_document)
    return package


def _snapshot_by_hardlink(publish_root: Path, target: Path) -> dict[Path, tuple[int, str]]:
    """用硬链接给 publish 现存文件留证：原地改写会同时改掉这份快照。"""
    snapshot: dict[Path, tuple[int, str]] = {}
    for path in sorted(publish_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(publish_root)
        if relative.parts[0] == ".git":
            continue
        link = target / relative
        link.parent.mkdir(parents=True, exist_ok=True)
        link.hardlink_to(path)
        snapshot[relative] = (path.stat().st_ino, _digest(path))
    return snapshot


def _run_transaction(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    publish = _build_canonical(tmp_path)
    package = _build_package(tmp_path, publish)
    output = tmp_path / ".qwq_output"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
            "merkleRoot"
        ],
    )
    return publish, package, output, audit


def test_applied_publish_files_share_inode_with_immutable_delta_blobs(
    tmp_path: Path,
) -> None:
    publish, package, output, audit = _run_transaction(tmp_path)
    run_root = output / "data/local/workspace/object-transactions" / TRANSACTION_ID
    before = _snapshot_by_hardlink(publish, tmp_path / "before-snapshot")

    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )

    manifest = json.loads(
        (run_root / "delta/manifest.json").read_text(encoding="utf-8")
    )
    entries = manifest["entries"]
    assert entries

    # 新对象与新 CAS 全部是 blob 的硬链接，不是逐文件字节复制。
    for entry in entries:
        blob = run_root / str(entry["blobRef"])
        destination = publish / str(entry["destination"])
        assert destination.is_file()
        assert destination.stat().st_ino == blob.stat().st_ino, entry["destination"]
        assert destination.stat().st_nlink >= 2, entry["destination"]

    # 事务只新增：既有文件的 inode 与字节一个都没被动过。
    for relative, (inode, digest) in before.items():
        current = publish / relative
        assert current.is_file(), relative
        assert current.stat().st_ino == inode, relative
        assert _digest(current) == digest, relative


def test_rollback_removes_overlay_links_without_mutating_delta_evidence(
    tmp_path: Path,
) -> None:
    publish, package, output, audit = _run_transaction(tmp_path)
    run_root = output / "data/local/workspace/object-transactions" / TRANSACTION_ID
    before = _snapshot_by_hardlink(publish, tmp_path / "before-snapshot")

    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )
    blob_digests = {
        path.relative_to(run_root): _digest(path)
        for path in sorted((run_root / "delta/blobs").rglob("*"))
        if path.is_file()
    }
    assert blob_digests

    rollback_object_transaction(
        publish_root=publish,
        output_root=output,
        transaction_id=TRANSACTION_ID,
    )

    # 回滚只摘掉 overlay 链接，不改 blob 字节，也不改回滚前既有对象。
    for relative, digest in blob_digests.items():
        assert _digest(run_root / relative) == digest, relative
    for relative, (inode, digest) in before.items():
        current = publish / relative
        assert current.stat().st_ino == inode, relative
        assert _digest(current) == digest, relative
    assert load_or_bootstrap_inventory(publish)["stats"]["merkleRoot"] == str(
        audit["beforeCanonical"]["merkleRoot"]
    )
