"""Run the real Alpha-local content release data plane.

This adapter owns only process wiring.  It consumes service-owned Alpha
packages and release media written by ``qwq-data ship apply``; it never seeds
or copies fixture content.  All deployment configuration and PKI live in the
external deploy workspace, while process records and logs are disposable
``.qwq_output`` state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_alpha_object_storage import (
    prepare_local_alpha_object_storage,
)
from quwoquan_ops.cli.lib.local_environment_auth import (
    prepare_local_environment_auth,
)
from quwoquan_ops.cli.lib.immutable_image_composition import (
    bind_packaged_image_composition,
)
from quwoquan_ops.cli.lib.local_provider_credentials import (
    load_protected_provider_environment,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    assert_local_runtime_available,
)
from quwoquan_ops.cli.lib.observability import write_run_manifest
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import (
    deployment_target_path,
    env_observability_run_dir,
    env_run_dir,
    legal_static_deployment_package_dir,
    service_deployment_package_dir,
    target_cache_dir,
    target_process_dir,
)
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports
from quwoquan_ops.cli.lib.public_domain_tls import certificate_paths


ENVIRONMENT = "alpha"
TARGET = "alpha-local"
COMPOSE_PROJECT = "quwoquan-alpha-content-release"
CADDY_NAME = "quwoquan_alpha_content_release_caddy"
SERVICE_NAMES = (
    "content-service",
    "entity-service",
    "recommendation-service",
    "user-service",
)
COMPOSE_SERVICES = ("postgres", "mongodb", "mongo-init", "redis", "object-storage", "object-storage-init", "recommendation-service", "content-service", "user-service")


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    process_dir: Path
    media_root: Path
    run_root: Path
    observability_root: Path
    logs_root: Path
    config_root: Path
    legal_root: Path
    caddyfile: Path

    @property
    def state_path(self) -> Path:
        return self.process_dir / "content-release.json"


def _run(arguments: list[str], *, env: Mapping[str, str] | None = None) -> None:
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env=dict(env) if env else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no process output"
        raise RuntimeError(f"command failed ({arguments[0]}): {detail[-1200:]}")


def _paths(*, new_run: bool = False) -> RuntimePaths:
    process_dir = target_process_dir(TARGET)
    cache_root = target_cache_dir(TARGET)
    external_root = deployment_target_path(TARGET, "rendered", "content-release")
    configured_run = os.environ.get("QWQ_RUN_ROOT", "").strip()
    configured_observability = os.environ.get("QWQ_OBSERVABILITY_RUN_ROOT", "").strip()
    if configured_run:
        run_root = Path(configured_run)
    elif new_run:
        run_root = env_run_dir(ENVIRONMENT, "up", target=TARGET)
    else:
        run_root = process_dir
    if configured_observability:
        observability_root = Path(configured_observability)
    elif new_run or configured_run:
        observability_root = env_observability_run_dir(ENVIRONMENT, run_root.name)
    else:
        observability_root = env_observability_run_dir(
            ENVIRONMENT,
            "alpha-content-release-local",
        )
    return RuntimePaths(
        process_dir=process_dir,
        media_root=cache_root / "media",
        run_root=run_root,
        observability_root=observability_root,
        logs_root=observability_root / "logs" / "service",
        config_root=external_root / "config-root",
        legal_root=legal_static_deployment_package_dir(ENVIRONMENT) / "current" / "public",
        caddyfile=external_root / "public.Caddyfile",
    )


def _materialize_observability_run(paths: RuntimePaths) -> None:
    """Create the run manifest before any managed process can emit logs."""
    paths.run_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        paths.observability_root,
        env_name=ENVIRONMENT,
        run_id=paths.observability_root.name,
        command="up",
        target=TARGET,
        report_dir=paths.run_root,
    )


def _service_package_config(service: str) -> Path:
    package = service_deployment_package_dir(ENVIRONMENT, service, target=TARGET)
    config = package / "config" / "config.yaml"
    provenance = package / "provenance.json"
    if not config.is_file() or not provenance.is_file():
        raise RuntimeError(f"service package is incomplete: {service}")
    return config


def _prepare_config_root(paths: RuntimePaths) -> dict[str, str]:
    paths.config_root.mkdir(parents=True, exist_ok=True)
    if not (paths.legal_root / "legal" / "user-agreement").is_file():
        raise RuntimeError("Alpha legal-static package is incomplete")
    versions: dict[str, str] = {}
    for service in SERVICE_NAMES:
        _run([
            sys.executable,
            "quwoquan_ops/cli/stackctl.py",
            "package",
            "--env",
            ENVIRONMENT,
            "--service",
            service,
        ])
        package = service_deployment_package_dir(ENVIRONMENT, service, target=TARGET)
        config = _service_package_config(service)
        payload = json.loads((package / "provenance.json").read_text(encoding="utf-8"))
        if payload.get("service") != service or payload.get("environment") != ENVIRONMENT:
            raise RuntimeError(f"service package provenance is invalid: {service}")
        version = str(payload.get("configVersion") or "")
        if not version.startswith("sha256:"):
            raise RuntimeError(f"service package has no config digest: {service}")
        target = paths.config_root / f"{service}.yaml"
        target.write_bytes(config.read_bytes())
        versions[service] = version
    return versions


def _compose_build_environment() -> dict[str, str]:
    target = get_target(load_environment_topology(), TARGET)
    public_bases = target.get("publicBases") or {}
    build_images = target.get("buildImages")
    if not isinstance(build_images, Mapping):
        raise RuntimeError(f"{TARGET}.buildImages policy must be an object")

    def required_image(name: str) -> str:
        value = build_images.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"{TARGET}.buildImages.{name} must be a non-empty string"
            )
        return value.strip()

    media_delivery = urlsplit(str(public_bases["mediaImage"]))
    return {
        "QWQ_COMPOSE_GO_BASE_IMAGE": required_image("goBaseImage"),
        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": required_image("alpineBaseImage"),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL": str(public_bases["publicWeb"]),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL": urlunsplit(
            (media_delivery.scheme, media_delivery.netloc, "", "", "")
        ),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
    }


def _base_environment(paths: RuntimePaths, versions: Mapping[str, str]) -> dict[str, str]:
    ports = profile_ports(load_port_manifest(), TARGET)
    auth = prepare_local_environment_auth(ENVIRONMENT, TARGET)
    provider = load_protected_provider_environment(
        environment=ENVIRONMENT,
        target_name=TARGET,
    )
    storage = prepare_local_alpha_object_storage(edge_port=ports["object-storage-edge"])
    env = os.environ.copy()
    env.update(auth.environment)
    env.update(provider)
    env.update(storage.environment)
    env.update(_compose_build_environment())
    env.update(
        {
            "QWQ_LOCAL_POSTGRES_PORT": str(ports["postgres"]),
            "QWQ_LOCAL_MONGO_PORT": str(ports["mongodb"]),
            "QWQ_LOCAL_REDIS_PORT": str(ports["redis"]),
            "QWQ_LOCAL_OBJECT_STORAGE_EDGE_PORT": str(ports["object-storage-edge"]),
            "QWQ_LOCAL_PUBLIC_UPLOAD_HOST": env["ALPHA_OBJECT_STORAGE_ENDPOINT"].rsplit(
                ":", 1
            )[0],
            "QWQ_LOCAL_OBJECT_STORAGE_BUCKET": env["ALPHA_OBJECT_STORAGE_BUCKET"],
            "QWQ_LOCAL_OBJECT_STORAGE_ACCESS_KEY_ID": env["ALPHA_OBJECT_STORAGE_ACCESS_KEY_ID"],
            "QWQ_LOCAL_OBJECT_STORAGE_ACCESS_KEY_SECRET": env["ALPHA_OBJECT_STORAGE_ACCESS_KEY_SECRET"],
            "QWQ_LOCAL_OBJECT_STORAGE_TLS_DIR": env["ALPHA_OBJECT_STORAGE_TLS_DIR"],
            "QWQ_COMPOSE_ENV": ENVIRONMENT,
            "QWQ_COMPOSE_CONFIG_ROOT": str(paths.config_root),
            "QWQ_COMPOSE_CONTENT_SERVICE_CONFIG_VERSION": versions["content-service"],
            "QWQ_COMPOSE_RECOMMENDATION_SERVICE_CONFIG_VERSION": versions["recommendation-service"],
            "QWQ_COMPOSE_USER_SERVICE_CONFIG_VERSION": versions["user-service"],
            "QWQ_COMPOSE_CONTENT_PORT": str(ports["content-service"]),
            "QWQ_COMPOSE_USER_PORT": str(ports["user-service"]),
            "QWQ_COMPOSE_REC_MODEL_PORT": str(ports["recommendation-service"]),
            "QWQ_COMPOSE_MONGO_URI": "mongodb://mongodb:27017/?replicaSet=rs0",
            "QWQ_COMPOSE_MONGODB_URI": "mongodb://mongodb:27017/?replicaSet=rs0",
            "QWQ_COMPOSE_SEARCH_ES_ENABLED": "false",
            "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT": env["ALPHA_OBJECT_STORAGE_ENDPOINT"],
            "QWQ_COMPOSE_OBJECT_STORAGE_BUCKET": env["ALPHA_OBJECT_STORAGE_BUCKET"],
            "QWQ_COMPOSE_OBJECT_STORAGE_REGION": env["ALPHA_OBJECT_STORAGE_REGION"],
            "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID": env["ALPHA_OBJECT_STORAGE_ACCESS_KEY_ID"],
            "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET": env["ALPHA_OBJECT_STORAGE_ACCESS_KEY_SECRET"],
            "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY": env["ALPHA_OBJECT_STORAGE_CDN_SIGN_KEY"],
            "QWQ_COMPOSE_EMBEDDING_ENDPOINT": env["CONTENT_EMBEDDING_ENDPOINT"],
            "QWQ_COMPOSE_EMBEDDING_API_KEY": env["CONTENT_EMBEDDING_API_KEY"],
            "QWQ_COMPOSE_REC_POLICY_SOURCE": str(
                ROOT / "quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
            ),
        }
    )
    bind_packaged_image_composition(
        ENVIRONMENT,
        env,
        services=(
            "recommendation-service",
            "content-service",
            "user-service",
        ),
    )
    return env


def _compose_arguments() -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        COMPOSE_PROJECT,
        "-f",
        str(ROOT / "quwoquan_ops/environments/compose/docker-compose.local-content-backing.yaml"),
        "-f",
        str(ROOT / "quwoquan_service/services/recommendation-service/deploy/compose.yaml"),
        "-f",
        str(ROOT / "quwoquan_service/services/content-service/deploy/compose.yaml"),
        "-f",
        str(ROOT / "quwoquan_service/services/user-service/deploy/compose.yaml"),
    ]


def _ensure_compose_images(env: Mapping[str, str]) -> None:
    base = _compose_arguments()
    for service in ("recommendation-service", "content-service", "user-service"):
        result = subprocess.run(
            [*base, "config", "--images", service],
            cwd=ROOT,
            env=dict(env),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        image = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else ""
        if not image:
            detail = result.stderr.strip() or result.stdout.strip() or "compose returned no image"
            raise RuntimeError(f"cannot resolve compose image for {service}: {detail[-320:]}")
        exists = subprocess.run(["docker", "image", "inspect", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if exists.returncode:
            _run([*base, "build", service], env=env)


def _compose_service_logs_indicate_migration_drift(service: str) -> str:
    result = subprocess.run(
        [*_compose_arguments(), "logs", "--no-color", "--tail", "80", service],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    text = result.stdout or ""
    markers = (
        "migration checksum",
        "checksum drift",
        "checksum mismatch",
        "Dirty database version",
    )
    for marker in markers:
        if marker.lower() in text.lower():
            return marker
    return ""


def _wait_http(url: str, *, timeout_seconds: int, compose_service: str = "") -> None:
    deadline = time.monotonic() + timeout_seconds
    early_deadline = time.monotonic() + min(30, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
        except OSError:
            pass
        if compose_service and time.monotonic() >= early_deadline:
            marker = _compose_service_logs_indicate_migration_drift(compose_service)
            if marker:
                raise RuntimeError(
                    f"GATE_BLOCK: {compose_service} migration drift detected "
                    f"({marker}); wipe local postgres instead of waiting "
                    f"readiness for {url}"
                )
            early_deadline = deadline + 1  # only probe once
        time.sleep(0.5)
    raise RuntimeError(f"service readiness timed out: {url}")


def _start_process(
    paths: RuntimePaths,
    name: str,
    arguments: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> dict[str, int | str]:
    log = paths.logs_root / name / "local" / "runtime.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "quwoquan_ops/cli/lib/runtime_log_process.py"), "--log-file", str(log), "--event", name, "--", *arguments],
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {
        "pid": process.pid,
        "pgid": os.getpgid(process.pid),
        "commandDigest": "sha256:"
        + hashlib.sha256(
            json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def _write_caddyfile(paths: RuntimePaths, ports: Mapping[str, int]) -> None:
    paths.caddyfile.parent.mkdir(parents=True, exist_ok=True)
    api_port = ports["api-edge"]
    media_port = ports["media-edge"]
    public_bases = get_target(load_environment_topology(), TARGET)["publicBases"]
    api_host = urlsplit(str(public_bases["api"])).hostname
    web_host = urlsplit(str(public_bases["publicWeb"])).hostname
    cdn_host = urlsplit(str(public_bases["mediaImage"])).hostname
    upload_host = urlsplit(str(public_bases["mediaUpload"])).hostname
    paths.caddyfile.write_text(
        "\n".join(
            (
                "{",
                "  admin off",
                "}",
                "",
                "(public_tls) {",
                "  tls /etc/caddy/tls/fullchain.pem /etc/caddy/tls/privkey.pem",
                "}",
                "",
                f"https://{api_host}:{api_port}, https://{web_host}:{api_port} {{",
                "  import public_tls",
                "  @web_api {",
                f"    host {web_host}",
                "    path /api/*",
                "  }",
                "  uri @web_api strip_prefix /api",
                "  handle /healthz {",
                f"    reverse_proxy host.docker.internal:{ports['content-service']}",
                "  }",
                "  handle /legal/* {",
                "    root * /srv/legal",
                "    file_server",
                "  }",
                f"  @content path /content /content/* /config/app",
                "  handle @content {",
                f"    reverse_proxy host.docker.internal:{ports['content-service']}",
                "  }",
                f"  @homepages path /homepages /homepages/* /homepage-claim-requests /homepage-status-reports",
                "  handle @homepages {",
                f"    reverse_proxy host.docker.internal:{ports['entity-service']}",
                "  }",
                f"  @users path /user /user/* /users /users/*",
                "  handle @users {",
                f"    reverse_proxy host.docker.internal:{ports['user-service']}",
                "  }",
                "  respond 404",
                "}",
                "",
                f"https://{cdn_host}:{media_port}, https://{upload_host}:{media_port} {{",
                "  import public_tls",
                "  header {",
                "    Access-Control-Allow-Origin \"*\"",
                "    Access-Control-Allow-Methods \"GET, HEAD, OPTIONS\"",
                "    Access-Control-Allow-Headers \"*\"",
                "    Cross-Origin-Resource-Policy \"cross-origin\"",
                "    ?Cache-Control \"no-store\"",
                "  }",
                "  @immutable_public_media {",
                "    path_regexp immutable_public_media ^/media/(?:avatar|image|video|background|attachment)/s/(?:[^/]+/)+v[1-9][0-9]*/(?:[^/]+/)*[^/]+$",
                "    vars_regexp canonical_media_query {http.request.uri.query} ^$",
                "  }",
                "  header @immutable_public_media {",
                "    Cache-Control \"public, max-age=31536000, immutable\"",
                "    X-QWQ-Media-Cache-Key \"{http.request.uri.path}\"",
                "  }",
                f"  reverse_proxy host.docker.internal:{ports['media-processor']}",
                "}",
                "",
            )
        ),
        encoding="utf-8",
    )


def _start_caddy(paths: RuntimePaths, ports: Mapping[str, int]) -> None:
    if _container_exists(CADDY_NAME):
        _run(["docker", "rm", "-f", CADDY_NAME])
    public_cert, public_key = certificate_paths(TARGET)
    _run(
        [
            "docker", "run", "-d", "--name", CADDY_NAME,
            "-p", f"{ports['api-edge']}:{ports['api-edge']}",
            "-p", f"{ports['media-edge']}:{ports['media-edge']}",
            "-v", f"{paths.caddyfile}:/etc/caddy/Caddyfile:ro",
            "-v", f"{public_cert}:/etc/caddy/tls/fullchain.pem:ro",
            "-v", f"{public_key}:/etc/caddy/tls/privkey.pem:ro",
            "-v", f"{paths.legal_root}:/srv/legal:ro",
            "-v", "quwoquan_alpha_content_release_caddy_data:/data",
            "-v", "quwoquan_alpha_content_release_caddy_config:/config",
            "docker.io/library/caddy:2.8.4-alpine",
        ]
    )


def _container_exists(name: str) -> bool:
    return subprocess.run(["docker", "container", "inspect", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_process_group_gone(pgid: int, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_group_exists(pgid):
            return True
        time.sleep(0.2)
    return not _process_group_exists(pgid)


def _stop_process(record: Mapping[str, object]) -> bool:
    pid = record.get("pid")
    pgid = record.get("pgid")
    if (
        not isinstance(pid, int)
        or pid <= 0
        or not isinstance(pgid, int)
        or pgid <= 0
    ):
        return False
    try:
        current_pgid = os.getpgid(pid)
    except ProcessLookupError:
        return True
    if current_pgid != pgid:
        raise RuntimeError(
            f"managed process identity drift: pid={pid} expectedPgid={pgid} "
            f"actualPgid={current_pgid}"
        )
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    if _wait_process_group_gone(pgid, timeout_seconds=15):
        return True
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return _wait_process_group_gone(pgid, timeout_seconds=5)


def _matches_orphaned_wrapper(
    command: str,
    *,
    name: str,
    ports: Mapping[str, int],
    paths: RuntimePaths,
) -> bool:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    wrapper = str((ROOT / "quwoquan_ops/cli/lib/runtime_log_process.py").resolve())
    if len(arguments) < 8 or str(Path(arguments[1]).resolve()) != wrapper:
        return False
    try:
        log_index = arguments.index("--log-file")
        event_index = arguments.index("--event")
        separator_index = arguments.index("--")
    except ValueError:
        return False
    if (
        log_index + 1 >= len(arguments)
        or event_index + 1 >= len(arguments)
        or arguments[event_index + 1] != name
        or separator_index <= event_index
    ):
        return False
    log_path = Path(arguments[log_index + 1]).resolve()
    observability_root = (ROOT / ".qwq_output/env/alpha/observability").resolve()
    try:
        relative_log = log_path.relative_to(observability_root)
    except ValueError:
        return False
    if relative_log.parts[-5:] != (
        "logs",
        "service",
        name,
        "local",
        "runtime.log",
    ):
        return False
    child = arguments[separator_index + 1 :]
    if name == "media-origin":
        required = {
            "quwoquan_ops/cli/lib/local_media_origin.py",
            "--listen-port",
            str(ports["media-origin"]),
            "--root-dir",
            str(paths.media_root.resolve()),
        }
        return required.issubset(set(child))
    if name == "media-edge":
        required = {
            "quwoquan_ops/cli/lib/http_reverse_proxy.py",
            "--listen-port",
            str(ports["media-processor"]),
            "--target-base-url",
            f"http://127.0.0.1:{ports['media-origin']}",
        }
        return required.issubset(set(child))
    if name == "entity-service":
        return child == ["go", "run", "./cmd/api"]
    return False


def discover_orphaned_managed_processes() -> dict[str, dict[str, int]]:
    """Find only target-scoped Alpha wrappers after their canonical ledger was lost."""
    paths = _paths()
    if paths.state_path.exists():
        raise RuntimeError(
            "Alpha managed process ledger still exists; use stackctl down instead"
        )
    result = subprocess.run(
        ["ps", "-axo", "pid=,pgid=,command="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "cannot inspect Alpha managed processes: "
            + (result.stderr.strip() or f"ps exit={result.returncode}")
        )
    ports = profile_ports(load_port_manifest(), TARGET)
    matches: dict[str, dict[str, int]] = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) != 3:
            continue
        try:
            pid, pgid = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        for name in ("media-origin", "media-edge", "entity-service"):
            if _matches_orphaned_wrapper(
                fields[2], name=name, ports=ports, paths=paths
            ):
                if name in matches:
                    raise RuntimeError(
                        f"multiple orphaned Alpha wrappers match managed role {name}"
                    )
                matches[name] = {"pid": pid, "pgid": pgid}
    return matches


def reclaim_orphaned_managed_processes(
    *, confirm: bool
) -> dict[str, dict[str, int]]:
    if not confirm:
        raise RuntimeError(
            "orphaned Alpha process reclaim requires explicit confirmation"
        )
    matches = discover_orphaned_managed_processes()
    residual: list[str] = []
    for name, record in matches.items():
        if not _stop_process(record):
            residual.append(name)
    if residual:
        raise RuntimeError(
            "orphaned Alpha process groups remain after repair: "
            + ", ".join(sorted(residual))
        )
    remaining = discover_orphaned_managed_processes()
    if remaining:
        raise RuntimeError(
            "orphaned Alpha wrappers remain after repair: "
            + ", ".join(sorted(remaining))
        )
    return matches


def up() -> None:
    if subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode:
        raise RuntimeError("Docker daemon is unavailable for Alpha content-release")
    assert_local_runtime_available(load_environment_topology(), TARGET)
    # Public TLS is a startup prerequisite.  Validate it before stopping the
    # current runtime so a missing certificate cannot turn a degraded but
    # inspectable Alpha stack into a full outage.
    certificate_paths(TARGET)
    down()
    paths = _paths(new_run=True)
    _materialize_observability_run(paths)
    ports = profile_ports(load_port_manifest(), TARGET)
    versions = _prepare_config_root(paths)
    env = _base_environment(paths, versions)
    paths.media_root.mkdir(parents=True, exist_ok=True)
    _ensure_compose_images(env)
    _run([*_compose_arguments(), "up", "-d", *COMPOSE_SERVICES], env=env)
    _wait_http(
        f"http://127.0.0.1:{ports['content-service']}/healthz",
        timeout_seconds=300,
        compose_service="content-service",
    )
    _wait_http(
        f"http://127.0.0.1:{ports['user-service']}/healthz",
        timeout_seconds=300,
        compose_service="user-service",
    )
    processes = {
        "media-origin": _start_process(
            paths,
            "media-origin",
            [sys.executable, "quwoquan_ops/cli/lib/local_media_origin.py", "--listen-host", "0.0.0.0", "--listen-port", str(ports["media-origin"]), "--root-dir", str(paths.media_root), "--server-label", "alpha-release-media-origin"],
            cwd=ROOT,
            env=env,
        ),
        "media-edge": _start_process(
            paths,
            "media-edge",
            [sys.executable, "quwoquan_ops/cli/lib/http_reverse_proxy.py", "--listen-host", "0.0.0.0", "--listen-port", str(ports["media-processor"]), "--target-base-url", f"http://127.0.0.1:{ports['media-origin']}"],
            cwd=ROOT,
            env=env,
        ),
        "entity-service": _start_process(
            paths,
            "entity-service",
            ["go", "run", "./cmd/api"],
            cwd=ROOT / "quwoquan_service/services/entity-service",
            env={
                **env,
                "APP_ENV": ENVIRONMENT,
                "CONFIG_ROOT": str(paths.config_root),
                "ENTITY_SERVICE_ADDR": f"0.0.0.0:{ports['entity-service']}",
                "ENTITY_MONGO_URI": f"mongodb://127.0.0.1:{ports['mongodb']}/?directConnection=true",
                "ENTITY_MONGO_DATABASE": "quwoquan_entity",
                "ENTITY_REDIS_ADDR": f"127.0.0.1:{ports['redis']}",
                "ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL": (
                    f"http://127.0.0.1:{ports['user-service']}"
                ),
            },
        ),
    }
    _wait_http(f"http://127.0.0.1:{ports['media-origin']}/healthz", timeout_seconds=30)
    _wait_http(f"http://127.0.0.1:{ports['media-processor']}/healthz", timeout_seconds=30)
    _wait_http(f"http://127.0.0.1:{ports['entity-service']}/healthz", timeout_seconds=120)
    _write_caddyfile(paths, ports)
    _start_caddy(paths, ports)
    paths.process_dir.mkdir(parents=True, exist_ok=True)
    paths.state_path.write_text(
        json.dumps(
            {
                "target": TARGET,
                "workload": "content-release",
                "runRoot": str(paths.run_root.resolve()),
                "observabilityRoot": str(paths.observability_root.resolve()),
                "processes": processes,
                "composeProject": COMPOSE_PROJECT,
                "caddy": CADDY_NAME,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def down() -> None:
    paths = _paths()
    state: dict[str, object] = {}
    if paths.state_path.is_file():
        try:
            loaded = json.loads(paths.state_path.read_text(encoding="utf-8"))
            state = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"managed process ledger is invalid JSON: {paths.state_path}"
            ) from exc
        if not state:
            raise RuntimeError(
                f"managed process ledger is not an object: {paths.state_path}"
            )
    process_records = state.get("processes") or {}
    if not isinstance(process_records, Mapping):
        raise RuntimeError(
            f"managed process ledger has invalid processes: {paths.state_path}"
        )
    residual_processes: list[str] = []
    for name, record in process_records.items():
        if not isinstance(record, Mapping) or not _stop_process(record):
            residual_processes.append(str(name))
    if _container_exists(CADDY_NAME):
        _run(["docker", "rm", "-f", CADDY_NAME])
    if subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0:
        result = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        container_ids = [line for line in result.stdout.splitlines() if line.strip()]
        if container_ids:
            _run(["docker", "rm", "-f", *container_ids])
    if residual_processes:
        raise RuntimeError(
            "managed process groups remain after Alpha teardown: "
            + ", ".join(sorted(residual_processes))
        )
    paths.state_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("up", "down"))
    args = parser.parse_args()
    try:
        if args.action == "up":
            up()
        else:
            down()
    except RuntimeError as exc:
        print(f"GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
