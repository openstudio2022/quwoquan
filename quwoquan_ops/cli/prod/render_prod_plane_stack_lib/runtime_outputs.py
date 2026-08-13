"""stack.env / systemd / observability 渲染落盘（从 render_prod_plane_stack.py 逐字搬移）。

``_write_env_file`` 对预检密钥材料的读取必须经入口模块属性访问：
测试在 ``render_prod_plane_stack`` 模块上 monkeypatch
``_prevalidation_secret_environment`` 后调用本函数。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.output_paths import deployment_target_path
from quwoquan_ops.cli.lib.output_paths import remove_deployment_tree

from .constants import OBSERVABILITY_SOURCE_ROOT, ROOT
from .package_inputs import _plane_spec
from .public_hosts import _prod_public_hosts

def _write_env_file(
    output_root: Path,
    candidate_digest: str,
    image_transport_tag: str,
    instance: str,
) -> None:
    from urllib.parse import urlsplit, urlunsplit

    # 延迟导入入口模块：测试会在入口模块上 monkeypatch
    # _prevalidation_secret_environment，必须走模块属性访问。
    from quwoquan_ops.cli.prod import render_prod_plane_stack as _stack

    public_bases = (
        get_target(load_environment_topology(), "prod-hosted").get("publicBases")
        or {}
    )
    public_hosts = _prod_public_hosts()
    media_delivery = urlsplit(str(public_bases["mediaImage"]))
    lines = [
        f"LOCAL_GAMMA_CONFIG_VERSION={candidate_digest}",
        f"LOCAL_GAMMA_IMAGE_VERSION={image_transport_tag}",
        (
            "LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE="
            f"localhost/quwoquan_service_realtime-gateway:{image_transport_tag}"
        ),
        (
            "LOCAL_GAMMA_RTC_SERVICE_IMAGE="
            f"localhost/quwoquan_service_rtc-service:{image_transport_tag}"
        ),
        f"LOCAL_GAMMA_TLS_MODE={'internal' if instance in {'gray', 'prevalidate'} else 'automatic'}",
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL="
        + urlunsplit((media_delivery.scheme, media_delivery.netloc, "", "", "")),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL=" + str(public_bases["mediaUpload"]),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL=" + str(public_bases["publicWeb"]),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL=" + str(public_bases["mediaAvatar"]),
        "QWQ_PUBLIC_API_HOST=" + public_hosts["api"],
        "QWQ_PUBLIC_WEB_HOST=" + public_hosts["publicWeb"],
        "QWQ_PUBLIC_RTC_HOST=" + public_hosts["rtc"],
        "QWQ_PUBLIC_OPS_HOST=" + public_hosts["productOps"],
        "QWQ_PUBLIC_CDN_HOST=" + public_hosts["mediaImage"],
    ]
    if instance == "prevalidate":
        auth = _stack._prevalidation_secret_environment()
        otp_key_version = "prod-hosted-prevalidation-k1"
        lines.extend(
            [
                "LOCAL_GAMMA_HTTP_PORT=39000",
                "LOCAL_GAMMA_PRODUCT_OPS_PORT=39010",
                "LOCAL_GAMMA_MEDIA_EDGE_PORT=39100",
                "LOCAL_GAMMA_HTTPS_PORT=38443",
                "LOCAL_GAMMA_ADMIN_PORT=32019",
                "LOCAL_GAMMA_CHAT_PORT=39200",
                "LOCAL_GAMMA_USER_PORT=39210",
                "LOCAL_GAMMA_CONTENT_PORT=39220",
                "LOCAL_GAMMA_ASSISTANT_PORT=39230",
                "LOCAL_GAMMA_REC_MODEL_PORT=39240",
                "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT=39250",
                "LOCAL_GAMMA_TAG_PORT=39270",
                "LOCAL_GAMMA_ENTITY_PORT=39290",
                "LOCAL_GAMMA_INTEGRATION_PORT=39310",
                "LOCAL_GAMMA_NOTIFICATION_PORT=39320",
                "LOCAL_GAMMA_REALTIME_PORT=39340",
                "LOCAL_GAMMA_RTC_PORT=39350",
                "LOCAL_GAMMA_POSTGRES_PORT=39400",
                "LOCAL_GAMMA_MONGO_PORT=39410",
                "LOCAL_GAMMA_REDIS_PORT=39420",
                "LOCAL_GAMMA_ES_PORT=39430",
                "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT=39440",
                "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT=object-storage:9000",
                "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID=prevalidation-only",
                "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_SECRET=prevalidation-only-not-production",
                "LOCAL_GAMMA_OBJECT_STORAGE_BUCKET=prevalidation-empty",
                "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT=http://object-storage:9000",
                "QWQ_COMPOSE_OBJECT_STORAGE_BUCKET=prevalidation-empty",
                "QWQ_COMPOSE_OBJECT_STORAGE_REGION=prevalidation-local",
                "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID=prevalidation-only",
                "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET=prevalidation-only-not-production",
                (
                    "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY="
                    + auth["QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY"]
                ),
                "AUTH_JWT_SECRET=" + auth["AUTH_JWT_SECRET"],
                "AUTH_JWT_ISSUER=quwoquan.prod-hosted.prevalidation",
                "AUTH_JWT_AUDIENCE=quwoquan-app",
                "AUTH_JWT_TOKEN_VERSION=1",
                "AUTH_DEVICE_TICKET_SECRET=" + auth["AUTH_DEVICE_TICKET_SECRET"],
                "AUTH_DEVICE_TICKET_ISSUER=quwoquan.prod-hosted.prevalidation.device",
                "AUTH_DEVICE_TICKET_AUDIENCE=quwoquan-app-device",
                "AUTH_DEVICE_TICKET_TOKEN_VERSION=1",
                "OTP_CODE_REF_ACTIVE_KEY_VERSION=" + otp_key_version,
                "OTP_CODE_REF_KEYS_JSON="
                + json.dumps(
                    {otp_key_version: auth["OTP_CODE_REF_KEY"]},
                    separators=(",", ":"),
                ),
                "QWQ_PUSH_TOKEN_ENCRYPTION_KEY="
                + auth["QWQ_PUSH_TOKEN_ENCRYPTION_KEY"],
                "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET="
                + auth["CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET"],
                "RUNTIME_LOG_INGEST_TOKEN=prevalidation-not-release-evidence",
                "ALERT_INGEST_TOKEN=prevalidation-not-release-evidence",
                "OPS_OIDC_ISSUER=https://provider-unavailable.invalid",
                "OPS_OIDC_AUDIENCE=quwoquan-prevalidation",
                "OPS_OIDC_JWKS_URL=https://provider-unavailable.invalid/jwks.json",
                "PROD_RTC_MEDIA_CONNECTION_URL=wss://sfu-unavailable.invalid",
                "PROD_RTC_MEDIA_API_KEY=provider-unavailable",
                "PROD_RTC_MEDIA_API_SECRET=provider-unavailable",
                "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT=http://elasticsearch:9200",
                "PRODUCT_OPS_ELASTICSEARCH_API_KEY=prevalidation-not-release-evidence",
            ]
        )
    elif instance == "gray":
        lines.extend(
            [
                "LOCAL_GAMMA_HTTP_PORT=29000",
                "LOCAL_GAMMA_PRODUCT_OPS_PORT=29010",
                "LOCAL_GAMMA_MEDIA_EDGE_PORT=29100",
                "LOCAL_GAMMA_HTTPS_PORT=28443",
                "LOCAL_GAMMA_ADMIN_PORT=22019",
                "LOCAL_GAMMA_CHAT_PORT=29200",
                "LOCAL_GAMMA_USER_PORT=29210",
                "LOCAL_GAMMA_CONTENT_PORT=29220",
                "LOCAL_GAMMA_ASSISTANT_PORT=29230",
                "LOCAL_GAMMA_REC_MODEL_PORT=29240",
                "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT=29250",
                "LOCAL_GAMMA_TAG_PORT=29270",
                "LOCAL_GAMMA_ENTITY_PORT=29290",
                "LOCAL_GAMMA_INTEGRATION_PORT=29310",
                "LOCAL_GAMMA_NOTIFICATION_PORT=29320",
                "LOCAL_GAMMA_REALTIME_PORT=29340",
                "LOCAL_GAMMA_RTC_PORT=29350",
                "LOCAL_GAMMA_POSTGRES_PORT=29400",
                "LOCAL_GAMMA_MONGO_PORT=29410",
                "LOCAL_GAMMA_REDIS_PORT=29420",
            ]
        )
    else:
        lines.extend(
            [
                "LOCAL_GAMMA_HTTP_PORT=19000",
                "LOCAL_GAMMA_PRODUCT_OPS_PORT=19010",
                "LOCAL_GAMMA_MEDIA_EDGE_PORT=19100",
                "LOCAL_GAMMA_HTTPS_PORT=18443",
                "LOCAL_GAMMA_ADMIN_PORT=12019",
                "LOCAL_GAMMA_CHAT_PORT=19200",
                "LOCAL_GAMMA_USER_PORT=19210",
                "LOCAL_GAMMA_CONTENT_PORT=19220",
                "LOCAL_GAMMA_ASSISTANT_PORT=19230",
                "LOCAL_GAMMA_REC_MODEL_PORT=19240",
                "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT=19250",
                "LOCAL_GAMMA_TAG_PORT=19270",
                "LOCAL_GAMMA_ENTITY_PORT=19290",
                "LOCAL_GAMMA_INTEGRATION_PORT=19310",
                "LOCAL_GAMMA_NOTIFICATION_PORT=19320",
                "LOCAL_GAMMA_REALTIME_PORT=19340",
                "LOCAL_GAMMA_RTC_PORT=19350",
                "LOCAL_GAMMA_POSTGRES_PORT=19400",
                "LOCAL_GAMMA_MONGO_PORT=19410",
                "LOCAL_GAMMA_REDIS_PORT=19420",
            ]
        )
    env_path = output_root / "stack.env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if instance == "prevalidate":
        env_path.chmod(0o600)


def _write_runtime_systemd_unit(
    output_root: Path,
    *,
    plane: dict[str, Any],
    plane_name: str,
    instance: str,
    replica_id: str,
    remote_root: str,
    startup_services: list[str],
) -> str:
    credentials_root = str(plane.get("credentialsPath") or "").strip()
    if not remote_root.startswith("/") or not credentials_root.startswith("/"):
        raise SystemExit("FAIL: runtime systemd paths must be absolute")
    layout = plane.get("rootlessRuntimeLayout") or {}
    compose_file = str(layout.get("composeFile") or "docker-compose.prod-hosted.yaml")
    env_file = str(layout.get("envFile") or "stack.env")
    unit_name = f"quwoquan-{plane_name}-{instance}-{replica_id}.service"
    project = f"quwoquan-{plane_name}-{instance}-{replica_id}"
    services = " ".join(startup_services)
    unit_dir = output_root / "systemd"
    unit_dir.mkdir(parents=True, exist_ok=True)
    service_lines = [
        "[Unit]",
        f"Description=Quwoquan {plane_name} {instance} {replica_id} rootless stack",
        "Wants=network-online.target",
        "After=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        "RemainAfterExit=yes",
        f"WorkingDirectory={remote_root}",
    ]
    if instance != "prevalidate":
        service_lines.append(
            f"EnvironmentFile=-{credentials_root.rstrip('/')}/runtime.env"
        )
    service_lines.extend(
        [
            (
                f"ExecStart=/usr/bin/podman compose --env-file {env_file} "
                f"-f {compose_file} -p {project} up -d --remove-orphans {services}"
            ),
            (
                f"ExecStop=/usr/bin/podman compose --env-file {env_file} "
                f"-f {compose_file} -p {project} down"
            ),
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    unit_dir.joinpath(unit_name).write_text(
        "\n".join(service_lines),
        encoding="utf-8",
    )
    return unit_name


def _write_observability_tree(
    output_root: Path,
    plane_name: str,
    *,
    render_name: str,
    remote_root: str,
) -> dict[str, Any] | None:
    plane = _plane_spec(plane_name)
    runtime = plane.get("rootlessObservabilityRuntime")
    if runtime is None:
        return None
    if not isinstance(runtime, dict):
        raise SystemExit(
            f"FAIL: {plane_name}.rootlessObservabilityRuntime must be an object"
        )

    directory = Path(str(runtime.get("composeDirectory") or ""))
    compose_file = str(runtime.get("composeFile") or "").strip()
    systemd_unit_file = str(runtime.get("systemdUnitFile") or "").strip()
    runtime_env_file = str(runtime.get("runtimeEnvFile") or "").strip()
    service_network_name = str(runtime.get("serviceNetworkName") or "").strip()
    if (
        not directory.parts
        or directory.is_absolute()
        or ".." in directory.parts
        or not compose_file
        or Path(compose_file).name != compose_file
        or not systemd_unit_file.endswith(".service")
        or Path(systemd_unit_file).name != systemd_unit_file
        or not runtime_env_file
        or Path(runtime_env_file).name != runtime_env_file
        or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,62}", service_network_name)
    ):
        raise SystemExit(
            "FAIL: rootlessObservabilityRuntime compose directory/file must be safe"
        )
    source_compose = OBSERVABILITY_SOURCE_ROOT / compose_file
    required_files = (
        source_compose,
        OBSERVABILITY_SOURCE_ROOT / "prometheus.yml",
        OBSERVABILITY_SOURCE_ROOT / "alertmanager.yml",
        OBSERVABILITY_SOURCE_ROOT / "otel-collector.yml",
    )
    if any(not path.is_file() for path in required_files):
        missing = ", ".join(
            str(path.relative_to(ROOT))
            for path in required_files
            if not path.is_file()
        )
        raise SystemExit(f"FAIL: observability source is incomplete: {missing}")
    alerts = OBSERVABILITY_SOURCE_ROOT / "alerts"
    if not alerts.is_dir():
        raise SystemExit(f"FAIL: observability alerts directory is missing: {alerts}")

    destination = deployment_target_path(
        "prod-hosted",
        "rendered",
        render_name,
        *directory.parts,
    )
    if destination.exists():
        remove_deployment_tree(
            "prod-hosted",
            "rendered",
            render_name,
            *directory.parts,
        )
    destination.mkdir(parents=True)
    for source in required_files:
        shutil.copy2(source, destination / source.name)
    shutil.copytree(alerts, destination / "alerts")
    (destination / runtime_env_file).write_text(
        f"PROD_SERVICE_NETWORK={service_network_name}\n",
        encoding="utf-8",
    )
    compose_root = remote_root
    credentials_root = str(plane.get("credentialsPath") or "").strip()
    credentials_env = str(runtime.get("credentialsEnvFile") or "").strip()
    if not (
        compose_root.startswith("/")
        and credentials_root.startswith("/")
        and credentials_env
        and not Path(credentials_env).is_absolute()
        and ".." not in Path(credentials_env).parts
    ):
        raise SystemExit("FAIL: observability systemd paths must be absolute/safe")
    unit_dir = destination / "systemd"
    unit_dir.mkdir()
    credentials_env_path = f"{credentials_root.rstrip('/')}/{credentials_env}"
    unit_dir.joinpath(systemd_unit_file).write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Quwoquan production observability rootless stack",
                "Wants=network-online.target",
                "After=network-online.target",
                "",
                "[Service]",
                "Type=oneshot",
                "RemainAfterExit=yes",
                f"WorkingDirectory={compose_root}",
                (
                    "ExecStart=/usr/bin/podman compose --env-file stack.env "
                    f"--env-file {directory.as_posix()}/{runtime_env_file} "
                    f"--env-file {credentials_env_path} "
                    f"-f {directory.as_posix()}/{compose_file} "
                    "-p quwoquan-observability-prod up -d --remove-orphans"
                ),
                (
                    "ExecStop=/usr/bin/podman compose --env-file stack.env "
                    f"--env-file {directory.as_posix()}/{runtime_env_file} "
                    f"--env-file {credentials_env_path} "
                    f"-f {directory.as_posix()}/{compose_file} "
                    "-p quwoquan-observability-prod down"
                ),
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "composeDirectory": directory.as_posix(),
        "composeFile": compose_file,
        "systemdUnitFile": systemd_unit_file,
        "runtimeEnvFile": runtime_env_file,
        "serviceNetworkName": service_network_name,
        "credentialsEnvFile": str(runtime.get("credentialsEnvFile") or ""),
        "requiredEnvironment": list(runtime.get("requiredEnvironment") or []),
        "healthURLs": list(runtime.get("healthURLs") or []),
    }
