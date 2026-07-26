"""Controlled deletion of one inactive, disposable immutable release."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from content.release.canonical.object_transaction_contract import _safe_id


def _active_release_processes(release_id: str) -> tuple[str, ...]:
    """Return live release writers that still reference exactly one release."""

    process = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError("unable to inspect active release commands before discard")
    active_commands = ("ship apply", "ship rollback", "ship verify", "release aggregate", "release baseline")
    return tuple(
        line.strip()
        for line in process.stdout.splitlines()
        if release_id in line and any(command in line for command in active_commands)
    )


def _environment_evidence_roots(*, output_root: Path, release_id: str) -> tuple[Path, ...]:
    """Find only derived environment evidence for the selected immutable release."""

    environment_root = output_root / "env"
    if not environment_root.is_dir():
        return ()
    return tuple(
        path
        for path in environment_root.glob(f"*/runs/data-release/{release_id}")
        if path.is_dir()
    )


def discard_release(
    release_id: str,
    *,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> None:
    """Delete one derived release and its derived environment evidence.

    The command is deliberately narrow: it accepts only a single safe release
    identifier, rejects live writers, and never reaches source configuration or
    canonical publish.  Environment databases must already point at another
    immutable release before this disposable evidence is removed.
    """

    normalized_id = _safe_id(release_id, label="releaseId")
    release = release_root / normalized_id
    if not release.is_dir():
        raise FileNotFoundError(f"release output does not exist: {normalized_id}")
    active_processes = _active_release_processes(normalized_id)
    if active_processes:
        raise RuntimeError(
            "GATE_BLOCK active release command owns release: " + "; ".join(active_processes)
        )
    evidence_roots = _environment_evidence_roots(
        output_root=output_root,
        release_id=normalized_id,
    )
    shutil.rmtree(release)
    for evidence_root in evidence_roots:
        shutil.rmtree(evidence_root)


def handle_discard(args: argparse.Namespace) -> None:
    release_id = str(getattr(args, "release_id", "") or "").strip()
    try:
        discard_release(release_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"[release discard] GATE_BLOCK {exc}") from exc
    print(f"[release discard] removed releaseId={release_id}")


__all__ = ["discard_release"]
