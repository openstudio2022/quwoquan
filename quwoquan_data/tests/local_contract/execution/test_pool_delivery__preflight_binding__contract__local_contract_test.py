"""Pool delivery preserves reviewed truth across transport outages.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.preflight import pool_delivery as delivery_preflight
from content.execution.queue.reliabletask.transport import ReliableTaskFleetTransport
from support.pool_delivery_fixture import EXECUTION_ID, _DIGEST, _write_json


def _backend_envelope() -> dict[str, object]:
    return {
        "poolDeliveryBackend": "reliabletask",
        "envelopeDigest": _DIGEST,
        "scaleClass": "M100_PLUS",
    }


def _transport() -> ReliableTaskFleetTransport:
    return ReliableTaskFleetTransport(
        target="data-local",
        mongo_uri="mongodb://127.0.0.1:18440/?directConnection=true",
        redis_addr="127.0.0.1:18450",
    )


def _runtime_binding():
    campaign = {
        "rootExecutionId": EXECUTION_ID,
        "campaignRunId": "campaign-pool-delivery-001",
        "campaignGeneration": 3,
        "campaignFencingToken": "sha256:" + "b" * 64,
        "campaignPlanDigest": "sha256:" + "d" * 64,
        "campaignSourceRevision": "sha256:" + "e" * 64,
        "campaignSourceDigest": "sha256:" + "f" * 64,
        "campaignEntityCatalogDigest": "sha256:" + "1" * 64,
    }
    return (
        {
            "observerBinaryRef": "data/local/cache/worker/data-content-worker",
            "observerBinarySha256": "sha256:" + "c" * 64,
        },
        3,
        "sha256:" + "b" * 64,
        campaign,
        _transport(),
    )


def test_pool_delivery_preflight__standalone_m100_dispatch_uses_exact_pool_fence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen_selection = {
        "carrier": "article",
        "candidateIds": ["article-1"],
        "candidateCount": 1,
    }
    frozen_selection["selectionDigest"] = delivery_preflight._digest(
        frozen_selection
    )
    request = {
        "scaleSourcePool": {
            "sourceDigest": "sha256:" + "9" * 64,
            "entityCatalogDigest": "sha256:" + "2" * 64,
            "planRef": "data/local/workspace/source-acquisition/pool.json",
            "planDigest": "sha256:" + "3" * 64,
            "planFileSha256": "sha256:" + "4" * 64,
        },
        "sourcePoolEvidenceRootRef": "data/local/workspace/source-acquisition",
        "sourcePoolSelection": frozen_selection,
    }
    plan = tmp_path / "0.plan"
    plan.mkdir(parents=True)
    (plan / "request.json").write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(
        delivery_preflight,
        "execution_external_input_envelope_path",
        lambda _root: tmp_path / "missing-external-input.json",
    )
    monkeypatch.setattr(delivery_preflight, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_execution_manifest",
        lambda _execution_id: {
            "sourceDigest": {"digest": "sha256:" + "1" * 64},
            "executionBundle": {"digest": "sha256:" + "6" * 64},
        },
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_target_set",
        lambda _execution_id: {"entityCatalogDigest": "sha256:" + "2" * 64},
    )
    binding = SimpleNamespace(
        as_document=lambda: {
            "observerBinaryRef": "data/local/cache/worker/data-content-worker",
            "observerBinarySha256": "sha256:" + "7" * 64,
        }
    )
    monkeypatch.setattr(
        delivery_preflight,
        "prepare_controller_observer_binary",
        lambda: SimpleNamespace(binding=binding),
    )
    validated: list[tuple[object, str]] = []
    monkeypatch.setattr(
        "content.execution.campaign.source_pool_binding.validate_bound_scale_source_pool",
        lambda pool, *, evidence_root_ref, output_root: (
            validated.append((pool, evidence_root_ref))
            or {
                "candidates": [
                    {"carrier": "article", "candidateId": "article-1"}
                ]
            }
        ),
    )

    worker, generation, token, campaign, fleet = (
        delivery_preflight._delivery_runtime_binding(
            EXECUTION_ID,
            {
                "scaleClass": "M100_PLUS",
                "envelopeDigest": "sha256:" + "8" * 64,
            },
        )
    )

    assert worker["observerBinarySha256"] == "sha256:" + "7" * 64
    assert generation == 1
    assert token == "sha256:" + "8" * 64
    assert campaign is None
    assert fleet is None
    assert validated == [
        (request["scaleSourcePool"], "data/local/workspace/source-acquisition")
    ]




def test_pool_delivery_preflight__binds_transport_generation_fence_and_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_queue_backend",
        lambda _execution_id: _backend_envelope(),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "_delivery_runtime_binding",
        lambda *_args: _runtime_binding(),
    )
    report = delivery_preflight.build_pool_delivery_preflight_report(
        EXECUTION_ID,
        transport_resolver=_transport,
        fleet_probe=lambda: {
            "target": "data-local",
            "ready": True,
            "mongo": True,
            "redis": True,
            "owned": True,
        },
    )
    receipt = delivery_preflight.build_pool_delivery_preflight_receipt(report)

    assert report["preflightProfile"] == "pool-delivery"
    assert report["poolDeliveryReady"] is True
    assert "semanticExecutionReady" not in receipt
    assert "provider" not in receipt
    delivery_preflight.validate_pool_delivery_preflight_receipt(
        receipt,
        expected_execution_id=EXECUTION_ID,
        minimum_generation=3,
        expected_fencing_token="sha256:" + "b" * 64,
    )
    with pytest.raises(ValueError, match="generation is stale"):
        delivery_preflight.validate_pool_delivery_preflight_receipt(
            receipt,
            minimum_generation=4,
        )
    with pytest.raises(ValueError, match="fencing token is stale"):
        delivery_preflight.validate_pool_delivery_preflight_receipt(
            receipt,
            expected_fencing_token="sha256:" + "d" * 64,
        )


def test_pool_delivery_preflight__transport_down_is_delivery_pending_not_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_queue_backend",
        lambda _execution_id: _backend_envelope(),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "_delivery_runtime_binding",
        lambda *_args: _runtime_binding(),
    )
    report = delivery_preflight.build_pool_delivery_preflight_report(
        EXECUTION_ID,
        transport_resolver=_transport,
        fleet_probe=lambda: {
            "target": "data-local",
            "ready": False,
            "mongo": False,
            "redis": True,
            "owned": True,
        },
    )

    assert report["poolDeliveryReady"] is False
    assert report["issueCode"] == "DATA.POOL.DELIVERY_UNAVAILABLE"
    with pytest.raises(ValueError, match="requires ready evidence"):
        delivery_preflight.build_pool_delivery_preflight_receipt(report)




def test_m100_pool_delivery_preflight__missing_worker_context_is_typed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_queue_backend",
        lambda _execution_id: _backend_envelope(),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "_delivery_runtime_binding",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("observer unavailable")),
    )

    report = delivery_preflight.build_pool_delivery_preflight_report(EXECUTION_ID)

    assert report["poolDeliveryReady"] is False
    assert report["issueCode"] == "DATA.POOL.DELIVERY_UNAVAILABLE"
    assert "workerRef" not in report



def test_pool_delivery_preflight_recovers_frozen_campaign_fence_without_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QWQ_CAMPAIGN_ROOT_EXECUTION_ID", raising=False)
    root_execution_id = (
        "20260811--travel-homepage-m100--china--scale-205"
    )
    execution_root = tmp_path / "execution"
    envelope_path = execution_root / "0.plan/campaign_external_input_envelope.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text("{}", encoding="utf-8")
    stable_plan = {
        "rootExecutionId": root_execution_id,
        "executionIds": {"article": EXECUTION_ID},
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "distributedRun": {
            "campaignRunId": "campaign-run-001",
            "campaignGeneration": 4,
            "campaignFencingToken": "sha256:" + "4" * 64,
        },
    }
    plan = {
        **stable_plan,
        "planDigest": delivery_preflight.sha256_payload(stable_plan),
    }
    campaigns_root = tmp_path / "campaigns"
    plan_path = campaigns_root / root_execution_id / "campaign_plan.json"
    _write_json(plan_path, plan)
    external = {
        "rootExecutionId": root_execution_id,
        "executionId": EXECUTION_ID,
        "carrier": "article",
        "planDigest": plan["planDigest"],
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    worker = {
        "observerBinaryRef": "data/local/cache/worker/data-content-worker",
        "observerBinarySha256": "sha256:" + "5" * 64,
    }
    transport = _transport()

    monkeypatch.setattr(delivery_preflight, "execution_root", lambda _id: execution_root)
    monkeypatch.setattr(
        delivery_preflight,
        "execution_external_input_envelope_path",
        lambda _root: envelope_path,
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_execution_external_input_envelope",
        lambda _path: external,
    )
    monkeypatch.setattr(
        delivery_preflight.CampaignRuntimePaths,
        "defaults",
        lambda: SimpleNamespace(campaigns_root=campaigns_root),
    )
    monkeypatch.setattr(delivery_preflight, "assert_valid", lambda *_a, **_k: None)
    monkeypatch.setattr(
        delivery_preflight,
        "read_runtime_snapshot",
        lambda *_a: {
            "rootExecutionId": root_execution_id,
            "planDigest": plan["planDigest"],
            "runId": "campaign-run-001",
            "generation": 4,
            "fencingToken": "sha256:" + "4" * 64,
        },
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_execution_manifest",
        lambda _id: {"sourceDigest": {"digest": plan["sourceDigest"]}},
    )
    monkeypatch.setattr(
        delivery_preflight,
        "load_frozen_target_set",
        lambda _id: {"entityCatalogDigest": plan["entityCatalogDigest"]},
    )
    monkeypatch.setattr(
        delivery_preflight,
        "resolve_campaign_observer_binary",
        lambda *_a, **_k: SimpleNamespace(as_document=lambda: worker),
    )
    monkeypatch.setattr(
        delivery_preflight,
        "resolve_campaign_fleet_transport",
        lambda *_a, **_k: SimpleNamespace(transport=transport),
    )

    recovered_worker, generation, fence, campaign, recovered_transport = (
        delivery_preflight._delivery_runtime_binding(
            EXECUTION_ID,
            _backend_envelope(),
        )
    )

    assert recovered_worker == worker
    assert generation == 4
    assert fence == "sha256:" + "4" * 64
    assert campaign["rootExecutionId"] == root_execution_id
    assert recovered_transport == transport
