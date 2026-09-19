# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
from __future__ import annotations

import argparse
import contextlib
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli import legal_static, stackctl
from quwoquan_ops.cli.commands import up_domain
from quwoquan_ops.cli.lib import startup_attempt_receipt as subject
from quwoquan_ops.cli.lib.environment_topology import formal_release_compose_project_name
from quwoquan_ops.cli.lib.output_paths import env_runs_root
from quwoquan_ops.cli.lib.startup_health_failure_evidence import TARGET_PATTERN
from quwoquan_ops.tests.support.startup_attempt_receipt_test_support import (
    _active_candidate_files,
    _composition,
    _oci_manifest,
)


def test_prod_sim_maps_to_prod_and_rejects_hosted_or_test_live() -> None:
    assert subject._environment_for_target("prod-sim") == "prod"
    assert subject._is_local_generation_identity("prod", "prod-sim")
    assert not subject._is_local_generation_identity("prod", "prod-hosted")
    assert not subject._is_local_generation_identity("alpha", "test-live")
    with pytest.raises(ValueError, match="target identity mismatch"):
        subject._environment_for_target("prod-hosted")
    with pytest.raises(ValueError, match="target identity mismatch"):
        subject._environment_for_target("test-live")


def test_prod_sim_formal_compose_project_is_local_generation() -> None:
    assert formal_release_compose_project_name("prod-sim") == "quwoquan_prod_sim_release"
    with pytest.raises(ValueError, match="requires a local target"):
        formal_release_compose_project_name("prod-hosted")


def test_prod_sim_health_failure_target_pattern_matches() -> None:
    assert TARGET_PATTERN.fullmatch("prod-sim") is not None
    assert TARGET_PATTERN.fullmatch("gamma-local") is not None
    assert TARGET_PATTERN.fullmatch("prod-hosted") is None


def test_load_startup_attempt_prod_sim_absent_is_none() -> None:
    assert subject.load_startup_attempt("prod-sim") is None


def test_prod_sim_oci_loader_accepts_prod_identity(
    tmp_path: Path,
) -> None:
    oci = _oci_manifest(environment="prod", target="prod-sim")
    active_path, candidate_root, oci_path, candidate = _active_candidate_files(
        tmp_path, manifest=oci
    )
    with (
        mock.patch.object(
            subject, "active_candidate_manifest_path", return_value=active_path
        ),
        mock.patch.object(
            subject, "deployment_candidate_dir", return_value=candidate_root
        ),
        mock.patch.object(subject, "load_candidate_manifest", return_value=candidate),
    ):
        loaded = subject.load_candidate_oci_image_composition(
            oci_path,
            expected_environment="prod",
            expected_target="prod-sim",
            expected_candidate_digest="sha256:" + "b" * 64,
        )
    assert loaded == _composition(environment="prod", target="prod-sim")
    with pytest.raises(ValueError, match="expected target identity mismatch"):
        subject.load_candidate_oci_image_composition(
            oci_path,
            expected_environment="prod",
            expected_target="prod-hosted",
        )


def test_prod_sim_startup_receipt_validates() -> None:
    composition = _composition(environment="prod", target="prod-sim")
    run_root = env_runs_root("prod") / "up-prod-sim"
    payload = {
        "schema": subject.SCHEMA,
        "attemptId": "up-prod-sim",
        "env": "prod",
        "target": "prod-sim",
        "status": "prepared",
        "workload": "full",
        "composeProject": "quwoquan_prod_sim_release",
        "candidateDigest": "sha256:" + "b" * 64,
        "configurationDigest": "sha256:" + "c" * 64,
        "providerRuntimeDigest": "sha256:" + "d" * 64,
        "observabilityLogSinkDigest": "sha256:" + "e" * 64,
        "imageTransportTag": composition["imageVersion"],
        "imageComposition": composition,
        "runRoot": str(run_root),
        "startedAt": "2026-09-18T00:00:00Z",
        "updatedAt": "2026-09-18T00:00:00Z",
        "failure": None,
        "cleanupFailure": None,
    }
    validated = subject.validate_startup_attempt(
        payload, expected_env="prod", expected_target="prod-sim"
    )
    assert validated["target"] == "prod-sim"
    assert validated["composeProject"] == "quwoquan_prod_sim_release"


def test_command_up_prod_sim_does_not_raise_identity_mismatch() -> None:
    up_args = argparse.Namespace(target="prod-sim", env="", workload="full")
    created = {"attemptId": "generation-sim", "status": "running", "workload": "full"}
    with (
        mock.patch.object(
            stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()
        ),
        mock.patch.object(stackctl, "load_environment_topology", return_value={"targets": {}}),
        mock.patch.object(stackctl, "assert_local_runtime_available"),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(
            stackctl, "_command_up_impl", return_value={"exitCode": 0}
        ) as start,
        mock.patch.object(
            stackctl, "load_startup_attempt", side_effect=[None, created]
        ),
    ):
        result = up_domain.command_up(up_args)
    assert result["exitCode"] == 0
    assert "unmanaged_runtime_authority" not in result
    assert "identity mismatch" not in str(result)
    start.assert_called_once()


def test_prod_sim_package_marks_placeholders_without_local_build() -> None:
    assert (
        legal_static.placeholder_policy_for_package(
            env_name="prod",
            target_name="prod-sim",
            rehearsal_material=False,
        )
        == "mark"
    )
    assert (
        legal_static.placeholder_policy_for_package(
            env_name="prod",
            target_name="prod-hosted",
            rehearsal_material=False,
        )
        == "block"
    )
    assert legal_static._non_promotable_for_placeholder_policy("mark")
    manifest, issues = legal_static.validate_manifest("prod")
    assert isinstance(manifest, dict)
    blocking, placeholders = legal_static._split_placeholder_issues(issues)
    assert blocking == []
    assert "owner.operatorName" in placeholders
    marked, remaining = legal_static._split_placeholder_issues(
        ["owner.operatorName contains placeholder text"]
    )
    assert marked == []
    assert remaining == ["owner.operatorName"]


def _prod_sim_local_log_sink_payload(tmp_path: Path) -> dict[str, object]:
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.candidate_fs import (
        _sha256_json,
    )
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.log_sink_package import (
        LOG_SINK_ADAPTER_ID,
        OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA,
        _expected_package_log_sink_bindings,
    )

    relative = "packages/runtime-shared/observability-log-sink/elasticsearch.compose.yaml"
    compose = "services:\n  elasticsearch:\n    image: quwoquan/elasticsearch-cjk:8.13.4\n"
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(compose, encoding="utf-8")
    import hashlib

    bindings = _expected_package_log_sink_bindings(
        env_name="prod",
        target_name="prod-sim",
    )
    return {
        "schema": OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA,
        "adapterId": LOG_SINK_ADAPTER_ID,
        "bindings": bindings,
        "bindingDigest": _sha256_json(bindings),
        "deploymentMode": "package-bound-local",
        "platform": "arm64",
        "runtimeEndpoint": "http://elasticsearch:9200",
        "imageDigest": "tag:8.13.4",
        "sourceComposeDigest": "sha256:" + "a" * 64,
        "composeRef": relative,
        "composeDigest": "sha256:" + hashlib.sha256(compose.encode()).hexdigest(),
    }


def test_prod_sim_log_sink_requires_package_bound_local_identity(tmp_path: Path) -> None:
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.log_sink_package import (
        validate_observability_log_sink_package,
    )

    payload = _prod_sim_local_log_sink_payload(tmp_path)
    validated = validate_observability_log_sink_package(
        payload,
        expected_environment="prod",
        expected_target="prod-sim",
        candidate_root=tmp_path,
    )
    assert validated["deploymentMode"] == "package-bound-local"
    hosted = {**payload, "deploymentMode": "managed-external"}
    with pytest.raises(ValueError, match="local observability log-sink package identity"):
        validate_observability_log_sink_package(
            hosted,
            expected_environment="prod",
            expected_target="prod-sim",
        )


def test_prod_sim_omits_app_launch_bundle_without_artifact_root(tmp_path: Path) -> None:
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.prod_sim_app_launch import (
        validate_prod_sim_app_launch_bundle,
    )
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.prod_sim_app_launch_materialization import (
        materialize_prod_sim_app_launch_bundle_impl,
    )

    with mock.patch.dict("os.environ", {"QWQ_PROD_RELEASE_ARTIFACT_ROOT": ""}, clear=False):
        omitted = materialize_prod_sim_app_launch_bundle_impl(
            candidate_root=tmp_path,
            package_snapshot={"baselineId": "sha256:" + "a" * 64},
            materialized_release_evidence={},
            source_root=tmp_path,
        )
    assert omitted is None
    assert (
        validate_prod_sim_app_launch_bundle(
            {"target": "prod-sim", "appLaunchBundle": None},
            candidate_root=tmp_path,
        )
        == {}
    )


def test_prod_sim_local_release_runtime_projects_port_environment() -> None:
    topology = stackctl.load_environment_topology()
    environment = stackctl._gamma_env_from_port_manifest(topology, "prod-sim")
    assert environment["QWQ_LOCAL_RELEASE_ENV"] == "prod"
    assert environment["QWQ_LOCAL_RELEASE_TARGET"] == "prod-sim"
    assert environment["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"] == "quwoquan_prod_sim_release"
    with pytest.raises(RuntimeError, match="does not support prod-hosted"):
        stackctl._gamma_env_from_port_manifest(topology, "prod-hosted")


def test_prod_sim_package_includes_package_bound_local_images() -> None:
    source = (
        Path(stackctl.__file__).resolve().parent
        / "commands"
        / "package_runtime.py"
    ).read_text(encoding="utf-8")
    assert (
        'target_name in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}'
        in source
    )


def test_prod_sim_log_sink_launch_projects_candidate_local_compose(
    tmp_path: Path,
) -> None:
    payload = _prod_sim_local_log_sink_payload(tmp_path)
    projected = stackctl._observability_log_sink_launch_environment(
        payload,
        environment_name="prod",
        target_name="prod-sim",
        candidate_root=tmp_path,
        workload="full",
    )
    assert projected["QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE"] == str(
        tmp_path / payload["composeRef"]
    )
    assert projected["QWQ_OBSERVABILITY_LOG_SINK_DIGEST"] == payload["composeDigest"]
    assert projected["PRODUCT_OPS_TELEMETRY_ELASTICSEARCH_ENDPOINT"] == (
        "http://elasticsearch:9200"
    )
    assert projected["PRODUCT_OPS_RUNTIME_LOG_ELASTICSEARCH_ENDPOINT"] == (
        "http://elasticsearch:9200"
    )


def test_prod_sim_package_build_object_storage_is_local_placeholder(
    tmp_path: Path,
) -> None:
    from quwoquan_ops.cli.lib.local_environment_object_storage import (
        package_build_object_storage_environment,
    )

    with mock.patch.dict(
        "os.environ",
        {"QWQ_OUTPUT_ROOT": str(tmp_path / "output")},
        clear=False,
    ):
        values = package_build_object_storage_environment(target_name="prod-sim")
    assert values["LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID"] == "package-build-only"
    assert "prod-sim" in values["LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE"]
    with pytest.raises(ValueError, match="must be local"):
        package_build_object_storage_environment(target_name="prod-hosted")
    from quwoquan_ops.cli.lib.local_environment_object_storage import (
        prepare_local_environment_object_storage,
    )

    with pytest.raises(ValueError, match="identity mismatch"):
        prepare_local_environment_object_storage(
            environment="prod",
            target_name="prod-hosted",
            edge_port=20110,
            environment_prefix="LOCAL_GAMMA",
        )


def test_prod_sim_package_provider_reference_uses_actual_target() -> None:
    environment = {"LOCAL_GAMMA_SMS_SUBSTITUTE_PORT": "20080"}
    with mock.patch.object(
        stackctl,
        "validate_provider_runtime_composition",
        return_value={"materialKeys": {"endpoint": [], "secret": []}},
    ) as validate:
        stackctl._bind_package_provider_reference_environment(
            environment,
            environment_name="prod",
            target_name="prod-sim",
            runtime_composition={"environment": "prod", "target": "prod-sim"},
        )
    validate.assert_called_once()
    assert validate.call_args.kwargs["expected_target"] == "prod-sim"
    assert validate.call_args.kwargs["expected_environment"] == "prod"


def test_prod_sim_package_provenance_uses_sim_workspace(tmp_path: Path) -> None:
    from quwoquan_ops.cli.lib.immutable_image_composition import (
        _load_package_provenance,
    )

    payload = {"service": "content-service", "environment": "prod"}
    (tmp_path / "provenance.json").write_text(
        __import__("json").dumps(payload),
        encoding="utf-8",
    )
    with mock.patch(
        "quwoquan_ops.cli.lib.immutable_image_composition.service_deployment_package_dir",
        return_value=tmp_path,
    ) as package_dir:
        path, loaded = _load_package_provenance(
            "prod",
            "content-service",
            target="prod-sim",
        )
    package_dir.assert_called_once_with(
        "prod",
        "content-service",
        target="prod-sim",
    )
    assert path == tmp_path / "provenance.json"
    assert loaded == payload


def test_prod_sim_is_local_compose_runtime_topology() -> None:
    from quwoquan_ops.cli.lib.runtime_topology_package import (
        is_local_compose_runtime_topology,
    )

    assert is_local_compose_runtime_topology("prod", "prod-sim")
    assert is_local_compose_runtime_topology("gamma", "gamma-local")
    assert not is_local_compose_runtime_topology("prod", "prod-hosted")
    assert not is_local_compose_runtime_topology("prod", "prod-local")


def test_prod_sim_runtime_shared_package_seals_local_compose_topology(
    tmp_path: Path,
) -> None:
    from quwoquan_ops.cli.lib.runtime_topology_package import (
        load_runtime_topology_package,
    )

    candidate = tmp_path / "prod-sim-candidate"
    shared = candidate / "packages/runtime-shared"
    with mock.patch.object(
        stackctl,
        "runtime_shared_deployment_package_dir",
        return_value=shared,
    ), mock.patch.object(
        stackctl,
        "remove_deployment_tree",
        return_value=None,
    ):
        package_dir = stackctl._build_runtime_shared_package(
            "prod",
            target="prod-sim",
        )
    manifest = __import__("json").loads(
        (package_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["environment"] == "prod"
    assert manifest["target"] == "prod-sim"
    topology_ref = manifest["runtimeTopology"]
    assert topology_ref["ref"] == (
        "packages/runtime-shared/runtime-topology/manifest.json"
    )
    loaded = load_runtime_topology_package(
        candidate,
        environment="prod",
        target="prod-sim",
        workload="full",
    )
    assert loaded["composeFiles"]
    topology = __import__("json").loads(
        (package_dir / "runtime-topology/manifest.json").read_text(encoding="utf-8")
    )
    assert topology["environment"] == "prod"
    assert topology["target"] == "prod-sim"
    assert "compose" in topology
    assert topology.get("assembly") != "hosted-render"


def test_prod_sim_up_uses_packaged_local_compose_start() -> None:
    up_source = (
        Path(stackctl.__file__).resolve().parent / "commands" / "up_runtime.py"
    ).read_text(encoding="utf-8")
    start_source = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    assert (
        'elif requested_target in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:'
        in up_source
    )
    assert (
        '"$QWQ_LOCAL_RELEASE_ENV" == "prod" && "$QWQ_LOCAL_RELEASE_TARGET" == "prod-sim"'
        in start_source
    )
    from quwoquan_ops.cli.lib.public_domain_tls import (
        PublicDomainTlsError,
        ensure_local_compose_runtime_tls,
    )

    with pytest.raises(PublicDomainTlsError, match="prod-sim only"):
        ensure_local_compose_runtime_tls("prod-hosted")


def test_prod_sim_provider_rehearsal_is_not_derived_from_legal_placeholder() -> None:
    source = (
        Path(stackctl.__file__).resolve().parent
        / "lib/deployment_candidate_manifest/provider_runtime_package.py"
    ).read_text(encoding="utf-8")
    report_source = (
        Path(stackctl.__file__).resolve().parent / "commands/package_runtime.py"
    ).read_text(encoding="utf-8")
    assert '"kind": "local-provider-substitute"' in source
    assert '"providerRehearsal"] = provider_rehearsal' in report_source
    assert "legal_placeholder_fields" not in source


def test_prod_sim_topology_and_launcher_seal_runtime_target() -> None:
    topology_source = (
        Path(stackctl.__file__).resolve().parent
        / "lib/runtime_topology_package.py"
    ).read_text(encoding="utf-8")
    launcher_source = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    assert '"QWQ_RUNTIME_TARGET": runtime_target' in topology_source
    assert 'QWQ_RUNTIME_TARGET="$QWQ_LOCAL_RELEASE_TARGET"' in launcher_source


def test_prod_sim_formal_bind_requires_local_substitute_workloads() -> None:
    binding = (
        Path(stackctl.__file__).resolve().parent
        / "commands"
        / "provider_runtime_binding.py"
    ).read_text(encoding="utf-8")
    composition = (
        Path(stackctl.__file__).resolve().parent
        / "lib"
        / "provider_runtime_composition.py"
    ).read_text(encoding="utf-8")
    assert '(environment_name, target_name) == ("prod", "prod-sim")' in binding
    assert '(environment_name, target_name) == ("prod", "prod-hosted")' in binding
    assert "Prod Provider runtime cannot start local workloads" in binding
    assert (
        'if expected_environment == "prod" and expected_target == "prod-hosted":'
        in composition
    )
    assert "Prod Provider runtime cannot contain local workloads" in composition


def test_prod_sim_runtime_authority_hook_stays_in_authority_helper() -> None:
    authority = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/gamma/local_gamma_runtime_authority.sh"
    ).read_text(encoding="utf-8")
    start = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    assert "ensure_prod_sim_rehearsal_authorities_for_locked_up" in authority
    assert '"$QWQ_LOCAL_RELEASE_TARGET" == "prod-sim"' in authority
    assert 'additions["PLATFORM_OPS_BASE_URL"]' in authority
    assert 'additions["OPS_OIDC_ISSUER"]' in authority
    assert "prod-sim-rehearsal-telemetry-key" in authority
    assert 'additions["PROMETHEUS_URL"]' in authority
    assert "bind_prod_sim_api_edge_rehearsal_runtime" in authority
    assert "bind_prod_sim_platform_ops_rehearsal_runtime" in authority
    assert "ensure_prod_sim_public_loopback_resolution" in authority
    assert "CURL_CA_BUNDLE" in authority
    assert "root_certificate_path(\"prod-sim\")" in authority
    repair = (
        Path(stackctl.__file__).resolve().parent
        / "commands"
        / "repair_undownable_startup_receipt.py"
    ).read_text(encoding="utf-8")
    assert 'if target != "prod-sim":' in repair
    assert 'if target not in (*_RECLAIMABLE_TARGETS, "prod-sim")' in repair
    assert "API_EDGE_ROLLOUT_ALLOCATION_KEY" in authority
    assert "ensure_prod_sim_rehearsal_authorities_for_locked_up" not in start
    assert 'additions["PLATFORM_OPS_BASE_URL"]' not in start
    assert 'additions["OPS_OIDC_ISSUER"]' not in start
    assert "bind_prod_sim_api_edge_rehearsal_runtime" not in start
    assert "bind_prod_sim_platform_ops_rehearsal_runtime" not in start


def test_prod_sim_print_defines_uses_rehearsal_app_runtime_signing() -> None:
    defines = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/env/print_app_env_dart_defines.py"
    ).read_text(encoding="utf-8")
    start = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
    ).read_text(encoding="utf-8")
    authority = (
        Path(stackctl.__file__).resolve().parents[2]
        / "quwoquan_app/scripts/gamma/local_gamma_runtime_authority.sh"
    ).read_text(encoding="utf-8")
    assert "prepare_local_prod_sim_rehearsal_runtime_config_signing" in defines
    assert 'target_name == "prod-sim"' in defines
    assert "resolve_signing_material(ROOT)" in defines
    assert "print_app_env_dart_defines.py" in authority
    assert "print_defines()" in authority
    assert "print_defines" in start
    assert "prepare_local_prod_sim_rehearsal_runtime_config_signing" not in start
