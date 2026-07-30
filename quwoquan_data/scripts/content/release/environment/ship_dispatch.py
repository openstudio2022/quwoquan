"""Small process-locking dispatcher for canonical Data ship operations."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from content.release.canonical.acceptance_lease import (
    AcceptanceLeaseError,
    active_acceptance_lease_refs,
)
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from core.control_types import ReleaseRunKind


def dispatch_ship(
    args: argparse.Namespace,
    *,
    release_root: Path,
    apply: Callable[[argparse.Namespace], None],
    rollback: Callable[[argparse.Namespace], None],
    verify: Callable[[argparse.Namespace], None],
) -> None:
    operations = {
        ReleaseRunKind.APPLY: (str(getattr(args, "release_id", "")), apply),
        ReleaseRunKind.ROLLBACK: (str(getattr(args, "to_release", "")), rollback),
        ReleaseRunKind.VERIFY: (str(getattr(args, "release_id", "")), verify),
    }
    selected = operations.get(args.ship_command)
    if selected is None:
        raise SystemExit("[ship] subcommand required")
    release_id, operation = selected
    environment = str(getattr(args, "env", "") or "").strip()
    try:
        with release_operation_guard(
            lock_root=release_operation_lock_root(release_root),
            release_ids=(release_id,),
            exclusive_releases=True,
            environments=(environment,),
            exclusive_environments=True,
        ):
            active = active_acceptance_lease_refs(
                output_root=release_root.parent.parent,
                environment=environment,
            )
            if active:
                raise AcceptanceLeaseError(
                    "GATE_BLOCK active acceptance lease protects environment="
                    f"{environment}: "
                    + ", ".join(path.as_posix() for path in active)
                )
            operation(args)
    except (AcceptanceLeaseError, ReleaseOperationConflict, ValueError) as exc:
        raise SystemExit(f"[ship] {exc}") from exc


__all__ = ["dispatch_ship"]
