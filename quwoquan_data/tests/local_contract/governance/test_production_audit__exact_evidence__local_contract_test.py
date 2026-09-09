# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-018
"""审计仅消费 exact evidence，不把已评审、已发布和 eligible 混为一谈。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from governance.production_audit import evidence, quality_audit, write_evidence


def put(path: Path, doc: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def fixture(tmp_path):
    root = tmp_path / "execution"
    ref = "posts/article/攻略/example/1"
    review = {"executionId": root.name, "objectRef": ref, "decision": "approved",
              "qualityScores": {"readability": 4}}
    path = put(root / ref / "5.review/content_review.json", review)
    digest = evidence(path)["sha256"]
    put(root / "_shared/receipts/003-5.review.json", {
        "executionId": root.name, "stage": "5.review", "verdict": "pass",
        "resultRefs": [{"ref": path.relative_to(root).as_posix(), "digest": digest}]})
    publish = tmp_path / "publish"
    put(publish / ref / "content_review.json", review)
    put(publish / ref / "_pool/versions/1.json", {
        "sourceIdentity": {"executionId": root.name}, "evidenceDigest": digest})
    pool = put(tmp_path / "pool.json", {"counts": {"article": 0},
                                       "eligible": {"homepages": [], "posts": []}})
    return root, publish, pool, path


def test_reviewed_published_and_eligible_are_distinct(tmp_path):
    root, publish, pool, path = fixture(tmp_path)
    before = path.read_bytes()
    result = quality_audit(executions=[root], publish_root=publish, pool_snapshot=pool,
                           observations=[], preserve_files=[pool])
    assert result["counts"]["reviewed"]["article"] == 1
    assert result["counts"]["published"]["article"] == 1
    assert result["counts"]["eligible"]["article"] == 0
    assert result["sets"]["reviewed"][0]["reviewSha256"] == evidence(path)["sha256"]
    assert path.read_bytes() == before


def test_receipt_digest_drift_fails_closed(tmp_path):
    root, publish, pool, path = fixture(tmp_path)
    path.write_text("{}")
    with pytest.raises(ValueError, match="REVIEW_DIGEST_DRIFT"):
        quality_audit(executions=[root], publish_root=publish, pool_snapshot=pool,
                      observations=[], preserve_files=[])


def test_different_current_reader_is_not_historical_baseline(tmp_path):
    root, publish, pool, _ = fixture(tmp_path)
    observation = put(tmp_path / "observation.json", {"counts": {"article": 2}})
    result = quality_audit(executions=[root], publish_root=publish, pool_snapshot=pool,
                           observations=[observation], preserve_files=[])
    assert result["firstTypedBlocker"] is None
    assert result["status"] == "passed"
    assert result["observationNotes"][0]["code"] == "DATA.AUDIT.READER_OBSERVATION_DIFFERS"
    assert result["poolSnapshot"]["counts"] == {"article": 0}


def test_evidence_is_create_once(tmp_path):
    path = tmp_path / "evidence.json"
    write_evidence(path, {"result": 1})
    with pytest.raises(FileExistsError):
        write_evidence(path, {"result": 2})
    assert json.loads(path.read_text())["result"] == 1


def test_media_matching_names_do_not_prove_matching_bytes(tmp_path):
    from governance.media_protection_audit import HashBudget, inspect_holders
    from core.content_library import file_sha256, library_cas_path

    source = tmp_path / "source"
    source.write_bytes(b"canonical")
    digest = file_sha256(source)
    library, carried, backup = [tmp_path / name for name in ("library", "carried", "backup")]
    holding = library_cas_path("media", digest, library_root=library)
    holding.parent.mkdir(parents=True)
    holding.write_bytes(source.read_bytes())
    carried.mkdir()
    backup.mkdir()
    (carried / f"{digest}.bin").write_bytes(b"canonical")
    (backup / f"{digest}.bin").write_bytes(b"corrupted")
    row = inspect_holders(digest, library=library, carried=carried, backup=backup, budget=HashBudget(100))
    assert row["libraryAndCarriedVerified"]
    assert not row["backupVerified"]
    assert row["holders"]["backup"][0]["state"] == "digest_drift"


def test_hash_budget_cannot_silently_claim_backup_success(tmp_path):
    from governance.media_protection_audit import HashBudget
    source = tmp_path / "source"
    source.write_bytes(b"larger than budget")
    budget = HashBudget(1)
    assert budget.inspect(source, "0" * 64)["state"] == "budget_exhausted"
    assert budget.read_bytes == 0


def test_real_governance_parser_routes_to_read_only_audit():
    import argparse
    from governance.handler import register_parser
    from governance.production_audit import handle_quality, _handle_media

    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    quality = parser.parse_args(["governance", "production-audit", "--execution", "e",
                                "--pool-snapshot", "p", "--output", "o"])
    assert quality.handler is handle_quality
    media = parser.parse_args(["governance", "media-protection-audit", "--releases-root", "r",
        "--reference-releases-root", "ref", "--backup-root", "b", "--max-digests", "1",
        "--max-hash-bytes", "10", "--max-files", "20", "--max-metadata-bytes", "50",
        "--budget-root", "b", "--output", "o"])
    assert media.handler is _handle_media


def test_freeze_entire_tree_reuses_only_stable_hardlink_inodes(tmp_path):
    from governance.media_protection_audit import HashBudget, InputBudget, freeze_files

    root = tmp_path / "release"
    put(root / "payload/objects/deep/object.json", {"immutable": True})
    media = root / "payload/media.bin"
    media.write_bytes(b"exact old media")
    (root / "payload/linked.bin").hardlink_to(media)
    (root / "payload/copy.bin").write_bytes(media.read_bytes())
    inputs, hashes = InputBudget(30, 100), HashBudget(1000)
    paths = inputs.tree(root)
    result = freeze_files(paths, hashes)
    assert result["status"] == "passed"
    assert result["fileCount"] == 4
    assert hashes.cache_hits == 1
    assert hashes.read_bytes == result["logicalBytes"] - media.stat().st_size
    changed = next(r for r in result["files"] if r["path"].endswith("object.json"))
    assert changed["sha256"] == evidence(Path(changed["path"]))["sha256"]


def test_same_name_and_size_cannot_reuse_other_inode_hash(tmp_path):
    from governance.media_protection_audit import HashBudget

    first, second = tmp_path / "first", tmp_path / "second"
    first.write_bytes(b"good")
    second.write_bytes(b"evil")
    hashes = HashBudget(8)
    known = hashes.inspect(first)
    assert hashes.inspect(second, known["sha256"])["state"] == "digest_drift"
    assert hashes.cache_hits == 0
    first.write_bytes(b"new!")
    assert hashes.inspect(first)["state"] == "budget_exhausted"


def test_tree_budget_and_symlink_fail_closed(tmp_path):
    from governance.media_protection_audit import InputBudget

    put(tmp_path / "nested/file.json", {})
    with pytest.raises(ValueError, match="FILE_BOUND_EXCEEDED"):
        InputBudget(1, 10).tree(tmp_path)
    (tmp_path / "escape").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="UNSUPPORTED_FILE_TYPE"):
        InputBudget(10, 100).tree(tmp_path)


def test_metadata_budget_accounts_each_read_document(tmp_path):
    from governance.media_protection_audit import InputBudget

    path = put(tmp_path / "large.json", {"large": "value"})
    with pytest.raises(ValueError, match="METADATA_BOUND_EXCEEDED"):
        InputBudget(10, 1).document(path)
    budget = InputBudget(10, 100)
    budget.document(path)
    budget.document(path)
    assert budget.metadata_bytes == path.stat().st_size


def capacity(tmp_path, budgets, monkeypatch, available=100, reserve=0):
    from types import SimpleNamespace
    from governance.media_protection_audit import COMPONENTS, capacity_audit

    monkeypatch.setattr("governance.media_protection_audit.os.statvfs",
                        lambda _: SimpleNamespace(f_bavail=available, f_frsize=1))
    return capacity_audit(budgets=budgets, roots={name: tmp_path for name in COMPONENTS},
                          reserve_bytes=reserve, known={"existingBytes": 10000})


def test_capacity_same_device_sums_five_peaks_not_existing_io(tmp_path, monkeypatch):
    from governance.media_protection_audit import COMPONENTS

    result = capacity(tmp_path, dict.fromkeys(COMPONENTS, 10), monkeypatch, reserve=5)
    assert result["status"] == "passed"
    assert len(result["devices"]) == 1
    assert result["devices"][0]["declaredPeakBytes"] == 50
    assert result["devices"][0]["remainingAfterDeclaredPeakBytes"] == 45
    assert all(r["basis"] == "caller_declared_upper_bound" for r in result["components"])


def test_capacity_missing_input_cannot_be_imputed_to_zero(tmp_path, monkeypatch):
    result = capacity(tmp_path, {"original": 10}, monkeypatch)
    assert result["status"] == "blocked"
    assert result["issues"][0]["code"] == "DATA.AUDIT.PEAK_CAPACITY_INPUT_MISSING"
    assert len(result["issues"][0]["components"]) == 4


def test_capacity_insufficient_and_original_limit_are_real_blockers(tmp_path, monkeypatch):
    from governance.media_protection_audit import COMPONENTS, ORIGINAL_LIMIT

    result = capacity(tmp_path, dict.fromkeys(COMPONENTS, 21), monkeypatch)
    assert result["issues"][0]["code"] == "DATA.AUDIT.PEAK_CAPACITY_INSUFFICIENT"
    budgets = dict.fromkeys(COMPONENTS, 0)
    budgets["original"] = ORIGINAL_LIMIT + 1
    result = capacity(tmp_path, budgets, monkeypatch, available=ORIGINAL_LIMIT * 3)
    assert result["issues"][0]["code"] == "DATA.AUDIT.ORIGINAL_BUDGET_EXCEEDS_LIMIT"
    with pytest.raises(ValueError, match="CAPACITY_BUDGET_INVALID"):
        capacity(tmp_path, {"original": True}, monkeypatch)


def protection_fixture(tmp_path, monkeypatch):
    from core.content_library import file_sha256, library_cas_path
    from governance import media_protection_audit as audit

    publish, releases, reference, library, carried, backup = [
        tmp_path / name for name in ("publish", "output/data/releases", "reference", "library", "carried", "backup")]
    for root in (publish, releases, reference, library, carried, backup):
        root.mkdir(parents=True)
    raw = tmp_path / "raw"
    raw.write_bytes(b"media")
    digest = file_sha256(raw)
    holding = library_cas_path("media", digest, library_root=library)
    holding.parent.mkdir(parents=True)
    holding.write_bytes(raw.read_bytes())
    for root in (carried, backup):
        (root / f"{digest}.bin").write_bytes(raw.read_bytes())
    release = releases / "old"
    put(release / "payload/media_manifest.json", {"assets": [{"sha256": digest, "bytes": 5}]})
    put(release / "payload/objects/deep/review.json", {"sealed": "unchanged"})
    (release / "payload/media.bin").hardlink_to(holding)
    binding = put(tmp_path / "output/env/local-binding.json", {
        "releaseId": "old", "releaseRef": "data/releases/old",
        "nested": {"mediaRef": "data/releases/old/payload/media.bin", "mediaDigest": f"sha256:{digest}"}})
    monkeypatch.setattr(audit, "LIBRARY_ROOT", library)
    monkeypatch.setattr(audit, "carried_media_root", lambda: carried)
    return dict(publish_root=publish, releases_root=releases, reference_root=reference,
                backup_root=backup, bindings=[binding], max_digests=10, max_hash_bytes=10000,
                max_files=100, max_metadata_bytes=10000, budgets=dict.fromkeys(audit.COMPONENTS, 1),
                budget_root=tmp_path)


def test_full_local_protection_can_pass_without_environment_or_restore(tmp_path, monkeypatch):
    from governance.media_protection_audit import protection_audit

    kwargs = protection_fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = protection_audit(**kwargs)
    assert result["status"] == "passed"
    assert result["firstTypedBlocker"] is None
    assert result["releaseFreeze"]["fileCount"] == 3
    assert result["counts"]["backupVerified"] == 1
    assert result["counts"]["independentDeviceCopies"] == 0
    assert result["scopeLayers"]["environment"].startswith("not_authorized_not_called")
    assert result["scopeLayers"]["crossDeviceRestore"].startswith("not_executed")
    assert result["bindings"][0]["exactRefChecks"][1]["state"] == "verified"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_protection_corrupt_backup_is_still_a_real_blocker(tmp_path, monkeypatch):
    from governance.media_protection_audit import protection_audit

    kwargs = protection_fixture(tmp_path, monkeypatch)
    next(kwargs["backup_root"].iterdir()).write_bytes(b"wrong")
    result = protection_audit(**kwargs)
    assert result["status"] == "blocked"
    assert result["firstTypedBlocker"]["code"] == "DATA.AUDIT.BACKUP_DIGEST_CLOSURE_INCOMPLETE"


def test_protection_missing_release_and_nested_digest_drift(tmp_path, monkeypatch):
    from governance.media_protection_audit import protection_audit

    kwargs = protection_fixture(tmp_path, monkeypatch)
    put(kwargs["bindings"][0], {"rollbackTo": "missing", "nested": {
        "mediaRef": "data/releases/old/payload/media.bin", "mediaDigest": "sha256:" + "0" * 64}})
    result = protection_audit(**kwargs)
    assert {r["code"] for r in result["issues"]} == {
        "DATA.AUDIT.BINDING_RELEASE_MISSING", "DATA.AUDIT.BINDING_TARGET_UNPROVEN"}


def test_freeze_detects_new_file_during_hash(tmp_path, monkeypatch):
    from governance import media_protection_audit as audit

    kwargs = protection_fixture(tmp_path, monkeypatch)
    original = audit.freeze_files
    def freeze_and_mutate(files, budget):
        result = original(files, budget)
        put(kwargs["releases_root"] / "old/new.json", {})
        return result
    monkeypatch.setattr(audit, "freeze_files", freeze_and_mutate)
    result = audit.protection_audit(**kwargs)
    assert any(r["code"] == "DATA.AUDIT.INPUT_CHANGED" for r in result["issues"])
