"""stackctl gamma/beta 正式发布环境绑定域: 外部 Provider 环境、对象存储绑定
与 release evidence 配置物化。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_inspect_gamma_release_runtime`、
`_bind_formal_local_release_provider_environment`、beta/local 外部 Provider
环境绑定、`_bind_package_provider_reference_environment`、
`_sync_object_storage_binding_aliases`、`_gamma_start_command`、
`_materialize_release_evidence_configuration`。

packaged/release/teardown 镜像 refs 绑定族已迁往 `runtime_image_composition`，
与该模块的 composition 加载合为同一责任。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import concurrent
import concurrent.futures
import json
import os

from pathlib import Path
from typing import Any
from typing import Mapping


def _inspect_gamma_release_runtime(
    release_composition: dict[str, Any],
    environment: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Prove that local containers actually run every exact candidate ref."""
    import quwoquan_ops.cli.stackctl as _stackctl


    images = release_composition.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("formal release composition has no images")
    project = str(
        environment.get("LOCAL_GAMMA_COMPOSE_PROJECT_NAME") or "quwoquan_service"
    ).strip()
    def inspect_service(item: tuple[str, Any]) -> tuple[str, dict[str, str]]:
        service, descriptor = item
        if not isinstance(descriptor, dict):
            raise ValueError(f"formal image descriptor is invalid: {service}")
        expected_ref = str(descriptor.get("ref") or "")
        expected_digest = str(descriptor.get("digest") or "")
        container_lookup = _stackctl.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--filter",
                f"label=com.docker.compose.service={service}",
            ],
            env=environment,
        )
        container_ids = [
            line.strip()
            for line in container_lookup.stdout.splitlines()
            if line.strip()
        ]
        if container_lookup.returncode != 0 or len(container_ids) != 1:
            raise ValueError(
                f"formal runtime must have exactly one {service} container; "
                f"found {len(container_ids)}"
            )
        container_id = container_ids[0]
        inspect_result = _stackctl.run(["docker", "inspect", container_id], env=environment)
        if inspect_result.returncode != 0:
            raise ValueError(f"formal runtime inspect failed: {service}")
        try:
            inspected = json.loads(inspect_result.stdout)
            container = inspected[0]
            actual_ref = str(container["Config"]["Image"])
            runtime_image_id = str(container["Image"])
            state = container["State"]
            status = str(state["Status"])
            health = str((state.get("Health") or {}).get("Status") or "not-declared")
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"formal runtime inspect is not canonical: {service}"
            ) from error
        if actual_ref != expected_ref:
            raise ValueError(
                f"formal runtime image differs from candidate: {service}"
            )
        if status != "running" or health not in {"healthy", "not-declared"}:
            raise ValueError(
                f"formal runtime is not ready: {service} status={status} health={health}"
            )
        image_result = _stackctl.run(["docker", "image", "inspect", expected_ref], env=environment)
        if image_result.returncode != 0:
            raise ValueError(f"formal local image inspect failed: {service}")
        try:
            local_images = json.loads(image_result.stdout)
            repo_digests = local_images[0].get("RepoDigests") or []
        except (IndexError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"formal local image inspect is not canonical: {service}"
            ) from error
        if expected_ref not in repo_digests:
            raise ValueError(
                f"formal local image has no exact pulled digest: {service}"
            )
        return service, {
            "ref": expected_ref,
            "digest": expected_digest,
            "containerId": container_id,
            "runtimeImageId": runtime_image_id,
            "status": status,
            "health": health,
        }

    items = sorted(images.items())
    runtime_images: dict[str, dict[str, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, len(items))
    ) as executor:
        futures = [executor.submit(inspect_service, item) for item in items]
        for future in concurrent.futures.as_completed(futures):
            service, runtime = future.result()
            runtime_images[service] = runtime
    return dict(sorted(runtime_images.items()))


def _bind_gamma_external_provider_environment(
    environment: dict[str, str],
) -> str | None:
    """Bind Gamma Providers from the active immutable runtime composition."""
    import quwoquan_ops.cli.stackctl as _stackctl

    storage_error = _stackctl._bind_gamma_object_storage_environment(environment)
    if storage_error is not None:
        return storage_error
    try:
        runtime = _stackctl._active_provider_runtime("gamma", "gamma-local")
    except (OSError, TypeError, ValueError) as exc:
        return f"gamma-local Provider runtime preflight failed: {exc}"
    return _stackctl._bind_local_external_provider_environment(
        environment,
        environment_name="gamma",
        target_name="gamma-local",
        storage_prefix="LOCAL_GAMMA",
        runtime_composition=runtime["composition"],
    )


def _bind_gamma_object_storage_environment(
    environment: dict[str, str],
) -> str | None:
    """Materialize only the platform-owned Gamma object-storage binding."""
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        storage = _stackctl.prepare_local_gamma_object_storage(
            edge_port=_stackctl.profile_ports(
                _stackctl.load_port_manifest(),
                "gamma-local",
            )["object-storage-edge"],
        )
    except (RuntimeError, ValueError) as exc:
        return f"gamma-local object storage materialization failed: {exc}"
    environment.update(storage.environment)
    environment.setdefault(
        "LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL",
        storage.host_endpoint,
    )
    public_bases = (
        _stackctl.get_target(_stackctl.load_environment_topology(), "gamma-local").get("publicBases")
        or {}
    )
    media_delivery_origin = _stackctl._public_url_origin(str(public_bases["mediaImage"]))
    environment.setdefault(
        "CONTENT_MEDIA_DELIVERY_BASE_URL",
        media_delivery_origin,
    )
    environment.setdefault(
        "CONTENT_MEDIA_UPLOAD_BASE_URL",
        str(public_bases["mediaUpload"]),
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL",
        media_delivery_origin,
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL",
        str(public_bases["mediaUpload"]),
    )
    _stackctl._sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    return None


def _bind_formal_local_release_provider_environment(
    environment: dict[str, str],
    *,
    environment_name: str,
    target_name: str,
    workload: str = "full",
    runtime_composition: Mapping[str, Any] | None = None,
) -> str | None:
    """Bind target-isolated infrastructure and protected nonprod Providers."""
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        auth = _stackctl.prepare_local_environment_auth(environment_name, target_name)
        storage = _stackctl.prepare_local_environment_object_storage(
            environment=environment_name,
            target_name=target_name,
            edge_port=_stackctl.profile_ports(
                _stackctl.load_port_manifest(),
                str(_stackctl.get_target(_stackctl.load_environment_topology(), target_name)["portProfile"]),
            )["object-storage-edge"],
            # The shared infrastructure Compose retains this private adapter
            # prefix. Service workloads consume only QWQ_COMPOSE_* aliases.
            environment_prefix="LOCAL_GAMMA",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return f"{target_name} infrastructure materialization failed: {exc}"
    environment.update(auth.environment)
    environment.update(storage.environment)
    if runtime_composition is None:
        return f"{target_name} Provider runtime composition is missing"
    try:
        validated_provider_runtime = _stackctl.validate_provider_runtime_composition(
            dict(runtime_composition),
            expected_environment=environment_name,
            expected_target=target_name,
        )
    except (TypeError, ValueError) as exc:
        return f"{target_name} Provider runtime composition is invalid: {exc}"
    public_bases = _stackctl.get_target(_stackctl.load_environment_topology(), target_name).get(
        "publicBases"
    ) or {}
    media_delivery_origin = _stackctl._public_url_origin(str(public_bases["mediaImage"]))
    environment.setdefault("LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL", storage.host_endpoint)
    environment.setdefault("CONTENT_MEDIA_DELIVERY_BASE_URL", media_delivery_origin)
    environment.setdefault(
        "CONTENT_MEDIA_UPLOAD_BASE_URL", str(public_bases["mediaUpload"])
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL", media_delivery_origin
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL", str(public_bases["mediaUpload"])
    )
    _stackctl._sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    try:
        integration_mtls = _stackctl.prepare_local_integration_service_mtls(
            environment_name,
            target_name,
        )
    except (OSError, _stackctl.PublicDomainTlsError, RuntimeError, ValueError) as exc:
        return (
            f"{target_name} integration-service mTLS materialization failed: "
            f"{exc}"
        )
    environment.update(integration_mtls.environment)
    # Nonprod mesh OTP client requires the canonical internal HTTP URL; the
    # schema default remains HTTPS for packaged/prod-shaped configs.
    environment["INTEGRATION_EXTERNAL_INTERACTION_BASE_URL"] = (
        "http://integration-service:18086"
    )
    # service-core 无条件把 assistant-service 模块并入单容器,因此 trust root
    # 是容器级前置。immutable candidate 必须消费 capsule 内已封存 Skill
    # release 携带的公钥材料,而不是在 up 时重新签发；mutable test_live 仍
    # 由同一次实时发布物构建生成 target-scoped trust root。
    try:
        candidate_root_value = str(
            environment.get("QWQ_FIXED_CANDIDATE_ROOT") or ""
        ).strip()
        if candidate_root_value:
            public_keys_json = (
                _stackctl.load_packaged_assistant_skill_package_trust(
                    candidate_root=Path(candidate_root_value),
                    environment=environment_name,
                    target=target_name,
                )
            )
            environment[
                "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"
            ] = public_keys_json
        else:
            skill_keys = _stackctl.prepare_local_assistant_skill_package_keys(
                environment_name,
                target_name,
            )
            environment.update(skill_keys.environment)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return (
            f"{target_name} assistant Skill package trust materialization "
            f"failed: {exc}"
        )
    if workload in {"content-release", "content-commercial"}:
        # Bounded content workloads own release import/public read and the
        # optional Product Ops premium command. External
        # login, embedding, assistant, integration and RTC capabilities are
        # not started by this workload; validating their protected material
        # here would incorrectly turn unrelated full-workload prerequisites
        # into a content activation or premium-command blocker.
        # user-service still mounts integration mTLS PEMs on every local up,
        # so empty /dev/null mounts must never reach Compose interpolation.
        return None
    provider_roles = {
        str(item["role"])
        for item in validated_provider_runtime["workloads"]
    }
    if not provider_roles:
        return f"{target_name} full runtime Provider workload closure is empty"
    unsupported_roles = provider_roles - {
        "sms-provider-substitute",
        "provider-protocol-substitute",
    }
    if unsupported_roles:
        return (
            f"{target_name} Provider runtime has unsupported materializers: "
            + ",".join(sorted(unsupported_roles))
        )
    if "sms-provider-substitute" in provider_roles:
        try:
            sms_substitute = _stackctl.prepare_local_sms_provider_substitute(
                environment_name,
                target_name,
                port=_stackctl.profile_ports(
                    _stackctl.load_port_manifest(),
                    str(
                        _stackctl.get_target(_stackctl.load_environment_topology(), target_name)[
                            "portProfile"
                        ]
                    ),
                )["sms-provider-substitute"],
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return f"{target_name} SMS substitute materialization failed: {exc}"
        environment.update(sms_substitute.environment)
    if "provider-protocol-substitute" in provider_roles:
        try:
            provider_substitute = _stackctl.prepare_local_provider_protocol_substitute(
                environment_name,
                target_name,
                port=_stackctl.profile_ports(
                    _stackctl.load_port_manifest(),
                    str(
                        _stackctl.get_target(_stackctl.load_environment_topology(), target_name)[
                            "portProfile"
                        ]
                    ),
                )["provider-protocol-substitute"],
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return (
                f"{target_name} Provider protocol substitute materialization "
                f"failed: {exc}"
            )
        environment.update(provider_substitute.environment)
    provider_error = _stackctl._bind_local_external_provider_environment(
        environment,
        environment_name=environment_name,
        target_name=target_name,
        storage_prefix="LOCAL_GAMMA",
        runtime_composition=validated_provider_runtime,
    )
    if provider_error is not None:
        return provider_error
    try:
        provider_config = _stackctl._provider_config()
        provider_config.project_provider_secret_bundles(
            environment=environment_name,
            target=target_name,
            source=environment,
            runtime_composition=validated_provider_runtime,
        )
        provider_config_result = provider_config.compile_provider_config(
            action="render",
            environment=environment_name,
            target=target_name,
            runtime_composition=validated_provider_runtime,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return f"{target_name} Provider configuration materialization failed: {exc}"
    if int(provider_config_result.get("exitCode", 2)) != 0:
        details = "; ".join(
            str(detail)
            for detail in provider_config_result.get("details", [])
            if str(detail).strip()
        )
        return (
            f"{target_name} Provider configuration materialization failed: "
            f"{details or 'required material is incomplete'}"
        )
    return None


def _bind_gamma_down_parse_environment(
    environment: dict[str, str],
    *,
    receipt_bound: bool = False,
) -> None:
    """Satisfy non-identity Compose interpolation used only while tearing down."""

    storage_placeholders = {
        "ENDPOINT": "https://unused.invalid",
        "BUCKET": "unused",
        "REGION": "unused",
        "ACCESS_KEY_ID": "unused",
        "ACCESS_KEY_SECRET": "unused",
        "CDN_SIGN_KEY": "unused",
        "TLS_DIR": "/tmp",
        "CA_FILE": "/tmp/unused-local-managed-ca.crt",
    }
    for suffix, value in storage_placeholders.items():
        source_key = f"LOCAL_GAMMA_OBJECT_STORAGE_{suffix}"
        compose_key = f"QWQ_COMPOSE_OBJECT_STORAGE_{suffix}"
        environment.setdefault(source_key, value)
        environment.setdefault(compose_key, environment[source_key])
    environment.update(
        {
            "AUTH_JWT_SECRET": "down-not-used",
            "AUTH_JWT_ISSUER": "down-not-used",
            "AUTH_JWT_AUDIENCE": "down-not-used",
            "AUTH_JWT_TOKEN_VERSION": "down-not-used",
            "AUTH_DEVICE_TICKET_SECRET": "down-not-used",
            "AUTH_DEVICE_TICKET_ISSUER": "down-not-used",
            "AUTH_DEVICE_TICKET_AUDIENCE": "down-not-used",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION": "down-not-used",
            "OTP_CODE_REF_ACTIVE_KEY_VERSION": "down-not-used",
            "OTP_CODE_REF_KEYS_JSON": '{"down-not-used":"down-not-used"}',
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON": (
                '{"down-not-used":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
            ),
            "QWQ_PUSH_TOKEN_ENCRYPTION_KEY": "down-not-used",
            "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET": "down-not-used",
            # Build/down only need deterministic Compose interpolation.  A
            # running local environment receives the real shared User/Content
            # key from prepare_local_environment_auth's target-scoped 0600
            # secret file.
            "CONTENT_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64": (
                "ZG93bi1ub3QtdXNlZC1yZXNlYXJjaC1pZGVudGl0eS1rZXk="
            ),
            "RTC_MEDIA_API_KEY": "down-not-used",
            "RTC_MEDIA_API_SECRET": "down-not-used",
            "INTEGRATION_SERVICE_MTLS_CA_FILE": "/tmp/down-not-used",
            "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/tmp/down-not-used",
            "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE": "/tmp/down-not-used",
            "INTEGRATION_PUSH_APNS_KEY_FILE": "/tmp/down-not-used",
            "INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE": "/tmp/down-not-used",
            "SMS_SUBSTITUTE_PROVIDER_TOKEN": "down-not-used",
            "SMS_SUBSTITUTE_OPERATOR_TOKEN": "down-not-used",
            "SMS_SUBSTITUTE_CAPTURE_KEY_B64": "down-not-used",
            "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN": "down-not-used",
            "QWQ_COMPOSE_SMS_SUBSTITUTE_CA_FILE": "/tmp/down-not-used",
            "QWQ_COMPOSE_SMS_SUBSTITUTE_TLS_CERT_FILE": "/tmp/down-not-used",
            "QWQ_COMPOSE_SMS_SUBSTITUTE_TLS_KEY_FILE": "/tmp/down-not-used",
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_CA_FILE": "/tmp/down-not-used",
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_TLS_CERT_FILE": "/tmp/down-not-used",
            "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_TLS_KEY_FILE": "/tmp/down-not-used",
            # DEC-005：环境身份与 platform-ops facts 是部署面挂载材料；down 只需
            # 确定性插值，不生成材料。
            "QWQ_COMPOSE_ARTIFACT_IDENTITY_FILE": "/tmp/down-not-used",
            "QWQ_COMPOSE_PLATFORM_OPS_FACTS_ROOT": "/tmp",
        }
    )
    if receipt_bound:
        if environment.get("LOCAL_GAMMA_SMS_SUBSTITUTE_PORT"):
            environment["QWQ_COMPOSE_SMS_SUBSTITUTE_PORT"] = environment[
                "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT"
            ]
        return
    # compose 模板对每个服务强制声明 CONFIG_VERSION；down 只需确定性插值，
    # 优先取 active candidate provenance 真值，candidate 缺席时用占位。
    # 变量名以模板声明为准（目录名与变量名不同构，如 control-plane/platform-ops
    # 声明 PLATFORM_OPS_SERVICE），服务名由变量名反推后查 provenance。
    import re as _re

    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.commands.runtime_image_composition import (
        candidate_service_config_versions,
    )

    config_versions = candidate_service_config_versions()
    compose_paths = sorted(
        (_stackctl.ROOT / "quwoquan_service").glob("services/*/deploy/compose.yaml")
    ) + sorted(
        (_stackctl.ROOT / "quwoquan_service").glob(
            "control-plane/*/deploy/compose.yaml"
        )
    )
    for compose_path in compose_paths:
        body = compose_path.read_text(encoding="utf-8")
        for key in set(
            _re.findall(r"QWQ_COMPOSE_[A-Z_]+_CONFIG_VERSION", body)
        ):
            service = (
                key.removeprefix("QWQ_COMPOSE_")
                .removesuffix("_CONFIG_VERSION")
                .lower()
                .replace("_", "-")
            )
            environment.setdefault(
                key, config_versions.get(service, "down-not-used")
            )
    if environment.get("LOCAL_GAMMA_SMS_SUBSTITUTE_PORT"):
        environment["QWQ_COMPOSE_SMS_SUBSTITUTE_PORT"] = environment[
            "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT"
        ]


def _bind_beta_external_provider_environment(
    environment: dict[str, str],
) -> str | None:
    """Bind Beta Providers from the active immutable runtime composition."""
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        runtime = _stackctl._active_provider_runtime("beta", "beta-local")
    except (OSError, TypeError, ValueError) as exc:
        return f"beta-local Provider runtime preflight failed: {exc}"
    return _stackctl._bind_local_external_provider_environment(
        environment,
        environment_name="beta",
        target_name="beta-local",
        storage_prefix="BETA",
        runtime_composition=runtime["composition"],
    )


def _bind_local_external_provider_environment(
    environment: dict[str, str],
    *,
    environment_name: str,
    target_name: str,
    storage_prefix: str,
    runtime_composition: Mapping[str, Any],
) -> str | None:
    """Bind the canonical non-production Provider substitute topology."""
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        values = _stackctl.load_nonprod_provider_environment(
            environment=environment_name,
            target_name=target_name,
            source=environment,
            debug_local=True,
            runtime_composition=runtime_composition,
        )
    except (RuntimeError, ValueError) as exc:
        return f"{target_name} external Provider preflight failed: {exc}"
    environment.update(values)
    _stackctl._sync_object_storage_binding_aliases(environment, prefix=storage_prefix)
    if values.get("CONTENT_EMBEDDING_ENDPOINT"):
        environment.setdefault(
            "QWQ_COMPOSE_EMBEDDING_ENDPOINT",
            values["CONTENT_EMBEDDING_ENDPOINT"],
        )
    if values.get("CONTENT_EMBEDDING_API_KEY"):
        environment.setdefault(
            "QWQ_COMPOSE_EMBEDDING_API_KEY",
            values["CONTENT_EMBEDDING_API_KEY"],
        )
    return None


def _bind_package_provider_reference_environment(
    environment: dict[str, str],
    *,
    environment_name: str,
    runtime_composition: Mapping[str, Any],
) -> None:
    """Bind non-runtime interpolation values for an OCI-only build.

    The build-only script exits before any container starts.  These values are
    never Provider credentials, never validated as Provider readiness and may
    not be copied into a package or image.  Their sole purpose is to let the
    canonical Compose definition parse while building source-digest images.
    """
    import quwoquan_ops.cli.stackctl as _stackctl


    validated = _stackctl.validate_provider_runtime_composition(
        dict(runtime_composition),
        expected_environment=environment_name,
        expected_target=f"{environment_name}-local",
    )
    endpoint_keys = set(validated["materialKeys"]["endpoint"])
    secret_keys = set(validated["materialKeys"]["secret"])
    # user-service Compose always mounts integration mTLS host files; package
    # interpolation must satisfy the required-file contract without runtime PEMs.
    package_keys = set(endpoint_keys) | set(secret_keys) | {
        "INTEGRATION_SERVICE_MTLS_CA_FILE",
        "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE",
        "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE",
        "SMS_SUBSTITUTE_PROVIDER_TOKEN",
        "SMS_SUBSTITUTE_OPERATOR_TOKEN",
        "SMS_SUBSTITUTE_CAPTURE_KEY_B64",
        "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN",
        "QWQ_COMPOSE_SMS_SUBSTITUTE_CA_FILE",
        "QWQ_COMPOSE_SMS_SUBSTITUTE_TLS_CERT_FILE",
        "QWQ_COMPOSE_SMS_SUBSTITUTE_TLS_KEY_FILE",
        "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_CA_FILE",
        "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_TLS_CERT_FILE",
        "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_TLS_KEY_FILE",
    }
    for key in sorted(package_keys):
        if key.endswith("_FILE"):
            value = "/tmp/qwq-package-build-not-runtime"
        elif key.endswith("_JSON"):
            value = '{"package-build-not-runtime":"package-build-not-runtime"}'
        elif key.endswith("_URL") or key.endswith("_ENDPOINT"):
            value = "https://127.0.0.1"
        else:
            value = "package-build-not-runtime"
        environment[key] = value
    environment["QWQ_COMPOSE_SMS_SUBSTITUTE_PORT"] = environment[
        "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT"
    ]


def _sync_object_storage_binding_aliases(
    environment: dict[str, str],
    *,
    prefix: str,
) -> None:
    """Align CONTENT_OSS_* / QWQ_COMPOSE_OBJECT_STORAGE_* with MinIO materializer."""

    storage_to_content = {
        f"{prefix}_OBJECT_STORAGE_ENDPOINT": "CONTENT_OSS_ENDPOINT",
        f"{prefix}_OBJECT_STORAGE_BUCKET": "CONTENT_OSS_BUCKET",
        f"{prefix}_OBJECT_STORAGE_REGION": "CONTENT_OSS_REGION",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_ID": "CONTENT_OSS_ACCESS_KEY_ID",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_SECRET": "CONTENT_OSS_ACCESS_KEY_SECRET",
        f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": "CONTENT_CDN_SIGN_KEY",
    }
    storage_to_compose = {
        f"{prefix}_OBJECT_STORAGE_ENDPOINT": "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT",
        f"{prefix}_OBJECT_STORAGE_BUCKET": "QWQ_COMPOSE_OBJECT_STORAGE_BUCKET",
        f"{prefix}_OBJECT_STORAGE_REGION": "QWQ_COMPOSE_OBJECT_STORAGE_REGION",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_ID": "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_SECRET": "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET",
        f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY",
    }
    for storage_key, content_key in storage_to_content.items():
        value = environment.get(storage_key)
        if value:
            environment[content_key] = value
    for storage_key, compose_key in storage_to_compose.items():
        value = environment.get(storage_key)
        if value:
            environment[compose_key] = value


def _gamma_start_command(args: argparse.Namespace) -> list[str]:
    command = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]
    if getattr(args, "skip_build", False):
        command.append("--skip-build")
    if getattr(args, "build_only", False):
        command.append("--build-only")
        build_services = str(getattr(args, "build_services", "")).strip()
        if build_services:
            command.extend(["--build-services", build_services])
    return command


def _materialize_release_evidence_configuration(
    env_name: str,
    *,
    target: str = "",
) -> dict[str, str]:
    """校验 CI release evidence 与环境自治服务包一致，并记录供应链证据。

    Release evidence 是可删除的回读副本，不再成为第二份运行配置。运行时始终只消费
    服务包中的 config/config.yaml，其 CONFIG_VERSION 为内容摘要。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    artifact_root_value = os.environ.get("QWQ_PROD_RELEASE_ARTIFACT_ROOT", "").strip()
    if not artifact_root_value:
        return {}
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = _stackctl.ROOT / artifact_root
    manifest_path = artifact_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prod release artifact manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"invalid release evidence manifest: {manifest_path}")
    allowed_statuses = (
        {"deployable", "released"}
        if env_name == "prod"
        else {"candidate-ready", "deployable", "released"}
    )
    from quwoquan_ops.ci.release_evidence_reader import (
        validate_frozen_diagnostic_snapshot,
    )

    validate_frozen_diagnostic_snapshot(
        manifest,
        artifact_dir=artifact_root,
        allowed_statuses=allowed_statuses,
    )
    candidate_id = str(manifest["candidateId"])
    configuration_packages = manifest["environmentArtifacts"][env_name][
        "configurationPackages"
    ]
    package_root = _stackctl.deployment_target_path(
        _stackctl.deployment_target_for_env(env_name, target=target),
        "packages",
        "services",
    )
    archive_digest = _stackctl._sha256_file(manifest_path)
    for service, descriptor in configuration_packages.items():
        relative_path = str(descriptor["path"])
        source = artifact_root / relative_path
        if not source.is_file():
            raise FileNotFoundError(
                f"{env_name} release evidence file missing: {source}"
            )
        destination_dir = package_root / str(service)
        report_path = destination_dir / "provenance.json"
        effective_config = destination_dir / "config/config.yaml"
        if not report_path.is_file() or not effective_config.is_file():
            raise FileNotFoundError(f"prod service package missing: {destination_dir}")
        source_digest = _stackctl._sha256_file(source)
        effective_digest = _stackctl._sha256_file(effective_config)
        if source_digest != effective_digest:
            raise ValueError(
                "release evidence config differs from autonomous package: "
                f"{env_name}/{service}"
            )
        provenance = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(provenance, dict):
            raise ValueError(f"service package provenance missing: {report_path}")
        if (provenance.get("digests") or {}).get("config") != effective_digest:
            raise ValueError(f"service package config provenance invalid: {report_path}")
        provenance["releaseEvidence"] = {
            "manifest": _stackctl.relpath(manifest_path),
            "evidenceFileDigest": archive_digest,
            "artifactDigest": manifest["artifactDigest"],
            "candidateId": candidate_id,
            "verifiedConfigDigest": effective_digest,
        }
        _stackctl.write_json(report_path, provenance)
    source = manifest["source"]
    return {
        "candidateId": candidate_id,
        "artifactDigest": str(manifest["artifactDigest"]),
        "sourceGitSha": str(source["gitSha"]),
        "sourceTreeDigest": str(source["treeDigest"]),
    }
