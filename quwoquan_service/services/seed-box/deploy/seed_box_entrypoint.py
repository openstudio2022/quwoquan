#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
BIN_DIR = ROOT / "bin"
CONTRACTS_DIR = ROOT / "contracts" / "metadata"
RUNTIME_CONFIG_ROOT = ROOT / "runtime-config"
CHAT_MEDIA_ROOT = Path(
    os.getenv("CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT", "/tmp/chat-media")
).resolve()
USER_CIRCLE_PATH = re.compile(r"^/v1/users/[^/]+/circles(?:/|$)")
# search domain 在 process_domain_mapping 中始终是独立部署进程（search-service），
# seed-box 不在本进程内运行 search domain，只按 service.yaml 的 proxy_search 能力把
# /v1/search* 透传到外部 search-service 上游。上游地址可经环境变量覆盖以适配不同拓扑。
SEARCH_UPSTREAM_HOST = (
    os.getenv("SEED_BOX_SEARCH_UPSTREAM_HOST", "search-service").strip()
    or "search-service"
)
SEARCH_UPSTREAM_PORT = int(
    os.getenv("SEED_BOX_SEARCH_UPSTREAM_PORT", "18095").strip() or "18095"
)
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _bool_env(name: str, default: str = "") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _http_status(port: int, path: str = "/healthz", timeout: float = 1.5) -> tuple[bool, int | None, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        payload = response.read()
        return 200 <= response.status < 300, response.status, payload.decode(
            "utf-8", errors="replace"
        )[:200]
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)
    finally:
        conn.close()


def _listen_port(raw: str) -> int:
    value = raw.strip()
    if not value:
        return 8080
    if value.startswith(":"):
        return int(value[1:])
    return int(value.rsplit(":", 1)[-1])


def _common_child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("APP_ENV", "prod")
    env.setdefault("CONFIG_ROOT", str(RUNTIME_CONFIG_ROOT))
    env.setdefault(
        "QWQ_SEGMENTS_PATH",
        str(CONTRACTS_DIR / "recommendation" / "rec_model" / "segments.yaml"),
    )
    env.setdefault("CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT", str(CHAT_MEDIA_ROOT))
    if not env.get("MONGODB_URI") and env.get("MONGO_URI"):
        env["MONGODB_URI"] = env["MONGO_URI"]
    if not env.get("CIRCLE_MONGO_URI") and env.get("MONGO_URI"):
        env["CIRCLE_MONGO_URI"] = env["MONGO_URI"]
    if not env.get("CIRCLE_REDIS_ADDR") and env.get("REDIS_ADDR"):
        env["CIRCLE_REDIS_ADDR"] = env["REDIS_ADDR"]
    if env.get("REDIS_ADDR"):
        env.setdefault("REDIS_REALTIME_ADDR", env["REDIS_ADDR"])
        env.setdefault("CHAT_REDIS_GENERAL_ADDR", env["REDIS_ADDR"])
        env.setdefault("CHAT_REDIS_REALTIME_ADDR", env["REDIS_ADDR"])
        env.setdefault("CHAT_REDIS_RELIABLE_TASK_ADDR", env["REDIS_ADDR"])
    return env


def _enabled_flag(name: str) -> str:
    return os.getenv(name, "auto").strip().lower()


def _content_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    return True, None


def _integration_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    return True, None


def _chat_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_CHAT")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_CHAT"
    if env.get("MONGO_URI"):
        return True, None
    return False, "missing MONGO_URI"


def _user_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_USER")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_USER"
    if env.get("POSTGRES_DSN"):
        return True, None
    return False, "missing POSTGRES_DSN"


def _circle_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_CIRCLE")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_CIRCLE"
    if env.get("CIRCLE_MONGO_URI") or env.get("MONGO_URI"):
        return True, None
    return False, "missing CIRCLE_MONGO_URI or MONGO_URI"


def _entity_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_ENTITY")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_ENTITY"
    return True, None


def _tag_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_TAG")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_TAG"
    if env.get("TAG_MONGO_URI") or env.get("MONGO_URI"):
        return True, None
    return False, "missing TAG_MONGO_URI or MONGO_URI"


def _assistant_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_ASSISTANT")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_ASSISTANT"
    return True, None


def _notification_enabled(env: dict[str, str]) -> tuple[bool, str | None]:
    flag = _enabled_flag("SEED_BOX_ENABLE_NOTIFICATION")
    if flag in {"0", "false", "no", "off"}:
        return False, "disabled by SEED_BOX_ENABLE_NOTIFICATION"
    return True, None


def _content_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "content-service",
        "CONTENT_SERVICE_ADDR": ":18080",
    }
    if not env.get("CONTENT_REDIS_REC_ADDR") and not env.get("CONTENT_REDIS_REC_ADDRS"):
        child.setdefault("CONTENT_REDIS_REC_MODE", "memory")
    if not env.get("CONTENT_REDIS_GENERAL_ADDR") and not env.get(
        "CONTENT_REDIS_GENERAL_ADDRS"
    ):
        child.setdefault("CONTENT_REDIS_GENERAL_MODE", "memory")
    child.setdefault("REC_MODEL_SERVICE_ENABLED", env.get("REC_MODEL_SERVICE_ENABLED", "false"))
    child.setdefault("REC_MODEL_SERVICE_URL", env.get("REC_MODEL_SERVICE_URL", "http://127.0.0.1:8000"))
    return child


def _chat_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "chat-service",
        "MODULE_PACKAGE": "seed-box",
        "CHAT_SERVICE_ADDR": ":18081",
        "CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT": env.get(
            "CHAT_GROUP_AVATAR_LOCAL_MEDIA_ROOT", str(CHAT_MEDIA_ROOT)
        ),
    }
    if not env.get("CHAT_REDIS_GENERAL_ADDR") and not env.get("REDIS_ADDR"):
        child.setdefault("CHAT_REDIS_GENERAL_MODE", "memory")
    if not env.get("CHAT_REDIS_REALTIME_ADDR") and not env.get("REDIS_ADDR"):
        child.setdefault("CHAT_REDIS_REALTIME_MODE", "memory")
    if not env.get("CHAT_REDIS_RELIABLE_TASK_ADDR") and not env.get("REDIS_ADDR"):
        child.setdefault("CHAT_REDIS_RELIABLE_TASK_MODE", "memory")
    if not env.get("CHAT_GROUP_AVATAR_CDN_BASE_URL") and env.get("MEDIA_AVATAR_CDN_BASE_URL"):
        child["CHAT_GROUP_AVATAR_CDN_BASE_URL"] = env["MEDIA_AVATAR_CDN_BASE_URL"]
    return child


def _user_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "user-service",
        "USER_SERVICE_ADDR": ":18082",
    }
    if not env.get("MONGODB_URI") and env.get("MONGO_URI"):
        child["MONGODB_URI"] = env["MONGO_URI"]
    return child


def _integration_env(env: dict[str, str]) -> dict[str, str]:
    return {
        "SERVICE_NAME": "integration-service",
        "INTEGRATION_SERVICE_ADDR": ":18086",
    }


def _circle_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "circle-service",
        "CIRCLE_SERVICE_ADDR": ":18084",
    }
    if not env.get("CIRCLE_MONGO_URI") and env.get("MONGO_URI"):
        child["CIRCLE_MONGO_URI"] = env["MONGO_URI"]
    if not env.get("CIRCLE_REDIS_ADDR") and env.get("REDIS_ADDR"):
        child["CIRCLE_REDIS_ADDR"] = env["REDIS_ADDR"]
    return child


def _entity_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "entity-service",
        "ENTITY_SERVICE_ADDR": ":18085",
    }
    if not env.get("ENTITY_MONGO_URI") and env.get("MONGO_URI"):
        child["ENTITY_MONGO_URI"] = env["MONGO_URI"]
    return child


def _tag_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "tag-service",
        "TAG_SERVICE_ADDR": ":18092",
    }
    if not env.get("TAG_MONGO_URI") and env.get("MONGO_URI"):
        child["TAG_MONGO_URI"] = env["MONGO_URI"]
    return child


def _assistant_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "assistant-service",
        "ASSISTANT_SERVICE_ADDR": ":18087",
        "ASSISTANT_CHAT_BASE_URL": env.get("ASSISTANT_CHAT_BASE_URL", "http://127.0.0.1:18081"),
        "ASSISTANT_NOTIFICATION_BASE_URL": env.get(
            "ASSISTANT_NOTIFICATION_BASE_URL", "http://127.0.0.1:18089"
        ),
    }
    if not env.get("REDIS_GENERAL_ADDR") and env.get("REDIS_ADDR"):
        child["REDIS_GENERAL_ADDR"] = env["REDIS_ADDR"]
    if not env.get("REDIS_REC_ADDR") and env.get("REDIS_ADDR"):
        child["REDIS_REC_ADDR"] = env["REDIS_ADDR"]
    return child


def _notification_env(env: dict[str, str]) -> dict[str, str]:
    child = {
        "SERVICE_NAME": "notification-service",
        "NOTIFICATION_SERVICE_ADDR": ":18089",
        "NOTIFICATION_MONGO_DATABASE": env.get(
            "NOTIFICATION_MONGO_DATABASE", "quwoquan_notification"
        ),
        "NOTIFICATION_INTEGRATION_BASE_URL": env.get(
            "NOTIFICATION_INTEGRATION_BASE_URL", "http://127.0.0.1:18086"
        ),
        "NOTIFICATION_INTEGRATION_TIMEOUT_MS": env.get(
            "NOTIFICATION_INTEGRATION_TIMEOUT_MS", "1500"
        ),
    }
    if not env.get("NOTIFICATION_MONGO_URI") and env.get("MONGO_URI"):
        child["NOTIFICATION_MONGO_URI"] = env["MONGO_URI"]
    return child


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    binary_name: str
    port: int
    required: bool
    enable_fn: Callable[[dict[str, str]], tuple[bool, str | None]]
    env_fn: Callable[[dict[str, str]], dict[str, str]]


class ManagedService:
    def __init__(self, spec: ServiceSpec, base_env: dict[str, str]) -> None:
        self.spec = spec
        self.base_env = base_env
        self.enabled, self.disable_reason = spec.enable_fn(base_env)
        self.process: subprocess.Popen[str] | None = None
        self._log_thread: threading.Thread | None = None

    @property
    def binary(self) -> Path:
        return BIN_DIR / self.spec.binary_name

    def start(self) -> None:
        if not self.enabled:
            return
        env = dict(self.base_env)
        env.update(self.spec.env_fn(self.base_env))
        self.process = subprocess.Popen(
            [str(self.binary)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._log_thread = threading.Thread(target=self._stream_logs, daemon=True)
        self._log_thread.start()

    def _stream_logs(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        prefix = f"[{self.spec.name}] "
        for line in self.process.stdout:
            sys.stdout.write(prefix + line)
            sys.stdout.flush()

    def status(self) -> dict[str, object]:
        if not self.enabled:
            return {
                "enabled": False,
                "required": self.spec.required,
                "status": "disabled",
                "reason": self.disable_reason or "",
                "port": self.spec.port,
            }
        if self.process is None:
            return {
                "enabled": True,
                "required": self.spec.required,
                "status": "not_started",
                "port": self.spec.port,
            }
        exit_code = self.process.poll()
        if exit_code is not None:
            return {
                "enabled": True,
                "required": self.spec.required,
                "status": "exited",
                "exitCode": exit_code,
                "port": self.spec.port,
            }
        healthy, http_status, detail = _http_status(self.spec.port)
        return {
            "enabled": True,
            "required": self.spec.required,
            "status": "ready" if healthy else "starting",
            "httpStatus": http_status,
            "detail": detail,
            "port": self.spec.port,
        }

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()

    def kill(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.kill()

    def wait(self, timeout: float) -> None:
        if self.process is None:
            return
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass


SERVICE_SPECS = [
    ServiceSpec(
        name="content-service",
        binary_name="content-service",
        port=18080,
        required=True,
        enable_fn=_content_enabled,
        env_fn=_content_env,
    ),
    ServiceSpec(
        name="chat-service",
        binary_name="chat-service",
        port=18081,
        required=True,
        enable_fn=_chat_enabled,
        env_fn=_chat_env,
    ),
    ServiceSpec(
        name="user-service",
        binary_name="user-service",
        port=18082,
        required=True,
        enable_fn=_user_enabled,
        env_fn=_user_env,
    ),
    ServiceSpec(
        name="integration-service",
        binary_name="integration-service",
        port=18086,
        required=False,
        enable_fn=_integration_enabled,
        env_fn=_integration_env,
    ),
    ServiceSpec(
        name="circle-service",
        binary_name="circle-service",
        port=18084,
        required=False,
        enable_fn=_circle_enabled,
        env_fn=_circle_env,
    ),
    ServiceSpec(
        name="entity-service",
        binary_name="entity-service",
        port=18085,
        required=False,
        enable_fn=_entity_enabled,
        env_fn=_entity_env,
    ),
    ServiceSpec(
        name="tag-service",
        binary_name="tag-service",
        port=18092,
        required=False,
        enable_fn=_tag_enabled,
        env_fn=_tag_env,
    ),
    ServiceSpec(
        name="assistant-service",
        binary_name="assistant-service",
        port=18087,
        required=False,
        enable_fn=_assistant_enabled,
        env_fn=_assistant_env,
    ),
    ServiceSpec(
        name="notification-service",
        binary_name="notification-service",
        port=18089,
        required=True,
        enable_fn=_notification_enabled,
        env_fn=_notification_env,
    ),
]


class ServiceRegistry:
    def __init__(self) -> None:
        base_env = _common_child_env()
        self.services = {
            spec.name: ManagedService(spec, base_env) for spec in SERVICE_SPECS
        }

    def start_all(self) -> None:
        CHAT_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        for service in self.services.values():
            service.start()

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            name: service.status()
            for name, service in self.services.items()
        }

    def health_payload(self) -> tuple[int, dict[str, object]]:
        services = self.snapshot()
        failures = [
            name
            for name, info in services.items()
            if info.get("required") and info.get("status") != "ready"
        ]
        payload = {
            "service": "seed-box",
            "status": "ok" if not failures else "degraded",
            "services": services,
            "failures": failures,
        }
        return (200 if not failures else 503), payload

    def service_for_path(self, path: str) -> str | None:
        if path in {"/healthz", "/livez", "/startupz"}:
            return None
        if path == "/v1/config/app" or path.startswith("/v1/content"):
            return "content-service"
        if path.startswith("/v1/chat"):
            return "chat-service"
        if path.startswith("/v1/auth") or path.startswith("/v1/user"):
            return "user-service"
        if path.startswith("/v1/integration"):
            return "integration-service"
        if path.startswith("/v1/homepages"):
            return "entity-service"
        if path.startswith("/v1/tag"):
            return "tag-service"
        if path.startswith("/v1/assistant"):
            return "assistant-service"
        if path.startswith("/v1/notifications") or path.startswith("/v1/app-messages"):
            return "notification-service"
        if path.startswith("/v1/circles"):
            return "circle-service"
        if path.startswith("/v1/users/"):
            if USER_CIRCLE_PATH.match(path):
                return "circle-service"
            return "user-service"
        return None

    def shutdown(self) -> None:
        for service in self.services.values():
            service.stop()
        deadline = time.time() + 10
        for service in self.services.values():
            remaining = max(0.0, deadline - time.time())
            service.wait(remaining)
        for service in self.services.values():
            service.kill()


REGISTRY = ServiceRegistry()


class SeedBoxHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802
        self._handle()

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write(f"[seed-box-gateway] {fmt % args}\n")
        sys.stdout.flush()

    def _handle(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in {"/healthz", "/livez", "/startupz"}:
            self._write_health()
            return
        if parsed.path.startswith("/v1/search"):
            self._proxy(SEARCH_UPSTREAM_HOST, SEARCH_UPSTREAM_PORT)
            return
        target_name = REGISTRY.service_for_path(parsed.path)
        if target_name is None:
            self._write_json(404, {"error": "route_not_found", "path": parsed.path})
            return
        service = REGISTRY.services[target_name]
        status = service.status()
        if status.get("status") != "ready":
            self._write_json(
                503,
                {
                    "error": "backend_unavailable",
                    "backend": target_name,
                    "status": status,
                },
            )
            return
        self._proxy("127.0.0.1", service.spec.port)

    def _write_health(self) -> None:
        status_code, payload = REGISTRY.health_payload()
        self._write_json(status_code, payload)

    def _proxy(self, host: str, port: int) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        headers["Host"] = f"{host}:{port}"
        path = self.path
        conn = http.client.HTTPConnection(host, port, timeout=30)
        try:
            conn.request(self.command, path, body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
        except Exception as exc:  # noqa: BLE001
            self._write_json(
                502,
                {
                    "error": "proxy_failed",
                    "detail": str(exc),
                    "upstreamHost": host,
                    "upstreamPort": port,
                },
            )
            return
        finally:
            conn.close()

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS or lower == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


class SeedBoxServer(ThreadingHTTPServer):
    daemon_threads = True


def main() -> int:
    REGISTRY.start_all()
    listen_port = _listen_port(os.getenv("SEED_BOX_HTTP_ADDR", ":8080"))
    server = SeedBoxServer(("0.0.0.0", listen_port), SeedBoxHandler)

    def _shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
        sys.stdout.write(f"[seed-box-gateway] received signal {signum}, shutting down\n")
        sys.stdout.flush()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        REGISTRY.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
