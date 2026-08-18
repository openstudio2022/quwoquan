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
PATROL_CLI_VERSION_ATTEMPTS = 3


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


def _version_probe_failure(path: Path) -> str | None:
    """探测版本，返回 None 表示确认为所需版本，否则返回失败原因。

    「探测不成」与「版本不符」是两种不同的失败，必须报成两句话：前者的处置是修
    工具链或环境（`patrol` 是 dart snapshot，子进程 PATH 里没有 dart 时它根本起
    不来），后者的处置才是重装指定版本。把两者塌陷成同一句「必须是 v4.4.0」会把
    人一路引向重装，而重装对前者无效。
    """
    expected = f"patrol_cli v{REQUIRED_PATROL_CLI_VERSION}"
    last_failure = "Patrol CLI version probe never ran"
    for _ in range(PATROL_CLI_VERSION_ATTEMPTS):
        try:
            result = subprocess.run(
                [str(path), "--version"],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            last_failure = (
                f"`{path} --version` did not answer within 30s; "
                "it checks pub.dev for updates, so a blocked network can stall it"
            )
            continue
        except OSError as exc:
            last_failure = f"`{path} --version` could not be executed: {exc}"
            continue
        output = "\n".join((result.stdout, result.stderr))
        if expected in output:
            return None
        if result.returncode != 0:
            detail = " ".join(output.split()) or "no output"
            last_failure = (
                f"`{path} --version` exited {result.returncode}: {detail}"
            )
            continue
        detail = " ".join(output.split()) or "no output"
        last_failure = (
            f"Patrol CLI must be v{REQUIRED_PATROL_CLI_VERSION}, but "
            f"`{path} --version` reported: {detail}"
        )
    return last_failure


def _resolved_cli(path: Path, source: str, searched: list[str]) -> PatrolCliResolution:
    failure = _version_probe_failure(path)
    if failure is None:
        return PatrolCliResolution(
            str(path),
            source,
            tuple(searched),
            "",
            REQUIRED_PATROL_CLI_VERSION,
        )
    return PatrolCliResolution(
        None,
        source,
        tuple(searched),
        f"{failure}; {INSTALL_HINT}",
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
