"""Contract: the creator_relations seed is consumable (follow + circle edges readable).

Covers Phase 2 of the no-breakpoint E2E closure: the previously-orphaned
``creator_relations.seed.json`` now has a single consumer that validates and
projects follow-graph + circle-membership injections.
"""
from __future__ import annotations

from governance.creator_pool.relations import build_relation_injections, load_relation_injections

CANONICAL_CIRCLE = "fixture_circle_travel_travel_batch_100_v1"


def test_canonical_relations_seed_is_consumable() -> None:
    injections = load_relation_injections(vertical="travel")
    assert injections.ok, injections.issues
    assert injections.batch_id == "travel_batch_100_v1"
    # 100 creators chained -> 99 follow edges, 100 circle members.
    assert injections.follow_edge_count == 99
    assert injections.circle_member_count == 100
    assert injections.members_of(CANONICAL_CIRCLE) and len(injections.members_of(CANONICAL_CIRCLE)) == 100


def test_follow_edges_readable_after_seed() -> None:
    injections = load_relation_injections(vertical="travel")
    follower = "agent_sub_account_travel_travel_batch_100_v1_002"
    followee = "agent_sub_account_travel_travel_batch_100_v1_001"
    assert followee in injections.following_of(follower)
    assert follower in injections.followers_of(followee)
    # Seed user 001 is followed but follows no one (chain head).
    assert injections.following_of(followee) == []


def test_every_edge_references_seeded_creator() -> None:
    injections = load_relation_injections(vertical="travel")
    seeded = {sub for pair in injections.follow_edges for sub in pair}
    for members in injections.circle_memberships.values():
        seeded.update(members)
    assert all(s.startswith("agent_sub_account_travel_travel_batch_100_v1_") for s in seeded)


def test_consumer_flags_unseeded_and_selffollow_edges() -> None:
    seed_users = [
        {"subAccountId": "agent_sub_account_travel_travel_batch_100_v1_001", "cohortId": "travel_batch_100_v1"},
        {"subAccountId": "agent_sub_account_travel_travel_batch_100_v1_002", "cohortId": "travel_batch_100_v1"},
    ]
    bad_seed = {
        "batchId": "travel_batch_100_v1",
        "edges": [
            {"kind": "FollowEdge", "fromSubAccountId": "ghost", "toSubAccountId": "agent_sub_account_travel_travel_batch_100_v1_001"},
            {"kind": "FollowEdge", "fromSubAccountId": "agent_sub_account_travel_travel_batch_100_v1_002", "toSubAccountId": "agent_sub_account_travel_travel_batch_100_v1_002"},
            {"kind": "CircleMember", "subAccountId": "ghost", "circleId": "c1"},
        ],
    }
    injections = build_relation_injections(bad_seed, seed_users)
    assert not injections.ok
    assert any("not a seeded creator" in i for i in injections.issues)
    assert any("self-follow" in i for i in injections.issues)


def test_consumer_flags_batch_mismatch() -> None:
    seed_users = [{"subAccountId": "x", "cohortId": "travel_batch_100_v1"}]
    bad_seed = {"batchId": "some_other_batch", "edges": [{"kind": "CircleMember", "subAccountId": "x", "circleId": "c1"}]}
    injections = build_relation_injections(bad_seed, seed_users)
    assert any("not in seeded cohortIds" in i for i in injections.issues)
