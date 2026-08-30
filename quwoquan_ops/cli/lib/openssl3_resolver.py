"""Resolve one capability-proven OpenSSL 3 executable."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

OPENSSL_BIN_ENV = "QWQ_OPENSSL_BIN"
_OPENSSL_3_VERSION = re.compile(r"^OpenSSL 3(?:[.]|\s|$)")
_HOMEBREW_OPENSSL_CANDIDATES = (
    Path("/opt/homebrew/opt/openssl@3/bin/openssl"),
    Path("/opt/homebrew/bin/openssl"),
    Path("/usr/local/opt/openssl@3/bin/openssl"),
    Path("/usr/local/bin/openssl"),
)
_CAPABILITY_BLOCKER = "GATE_BLOCK[OPENSSL_3_ED25519_RAWIN_CAPABILITY]"


class OpenSSL3CapabilityError(ValueError):
    """The selected executable cannot provide the required signing primitive."""


@dataclass(frozen=True)
class OpenSSL3Executable:
    executable: Path
    version: str
    digest: str
    device: int = 0
    inode: int = 0

    def revalidate(self) -> "OpenSSL3Executable":
        """Fail closed if the selected physical executable identity drifted."""

        physical = _physical_executable(self.executable, source="resolved OpenSSL 3")
        if physical != self.executable:
            raise _block("selected OpenSSL 3 physical executable identity changed")
        try:
            info = physical.stat()
            digest = "sha256:" + hashlib.sha256(physical.read_bytes()).hexdigest()
        except OSError as exc:
            raise _block("selected OpenSSL 3 executable identity is unreadable") from exc
        if (self.device and info.st_dev != self.device) or (
            self.inode and info.st_ino != self.inode
        ):
            raise _block("selected OpenSSL 3 physical executable identity changed")
        if digest != self.digest:
            raise _block("selected OpenSSL 3 executable digest changed")
        return self

    def argv(self, *arguments: str) -> list[str]:
        self.revalidate()
        return [str(self.executable), *arguments]

    def redacted_identity(self) -> dict[str, str]:
        return {"version": self.version, "digest": self.digest}


def _block(message: str) -> OpenSSL3CapabilityError:
    return OpenSSL3CapabilityError(f"{_CAPABILITY_BLOCKER}: {message}")


def _physical_executable(candidate: Path, *, source: str) -> Path:
    if not candidate.is_absolute():
        raise _block(f"{source} must resolve to an absolute executable")
    try:
        physical = candidate.resolve(strict=True)
        info = physical.stat()
    except OSError as exc:
        raise _block(f"{source} executable is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(physical, os.X_OK):
        raise _block(f"{source} must resolve to a regular executable file")
    return physical


def _run(
    executable: Path,
    arguments: list[str],
    *,
    step: str,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            [str(executable), *arguments],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _block(
            f"OpenSSL 3 capability probe could not execute step={step}"
        ) from exc


def _version(executable: Path) -> str:
    result = _run(executable, ["version"], step="version")
    identity = (result.stdout or result.stderr).decode("utf-8", "replace").strip()
    if result.returncode != 0 or not identity:
        raise _block("selected executable cannot report its implementation version")
    first_line = identity.splitlines()[0].strip()
    if _OPENSSL_3_VERSION.match(first_line) is None:
        raise _block(
            "selected executable does not self-identify as OpenSSL 3 "
            f"(implementation={first_line})"
        )
    return first_line


def _probe_ed25519_rawin(executable: Path, *, version: str, digest: str) -> None:
    with tempfile.TemporaryDirectory(prefix="qwq-openssl3-capability-") as temporary:
        root = Path(temporary)
        private_key = root / "private.pem"
        public_key = root / "public.pem"
        payload = root / "payload.bin"
        signature = root / "signature.bin"
        payload.write_bytes(b"quwoquan-openssl3-ed25519-rawin-capability-v1")
        commands = (
            ("genpkey", ["genpkey", "-algorithm", "ED25519", "-out", str(private_key)]),
            (
                "public-key",
                ["pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
            ),
            (
                "pkeyutl-sign-rawin",
                [
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    str(private_key),
                    "-in",
                    str(payload),
                    "-out",
                    str(signature),
                ],
            ),
            (
                "pkeyutl-verify-rawin",
                [
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-inkey",
                    str(public_key),
                    "-in",
                    str(payload),
                    "-sigfile",
                    str(signature),
                ],
            ),
        )
        for step, arguments in commands:
            result = _run(executable, arguments, step=step)
            if result.returncode != 0:
                raise _block(
                    "selected OpenSSL 3 lacks Ed25519 pkeyutl -rawin capability "
                    f"(implementation={version}, digest={digest}, step={step})"
                )
        if not signature.is_file() or signature.stat().st_size != 64:
            raise _block(
                "selected OpenSSL 3 produced a non-Ed25519 probe signature "
                f"(implementation={version}, digest={digest})"
            )


def _resolve_candidate(candidate: Path, *, source: str) -> OpenSSL3Executable:
    executable = _physical_executable(candidate, source=source)
    try:
        digest = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
    except OSError as exc:
        raise _block(f"{source} executable bytes are unreadable") from exc
    version = _version(executable)
    _probe_ed25519_rawin(executable, version=version, digest=digest)
    info = executable.stat()
    return OpenSSL3Executable(
        executable=executable,
        version=version,
        digest=digest,
        device=info.st_dev,
        inode=info.st_ino,
    )


def resolve_openssl3(
    getenv: Callable[[str], str | None] = os.getenv,
    which: Callable[[str], str | None] = shutil.which,
) -> OpenSSL3Executable:
    """Resolve QWQ_OPENSSL_BIN, Homebrew OpenSSL 3, then PATH.

    An explicit QWQ_OPENSSL_BIN is authoritative and never falls through. Other
    candidates may be skipped only when absent; an existing incompatible binary
    is rejected and resolution continues to the next declared source. LibreSSL
    can therefore never become an implicit signing fallback.
    """

    explicit = str(getenv(OPENSSL_BIN_ENV) or "").strip()
    if explicit:
        return _resolve_candidate(Path(explicit).expanduser(), source=OPENSSL_BIN_ENV)

    first_blocker: OpenSSL3CapabilityError | None = None
    seen: set[Path] = set()
    candidates: list[tuple[Path, str]] = [
        (candidate, "Homebrew OpenSSL 3")
        for candidate in _HOMEBREW_OPENSSL_CANDIDATES
        if candidate.exists()
    ]
    path_candidate = which("openssl")
    if path_candidate:
        candidates.append((Path(path_candidate), "PATH openssl"))
    for candidate, source in candidates:
        lexical = (
            Path(os.path.abspath(candidate)) if candidate.is_absolute() else candidate
        )
        try:
            physical = candidate.resolve(strict=True)
        except OSError:
            physical = lexical
        if physical in seen:
            continue
        seen.add(physical)
        try:
            return _resolve_candidate(candidate, source=source)
        except OpenSSL3CapabilityError as exc:
            if first_blocker is None:
                first_blocker = exc
    if first_blocker is not None:
        raise first_blocker
    raise _block(
        "no OpenSSL 3 executable was found via QWQ_OPENSSL_BIN, Homebrew, or PATH"
    )


def openssl3_identity_report(
    executable: OpenSSL3Executable,
) -> Mapping[str, str]:
    """Return the only report-safe executable identity (never its path)."""

    return executable.revalidate().redacted_identity()
