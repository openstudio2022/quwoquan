"""各 runtime target 共享的 Docker 基础镜像锁与预热。

类似 Flutter `pub cache`：package 只消费本机已缓存镜像；缺失时先预热再继续。
升级检查是独立动作，不在 package 路径强制更新。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from quwoquan_ops.cli.lib.common import ROOT, run

LOCK_SCHEMA = "quwoquan-docker-dependencies-lock-v1"
REGISTRY_ENV_RELATIVE = "quwoquan_ops/policies/registry.env"
LOCK_FILE_RELATIVE = "quwoquan_ops/policies/docker-dependencies.lock.json"
CACHE_DIR = Path.home() / ".cache/quwoquan/docker-dependencies"
_ENV_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_DEFAULT_MIRRORS = (
    "docker.m.daocloud.io",
    "docker.nju.edu.cn",
    "docker.mirrors.sjtug.sjtu.edu.cn",
)
_REQUIRED_LOCAL_KEYS = (
    "golang:1.24-bookworm",
    "alpine:3.21",
    "python:3.11-slim-bookworm",
    "postgres:16-alpine",
    "mongo:7-jammy",
    "redis:7.2-alpine",
)

DockerRunner = Callable[..., CompletedProcess[str]]


class DockerDependencyError(RuntimeError):
    """基础镜像缓存缺失或预热失败。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def registry_env_path(source_root: Path | None = None) -> Path:
    return (source_root or ROOT) / REGISTRY_ENV_RELATIVE


def lock_file_path(source_root: Path | None = None) -> Path:
    return (source_root or ROOT) / LOCK_FILE_RELATIVE


def load_registry_env(path: Path | None = None) -> dict[str, str]:
    env_path = path or registry_env_path()
    if not env_path.is_file():
        raise DockerDependencyError(f"registry env missing: {env_path}")
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.fullmatch(line)
        if match is None:
            raise DockerDependencyError(f"registry env line is invalid: {raw_line}")
        values[match.group(1)] = match.group(2).strip()
    required = (
        "QWQ_REGISTRY_MIRROR_HOSTS",
        "QWQ_GO_BASE_IMAGE",
        "QWQ_ALPINE_BASE_IMAGE",
        "QWQ_PYTHON_BASE_IMAGE",
        "QWQ_POSTGRES_IMAGE",
        "QWQ_MONGO_IMAGE",
        "QWQ_REDIS_IMAGE",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise DockerDependencyError(
            "registry env missing keys: " + ", ".join(missing)
        )
    return values


def load_lock_file(path: Path | None = None) -> dict[str, Any]:
    lock_path = path or lock_file_path()
    if not lock_path.is_file():
        raise DockerDependencyError(f"docker dependency lock missing: {lock_path}")
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DockerDependencyError("docker dependency lock is not JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != LOCK_SCHEMA:
        raise DockerDependencyError("docker dependency lock schema is invalid")
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        raise DockerDependencyError("docker dependency lock has no dependencies")
    for name, descriptor in dependencies.items():
        if not isinstance(name, str) or not name.strip():
            raise DockerDependencyError("docker dependency name is invalid")
        if not isinstance(descriptor, dict):
            raise DockerDependencyError(f"docker dependency descriptor is invalid: {name}")
        repository = str(descriptor.get("repository") or "").strip()
        tag = str(descriptor.get("tag") or "").strip()
        if not repository or not tag:
            raise DockerDependencyError(f"docker dependency repository/tag missing: {name}")
    missing_required = [
        name for name in _REQUIRED_LOCAL_KEYS if name not in dependencies
    ]
    if missing_required:
        raise DockerDependencyError(
            "docker dependency lock missing required images: "
            + ", ".join(missing_required)
        )
    return payload


def locked_python_base_image(source_root: Path | None = None) -> str:
    """package/compose 注入的 Python 基础镜像，只接受 registry 与 lock 的同一 pin。"""
    registry = load_registry_env(registry_env_path(source_root))
    pin = str(registry["QWQ_PYTHON_BASE_IMAGE"]).strip()
    lock = load_lock_file(lock_file_path(source_root))
    if pin not in lock["dependencies"]:
        raise DockerDependencyError(
            f"docker dependency lock missing required image: {pin}"
        )
    return pin


def mirror_hosts(registry: Mapping[str, str] | None = None) -> tuple[str, ...]:
    raw = ""
    if registry is not None:
        raw = str(registry.get("QWQ_REGISTRY_MIRROR_HOSTS") or "")
    hosts = tuple(
        host.strip().removeprefix("https://").removeprefix("http://").strip("/")
        for host in raw.split(",")
        if host.strip()
    )
    return hosts or _DEFAULT_MIRRORS


def _canonical_image_name(name: str) -> str:
    return name.split("@", 1)[0]


def _mirror_ref(mirror_host: str, repository: str, tag: str) -> str:
    path = repository
    if path.startswith("docker.io/"):
        path = path[len("docker.io/") :]
    return f"{mirror_host}/{path}:{tag}"


def inspect_image(
    name: str,
    *,
    run_command: DockerRunner = run,
) -> dict[str, str]:
    result = run_command(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}} {{json .RepoDigests}}",
            _canonical_image_name(name),
        ]
    )
    if result.returncode != 0:
        return {}
    parts = result.stdout.strip().split(" ", 1)
    image_id = parts[0].strip() if parts else ""
    if _DIGEST.fullmatch(image_id) is None:
        return {}
    digest = ""
    if len(parts) == 2:
        try:
            repo_digests = json.loads(parts[1])
        except json.JSONDecodeError:
            repo_digests = []
        if isinstance(repo_digests, list):
            for item in repo_digests:
                text = str(item)
                if "@sha256:" in text:
                    digest = "sha256:" + text.rsplit("@sha256:", 1)[1]
                    if _DIGEST.fullmatch(digest):
                        break
                    digest = ""
    return {"id": image_id, "digest": digest}


def image_is_cached(name: str, *, run_command: DockerRunner = run) -> bool:
    return bool(inspect_image(name, run_command=run_command))


def verify_cache(
    *,
    lock_path: Path | None = None,
    required_only: bool = True,
    run_command: DockerRunner = run,
) -> tuple[bool, list[str]]:
    payload = load_lock_file(lock_path)
    missing: list[str] = []
    names = (
        _REQUIRED_LOCAL_KEYS
        if required_only
        else tuple(payload["dependencies"])
    )
    for name in names:
        if not image_is_cached(name, run_command=run_command):
            missing.append(name)
    return not missing, missing


def _pull_one(
    name: str,
    descriptor: Mapping[str, Any],
    mirrors: Sequence[str],
    *,
    run_command: DockerRunner,
    pull_timeout_seconds: float,
) -> dict[str, str]:
    repository = str(descriptor["repository"]).strip()
    tag = str(descriptor["tag"]).strip()
    canonical = _canonical_image_name(name)
    attempts: list[str] = []
    for mirror in mirrors:
        ref = _mirror_ref(mirror, repository, tag)
        attempts.append(ref)
        pulled = run_command(
            ["docker", "pull", ref],
            timeout_seconds=pull_timeout_seconds,
        )
        if int(pulled.returncode) != 0:
            continue
        tagged = run_command(["docker", "tag", ref, canonical])
        if int(tagged.returncode) != 0:
            continue
        inspected = inspect_image(canonical, run_command=run_command)
        if inspected:
            return {
                "digest": inspected.get("digest") or inspected["id"],
                "source": mirror,
                "pulledAt": utc_now(),
            }
    canonical_ref = f"{repository}:{tag}"
    attempts.append(canonical_ref)
    pulled = run_command(
        ["docker", "pull", canonical_ref],
        timeout_seconds=pull_timeout_seconds,
    )
    if int(pulled.returncode) == 0:
        inspected = inspect_image(canonical, run_command=run_command)
        if inspected:
            return {
                "digest": inspected.get("digest") or inspected["id"],
                "source": "docker.io",
                "pulledAt": utc_now(),
            }
    raise DockerDependencyError(
        f"failed to pull {canonical}; attempts={attempts}"
    )


def prepare_dependencies(
    *,
    lock_path: Path | None = None,
    registry_path: Path | None = None,
    run_command: DockerRunner = run,
    pull_timeout_seconds: float = 180.0,
    persist_lock: bool = True,
) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    registry = load_registry_env(registry_path)
    payload = load_lock_file(lock_path)
    mirrors = mirror_hosts(registry)
    prepared: dict[str, Any] = {}
    for name, descriptor in payload["dependencies"].items():
        cached = inspect_image(name, run_command=run_command)
        if cached:
            prepared[name] = {
                "status": "cached",
                "digest": cached.get("digest") or cached["id"],
                "source": str(descriptor.get("source") or "local-cache"),
                "pulledAt": str(descriptor.get("pulledAt") or ""),
            }
            if not descriptor.get("digest"):
                descriptor["digest"] = prepared[name]["digest"]
            continue
        pulled = _pull_one(
            name,
            descriptor,
            mirrors,
            run_command=run_command,
            pull_timeout_seconds=pull_timeout_seconds,
        )
        descriptor["digest"] = pulled["digest"]
        descriptor["pulledAt"] = pulled["pulledAt"]
        descriptor["source"] = pulled["source"]
        prepared[name] = {"status": "pulled", **pulled}
    payload["generatedAt"] = utc_now()
    resolved_lock = lock_path or lock_file_path()
    if persist_lock:
        resolved_lock.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    cache_copy = CACHE_DIR / "docker-dependencies.lock.json"
    cache_copy.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ok, missing = verify_cache(
        lock_path=resolved_lock,
        required_only=True,
        run_command=run_command,
    )
    if not ok:
        raise DockerDependencyError(
            "docker dependency cache still missing after prepare: "
            + ", ".join(missing)
        )
    return {
        "schema": LOCK_SCHEMA,
        "lockFile": str(resolved_lock),
        "cacheDir": str(CACHE_DIR),
        "mirrors": list(mirrors),
        "dependencies": prepared,
    }


def ensure_prepared(
    *,
    source_root: Path | None = None,
    run_command: DockerRunner = run,
) -> dict[str, Any]:
    lock_path = lock_file_path(source_root)
    registry_path = registry_env_path(source_root)
    ok, missing = verify_cache(lock_path=lock_path, run_command=run_command)
    if ok:
        return {
            "status": "cached",
            "missing": [],
            "lockFile": str(lock_path),
        }
    prepared = prepare_dependencies(
        lock_path=lock_path,
        registry_path=registry_path,
        run_command=run_command,
    )
    return {
        "status": "prepared",
        "missing": missing,
        "lockFile": str(lock_path),
        "prepared": prepared,
    }


def check_outdated(
    *,
    lock_path: Path | None = None,
    run_command: DockerRunner = run,
) -> dict[str, Any]:
    payload = load_lock_file(lock_path)
    rows: list[dict[str, str]] = []
    for name, descriptor in payload["dependencies"].items():
        cached = inspect_image(name, run_command=run_command)
        locked_digest = str(descriptor.get("digest") or "")
        local_digest = str(cached.get("digest") or cached.get("id") or "")
        status = "cached" if cached else "missing"
        if cached and locked_digest and local_digest and locked_digest != local_digest:
            status = "digest_drift"
        rows.append(
            {
                "name": name,
                "status": status,
                "lockedDigest": locked_digest,
                "localDigest": local_digest,
            }
        )
    return {
        "schema": LOCK_SCHEMA,
        "action": "check-outdated",
        "dependencies": rows,
        "note": "upgrade is a separate offline action; package does not auto-update tags",
    }


def load_target_build_images(source_root: Path | None = None) -> dict[str, dict[str, str]]:
    """读取各 runtime target 声明的 buildImages，供统一性契约测试。"""
    # 环境闭集的唯一声明源是 environment_topology；延迟导入使 package 预热路径
    # 不必为读几个 manifest 承担该模块 import 期的目录扫描与文件读取。
    from quwoquan_ops.cli.lib.environment_topology import ENVIRONMENTS

    root = source_root or ROOT
    images: dict[str, dict[str, str]] = {}
    for env_name in ENVIRONMENTS:
        path = root / f"quwoquan_ops/environments/{env_name}/runtime.yaml"
        payload = json.loads(path.read_text(encoding="utf-8"))
        targets = payload.get("targets")
        if not isinstance(targets, dict) or not targets:
            raise DockerDependencyError(f"{path} has no targets")
        for target, target_payload in targets.items():
            if not isinstance(target_payload, dict):
                raise DockerDependencyError(f"{path} target {target} must be an object")
            build_images = target_payload.get("buildImages")
            if not isinstance(build_images, dict):
                raise DockerDependencyError(f"{target} buildImages policy must be an object")
            go_image = str(build_images.get("goBaseImage") or "").strip()
            alpine_image = str(build_images.get("alpineBaseImage") or "").strip()
            if not go_image or not alpine_image:
                raise DockerDependencyError(
                    f"{target}.buildImages.goBaseImage/alpineBaseImage must be non-empty"
                )
            images[str(target)] = {
                "goBaseImage": go_image,
                "alpineBaseImage": alpine_image,
            }
    return images
