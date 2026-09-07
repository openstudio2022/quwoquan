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
from content.release.environment.release_runtime import admit_environment_release
from content.release.environment.run_evidence import validate_path_segment
from content.release.model import DEPLOYMENT_ENVIRONMENTS
from core.paths import OUTPUT_ROOT, REPO_ROOT
from core.control_types import ReleaseRunKind

_VALID_ENVIRONMENTS = frozenset(
    str(environment) for environment in DEPLOYMENT_ENVIRONMENTS
)


def dispatch_ship(
    args: argparse.Namespace,
    *,
    release_root: Path,
    apply: Callable[[argparse.Namespace], None],
    rollback: Callable[[argparse.Namespace], None],
    verify: Callable[[argparse.Namespace], None],
    activate: Callable[[argparse.Namespace], None] | None = None,
    repo_root: Path = REPO_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> None:
    operations = {
        ReleaseRunKind.APPLY: apply,
        ReleaseRunKind.ROLLBACK: rollback,
        ReleaseRunKind.VERIFY: verify,
    }
    if activate is not None:
        operations[ReleaseRunKind.ACTIVATE] = activate
    selected = operations.get(args.ship_command)
    if selected is None:
        raise SystemExit("[ship] subcommand required")
    operation = selected
    raw_environment = str(getattr(args, "env", "") or "")
    environment = raw_environment.strip()
    if (
        not environment
        or raw_environment != environment
        or "," in environment
        or any(character.isspace() for character in environment)
        or environment not in _VALID_ENVIRONMENTS
    ):
        raise SystemExit("[ship] --env 必须且只能是一个有效环境")
    try:
        admission = admit_environment_release(
            args,
            repo_root=repo_root,
            output_root=output_root,
            release_root=release_root,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(f"[ship] GATE_BLOCK release admission failed: {exc}") from exc
    release_id = validate_path_segment(admission.release_id, label="release_id")
    setattr(args, "release_admission", admission)
    run_id = str(getattr(args, "run_id", "") or "")
    if run_id:
        validate_path_segment(run_id, label="run_id")
    if args.ship_command == ReleaseRunKind.ROLLBACK:
        validate_path_segment(
            str(getattr(args, "from_release_id", "") or ""),
            label="from_release_id",
        )
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
                    f"{environment}: " + ", ".join(path.as_posix() for path in active)
                )
            operation(args)
    except (AcceptanceLeaseError, ReleaseOperationConflict, ValueError) as exc:
        raise SystemExit(f"[ship] {exc}") from exc


__all__ = ["dispatch_ship"]
