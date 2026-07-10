from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod_plane_access_isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh/quwoquan-prod"
DEFAULT_HOST = "118.31.239.122"
DEFAULT_COMPOSE_TEMPLATE = ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
DEFAULT_IMAGE_PATTERN = re.compile(r"\$\{[^}]+:-([^}]+)\}")


@dataclass(frozen=True)
class PlaneSpec:
    plane: str
    account: str
    governed_services: tuple[str, ...]
    support_services: tuple[str, ...]


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _plane_spec(plane_name: str) -> PlaneSpec:
    access = _load_yaml(ACCESS_MANIFEST)
    for plane in access.get("planes") or []:
        if str(plane.get("plane")) != plane_name:
            continue
        return PlaneSpec(
            plane=plane_name,
            account=str(plane.get("account") or ""),
            governed_services=tuple(str(item) for item in (plane.get("rootlessGovernedComposeServices") or [])),
            support_services=tuple(str(item) for item in (plane.get("rootlessSupportComposeServices") or [])),
        )
    raise SystemExit(f"FAIL: unknown plane: {plane_name}")


def _parse_image_ref(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    match = DEFAULT_IMAGE_PATTERN.search(text)
    if match:
        return match.group(1)
    return text


def _compose_image_refs(services: list[str]) -> dict[str, str]:
    compose = _load_yaml(DEFAULT_COMPOSE_TEMPLATE)
    refs: dict[str, str] = {}
    for service in services:
        spec = (compose.get("services") or {}).get(service) or {}
        ref = _parse_image_ref(spec.get("image"))
        if not ref or not ref.startswith("localhost/"):
            continue
        refs[service] = ref
    return refs


def _local_image_exists(image_ref: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image_ref],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _local_image_architecture(image_ref: str) -> str | None:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Architecture}}", image_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _target_arch(platform: str) -> str:
    return platform.split("/")[-1].strip()


def _rebuild_images(services: list[str], platform: str) -> None:
    env = os.environ.copy()
    env["DOCKER_DEFAULT_PLATFORM"] = platform
    env["LOCAL_GAMMA_ALPINE_BASE_IMAGE"] = "docker.io/library/debian:bookworm-slim"
    result = subprocess.run(
        ["docker", "compose", "-f", str(DEFAULT_COMPOSE_TEMPLATE), "build", *services],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "FAIL: docker compose build failed for "
            f"{', '.join(services)} on {platform}:\n{result.stdout}"
        )


def _stream_image(image_ref: str, account: str, host: str, key_file: Path) -> None:
    save_proc = subprocess.Popen(
        ["docker", "save", image_ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert save_proc.stdout is not None
    load_proc = subprocess.run(
        [
            "ssh",
            "-i",
            str(key_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            f"{account}@{host}",
            "podman load",
        ],
        stdin=save_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    save_proc.stdout.close()
    save_stderr = save_proc.stderr.read().decode("utf-8", errors="replace") if save_proc.stderr else ""
    save_rc = save_proc.wait()
    if save_rc != 0:
        raise SystemExit(f"FAIL: docker save failed for {image_ref}: {save_stderr.strip()}")
    if load_proc.returncode != 0:
        raise SystemExit(
            "FAIL: remote podman load failed for "
            f"{image_ref}: {(load_proc.stderr or '').strip()}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load local Docker service images into a prod plane rootless Podman store.",
    )
    parser.add_argument("--plane", default="service")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR)
    parser.add_argument("--services", default="")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--rebuild-if-needed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plane = _plane_spec(args.plane)
    requested = [item.strip() for item in args.services.split(",") if item.strip()]
    governed = list(plane.governed_services)
    if requested:
        governed = [item for item in governed if item in requested]
    if not governed:
        raise SystemExit("FAIL: no governed services selected")
    key_file = args.key_dir / plane.account
    if not key_file.is_file():
        raise SystemExit(f"FAIL: missing key file: {key_file}")
    image_refs = _compose_image_refs(governed)
    target_arch = _target_arch(args.platform)
    rebuild_services: list[str] = []
    missing: list[str] = []
    arch_mismatch: dict[str, str] = {}
    for service, ref in image_refs.items():
        arch = _local_image_architecture(ref)
        if arch is None:
            missing.append(ref)
            rebuild_services.append(service)
            continue
        if arch != target_arch:
            arch_mismatch[service] = arch
            rebuild_services.append(service)
    if rebuild_services and args.rebuild_if_needed and not args.dry_run:
        _rebuild_images(rebuild_services, args.platform)
        missing = []
        arch_mismatch = {}
        for service in rebuild_services:
            ref = image_refs[service]
            arch = _local_image_architecture(ref)
            if arch is None:
                missing.append(ref)
            elif arch != target_arch:
                arch_mismatch[service] = arch
    report = {
        "plane": plane.plane,
        "account": plane.account,
        "host": args.host,
        "keyFile": str(key_file),
        "services": governed,
        "images": image_refs,
        "platform": args.platform,
        "rebuildServices": rebuild_services,
        "missingImages": missing,
        "archMismatch": arch_mismatch,
        "dryRun": bool(args.dry_run),
    }
    print(json.dumps(report, ensure_ascii=False))
    if args.dry_run:
        return 0
    if missing:
        raise SystemExit("FAIL: local docker images missing: " + ", ".join(missing))
    if arch_mismatch:
        detail = ", ".join(f"{service}={arch}" for service, arch in sorted(arch_mismatch.items()))
        raise SystemExit(
            f"FAIL: local docker images are not {target_arch}: {detail}; "
            "rerun with --rebuild-if-needed"
        )
    for service in governed:
        image_ref = image_refs.get(service)
        if not image_ref:
            continue
        _stream_image(image_ref, plane.account, args.host, key_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
