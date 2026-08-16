from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from content.execution.campaign.external_inputs import payload_digest
from content.release.canonical.garbage_collection import plan_canonical_gc
from content.release.canonical.garbage_collection_contract import (
    write_create_once_json,
)
from content.release.canonical.garbage_collection_reference_graph import (
    _capsule_tree_digest,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.paths import research_scale_promotions_root


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


def _capsule(output: Path, marker: str) -> Path:
    lane_digest = "sha256:" + "9" * 64
    stable = {
        "schema": "quwoquan_data.content_campaign_source_capsule",
        "format": "source-capsule-v2",
        "gitBranch": "codex/test-canonical-gc",
        "gitCommitSha": "1" * 40,
        "sourceRevision": "sha256:" + "2" * 64,
        "sourceDigest": "sha256:" + marker * 64,
        "entityCatalogDigest": "sha256:" + "4" * 64,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "6" * 64,
            "inputs": ["quwoquan_data/scripts/content"],
        },
        "roots": ["quwoquan_data"],
        "laneExternalInputs": {
            carrier: {
                "rootRef": f"external-inputs/{carrier}",
                "externalInputRefs": [],
                "externalInputsDigest": lane_digest,
            }
            for carrier in ("homepage", "article", "image", "video")
        },
        "externalInputsDigest": "sha256:" + "5" * 64,
    }
    digest = payload_digest(stable)
    stable["capsuleDigest"] = digest
    root = (
        output
        / "data/local/cache/content-campaign-workspaces/content-addressed-capsules"
        / digest.removeprefix("sha256:")
    )
    payload = root / "quwoquan_data/source.txt"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(marker, encoding="utf-8")
    stable["treeDigest"] = _capsule_tree_digest(root)
    _write_json(root / ".qwq_campaign_capsule.json", stable)
    return root


def test_gc_reference_graph_protects_referenced_capsule_and_collects_only_orphan(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    task = _task(
        output,
        "20260805--travel-image-gc-graph--cn--pilot-001",
    )
    referenced = _capsule(output, "a")
    orphan = _capsule(output, "b")
    _write_json(
        task / "_shared/campaign_checkpoint.json",
        {
            "capsuleRef": referenced.relative_to(output).as_posix(),
            "capsuleDigest": json.loads(
                (referenced / ".qwq_campaign_capsule.json").read_text(encoding="utf-8")
            )["capsuleDigest"],
        },
    )

    plan, _ = plan_canonical_gc(
        plan_id="gc-reference-capsules",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )

    candidates = {row["ref"]: row for row in plan["candidates"]}
    assert orphan.relative_to(output).as_posix() in candidates
    assert candidates[orphan.relative_to(output).as_posix()]["kind"] == "source_capsule"
    assert referenced.relative_to(output).as_posix() not in candidates
    protected = {
        row["ref"]: row["reasons"]
        for row in plan["referenceGraph"]["protectedArtifactRefs"]
    }
    assert protected[referenced.relative_to(output).as_posix()] == [
        "source_capsule_reference"
    ]


def test_gc_reference_graph_keeps_acquisition_cas_until_its_receipt_evidence_moves(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    acquisition = output / "data/local/workspace/source-acquisition"
    body = b"immutable-acquisition-object"
    digest = hashlib.sha256(body).hexdigest()
    cas = acquisition / "cas/sha256" / digest[:2] / f"{digest}.jpg"
    cas.parent.mkdir(parents=True, exist_ok=True)
    cas.write_bytes(body)
    evidence = acquisition / "evidence/orphan-receipt-evidence.json"
    _write_json(
        evidence,
        {"assetRef": cas.relative_to(output).as_posix()},
    )

    plan, _ = plan_canonical_gc(
        plan_id="gc-acquisition-cas",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )

    candidates = {row["ref"]: row for row in plan["candidates"]}
    assert evidence.relative_to(output).as_posix() in candidates
    assert candidates[evidence.relative_to(output).as_posix()]["pathType"] == "file"
    assert cas.relative_to(output).as_posix() not in candidates
    protected = {
        row["ref"]: row["reasons"]
        for row in plan["referenceGraph"]["protectedArtifactRefs"]
    }
    assert protected[cas.relative_to(output).as_posix()] == ["output_assetRef"]


def test_gc_reference_graph_protects_environment_promotion_recovery_and_reconciliation(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    execution_id = "20260805--travel-video-gc-graph--cn--pilot-002"
    task = _task(output, execution_id)
    _write_json(
        research_scale_promotions_root(output_root=output)
        / "release-one/m100/research-m100.json",
        {"executionIds": [execution_id]},
    )
    _write_json(
        output / "env/gamma/runs/data-release/release-one/run-one/readiness.json",
        {"executionIds": [execution_id]},
    )
    _write_json(
        output
        / "data/local/release-identity-recoveries/release-one/r1/provenance.json",
        {"executionIds": [execution_id]},
    )
    _write_json(
        output
        / "data/local/workspace/content-campaign-submissions/campaign-one/reconciliation/receipt.json",
        {"executionIds": [execution_id]},
    )
    _write_json(
        task / "_shared/reconciliation/stale-proof.json",
        {"executionId": execution_id, "decision": "interrupted"},
    )

    plan, _ = plan_canonical_gc(
        plan_id="gc-evidence-roots",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )

    protected = {
        row["executionId"]: set(row["reasons"]) for row in plan["protectedExecutions"]
    }
    assert {
        "promotion_evidence",
        "activation_readiness_evidence",
        "release_identity_recovery",
        "campaign_submission_reconciliation",
        "execution_reconciliation_evidence",
    } <= protected[execution_id]
    assert f"data/tasks/{execution_id}" not in {
        row["ref"] for row in plan["candidates"]
    }


def test_gc_reference_graph_fails_closed_on_missing_or_corrupt_reference(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    evidence = output / "env/alpha/runs/data-release/r1/v1/readiness.json"
    _write_json(
        evidence,
        {
            "resourceSoakEvidenceRef": (
                "data/local/workspace/source-acquisition/evidence/missing.json"
            )
        },
    )
    with pytest.raises(ObjectTransactionError, match="REFERENCE_MISSING"):
        plan_canonical_gc(
            plan_id="gc-missing-reference",
            output_root=output,
            publish_root=publish,
            min_age_hours=0,
        )

    evidence.unlink()
    corrupt = output / "data/local/workspace/source-acquisition/evidence/corrupt.json"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("{", encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="JSON"):
        plan_canonical_gc(
            plan_id="gc-corrupt-reference",
            output_root=output,
            publish_root=publish,
            min_age_hours=0,
        )


def test_gc_plan_recovers_empty_plan_directory_and_create_once_is_race_safe(
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    plan_dir = output / "data/local/workspace/gc/plans/gc-orphan-directory"
    plan_dir.mkdir(parents=True)
    plan, path = plan_canonical_gc(
        plan_id="gc-orphan-directory",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )
    assert path.is_file()
    assert plan["candidateCount"] == 0

    target = tmp_path / "create-once.json"
    document = {"schema": "gc-test", "digest": payload_digest({"value": 1})}
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _index: write_create_once_json(target, document),
                range(32),
            )
        )
    assert sum(results) == 1
    assert json.loads(target.read_text(encoding="utf-8")) == document


def test_gc_plan_space_is_linear_in_candidate_count(tmp_path: Path) -> None:
    output = tmp_path / ".qwq_output"
    publish = tmp_path / "publish"
    for index in range(200):
        _task(
            output,
            f"20260805--travel-image-gc-linear--cn--scale-{index + 1:03d}",
        )

    plan, path = plan_canonical_gc(
        plan_id="gc-linear-two-hundred",
        output_root=output,
        publish_root=publish,
        min_age_hours=0,
    )

    assert plan["candidateCount"] == 200
    assert plan["referenceGraph"]["nodeCount"] <= 3 * 200
    assert path.stat().st_size < 600_000
