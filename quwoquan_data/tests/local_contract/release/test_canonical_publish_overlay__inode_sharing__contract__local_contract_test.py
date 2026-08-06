"""canonical publish 是 delta blob 的 overlay：共享 inode，且永不原地改写。

publish 树的每个文件都由不可变事务 blob 硬链接而来，因此「只新增、从不原地改写」
不是一句注释而是回滚与幂等重放的前提：一旦有人原地改写 publish 文件，同一个 inode
上的不可变事务证据会被静默篡改，而所有 digest 仍然自洽。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from content.release.canonical.application import (
    apply_object_transaction,
    rollback_object_transaction,
)
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction_audit import audit_object_transaction
from support.object_transaction_fixtures import (
    TRANSACTION_ID,
    build_canonical,
    build_package,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_by_hardlink(publish_root: Path, target: Path) -> dict[Path, tuple[int, str]]:
    """用硬链接给 publish 现存文件留证：原地改写会同时改掉这份快照。"""
    snapshot: dict[Path, tuple[int, str]] = {}
    for path in sorted(publish_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(publish_root)
        link = target / relative
        link.parent.mkdir(parents=True, exist_ok=True)
        link.hardlink_to(path)
        snapshot[relative] = (path.stat().st_ino, _digest(path))
    return snapshot


def _run_transaction(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    publish = build_canonical(tmp_path)
    package = build_package(tmp_path, publish)
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

    import json

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
