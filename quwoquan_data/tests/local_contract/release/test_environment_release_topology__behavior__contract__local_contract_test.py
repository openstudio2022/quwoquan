"""Environment-owned Data release target resolution contract."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.environment import topology
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    MediaDeliverySlice,
    resolve_environment_release_target,
)
from content.release.model import DeploymentEnvironment


def test_media_sync_uses_same_host_runtime_root_as_stackctl(monkeypatch, tmp_path):
    from quwoquan_ops.cli.lib import output_paths
    monkeypatch.delenv("QWQ_OUTPUT_ROOT", raising=False)
    monkeypatch.setattr(output_paths, "DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT", tmp_path / "host-runtime")
    monkeypatch.setattr(topology, "_local_managed_ssl_cafile", lambda target: "")
    target = resolve_environment_release_target(DeploymentEnvironment.BETA)
    assert target.media_sync_root == tmp_path / "host-runtime/env/beta/local/beta-local/cache/media"


def test_local_release_targets_derive_ports_paths_and_tls_from_ops_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_targets: list[str] = []

    def resolve_test_cafile(target_name: str) -> str:
        resolved_targets.append(target_name)
        return f"/test/{target_name}/root.crt"

    monkeypatch.setattr(topology, "_local_managed_ssl_cafile", resolve_test_cafile)

    beta = resolve_environment_release_target(DeploymentEnvironment.BETA)

    assert beta.mode is EnvironmentReleaseMode.LOCAL_IMPORT
    assert beta.mongo_uri == "mongodb://127.0.0.1:18410/?directConnection=true"
    assert beta.redis_addr == "127.0.0.1:18420"
    assert beta.redis_database == 1
    assert beta.user_postgres_dsn == (
        "postgres://quwoquan:quwoquan@127.0.0.1:18400/quwoquan?sslmode=disable"
    )
    assert beta.media_sync_root is not None
    assert beta.media_sync_root.as_posix().endswith("/env/beta/local/beta-local/cache/media")
    assert beta.api_base_url == "https://api.beta.quwoquan.com:18000"
    assert beta.media_delivery_base_url == "https://cdn.beta.quwoquan.com:18100"
    assert beta.ssl_cafile == "/test/beta-local/root.crt"
    assert beta.media_base_url(MediaDeliverySlice.AVATAR).endswith("/media/avatar")
    assert resolved_targets == ["beta-local"]


def test_alpha_release_target_is_local_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_targets: list[str] = []

    def resolve_test_cafile(target_name: str) -> str:
        resolved_targets.append(target_name)
        return f"/test/{target_name}/root.crt"

    monkeypatch.setattr(topology, "_local_managed_ssl_cafile", resolve_test_cafile)

    target = resolve_environment_release_target(DeploymentEnvironment.ALPHA)

    assert target.mode is EnvironmentReleaseMode.LOCAL_IMPORT
    assert target.import_ready is True
    assert target.mongo_uri == "mongodb://127.0.0.1:17410/?directConnection=true"
    assert target.redis_addr == "127.0.0.1:17420"
    assert target.redis_database == 1
    assert target.user_postgres_dsn == (
        "postgres://quwoquan:quwoquan@127.0.0.1:17400/quwoquan?sslmode=disable"
    )
    assert target.media_sync_root is not None
    assert target.media_sync_root.as_posix().endswith("/env/alpha/local/alpha-local/cache/media")
    assert target.api_base_url == "https://api.alpha.quwoquan.com:17000"
    assert target.media_delivery_base_url == "https://cdn.alpha.quwoquan.com:17100"
    assert target.ssl_cafile == "/test/alpha-local/root.crt"
    assert resolved_targets == ["alpha-local"]


def test_local_release_target_fails_closed_when_managed_ca_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quwoquan_ops.cli.lib import public_domain_tls

    error = public_domain_tls.PublicDomainTlsError(
        "GATE_BLOCK: local-managed root certificate is missing for alpha-local"
    )
    def missing_root_certificate(_target_name: str) -> Path:
        raise error

    monkeypatch.setattr(
        public_domain_tls,
        "root_certificate_path",
        missing_root_certificate,
    )

    with pytest.raises(RuntimeError, match="root certificate is missing for alpha-local"):
        resolve_environment_release_target(DeploymentEnvironment.ALPHA)


def test_gamma_and_prod_reject_runtime_yaml_coordinate_bypass() -> None:
    for environment in (DeploymentEnvironment.GAMMA, DeploymentEnvironment.PROD):
        with pytest.raises(RuntimeError, match="DATA.RELEASE.RUNTIME_CANDIDATE_MISSING"):
            resolve_environment_release_target(environment)


def _canonical_binding(environment: str, target_name: str):
    from quwoquan_ops.cli.lib.data_plane_binding import canonical_data_plane_binding
    from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
    target = get_target(load_environment_topology(), target_name)
    canonical = canonical_data_plane_binding(target, target_name=target_name)
    raw = (json.dumps(canonical, sort_keys=True) + "\n").encode()
    descriptor = {
        "ref": "packages/runtime-shared/data-plane-binding.json",
        "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "bindingDigest": canonical["bindingDigest"],
    }
    return canonical, descriptor, raw


def test_gamma_maps_import_coordinates_from_exact_canonical_binding(monkeypatch, tmp_path):
    canonical, descriptor, raw = _canonical_binding("gamma", "gamma-local")
    artifact = tmp_path / descriptor["ref"]
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(raw)
    monkeypatch.setattr(topology, "_candidate_binding", lambda *_args, **_kwargs: (canonical, descriptor, raw, {"baselineId": "sha256:" + "a" * 64, "packageDigest": "sha256:" + "b" * 64}))
    monkeypatch.setattr(topology, "_local_managed_ssl_cafile", lambda _target: "")
    monkeypatch.setattr(topology, "_post_safety_import_projection", lambda *_args, **_kwargs: (tmp_path, "current.json", "fact.json", "post-safety.key", "candidate-service-core"))
    oci = tmp_path / "packages/runtime-shared/oci-images.json"
    oci.parent.mkdir(parents=True, exist_ok=True)
    oci.write_text(json.dumps({"images": {"service-core": {"ref": "candidate-service-core"}}}))

    target = resolve_environment_release_target(DeploymentEnvironment.GAMMA, candidate_root=tmp_path)

    assert target.mongo_uri == "mongodb://127.0.0.1:19410/?directConnection=true"
    assert target.user_postgres_dsn.endswith(":19400/quwoquan_user?sslmode=disable")
    assert target.redis_addr == "127.0.0.1:19420"
    assert target.content_mongo_database == "quwoquan_content"
    assert target.tag_mongo_database == "quwoquan_tag"
    assert target.creator_mongo_database == "quwoquan_user"
    assert target.homepage_mongo_database == "quwoquan_entity"
    assert target.binding_digest == canonical["bindingDigest"]
    topology.assert_environment_release_target_unchanged(target)


def test_prod_maps_hosted_secrets_and_media_from_canonical_authorities(monkeypatch, tmp_path):
    canonical, descriptor, raw = _canonical_binding("prod", "prod-hosted")
    artifact = tmp_path / descriptor["ref"]
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(raw)
    monkeypatch.setattr(topology, "_candidate_binding", lambda *_args, **_kwargs: (canonical, descriptor, raw, {"baselineId": "sha256:" + "a" * 64, "packageDigest": "sha256:" + "b" * 64}))
    monkeypatch.setattr(topology, "_post_safety_import_projection", lambda *_args, **_kwargs: (tmp_path, "current.json", "fact.json", "post-safety.key", "candidate-service-core"))
    oci = tmp_path / "packages/runtime-shared/oci-images.json"
    oci.parent.mkdir(parents=True, exist_ok=True)
    oci.write_text(json.dumps({"images": {"service-core": {"ref": "candidate-service-core"}}}))
    resources = canonical["resources"]
    resources["primary-mongodb"]["physicalIdentity"] = {
        "external": "prod-primary-mongodb",
        "prevalidate": "prevalidate-mongodb",
    }
    resources["primary-postgres"]["physicalIdentity"] = {
        "external": "prod-primary-postgres",
        "prevalidate": "prevalidate-postgres",
    }
    resources["primary-redis"]["physicalIdentity"] = {
        "external": "prod-primary-redis",
        "prevalidate": "prevalidate-redis",
    }
    from quwoquan_ops.cli.lib.data_plane_binding import canonical_data_plane_binding
    canonical = canonical_data_plane_binding(
        {"dataPlane": {"resources": resources, "bindings": canonical["bindings"]}},
        target_name="prod-hosted",
    )
    raw = (json.dumps(canonical, sort_keys=True) + "\n").encode()
    descriptor = {
        "ref": "packages/runtime-shared/data-plane-binding.json",
        "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "bindingDigest": canonical["bindingDigest"],
    }
    artifact.write_bytes(raw)
    monkeypatch.setattr(topology, "_candidate_binding", lambda *_args, **_kwargs: (canonical, descriptor, raw, {"baselineId": "sha256:" + "a" * 64, "packageDigest": "sha256:" + "b" * 64}))
    monkeypatch.setattr(topology, "_post_safety_import_projection", lambda *_args, **_kwargs: (tmp_path, "current.json", "fact.json", "post-safety.key", "candidate-service-core"))
    oci = tmp_path / "packages/runtime-shared/oci-images.json"
    oci.parent.mkdir(parents=True, exist_ok=True)
    oci.write_text(json.dumps({"images": {"service-core": {"ref": "candidate-service-core"}}}))

    target = resolve_environment_release_target(DeploymentEnvironment.PROD, candidate_root=tmp_path)

    assert target.mongo_uri == "mongodb://prevalidate-mongodb:27017/?directConnection=true"
    assert target.user_postgres_dsn == (
        "postgres://quwoquan:quwoquan@prevalidate-postgres:5432/"
        "quwoquan_user?sslmode=disable"
    )
    assert target.redis_addr == "prevalidate-redis:6379"
    assert target.media_sync_root == Path("/home/prod-service-svc/stack/state/prod/r0/process/volumes/media")


def test_binding_exact_bytes_drift_blocks_before_mutation(monkeypatch, tmp_path):
    canonical, descriptor, raw = _canonical_binding("gamma", "gamma-local")
    artifact = tmp_path / descriptor["ref"]
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(raw)
    monkeypatch.setattr(topology, "_candidate_binding", lambda *_args, **_kwargs: (canonical, descriptor, raw, {"baselineId": "sha256:" + "a" * 64, "packageDigest": "sha256:" + "b" * 64}))
    monkeypatch.setattr(topology, "_local_managed_ssl_cafile", lambda _target: "")
    monkeypatch.setattr(topology, "_post_safety_import_projection", lambda *_args, **_kwargs: (tmp_path, "current.json", "fact.json", "post-safety.key", "candidate-service-core"))
    oci = tmp_path / "packages/runtime-shared/oci-images.json"
    oci.parent.mkdir(parents=True, exist_ok=True)
    oci.write_text(json.dumps({"images": {"service-core": {"ref": "candidate-service-core"}}}))
    target = resolve_environment_release_target(DeploymentEnvironment.GAMMA, candidate_root=tmp_path)
    artifact.write_bytes(raw + b" ")
    with pytest.raises(RuntimeError, match="DATA.RELEASE.DATA_PLANE_BINDING_CAS_DRIFT"):
        topology.assert_environment_release_target_unchanged(target)
