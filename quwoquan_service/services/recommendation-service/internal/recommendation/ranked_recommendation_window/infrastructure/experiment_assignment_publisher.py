from __future__ import annotations

import hashlib
from typing import Any

from ..domain.experiment_policy import Assignment


STREAM = "events.ops.experiment_assignment_observed"
RETENTION_SECONDS = 7 * 24 * 60 * 60


class RedisExperimentAssignmentPublisher:
    def __init__(self, redis_client: Any) -> None:
        if redis_client is None:
            raise ValueError("recommendation experiment assignment publisher requires Redis")
        self._redis = redis_client

    def publish(self, assignment: Assignment) -> None:
        identity = "\x00".join(
            (
                assignment.experiment_id,
                str(assignment.experiment_revision),
                assignment.subject_key,
            )
        )
        event_id = "recommendation-experiment-assignment-" + hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()
        self._redis.xadd(
            STREAM,
            {
                "eventId": event_id,
                "eventType": "ExperimentAssignmentObserved",
                "producer": "recommendation-service",
                "experimentId": assignment.experiment_id,
                "experimentRevision": str(assignment.experiment_revision),
                "subjectKey": assignment.subject_key,
                "variant": assignment.bucket,
                "assignedAt": assignment.assigned_at.isoformat(),
            },
        )
        server_time = self._redis.time()
        cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
        self._redis.xtrim(STREAM, minid=f"{max(cutoff_ms, 0)}-0", approximate=False)
        self._redis.expire(STREAM, RETENTION_SECONDS)
