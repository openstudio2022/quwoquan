"""Create-once measurement-only capacity bootstrap process manager."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core import paths
from core.io import read_json
from core.schema import assert_valid


_SCHEMA = "quwoquan_data.capacity_calibration_bootstrap"
_POLICY_PATH = (
    paths.CONTROL_PLANE_SHARED_ROOT
    / "capacity_bootstrap_measurement_safety.policy.yaml"
)
_RUNS_REF = "data/local/capacity-bootstrap/runs"
_TERMINAL = frozenset({"measured", "failed", "canceled"})


class CapacityBootstrapError(RuntimeError):
    """A typed bootstrap command or evidence boundary failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    try:
        assert_valid(payload, "execution", "capacity_bootstrap_run")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise CapacityBootstrapError(
            "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID", str(exc)
        ) from exc
    return payload


def _write_create_once(path: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = read_json(path)
        if existing != payload:
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_CREATE_ONCE_CONFLICT",
                f"capacity bootstrap create-once conflict: {path}",
            )
        return payload
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return payload


def load_measurement_safety_policy() -> tuple[dict[str, Any], Path, str]:
    if _POLICY_PATH.is_symlink() or not _POLICY_PATH.is_file():
        raise CapacityBootstrapError(
            "DATA.CAPACITY.BOOTSTRAP_POLICY_INVALID",
            "measurement safety policy is missing",
        )
    try:
        policy = yaml.safe_load(_POLICY_PATH.read_text(encoding="utf-8"))
        assert_valid(
            policy,
            "execution",
            "capacity_bootstrap_measurement_safety_policy",
            label="capacity bootstrap measurement safety policy",
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise CapacityBootstrapError(
            "DATA.CAPACITY.BOOTSTRAP_POLICY_INVALID", str(exc)
        ) from exc
    if not isinstance(policy, dict):
        raise CapacityBootstrapError(
            "DATA.CAPACITY.BOOTSTRAP_POLICY_INVALID",
            "measurement safety policy must be an object",
        )
    return policy, _POLICY_PATH, _file_digest(_POLICY_PATH)


class CapacityBootstrapStatusQuery:
    def __init__(self, *, output_root: Path | None = None) -> None:
        self._output_root = Path(output_root or paths.OUTPUT_ROOT).resolve()

    def _root(self, run_id: str) -> Path:
        return self._output_root / _RUNS_REF / run_id

    def _run(self, run_id: str) -> dict[str, Any]:
        path = self._root(run_id) / "run.json"
        if path.is_symlink() or not path.is_file():
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_NOT_FOUND",
                f"capacity bootstrap run is missing: {run_id}",
            )
        run = _validate(read_json(path))
        if run.get("documentKind") != "run":
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                "capacity bootstrap run document kind drifted",
            )
        stable = {key: value for key, value in run.items() if key != "runDigest"}
        if run.get("runDigest") != _digest(stable):
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                "capacity bootstrap run digest drifted",
            )
        return run

    def get(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        state_paths = sorted((self._root(run_id) / "states").glob("*.json"))
        if not state_paths:
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                "capacity bootstrap state is missing",
            )
        states = [_validate(read_json(path)) for path in state_paths]
        if any(state.get("documentKind") != "state" for state in states):
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                "capacity bootstrap state document kind drifted",
            )
        ordinals = [int(state["ordinal"]) for state in states]
        if ordinals != list(range(1, len(states) + 1)):
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                "capacity bootstrap state sequence drifted",
            )
        state = states[-1]
        stable = {key: value for key, value in state.items() if key != "stateDigest"}
        if (
            state.get("stateDigest") != _digest(stable)
            or state.get("runDigest") != run.get("runDigest")
        ):
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                "capacity bootstrap state binding drifted",
            )
        if state["status"] in {"measured", "failed"}:
            evidence_path = self._output_root / str(state["evidenceRef"])
            if (
                evidence_path.is_symlink()
                or not evidence_path.is_file()
                or _file_digest(evidence_path) != state["evidenceDigest"]
            ):
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                    "capacity bootstrap evidence binding drifted",
                )
        return state


class CapacityBootstrapCommandWriter:
    def __init__(self, *, output_root: Path | None = None) -> None:
        self._output_root = Path(output_root or paths.OUTPUT_ROOT).resolve()
        self._query = CapacityBootstrapStatusQuery(output_root=self._output_root)

    def _root(self, run_id: str) -> Path:
        return self._output_root / _RUNS_REF / run_id

    @contextmanager
    def _locked(self, run_id: str) -> Iterator[None]:
        lock_path = self._root(run_id) / ".lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield

    def _write_state(
        self,
        run: Mapping[str, Any],
        *,
        ordinal: int,
        status: str,
        evidence_ref: str | None = None,
        evidence_digest: str | None = None,
        blocker: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        stable: dict[str, Any] = {
            "schema": _SCHEMA,
            "documentKind": "state",
            "bootstrapRunId": run["bootstrapRunId"],
            "ordinal": ordinal,
            "status": status,
            "runRef": f"{_RUNS_REF}/{run['bootstrapRunId']}/run.json",
            "runDigest": run["runDigest"],
            "recordedAt": _now(),
        }
        if evidence_ref is not None:
            stable["evidenceRef"] = evidence_ref
            stable["evidenceDigest"] = evidence_digest
        if blocker is not None:
            stable["blocker"] = dict(blocker)
        state = _validate({**stable, "stateDigest": _digest(stable)})
        path = self._root(str(run["bootstrapRunId"])) / "states" / (
            f"{ordinal:06d}-{status}.json"
        )
        return _write_create_once(path, state)

    def prepare(
        self,
        *,
        bootstrap_run_id: str,
        host_class: str,
        provider_tier: str,
        semantic_selection_id: str,
        workload_digest: str,
        retry_of: str | None = None,
    ) -> dict[str, Any]:
        policy, policy_path, policy_digest = load_measurement_safety_policy()
        if semantic_selection_id not in policy["allowedSemanticSelectionIds"]:
            raise CapacityBootstrapError(
                "DATA.CAPACITY.BOOTSTRAP_AUTHORITY_REJECTED",
                "semantic selection is not authorized for capacity bootstrap",
            )
        stable: dict[str, Any] = {
            "schema": _SCHEMA,
            "documentKind": "run",
            "bootstrapRunId": bootstrap_run_id,
            "authority": "measurement_only",
            "hostClass": host_class,
            "providerTier": provider_tier,
            "semanticSelectionId": semantic_selection_id,
            "workload": {
                **policy["workload"],
                "digest": workload_digest,
            },
            "policyRef": policy_path.relative_to(paths.REPO_ROOT).as_posix(),
            "policyDigest": policy_digest,
            "preparedAt": _now(),
        }
        if retry_of:
            stable["retryOf"] = retry_of
        root = self._root(bootstrap_run_id)
        with self._locked(bootstrap_run_id):
            run_path = root / "run.json"
            if run_path.is_file():
                existing = self._query._run(bootstrap_run_id)
                immutable = {
                    key: value
                    for key, value in existing.items()
                    if key not in {"preparedAt", "runDigest"}
                }
                candidate = {
                    key: value
                    for key, value in stable.items()
                    if key != "preparedAt"
                }
                if immutable != candidate:
                    raise CapacityBootstrapError(
                        "DATA.CAPACITY.BOOTSTRAP_CREATE_ONCE_CONFLICT",
                        "capacity bootstrap identity already has different intent",
                    )
                if not tuple((root / "states").glob("*.json")):
                    return self._write_state(
                        existing, ordinal=1, status="prepared"
                    )
                return self._query.get(bootstrap_run_id)
            run = _validate({**stable, "runDigest": _digest(stable)})
            _write_create_once(run_path, run)
            return self._write_state(run, ordinal=1, status="prepared")

    def run(self, bootstrap_run_id: str) -> dict[str, Any]:
        with self._locked(bootstrap_run_id):
            current = self._query.get(bootstrap_run_id)
            if current["status"] == "running":
                return current
            if current["status"] != "prepared":
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_INVALID_TRANSITION",
                    f"cannot run capacity bootstrap from {current['status']}",
                )
            return self._write_state(
                self._query._run(bootstrap_run_id), ordinal=2, status="running"
            )

    def finalize(self, bootstrap_run_id: str, *, evidence_path: Path) -> dict[str, Any]:
        with self._locked(bootstrap_run_id):
            current = self._query.get(bootstrap_run_id)
            if current["status"] in {"measured", "failed"}:
                return current
            if current["status"] != "running":
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_INVALID_TRANSITION",
                    f"cannot finalize capacity bootstrap from {current['status']}",
                )
            run = self._query._run(bootstrap_run_id)
            try:
                source = read_json(Path(evidence_path))
            except (OSError, TypeError, ValueError) as exc:
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID", str(exc)
                ) from exc
            if not isinstance(source, dict):
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID",
                    "capacity bootstrap evidence must be an object",
                )
            stable = {key: value for key, value in source.items() if key != "evidenceDigest"}
            evidence = _validate({**stable, "evidenceDigest": _digest(stable)})
            for field in (
                "bootstrapRunId", "authority", "hostClass", "providerTier",
                "semanticSelectionId", "workload", "policyDigest",
            ):
                expected = run[field] if field in run else "measurement_only"
                if evidence.get(field) != expected:
                    raise CapacityBootstrapError(
                        "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_DRIFT",
                        f"capacity bootstrap evidence {field} drifted",
                    )
            object_refs = [row["objectRef"] for row in evidence["objectTimings"]]
            if len(set(object_refs)) != 100:
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID",
                    "capacity bootstrap requires 100 unique object timings",
                )
            passed = (
                evidence["fleetReport"]["outcome"] == "passed"
                and all(row["outcome"] == "succeeded" for row in evidence["objectTimings"])
                and evidence["blockers"] == []
            )
            if not passed and not evidence["blockers"]:
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_EVIDENCE_INVALID",
                    "failed capacity bootstrap evidence requires a typed blocker",
                )
            destination = self._root(bootstrap_run_id) / "evidence.json"
            _write_create_once(destination, evidence)
            evidence_ref = destination.relative_to(self._output_root).as_posix()
            evidence_digest = _file_digest(destination)
            blocker = None if passed else evidence["blockers"][0]
            return self._write_state(
                run,
                ordinal=int(current["ordinal"]) + 1,
                status="measured" if passed else "failed",
                evidence_ref=evidence_ref,
                evidence_digest=evidence_digest,
                blocker=blocker,
            )

    def cancel(self, bootstrap_run_id: str, *, reason: str) -> dict[str, Any]:
        with self._locked(bootstrap_run_id):
            current = self._query.get(bootstrap_run_id)
            if current["status"] == "canceled":
                return current
            if current["status"] in _TERMINAL:
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_INVALID_TRANSITION",
                    f"cannot cancel capacity bootstrap from {current['status']}",
                )
            blocker = {
                "code": "DATA.CAPACITY.BOOTSTRAP_OPERATOR_CANCELED",
                "recovery": "operator_canceled",
            }
            if not str(reason or "").strip():
                raise CapacityBootstrapError(
                    "DATA.CAPACITY.BOOTSTRAP_CANCEL_REASON_REQUIRED",
                    "capacity bootstrap cancel reason is required",
                )
            return self._write_state(
                self._query._run(bootstrap_run_id),
                ordinal=int(current["ordinal"]) + 1,
                status="canceled",
                blocker=blocker,
            )


@dataclass(frozen=True)
class CapacityBootstrapComposition:
    command_writer: CapacityBootstrapCommandWriter
    status_query: CapacityBootstrapStatusQuery


def build_capacity_bootstrap_composition(
    *, output_root: Path | None = None
) -> CapacityBootstrapComposition:
    query = CapacityBootstrapStatusQuery(output_root=output_root)
    return CapacityBootstrapComposition(
        command_writer=CapacityBootstrapCommandWriter(output_root=output_root),
        status_query=query,
    )


__all__ = [
    "CapacityBootstrapCommandWriter",
    "CapacityBootstrapComposition",
    "CapacityBootstrapError",
    "CapacityBootstrapStatusQuery",
    "build_capacity_bootstrap_composition",
    "load_measurement_safety_policy",
]
