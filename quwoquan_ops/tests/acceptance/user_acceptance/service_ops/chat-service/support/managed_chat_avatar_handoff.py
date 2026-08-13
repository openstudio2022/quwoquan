"""受管 Chat Avatar ActorLease 到旧探针参数面的窄投影。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Mapping

from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole


HANDOFF_SCHEMA = "qwq.chat_avatar_actor_handoff_projection.v1"
ACTOR_ROLES = tuple(
    role.value
    for role in (
        ActorRole.PRIMARY,
        ActorRole.SENDER,
        ActorRole.RECEIVER,
        ActorRole.MEMBER,
    )
)
LIFECYCLE_ENV = {
    "environment": "QWQ_TEST_DATA_ENVIRONMENT",
    "target": "QWQ_TEST_DATA_TARGET",
    "case_result_id": "QWQ_TEST_DATA_CASE_RESULT_ID",
    "test_data_instance_id": "QWQ_TEST_DATA_INSTANCE_ID",
    "candidate_binding_digest": "QWQ_TEST_DATA_CANDIDATE_BINDING_DIGEST",
    "request_digest": "QWQ_TEST_DATA_REQUEST_DIGEST",
    "lease_id": "QWQ_TEST_DATA_ACTOR_LEASE_ID",
    "lease_generation": "QWQ_TEST_DATA_ACTOR_LEASE_GENERATION",
    "lease_state": "QWQ_TEST_DATA_ACTOR_LEASE_STATE",
    "lease_expires_at": "QWQ_TEST_DATA_ACTOR_LEASE_EXPIRES_AT",
}


@dataclass(frozen=True)
class ManagedActorIdentity:
    role: str
    owner_id: str
    persona_id: str
    access_token: str
    refresh_token: str

    def __post_init__(self) -> None:
        if self.role not in ACTOR_ROLES:
            raise ValueError(f"unsupported managed actor role: {self.role}")
        if any(
            not value.strip()
            for value in (
                self.owner_id,
                self.persona_id,
                self.access_token,
                self.refresh_token,
            )
        ):
            raise ValueError(f"managed actor role {self.role} is incomplete")


@dataclass(frozen=True)
class ManagedChatAvatarHandoff:
    environment: str
    target: str
    case_result_id: str
    test_data_instance_id: str
    candidate_binding_digest: str
    request_digest: str
    lease_id: str
    lease_generation: int
    lease_state: str
    lease_expires_at: str
    actors: tuple[ManagedActorIdentity, ...]

    def __post_init__(self) -> None:
        if self.environment not in {"alpha", "beta", "gamma"}:
            raise ValueError(
                "managed chat avatar mutation is restricted to Alpha/Beta/Gamma"
            )
        if self.target != f"{self.environment}-local":
            raise ValueError("managed chat avatar target/environment mismatch")
        for name in ("case_result_id", "test_data_instance_id", "lease_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"managed chat avatar {name} is required")
        for name in ("candidate_binding_digest", "request_digest"):
            value = str(getattr(self, name))
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError(f"managed chat avatar {name} must be canonical sha256")
        if self.lease_generation <= 0:
            raise ValueError("managed chat avatar lease generation must be positive")
        if self.lease_state != "active":
            raise ValueError("managed chat avatar ActorLease must be active")
        expires_at = _parse_utc(self.lease_expires_at)
        if expires_at <= dt.datetime.now(dt.timezone.utc):
            raise ValueError("managed chat avatar ActorLease is expired")
        if tuple(actor.role for actor in self.actors) != ACTOR_ROLES:
            raise ValueError(
                "managed chat avatar actors must contain primary/sender/receiver/member"
            )
        owner_ids = tuple(actor.owner_id for actor in self.actors)
        persona_ids = tuple(actor.persona_id for actor in self.actors)
        if len(set(owner_ids)) != len(owner_ids):
            raise ValueError("managed chat avatar actors must use distinct accounts")
        if len(set(persona_ids)) != len(persona_ids):
            raise ValueError("managed chat avatar actors must use distinct personas")

    def actor(self, role: str) -> ManagedActorIdentity:
        matches = tuple(actor for actor in self.actors if actor.role == role)
        if len(matches) != 1:
            raise ValueError(f"managed chat avatar actor role {role} is unavailable")
        return matches[0]

    def actor_for_owner(self, owner_id: str) -> ManagedActorIdentity:
        matches = tuple(actor for actor in self.actors if actor.owner_id == owner_id)
        if len(matches) != 1:
            raise ValueError("request identity is outside the managed ActorLease")
        return matches[0]

    def command_arguments(self) -> list[str]:
        primary = self.actor("primary")
        sender = self.actor("sender")
        receiver = self.actor("receiver")
        member = self.actor("member")
        return [
            "--test-data-case-result-id",
            self.case_result_id,
            "--test-data-instance-id",
            self.test_data_instance_id,
            "--candidate-binding-digest",
            self.candidate_binding_digest,
            "--request-digest",
            self.request_digest,
            "--actor-lease-id",
            self.lease_id,
            "--actor-lease-generation",
            str(self.lease_generation),
            "--actor-lease-state",
            self.lease_state,
            "--actor-lease-expires-at",
            self.lease_expires_at,
            "--creator-id",
            primary.owner_id,
            "--initial-member-id",
            sender.owner_id,
            "--initial-member-id",
            receiver.owner_id,
            "--added-member-id",
            member.owner_id,
            "--removed-member-id",
            member.owner_id,
        ]

    def validate_namespace(self, args: argparse.Namespace) -> None:
        expected = {
            "test_data_case_result_id": self.case_result_id,
            "test_data_instance_id": self.test_data_instance_id,
            "candidate_binding_digest": self.candidate_binding_digest,
            "request_digest": self.request_digest,
            "actor_lease_id": self.lease_id,
            "actor_lease_generation": self.lease_generation,
            "actor_lease_state": self.lease_state,
            "actor_lease_expires_at": self.lease_expires_at,
            "creator_id": self.actor("primary").owner_id,
            "added_member_id": self.actor("member").owner_id,
            "removed_member_id": self.actor("member").owner_id,
        }
        for name, value in expected.items():
            if getattr(args, name, None) != value:
                raise ValueError(
                    f"--{name.replace('_', '-')} must match the managed ActorLease projection"
                )
        expected_members = (
            self.actor("sender").owner_id,
            self.actor("receiver").owner_id,
        )
        if tuple(getattr(args, "initial_member_id", ())) != expected_members:
            raise ValueError(
                "--initial-member-id must project sender and receiver exactly once"
            )

    def public_document(self) -> dict[str, object]:
        actors = [
            {
                "role": actor.role,
                "accountId": actor.owner_id,
                "personaId": actor.persona_id,
            }
            for actor in self.actors
        ]
        actor_set_digest = _canonical_digest({"actors": actors})
        return {
            "schema": HANDOFF_SCHEMA,
            "environment": self.environment,
            "target": self.target,
            "caseResultId": self.case_result_id,
            "testDataInstanceId": self.test_data_instance_id,
            "candidateBindingDigest": self.candidate_binding_digest,
            "requestDigest": self.request_digest,
            "actorLease": {
                "leaseId": self.lease_id,
                "generation": self.lease_generation,
                "state": self.lease_state,
                "expiresAt": self.lease_expires_at,
                "actorSetDigest": actor_set_digest,
            },
            "actors": actors,
        }

    def primary_patrol_defines(self) -> dict[str, str]:
        primary = self.actor("primary")
        return {
            "TEST_AUTH_TOKEN": primary.access_token,
            "TEST_REFRESH_TOKEN": primary.refresh_token,
            "APP_CURRENT_OWNER_ID": primary.owner_id,
            "APP_CURRENT_PERSONA_ID": primary.persona_id,
        }

    def secret_values(self) -> tuple[str, ...]:
        return tuple(
            secret
            for actor in self.actors
            for secret in (actor.access_token, actor.refresh_token)
        )


def add_required_handoff_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--test-data-case-result-id", required=True)
    parser.add_argument("--test-data-instance-id", required=True)
    parser.add_argument("--candidate-binding-digest", required=True)
    parser.add_argument("--request-digest", required=True)
    parser.add_argument("--actor-lease-id", required=True)
    parser.add_argument("--actor-lease-generation", type=int, required=True)
    parser.add_argument("--actor-lease-state", choices=("active",), required=True)
    parser.add_argument("--actor-lease-expires-at", required=True)
    parser.add_argument("--creator-id", required=True)
    parser.add_argument("--initial-member-id", action="append", required=True)
    parser.add_argument("--added-member-id", required=True)
    parser.add_argument("--removed-member-id", required=True)


def load_managed_handoff_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ManagedChatAvatarHandoff:
    source = os.environ if environment is None else environment
    lifecycle = {
        field: str(source.get(environment_key) or "").strip()
        for field, environment_key in LIFECYCLE_ENV.items()
    }
    missing = [
        environment_key
        for field, environment_key in LIFECYCLE_ENV.items()
        if not lifecycle[field]
    ]
    actors: list[ManagedActorIdentity] = []
    for role in ACTOR_ROLES:
        prefix = "QWQ_TEST_DATA_" + role.upper()
        values = {
            "owner_id": str(source.get(prefix + "_OWNER_ID") or "").strip(),
            "persona_id": str(source.get(prefix + "_PERSONA_ID") or "").strip(),
            "access_token": str(source.get(prefix + "_ACCESS_TOKEN") or "").strip(),
            "refresh_token": str(source.get(prefix + "_REFRESH_TOKEN") or "").strip(),
        }
        missing.extend(
            prefix + "_" + name.upper()
            for name, value in values.items()
            if not value
        )
        if all(values.values()):
            actors.append(ManagedActorIdentity(role=role, **values))
    if missing:
        raise ValueError(
            "managed chat avatar ActorLease handoff is incomplete: "
            + ", ".join(sorted(missing))
        )
    try:
        generation = int(lifecycle["lease_generation"])
    except ValueError as exc:
        raise ValueError(
            "managed chat avatar ActorLease generation must be an integer"
        ) from exc
    return ManagedChatAvatarHandoff(
        environment=lifecycle["environment"],
        target=lifecycle["target"],
        case_result_id=lifecycle["case_result_id"],
        test_data_instance_id=lifecycle["test_data_instance_id"],
        candidate_binding_digest=lifecycle["candidate_binding_digest"],
        request_digest=lifecycle["request_digest"],
        lease_id=lifecycle["lease_id"],
        lease_generation=generation,
        lease_state=lifecycle["lease_state"],
        lease_expires_at=lifecycle["lease_expires_at"],
        actors=tuple(actors),
    )


def _parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "managed chat avatar ActorLease expiry must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError("managed chat avatar ActorLease expiry must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
