"""Receipt/project admission gate for exact orphan Compose recovery."""

from __future__ import annotations

from typing import Any


def orphan_compose_runtime_gate(target_name: str) -> dict[str, Any]:
    """Resolve the one receipt/project identity eligible for exact recovery.

    Valid mutable receipts retain priority for their receipt-bound normal down.
    Only an inadmissible receipt that still satisfies the bounded target/project
    identity may select the mutable project for orphan recovery.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    leases = _stackctl.active_consumer_leases(target_name)
    if leases:
        identities = ", ".join(
            f"{item.get('device')}:{item.get('consumer')}" for item in leases
        )
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose teardown requires zero active consumer leases"
            + (f": {identities}" if identities else "")
        )
    try:
        startup = _stackctl.load_startup_attempt(target_name)
    except (OSError, ValueError) as exc:
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            f"canonical startup receipt is unreadable: {exc}"
        ) from exc

    stale_mutable: dict[str, Any] | None = None
    try:
        mutable = _stackctl.load_test_live_startup_attempt(target_name)
    except _stackctl.UnsafeTestLiveStartupReceiptPath as exc:
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            f"mutable startup receipt is unreadable: {exc}"
        ) from exc
    except (OSError, ValueError):
        try:
            candidate = _stackctl.read_stale_test_live_startup_attempt(target_name)
        except (OSError, ValueError) as exc:
            raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                f"mutable startup receipt is unreadable: {exc}"
            ) from exc
        if candidate is None:
            raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                "mutable startup receipt is unreadable but not eligible for "
                "bounded stale test-live recovery"
            )
        try:
            stale_mutable = (
                _stackctl.require_bounded_stale_test_live_startup_attempt(
                    target_name,
                    candidate,
                )
            )
        except ValueError as exc:
            raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                str(exc)
            ) from exc
        mutable = None

    mutable_status = str((mutable or {}).get("status") or "").strip()
    if mutable is not None and mutable_status != "stopped":
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose teardown cannot replace receipt-bound mutable normal "
            f"down; status={mutable_status or '<missing>'}"
        )

    startup_status = str((startup or {}).get("status") or "").strip()
    if stale_mutable is not None:
        if startup is not None and startup_status != "stopped":
            raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                "mutable and immutable startup receipts both claim live runtime; "
                "orphan Compose teardown identity is ambiguous"
            )
        project = _stackctl.orphan_compose_teardown.require_canonical_project(
            target_name,
            stale_mutable.get("composeProject"),
        )
        if (
            _stackctl.orphan_compose_teardown.canonical_project_kind(
                target_name,
                project,
            )
            != "mutable_test_live"
        ):
            raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
                "stale mutable startup receipt does not bind the target's exact "
                "test-live Compose project"
            )
        return {
            "startup": startup,
            "staleMutableStartup": stale_mutable,
            "expectedProject": project,
        }

    if startup is not None and startup_status != "stopped" and not (
        _stackctl._normal_down_structurally_impossible(target_name, startup)
    ):
        raise _stackctl.orphan_compose_teardown.OrphanComposeTeardownError(
            "orphan Compose teardown requires an absent or stopped startup receipt; "
            f"status={startup_status or '<missing>'} must use candidate-bound normal down"
        )
    return {
        "startup": startup,
        "staleMutableStartup": None,
        "expectedProject": "",
    }
