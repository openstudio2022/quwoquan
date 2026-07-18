"""Bounded HTTP transport for source and media downloads."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from core.runtime_policy import active_runtime_policy
from content.source.fetch_text import (
    DOWNLOAD_BYTES_TIMEOUT_SECONDS,
    DOWNLOAD_CURL_RETRIES,
    _USER_AGENT,
)

_RUNTIME_POLICY = active_runtime_policy()


def _curl_get_bytes(
    url: str,
    *,
    timeout: int = DOWNLOAD_BYTES_TIMEOUT_SECONDS,
    max_bytes: int = 0,
) -> tuple[int, bytes, str]:
    """Use the single bounded transport selected by the runtime policy."""
    size_guard: list[str] = []
    if int(max_bytes or 0) > 0:
        size_guard = ["--max-filesize", str(int(max_bytes))]
    with tempfile.NamedTemporaryFile() as body_file:
        proc = subprocess.run(
            [
                "curl", "-sS", "-L", "--compressed", "-A", _USER_AGENT,
                "--retry", str(DOWNLOAD_CURL_RETRIES),
                "--retry-delay", str(_RUNTIME_POLICY.curl_retry_delay_seconds),
                "--retry-all-errors",
                "--max-time", str(timeout),
                *size_guard,
                "-o", body_file.name,
                "-w", "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
        try:
            status = int((proc.stdout or "").strip() or "0")
        except ValueError:
            status = 0
        body = Path(body_file.name).read_bytes()
    return status, body, ""


def _http_get_bytes(
    url: str,
    *,
    timeout: int = DOWNLOAD_BYTES_TIMEOUT_SECONDS,
    max_bytes: int = 0,
) -> tuple[int, bytes, str]:
    """Return one bounded HTTP response through the canonical curl transport."""
    return _curl_get_bytes(url, timeout=timeout, max_bytes=max_bytes)
