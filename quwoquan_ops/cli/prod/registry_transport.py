#!/usr/bin/env python3
"""Bounded retry for immutable registry transport commands."""
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable


RETRY_DELAYS_SECONDS = (0, 5, 15)


def run_with_bounded_retry(
    command: Callable[[], subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    """Run the exact same command at most three times with fixed backoff."""

    result: subprocess.CompletedProcess[str] | None = None
    for delay_seconds in RETRY_DELAYS_SECONDS:
        if delay_seconds:
            time.sleep(delay_seconds)
        result = command()
        if result.returncode == 0:
            return result
    assert result is not None
    return result
