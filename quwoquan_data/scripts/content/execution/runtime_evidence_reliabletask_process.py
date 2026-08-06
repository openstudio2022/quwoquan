"""Frozen-binary process boundary for ReliableTask read-only observations."""
from __future__ import annotations

import hashlib
import os
import re
import signal
import stat
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from core.paths import OUTPUT_ROOT, REPO_ROOT

from content.execution.reliabletask_transport import ReliableTaskFleetTransport
from content.execution.runtime_evidence_contract import RuntimeEvidenceError


class ReliableTaskObserverError(RuntimeEvidenceError):
    """Typed fail-closed result from the governed observer process boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def observer_error(suffix: str, message: str) -> ReliableTaskObserverError:
    return ReliableTaskObserverError(
        f"DATA.RUNTIME_EVIDENCE.RELIABLETASK_OBSERVER_{suffix}",
        message,
    )


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OBSERVER_BINARY_CACHE_REF = Path(
    "data/local/cache/reliabletask-observer-binaries"
)
_OBSERVER_BINARY_NAME = "data-content-worker"
_OBSERVER_TERMINATION_GRACE_SECONDS = 0.5
OBSERVER_BINARY_REF_ENV = "QWQ_RELIABLETASK_OBSERVER_BINARY_REF"
OBSERVER_BINARY_SHA256_ENV = "QWQ_RELIABLETASK_OBSERVER_BINARY_SHA256"
_CAMPAIGN_CONTEXT_ENV = {
    "root_execution_id": "QWQ_CAMPAIGN_ROOT_EXECUTION_ID",
    "run_id": "QWQ_CAMPAIGN_RUN_ID",
    "generation": "QWQ_CAMPAIGN_GENERATION",
    "fencing_token": "QWQ_CAMPAIGN_FENCING_TOKEN",
    "carrier": "QWQ_CAMPAIGN_CARRIER",
    "execution_id": "QWQ_CAMPAIGN_EXECUTION_ID",
}


@dataclass(frozen=True, slots=True)
class ReliableTaskObserverBinaryBinding:
    """Immutable output-relative executable identity frozen per execution."""

    ref: str
    sha256: str

    def as_document(self) -> dict[str, str]:
        return {
            "observerBinaryRef": self.ref,
            "observerBinarySha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class PreparedReliableTaskObserverBinary:
    """Controller-built observer plus its canonical source/build identity."""

    binding: ReliableTaskObserverBinaryBinding
    source_digest: str
    build_attestation_digest: str


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _observer_source_digest() -> str:
    """Over-invalidate safely when any Service Go source or module input changes."""
    service_root = REPO_ROOT / "quwoquan_service"
    inputs = [service_root / "go.mod", service_root / "go.sum"]
    inputs.extend(
        path
        for path in sorted(service_root.rglob("*.go"))
        if not path.name.endswith("_test.go")
    )
    digest = hashlib.sha256()
    for path in inputs:
        if not path.is_file() or path.is_symlink():
            raise observer_error(
                "BINARY_SOURCE_INVALID",
                "repository Service build input is missing or symbolic",
            )
        relative = path.relative_to(service_root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _binary_cache_ref(source_digest: str) -> str:
    return (
        _OBSERVER_BINARY_CACHE_REF
        / source_digest.removeprefix("sha256:")
        / _OBSERVER_BINARY_NAME
    ).as_posix()


def validate_frozen_observer_binary(
    binding: ReliableTaskObserverBinaryBinding,
) -> Path:
    if _DIGEST.fullmatch(binding.sha256) is None:
        raise observer_error("BINARY_BINDING_INVALID", "binary sha256 is invalid")
    relative = Path(binding.ref)
    if (
        not binding.ref
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.name != _OBSERVER_BINARY_NAME
        or not relative.is_relative_to(_OBSERVER_BINARY_CACHE_REF)
    ):
        raise observer_error(
            "BINARY_BINDING_INVALID",
            "binary ref must be canonical output-root-relative data-content-worker",
        )
    output_root = OUTPUT_ROOT.absolute()
    path = output_root / relative
    current = path
    while current != output_root:
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise observer_error(
                "BINARY_UNAVAILABLE",
                "frozen observer binary path is unavailable",
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise observer_error(
                "BINARY_UNSAFE",
                "frozen observer binary path cannot contain symbolic links",
            )
        current = current.parent
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o111 == 0:
        raise observer_error(
            "BINARY_UNSAFE",
            "frozen observer binary must be a regular executable file",
        )
    if _file_sha256(path) != binding.sha256:
        raise observer_error("BINARY_DIGEST_DRIFT", "frozen observer binary drift")
    return path


def load_frozen_observer_binary_binding() -> ReliableTaskObserverBinaryBinding:
    """Load the plan-bound observer passed into a frozen campaign lane."""
    ref = str(os.environ.get(OBSERVER_BINARY_REF_ENV) or "").strip()
    sha256 = str(os.environ.get(OBSERVER_BINARY_SHA256_ENV) or "").strip()
    if not ref and not sha256:
        raise observer_error(
            "BINARY_BINDING_MISSING",
            "campaign lane observer binary binding is missing",
        )
    if not ref or not sha256:
        raise observer_error(
            "BINARY_BINDING_INVALID",
            "controller observer binary ref and sha256 must be provided together",
        )
    _validate_prebound_campaign_context()
    binding = ReliableTaskObserverBinaryBinding(ref=ref, sha256=sha256)
    validate_frozen_observer_binary(binding)
    return binding


def _validate_prebound_campaign_context() -> None:
    """Prove the prebound binary belongs to this active fenced lane process."""
    values = {
        name: str(os.environ.get(environment_name) or "").strip()
        for name, environment_name in _CAMPAIGN_CONTEXT_ENV.items()
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise observer_error(
            "BINARY_BINDING_INVALID",
            "controller observer binary requires a complete campaign fence",
        )
    try:
        generation = int(values["generation"])
    except ValueError as exc:
        raise observer_error(
            "BINARY_BINDING_INVALID",
            "controller observer binary campaign generation is invalid",
        ) from exc
    try:
        from content.execution.campaign_runtime import (
            assert_campaign_fence,
            read_lane_checkpoint,
        )
        from content.execution.campaign_workspace import CampaignRuntimePaths

        runtime = CampaignRuntimePaths.defaults()
        snapshot = assert_campaign_fence(
            runtime,
            values["root_execution_id"],
            run_id=values["run_id"],
            generation=generation,
            fencing_token=values["fencing_token"],
        )
        checkpoint = read_lane_checkpoint(
            runtime,
            values["root_execution_id"],
            values["carrier"],
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise observer_error(
            "BINARY_BINDING_INVALID",
            "controller observer binary campaign fence is unavailable",
        ) from exc
    if (
        str(snapshot.get("status") or "")
        in {"blocked", "interrupted", "succeeded", "succeeded_partial"}
        or snapshot.get("finishedAt")
        or not isinstance(checkpoint, Mapping)
        or str(checkpoint.get("runId") or "") != values["run_id"]
        or int(checkpoint.get("generation") or 0) != generation
        or str(checkpoint.get("fencingToken") or "")
        != values["fencing_token"]
        or str(checkpoint.get("executionId") or "")
        != values["execution_id"]
        or str(checkpoint.get("carrier") or "") != values["carrier"]
        or str(checkpoint.get("status") or "") != "running"
        or int(checkpoint.get("pid") or 0) != os.getpid()
    ):
        raise observer_error(
            "BINARY_BINDING_INVALID",
            "controller observer binary lane fence does not match this process",
        )


def observer_build_attestation_digest(
    *,
    source_digest: str,
    binding: ReliableTaskObserverBinaryBinding,
) -> str:
    payload = (
        "data-content-worker-observer-build\n"
        f"{source_digest}\n"
        f"{binding.ref}\n"
        f"{binding.sha256}\n"
        "go build -trimpath -buildvcs=false\n"
        "./services/content-service/cmd/data-content-worker\n"
        "CGO_ENABLED=0\n"
        "GOPROXY=off"
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def prepare_controller_observer_binary() -> PreparedReliableTaskObserverBinary:
    """Build or reuse the canonical binary only from controller Service source."""
    if os.environ.get(OBSERVER_BINARY_REF_ENV) or os.environ.get(
        OBSERVER_BINARY_SHA256_ENV
    ):
        raise observer_error(
            "CONTROLLER_ENV_INVALID",
            "campaign controller cannot inherit a lane observer binding",
        )
    source_digest = _observer_source_digest()
    ref = _binary_cache_ref(source_digest)
    path = OUTPUT_ROOT / ref
    if path.exists() or path.is_symlink():
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise observer_error(
                "BINARY_UNAVAILABLE",
                "frozen observer binary path is unavailable",
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise observer_error(
                "BINARY_UNSAFE",
                "frozen observer binary must be a regular non-symbolic file",
            )
        candidate = ReliableTaskObserverBinaryBinding(
            ref=ref,
            sha256=_file_sha256(path),
        )
        validate_frozen_observer_binary(candidate)
        return PreparedReliableTaskObserverBinary(
            binding=candidate,
            source_digest=source_digest,
            build_attestation_digest=observer_build_attestation_digest(
                source_digest=source_digest,
                binding=candidate,
            ),
        )

    go_executable = which("go")
    if not go_executable:
        raise observer_error(
            "BINARY_PREPARE_FAILED",
            "Go toolchain is unavailable for the canonical prepare step",
        )
    resolved_go = Path(go_executable).resolve(strict=True)
    cache_root = OUTPUT_ROOT / "env/repo/local/reliabletask-observer-build"
    cache_root.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="data-content-worker-",
        dir=cache_root,
    ) as temporary:
        staged = Path(temporary) / _OBSERVER_BINARY_NAME
        go_environment = {
            "HOME": str(Path.home()),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        try:
            module_cache_probe = subprocess.run(
                [str(resolved_go), "env", "GOMODCACHE"],
                cwd=REPO_ROOT / "quwoquan_service",
                env=go_environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise observer_error(
                "BINARY_PREPARE_FAILED",
                "Go module cache probe could not start",
            ) from exc
        module_cache = Path(module_cache_probe.stdout.strip())
        if (
            module_cache_probe.returncode != 0
            or not module_cache.is_absolute()
            or not module_cache.is_dir()
        ):
            raise observer_error(
                "BINARY_PREPARE_FAILED",
                "Go module cache is unavailable for the canonical prepare step",
            )
        build_environment = {
            "CGO_ENABLED": "0",
            "GOCACHE": str(cache_root / "go-build"),
            "GOMODCACHE": str(module_cache),
            "GOPROXY": "off",
            "HOME": str(cache_root / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        for directory in (
            Path(build_environment["GOCACHE"]),
            Path(build_environment["HOME"]),
        ):
            directory.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                [
                    str(resolved_go),
                    "build",
                    "-trimpath",
                    "-buildvcs=false",
                    "-o",
                    str(staged),
                    "./services/content-service/cmd/data-content-worker",
                ],
                cwd=REPO_ROOT / "quwoquan_service",
                env=build_environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise observer_error(
                "BINARY_PREPARE_FAILED",
                "canonical observer binary build could not start",
            ) from exc
        if completed.returncode != 0 or not staged.is_file():
            raise observer_error(
                "BINARY_PREPARE_FAILED",
                f"canonical observer binary build exited with status {completed.returncode}",
            )
        staged.chmod(0o755)
        binding = ReliableTaskObserverBinaryBinding(
            ref=ref,
            sha256=_file_sha256(staged),
        )
        try:
            os.link(staged, path)
        except FileExistsError:
            existing = ReliableTaskObserverBinaryBinding(
                ref=ref,
                sha256=_file_sha256(path),
            )
            validate_frozen_observer_binary(existing)
            if existing.sha256 != binding.sha256:
                raise observer_error(
                    "BINARY_DIGEST_DRIFT",
                    "concurrent canonical observer binary build drift",
                )
            binding = existing
        except OSError as exc:
            raise observer_error(
                "BINARY_PREPARE_FAILED",
                "canonical observer binary could not be frozen",
            ) from exc
    validate_frozen_observer_binary(binding)
    return PreparedReliableTaskObserverBinary(
        binding=binding,
        source_digest=source_digest,
        build_attestation_digest=observer_build_attestation_digest(
            source_digest=source_digest,
            binding=binding,
        ),
    )


def observer_command(
    binding: ReliableTaskObserverBinaryBinding,
) -> tuple[list[str], Path]:
    """Resolve only the digest-bound executable frozen in the envelope."""
    return [
        validate_frozen_observer_binary(binding).as_posix()
    ], REPO_ROOT / "quwoquan_service"


def _terminate_observer_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        process.wait(timeout=_OBSERVER_TERMINATION_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        return
    try:
        process.wait(timeout=_OBSERVER_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return


def run_observer_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
) -> str:
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise observer_error(
            "SPAWN_FAILED",
            "read-only observer process could not start",
        ) from exc
    try:
        stdout, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_observer_process(process)
        raise observer_error(
            "DEADLINE_EXCEEDED",
            "read-only observer exceeded its governed hard deadline",
        ) from exc
    if process.returncode != 0:
        raise observer_error(
            "PROCESS_FAILED",
            f"read-only observer exited with status {process.returncode}",
        )
    return stdout


def observer_timeout_seconds() -> float:
    from core.runtime_policy import active_runtime_policy

    return float(
        active_runtime_policy().runtime_evidence.process_inspection_timeout_seconds
    )


def observer_environment(
    transport: ReliableTaskFleetTransport,
) -> dict[str, str]:
    runtime_root = OUTPUT_ROOT / "data/local/cache/reliabletask-observer-runtime"
    home = runtime_root / "home"
    cache = runtime_root / "cache"
    temporary = runtime_root / "tmp"
    for directory in (home, cache, temporary):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "XDG_CACHE_HOME": str(cache),
        "TMPDIR": str(temporary),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "QWQ_DATA_FLEET_MONGO_URI": transport.mongo_uri,
        "QWQ_DATA_FLEET_REDIS_ADDR": transport.redis_addr,
    }


__all__ = [
    "OBSERVER_BINARY_REF_ENV",
    "OBSERVER_BINARY_SHA256_ENV",
    "PreparedReliableTaskObserverBinary",
    "ReliableTaskObserverBinaryBinding",
    "ReliableTaskObserverError",
    "load_frozen_observer_binary_binding",
    "observer_build_attestation_digest",
    "observer_command",
    "observer_environment",
    "observer_error",
    "observer_timeout_seconds",
    "prepare_controller_observer_binary",
    "run_observer_command",
    "validate_frozen_observer_binary",
]
