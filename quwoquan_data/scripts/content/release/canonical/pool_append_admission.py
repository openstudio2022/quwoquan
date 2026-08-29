# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005
"""Keep the raw append path off objects a WorkRequest already owns.

`pool-append` exists for objects that predate the receipt protocol and therefore
have no reviewed delivery intent to consume. An object produced by a compiled
WorkRequest does have one, so letting it in here would give the canonical pool a
second write path whose admission never passed independent review.

The admitted-or-refused decision reads one explicit declaration: a compiled
WorkRequest package names every carrier execution it drives. Whether the
execution workspace still sits on disk is not consulted — that would make
admission depend on the shape of the filesystem rather than on something a
writer signed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.request_envelope import envelopes_root
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)

DELIVERY_INTENT_REQUIRED = "DATA.POOL.DELIVERY_INTENT_REQUIRED"


def work_request_driven_execution_ids(*, output_root: Path | None = None) -> dict[str, str]:
    """Index every carrier execution a compiled WorkRequest declares it drives.

    Read once per batch rather than per item: the index is the same for all
    items, and re-deriving it per item would let two items in one batch be
    judged against two different views of the compile packages.
    """

    root = envelopes_root(root=output_root)
    if not root.is_dir():
        return {}
    driven: dict[str, str] = {}
    for path in sorted(root.rglob("work-request.json")):
        document = _read_json(path)
        if not isinstance(document, Mapping):
            raise ObjectTransactionError(
                f"DATA.POOL.WORK_REQUEST_PACKAGE_INVALID: {path}"
            )
        envelopes = document.get("carrierEnvelopes")
        if not isinstance(envelopes, list):
            raise ObjectTransactionError(
                f"DATA.POOL.WORK_REQUEST_PACKAGE_INVALID: {path}"
            )
        work_request_id = str(document.get("workRequestId") or "").strip()
        if not work_request_id:
            raise ObjectTransactionError(
                f"DATA.POOL.WORK_REQUEST_PACKAGE_INVALID: {path}"
            )
        for row in envelopes:
            if not isinstance(row, Mapping):
                raise ObjectTransactionError(
                    f"DATA.POOL.WORK_REQUEST_PACKAGE_INVALID: {path}"
                )
            execution_id = str(row.get("executionId") or "").strip()
            if execution_id:
                driven[execution_id] = work_request_id
    return driven


def assert_no_work_request_object(
    items: Iterable[Mapping[str, Any]], *, output_root: Path | None = None
) -> None:
    """Refuse the whole batch when any item belongs to a compiled WorkRequest.

    The refusal is batch-wide rather than per item: a batch that silently drops
    the WorkRequest-owned rows and admits the rest would report success while
    having quietly split one operator action across two write paths.
    """

    driven = work_request_driven_execution_ids(output_root=output_root)
    if not driven:
        return
    for item in items:
        record = item.get("record")
        if not isinstance(record, Mapping):
            continue
        identity = record.get("sourceIdentity")
        if not isinstance(identity, Mapping):
            # author 记录不带 sourceIdentity：它不是 WorkRequest 的载体产物，
            # 本判据对它无话可说，交由既有身份判据裁决。
            continue
        execution_id = str(identity.get("executionId") or "").strip()
        work_request_id = driven.get(execution_id)
        if work_request_id is not None:
            raise ObjectTransactionError(
                f"{DELIVERY_INTENT_REQUIRED}: execution {execution_id} is driven by "
                f"{work_request_id}; admit it through its reviewed delivery intent "
                "and drain instead of the raw append path"
            )


__all__ = [
    "DELIVERY_INTENT_REQUIRED",
    "assert_no_work_request_object",
    "work_request_driven_execution_ids",
]
