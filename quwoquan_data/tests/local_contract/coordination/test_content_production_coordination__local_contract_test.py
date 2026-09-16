"""具名分片 SQLite 协作的本地契约。

spec_ref: 用户冻结的具名分片最小协作契约（2026-09-13）
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.coordination import ConflictError, CoordinationError, CoordinationStore, ROLE_NAMES  # noqa: E402

EXPECTED_ROLES = (
    "director", "homepage_creator", "article_creator", "image_creator",
    "video_creator", "qa", "computer_steward",
)


def _store(tmp_path: Path, *, shards: int = 1) -> CoordinationStore:
    store = CoordinationStore(tmp_path / "coordination.sqlite", timeout=20)
    store.register_iteration("i1", "approval://iteration/i1")
    store.register_deployment("i1", "d1", {role: [__import__("json").dumps(["cursor", f"team-{role}", f"run-{role}"])] for role in ROLE_NAMES})
    for index in range(shards):
        store.register_shard("i1", f"shard-{index + 1}", f"名称{index + 1}", f"scope://s{index + 1}", index, [f"target://{index + 1}"])
    return store


def test_role_positions_are_exact_and_single_value_legacy_is_rejected(tmp_path: Path) -> None:
    assert ROLE_NAMES == EXPECTED_ROLES
    store = CoordinationStore(tmp_path / "db.sqlite")
    store.register_iteration("i1", "approval://i1")
    with pytest.raises(CoordinationError) as invalid:
        store.register_deployment("i1", "bad", {"director": "team"})
    assert invalid.value.code == "COORDINATION.INVALID_ROLE_BINDINGS"


def test_ten_threads_compete_for_one_shard_with_cas_exclusion(tmp_path: Path) -> None:
    store = _store(tmp_path)

    def attempt(index: int):
        try:
            return store.claim("i1", f"team-{index}", f"claim-{index}")
        except CoordinationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(10)))
    winners = [result for result in results if isinstance(result, dict)]
    assert len(winners) == 1
    assert results.count("COORDINATION.NO_SHARD_AVAILABLE") == 9
    assert winners[0]["shard_id"] == "shard-1" and winners[0]["name"] == "名称1"
    assert store.status("i1")["shards"][0]["claim"]["team"] == winners[0]["team"]


def test_same_team_retry_and_lost_response_are_idempotent_and_one_team_has_one_shard(tmp_path: Path) -> None:
    store = _store(tmp_path, shards=2)
    first = store.claim("i1", "alpha", "request-1")
    assert store.claim("i1", "alpha", "request-1") == first
    assert store.claim("i1", "alpha", "request-after-lost-response") == first
    assert {"shard_id", "name"} <= first.keys()
    assert store.status("i1")["shards"][1]["state"] == "available"


def test_fixed_order_named_authorization_no_shard_and_target_occupancy(tmp_path: Path) -> None:
    store = CoordinationStore(tmp_path / "db.sqlite")
    store.register_iteration("i1", "approval://i1")
    store.register_shard("i1", "later-id", "later", "scope://later", 2, ["target://shared"])
    store.register_shard("i1", "named-id", "named", "scope://named", 1, ["target://named"], authorized_team="special")
    store.register_shard("i1", "first-id", "first", "scope://first", 0, ["target://shared"])
    assert store.claim("i1", "ordinary", "c1")["shard_id"] == "first-id"
    assert store.claim("i1", "special", "c2", shard_id="named-id")["name"] == "named"
    with pytest.raises(ConflictError) as no_shard:
        store.claim("i1", "third", "c3")
    assert no_shard.value.code == "COORDINATION.TARGET_OCCUPIED"
    with pytest.raises(ConflictError) as unauthorized:
        store.claim("i1", "ordinary-2", "c4", shard_id="named-id")
    assert unauthorized.value.code == "COORDINATION.NO_SHARD_AVAILABLE"


def test_release_requires_handoff_rejects_old_generation_and_sets_available_or_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.claim("i1", "alpha", "c1")
    with pytest.raises(CoordinationError) as missing:
        store.release("i1", "shard-1", "alpha", first["generation"], "r0", handoff_ref="", remaining=True)
    assert missing.value.code == "COORDINATION.HANDOFF_REQUIRED"
    store.begin_drain("i1", "shard-1", "alpha", first["generation"], "d1")
    available = store.release("i1", "shard-1", "alpha", first["generation"], "r1", handoff_ref="handoff://1", remaining=True)
    assert available["state"] == "available"
    assert store.release("i1", "shard-1", "alpha", first["generation"], "r1", handoff_ref="handoff://1", remaining=True) == available
    second = store.claim("i1", "beta", "c2")
    assert second["generation"] == first["generation"] + 1
    with pytest.raises(ConflictError) as stale:
        store.release("i1", "shard-1", "alpha", first["generation"], "r-old", handoff_ref="handoff://old", remaining=False)
    assert stale.value.code == "COORDINATION.STALE_CLAIM"
    closed = store.release("i1", "shard-1", "beta", second["generation"], "r2", handoff_ref="handoff://2", remaining=False)
    assert closed["state"] == "closed"


def test_disconnect_never_auto_releases_and_recovery_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "coordination.sqlite"
    _store(tmp_path).claim("i1", "alpha", "c1")
    reopened = CoordinationStore(path)
    assert reopened.claim("i1", "alpha", "retry")["team"] == "alpha"
    with pytest.raises(ConflictError) as occupied:
        reopened.claim("i1", "beta", "c2")
    assert occupied.value.code == "COORDINATION.NO_SHARD_AVAILABLE"
    claim = reopened.status("i1")["shards"][0]["claim"]
    reopened.block("i1", "shard-1", "alpha", claim["generation"], "b1", fact_ref="incident://lost")
    recovered = reopened.recover("i1", "shard-1", "alpha", claim["generation"], "m1", recovery_ref="recovery://human-1")
    assert recovered["state"] == "claimed"


def test_rename_keeps_stable_identity_claim_and_historical_snapshots(tmp_path: Path) -> None:
    store = _store(tmp_path, shards=2)
    claim = store.claim("i1", "alpha", "c1", shard_id="shard-1")
    claim_id = claim["claim_id"]
    store.rename_shard("i1", "shard-1", "新名称", occurred_at="2026-09-02T00:00:00Z")
    status = store.status("i1")["shards"][0]
    assert status["shard_id"] == "shard-1" and status["name"] == "新名称"
    assert status["claim"]["claim_id"] == claim_id
    assert status["claim"]["shard_id"] == "shard-1" and status["claim"]["name"] == "新名称"
    released = store.release("i1", "shard-1", "alpha", claim["generation"], "r1", handoff_ref="handoff://1", remaining=False)
    assert released["shard_id"] == "shard-1" and released["name"] == "新名称"
    events = store.timeline("i1", shard_id="shard-1")
    registered = next(event for event in events if event["event_type"] == "shard.registered")
    acquired = next(event for event in events if event["event_type"] == "claim.acquired")
    renamed = next(event for event in events if event["event_type"] == "shard.renamed")
    assert {event["shard_id"] for event in events} == {"shard-1"}
    assert registered["shard_name_snapshot"] == acquired["shard_name_snapshot"] == "名称1"
    assert renamed["shard_name_snapshot"] == "新名称"


def test_empty_or_duplicate_shard_name_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path, shards=2)
    with pytest.raises(CoordinationError) as empty:
        store.rename_shard("i1", "shard-1", "   ")
    assert empty.value.code == "COORDINATION.INVALID_SHARD_NAME"
    with pytest.raises(ConflictError) as duplicate:
        store.rename_shard("i1", "shard-1", "名称2")
    assert duplicate.value.code == "COORDINATION.SHARD_NAME_CONFLICT"
    with pytest.raises(CoordinationError):
        store.register_shard("i1", "shard-3", "", "scope://3", 3, ["target://3"])


def test_checkpoint_is_external_fact_idempotent_drift_safe_and_filterable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    checkpoint = store.append_checkpoint(
        "i1", fact_ref="fact://producer/1", fact_digest="sha256:aaa", source_type="producer-receipt",
        occurred_at=None, payload={"stage": "author"}, shard_id="shard-1", deployment_id="d1",
    )
    assert checkpoint["occurred_at"] is None and checkpoint["payload"] == {"stage": "author"}
    assert checkpoint["shard_id"] == "shard-1" and checkpoint["deployment_id"] == "d1"
    assert store.append_checkpoint(
        "i1", fact_ref="fact://producer/1", fact_digest="sha256:aaa", source_type="producer-receipt",
        occurred_at="ignored-on-replay", payload={"other": "ignored"}, shard_id="shard-1", deployment_id="d1",
    ) == checkpoint
    with pytest.raises(ConflictError) as drift:
        store.append_checkpoint("i1", fact_ref="fact://producer/1", fact_digest="sha256:bbb", source_type="producer-receipt", shard_id="shard-1", deployment_id="d1")
    assert drift.value.code == "COORDINATION.CHECKPOINT_FACT_DRIFT"
    with pytest.raises(CoordinationError) as authority:
        store.append_checkpoint("i1", fact_ref="fact://producer/2", fact_digest="sha256:ccc", source_type="producer-receipt", payload={"completed": True})
    assert authority.value.code == "COORDINATION.COMPLETION_AUTHORITY_FORBIDDEN"
    store.append_checkpoint("i1", fact_ref="fact://global/1", fact_digest="sha256:ddd", source_type="director", payload={})
    assert [event["fact_ref"] for event in store.timeline("i1", shard_id="shard-1") if event["event_type"] == "checkpoint.appended"] == ["fact://producer/1"]
    assert [event["fact_ref"] for event in store.timeline("i1", deployment_id="d1") if event["event_type"] == "checkpoint.appended"] == ["fact://producer/1"]
    assert len(store.timeline("i1")) > len(store.timeline("i1", deployment_id="d1"))


def test_multi_instance_deployment_requires_complete_binding_and_resource_reservation(tmp_path: Path) -> None:
    store = CoordinationStore(tmp_path / "db.sqlite")
    store.register_iteration("i1", "approval://i1")
    roles = {role: [__import__("json").dumps(["cursor", f"actor-{role}", f"run-{role}"])] for role in ROLE_NAMES}
    with pytest.raises(CoordinationError) as incomplete:
        store.register_deployment("i1", "d1", roles, instance_id="instance-a")
    assert incomplete.value.code == "COORDINATION.DEPLOYMENT_BINDING_INCOMPLETE"
    store.register_deployment(
        "i1", "d1", roles, instance_id="instance-a",
        account_identity_ref="account://a", resource_reservation_ref="budget://a",
    )
    store.register_shard("i1", "s1", "一", "scope://1", 0, ["target://1"])
    store.register_shard("i1", "s2", "二", "scope://2", 1, ["target://2"])
    first = store.claim("i1", "team-a", "c1", deployment_id="d1")
    assert first["deployment_id"] == "d1"
    with pytest.raises(ConflictError) as duplicate:
        store.claim("i1", "renamed-team", "c2", deployment_id="d1")
    assert duplicate.value.code == "COORDINATION.DEPLOYMENT_ALREADY_CLAIMED"


def test_legacy_deployment_without_reservation_cannot_claim_in_multi_instance_mode(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ConflictError) as missing:
        store.claim("i1", "team-a", "c1", deployment_id="d1")
    assert missing.value.code == "COORDINATION.RESOURCE_RESERVATION_REQUIRED"

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t13
def test_target_occupancy_is_global_across_iterations(tmp_path: Path) -> None:
    store=CoordinationStore(tmp_path/"db.sqlite")
    for iteration in ("i1","i2"):
        store.register_iteration(iteration,f"approval://{iteration}")
        store.register_shard(iteration,"s","s",f"scope://{iteration}",0,["entities/shared"])
    store.claim("i1","team-1","c1")
    with pytest.raises(ConflictError) as conflict:
        store.claim("i2","team-2","c2")
    assert conflict.value.code=="COORDINATION.TARGET_OCCUPIED"
