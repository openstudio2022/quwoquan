"""spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/config-source-governance/spec.md#gwt-001"""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_environment_auth import (
    prepare_local_environment_auth,
)
from quwoquan_ops.cli.lib.output_paths import (
    deployment_candidate_dir,
    target_cache_dir,
    target_process_dir,
)
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports
from quwoquan_ops.cli.lib.public_domain_tls import certificate_dir


TARGETS = ("alpha-local", "beta-local", "gamma-local")
ENVIRONMENTS = ("alpha", "beta", "gamma")
BASELINE = "sha256:" + "a" * 64


def test_local_targets_have_disjoint_ports_urls_and_physical_output_roots() -> None:
    topology = load_environment_topology()
    port_manifest = load_port_manifest()
    all_ports: dict[str, set[int]] = {}
    api_urls: set[str] = set()
    process_roots: set[Path] = set()
    cache_roots: set[Path] = set()
    certificate_roots: set[Path] = set()
    candidate_roots: set[Path] = set()

    for target_name in TARGETS:
        target = get_target(topology, target_name)
        ports = set(profile_ports(port_manifest, str(target["portProfile"])).values())
        assert ports
        data_release = target["dataRelease"]
        assert data_release["redisPortRole"] == "redis"
        assert data_release["redisDatabase"] == 1
        all_ports[target_name] = ports
        api_urls.add(str((target["publicBases"] or {})["api"]))
        process_roots.add(target_process_dir(target_name))
        cache_roots.add(target_cache_dir(target_name))
        certificate_roots.add(certificate_dir(target_name))
        candidate_roots.add(deployment_candidate_dir(target_name, BASELINE))

    for index, left in enumerate(TARGETS):
        for right in TARGETS[index + 1 :]:
            assert all_ports[left].isdisjoint(all_ports[right])
    assert len(api_urls) == len(TARGETS)
    assert len(process_roots) == len(TARGETS)
    assert len(cache_roots) == len(TARGETS)
    assert len(certificate_roots) == len(TARGETS)
    assert len(candidate_roots) == len(TARGETS)


def test_auth_material_is_target_scoped_and_cryptographically_distinct(
    tmp_path: Path,
) -> None:
    auth = [
        prepare_local_environment_auth(
            environment,
            target,
            deployment_work_root=tmp_path,
        )
        for environment, target in zip(ENVIRONMENTS, TARGETS, strict=True)
    ]

    assert len({item.secret_path for item in auth}) == len(TARGETS)
    assert len({item.environment["AUTH_JWT_SECRET"] for item in auth}) == len(TARGETS)
    assert len({item.environment["AUTH_JWT_ISSUER"] for item in auth}) == len(TARGETS)
    assert all(item.secret_path.stat().st_mode & 0o077 == 0 for item in auth)


def test_manual_podman_path_rewrites_owned_resources_into_target_namespace() -> None:
    script = (
        Path(__file__).resolve().parents[3]
        / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")

    assert (
        'default_compose_project="quwoquan_${QWQ_LOCAL_RELEASE_ENV}_release"'
        in script
    )
    assert "LOCAL_GAMMA_RESOURCE_PREFIX" in script
    assert "compgen -A variable LOCAL_GAMMA_" in script
    assert '[[ "$port_variable" == LOCAL_GAMMA_*_PORT ]]' in script
    assert 'cancelled_ports="${cancelled_ports}${port} "' in script
    assert "restart_colima_for_stale_target_ports" not in script
    assert "colima stop" not in script
    assert 'command podman "${isolated_args[@]}"' in script
    assert (
        'value="${LOCAL_GAMMA_RESOURCE_PREFIX}_local-${QWQ_LOCAL_RELEASE_ENV}-'
        in script
    )
    assert (
        'for container_name in "${LOCAL_GAMMA_RESOURCE_PREFIX}_${base_name}_1"'
        in script
    )
