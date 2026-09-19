# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""prod-sim schema owner and Post safety rehearsal producer contracts."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import yaml

from quwoquan_ops.cli.lib.post_safety_runtime import (
    FileDeploymentStartupMaterialOwner,
    PostSafetyRuntimeError,
    PostSafetyTarget,
)
from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
    ProdSimRehearsalAuthorityError,
    ensure_prod_sim_user_schema_for_locked_up,
    produce_prod_sim_rehearsal_startup_material,
)
from quwoquan_ops.cli.lib.source_initializer_package import (
    build_source_initializer,
    source_initializer_required,
)


def test_source_initializer_required_includes_prod_sim_not_hosted(tmp_path: Path) -> None:
    assert source_initializer_required("alpha", "alpha-local")
    assert source_initializer_required("gamma", "gamma-local")
    assert source_initializer_required("prod", "prod-sim")
    assert not source_initializer_required("prod", "prod-hosted")
    assert not source_initializer_required("gamma", "prod-sim")
    with pytest.raises(ValueError, match="managed nonproduction"):
        build_source_initializer(tmp_path, tmp_path, "prod", "prod-hosted")


def test_ensure_schema_applies_packaged_initializer_when_empty(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "source-init"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    states = {"calls": 0}

    def readback(_dsn: str):
        states["calls"] += 1
        if states["calls"] == 1:
            return None, None, 0
        return "service_schema_migrations", "user_profiles", 2

    captured: dict[str, object] = {}

    def run(cmd, env=None, cwd=None, capture_output=None, timeout=None):
        captured.update({"cmd": cmd, "env": env, "cwd": cwd, "timeout": timeout})
        return mock.Mock(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._active_prod_sim_candidate",
        lambda: ({}, tmp_path, {"environment": "prod", "target": "prod-sim"}),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._load_packaged_initializer",
        lambda _root: executable,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._schema_readback",
        readback,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.prod_sim_user_postgres_host_dsn",
        lambda: "postgresql://quwoquan:quwoquan@127.0.0.1:5432/quwoquan_user",
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.subprocess.run",
        run,
    )
    result = ensure_prod_sim_user_schema_for_locked_up()
    assert result["status"] == "applied"
    assert captured["cwd"] == executable.parent
    env = captured["env"]
    assert env["QWQ_SOURCE_INIT_ENV"] == "prod"
    assert env["QWQ_SOURCE_INIT_TARGET"] == "prod-sim"


def test_ensure_schema_verified_does_not_rerun_initializer(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "source-init"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._active_prod_sim_candidate",
        lambda: ({}, tmp_path, {"environment": "prod", "target": "prod-sim"}),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._load_packaged_initializer",
        lambda _root: executable,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._schema_readback",
        lambda _dsn: ("service_schema_migrations", "user_profiles", 2),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.prod_sim_user_postgres_host_dsn",
        lambda: "postgresql://example",
    )

    def run(*_args, **_kwargs):
        raise AssertionError("initializer must not rerun a verified schema")

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.subprocess.run",
        run,
    )
    result = ensure_prod_sim_user_schema_for_locked_up()
    assert result["status"] == "verified"


def test_ensure_schema_rejects_nonempty_namespace_without_ledger(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "source-init"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._active_prod_sim_candidate",
        lambda: ({}, tmp_path, {"environment": "prod", "target": "prod-sim"}),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._load_packaged_initializer",
        lambda _root: executable,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._schema_readback",
        lambda _dsn: (None, None, 3),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.prod_sim_user_postgres_host_dsn",
        lambda: "postgresql://example",
    )
    with pytest.raises(ProdSimRehearsalAuthorityError, match="not empty"):
        ensure_prod_sim_user_schema_for_locked_up()


def test_prod_sim_post_safety_producer_rejects_prod_hosted(tmp_path: Path) -> None:
    current = PostSafetyTarget(
        "prod",
        "prod-hosted",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        "mongo",
        "quwoquan_content",
        "generation",
        "attempt",
    )
    with pytest.raises(PostSafetyRuntimeError, match="prod-sim only"):
        produce_prod_sim_rehearsal_startup_material(
            current=current,
            database=object(),
            account_material_root=(tmp_path / "account").absolute(),
            deployment_owner=FileDeploymentStartupMaterialOwner("prod-hosted"),
        )


def test_startup_package_binding_ignores_attempt_and_requires_candidate() -> None:
    from types import SimpleNamespace

    from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
        _startup_package_binding_matches,
    )

    expected = PostSafetyTarget(
        "prod",
        "prod-sim",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        "mongo",
        "quwoquan_content",
        "new-generation",
        "new-attempt",
    )
    matching = SimpleNamespace(
        environment="prod",
        target="prod-sim",
        candidateDigest="sha256:" + "a" * 64,
        dataPlaneBindingDigest="sha256:" + "b" * 64,
    )
    drifted = SimpleNamespace(
        environment="prod",
        target="prod-sim",
        candidateDigest="sha256:" + "c" * 64,
        dataPlaneBindingDigest="sha256:" + "b" * 64,
    )
    assert _startup_package_binding_matches(matching, expected)
    assert not _startup_package_binding_matches(drifted, expected)


def test_archive_stale_prod_sim_post_safety_residue_moves_create_once_root(
    tmp_path: Path, monkeypatch
) -> None:
    from quwoquan_ops.cli.lib import output_paths
    from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
        _archive_stale_prod_sim_post_safety_residue,
    )

    deploy = tmp_path / "deploy" / "prod-sim"
    startup_root = deploy / "startup-material" / "content-service" / "post-safety"
    startup_root.mkdir(parents=True, mode=0o700)
    (startup_root / "startup.json").write_text("{}", encoding="utf-8")
    secrets_root = deploy / "secrets" / "post-safety" / "old-generation"
    secrets_root.mkdir(parents=True, mode=0o700)
    account_root = deploy / "secrets" / "content-account-closure" / "old-attempt"
    account_root.mkdir(parents=True, mode=0o700)

    monkeypatch.setattr(
        output_paths,
        "deployment_target_path",
        lambda _target, *segments: deploy.joinpath(*segments),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.post_safety_runtime.post_safety_startup_material_root",
        lambda _target: startup_root,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.output_paths.deployment_target_path",
        lambda _target, *segments: deploy.joinpath(*segments),
    )

    _archive_stale_prod_sim_post_safety_residue(attempt_id="new-attempt")
    assert not startup_root.exists()
    archive = deploy / "archive" / "rehearsal-post-safety" / "new-attempt"
    assert (archive / "00-post-safety" / "startup.json").is_file()
    assert (archive / "01-post-safety" / "old-generation").is_dir()
    assert (archive / "02-content-account-closure" / "old-attempt").is_dir()


def test_drop_stale_prod_sim_post_safety_collections_drops_known_names() -> None:
    from quwoquan_ops.cli.lib.content_account_closure_runtime import COLLECTIONS
    from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
        _drop_stale_prod_sim_post_safety_collections,
    )

    dropped: list[str] = []

    class _Database:
        def command(self, command):
            if command.get("listCollections") == 1:
                return {
                    "cursor": {
                        "firstBatch": [
                            {"name": "post_safety_states"},
                            {"name": COLLECTIONS[0]},
                            {"name": "unrelated"},
                        ]
                    }
                }
            if "drop" in command:
                dropped.append(command["drop"])
                return {}
            raise AssertionError(command)

    _drop_stale_prod_sim_post_safety_collections(_Database())
    assert dropped == ["post_safety_states", COLLECTIONS[0]]


def test_bind_prod_sim_api_edge_rehearsal_runtime_pins_package_and_local_redis(
    tmp_path: Path, monkeypatch
) -> None:
    from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
        PROD_ROLLOUT_POLICY,
        bind_prod_sim_api_edge_rehearsal_runtime,
    )

    digest = "sha256:" + "b" * 64
    version = "sha256:" + "c" * 64
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "api-edge.yaml").write_text(
        "\n".join(
            [
                "graphql_read:",
                f"  candidate_digest: {digest}",
                "  enabled: true",
                "redis:",
                "  admission:",
                "    mode: cluster",
                "    addrs: [redis-admission-0:6379, redis-admission-1:6379, redis-admission-2:6379]",
                "    tls: true",
                "rollout:",
                "  enabled: true",
                "  policy_file: rollout/routing_policy.yaml",
                "  policy_sha256: sha256:" + "a" * 64,
                "config:",
                f"  version: {version}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (config_root / "assistant-service.yaml").write_text(
        "\n".join(
            [
                "skill_package:",
                "  asset_root: /app/resources/skills/packages/official",
                "config:",
                f"  version: {version}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    publication = (
        config_root
        / "skill-packages"
        / "official"
        / "releases"
        / "prod-sim-rehearsal"
        / "publication.json"
    )
    publication.parent.mkdir(parents=True)
    publication.write_text("{}\n", encoding="utf-8")
    (config_root / "product-ops-service.yaml").write_text(
        "\n".join(
            [
                "redis:",
                "  general:",
                "    mode: cluster",
                "    tls: true",
                "    addrs: [redis-admission-0:6379]",
                "  rec:",
                "    mode: cluster",
                "    tls: true",
                "    addrs: [redis-admission-1:6379]",
                "config:",
                f"  version: {version}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    deploy = tmp_path / "deploy"
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.output_paths.deployment_target_path",
        lambda _target, *segments: deploy.joinpath(*segments),
    )
    bound = bind_prod_sim_api_edge_rehearsal_runtime(
        config_root=config_root,
        candidate_digest=digest,
        source_policy=PROD_ROLLOUT_POLICY,
    )
    policy = yaml.safe_load(
        (config_root / "rollout" / "routing_policy.yaml").read_text(encoding="utf-8")
    )
    portal = (config_root / "gray-routing" / "policy.yaml").read_bytes()
    edge = yaml.safe_load((config_root / "api-edge.yaml").read_text(encoding="utf-8"))
    assert policy["policy"]["candidateDigest"] == digest
    assert policy["policy"]["status"] == "complete"
    assert policy["policy"]["enabled"] is True
    assert (config_root / "rollout" / "routing_policy.yaml").read_bytes() == portal
    assert edge["rollout"]["policy_sha256"] == bound["policyDigest"]
    assert edge["config"]["version"] == version
    assert edge["redis"]["admission"] == {
        "mode": "standalone",
        "addr": "redis:6379",
        "tls": False,
    }
    assistant = yaml.safe_load(
        (config_root / "assistant-service.yaml").read_text(encoding="utf-8")
    )
    assert assistant["skill_package"]["asset_root"] == (
        "/etc/qwq-config/skill-packages/official"
    )
    assert assistant["config"]["version"] == version
    product_ops = yaml.safe_load(
        (config_root / "product-ops-service.yaml").read_text(encoding="utf-8")
    )
    assert product_ops["redis"]["general"] == {
        "mode": "standalone",
        "tls": False,
        "addrs": [],
        "addr": "redis:6379",
    }
    assert product_ops["redis"]["rec"]["mode"] == "standalone"
    assert product_ops["config"]["version"] == version
    assert len(bound["allocationKey"]) >= 32
    again = bind_prod_sim_api_edge_rehearsal_runtime(
        config_root=config_root,
        candidate_digest=digest,
        source_policy=PROD_ROLLOUT_POLICY,
    )
    assert again["allocationKey"] == bound["allocationKey"]


def test_bind_prod_sim_platform_ops_rehearsal_runtime_is_create_once(
    tmp_path: Path, monkeypatch
) -> None:
    from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
        bind_prod_sim_platform_ops_rehearsal_runtime,
    )

    deploy = tmp_path / "deploy"
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.output_paths.deployment_target_path",
        lambda _target, *segments: deploy.joinpath(*segments),
    )
    digest = "sha256:" + "b" * 64
    bound = bind_prod_sim_platform_ops_rehearsal_runtime(candidate_digest=digest)
    assert bound["RELEASE_MANIFEST_DIGEST"] == digest
    assert bound["PLATFORM_OPS_HUMAN_AUTHORITY_ISSUER"] == "quwoquan-prod-sim-rehearsal"
    assert bound["PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_KEY_ID"]
    assert bound["PLATFORM_OPS_HUMAN_AUTHORITY_SIGNING_PRIVATE_KEY_BASE64"]
    assert len(bound["PLATFORM_OPS_HUMAN_AUTHORITY_GITHUB_WEBHOOK_SECRET"]) >= 16
    assert "release_owner" in bound["PLATFORM_OPS_HUMAN_AUTHORITY_ROLE_MAPPINGS"]
    again = bind_prod_sim_platform_ops_rehearsal_runtime(candidate_digest=digest)
    assert again == bound


def test_ensure_prod_sim_public_loopback_resolution_rejects_non_loopback(
    monkeypatch,
) -> None:
    from quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities import (
        ProdSimRehearsalAuthorityError,
        ensure_prod_sim_public_loopback_resolution,
    )

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities.prod_sim_public_loopback_hosts",
        lambda: ("api.sim.quwoquan.com",),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._resolved_addresses",
        lambda _host: {"198.18.1.92"},
    )
    with pytest.raises(ProdSimRehearsalAuthorityError, match="loopback"):
        ensure_prod_sim_public_loopback_resolution()
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.prod_sim_rehearsal_authorities._resolved_addresses",
        lambda _host: {"127.0.0.1"},
    )
    assert ensure_prod_sim_public_loopback_resolution()["status"] == "verified"
