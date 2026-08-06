from __future__ import annotations

import fcntl
from pathlib import Path

import pytest
from content.execution import discard, workspace
from content.execution.reviewed_closure_adoption_contract import (
    canonical_digest,
    file_digest,
)
from content.release.canonical.release_identity_incident import (
    identity_protection_lock_path,
)
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_IDENTITY_INCIDENTS_ROOT

EXECUTION_ID = "20260725--travel-homepage-coverage--test-region-a--scale-002"


def _identity_incident(output: Path, execution_id: str) -> None:
    release_id = "release-identity-collision-discard"
    incident_id = "identity-collision-discard-001"
    root = output / RELEASE_IDENTITY_INCIDENTS_ROOT.relative_to(OUTPUT_ROOT)
    root = root / release_id / incident_id
    observed: list[dict[str, object]] = []
    for name, payload_digest, canonical_merkle in (
        ("old", "sha256:" + "5" * 64, "sha256:" + "6" * 64),
        ("current", "sha256:" + "7" * 64, "sha256:" + "8" * 64),
    ):
        attestation = root / "evidence" / f"{name}.json"
        write_json(
            attestation,
            {
                "releaseId": release_id,
                "payloadSha256": payload_digest,
                "canonicalMerkle": canonical_merkle,
                "executionIds": [execution_id],
            },
        )
        observed.append(
            {
                "releaseId": release_id,
                "payloadSha256": payload_digest,
                "canonicalMerkle": canonical_merkle,
                "attestationFileSha256": file_digest(attestation),
                "attestationRef": attestation.relative_to(output).as_posix(),
                "acquisitionMode": "original_file",
                "executionIds": [execution_id],
                "observedAt": "2026-08-05T00:00:00+00:00",
            }
        )
    observed.sort(
        key=lambda row: (
            str(row["releaseId"]),
            str(row["payloadSha256"]),
            str(row["canonicalMerkle"]),
            str(row["attestationFileSha256"]),
        )
    )
    stable: dict[str, object] = {
        "schema": "quwoquan_data.release_identity_incident",
        "incidentId": incident_id,
        "releaseId": release_id,
        "status": "identity_collided",
        "storageClass": "append_only_create_once",
        "observedIdentities": observed,
        "protectedExecutionIds": [execution_id],
        "recordedAt": "2026-08-05T00:00:00+00:00",
    }
    write_json(
        root / "incident.json",
        {**stable, "receiptDigest": canonical_digest(stable)},
    )


def test_frozen_target_archive_survives_execution_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "execution" / "0.plan" / "target_set.json"
    archive = tmp_path / "workspace" / f"{EXECUTION_ID}.json"
    payload = {
        "executionId": EXECUTION_ID,
        "selectionPolicy": "frozen",
        "sourceRef": "quwoquan_data/reference/travel/entities/china",
        "entityCatalogDigest": "sha256:" + "1" * 64,
        "targetCount": 1,
        "targetRefs": ["地点/景区/测试景区"],
        "targets": [{"name": "测试景区", "entityType": "地点/景区"}],
    }
    write_json(source, payload)
    monkeypatch.setattr(workspace, "execution_target_set_path", lambda _value: source)
    monkeypatch.setattr(workspace, "frozen_target_archive_path", lambda _value: archive)

    assert workspace.archive_frozen_target_set(EXECUTION_ID) == archive
    source.unlink()

    assert workspace.load_frozen_target_set(EXECUTION_ID) == payload


def test_discard_removes_only_inactive_execution_and_derived_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / EXECUTION_ID
    root.mkdir()
    transactions = tmp_path / "transactions"
    derived = transactions / f"{EXECUTION_ID}--entity-测试对象"
    derived.mkdir(parents=True)
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(discard, "transaction_workspace_root", lambda: transactions)
    monkeypatch.setattr(discard, "active_controller_issue", lambda _execution_id: None)
    monkeypatch.setattr(discard, "_active_execution_processes", lambda _execution_id: ())
    archived: list[str] = []
    monkeypatch.setattr(
        discard,
        "archive_frozen_target_set",
        lambda execution_id: archived.append(execution_id),
    )

    discard.discard_execution(EXECUTION_ID)

    assert not root.exists()
    assert not derived.exists()
    assert archived == [EXECUTION_ID]


def test_discard_rejects_live_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / EXECUTION_ID
    root.mkdir()
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(
        discard,
        "active_controller_issue",
        lambda _execution_id: "GATE_BLOCK controller lease active for execution",
    )

    with pytest.raises(RuntimeError, match="controller lease active"):
        discard.discard_execution(EXECUTION_ID)


def test_discard_rejects_execution_protected_by_release_identity_incident(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    root = tmp_path / EXECUTION_ID
    root.mkdir()
    _identity_incident(output, EXECUTION_ID)
    archived: list[str] = []
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(
        discard,
        "archive_frozen_target_set",
        lambda execution_id: archived.append(execution_id),
    )

    with pytest.raises(RuntimeError, match="IDENTITY_INCIDENT_PROTECTED"):
        discard.discard_execution(EXECUTION_ID, output_root=output)

    assert root.is_dir()
    assert archived == []


def test_discard_holds_identity_protection_lock_through_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    root = tmp_path / EXECUTION_ID
    root.mkdir()
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(
        discard,
        "transaction_workspace_root",
        lambda: tmp_path / "transactions",
    )
    monkeypatch.setattr(discard, "active_controller_issue", lambda _execution_id: None)
    monkeypatch.setattr(discard, "_active_execution_processes", lambda _execution_id: ())
    monkeypatch.setattr(discard, "archive_frozen_target_set", lambda _execution_id: None)
    original_rmtree = discard.shutil.rmtree
    lock_observed: list[Path] = []

    def _locked_rmtree(path: Path) -> None:
        lock_path = identity_protection_lock_path(output_root=output)
        with lock_path.open("a+b") as handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_observed.append(path)
        original_rmtree(path)

    monkeypatch.setattr(discard.shutil, "rmtree", _locked_rmtree)
    discard.discard_execution(EXECUTION_ID, output_root=output)

    assert lock_observed == [root]


def test_discard_purges_service_owned_fleet_before_local_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / EXECUTION_ID
    (root / "evidence" / "reliabletask").mkdir(parents=True)
    calls: list[str] = []
    monkeypatch.setattr(discard, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(discard, "transaction_workspace_root", lambda: tmp_path / "transactions")
    monkeypatch.setattr(discard, "active_controller_issue", lambda _execution_id: None)
    monkeypatch.setattr(discard, "_active_execution_processes", lambda _execution_id: ())
    monkeypatch.setattr(discard, "archive_frozen_target_set", lambda _execution_id: None)
    from content.execution import reliabletask_fleet

    monkeypatch.setattr(
        reliabletask_fleet,
        "discard_reliabletask_execution",
        lambda execution_id: calls.append(execution_id),
    )

    discard.discard_execution(EXECUTION_ID)

    assert calls == [EXECUTION_ID]
    assert not root.exists()


def test_task_execute_process_matcher_ignores_shell_text_and_matches_real_cli() -> None:
    shell_command = (
        'zsh -c "python3 quwoquan_data/scripts/cli.py task execute '
        f'--execution-id {EXECUTION_ID}"'
    )
    cli_command = (
        "/usr/bin/python3 quwoquan_data/scripts/cli.py task execute "
        f"--execution-id {EXECUTION_ID}"
    )

    assert not discard._is_task_execute_command(shell_command, EXECUTION_ID)
    assert discard._is_task_execute_command(cli_command, EXECUTION_ID)
