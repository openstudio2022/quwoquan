"""The source digest gate rejects execution drift and release receipt drift."""
from __future__ import annotations

import json
import sys
from argparse import Namespace
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
from verify import handler as verify_handler  # noqa: E402
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
        scope="all",
    ) == []


def test_source_digest_gate__rejects_release_receipt_drift__contract__local_contract(
    tmp_path: Path,
) -> None:
    digest = current_source_definition_snapshot().to_document()
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
        scope="all",
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
        scope="all",
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


def test_current_candidate_ignores_legacy_execution_while_all_audits_it(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "tasks" / CANDIDATE_ID / "execution_manifest.json"
    _write(candidate, _candidate_manifest())
    legacy = (
        tmp_path
        / "tasks/20260811--travel-video-legacy--china--pilot-001/execution_manifest.json"
    )
    _write(
        legacy,
        {
            "executionId": legacy.parent.name,
            "sourceDigest": current_source_digest().to_document(),
        },
    )

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        candidate_execution_id=CANDIDATE_ID,
        scope="current",
    ) == []
    all_issues = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        scope="all",
    )
    assert any(
        "DATA.EXECUTION.SOURCE_IDENTITY_MIGRATION_REQUIRED" in issue
        and str(legacy) in issue
        for issue in all_issues
    )


def test_current_candidate_source_drift_remains_gate_blocking(tmp_path: Path) -> None:
    manifest = _candidate_manifest()
    source_digest = dict(manifest["sourceDigest"])
    source_digest["digest"] = "sha256:" + "0" * 64
    manifest["sourceDigest"] = source_digest
    path = tmp_path / "tasks" / CANDIDATE_ID / "execution_manifest.json"
    _write(path, manifest)

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        candidate_execution_id=CANDIDATE_ID,
        scope="current",
    ) == [
        f"{path}: candidate source snapshot/execution bundle drift; "
        "create a new execution sequence with retryOf"
    ]


def test_current_without_selected_candidate_does_not_infer_one_from_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = (
        tmp_path
        / "tasks/20260811--travel-video-legacy--china--pilot-001/execution_manifest.json"
    )
    _write(legacy, {"sourceDigest": {"invalid": True}})
    monkeypatch.setattr(
        verify_source_digest,
        "load_terminal_execution_evidence",
        lambda _root: pytest.fail("current scope inferred a candidate from history"),
    )

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        scope="current",
    ) == []


def test_current_release_view_excludes_legacy_shape_but_detects_current_drift(
    tmp_path: Path,
) -> None:
    legacy_digest = current_source_digest().to_document()
    legacy_header = tmp_path / "releases/legacy/payload/release.json"
    legacy_attestation = tmp_path / "releases/legacy/attestations/release.json"
    _write(legacy_header, {"sourceDigests": [legacy_digest]})
    invalid_legacy = dict(legacy_digest)
    invalid_legacy["inputs"] = ["quwoquan_data/historical/pre-contract-source"]
    _write(legacy_attestation, {"sourceDigests": [invalid_legacy]})

    current_digest = current_source_definition_snapshot().to_document()
    current_header = tmp_path / "releases/current/payload/release.json"
    current_attestation = tmp_path / "releases/current/attestations/release.json"
    _write(current_header, {"sourceDigests": [current_digest]})
    changed = dict(current_digest)
    changed["digest"] = "sha256:" + "0" * 64
    _write(current_attestation, {"sourceDigests": [changed]})

    assert source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        scope="current",
    ) == [f"{current_attestation}: sourceDigests drift from release header"]
    all_issues = source_digest_issues(
        executions_root=tmp_path / "tasks",
        release_root=tmp_path / "releases",
        scope="all",
    )
    assert any(str(legacy_attestation) in issue for issue in all_issues)


def test_source_digest_cli_forwards_scope_to_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def _main(argv: list[str]) -> int:
        captured.append(argv)
        return 0

    monkeypatch.setattr(verify_source_digest, "main", _main)
    with pytest.raises(SystemExit) as stopped:
        verify_handler.handle_verify(
            Namespace(
                verify_command="source-digest",
                source_execution_id=None,
                scope="all",
            )
        )

    assert stopped.value.code == 0
    assert captured == [["--scope", "all"]]
