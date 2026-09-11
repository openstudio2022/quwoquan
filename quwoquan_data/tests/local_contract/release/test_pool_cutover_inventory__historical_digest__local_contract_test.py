"""离线迁移按原协议摘要核验，不把新 records 规则套在旧 _pool 树上。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#gwt-003
import hashlib
import json

import pytest

from content.release.canonical.pool_cutover import PoolCutoverError
from content.release.canonical.pool_cutover_inventory import original_pool_payload_digest


def test_original_digest_excludes_only_historical_pool_and_media(tmp_path):
    metadata = tmp_path / "manifest.json"
    metadata.write_bytes(b'{"title":"original"}\n')
    (tmp_path / "_pool/versions").mkdir(parents=True)
    record = tmp_path / "_pool/versions/1.json"
    record.write_bytes(b'{"payloadDigest":"frozen"}')
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/body.jpg").write_bytes(b"media bytes")
    expected_rows = [{"path": "manifest.json", "sha256": "sha256:" + hashlib.sha256(metadata.read_bytes()).hexdigest(), "bytes": metadata.stat().st_size}]
    raw = (json.dumps(expected_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    expected = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert original_pool_payload_digest(tmp_path) == expected
    record.write_bytes(b'{"payloadDigest":"another"}')
    assert original_pool_payload_digest(tmp_path) == expected
    metadata.write_bytes(b'{"title":"tampered"}\n')
    assert original_pool_payload_digest(tmp_path) != expected


def test_original_digest_does_not_drop_necessary_rights_source_documents(tmp_path):
    (tmp_path / "rights_snapshots").mkdir()
    evidence = tmp_path / "rights_snapshots/1.json"
    evidence.write_bytes(b'{"creator":"original"}')
    before = original_pool_payload_digest(tmp_path)
    evidence.write_bytes(b'{"creator":"changed"}')
    assert original_pool_payload_digest(tmp_path) != before
    evidence.unlink()
    evidence.symlink_to(tmp_path / "missing.json")
    with pytest.raises(PoolCutoverError, match="SYMLINK"):
        original_pool_payload_digest(tmp_path)


def test_recovery_inventory_reads_original_record_digest_without_refresh(tmp_path):
    from content.release.canonical.pool_cutover_inventory import _recovery_row
    ref = "posts/article/导览/旧文/1"
    root = tmp_path / "pool" / ref
    (root / "_pool/versions").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"sourceIdentity": {"executionId": "original"}}))
    record = root / "_pool/versions/1.json"
    record.write_text(json.dumps({"recordSequence": 1, "payloadDigest": original_pool_payload_digest(root)}))
    before = record.read_bytes()
    row = {"objectRef": ref, "before": {}, "issues": [], "missingDependencyRefs": []}
    result = _recovery_row(row, tmp_path / "pool", tmp_path / "tasks", [], {ref: []}, {})
    assert result["recordPayloadMatches"] is True
    (root / "page.md").write_text("changed canonical bytes")
    assert _recovery_row(row, tmp_path / "pool", tmp_path / "tasks", [], {ref: []}, {})["recordPayloadMatches"] is False
    assert record.read_bytes() == before
