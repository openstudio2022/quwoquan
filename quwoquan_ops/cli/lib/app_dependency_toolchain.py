"""Resolve App native dependency tools to one self-consistent runtime."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quwoquan_ops.cli.lib.package_reuse.ios_pod_identity import CocoaPodsIdentity

COCOAPODS_ENVIRONMENT_KEYS = (
    "QWQ_COCOAPODS_EXECUTABLE",
    "QWQ_COCOAPODS_VERSION",
    "QWQ_COCOAPODS_EXECUTABLE_DIGEST",
    "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST",
    "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST",
    "QWQ_COCOAPODS_BINDING_SEAL",
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class AppDependencyToolchainError(RuntimeError):
    """A required native dependency tool is absent or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class ResolvedCocoaPodsIdentity:
    """Exact CocoaPods runtime plus its attempt-scoped binding seal."""

    physical: "CocoaPodsIdentity"
    binding_seal: str

    @property
    def executable(self) -> Path:
        executable = self.physical.executable
        if executable is None:
            raise AppDependencyToolchainError(
                "APP.DEPENDENCY.cocoapods_missing: physical executable is absent"
            )
        return executable

    @property
    def version(self) -> str:
        return self.physical.version

    @property
    def executable_digest(self) -> str:
        return self.physical.executable_digest

    @property
    def runtime_environment_digest(self) -> str:
        return self.physical.runtime_environment_digest

    @property
    def command_resolution_digest(self) -> str:
        return self.physical.command_resolution_digest

    def as_dict(self) -> dict[str, str]:
        return self.physical.resolved_dict()

    def as_environment(self) -> dict[str, str]:
        return {
            "QWQ_COCOAPODS_EXECUTABLE": str(self.executable),
            "QWQ_COCOAPODS_VERSION": self.version,
            "QWQ_COCOAPODS_EXECUTABLE_DIGEST": self.executable_digest,
            "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST": (
                self.runtime_environment_digest
            ),
            "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST": (
                self.command_resolution_digest
            ),
            "QWQ_COCOAPODS_BINDING_SEAL": self.binding_seal,
        }


def _inspect(executable: str | Path) -> ResolvedCocoaPodsIdentity:
    from quwoquan_ops.cli.lib.package_reuse.ios_pod_identity import (
        inspect_cocoapods_executable,
    )

    try:
        identity = inspect_cocoapods_executable(executable)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise AppDependencyToolchainError(
            f"APP.DEPENDENCY.cocoapods_mixed: {error}"
        ) from error
    return ResolvedCocoaPodsIdentity(
        physical=identity,
        binding_seal=identity.binding_seal,
    )


def resolve_cocoapods_identity(
    candidate: str | Path = "",
    *,
    search_path: str | None = None,
) -> ResolvedCocoaPodsIdentity:
    """Resolve one physical CocoaPods executable and return its complete identity."""

    declared = str(candidate).strip()
    ambient = shutil.which(
        "pod",
        path=os.environ.get("PATH", "") if search_path is None else search_path,
    )
    if not declared and not ambient:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_missing: pod executable not found"
        )
    declared_identity = _inspect(declared) if declared else None
    ambient_identity = None
    if ambient:
        ambient_physical = Path(ambient).expanduser().resolve(strict=True)
        if declared_identity is None or ambient_physical != declared_identity.executable:
            ambient_identity = _inspect(ambient_physical)
    if (
        declared_identity is not None
        and ambient_identity is not None
        and declared_identity.as_dict() != ambient_identity.as_dict()
    ):
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: declared executable differs from PATH"
        )
    selected = declared_identity or ambient_identity
    if selected is None:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_missing: pod executable not found"
        )
    return selected


def resolve_cocoapods_executable(candidate: str = "") -> str:
    """Compatibility projection of :func:`resolve_cocoapods_identity`."""

    return str(resolve_cocoapods_identity(candidate).executable)


def cocoapods_environment(
    identity: ResolvedCocoaPodsIdentity,
    *,
    base: Mapping[str, str],
) -> dict[str, str]:
    """Project an exact CocoaPods binding and prepend its physical directory."""

    environment = {str(key): str(value) for key, value in base.items()}
    environment.update(identity.as_environment())
    directory = str(identity.executable.parent)
    entries = [
        item
        for item in str(environment.get("PATH") or "").split(os.pathsep)
        if item and item != directory
    ]
    environment["PATH"] = os.pathsep.join((directory, *entries))
    return environment


def cocoapods_identity_from_environment(
    environment: Mapping[str, str],
    *,
    inspect_physical: bool = True,
) -> ResolvedCocoaPodsIdentity:
    """Validate a complete QWQ binding and optionally reinspect its executable."""

    values = {
        key: str(environment.get(key) or "").strip()
        for key in COCOAPODS_ENVIRONMENT_KEYS
    }
    present = {key for key, value in values.items() if value}
    if not present:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_missing: CocoaPods identity is absent"
        )
    if present != set(COCOAPODS_ENVIRONMENT_KEYS):
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: CocoaPods identity is incomplete"
        )
    if any(
        not _DIGEST.fullmatch(values[key])
        for key in COCOAPODS_ENVIRONMENT_KEYS[2:]
    ):
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: CocoaPods digest or seal is invalid"
        )
    executable = Path(values["QWQ_COCOAPODS_EXECUTABLE"])
    if not executable.is_absolute() or str(executable) != values[
        "QWQ_COCOAPODS_EXECUTABLE"
    ]:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: CocoaPods executable is not literal"
        )
    if not inspect_physical:
        from quwoquan_ops.cli.lib.package_reuse.ios_pod_identity import CocoaPodsIdentity

        physical = CocoaPodsIdentity(
            executable=executable,
            version=values["QWQ_COCOAPODS_VERSION"],
            executable_digest=values["QWQ_COCOAPODS_EXECUTABLE_DIGEST"],
            runtime_environment_digest=values[
                "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST"
            ],
            command_resolution_digest=values[
                "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST"
            ],
        )
        observed = ResolvedCocoaPodsIdentity(
            physical=physical,
            binding_seal=physical.binding_seal,
        )
        if observed.as_environment() != values:
            raise AppDependencyToolchainError(
                "APP.DEPENDENCY.cocoapods_mixed: CocoaPods binding seal drifted"
            )
        return observed
    observed = _inspect(values["QWQ_COCOAPODS_EXECUTABLE"])
    if observed.as_environment() != values:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: CocoaPods identity drifted"
        )
    return observed


def validate_cocoapods_child_environment(
    environment: Mapping[str, str],
) -> tuple[ResolvedCocoaPodsIdentity, dict[str, str]]:
    """Require QWQ identity and prove incoming PATH resolves that physical pod."""

    identity = cocoapods_identity_from_environment(environment)
    incoming_path = str(environment.get("PATH") or "")
    resolved = shutil.which("pod", path=incoming_path)
    if not resolved:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_missing: pod is absent from child PATH"
        )
    try:
        physical = Path(resolved).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: child PATH pod is invalid"
        ) from error
    if physical != identity.executable:
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: child PATH resolves another pod"
        )
    if _inspect(physical).as_dict() != identity.as_dict():
        raise AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: child PATH CocoaPods identity drifted"
        )
    return identity, cocoapods_environment(identity, base=environment)
