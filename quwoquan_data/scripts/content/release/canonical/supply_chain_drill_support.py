"""Contracts and formal-command adapters for the supply-chain drill."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from content.release.environment.activation_recovery import (
    PreviousVerifiedRelease,
)
from core.io import read_json
from core.paths import REPO_ROOT
from verify.release_publishability import readiness_phase_issue


ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
PROFILES = frozenset({"inspect", "delivery", "rehearsal"})
PLATFORMS = frozenset({"android", "ios-simulator"})
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
DATA_CLI = REPO_ROOT / "quwoquan_data/scripts/cli.py"
STACKCTL = REPO_ROOT / "quwoquan_ops/cli/stackctl.py"


class SupplyChainDrillError(RuntimeError):
    """The drill cannot continue without inventing delivery evidence."""


class StageBlocked(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FormalCommand:
    name: str
    argv: tuple[str, ...]
    evidence_ref: str
    input: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FormalCommandResult:
    returncode: int
    payload: Mapping[str, object]
    evidence_ref: str
    first_blocker: str


@dataclass(frozen=True, slots=True)
class DrillDependencies:
    run_command: Callable[[FormalCommand], FormalCommandResult]
    read_runtime: Callable[[str], Mapping[str, object] | None]
    now: Callable[[], datetime]
    monotonic: Callable[[], float]


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    release_id: str
    release_root: Path
    attestation_path: Path
    manifest_digest: str
    expected_posts: int


@dataclass(frozen=True, slots=True)
class VerifiedCandidate:
    import_run_id: str
    verify_run_id: str
    readiness_path: Path
    import_report_path: Path


def safe_segment(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    if _SEGMENT.fullmatch(normalized) is None:
        raise SupplyChainDrillError(
            f"DATA.SUPPLY_CHAIN_DRILL.INPUT_INVALID: {label}={normalized!r}"
        )
    return normalized


def relative_ref(path: Path, *, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.EVIDENCE_REF_INVALID"
        ) from exc


def resolve_evidence_ref(output_root: Path, evidence_ref: str) -> Path:
    relative = Path(str(evidence_ref or ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.EVIDENCE_REF_INVALID"
        )
    path = (output_root / relative).resolve()
    relative_ref(path, output_root=output_root)
    if path.is_symlink() or not path.is_file():
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.EVIDENCE_MISSING"
        )
    return path


def release_identity(
    *, output_root: Path, release_id: str, environment: str
) -> ReleaseIdentity:
    release_root = output_root / "data/releases" / release_id
    attestation_path = release_root / "attestations/release.json"
    header_path = release_root / "payload/release.json"
    desired_path = release_root / "payload/desired_state.json"
    if any(
        path.is_symlink() or not path.is_file()
        for path in (attestation_path, header_path, desired_path)
    ):
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.RELEASE_EVIDENCE_MISSING"
        )
    attestation = read_json(attestation_path)
    header = read_json(header_path)
    desired = read_json(desired_path)
    digest = str(attestation.get("payloadSha256") or "")
    if (
        any(
            document.get("releaseId") != release_id
            for document in (attestation, header, desired)
        )
        or _DIGEST.fullmatch(digest) is None
    ):
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.RELEASE_IDENTITY_INVALID"
        )
    target = str(header.get("targetEnvironment") or "")
    if target and target != environment:
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.ENVIRONMENT_MISMATCH"
        )
    desired_refs = desired.get("desiredRefs")
    posts = desired_refs.get("posts") if isinstance(desired_refs, Mapping) else None
    if not isinstance(posts, list):
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.DESIRED_STATE_INVALID"
        )
    return ReleaseIdentity(
        release_id, release_root, attestation_path, digest, len(posts)
    )


def verified_candidate(
    *, output_root: Path, environment: str, identity: ReleaseIdentity
) -> VerifiedCandidate:
    root = (
        output_root
        / "env"
        / environment
        / "runs/data-release"
        / identity.release_id
    )
    matches: list[tuple[str, Path, Mapping[str, object]]] = []
    for path in sorted(root.glob("*/release-readiness.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            document = read_json(path)
        except (OSError, TypeError, ValueError):
            continue
        if (
            isinstance(document, Mapping)
            and document.get("schema")
            == "quwoquan_data.environment_release_readiness"
            and document.get("environment") == environment
            and document.get("releaseId") == identity.release_id
            and document.get("manifestDigest") == identity.manifest_digest
            and document.get("passed") is True
        ):
            matches.append((str(document.get("verifiedAt") or ""), path, document))
    if not matches:
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.CANDIDATE_NOT_VERIFIED"
        )
    _verified_at, path, readiness = max(
        matches, key=lambda item: (item[0], item[1].as_posix())
    )
    return VerifiedCandidate(
        import_run_id=safe_segment(
            str(readiness.get("importRunId") or ""), label="importRunId"
        ),
        verify_run_id=safe_segment(
            str(readiness.get("verifyRunId") or path.parent.name),
            label="verifyRunId",
        ),
        readiness_path=path,
        import_report_path=resolve_evidence_ref(
            output_root, str(readiness.get("contentImportReportRef") or "")
        ),
    )


def previous_import_run_id(previous: PreviousVerifiedRelease) -> str:
    return safe_segment(
        str(read_json(previous.readiness_path).get("importRunId") or ""),
        label="previousImportRunId",
    )


def readiness_phase(path: Path) -> str:
    value = str(read_json(path).get("readinessPhase") or "")
    issue = readiness_phase_issue(value)
    if issue is not None:
        raise SupplyChainDrillError(f"{path}: {issue}")
    return value


def runtime_state(value: Mapping[str, object] | None) -> tuple[bool, str]:
    if not isinstance(value, Mapping) or value.get("status") != "running":
        return False, ""
    return True, str(value.get("workload") or "")


def runtime_restored(
    before: Mapping[str, object] | None,
    after: Mapping[str, object] | None,
) -> bool:
    return runtime_state(before) == runtime_state(after)


def _default_runtime_reader(target: str) -> Mapping[str, object] | None:
    from quwoquan_ops.cli.lib.startup_attempt_receipt import (
        startup_attempt_path,
        validate_startup_attempt,
    )

    path = startup_attempt_path(target)
    return (
        validate_startup_attempt(read_json(path), expected_target=target)
        if path.is_file()
        else None
    )


def _payload_from_evidence(path: Path) -> Mapping[str, object]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _payload_blocker(value: Mapping[str, object]) -> str:
    for field in ("firstBlocker", "blocker", "code"):
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate:
            return candidate
    issues = value.get("issues")
    if isinstance(issues, list) and issues and isinstance(issues[0], Mapping):
        code = issues[0].get("code")
        return str(code or "")
    return ""


def default_dependencies(output_root: Path) -> DrillDependencies:
    def run(command: FormalCommand) -> FormalCommandResult:
        executable = Path(command.argv[0])
        argv = [sys.executable, str(executable)]
        if executable == STACKCTL:
            argv.extend(["--output-format", "json"])
        completed = subprocess.run(
            [*argv, *command.argv[1:]],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        payload = _payload_from_evidence(output_root / command.evidence_ref)
        if not payload and completed.stdout.strip().startswith("{"):
            try:
                decoded = json.loads(completed.stdout)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, Mapping):
                payload = decoded
        blocker = _payload_blocker(payload)
        if completed.returncode and not blocker:
            blocker = (
                "DATA.SUPPLY_CHAIN_DRILL."
                + command.name.upper().replace("-", "_")
                + "_FAILED"
            )
        return FormalCommandResult(
            completed.returncode,
            payload,
            command.evidence_ref,
            blocker,
        )

    return DrillDependencies(
        run_command=run,
        read_runtime=_default_runtime_reader,
        now=lambda: datetime.now(timezone.utc),
        monotonic=monotonic,
    )


def command_stage(
    command: FormalCommand, *, dependencies: DrillDependencies
) -> tuple[dict[str, object], FormalCommandResult]:
    started = dependencies.monotonic()
    result = dependencies.run_command(command)
    duration = max(0, int((dependencies.monotonic() - started) * 1000))
    passed = result.returncode == 0
    return (
        {
            "name": command.name,
            "result": "passed" if passed else "failed",
            "durationMs": duration,
            "input": dict(command.input),
            "succeeded": int(passed),
            "failed": int(not passed),
            "excluded": int(result.payload.get("excludedCount") or 0),
            "successRate": 1.0 if passed else 0.0,
            "firstBlocker": "" if passed else result.first_blocker,
            "evidenceRef": result.evidence_ref or command.evidence_ref,
        },
        result,
    )


def fact_stage(
    name: str,
    *,
    passed: bool,
    blocker: str,
    evidence_ref: str,
    input: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "result": "passed" if passed else "failed",
        "durationMs": 0,
        "input": dict(input or {}),
        "succeeded": int(passed),
        "failed": int(not passed),
        "excluded": 0,
        "successRate": 1.0 if passed else 0.0,
        "firstBlocker": "" if passed else blocker,
        "evidenceRef": evidence_ref,
    }


def data_command(name: str, evidence_ref: str, *arguments: str) -> FormalCommand:
    return FormalCommand(
        name,
        (str(DATA_CLI), *arguments),
        evidence_ref,
        {"entrypoint": "qwq-data", "arguments": list(arguments)},
    )


def stack_command(name: str, evidence_ref: str, *arguments: str) -> FormalCommand:
    return FormalCommand(
        name,
        (str(STACKCTL), *arguments),
        evidence_ref,
        {"entrypoint": "stackctl", "arguments": list(arguments)},
    )


def run_required(
    command: FormalCommand,
    *,
    dependencies: DrillDependencies,
    stages: list[dict[str, object]],
) -> FormalCommandResult:
    stage, result = command_stage(command, dependencies=dependencies)
    stages.append(stage)
    if result.returncode:
        raise StageBlocked(
            result.first_blocker or "DATA.SUPPLY_CHAIN_DRILL.STAGE_FAILED"
        )
    return result


def delivery_counts(
    expected: int, result: FormalCommandResult
) -> dict[str, int | None]:
    source = result.payload.get("counts")
    if not isinstance(source, Mapping):
        raise StageBlocked("DATA.SUPPLY_CHAIN_DRILL.DELIVERY_COUNTS_MISSING")
    counts: dict[str, int | None] = {
        "expected": expected,
        "imported": source.get("importedPosts"),
        "active": source.get("activePosts"),
        "searchable": source.get("searchablePosts"),
        "recommendable": source.get("recommendablePosts"),
    }
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in counts.values()
    ):
        raise StageBlocked("DATA.SUPPLY_CHAIN_DRILL.DELIVERY_COUNTS_INVALID")
    if any(value != expected for value in counts.values()):
        raise StageBlocked("DATA.SUPPLY_CHAIN_DRILL.DELIVERY_COUNT_MISMATCH")
    return counts


def stage_ref(run_ref: str, stage: str) -> str:
    return f"{run_ref}/{stage}/report.json"


def report_dir(output_root: Path, run_ref: str, stage: str) -> str:
    return str((output_root / run_ref / stage).resolve())


__all__ = [
    "DATA_CLI",
    "STACKCTL",
    "DrillDependencies",
    "ENVIRONMENTS",
    "FormalCommand",
    "FormalCommandResult",
    "PLATFORMS",
    "PROFILES",
    "ReleaseIdentity",
    "StageBlocked",
    "SupplyChainDrillError",
    "command_stage",
    "data_command",
    "default_dependencies",
    "delivery_counts",
    "fact_stage",
    "previous_import_run_id",
    "readiness_phase",
    "relative_ref",
    "release_identity",
    "report_dir",
    "run_required",
    "runtime_restored",
    "runtime_state",
    "safe_segment",
    "stack_command",
    "stage_ref",
    "verified_candidate",
]
