"""Private Patrol command-envelope fixtures shared by projection consumers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quwoquan_ops.cli.lib.package_reuse.patrol_command_envelope import (
    patrol_command_envelope,
    patrol_command_envelope_digest,
)


def sealed_patrol_command_fixture(
    dependency_environment: Mapping[str, str],
) -> tuple[dict[str, Any], str]:
    envelope = patrol_command_envelope(
        flutter_identity={
            "executable": "/private/sdk/flutter/bin/flutter",
            "flutterVersion": "3.47.0",
            "commandResolutionDigest": "sha256:" + "f" * 64,
        },
        path="/private/sdk/flutter/bin:/usr/bin:/bin",
        dependency_environment=dependency_environment,
    )
    return envelope, patrol_command_envelope_digest(envelope)
