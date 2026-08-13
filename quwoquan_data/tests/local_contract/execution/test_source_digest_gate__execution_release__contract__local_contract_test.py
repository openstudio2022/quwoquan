"""The source digest gate rejects execution drift and release receipt drift."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.source_digest import current_source_digest  # noqa: E402
from core.source_digest import (  # noqa: E402
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from verify import verify_source_digest  # noqa: E402
from verify.verify_source_digest import source_digest_issues  # noqa: E402

CANDIDATE_ID = "20260812--travel-article-candidate--china--pilot-001"


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_source_digest_gate__execution_release__contract__local_contract(tmp_path: Path) -> None:
    digest = current_source_digest().to_document()
    _write(
        tmp_path / f"tasks/{CANDIDATE_ID}/execution_manifest.json",
        _candidate_manifest(),
    )
    _write(
        tmp_path / "releases/example/payload/release.json",
        {"sourceDigests": [digest]},
    )
    _write(
        tmp_path / "releases/example/attestations/release.json",
        {"sourceDigests": [digest]},
    )

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
    ) == []


def test_source_digest_gate__rejects_release_receipt_drift__contract__local_contract(
    tmp_path: Path,
) -> None:
    digest = current_source_digest().to_document()
    changed = dict(digest)
    changed["digest"] = "sha256:" + "0" * 64
    _write(
        tmp_path / "releases/example/payload/release.json",
        {"sourceDigests": [digest]},
    )
    aggregate = tmp_path / "releases/example/attestations/release.json"
    _write(aggregate, {"sourceDigests": [changed]})

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
    ) == [f"{aggregate}: sourceDigests drift from release header"]


def test_source_digest_gate__rejects_identity_annotated_frozen_digest__contract__local_contract(
    tmp_path: Path,
) -> None:
    digest = current_source_digest().to_document()
    digest["inputs"] = ["quwoquan_data/historical/pre-contract-source"]
    identities = [
        {
            "identityKind": "retired-kind-must-not-unlock-frozen-inputs",
            "sourceDigest": digest["digest"],
        }
    ]
    header = tmp_path / "releases/example/payload/release.json"
    aggregate = tmp_path / "releases/example/attestations/release.json"
    for path in (header, aggregate):
        _write(path, {"sourceDigests": [digest], "sourceIdentities": identities})

    issues = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
    )

    assert issues == [
        f"{header}: sourceDigest.inputs must name the fixed repository inputs",
        f"{aggregate}: sourceDigest.inputs must name the fixed repository inputs",
    ]


def test_source_digest_gate__rejects_frozen_digest__contract__local_contract(
    tmp_path: Path,
) -> None:
    digest = current_source_digest().to_document()
    digest["inputs"] = ["quwoquan_data/historical/pre-contract-source"]
    header = tmp_path / "releases/example/payload/release.json"
    aggregate = tmp_path / "releases/example/attestations/release.json"
    for path in (header, aggregate):
        _write(path, {"sourceDigests": [digest], "sourceIdentities": []})

    issues = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
    )

    assert issues == [
        f"{header}: sourceDigest.inputs must name the fixed repository inputs",
        f"{aggregate}: sourceDigest.inputs must name the fixed repository inputs",
    ]


def _candidate_manifest() -> dict[str, object]:
    return {
        "executionId": CANDIDATE_ID,
        "sourceDigest": current_source_definition_snapshot().to_document(),
        "executionBundle": current_execution_bundle_identity().to_document(),
    }


def test_candidate_verify_requires_strict_existing_execution_id(tmp_path: Path) -> None:
    invalid = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        candidate_execution_id="example",
    )
    missing = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        candidate_execution_id=CANDIDATE_ID,
    )

    assert invalid[0].startswith("GATE_BLOCK DATA.EXECUTION.CANDIDATE_ID_INVALID")
    assert missing[0].startswith("GATE_BLOCK DATA.EXECUTION.CANDIDATE_NOT_FOUND")


def test_invalid_candidate_fails_before_any_live_digest_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verify_source_digest,
        "current_source_definition_snapshot",
        lambda: pytest.fail("invalid candidate read live source snapshot"),
    )
    monkeypatch.setattr(
        verify_source_digest,
        "current_execution_bundle_identity",
        lambda: pytest.fail("invalid candidate read live execution bundle"),
    )

    issues = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        candidate_execution_id="invalid",
    )

    assert issues[0].startswith("GATE_BLOCK DATA.EXECUTION.CANDIDATE_ID_INVALID")


def test_candidate_verify_scans_only_exact_execution_and_no_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "tasks" / CANDIDATE_ID / "execution_manifest.json"
    _write(candidate, _candidate_manifest())
    _write(
        tmp_path / "tasks/20260812--travel-video-other--china--pilot-001/execution_manifest.json",
        {"sourceDigest": {"invalid": True}},
    )
    _write(
        tmp_path / "releases/broken/payload/release.json",
        {"sourceDigests": []},
    )
    monkeypatch.setattr(
        verify_source_digest,
        "load_terminal_execution_evidence",
        lambda root: None
        if root.name == CANDIDATE_ID
        else pytest.fail("candidate verifier scanned another execution"),
    )

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        candidate_execution_id=CANDIDATE_ID,
    ) == []
