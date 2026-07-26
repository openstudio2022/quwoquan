from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


INSTALL_HINT = (
    "install with `dart pub global activate patrol_cli 4.4.0` or set "
    "`PATROL_CLI=/absolute/path/to/patrol`"
)
REQUIRED_PATROL_CLI_VERSION = "4.4.0"


@dataclass(frozen=True)
class PatrolCliResolution:
    executable: str | None
    source: str
    searched: tuple[str, ...]
    error: str
    version: str = ""

    def as_report(self, *, required: bool) -> dict[str, object]:
        return {
            "required": required,
            "executable": self.executable or "",
            "source": self.source,
            "searched": list(self.searched),
            "error": self.error,
            "version": self.version,
            "installHint": INSTALL_HINT,
        }


def _is_command_name(value: str) -> bool:
    return not any(separator and separator in value for separator in (os.sep, os.altsep))


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _home_pub_cache_candidate(env: Mapping[str, str]) -> Path:
    home = env.get("HOME", "").strip()
    return (Path(home).expanduser() if home else Path.home()) / ".pub-cache" / "bin" / "patrol"


def _version_for_executable(path: Path) -> str | None:
    try:
        result = subprocess.run(
            [str(path), "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except OSError:
        return None
    output = "\n".join((result.stdout, result.stderr))
    expected = f"patrol_cli v{REQUIRED_PATROL_CLI_VERSION}"
    return REQUIRED_PATROL_CLI_VERSION if result.returncode == 0 and expected in output else None


def _resolved_cli(path: Path, source: str, searched: list[str]) -> PatrolCliResolution:
    version = _version_for_executable(path)
    if version is not None:
        return PatrolCliResolution(str(path), source, tuple(searched), "", version)
    return PatrolCliResolution(
        None,
        source,
        tuple(searched),
        f"Patrol CLI must be v{REQUIRED_PATROL_CLI_VERSION}; {INSTALL_HINT}",
    )


def resolve_patrol_cli(env: Mapping[str, str] | None = None) -> PatrolCliResolution:
    """Resolve the Patrol CLI without requiring pub-cache/bin to be in PATH."""
    values = os.environ if env is None else env
    searched: list[str] = []
    path_value = values.get("PATH", "")

    configured = values.get("PATROL_CLI", "").strip()
    if configured:
        if _is_command_name(configured):
            searched.append(f"PATROL_CLI command: {configured}")
            found = shutil.which(configured, path=path_value)
            if found:
                resolved = Path(found)
                if _is_executable(resolved):
                    return _resolved_cli(resolved, "PATROL_CLI", searched)
            return PatrolCliResolution(
                None,
                "PATROL_CLI",
                tuple(searched),
                f"PATROL_CLI={configured!r} is not executable or not found in PATH; {INSTALL_HINT}",
            )

        configured_path = Path(configured).expanduser()
        searched.append(f"PATROL_CLI path: {configured_path}")
        if _is_executable(configured_path):
            return _resolved_cli(configured_path, "PATROL_CLI", searched)
        return PatrolCliResolution(
            None,
            "PATROL_CLI",
            tuple(searched),
            f"PATROL_CLI={configured!r} is not executable; {INSTALL_HINT}",
        )

    searched.append("PATH command: patrol")
    found = shutil.which("patrol", path=path_value)
    if found:
        resolved = Path(found)
        if _is_executable(resolved):
            return _resolved_cli(resolved, "PATH", searched)

    pub_cache = values.get("PUB_CACHE", "").strip()
    if pub_cache:
        candidate = Path(pub_cache).expanduser() / "bin" / "patrol"
        searched.append(f"PUB_CACHE bin: {candidate}")
        if _is_executable(candidate):
            return _resolved_cli(candidate, "PUB_CACHE", searched)

    home_candidate = _home_pub_cache_candidate(values)
    searched.append(f"home pub-cache bin: {home_candidate}")
    if _is_executable(home_candidate):
        return _resolved_cli(home_candidate, "HOME_PUB_CACHE", searched)

    return PatrolCliResolution(None, "missing", tuple(searched), f"Patrol CLI not found; {INSTALL_HINT}")
