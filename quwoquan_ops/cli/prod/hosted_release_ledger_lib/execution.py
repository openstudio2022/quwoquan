"""DEC-015现役ledger的execution内核；仅本地安装authority可见的受限guard。

不安装helper、不持跨plane凭据；跨主机投递尚未接入，不签release/absence。
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from .contract import (
    EXECUTION_ACTIONS, EXECUTION_ACTION_PARAMETERS, EXECUTION_IDENTITY_RELATIVE_PATH,
    EXECUTION_INVENTORY_FIELDS, EXECUTION_PLACEMENT_FIELDS, EXECUTION_REQUEST_SCHEMA,
    EXECUTION_RESULT_SCHEMA, EXECUTION_STEP_FIELDS, SHA256_RE, _canonical_bytes,
)
from .ledger_store import _atomic_write, _validated_readback


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identity(value: Any) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError("EXECUTION.INVALID: exact digest required")
    return value


def _safe(path: Path, *, directory: bool) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("EXECUTION.PATH_INVALID")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("EXECUTION.SYMLINK")
    info = path.lstat()
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError("EXECUTION.PATH_AUTHORITY_INVALID")
    return path


def _read(path: Path) -> dict:
    _safe(path, directory=False)
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("EXECUTION.INVALID: object required")
    return value


@contextlib.contextmanager
def _locked(path: Path):
    _safe(path, directory=False)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _held(fd, path)
        yield fd
        _held(fd, path)
    finally:
        os.close(fd)


def _held(fd: int, path: Path) -> None:
    _safe(path, directory=False)
    opened, current = os.fstat(fd), path.stat()
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise RuntimeError("EXECUTION.LOCK_LOST")


class ExecutionSlot:
    """使用既有ledger锁保留durable execution generation，不从TTL恢复。"""

    def __init__(self, ledger_root: Path):
        self.root = _safe(ledger_root, directory=True)
        self.directory = _safe(self.root / "execution", directory=True)
        self.history = _safe(self.directory / "history", directory=True)
        self.inventory_path = self.directory / "inventory.json"
        self.state_path = self.directory / "slot.json"
        self.lock_path = _safe(self.root / ".ledger.lock", directory=False)
        self.inventory = _read(self.inventory_path)
        self._validate_inventory()
        self.inventory_digest = _digest(self.inventory)

    def _validate_inventory(self) -> None:
        inventory = self.inventory
        if set(inventory) != EXECUTION_INVENTORY_FIELDS or inventory["environment"] != "prod" or inventory["target"] != "prod-hosted":
            raise ValueError("EXECUTION.INVENTORY_INVALID")
        _identity(inventory["sourceDigest"])
        placements = inventory["placements"]
        if not isinstance(placements, list) or not placements:
            raise ValueError("EXECUTION.INVENTORY_EMPTY")
        seen, slots = set(), set()
        for item in placements:
            if not isinstance(item, dict) or set(item) != EXECUTION_PLACEMENT_FIELDS:
                raise ValueError("EXECUTION.PLACEMENT_INVALID")
            if item["plane"] not in {"service", "edge"} or item["instance"] not in {"gray", "prod"}:
                raise ValueError("EXECUTION.PLACEMENT_INVALID")
            if not all(isinstance(item[key], str) and item[key] for key in item):
                raise ValueError("EXECUTION.PLACEMENT_INVALID")
            key = (item["hostId"], item["plane"], item["instance"])
            if item["id"] in seen or key in slots:
                raise ValueError("EXECUTION.PLACEMENT_DUPLICATE")
            seen.add(item["id"]); slots.add(key)
            runtime = _safe(Path(item["runtimeRoot"]), directory=True)
            guard = _safe(Path(item["guardRoot"]), directory=True)
            if guard != runtime / "process/execution-guard":
                raise ValueError("EXECUTION.GUARD_PATH_INVALID")
        if placements != sorted(placements, key=lambda item: (item["hostId"], item["plane"], item["instance"], item["replicaId"])):
            raise ValueError("EXECUTION.INVENTORY_ORDER_INVALID")
        if inventory["authorityHostId"] not in {item["hostId"] for item in placements}:
            raise ValueError("EXECUTION.AUTHORITY_HOST_INVALID")
        for host in {item["hostId"] for item in placements}:
            group = [item for item in placements if item["hostId"] == host]
            if {(item["plane"], item["instance"]) for item in group} != {(p, i) for p in ("service", "edge") for i in ("gray", "prod")} or len({item["replicaId"] for item in group}) != 1:
                raise ValueError("EXECUTION.INVENTORY_INCOMPLETE")

    def _state(self) -> dict:
        if _digest(_read(self.inventory_path)) != self.inventory_digest:
            raise RuntimeError("EXECUTION.INVENTORY_DRIFT")
        state = _read(self.state_path)
        if (type(state.get("generation")) is not int or state["generation"] < 0
                or type(state.get("revision")) is not int or state["revision"] < 0
                or state.get("status") not in {"held", "closed"}):
            raise RuntimeError("EXECUTION.SLOT_STATE_INVALID")
        for path in self.history.iterdir():
            record = _read(path)
            if path.name != _digest(record).removeprefix("sha256:") + ".json" or record.get("revision", -1) > state["revision"]:
                raise RuntimeError("EXECUTION.HISTORY_RECONCILE_REQUIRED")
        if state["revision"] and not (self.history / (_digest(state).removeprefix("sha256:") + ".json")).is_file():
            raise RuntimeError("EXECUTION.HISTORY_MISSING")
        return state

    def _write(self, value: dict) -> None:
        value["revision"] = self._state()["revision"] + 1
        raw = _canonical_bytes(value) + b"\n"
        history_path = self.history / (_digest(value).removeprefix("sha256:") + ".json")
        if history_path.exists():
            if _read(history_path) != value:
                raise RuntimeError("EXECUTION.HISTORY_CONFLICT")
        else:
            fd = os.open(history_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(raw); out.flush(); os.fsync(out.fileno())
        _atomic_write(self.state_path, raw)

    def acquire(self, *, attempt_id: str, expected_execution_generation: int, expected_release_generation: int) -> dict:
        _identity(attempt_id)
        if (type(expected_execution_generation) is not int or expected_execution_generation < 0
                or type(expected_release_generation) is not int or expected_release_generation < 0):
            raise ValueError("EXECUTION.GENERATION_INVALID")
        with _locked(self.lock_path):
            state = self._state()
            if state.get("status") != "closed" or state.get("generation") != expected_execution_generation:
                raise RuntimeError("EXECUTION.BUSY_OR_STALE: reconcile required; timeout is not release")
            release = _validated_readback(self.root, "prod-stack")["state"]
            if int(release.get("generation") or 0) != expected_release_generation:
                raise RuntimeError("EXECUTION.RELEASE_GENERATION_DRIFT")
            state = {"status": "held", "generation": expected_execution_generation + 1,
                     "attemptId": attempt_id, "releaseGeneration": expected_release_generation,
                     "inventoryDigest": self.inventory_digest, "participants": [], "steps": {}, "phase": "executing", "observationDigest": "", "humanWinnerDigest": ""}
            self._write(state)
            return state


    def _owner(self, state: dict, attempt: str, generation: int) -> None:
        if state.get("status") != "held" or state.get("attemptId") != attempt or state.get("generation") != generation:
            raise RuntimeError("EXECUTION.OWNER_MISMATCH")

    def register(self, request: dict) -> str:
        from .execution_guard import _validate_request
        _validate_request(request)
        if request["releaseGeneration"] != self._state().get("releaseGeneration"):
            raise RuntimeError("EXECUTION.RELEASE_GENERATION_DRIFT")
        with _locked(self.lock_path):
            state = self._state()
            self._owner(state, request["attemptId"], request["executionGeneration"])
            expected = {item["id"] for item in self.inventory["placements"]}
            if request["action"] != "guard-prepare":
                if set(state["participants"]) != expected:
                    raise RuntimeError("EXECUTION.PARTICIPANTS_INCOMPLETE")
            if request["action"] != "guard-prepare":
                self._participants_held(state)
            if request["action"] == "ledger-activation-cas" and state.get("phase") != "consumed":
                raise RuntimeError("EXECUTION.HUMAN_WINNER_NOT_CONTINUOUS")
            if request["inventoryDigest"] != self.inventory_digest or request["placementId"] not in expected:
                raise ValueError("EXECUTION.STEP_SCOPE_INVALID")
            key = request["placementId"] + ":" + str(request["sequence"])
            prior = state["steps"].get(key)
            if prior is not None and prior.get("request") != request:
                raise RuntimeError("EXECUTION.STEP_CONFLICT")
            sequences = [item["request"]["sequence"] for item in state["steps"].values() if item["request"]["placementId"] == request["placementId"]]
            if prior is None and request["sequence"] != max(sequences, default=0) + 1:
                raise RuntimeError("EXECUTION.SEQUENCE_GAP")
            state["steps"][key] = {"request": dict(request), "requestDigest": _digest(request), "result": None}
            self._write(state)
            return _digest(request)

    def _participants_held(self, state: dict) -> None:
        for item in self.inventory["placements"]:
            guard_root = Path(item["guardRoot"])
            journal = guard_root / "journal.json"
            guard = _read(journal if journal.is_file() else guard_root / "guard.json")
            if not ((guard.get("status") == "held" or guard.get("mode") == "held") and guard.get("generation", guard.get("lastGeneration")) == state["generation"]
                    and guard.get("attemptId") == state["attemptId"]):
                raise RuntimeError("EXECUTION.PARTICIPANT_NOT_HELD")
            try:
                with _locked(guard_root / "guard.lock"):
                    pass
            except BlockingIOError:
                continue
            raise RuntimeError("EXECUTION.PARTICIPANT_LOCK_LOST")

    def acknowledge(self, result: dict) -> None:
        required = {"schema", "requestDigest", "placementId", "guardIncarnation", "sequence", "status", "effectDigest", "processGroup", "returnCode", "terminal", "reconciled"}
        if set(result) != required or result.get("schema") != EXECUTION_RESULT_SCHEMA or not result.get("terminal"):
            raise ValueError("EXECUTION.RESULT_INVALID")
        _identity(result["requestDigest"]); _identity(result["effectDigest"])
        with _locked(self.lock_path):
            state = self._state()
            key = result["placementId"] + ":" + str(result["sequence"])
            step = state["steps"].get(key)
            if not step or step["requestDigest"] != result["requestDigest"] or step["request"]["guardIncarnation"] != result["guardIncarnation"]:
                raise RuntimeError("EXECUTION.RESULT_BINDING_INVALID")
            if step["result"] is not None and step["result"] != result:
                raise RuntimeError("EXECUTION.RESULT_CONFLICT")
            step["result"] = dict(result)
            if step["request"]["action"] == "guard-prepare" and result["status"] == "completed":
                order = [item["id"] for item in self.inventory["placements"]]
                if state["participants"] != order[:len(state["participants"])] or order[len(state["participants"])] != result["placementId"]:
                    raise RuntimeError("EXECUTION.PREPARE_ORDER_INVALID")
                state["participants"].append(result["placementId"])
            if step["request"]["action"].startswith("observe-"):
                observations = sorted(x["result"]["effectDigest"] for x in state["steps"].values() if x.get("result") and x["request"]["action"].startswith("observe-"))
                state["observationDigest"] = _digest(observations); state["phase"] = "observing"
            self._write(state)

    def consume_human(self, *, attempt_id: str, generation: int, observation_digest: str, winner_digest: str) -> dict:
        _identity(observation_digest); _identity(winner_digest)
        with _locked(self.lock_path):
            state = self._state(); self._owner(state, attempt_id, generation); self._participants_held(state)
            if state.get("phase") != "observing" or state.get("observationDigest") != observation_digest:
                raise RuntimeError("EXECUTION.OBSERVATION_RELEASED_OR_DRIFTED")
            if state.get("humanWinnerDigest") and state["humanWinnerDigest"] != winner_digest:
                raise RuntimeError("EXECUTION.HUMAN_WINNER_CONFLICT")
            state["humanWinnerDigest"] = winner_digest; state["phase"] = "consumed"; self._write(state); return state

    def close(self, *, attempt_id: str, generation: int) -> None:
        with _locked(self.lock_path):
            state = self._state(); self._owner(state, attempt_id, generation)
            if any(not step.get("result") or not step["result"].get("terminal") for step in state["steps"].values()):
                raise RuntimeError("EXECUTION.RESULTS_INCOMPLETE")
            for item in reversed(self.inventory["placements"]):
                path = Path(item["guardRoot"])
                with _locked(path / "guard.lock"):
                    guard = _read(path / "guard.json")
                    if guard.get("status") != "closed":
                        raise RuntimeError("EXECUTION.CLOSURE_UNKNOWN")
                    if item["id"] in state["participants"] and (guard.get("attemptId") != attempt_id or guard.get("generation") != generation):
                        raise RuntimeError("EXECUTION.CLOSURE_UNKNOWN")
            state["status"] = "closed"
            self._write(state)


# 固定只读程序，caller不能替换argv、传shell或选择任意文件。
_READ_IDENTITY = "import os,sys; fd=os.open(sys.argv[1], os.O_RDONLY|os.O_NOFOLLOW); b=os.read(fd,65537); os.close(fd); sys.exit(2) if len(b)>65536 else None; sys.stdout.buffer.write(b)"


def _process_group_closed(pgid: int) -> None:
    """只查询本guard记录的组；leader已wait不代表其后代退出。"""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise RuntimeError("EXECUTION.PROCESS_GROUP_CLOSURE_UNKNOWN") from error
    raise RuntimeError("EXECUTION.PROCESS_GROUP_NOT_CLOSED")


class PlaneGuard:
    """本地可信authority可见的核心adapter；远端投递必须另接受限SSH。"""

    def __init__(self, slot: ExecutionSlot, placement_id: str):
        self.slot = slot
        self.placement = next((item for item in slot.inventory["placements"] if item["id"] == placement_id), None)
        if self.placement is None:
            raise ValueError("EXECUTION.UNKNOWN_PLACEMENT")
        self.root = Path(self.placement["guardRoot"])
        self.path = self.root / "guard.json"
        self.lock_path = self.root / "guard.lock"
        self.fd: int | None = None
        self.state: dict = {}

    def prepare(self, *, attempt_id: str, generation: int) -> None:
        with _locked(self.slot.lock_path):
            state = self.slot._state(); self.slot._owner(state, attempt_id, generation)
            order = [item["id"] for item in self.slot.inventory["placements"]]
            if state["participants"] != order[:len(state["participants"])] or len(state["participants"]) >= len(order) or order[len(state["participants"])] != self.placement["id"]:
                raise RuntimeError("EXECUTION.PREPARE_ORDER_INVALID")
            _safe(self.lock_path, directory=False)
            fd = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _held(fd, self.lock_path)
                previous = _read(self.path)
                if previous.get("status") != "closed":
                    raise RuntimeError("EXECUTION.GUARD_RECONCILE_REQUIRED")
                if self.placement["id"] in state["participants"]:
                    raise RuntimeError("EXECUTION.DUPLICATE_PREPARE")
                self.fd = fd
                self.state = {"status": "held", "attemptId": attempt_id, "generation": generation, "steps": {}}
                self._write()
                state["participants"].append(self.placement["id"])
                self.slot._write(state)
            except BaseException:
                self.fd = None
                os.close(fd)
                raise

    def _write(self) -> None:
        _atomic_write(self.path, _canonical_bytes(self.state) + b"\n")

    def _assert_durable_held(self) -> None:
        if self.fd is None:
            raise RuntimeError("EXECUTION.GUARD_NOT_HELD")
        _held(self.fd, self.lock_path)
        if self.state.get("status") != "held" or _read(self.path) != self.state:
            raise RuntimeError("EXECUTION.DURABLE_STATE_DRIFT")

    def execute(self, request: dict, *, timeout_seconds: float = 10) -> dict:
        self._assert_durable_held()
        with _locked(self.slot.lock_path):
            state = self.slot._state()
            self.slot._owner(state, self.state["attemptId"], self.state["generation"])
            self.slot._participants_held(state)
            key = self.placement["id"] + ":" + str(request.get("sequence"))
            registered = state["steps"].get(key)
            if request.get("placementId") != self.placement["id"] or not registered or registered.get("request") != request:
                raise RuntimeError("EXECUTION.UNREGISTERED_STEP")
        step_digest = _digest(request)
        old = self.state["steps"].get(key)
        if old:
            if old["digest"] != step_digest or old["status"] != "completed":
                raise RuntimeError("EXECUTION.STEP_OUTCOME_UNKNOWN")
            return old
        path = _safe(Path(self.placement["runtimeRoot"]) / EXECUTION_IDENTITY_RELATIVE_PATH, directory=False)
        self.state["steps"][key] = {"digest": step_digest, "status": "running"}
        self._write()  # spawn前先durable占位，崩溃不能重试猜没运行。
        child = subprocess.Popen([sys.executable, "-I", "-B", "-c", _READ_IDENTITY, str(path)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.state["steps"][key]["processGroup"] = child.pid
        self._write()
        try:
            output, _ = child.communicate(timeout=timeout_seconds)
            _held(self.fd, self.lock_path)
            if child.returncode != 0:
                raise RuntimeError("EXECUTION.CHILD_FAILED")
            _process_group_closed(child.pid)
            with _locked(self.slot.lock_path):
                state = self.slot._state()
                self.slot._owner(state, self.state["attemptId"], self.state["generation"])
                self.slot._participants_held(state)
            observed = "sha256:" + hashlib.sha256(output).hexdigest()
            if observed != request["materialDigest"]:
                raise RuntimeError("EXECUTION.MATERIAL_DRIFT")
            result = {"digest": step_digest, "status": "completed", "outputDigest": observed,
                      "processGroup": child.pid, "returncode": child.returncode, "admissionEligible": False}
            self.state["steps"][key] = result; self._write()
            return result
        except BaseException:
            # 只回收本guard自己启动的进程组，仍保留running记录要求显式reconcile。
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            for stream in (child.stdout, child.stderr):
                if stream is not None:
                    stream.close()
            raise

    def close(self) -> None:
        self._assert_durable_held()
        if any(item["status"] != "completed" for item in self.state["steps"].values()):
            raise RuntimeError("EXECUTION.GUARD_RECONCILE_REQUIRED")
        self.state["status"] = "closed"; self._write()
        os.close(self.fd); self.fd = None
