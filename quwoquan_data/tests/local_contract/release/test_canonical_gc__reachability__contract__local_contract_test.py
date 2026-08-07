from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.closure.adoption_contract import (
    canonical_digest,
    file_digest,
)
from content.release.canonical import (
    garbage_collection_operations,
    garbage_collection_protection,
)
from content.release.canonical.garbage_collection import (
    apply_canonical_gc,
    plan_canonical_gc,
)
from content.release.canonical.handler import register_parser
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.release_identity_incident import (
    identity_protection_lock_path,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _task(
    output: Path,
    execution_id: str,
    *,
    retry_of: str | None = None,
    active_lease: bool = False,
) -> Path:
    root = output / "data/tasks" / execution_id
    _write_json(
        root / "execution_manifest.json",
        {
            "executionId": execution_id,
            "retryOf": retry_of,
        },
    )
    _write_json(
        root / "_shared/execution_state.json",
        {"executionId": execution_id, "status": "succeeded"},
    )
    if active_lease:
        _write_json(
            root / "_shared/controller_lease.json",
            {
                "schema": "quwoquan_data.controller_lease",
                "status": "active",
                "executionId": execution_id,
                "controllerRunId": "gc-test-controller",
                "pid": os.getpid(),
                "startedAt": "2026-08-05T00:00:00+00:00",
                "heartbeatAt": "2026-08-05T00:00:00+00:00",
            },
        )
    return root


def _release(release_root: Path, release_id: str, execution_ids: list[str]) -> None:
    _write_json(
        release_root / release_id / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": release_id,
            "executionIds": execution_ids,
        },
    )


def _transaction(output: Path, transaction_id: str, execution_id: str) -> Path:
    root = output / "data/local/workspace/object-transactions" / transaction_id
    _write_json(
        root / "audit_report.json",
        {"transactionId": transaction_id, "executionId": execution_id},
    )
    _write_json(
        root / "apply_report.json",
        {"transactionId": transaction_id, "executionId": execution_id},
    )
    return root


def _identity_incident(output: Path, execution_id: str) -> Path:
    release_id = "release-identity-collision-gc"
    incident_id = "identity-collision-gc-001"
    root = (
        output
        / "data/local/workspace/release-identity-incidents"
        / release_id
        / incident_id
    )
    observed: list[dict[str, object]] = []
    for name, payload_digest, canonical_merkle in (
        ("old", "sha256:" + "1" * 64, "sha256:" + "2" * 64),
        ("current", "sha256:" + "3" * 64, "sha256:" + "4" * 64),
    ):
        attestation = root / "evidence" / f"{name}.json"
        _write_json(
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
    incident = root / "incident.json"
    _write_json(incident, {**stable, "receiptDigest": canonical_digest(stable)})
    return incident


def test_gc_plan_and_apply_preserve_release_retry_lease_and_incomplete_work(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    released = "20260801--travel-image-gc--cn--pilot-001"
    retry_parent = "20260801--travel-image-gc--cn--pilot-002"
    retry_child = "20260801--travel-image-gc--cn--pilot-003"
    active = "20260801--travel-image-gc--cn--pilot-004"
    collectible = "20260801--travel-image-gc--cn--pilot-005"
    publish_protected = "20260801--travel-image-gc--cn--pilot-006"
    for execution_id in (released, retry_parent, collectible, publish_protected):
        _task(output, execution_id)
    _task(output, retry_child, retry_of=retry_parent)
    _task(output, active, active_lease=True)
    _release(release_root, "release-protected", [released])
    _write_json(
        publish / "posts/image/gc/fixture/manifest.json",
        {"sourceTaskId": publish_protected},
    )
    collectible_transaction = _transaction(
        output,
        "collectible-transaction",
        collectible,
    )
    released_transaction = _transaction(
        output,
        "released-transaction",
        released,
    )
    incomplete_transaction = (
        output / "data/local/workspace/object-transactions/incomplete-transaction"
    )
    _write_json(
        incomplete_transaction / "audit_report.json",
        {"transactionId": "incomplete-transaction", "executionId": collectible},
    )

    plan, _path = plan_canonical_gc(
        plan_id="gc-plan-one",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
        min_age_hours=0,
    )
    candidate_refs = {row["ref"] for row in plan["candidates"]}

    assert f"data/tasks/{collectible}" in candidate_refs
    assert (
        "data/local/workspace/object-transactions/collectible-transaction"
        in candidate_refs
    )
    assert f"data/tasks/{released}" not in candidate_refs
    assert f"data/tasks/{retry_parent}" not in candidate_refs
    assert f"data/tasks/{active}" not in candidate_refs
    assert f"data/tasks/{publish_protected}" not in candidate_refs
    assert (
        "data/local/workspace/object-transactions/released-transaction"
        not in candidate_refs
    )
    assert (
        "data/local/workspace/object-transactions/incomplete-transaction"
        not in candidate_refs
    )

    receipt, receipt_path = apply_canonical_gc(
        plan_id="gc-plan-one",
        plan_digest=str(plan["planDigest"]),
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )

    assert receipt["status"] == "applied"
    assert receipt["permanentDeletion"] is False
    assert receipt["quarantinedCount"] == plan["candidateCount"]
    for row in receipt["quarantined"]:
        assert (output / row["quarantineRef"]).is_dir()
    assert receipt_path.is_file()
    assert not (output / f"data/tasks/{collectible}").exists()
    assert not collectible_transaction.exists()
    assert (output / f"data/tasks/{released}").is_dir()
    assert (output / f"data/tasks/{retry_parent}").is_dir()
    assert (output / f"data/tasks/{active}").is_dir()
    assert released_transaction.is_dir()
    assert incomplete_transaction.is_dir()

    rerun, _ = apply_canonical_gc(
        plan_id="gc-plan-one",
        plan_digest=str(plan["planDigest"]),
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    assert rerun["idempotent"] is True


def test_gc_apply_rechecks_release_reachability_before_quarantine(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    execution_id = "20260801--travel-video-gc--cn--pilot-001"
    task = _task(output, execution_id)

    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-drift",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
        min_age_hours=0,
    )
    assert plan["candidateCount"] == 1
    _release(release_root, "late-release", [execution_id])

    with pytest.raises(ObjectTransactionError, match="became protected"):
        apply_canonical_gc(
            plan_id="gc-plan-drift",
            plan_digest=str(plan["planDigest"]),
            output_root=output,
            publish_root=publish,
            release_root=release_root,
        )

    assert task.is_dir()


def test_gc_plan_create_once_rejects_request_drift(tmp_path: Path) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    _task(output, "20260801--travel-image-gc--cn--pilot-031")
    plan_canonical_gc(
        plan_id="gc-plan-create-once",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )

    with pytest.raises(ObjectTransactionError, match="request drift"):
        plan_canonical_gc(
            plan_id="gc-plan-create-once",
            output_root=output,
            publish_root=publish,
            min_age_hours=24,
        )


def test_gc_apply_fails_closed_when_prepared_target_and_quarantine_are_missing(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    execution_id = "20260801--travel-image-gc--cn--pilot-032"
    task = _task(output, execution_id)
    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-lost-target",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )
    candidate = next(
        row for row in plan["candidates"] if row["ref"].endswith(execution_id)
    )
    journal = (
        output / "data/local/workspace/gc/plans/gc-plan-lost-target/apply.journal.jsonl"
    )
    journal.write_text(
        json.dumps(
            {
                "ref": candidate["ref"],
                "kind": candidate["kind"],
                "pathType": candidate["pathType"],
                "status": "prepared",
                "merkleRoot": candidate["merkleRoot"],
                "fileCount": candidate["fileCount"],
                "bytes": candidate["bytes"],
                "quarantineRef": (
                    "data/local/workspace/quarantine/canonical-gc/"
                    f"gc-plan-lost-target/{candidate['ref']}"
                ),
                "preparedAt": "2026-08-05T00:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    task.rename(tmp_path / "lost-outside-output")

    with pytest.raises(ObjectTransactionError, match="quarantine candidate is missing"):
        apply_canonical_gc(
            plan_id="gc-plan-lost-target",
            plan_digest=str(plan["planDigest"]),
            output_root=output,
            publish_root=publish,
        )


def test_gc_preserves_execution_protected_by_release_identity_incident(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    protected = "20260801--travel-image-gc--cn--pilot-021"
    collectible = "20260801--travel-image-gc--cn--pilot-022"
    _task(output, protected)
    _task(output, collectible)
    _identity_incident(output, protected)

    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-identity-incident",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
        min_age_hours=0,
    )

    candidates = {row["ref"] for row in plan["candidates"]}
    protected_rows = {
        row["executionId"]: row["reasons"] for row in plan["protectedExecutions"]
    }
    assert f"data/tasks/{protected}" not in candidates
    assert f"data/tasks/{collectible}" in candidates
    assert protected_rows[protected] == ["release_identity_incident"]
    assert plan["releaseIdentityIncidentReleaseRefs"] == [
        "release-identity-collision-gc"
    ]
    assert plan["releaseIdentityIncidentExecutionRefs"] == [protected]


def test_gc_apply_rechecks_late_release_identity_incident(tmp_path: Path) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    execution_id = "20260801--travel-video-gc--cn--pilot-024"
    task = _task(output, execution_id)
    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-before-identity-incident",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )
    assert plan["candidateCount"] == 1
    _identity_incident(output, execution_id)

    with pytest.raises(ObjectTransactionError, match="became protected"):
        apply_canonical_gc(
            plan_id="gc-plan-before-identity-incident",
            plan_digest=str(plan["planDigest"]),
            output_root=output,
            publish_root=publish,
        )

    assert task.is_dir()


def test_gc_apply_holds_identity_protection_lock_through_quarantine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    execution_id = "20260801--travel-video-gc--cn--pilot-026"
    _task(output, execution_id)
    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-protection-lock",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )
    lock_observed: list[Path] = []
    original_validate = garbage_collection_operations._validate_quarantined_candidate

    def _validate_while_locked(path: Path, candidate: dict[str, object]) -> None:
        lock_path = identity_protection_lock_path(output_root=output)
        with lock_path.open("a+b") as handle, pytest.raises(BlockingIOError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_observed.append(path)
        original_validate(path, candidate)

    monkeypatch.setattr(
        garbage_collection_operations,
        "_validate_quarantined_candidate",
        _validate_while_locked,
    )
    receipt, _ = apply_canonical_gc(
        plan_id="gc-plan-protection-lock",
        plan_digest=str(plan["planDigest"]),
        output_root=output,
        publish_root=publish,
    )

    assert receipt["status"] == "applied"
    assert output / "data/tasks" / execution_id in lock_observed
    assert any("workspace/quarantine" in path.as_posix() for path in lock_observed)


def test_gc_fails_closed_when_identity_incident_receipt_drifts(tmp_path: Path) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    execution_id = "20260801--travel-image-gc--cn--pilot-023"
    _task(output, execution_id)
    incident = _identity_incident(output, execution_id)
    document = json.loads(incident.read_text(encoding="utf-8"))
    document["protectedExecutionIds"] = []
    stable = {key: value for key, value in document.items() if key != "receiptDigest"}
    document["receiptDigest"] = canonical_digest(stable)
    _write_json(incident, document)

    with pytest.raises(ObjectTransactionError, match="IDENTITY_INCIDENT_INVALID"):
        plan_canonical_gc(
            plan_id="gc-plan-invalid-identity-incident",
            output_root=output,
            publish_root=publish,
            min_age_hours=0,
        )


def test_gc_preserves_execution_and_source_release_referenced_by_adoption(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    execution_id = "20260801--travel-article-gc--cn--pilot-025"
    _task(output, execution_id)
    ref = (
        output
        / "data/local/reviewed-closure-adoptions/adoption-gc-001/adoption_ref.json"
    )
    _write_json(ref, {})
    monkeypatch.setattr(
        garbage_collection_protection,
        "validate_reviewed_closure_adoption_ref",
        lambda _document, *, output_root: SimpleNamespace(
            adoption_id="adoption-gc-001",
            source_release_identity=SimpleNamespace(release_id="source-release-gc"),
            upstream_execution_ids=(execution_id,),
        ),
    )

    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-adoption-reference",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )

    protected = {
        row["executionId"]: row["reasons"] for row in plan["protectedExecutions"]
    }
    assert protected[execution_id] == ["reviewed_closure_adoption"]
    assert plan["reviewedClosureAdoptionSourceReleaseRefs"] == ["source-release-gc"]
    assert plan["reviewedClosureAdoptionExecutionRefs"] == [execution_id]


def test_gc_apply_recovers_quarantine_before_journal_event(tmp_path: Path) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    execution_id = "20260801--travel-article-gc--cn--pilot-001"
    task = _task(output, execution_id)

    plan, _ = plan_canonical_gc(
        plan_id="gc-plan-interrupted",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
        min_age_hours=0,
    )
    candidate = next(
        row for row in plan["candidates"] if row["ref"] == f"data/tasks/{execution_id}"
    )
    journal = (
        output / "data/local/workspace/gc/plans/gc-plan-interrupted/apply.journal.jsonl"
    )
    quarantine = (
        output
        / "data/local/workspace/quarantine/canonical-gc/gc-plan-interrupted"
        / candidate["ref"]
    )
    journal.write_text(
        json.dumps(
            {
                "ref": candidate["ref"],
                "kind": candidate["kind"],
                "pathType": candidate["pathType"],
                "status": "prepared",
                "merkleRoot": candidate["merkleRoot"],
                "fileCount": candidate["fileCount"],
                "bytes": candidate["bytes"],
                "quarantineRef": quarantine.relative_to(output).as_posix(),
                "preparedAt": "2026-08-05T00:00:00+00:00",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # Simulate a stop after the fsynced prepared event and atomic quarantine,
    # but before the quarantined event is appended.
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    task.replace(quarantine)

    receipt, _ = apply_canonical_gc(
        plan_id="gc-plan-interrupted",
        plan_digest=str(plan["planDigest"]),
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )

    assert receipt["status"] == "applied"
    assert receipt["quarantinedCount"] == 1
    assert receipt["quarantined"][0]["status"] == "quarantined"
    assert receipt["permanentDeletion"] is False
    assert quarantine.is_dir()


def test_release_cli_exposes_digest_bound_gc_plan_and_apply() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser(commands)

    plan = parser.parse_args(["release", "gc", "plan", "--plan-id", "gc-plan-cli"])
    apply = parser.parse_args(
        [
            "release",
            "gc",
            "apply",
            "--plan-id",
            "gc-plan-cli",
            "--plan-digest",
            "sha256:" + "1" * 64,
        ]
    )

    assert plan.release_gc_action == "plan"
    assert plan.min_age_hours == 168.0
    assert apply.release_gc_action == "apply"
    assert apply.plan_digest == "sha256:" + "1" * 64
