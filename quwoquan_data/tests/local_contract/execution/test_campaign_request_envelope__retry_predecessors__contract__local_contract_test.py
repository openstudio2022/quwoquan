"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

from pathlib import Path

import content.execution.planning.request_envelope as envelopes
import pytest
from content.execution.source_pool.external_inputs import content_source_revision
from core.source_digest import SourceDefinitionSnapshot
from core.io import read_json, write_json
from support.campaign_request_envelope_fixture import (
    _expected_count,
    _patch_envelope_deps,
    _promotion_output_root,
    _research_m100_receipt,
)
from support.semantic_preflight_fixture import (
    ready_semantic_preflight,
    write_typed_cursor_grok_failure,
)


def test_campaign_retry_envelope_requires_one_matching_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    predecessor = (
        "20260805--travel-image-workload-image-3--china--scale-001"
    )

    with pytest.raises(ValueError, match="sequence=1 forbids"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            repo_root=repo,
            day="20260805",
            predecessor_execution_id=predecessor,
        )
    rolling = envelopes.build_envelope(
        scale="M3",
        carrier="image",
        repo_root=repo,
        day="20260805",
        sequence=2,
    )
    assert rolling["retryOf"] is None

    retry = envelopes.build_envelope(
        scale="M3",
        carrier="image",
        repo_root=repo,
        day="20260805",
        sequence=2,
        predecessor_execution_id=predecessor,
    )

    assert retry["retryOf"] == predecessor
    assert retry["quota"] == 3
    assert retry["count"] == _expected_count(3)
    assert retry["semanticSelectionId"] == "default"
    assert retry["executionId"] == (
        "20260805--travel-image-workload-image-3--china--scale-002"
    )
    assert retry["rootExecutionId"] == (
        "20260805--travel-image-workload-image-3--china--scale-002"
    )
    preflight_root = tmp_path / "semantic-output"
    write_typed_cursor_grok_failure(predecessor, output_root=preflight_root)
    preflight_path, _preflight_binding = ready_semantic_preflight(
        "cursor_auto",
        output_root=preflight_root,
    )
    cursor_retry = envelopes.build_envelope(
        scale="M3",
        carrier="image",
        repo_root=repo,
        day="20260805",
        sequence=2,
        predecessor_execution_id=predecessor,
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
    )
    assert cursor_retry["semanticSelectionId"] == "cursor_auto"
    assert cursor_retry["semanticPreflightReceipt"] == _preflight_binding
    with pytest.raises(ValueError, match="CURSOR_AUTO_RETRY_REQUIRED"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            repo_root=repo,
            day="20260805",
            semantic_selection_id="cursor_auto",
            semantic_preflight_receipt=preflight_path,
            semantic_preflight_output_root=preflight_root,
        )
    with pytest.raises(ValueError, match="preserve execution scope"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            repo_root=repo,
            day="20260805",
            sequence=2,
            predecessor_execution_id=(
                "20260805--travel-video-workload-video-3--china--scale-001"
            ),
        )
    subset_predecessor = (
        "20260805--travel-image-"
        "workload-homepage-3-article-3-image-3-video-3--china--scale-001"
    )
    with pytest.raises(ValueError, match="preserve execution scope"):
        envelopes.build_envelope(
            scale="M1",
            carrier="image",
            repo_root=repo,
            day="20260805",
            sequence=2,
            predecessor_execution_id=subset_predecessor,
        )
    subset_retry = envelopes.build_envelope(
        scale="M1",
        carrier="image",
        repo_root=repo,
        day="20260805",
        sequence=2,
        predecessor_execution_id=subset_predecessor,
        allow_retry_intent_change=True,
    )
    assert subset_retry["retryOf"] == subset_predecessor
    assert subset_retry["executionId"] == (
        "20260805--travel-image-workload-image-1--china--scale-002"
    )


def test_campaign_retry_write_requires_all_active_predecessors_and_separate_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    intent = "workload-homepage-3-article-3-image-3-video-3"
    predecessors = {
        carrier: f"20260805--travel-{carrier}-{intent}--china--scale-001"
        for carrier in ("homepage", "article", "image", "video")
    }

    with pytest.raises(ValueError, match="exactly match active carriers"):
        envelopes.write_scale_envelopes(
            "M3",
            repo_root=repo,
            output_root=tmp_path,
            day="20260805",
            sequence=2,
            predecessor_execution_ids_by_carrier={
                "homepage": predecessors["homepage"]
            },
        )
    with pytest.raises(ValueError, match="sequence=1 forbids"):
        envelopes.write_scale_envelopes(
            "M3",
            repo_root=repo,
            output_root=tmp_path,
            day="20260805",
            predecessor_execution_ids_by_carrier=predecessors,
        )

    first = envelopes.write_scale_envelopes(
        "M3",
        repo_root=repo,
        output_root=tmp_path,
        day="20260805",
        sequence=2,
        predecessor_execution_ids_by_carrier=predecessors,
    )
    second = envelopes.write_scale_envelopes(
        "M3",
        repo_root=repo,
        output_root=tmp_path,
        day="20260805",
        sequence=2,
        predecessor_execution_ids_by_carrier=predecessors,
    )

    assert second == first
    for carrier, path in first.items():
        assert f"travel/M3/china/sequence-002/{carrier}.json" in path.as_posix()
        payload = envelopes.load_campaign_envelope(path)
        assert payload["retryOf"] == predecessors[carrier]
        assert payload["executionId"].endswith("--scale-002")
        assert payload["rootExecutionId"].endswith("--scale-002")


def test_campaign_retry_envelopes_bind_submission_reconciliation_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    receipt_path = tmp_path / "submission-only-abandonment.json"
    active_carriers = ("homepage", "article", "image", "video")
    workloads = {carrier: 3 for carrier in active_carriers}
    intent = "workload-homepage-3-article-3-image-3-video-3"
    predecessors = {
        carrier: f"20260805--travel-{carrier}-{intent}--china--scale-001"
        for carrier in active_carriers
    }
    receipt = {
        "rootExecutionId": predecessors["homepage"],
        "activeCarriers": list(active_carriers),
        "workloads": workloads,
        "reason": "source_drift",
        "originalSourceIdentity": {
            "sourceRevision": content_source_revision(
                source_digest="sha256:" + "d" * 64,
                entity_catalog_digest="sha256:" + "b" * 64,
            ),
            "sourceDigest": SourceDefinitionSnapshot(
                digest="sha256:" + "d" * 64
            ).to_document(),
            "entityCatalogDigest": "sha256:" + "b" * 64,
        },
        "observedSourceIdentity": {
            "sourceRevision": content_source_revision(
                source_digest="sha256:" + "c" * 64,
                entity_catalog_digest="sha256:" + "b" * 64,
            ),
            "sourceDigest": SourceDefinitionSnapshot(
                digest="sha256:" + "c" * 64
            ).to_document(),
            "entityCatalogDigest": "sha256:" + "b" * 64,
        },
        "submissions": {
            carrier: {
                "executionId": execution_id,
                "targetNames": ["乌镇", "成都大熊猫繁育研究基地", "西湖"],
            }
            for carrier, execution_id in predecessors.items()
        },
        "receiptDigest": "sha256:" + "c" * 64,
    }
    monkeypatch.setattr(
        envelopes,
        "load_submission_reconciliation_receipt",
        lambda *_args, **_kwargs: receipt,
    )
    monkeypatch.setattr(
        envelopes,
        "reconciliation_reference",
        lambda *_args, **_kwargs: {
            "predecessorRootExecutionId": predecessors["homepage"],
            "receiptRef": "data/local/reconciliation/submission-only.json",
            "receiptDigest": "sha256:" + "c" * 64,
        },
    )

    paths = envelopes.write_scale_envelopes(
        "M3",
        repo_root=repo,
        output_root=tmp_path / "envelopes",
        day="20260805",
        sequence=2,
        predecessor_reconciliation_receipt=receipt_path,
    )

    for carrier, path in paths.items():
        payload = envelopes.load_campaign_envelope(path)
        assert payload["retryOf"] == predecessors[carrier]
        assert payload["targetNames"] == [
            "乌镇",
            "成都大熊猫繁育研究基地",
            "西湖",
        ]
        assert payload["predecessorReconciliation"]["receiptDigest"] == (
            "sha256:" + "c" * 64
        )

    with pytest.raises(ValueError, match="targetNames differ"):
        envelopes.write_scale_envelopes(
            "M3",
            target_names=["另一个目标"],
            repo_root=repo,
            output_root=tmp_path / "drifted-envelopes",
            day="20260805",
            sequence=2,
            predecessor_reconciliation_receipt=receipt_path,
        )

    current_identity = {
        "sourceRevision": content_source_revision(
            source_digest="sha256:" + "a" * 64,
            entity_catalog_digest="sha256:" + "b" * 64,
        ),
        "sourceDigest": SourceDefinitionSnapshot(
            digest="sha256:" + "a" * 64
        ).to_document(),
        "entityCatalogDigest": "sha256:" + "b" * 64,
    }
    receipt["originalSourceIdentity"] = current_identity
    with pytest.raises(ValueError, match="did not leave the reconciled source"):
        envelopes.write_scale_envelopes(
            "M3",
            repo_root=repo,
            output_root=tmp_path / "original-source-envelopes",
            day="20260805",
            sequence=2,
            predecessor_reconciliation_receipt=receipt_path,
        )


def test_predecessor_loader_rejects_noncanonical_path_and_count_arithmetic(
    tmp_path: Path,
) -> None:
    approved = _research_m100_receipt(tmp_path / "canonical")
    document = read_json(approved)
    identity = {
        "next_scale": "M1000",
        "source_digest": {"digest": document["sourceDigest"]},
        "entity_catalog_digest": document["entityCatalogDigest"],
        "source_revision": document["sourceRevision"],
    }

    noncanonical = tmp_path / "research-m100.json"
    write_json(noncanonical, document)
    with pytest.raises(ValueError, match="canonical promotion path"):
        envelopes._research_scale_promotion_ref(
            noncanonical,
            output_root=tmp_path,
            **identity,
        )

    document["carrierCounts"][0]["predecessorCarriedCount"] = 1
    write_json(approved, document)
    with pytest.raises(ValueError, match="DATA.SCALE.ATTAINMENT_SHORTFALL"):
        envelopes._research_scale_promotion_ref(
            approved,
            output_root=_promotion_output_root(approved),
            **identity,
        )
