"""Resolve the real local-Gamma object-storage connection from Ops contracts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_gamma_object_storage import (
    prepare_local_gamma_object_storage,
)
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports


GAMMA_LOCAL_TARGET = "gamma-local"
OBJECT_STORAGE_PORT_ROLE = "object-storage-edge"


@dataclass(frozen=True)
class GammaObjectStorageConnection:
    endpoint: str
    bucket: str
    region: str
    access_key: str
    secret_key: str
    ca_bundle: Path


def resolve_gamma_object_storage() -> GammaObjectStorageConnection:
    topology = load_environment_topology()
    target = get_target(topology, GAMMA_LOCAL_TARGET)
    profile_name = str(target["portProfile"])
    ports = profile_ports(load_port_manifest(), profile_name)
    prepared = prepare_local_gamma_object_storage(
        edge_port=ports[OBJECT_STORAGE_PORT_ROLE],
    )
    environment = prepared.environment
    return GammaObjectStorageConnection(
        endpoint=prepared.host_endpoint,
        bucket=environment["LOCAL_GAMMA_OBJECT_STORAGE_BUCKET"],
        region=environment["LOCAL_GAMMA_OBJECT_STORAGE_REGION"],
        access_key=environment["LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID"],
        secret_key=environment["LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_SECRET"],
        ca_bundle=Path(environment["LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE"]),
    )
