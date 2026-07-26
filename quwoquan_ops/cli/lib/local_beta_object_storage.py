from __future__ import annotations

import shlex
import sys

from .local_environment_object_storage import (
    LocalEnvironmentObjectStorage,
    prepare_local_environment_object_storage,
)


LocalBetaObjectStorage = LocalEnvironmentObjectStorage


def prepare_local_beta_object_storage(*, edge_port: int) -> LocalBetaObjectStorage:
    """Prepare real Beta-local S3 credentials and TLS outside output roots."""
    return prepare_local_environment_object_storage(
        environment="beta",
        target_name="beta-local",
        edge_port=edge_port,
        public_host="beta-upload.quwoquan-env.test",
        local_host="beta-upload.localhost",
        environment_prefix="BETA",
    )


def _print_shell_environment(edge_port: int) -> None:
    storage = prepare_local_beta_object_storage(edge_port=edge_port)
    for key, value in sorted(storage.environment.items()):
        print(f"export {key}={shlex.quote(value)}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--shell":
        raise SystemExit(
            "usage: python -m quwoquan_ops.cli.lib.local_beta_object_storage "
            "--shell <edge-port>"
        )
    try:
        _print_shell_environment(int(sys.argv[2]))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
