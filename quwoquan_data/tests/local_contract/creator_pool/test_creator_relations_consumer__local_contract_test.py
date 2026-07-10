"""Contract: the creator_relations seed is consumable (follow + circle edges readable).

Covers Phase 2 of the no-breakpoint E2E closure: the previously-orphaned
``creator_relations.travel_photo_1k_v1.seed.json`` now has a single consumer that validates and
projects follow-graph + circle-membership injections.
"""
from __future__ import annotations

from _common.creator_pool.batch_policy import default_target_for_batch
from governance.creator_pool.relations import build_relation_injections, load_relation_injections

CANONICAL_BATCH = "travel_photo_1k_v1"
CANONICAL_TARGET = default_target_for_batch(CANONICAL_BATCH)


def test_canonical_relations_seed_is_consumable() -> None:
    injections = load_relation_injections(vertical="travel")
    assert injections.ok, injections.issues
    assert injections.batch_id == CANONICAL_BATCH
    # Canonical 1200 creators form a single follow chain -> target-1 edges; each
    # creator may now join multiple vertical/topic circles after the profile metadata expansion.
    assert injections.follow_edge_count == CANONICAL_TARGET - 1
    assert injections.circle_member_count >= CANONICAL_TARGET
    assert injections.entity_affinity_count >= CANONICAL_TARGET
    assert injections.circle_affinity_count >= CANONICAL_TARGET


def test_follow_edges_readable_after_seed() -> None:
    injections = load_relation_injections(vertical="travel")
    follower = "sys_photo_0002_sub_01"
    followee = "sys_photo_0001_sub_01"
    assert followee in injections.following_of(follower)
    assert follower in injections.followers_of(followee)
    # Seed user 001 is followed but follows no one (chain head).
    assert injections.following_of(followee) == []


def test_every_edge_references_seeded_creator() -> None:
    injections = load_relation_injections(vertical="travel")
    seeded = {sub for pair in injections.follow_edges for sub in pair}
    for members in injections.circle_memberships.values():
        seeded.update(members)
    assert all(s.startswith(("sys_travel_", "sys_photo_", "sys_travelphoto_")) and s.endswith("_sub_01") for s in seeded)


def test_consumer_flags_unseeded_and_selffollow_edges() -> None:
    seed_users = [
        {"subAccountId": "sys_photo_0001_sub_01", "cohortId": CANONICAL_BATCH},
        {"subAccountId": "sys_photo_0002_sub_01", "cohortId": CANONICAL_BATCH},
    ]
    bad_seed = {
        "batchId": CANONICAL_BATCH,
        "edges": [
            {"kind": "FollowEdge", "fromSubAccountId": "ghost", "toSubAccountId": "sys_photo_0001_sub_01"},
            {"kind": "FollowEdge", "fromSubAccountId": "sys_photo_0002_sub_01", "toSubAccountId": "sys_photo_0002_sub_01"},
            {"kind": "CircleMember", "subAccountId": "ghost", "circleId": "c1"},
        ],
    }
    injections = build_relation_injections(bad_seed, seed_users)
    assert not injections.ok
    assert any("not a seeded creator" in i for i in injections.issues)
    assert any("self-follow" in i for i in injections.issues)


def test_consumer_flags_batch_mismatch() -> None:
    seed_users = [{"subAccountId": "x", "cohortId": CANONICAL_BATCH}]
    bad_seed = {"batchId": "some_other_batch", "edges": [{"kind": "CircleMember", "subAccountId": "x", "circleId": "c1"}]}
    injections = build_relation_injections(bad_seed, seed_users)
    assert any("not in seeded cohortIds" in i for i in injections.issues)
