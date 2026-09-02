from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

import pytest

from quwoquan_ops.cli.lib.evidence_fingerprint import (
    EvidenceFingerprintError,
    canonical_json_bytes,
    validate_evidence_fingerprint,
)
from quwoquan_ops.cli.lib.feature_context_fingerprint import (
    build_feature_context_fingerprint,
    referenced_fingerprint_binding,
    resolve_fingerprint_binding,
)

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/review_dispatch.py"


def _load_review_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_review_dispatch_security", CLI
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


review_cli = _load_review_cli()


def _owner_manifest_ref(raw: bytes) -> str:
    prefix = ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/"
    return prefix + hashlib.sha256(raw).hexdigest() + ".json"


def _referenced_receipt_fixture() -> tuple[dict[str, object], str, bytes]:
    receipt = validate_evidence_fingerprint(
        build_feature_context_fingerprint(
            {
                "schema_version": 3,
                "target": "README.md",
                "resolved_owner": "specs/feature-tree/spec.md",
                "owner_chain": [],
                "canonical_contexts": [],
                "applicable_agents": ["AGENTS.md"],
                "open_items": [],
            },
            repo_root=ROOT,
        )
    )
    raw = canonical_json_bytes(receipt)
    ref = (
        ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/receipts/"
        + hashlib.sha256(raw).hexdigest()
        + ".json"
    )
    return referenced_fingerprint_binding(receipt, receipt_ref=ref), ref, raw


def test_referenced_receipt_reader_rejects_ancestor_and_final_symlinks(
    tmp_path: Path,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    binding, ref, raw = _referenced_receipt_fixture()
    parts = Path(ref).parts
    for symlink_index in (0, len(parts) - 2):
        root = tmp_path / f"repo-{symlink_index}"
        outside = tmp_path / f"outside-{symlink_index}"
        outside.mkdir()
        parent = root.joinpath(*parts[:symlink_index])
        parent.mkdir(parents=True)
        target = outside / parts[symlink_index]
        target.joinpath(*parts[symlink_index + 1 : -1]).mkdir(parents=True)
        target.joinpath(*parts[symlink_index + 1 :]).write_bytes(raw)
        (parent / parts[symlink_index]).symlink_to(
            target, target_is_directory=True
        )
        with pytest.raises(EvidenceFingerprintError, match="无法读取"):
            resolve_fingerprint_binding(binding, repo_root=root)

    root = tmp_path / "repo-final-link"
    outside = tmp_path / "outside-final-link.json"
    outside.write_bytes(raw)
    final = root / ref
    final.parent.mkdir(parents=True)
    final.symlink_to(outside)
    with pytest.raises(EvidenceFingerprintError, match="无法读取"):
        resolve_fingerprint_binding(binding, repo_root=root)


def test_referenced_receipt_reader_rejects_fifo_and_hardlink(
    tmp_path: Path,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    binding, ref, raw = _referenced_receipt_fixture()
    fifo_root = tmp_path / "repo-fifo"
    fifo = fifo_root / ref
    fifo.parent.mkdir(parents=True)
    os.mkfifo(fifo)
    with pytest.raises(EvidenceFingerprintError, match="regular file"):
        resolve_fingerprint_binding(binding, repo_root=fifo_root)

    hardlink_root = tmp_path / "repo-hardlink"
    receipt = hardlink_root / ref
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(raw)
    os.link(receipt, receipt.parent / "alias.json")
    with pytest.raises(EvidenceFingerprintError, match="link count 必须为 1"):
        resolve_fingerprint_binding(binding, repo_root=hardlink_root)


def test_referenced_receipt_reader_keeps_open_inode_during_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    binding, ref, raw = _referenced_receipt_fixture()
    root = tmp_path / "repo-race"
    receipt = root / ref
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(raw)
    replacement = receipt.parent / "replacement.json"
    replacement.write_bytes(b"{}")
    real_read = os.read
    replaced = False

    def replace_path_then_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        if not replaced:
            replaced = True
            replacement.replace(receipt)
        return real_read(descriptor, size)

    monkeypatch.setattr(os, "read", replace_path_then_read)
    observed = resolve_fingerprint_binding(binding, repo_root=root)
    assert replaced
    assert receipt.read_bytes() == b"{}"
    assert observed["ref"] == binding["ref"]


def test_owner_manifest_reader_rejects_ancestor_and_final_symlinks(
    tmp_path: Path,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    raw = canonical_json_bytes({"fixture": "outside"})
    ref = _owner_manifest_ref(raw)
    parts = review_cli._OWNER_MANIFEST_DIRECTORY_PARTS
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "repo-ancestor"
    parent = root.joinpath(*parts[:-1])
    parent.mkdir(parents=True)
    target = outside / parts[-1]
    target.mkdir()
    (target / Path(ref).name).write_bytes(raw)
    (parent / parts[-1]).symlink_to(target, target_is_directory=True)
    with mock.patch.object(review_cli, "REPO_ROOT", root), pytest.raises(OSError):
        review_cli._read_owner_manifest_exact_bytes(ref)

    root = tmp_path / "repo-final"
    final = root.joinpath(*parts, Path(ref).name)
    final.parent.mkdir(parents=True)
    outside_file = outside / "manifest.json"
    outside_file.write_bytes(raw)
    final.symlink_to(outside_file)
    with mock.patch.object(review_cli, "REPO_ROOT", root), pytest.raises(OSError):
        review_cli._read_owner_manifest_exact_bytes(ref)


def test_owner_manifest_reader_rejects_fifo_and_hardlink(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    raw = canonical_json_bytes({"fixture": "special"})
    ref = _owner_manifest_ref(raw)
    parts = review_cli._OWNER_MANIFEST_DIRECTORY_PARTS
    fifo_root = tmp_path / "repo-fifo-manifest"
    fifo = fifo_root.joinpath(*parts, Path(ref).name)
    fifo.parent.mkdir(parents=True)
    os.mkfifo(fifo)
    with (
        mock.patch.object(review_cli, "REPO_ROOT", fifo_root),
        pytest.raises(OSError, match="regular file"),
    ):
        review_cli._read_owner_manifest_exact_bytes(ref)

    hardlink_root = tmp_path / "repo-hardlink-manifest"
    manifest = hardlink_root.joinpath(*parts, Path(ref).name)
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(raw)
    os.link(manifest, manifest.parent / "alias.json")
    with (
        mock.patch.object(review_cli, "REPO_ROOT", hardlink_root),
        pytest.raises(OSError, match="link count 必须为 1"),
    ):
        review_cli._read_owner_manifest_exact_bytes(ref)


def test_owner_manifest_reader_keeps_open_inode_during_replacement(
    tmp_path: Path,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    original = canonical_json_bytes({"fixture": "opened-descriptor"})
    replacement = canonical_json_bytes({"fixture": "replacement-path"})
    ref = _owner_manifest_ref(original)
    root = tmp_path / "repo-race-manifest"
    manifest = root.joinpath(
        *review_cli._OWNER_MANIFEST_DIRECTORY_PARTS, Path(ref).name
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(original)
    replacement_path = manifest.parent / "replacement.json"
    replacement_path.write_bytes(replacement)
    real_read = review_cli.os.read
    replaced = False

    def replace_path_then_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        if not replaced:
            replaced = True
            replacement_path.replace(manifest)
        return real_read(descriptor, size)

    with (
        mock.patch.object(review_cli, "REPO_ROOT", root),
        mock.patch.object(
            review_cli.os, "read", side_effect=replace_path_then_read
        ),
    ):
        observed = review_cli._read_owner_manifest_exact_bytes(ref)
    assert replaced
    assert manifest.read_bytes() == replacement
    assert observed == original
