"""Canonical package/runtime zero-legacy-entry producer and scan contract.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-003
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#open-006
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

DATA_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = DATA_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify import legacy_runtime_entries as patterns  # noqa: E402
from verify import legacy_runtime_zero_evidence as subject  # noqa: E402
from verify import verify_script_architecture  # noqa: E402

FINGERPRINT = "sha256:" + "f" * 64


def _repo(root: Path) -> Path:
    for name in patterns.SCANNED_ROOTS:
        (root / name).mkdir(parents=True)
    return root


def test_scan_and_architecture_gate_share_one_pattern_authoring_source() -> None:
    assert (
        verify_script_architecture.LEGACY_ORCHESTRATION_FAMILIES
        is patterns.LEGACY_ORCHESTRATION_FAMILIES
    )
    assert verify_script_architecture.scan_legacy_runtime_entries is patterns.scan_legacy_runtime_entries


def test_real_legacy_entry_blocks_and_create_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    legacy = repo / "quwoquan_service/services/content-service/cmd/data-content-worker/main.go"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("package main\n", encoding="utf-8")

    scan = subject.scan_package_runtime_zero_evidence(
        repo_root=repo, source_fingerprint=FINGERPRINT
    )

    assert scan["verdict"] == "blocked"
    assert any("data-content-worker" in ref for ref in scan["legacyEntryRefs"])
    output = tmp_path / "output/evidence.json"
    with pytest.raises(subject.LegacyRuntimeZeroEvidenceError, match="legacy package/runtime refs remain"):
        subject.create_package_runtime_zero_evidence(
            repo_root=repo,
            source_fingerprint=FINGERPRINT,
            output=output,
        )
    assert not output.exists()


def test_zero_entry_scan_creates_exact_create_once_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    safe = repo / "quwoquan_service/runtime/reliabletask/runtime.go"
    safe.parent.mkdir(parents=True)
    safe.write_text("package reliabletask\n", encoding="utf-8")
    output = tmp_path / "evidence/zero.json"

    first, first_path = subject.create_package_runtime_zero_evidence(
        repo_root=repo,
        source_fingerprint=FINGERPRINT,
        output=output,
    )
    replay, replay_path = subject.create_package_runtime_zero_evidence(
        repo_root=repo,
        source_fingerprint=FINGERPRINT,
        output=output,
    )

    expected = {
        "schema": "quwoquan_data.legacy_runtime_zero_evidence",
        "sourceFingerprint": FINGERPRINT,
        "scannedRoots": ["quwoquan_app", "quwoquan_service", "quwoquan_ops", ".github"],
        "legacyEntryRefs": [],
        "verdict": "pass",
    }
    assert first == replay == expected
    assert first_path == replay_path == output
    assert output.read_bytes() == subject._canonical_bytes(expected)


def test_create_once_id_collision_preserves_existing_bytes(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    output = tmp_path / "evidence/zero.json"
    output.parent.mkdir(parents=True)
    original = b'{"existing":"different identity"}\n'
    output.write_bytes(original)

    with pytest.raises(subject.LegacyRuntimeZeroEvidenceError, match="id collision"):
        subject.create_package_runtime_zero_evidence(
            repo_root=repo,
            source_fingerprint=FINGERPRINT,
            output=output,
        )

    assert output.read_bytes() == original


def test_zero_entry_create_is_safe_under_identical_concurrent_writers(
    tmp_path: Path,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    repo = _repo(tmp_path / "repo")
    output = tmp_path / "evidence/zero.json"

    def create() -> tuple[dict[str, object], Path]:
        return subject.create_package_runtime_zero_evidence(
            repo_root=repo,
            source_fingerprint=FINGERPRINT,
            output=output,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: create(), range(2)))

    assert results[0] == results[1]
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "pass"


def test_symbolic_entry_and_unknown_entry_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    external = tmp_path / "external.py"
    external.write_text("print('external')\n", encoding="utf-8")
    (repo / "quwoquan_app/runtime.py").symlink_to(external)
    fifo = repo / "quwoquan_ops/runtime.pipe"
    os.mkfifo(fifo)

    with pytest.raises(subject.LegacyRuntimeZeroEvidenceError, match="scan is blocked") as error:
        subject.scan_package_runtime_zero_evidence(
            repo_root=repo, source_fingerprint=FINGERPRINT
        )

    assert "symbolic file is not accepted" in str(error.value)
    assert "unknown file entry type" in str(error.value)


def test_read_error_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path / "repo")
    source = repo / "quwoquan_service/runtime.go"
    source.write_text("package runtime\n", encoding="utf-8")
    original = patterns._read_regular_text

    def fail_selected(path: Path) -> str:
        if path == source:
            raise OSError("synthetic read failure")
        return original(path)

    monkeypatch.setattr(patterns, "_read_regular_text", fail_selected)
    with pytest.raises(subject.LegacyRuntimeZeroEvidenceError, match="synthetic read failure"):
        subject.scan_package_runtime_zero_evidence(
            repo_root=repo, source_fingerprint=FINGERPRINT
        )


def test_source_fingerprint_must_be_explicit_and_canonical(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    for value in ("", "HEAD", "f" * 64, "sha256:" + "F" * 64):
        with pytest.raises(subject.LegacyRuntimeZeroEvidenceError, match="explicit canonical"):
            subject.scan_package_runtime_zero_evidence(
                repo_root=repo, source_fingerprint=value
            )
