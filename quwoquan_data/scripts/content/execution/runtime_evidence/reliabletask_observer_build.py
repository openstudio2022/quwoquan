"""Controller-only preparation of the frozen ReliableTask observer binary."""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path
from shutil import which

from core.paths import OUTPUT_ROOT, REPO_ROOT

from content.execution.runtime_evidence.reliabletask_binary_digest import (
    OBSERVER_BINARY_NAME as _OBSERVER_BINARY_NAME,
)
from content.execution.runtime_evidence.reliabletask_binary_digest import (
    binary_cache_ref as _binary_cache_ref,
)
from content.execution.runtime_evidence.reliabletask_binary_digest import (
    file_sha256 as _file_sha256,
)
from content.execution.runtime_evidence.reliabletask_binary_digest import (
    observer_build_attestation_digest as _derive_build_attestation_digest,
)
from content.execution.runtime_evidence.reliabletask_binary_digest import (
    observer_source_digest as _derive_observer_source_digest,
)
from content.execution.runtime_evidence.reliabletask_process import (
    OBSERVER_BINARY_REF_ENV,
    OBSERVER_BINARY_SHA256_ENV,
    PreparedReliableTaskObserverBinary,
    ReliableTaskObserverBinaryBinding,
    observer_error,
    validate_frozen_observer_binary,
)


def _observer_source_digest() -> str:
    try:
        return _derive_observer_source_digest()
    except OSError as exc:
        raise observer_error(
            "BINARY_SOURCE_INVALID",
            "repository Service build input is missing or symbolic",
        ) from exc


def observer_build_attestation_digest(
    *,
    source_digest: str,
    binding: ReliableTaskObserverBinaryBinding,
) -> str:
    return _derive_build_attestation_digest(
        source_digest=source_digest,
        binary_ref=binding.ref,
        binary_sha256=binding.sha256,
    )


def _observer_build_cache_root(source_digest: str) -> Path:
    return (OUTPUT_ROOT / _binary_cache_ref(source_digest)).parent / "build"


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
    cache_root = _observer_build_cache_root(source_digest)
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
