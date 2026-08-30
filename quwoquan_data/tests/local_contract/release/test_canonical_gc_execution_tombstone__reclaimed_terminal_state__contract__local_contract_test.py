# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-007.t2
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.release.canonical.garbage_collection import (
    apply_canonical_gc,
    backfill_absent_execution_tombstones,
    plan_canonical_gc,
    unresolved_execution_references,
)
from content.release.canonical.garbage_collection_tombstone import (
    ExecutionReclaimReason,
    execution_tombstone_path,
    load_execution_tombstones,
    write_execution_tombstone,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _task(output: Path, execution_id: str) -> Path:
    root = output / "data/tasks" / execution_id
    _write_json(
        root / "execution_manifest.json",
        {"executionId": execution_id, "retryOf": None},
    )
    _write_json(
        root / "_shared/execution_state.json",
        {"executionId": execution_id, "status": "succeeded"},
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


def test_release_reference_to_an_absent_task_blocks_the_plan_without_a_tombstone(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    gone = "20260801--travel-article-gc--cn--pilot-101"
    _release(release_root, "release-history", [gone])

    with pytest.raises(ObjectTransactionError, match="REFERENCE_MISSING"):
        plan_canonical_gc(
            plan_id="gc-tombstone-absent",
            output_root=output,
            publish_root=publish,
            release_root=release_root,
            min_age_hours=0,
        )


def test_backfilled_tombstone_makes_the_release_reference_a_readable_terminal_state(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    gone = "20260801--travel-article-gc--cn--pilot-102"
    live = "20260801--travel-article-gc--cn--pilot-103"
    _task(output, live)
    _release(release_root, "release-history", [gone])

    unresolved = unresolved_execution_references(
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    assert set(unresolved) == {gone}
    assert {row["relation"] for row in unresolved[gone]} == {
        "immutable_release_reference"
    }

    receipt, receipt_path = backfill_absent_execution_tombstones(
        backfill_id="gc-backfill-one",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    assert receipt["tombstoneCount"] == 1
    assert receipt["tombstones"][0]["executionId"] == gone
    assert receipt["tombstones"][0]["created"] is True
    assert receipt_path.is_file()

    plan, _ = plan_canonical_gc(
        plan_id="gc-tombstone-backfilled",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
        min_age_hours=0,
    )

    assert plan["reclaimedExecutions"] == [
        {
            "executionId": gone,
            "reclaimReason": "reclaimed_before_tombstone_protocol",
            "tombstoneRef": (
                f"data/local/workspace/gc/tombstones/{gone}/tombstone.json"
            ),
        }
    ]
    nodes = {row["ref"]: row["kind"] for row in plan["referenceGraph"]["nodes"]}
    assert nodes[f"data/tasks/{gone}"] == "reclaimed_execution"
    assert nodes[f"data/tasks/{live}"] == "execution"
    protected = {
        row["ref"] for row in plan["referenceGraph"]["protectedArtifactRefs"]
    }
    assert (
        f"data/local/workspace/gc/tombstones/{gone}/tombstone.json" in protected
    )
    # The tombstone resolves the reference; it does not resurrect protection for
    # an execution that is no longer on disk, and it never becomes collectable
    # evidence of itself.
    assert not any(
        str(row["ref"]).startswith("data/local/workspace/gc/")
        for row in plan["candidates"]
    )


def test_backfill_is_create_once_and_replays_to_the_same_conclusion(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    gone = "20260801--travel-article-gc--cn--pilot-104"
    _release(release_root, "release-history", [gone])

    first, _ = backfill_absent_execution_tombstones(
        backfill_id="gc-backfill-replay",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    digest = first["tombstones"][0]["tombstoneDigest"]

    second, _ = backfill_absent_execution_tombstones(
        backfill_id="gc-backfill-replay",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )

    assert second["receiptDigest"] == first["receiptDigest"]
    assert (
        load_execution_tombstones(output)[gone].document["tombstoneDigest"] == digest
    )
    # A second backfill under a new id finds nothing left to conclude, because
    # the first one already gave the reference its terminal state.
    third, _ = backfill_absent_execution_tombstones(
        backfill_id="gc-backfill-second-pass",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    assert third["tombstoneCount"] == 0


def test_collector_writes_a_tombstone_where_it_reclaimed_an_execution(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    collectible = "20260801--travel-article-gc--cn--pilot-105"
    task = _task(output, collectible)

    plan, _ = plan_canonical_gc(
        plan_id="gc-tombstone-reclaim",
        output_root=output,
        publish_root=publish,
        release_root=release_root,
        min_age_hours=0,
    )
    assert {row["ref"] for row in plan["candidates"]} == {
        f"data/tasks/{collectible}"
    }

    receipt, _ = apply_canonical_gc(
        plan_id="gc-tombstone-reclaim",
        plan_digest=str(plan["planDigest"]),
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    assert receipt["status"] == "applied"
    assert not task.exists()

    tombstone = json.loads(
        execution_tombstone_path(output, collectible).read_text(encoding="utf-8")
    )
    assert tombstone["reclaimReason"] == "gc_quarantine_reclaim"
    assert tombstone["planId"] == "gc-tombstone-reclaim"
    assert tombstone["planDigest"] == plan["planDigest"]
    assert tombstone["quarantineRef"] == receipt["quarantined"][0]["quarantineRef"]
    assert tombstone["merkleRoot"] == receipt["quarantined"][0]["merkleRoot"]
    # Nothing referenced this execution — that is exactly why it was collectable,
    # and recording the empty set is what separates an authorized reclaim from a
    # backfilled absence.
    assert tombstone["referencedBy"] == []

    replay, _ = apply_canonical_gc(
        plan_id="gc-tombstone-reclaim",
        plan_digest=str(plan["planDigest"]),
        output_root=output,
        publish_root=publish,
        release_root=release_root,
    )
    assert replay["idempotent"] is True


def test_a_tombstoned_execution_back_on_disk_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    revived = "20260801--travel-article-gc--cn--pilot-106"
    write_execution_tombstone(
        output_root=output,
        execution_id=revived,
        reason=ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
        reclaimed_at="2026-08-01T00:00:00+00:00",
        referenced_by=(
            {"ref": "data/releases/r/payload/release.json", "relation": "x"},
        ),
        backfill_id="gc-backfill-revived",
    )
    _task(output, revived)

    with pytest.raises(ObjectTransactionError, match="RECLAIMED_EXECUTION_REVIVED"):
        plan_canonical_gc(
            plan_id="gc-tombstone-revived",
            output_root=output,
            publish_root=publish,
            release_root=release_root,
            min_age_hours=0,
        )


def test_never_materialized_and_reclaimed_are_not_merged_into_one_absence(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    release_root = output / "data/releases"
    contested = "20260801--travel-article-gc--cn--pilot-107"
    _release(release_root, "release-history", [contested])
    _write_json(
        output
        / "data/local/workspace/content-campaign-submissions"
        / "campaign-one/reconciliation/receipt.json",
        {
            "schema": "quwoquan_data.campaign_reconciliation",
            "executionEvidence": [
                {"executionId": contested, "executionRootExists": False}
            ],
        },
    )
    write_execution_tombstone(
        output_root=output,
        execution_id=contested,
        reason=ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
        reclaimed_at="2026-08-01T00:00:00+00:00",
        referenced_by=(
            {
                "ref": "data/releases/release-history/payload/release.json",
                "relation": "immutable_release_reference",
            },
        ),
        backfill_id="gc-backfill-contested",
    )

    with pytest.raises(
        ObjectTransactionError,
        match="EXECUTION_ABSENCE_CONTRADICTION",
    ):
        plan_canonical_gc(
            plan_id="gc-tombstone-contested",
            output_root=output,
            publish_root=publish,
            release_root=release_root,
            min_age_hours=0,
        )


def test_a_tombstone_stating_a_different_conclusion_is_rejected(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    execution_id = "20260801--travel-article-gc--cn--pilot-108"
    referrer = (
        {"ref": "data/releases/r/payload/release.json", "relation": "release"},
    )
    write_execution_tombstone(
        output_root=output,
        execution_id=execution_id,
        reason=ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
        reclaimed_at="2026-08-01T00:00:00+00:00",
        referenced_by=referrer,
        backfill_id="gc-backfill-first",
    )

    _document, _path, created = write_execution_tombstone(
        output_root=output,
        execution_id=execution_id,
        reason=ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
        reclaimed_at="2026-08-02T00:00:00+00:00",
        referenced_by=referrer,
        backfill_id="gc-backfill-first",
    )
    # Only the observation instant differs, so the replay is the same conclusion.
    assert created is False

    with pytest.raises(
        ObjectTransactionError,
        match="EXECUTION_TOMBSTONE_CONFLICT",
    ):
        write_execution_tombstone(
            output_root=output,
            execution_id=execution_id,
            reason=ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
            reclaimed_at="2026-08-01T00:00:00+00:00",
            referenced_by=referrer,
            backfill_id="gc-backfill-different",
        )
