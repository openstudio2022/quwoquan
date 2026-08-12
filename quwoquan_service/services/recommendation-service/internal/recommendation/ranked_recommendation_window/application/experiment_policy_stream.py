from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from ..domain.experiment_policy import ExperimentPolicy


@dataclass(frozen=True, slots=True)
class ExperimentPolicyStreamRecord:
    stream_id: str
    values: Mapping[str, str]


class ExperimentPolicyDependencyUnavailable(RuntimeError):
    """A declared policy dependency could not complete the requested operation."""


class ExperimentPolicyStreamUnavailable(ExperimentPolicyDependencyUnavailable):
    """The policy event stream is temporarily unavailable."""


class ExperimentPolicyStoreUnavailable(ExperimentPolicyDependencyUnavailable):
    """The policy projection store is temporarily unavailable."""


class ExperimentPolicyStream(Protocol):
    def ensure_consumer_group(self) -> None: ...

    def read(self, *, consumer: str) -> tuple[ExperimentPolicyStreamRecord, ...]: ...

    def acknowledge(self, stream_id: str) -> None: ...

    def dead_letter(
        self,
        *,
        stream_id: str,
        event_id: str,
        reason: str,
        dead_lettered_at: datetime,
    ) -> None: ...


class ExperimentPolicyStore(Protocol):
    def apply(self, policy: ExperimentPolicy) -> ExperimentPolicy: ...
