"""受管 Circle journey ActorLease 到 probe 参数面的窄投影。

SCN-014 主旅程需要两个隔离 Actor：PRIMARY（圈主/群主）与 MEMBER（申请加入者）。
身份与生命周期只允许来自 `stackctl verify` 注入的 `QWQ_TEST_DATA_*` 环境变量；
禁止 fixture、seed 或固定业务对象 ID。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from dataclasses import dataclass
from typing import Mapping

from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole

HANDOFF_SCHEMA = "qwq.circle_journey_actor_handoff_projection.v1"
ACTOR_ROLES = (ActorRole.PRIMARY.value, ActorRole.MEMBER.value)
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
class ManagedJourneyActor:
    role: str
    owner_id: str
    persona_id: str
    access_token: str
    refresh_token: str

    def __post_init__(self) -> None:
        if self.role not in ACTOR_ROLES:
            raise ValueError(f"unsupported circle journey actor role: {self.role}")
        if any(
            not value.strip()
            for value in (
                self.owner_id,
                self.persona_id,
                self.access_token,
                self.refresh_token,
            )
        ):
            raise ValueError(f"circle journey actor role {self.role} is incomplete")


@dataclass(frozen=True)
class ManagedCircleJourneyHandoff:
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
    actors: tuple[ManagedJourneyActor, ...]

    def actor(self, role: str) -> ManagedJourneyActor:
        for actor in self.actors:
            if actor.role == role:
                return actor
        raise ValueError(f"circle journey handoff lacks actor role {role}")

    def require_active(self, now: dt.datetime | None = None) -> None:
        if self.lease_state != "active":
            raise ValueError(
                f"circle journey ActorLease must be active, got {self.lease_state}"
            )
        current = now or dt.datetime.now(dt.timezone.utc)
        if _parse_utc(self.lease_expires_at) <= current:
            raise ValueError("circle journey ActorLease has expired")

    def public_document(self) -> dict[str, object]:
        """脱敏生命周期证据：不含任何 token。"""

        return {
            "schema": HANDOFF_SCHEMA,
            "environment": self.environment,
            "target": self.target,
            "caseResultId": self.case_result_id,
            "testDataInstanceId": self.test_data_instance_id,
            "candidateBindingDigest": self.candidate_binding_digest,
            "requestDigest": self.request_digest,
            "leaseId": self.lease_id,
            "leaseGeneration": self.lease_generation,
            "leaseState": self.lease_state,
            "leaseExpiresAt": self.lease_expires_at,
            "actors": [
                {
                    "role": actor.role,
                    "personaDigest": hashlib.sha256(
                        actor.persona_id.encode("utf-8")
                    ).hexdigest()[:16],
                }
                for actor in self.actors
            ],
        }


def load_journey_handoff_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ManagedCircleJourneyHandoff:
    source = os.environ if environment is None else environment
    lifecycle = {
        field: str(source.get(environment_key) or "").strip()
        for field, environment_key in LIFECYCLE_ENV.items()
    }
    missing = [
        LIFECYCLE_ENV[field] for field, value in lifecycle.items() if not value
    ]
    actors: list[ManagedJourneyActor] = []
    for role in ACTOR_ROLES:
        prefix = "QWQ_TEST_DATA_" + role.upper()
        values = {
            "owner_id": str(source.get(prefix + "_OWNER_ID") or "").strip(),
            "persona_id": str(source.get(prefix + "_PERSONA_ID") or "").strip(),
            "access_token": str(source.get(prefix + "_ACCESS_TOKEN") or "").strip(),
            "refresh_token": str(source.get(prefix + "_REFRESH_TOKEN") or "").strip(),
        }
        missing.extend(
            prefix + "_" + name.upper() for name, value in values.items() if not value
        )
        if all(values.values()):
            actors.append(ManagedJourneyActor(role=role, **values))
    if missing:
        raise ValueError(
            "circle journey ActorLease handoff is incomplete: "
            + ", ".join(sorted(missing))
        )
    try:
        generation = int(lifecycle["lease_generation"])
    except ValueError as exc:
        raise ValueError(
            "circle journey ActorLease generation must be an integer"
        ) from exc
    handoff = ManagedCircleJourneyHandoff(
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
    handoff.require_active()
    return handoff


def _parse_utc(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"circle journey ActorLease expiry is not ISO-8601: {value}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed
