#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("FAIL: PyYAML required")

ROOT = Path(__file__).resolve().parents[3]
ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod_plane_access_isolation.yaml"
TOPOLOGY_MANIFEST = ROOT / "quwoquan_ops/environments/environment_topology_manifest.yaml"
STATE_GAMMA_CONFIG_ROOT = ROOT / ".qwq_output" / "env" / "gamma" / "local" / "gamma-local" / "config-root"
DEFAULT_OUTPUT_ROOT = ROOT / ".qwq_output" / "env" / "prod" / "local" / "prod-plane-stack"

CONFIG_PACKAGE_ALIAS = {
    "recommendation-service": "rec-model-service",
}
EXTERNAL_DATA_HOST = "host.containers.internal"
EXTERNAL_POSTGRES_PORT = 19400
EXTERNAL_MONGO_PORT = 19410
EXTERNAL_REDIS_PORT = 19420
EXTERNAL_MONGO_URI = f"mongodb://{EXTERNAL_DATA_HOST}:{EXTERNAL_MONGO_PORT}/?directConnection=true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render prod plane rootless stack from truth sources.",
    )
    parser.add_argument("--plane", default="service", choices=["service"])
    parser.add_argument("--instance", default="prod", choices=["gray", "prod"])
    parser.add_argument("--config-version", required=True)
    parser.add_argument("--image-version", default=os.environ.get("IMAGE_VERSION", "0.0.1"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT / "service"))
    parser.add_argument("--host", default="")
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must parse as object")
    return data


def _plane_spec(plane_name: str) -> dict[str, Any]:
    access = _load_yaml(ACCESS_MANIFEST)
    for plane in access.get("planes") or []:
        if str(plane.get("plane")) == plane_name:
            return plane
    raise SystemExit(f"FAIL: plane missing from access manifest: {plane_name}")


def _rewrite_volume(raw: str) -> str:
    return raw


def _compose_bind_source(path_value: str) -> str:
    value = str(path_value).strip()
    if not value:
        raise SystemExit("FAIL: compose bind source path is empty")
    if value.startswith("/"):
        return value
    if value.startswith("./"):
        return value
    return f"./{value}"


def _rewrite_volume_with_layout(
    raw: str,
    *,
    config_root: str,
    media_root: str,
    legal_root: str,
    caddyfile_path: str,
    model_cache_root: str,
) -> str:
    if raw == "local-gamma-model-cache:/app/cache":
        return f"{_compose_bind_source(model_cache_root)}:/app/cache"
    return (
        raw.replace("../.qwq_output/env/gamma/local/gamma-local/config-root", _compose_bind_source(config_root))
        .replace("../.qwq_output/env/gamma/local/gamma-local/media", _compose_bind_source(media_root))
        .replace(
            "${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-../.qwq_output/env/gamma/release/legal-static/current/public}",
            _compose_bind_source(legal_root),
        )
        .replace("../.qwq_output/env/gamma/local/gamma-local/Caddyfile", _compose_bind_source(caddyfile_path))
    )


def _named_volume_source(raw: str) -> str | None:
    if ":" not in raw:
        return None
    source = raw.split(":", 1)[0]
    if source.startswith(".") or source.startswith("/") or source.startswith("${"):
        return None
    return source


def _rewrite_service(
    name: str,
    spec: dict[str, Any],
    selected: set[str],
    *,
    config_root: str,
    media_root: str,
    legal_root: str,
    caddyfile_path: str,
    model_cache_root: str,
) -> dict[str, Any]:
    updated = copy.deepcopy(spec)
    updated.pop("build", None)
    if isinstance(updated.get("depends_on"), dict):
        updated["depends_on"] = {
            dep: dep_spec
            for dep, dep_spec in updated["depends_on"].items()
            if dep in selected
        }
    environment = updated.get("environment")
    if isinstance(environment, dict) and environment.get("APP_ENV") == "gamma":
        environment["APP_ENV"] = "prod"
    if isinstance(environment, dict):
        if name == "rec-model-service":
            environment["MONGODB_URI"] = EXTERNAL_MONGO_URI
        if name == "content-service":
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["CONTENT_REDIS_REC_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CONTENT_REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "chat-service":
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CHAT_REDIS_REALTIME_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CHAT_REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["CHAT_REDIS_RELIABLE_TASK_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "user-service":
            environment["POSTGRES_DSN"] = (
                f"postgres://quwoquan:quwoquan@{EXTERNAL_DATA_HOST}:{EXTERNAL_POSTGRES_PORT}/"
                "quwoquan?sslmode=disable"
            )
            environment["MONGODB_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "assistant-service":
            environment["MONGODB_URI"] = EXTERNAL_MONGO_URI
            environment["REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["REDIS_REC_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "product-ops-service":
            environment["MONGO_URI"] = EXTERNAL_MONGO_URI
            environment["PRODUCT_OPS_REDIS_REC_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["PRODUCT_OPS_REDIS_GENERAL_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
        if name == "tag-service":
            environment["REDIS_ADDR"] = f"{EXTERNAL_DATA_HOST}:{EXTERNAL_REDIS_PORT}"
            environment["TAG_MONGO_URI"] = EXTERNAL_MONGO_URI
        if name == "entity-service":
            environment["ENTITY_MONGO_URI"] = EXTERNAL_MONGO_URI
            # prod-hosted 首波 service plane 不含 elasticsearch（search-service 未迁入），
            # 关闭 write-time 索引投影；主页读写主链路（Mongo homepage_state）不受影响。
            environment["SEARCH_ES_ENABLED"] = "false"
            environment.pop("SEARCH_ES_ENDPOINTS", None)
    if name != "gamma-proxy":
        extra_hosts = list(updated.get("extra_hosts") or [])
        if f"{EXTERNAL_DATA_HOST}:host-gateway" not in extra_hosts:
            extra_hosts.append(f"{EXTERNAL_DATA_HOST}:host-gateway")
        updated["extra_hosts"] = extra_hosts
    volumes = updated.get("volumes")
    if isinstance(volumes, list):
        updated["volumes"] = [
            (
                _rewrite_volume_with_layout(
                    item,
                    config_root=config_root,
                    media_root=media_root,
                    legal_root=legal_root,
                    caddyfile_path=caddyfile_path,
                    model_cache_root=model_cache_root,
                )
                if isinstance(item, str)
                else item
            )
            for item in volumes
        ]
    return updated


def _filter_top_level_volumes(services: dict[str, Any], top_level: dict[str, Any]) -> dict[str, Any]:
    referenced: set[str] = set()
    for spec in services.values():
        for item in spec.get("volumes") or []:
            if not isinstance(item, str):
                continue
            source = _named_volume_source(item)
            if source:
                referenced.add(source)
    return {name: value for name, value in top_level.items() if name in referenced}


def _ensure_mapping(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    node = payload
    for key in keys:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    return node


def _set_standalone_redis(spec: dict[str, Any], addr_placeholder: str) -> None:
    spec["mode"] = "standalone"
    spec["addr"] = addr_placeholder
    spec["addrs"] = []
    spec["tls"] = False


def _rewrite_env_override(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(payload)
    if service == "content-service":
        _ensure_mapping(updated, "mongo")["uri"] = "${MONGO_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "rec"), "${CONTENT_REDIS_REC_ADDR}")
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "general"),
            "${CONTENT_REDIS_GENERAL_ADDR}",
        )
        rec_model = _ensure_mapping(updated, "rec_model_service")
        rec_model["url"] = "${REC_MODEL_SERVICE_URL}"
        rec_model["enabled"] = True
    elif service == "chat-service":
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGO_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "realtime"), "${REDIS_ADDR}")
        _set_standalone_redis(_ensure_mapping(updated, "redis", "general"), "${REDIS_ADDR}")
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "reliabletask"),
            "${REDIS_ADDR}",
        )
    elif service == "user-service":
        _ensure_mapping(updated, "postgres")["dsn"] = "${POSTGRES_DSN}"
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGODB_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "general"), "${REDIS_ADDR}")
    elif service == "assistant-service":
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGODB_URI}"
        _set_standalone_redis(_ensure_mapping(updated, "redis", "rec"), "${REDIS_REC_ADDR}")
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "general"),
            "${REDIS_GENERAL_ADDR}",
        )
    elif service == "product-ops-service":
        _ensure_mapping(updated, "mongodb")["uri"] = "${MONGO_URI}"
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "rec"),
            "${PRODUCT_OPS_REDIS_REC_ADDR}",
        )
        _set_standalone_redis(
            _ensure_mapping(updated, "redis", "general"),
            "${PRODUCT_OPS_REDIS_GENERAL_ADDR}",
        )
    elif service == "tag-service":
        _set_standalone_redis(_ensure_mapping(updated, "redis", "rec"), "${REDIS_ADDR}")
        _set_standalone_redis(_ensure_mapping(updated, "redis", "general"), "${REDIS_ADDR}")
    elif service == "entity-service":
        # mongo 经 ENTITY_MONGO_URI env 注入；prod-hosted 首波无 ES，配置层同步关闭。
        _ensure_mapping(updated, "es")["enabled"] = False
    return updated


def _write_config_tree(
    *,
    config_services: list[str],
    config_version: str,
    output_root: Path,
) -> None:
    config_root = output_root / "runtime" / "config-root"
    for service in config_services:
        package_service = CONFIG_PACKAGE_ALIAS.get(service, service)
        package_dir = ROOT / ".qwq_output" / "env" / "prod" / "release" / "service" / package_service
        if not package_dir.is_dir():
            raise SystemExit(f"FAIL: missing prod service package for {service}: {package_dir}")
        default_src = package_dir / "default_config.yaml"
        env_src = package_dir / "config.yaml"
        if not default_src.is_file() or not env_src.is_file():
            raise SystemExit(f"FAIL: incomplete service package for {service}: {package_dir}")
        target_default = config_root / "configs" / service / "default" / "config.yaml"
        target_env = config_root / "configs" / service / "prod" / "config.yaml"
        target_default.parent.mkdir(parents=True, exist_ok=True)
        target_env.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_src, target_default)
        env_payload = yaml.safe_load(env_src.read_text(encoding="utf-8")) or {}
        if not isinstance(env_payload, dict):
            raise SystemExit(f"FAIL: env override must be object: {env_src}")
        target_env.write_text(
            yaml.safe_dump(
                _rewrite_env_override(service, env_payload),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        release_candidates = [
            ROOT / "releases" / "config" / service / f"{config_version}.yaml",
            ROOT / "releases" / "config" / package_service / f"{config_version}.yaml",
            STATE_GAMMA_CONFIG_ROOT / "releases" / "config" / service / f"{config_version}.yaml",
            STATE_GAMMA_CONFIG_ROOT / "releases" / "config" / package_service / f"{config_version}.yaml",
        ]
        release_target = config_root / "releases" / "config" / service / f"{config_version}.yaml"
        release_target.parent.mkdir(parents=True, exist_ok=True)
        for candidate in release_candidates:
            if candidate.is_file():
                shutil.copy2(candidate, release_target)
                break
        else:
            release_target.write_text(
                yaml.safe_dump(
                    {
                        "config": {"version": config_version},
                        "service": {"name": service},
                    },
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

    shared_dir = config_root / "deploy" / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    for rel in (
        "quwoquan_ops/environments/reliable_task_module_catalog.yaml",
        "quwoquan_ops/environments/reliable_task_retention_policy.yaml",
    ):
        src = ROOT / rel
        if src.is_file():
            shutil.copy2(src, shared_dir / src.name)


def _prod_public_edge_ip() -> str:
    """从环境拓扑真相源解析 prod-hosted 公网 edge IP。

    topology publicBases 以 IP 声明公共基址，而 Caddy 站点按域名 SNI 匹配；
    IP 直连（无 SNI）必须由 IP 站点别名承接，否则 health/media URL 结构性不可达。
    """
    from urllib.parse import urlparse

    topology = _load_yaml(TOPOLOGY_MANIFEST)
    api_base = str(
        ((topology.get("targets") or {}).get("prod-hosted") or {}).get("publicBases", {}).get("api", "")
    )
    host = urlparse(api_base).hostname
    if not host:
        raise SystemExit("FAIL: topology prod-hosted publicBases.api missing/unparsable")
    return host


def _write_caddyfile(output_root: Path) -> None:
    target = output_root / "runtime" / "Caddyfile"
    target.parent.mkdir(parents=True, exist_ok=True)
    edge_ip = _prod_public_edge_ip()
    caddy_text = """{
\tadmin 0.0.0.0:2019
\tlocal_certs
}

(local_gamma_tls) {
\ttls internal
}

(media_cors) {
\theader {
\t\tAccess-Control-Allow-Origin "*"
\t\tAccess-Control-Allow-Methods "GET, HEAD, OPTIONS"
\t\tAccess-Control-Allow-Headers "*"
\t\tCross-Origin-Resource-Policy "cross-origin"
\t}
}

prod-api.quwoquan-env.test {
\timport local_gamma_tls
\thandle /healthz {
\t\treverse_proxy content-service:18080
\t}
\thandle /v1/config/app {
\t\treverse_proxy content-service:18080
\t}
\thandle /livez {
\t\treverse_proxy content-service:18080
\t}
\thandle /startupz {
\t\treverse_proxy content-service:18080
\t}
\t@api_content path /v1/content*
\thandle @api_content {
\t\treverse_proxy content-service:18080
\t}
\t@api_chat path /v1/chat*
\thandle @api_chat {
\t\treverse_proxy chat-service:18081
\t}
\t@api_user path /v1/user* /v1/me /v1/me/*
\thandle @api_user {
\t\treverse_proxy user-service:18082
\t}
\t@api_assistant path /v1/assistant*
\thandle @api_assistant {
\t\treverse_proxy assistant-service:18087
\t}
\t@api_tag path /v1/tag*
\thandle @api_tag {
\t\treverse_proxy tag-service:18092
\t}
\t@api_entity path /v1/homepages*
\thandle @api_entity {
\t\treverse_proxy entity-service:18084
\t}
\thandle /v1/ops/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /v1/control-plane/product/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /legal/* {
\t\theader {
\t\t\tCache-Control "public, max-age=300"
\t\t\tX-Content-Type-Options "nosniff"
\t\t}
\t\troot * /srv/legal
\t\tfile_server
\t}
\thandle /media/* {
\t\timport media_cors
\t\troot * /srv/media
\t\tfile_server
\t}
\thandle {
\t\trespond "prod-hosted route is not ready for this path" 404
\t}
}

prod-product-ops.quwoquan-env.test {
\timport local_gamma_tls
\thandle /healthz {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /v1/ops/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle {
\t\trespond "prod-hosted product-ops route is not ready for this path" 404
\t}
}

prod-avatar.quwoquan-env.test,
prod-image.quwoquan-env.test,
prod-video.quwoquan-env.test,
prod-upload.quwoquan-env.test {
\timport local_gamma_tls
\timport media_cors
\troot * /srv/media
\tfile_server
}

:80 {
\thandle /healthz {
\t\treverse_proxy content-service:18080
\t}
\thandle /v1/config/app {
\t\treverse_proxy content-service:18080
\t}
\t@pub_content path /v1/content*
\thandle @pub_content {
\t\treverse_proxy content-service:18080
\t}
\t@pub_chat path /v1/chat*
\thandle @pub_chat {
\t\treverse_proxy chat-service:18081
\t}
\t@pub_user path /v1/user* /v1/me /v1/me/*
\thandle @pub_user {
\t\treverse_proxy user-service:18082
\t}
\t@pub_assistant path /v1/assistant*
\thandle @pub_assistant {
\t\treverse_proxy assistant-service:18087
\t}
\t@pub_tag path /v1/tag*
\thandle @pub_tag {
\t\treverse_proxy tag-service:18092
\t}
\t@pub_entity path /v1/homepages*
\thandle @pub_entity {
\t\treverse_proxy entity-service:18084
\t}
\thandle /v1/ops/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /v1/control-plane/product/* {
\t\treverse_proxy product-ops-service:18086
\t}
\thandle /legal/* {
\t\theader {
\t\t\tCache-Control "public, max-age=300"
\t\t\tX-Content-Type-Options "nosniff"
\t\t}
\t\troot * /srv/legal
\t\tfile_server
\t}
\thandle /media/* {
\t\timport media_cors
\t\troot * /srv/media
\t\tfile_server
\t}
\thandle {
\t\trespond "prod-hosted route is not ready for this path" 404
\t}
}
"""
    # topology publicBases 以 IP 声明；给 api 站点追加 IP 地址别名，并用 default_sni
    # 把无 SNI 的 IP 直连归位到该站点，否则 TLS 握手无匹配证书（alert internal error）。
    caddy_text = caddy_text.replace(
        "prod-api.quwoquan-env.test {",
        f"prod-api.quwoquan-env.test, {edge_ip} {{",
    )
    caddy_text = caddy_text.replace(
        "\tlocal_certs",
        f"\tlocal_certs\n\tdefault_sni {edge_ip}",
    )
    target.write_text(caddy_text, encoding="utf-8")


def _write_env_file(
    output_root: Path,
    config_version: str,
    image_version: str,
    instance: str,
) -> None:
    lines = [
        f"LOCAL_GAMMA_CONFIG_VERSION={config_version}",
        f"LOCAL_GAMMA_IMAGE_VERSION={image_version}",
        "LOCAL_GAMMA_TLS_MODE=internal",
    ]
    if instance == "gray":
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
                "LOCAL_GAMMA_POSTGRES_PORT=19400",
                "LOCAL_GAMMA_MONGO_PORT=19410",
                "LOCAL_GAMMA_REDIS_PORT=19420",
            ]
        )
    (output_root / "stack.env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    plane = _plane_spec(args.plane)
    compose_template = ROOT / str(plane.get("rootlessComposeTemplate") or "")
    if not compose_template.is_file():
        raise SystemExit(f"FAIL: missing compose template: {compose_template}")

    governed = [str(item) for item in plane.get("rootlessGovernedComposeServices") or []]
    support = [str(item) for item in plane.get("rootlessSupportComposeServices") or []]
    config_services = [str(item) for item in plane.get("rootlessConfigServices") or []]
    selected = governed + support
    if not selected:
        raise SystemExit(f"FAIL: plane {args.plane} missing rootless compose service list")

    layout = plane.get("rootlessRuntimeLayout") or {}
    config_root = str(layout.get("configRoot") or "runtime/config-root")
    caddyfile_path = str(layout.get("caddyfile") or "runtime/Caddyfile")
    media_root = str(layout.get("mediaRoot") or "runtime/media")
    legal_root = str(layout.get("legalStaticRoot") or "runtime/legal-static")
    model_cache_root = str(layout.get("modelCacheRoot") or "runtime/model-cache")
    if Path(config_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.configRoot must remain relative")
    if Path(caddyfile_path).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.caddyfile must remain relative")
    if Path(legal_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.legalStaticRoot must remain relative")
    if Path(model_cache_root).is_absolute():
        raise SystemExit("FAIL: rootlessRuntimeLayout.modelCacheRoot must remain relative")

    output_root = Path(args.output_dir).expanduser().resolve()
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    if not Path(media_root).is_absolute():
        (output_root / media_root).mkdir(parents=True, exist_ok=True)
    legal_package_public = ROOT / ".qwq_output" / "env" / "prod" / "release" / "legal-static" / "current" / "public"
    legal_output_root = output_root / legal_root
    if legal_output_root.exists():
        shutil.rmtree(legal_output_root)
    if legal_package_public.is_dir():
        shutil.copytree(legal_package_public, legal_output_root)
    else:
        legal_output_root.mkdir(parents=True, exist_ok=True)
    (output_root / model_cache_root).mkdir(parents=True, exist_ok=True)

    template = _load_yaml(compose_template)
    services = template.get("services") or {}
    rendered_services: dict[str, Any] = {}
    selected_names = set(selected)
    for service_name in selected:
        raw = services.get(service_name)
        if raw is None:
            raise SystemExit(
                f"FAIL: compose template missing selected service {service_name}: {compose_template}"
            )
        rendered_services[service_name] = _rewrite_service(
            service_name,
            raw,
            selected_names,
            config_root=config_root,
            media_root=media_root,
            legal_root=legal_root,
            caddyfile_path=caddyfile_path,
            model_cache_root=model_cache_root,
        )

    compose_payload: dict[str, Any] = {"services": rendered_services}
    top_level_volumes = template.get("volumes")
    if isinstance(top_level_volumes, dict):
        filtered = _filter_top_level_volumes(rendered_services, top_level_volumes)
        if filtered:
            compose_payload["volumes"] = filtered

    compose_file_name = (
        ((plane.get("rootlessRuntimeLayout") or {}).get("composeFile"))
        or "docker-compose.prod-hosted.yaml"
    )
    compose_out = output_root / str(compose_file_name)
    compose_out.write_text(
        yaml.safe_dump(compose_payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    _write_config_tree(
        config_services=config_services,
        config_version=args.config_version,
        output_root=output_root,
    )
    _write_caddyfile(output_root)
    _write_env_file(output_root, args.config_version, args.image_version, args.instance)

    report = {
        "plane": args.plane,
        "host": args.host or "",
        "composeTemplate": str(compose_template.relative_to(ROOT)),
        "composeFile": str(compose_out.relative_to(ROOT) if compose_out.is_relative_to(ROOT) else compose_out),
        "instance": args.instance,
        "governedComposeServices": governed,
        "supportComposeServices": support,
        "configServices": config_services,
        "configVersion": args.config_version,
        "outputDir": str(output_root),
        "mediaRoot": media_root,
        "legalStaticRoot": legal_root,
        "legalStaticSource": str(legal_package_public),
    }
    (output_root / "render_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
