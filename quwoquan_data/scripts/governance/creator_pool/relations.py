"""Creator pool relations consumer.

`seed.py` emits ``creator_relations.travel_photo_1k_v1.seed.json`` (follow +
circle-member edges) for the canonical batch, but until now nothing consumed it — the file was a dead
artifact. This module is the single consumer: it loads the relations seed plus the
batch seed, validates every edge references a seeded creator ``subAccountId``, and
projects normalized follow-graph + circle-membership injections that downstream
seeding (user-service follow store / circle-service member store) applies so that
"seed 之后 follow 边可读" has a contract-tested truth source.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from _common.creator_pool.batch_policy import CANONICAL_BATCH_ID
from _common.creator_pool.io import repo_seed_fixture_dir
from _common.io import read_json
RELATIONS_SEED_NAME = "creator_relations.travel_photo_1k_v1.seed.json"


def _default_seed_name(vertical: str) -> str:
    if vertical == "travel":
        return "creator_travel_photo_1k_v1.seed.json"
    return f"creator_{vertical}_{CANONICAL_BATCH_ID}.seed.json"


@dataclass
class RelationInjections:
    """Normalized, apply-ready relation injections derived from the relations seed."""

    batch_id: str
    follow_edges: list[tuple[str, str]] = field(default_factory=list)
    circle_memberships: dict[str, list[str]] = field(default_factory=dict)
    entity_affinities: dict[str, list[str]] = field(default_factory=dict)
    circle_affinities: dict[str, list[str]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def follow_edge_count(self) -> int:
        return len(self.follow_edges)

    @property
    def circle_member_count(self) -> int:
        return sum(len(members) for members in self.circle_memberships.values())

    @property
    def entity_affinity_count(self) -> int:
        return sum(len(refs) for refs in self.entity_affinities.values())

    @property
    def circle_affinity_count(self) -> int:
        return sum(len(refs) for refs in self.circle_affinities.values())

    def following_of(self, sub_account_id: str) -> list[str]:
        """Who ``sub_account_id`` follows (outbound edges)."""
        return [to for frm, to in self.follow_edges if frm == sub_account_id]

    def followers_of(self, sub_account_id: str) -> list[str]:
        """Who follows ``sub_account_id`` (inbound edges)."""
        return [frm for frm, to in self.follow_edges if to == sub_account_id]

    def members_of(self, circle_id: str) -> list[str]:
        return list(self.circle_memberships.get(circle_id, []))

    def entity_affinities_of(self, sub_account_id: str) -> list[str]:
        return list(self.entity_affinities.get(sub_account_id, []))

    def circle_affinities_of(self, sub_account_id: str) -> list[str]:
        return list(self.circle_affinities.get(sub_account_id, []))


def build_relation_injections(
    relations_seed: Mapping[str, Any],
    seed_users: Iterable[Mapping[str, Any]],
) -> RelationInjections:
    """Validate + normalize the relations seed against the batch seed users."""
    batch_id = str(relations_seed.get("batchId") or "")
    seeded: set[str] = set()
    cohort_ids: set[str] = set()
    for user in seed_users:
        sub = str(user.get("subAccountId") or "")
        if sub:
            seeded.add(sub)
        cohort = str(user.get("cohortId") or "")
        if cohort:
            cohort_ids.add(cohort)

    result = RelationInjections(batch_id=batch_id)
    if not batch_id:
        result.issues.append("relations seed missing batchId")
    if cohort_ids and batch_id and batch_id not in cohort_ids:
        result.issues.append(
            f"relations batchId '{batch_id}' not in seeded cohortIds {sorted(cohort_ids)}"
        )

    edges = relations_seed.get("edges")
    if not isinstance(edges, list) or not edges:
        result.issues.append("relations seed has no edges")
        return result

    seen_follow: set[tuple[str, str]] = set()
    for idx, edge in enumerate(edges):
        if not isinstance(edge, Mapping):
            result.issues.append(f"edge[{idx}] is not an object")
            continue
        kind = str(edge.get("kind") or "")
        if kind == "FollowEdge":
            frm = str(edge.get("fromSubAccountId") or "")
            to = str(edge.get("toSubAccountId") or "")
            if not frm or not to:
                result.issues.append(f"edge[{idx}] FollowEdge missing from/to")
                continue
            if frm == to:
                result.issues.append(f"edge[{idx}] FollowEdge self-follow {frm}")
                continue
            if frm not in seeded:
                result.issues.append(f"edge[{idx}] FollowEdge.from '{frm}' not a seeded creator")
            if to not in seeded:
                result.issues.append(f"edge[{idx}] FollowEdge.to '{to}' not a seeded creator")
            pair = (frm, to)
            if pair in seen_follow:
                result.issues.append(f"edge[{idx}] duplicate FollowEdge {frm}->{to}")
                continue
            seen_follow.add(pair)
            result.follow_edges.append(pair)
        elif kind == "CircleMember":
            sub = str(edge.get("subAccountId") or "")
            circle_id = str(edge.get("circleId") or "")
            if not sub or not circle_id:
                result.issues.append(f"edge[{idx}] CircleMember missing subAccountId/circleId")
                continue
            if sub not in seeded:
                result.issues.append(f"edge[{idx}] CircleMember '{sub}' not a seeded creator")
            members = result.circle_memberships.setdefault(circle_id, [])
            if sub in members:
                result.issues.append(f"edge[{idx}] duplicate CircleMember {sub} in {circle_id}")
                continue
            members.append(sub)
        elif kind == "EntityAffinity":
            sub = str(edge.get("subAccountId") or "")
            entity_ref = str(edge.get("entityRef") or "")
            if not sub or not entity_ref:
                result.issues.append(f"edge[{idx}] EntityAffinity missing subAccountId/entityRef")
                continue
            if sub not in seeded:
                result.issues.append(f"edge[{idx}] EntityAffinity '{sub}' not a seeded creator")
            refs = result.entity_affinities.setdefault(sub, [])
            if entity_ref not in refs:
                refs.append(entity_ref)
        elif kind == "CircleAffinity":
            sub = str(edge.get("subAccountId") or "")
            circle_ref = str(edge.get("circleRef") or "")
            if not sub or not circle_ref:
                result.issues.append(f"edge[{idx}] CircleAffinity missing subAccountId/circleRef")
                continue
            if sub not in seeded:
                result.issues.append(f"edge[{idx}] CircleAffinity '{sub}' not a seeded creator")
            refs = result.circle_affinities.setdefault(sub, [])
            if circle_ref not in refs:
                refs.append(circle_ref)
        else:
            result.issues.append(f"edge[{idx}] unknown kind '{kind}'")

    return result


def load_relation_injections(
    *,
    vertical: str = "travel",
    batch_id: str | None = None,
    relations_path: Path | None = None,
    seed_path: Path | None = None,
) -> RelationInjections:
    """Load + build injections from on-disk canonical seeds (default travel-photo 1k batch)."""
    fixtures = repo_seed_fixture_dir()
    if relations_path is None:
        if batch_id and batch_id != CANONICAL_BATCH_ID:
            relations_path = fixtures / f"creator_relations.{batch_id}.seed.json"
        else:
            relations_path = fixtures / RELATIONS_SEED_NAME
    if seed_path is None:
        if batch_id and batch_id != CANONICAL_BATCH_ID:
            from governance.creator_pool.seed import seed_fixture_name

            seed_path = fixtures / seed_fixture_name(vertical, batch_id)
        else:
            seed_path = fixtures / _default_seed_name(vertical)
    relations_seed = read_json(relations_path)
    batch_seed = read_json(seed_path)
    users = batch_seed.get("users") if isinstance(batch_seed, Mapping) else []
    if not isinstance(users, list):
        users = []
    return build_relation_injections(relations_seed, users)
