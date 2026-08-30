"""环境首次 mutation 的显式前环境 acceptance 前驱门禁。

兼容调用方独立传入 ref/digest 的 mutation 边界，并把校验委托给 canonical
``environment_acceptance_fact`` pure gate。该模块不搜索 ``latest``，不执行副作用。
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    EnvironmentAcceptanceFactError,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    validate_predecessor_acceptance as _validate_predecessor_acceptance,
)


class NormalizedPredecessorAcceptance(TypedDict):
    """mutation 入口可直接绑定的 canonical 前驱引用。"""

    environment: str
    factId: str
    ref: str
    digest: str


EnvironmentAcceptancePredecessorError = EnvironmentAcceptanceFactError


def validate_predecessor_acceptance(
    *,
    environment: str,
    release_id: str,
    release_digest: str,
    predecessor_ref: str | None,
    predecessor_digest: str | None,
    predecessor_fact_id: str | None,
    evidence_root: Path,
) -> NormalizedPredecessorAcceptance | None:
    """校验首次 mutation 的显式前环境 acceptance，并返回规范化绑定。

    Alpha 只接受三个 ``None``；Beta/Gamma/Prod 必须分别显式绑定
    Alpha/Beta/Gamma 的 canonical ``factId``、ref 与 exact-byte digest。
    """

    if (
        predecessor_ref is None
        and predecessor_digest is None
        and predecessor_fact_id is None
    ):
        predecessor = None
    elif (
        predecessor_ref is None
        or predecessor_digest is None
        or predecessor_fact_id is None
    ):
        raise EnvironmentAcceptanceFactError(
            "OPS.ENVIRONMENT_ACCEPTANCE_FACT.predecessor_blocked",
            "predecessor factId, ref, and digest must be supplied together",
        )
    else:
        predecessor = {
            "environment": {
                "beta": "alpha",
                "gamma": "beta",
                "prod": "gamma",
            }.get(environment, ""),
            "factId": predecessor_fact_id,
            "ref": predecessor_ref,
            "digest": predecessor_digest,
        }

    return _validate_predecessor_acceptance(
        environment=environment,
        predecessor_acceptance=predecessor,
        evidence_root=evidence_root,
        release_id=release_id,
        release_digest=release_digest,
    )
