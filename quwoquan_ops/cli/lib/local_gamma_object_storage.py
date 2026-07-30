from __future__ import annotations

from .local_environment_object_storage import (
    LocalEnvironmentObjectStorage,
    prepare_local_environment_object_storage,
)


LocalGammaObjectStorage = LocalEnvironmentObjectStorage


def prepare_local_gamma_object_storage(*, edge_port: int) -> LocalGammaObjectStorage:
    """Prepare real Gamma-local S3 credentials and TLS outside output roots."""
    return prepare_local_environment_object_storage(
        environment="gamma",
        target_name="gamma-local",
        edge_port=edge_port,
        environment_prefix="LOCAL_GAMMA",
    )
