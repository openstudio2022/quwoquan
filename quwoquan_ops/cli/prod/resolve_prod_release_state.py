#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import load_environment_topology

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"


@dataclass(frozen=True)
class ServicePlaneAccess:
    host: str
    account: str
    ssh_key_secret: str
    instance_suffix: str
    services: tuple[str, ...]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid yaml payload: {path}")
    return payload


def _resolve_prod_host(topology: dict) -> str:
    env_host = os.environ.get("PROD_SSH_HOST", "").strip()
    if env_host:
        return env_host
    host = str(
        ((topology.get("targets") or {}).get("prod-hosted") or {}).get("sshHost")
        or ""
    ).strip()
    if not host:
        raise RuntimeError("topology 缺少 prod-hosted.sshHost，请设置 PROD_SSH_HOST")
    return host


def _resolve_service_plane(access: dict, topology: dict, instance_suffix: str) -> ServicePlaneAccess:
    planes = access.get("planes") or []
    service_plane = None
    for plane in planes:
        if plane.get("plane") == "service":
            service_plane = plane
            break
    if not service_plane:
        raise RuntimeError("访问隔离映射缺少 service 平面")
    account = str(service_plane.get("account") or "").strip()
    ssh_key_secret = str(service_plane.get("sshKeySecret") or "").strip()
    if not account or not ssh_key_secret:
        raise RuntimeError("service 平面缺少账号或 SSH secret 声明")
    services = tuple(
        str(item).strip()
        for item in (service_plane.get("rootlessGovernedComposeServices") or [])
        if str(item).strip()
    )
    if not services:
        raise RuntimeError("service 平面缺少 governed compose services")
    return ServicePlaneAccess(
        host=_resolve_prod_host(topology),
        account=account,
        ssh_key_secret=ssh_key_secret,
        instance_suffix=instance_suffix,
        services=services,
    )


def _remote_probe_script(instance_suffix: str, services: tuple[str, ...]) -> str:
    quoted_services = " ".join(shlex.quote(service) for service in services)
    return f"""set -euo pipefail
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
for service in {quoted_services}; do
  pattern="^quwoquan-service-{instance_suffix}[_-]${{service}}[_-][0-9]+$"
  container="$(podman ps -a --format '{{{{.Names}}}}' | grep -E "$pattern" | head -n 1 || true)"
  if [[ -z "$container" ]]; then
    echo "FAIL: missing $service container for instance_suffix={instance_suffix}" >&2
    exit 2
  fi
  image_ref="$(podman inspect -f '{{{{.Config.Image}}}}' "$container")"
  image_version="${{image_ref##*:}}"
  config_version="$(
    podman inspect -f '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' "$container" \
      | awk -F= '/^CONFIG_VERSION=/ {{print $2; exit}}'
  )"
  if [[ -z "$image_version" || "$image_version" == "$image_ref" ]]; then
    echo "FAIL: $service current image version is empty or digest-only" >&2
    exit 2
  fi
  if [[ -z "$config_version" ]]; then
    echo "FAIL: $service current config version is empty" >&2
    exit 2
  fi
  printf '%s\\t%s\\t%s\\t%s\\n' "$service" "$container" "$image_version" "$config_version" >> "$tmp"
done
PROBE_FILE="$tmp" python3 - <<'PY'
import json
import os
from pathlib import Path

rows = []
for line in Path(os.environ["PROBE_FILE"]).read_text(encoding="utf-8").splitlines():
    service, container, image, config = line.split("\\t")
    rows.append({{"service": service, "container": container, "image": image, "config": config}})
images = {{row["image"] for row in rows}}
configs = {{row["config"] for row in rows}}
if len(images) != 1 or len(configs) != 1:
    raise SystemExit(f"FAIL: production workload version drift: images={{sorted(images)}} configs={{sorted(configs)}}")
payload = {{
    "from_image": next(iter(images)),
    "from_config": next(iter(configs)),
    "workloads": rows,
}}
print(json.dumps(payload, ensure_ascii=False))
PY
"""


def _run_remote_probe(access: ServicePlaneAccess) -> dict[str, str]:
    if os.environ.get("PROD_KUBECONFIG", "").strip():
        raise RuntimeError("PROD_KUBECONFIG 已退役，禁止再作为 prod 状态来源")
    ssh_key = os.environ.get(access.ssh_key_secret, "").strip()
    if not ssh_key:
        raise RuntimeError(f"缺少远端状态探测所需凭据 {access.ssh_key_secret}")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        key_path = Path(handle.name)
        handle.write(ssh_key + "\n")
    try:
        key_path.chmod(0o600)
        result = subprocess.run(
            [
                "ssh",
                "-i",
                str(key_path),
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{access.account}@{access.host}",
                "bash",
                "-s",
            ],
            input=_remote_probe_script(access.instance_suffix, access.services),
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        key_path.unlink(missing_ok=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"ssh exit={result.returncode}"
        raise RuntimeError(f"远端 prod 状态探测失败: {detail}")
    try:
        payload = json.loads((result.stdout or "").strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"远端 prod 状态返回非 JSON: {result.stdout!r}") from exc
    from_image = str(payload.get("from_image") or "").strip()
    from_config = str(payload.get("from_config") or "").strip()
    if not from_image or not from_config:
        raise RuntimeError("远端 prod 状态缺少 from_image/from_config")
    return {
        "from_image": from_image,
        "from_config": from_config,
        "source_host": access.host,
        "source_account": access.account,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve current prod release state from the service plane over SSH.",
    )
    parser.add_argument("--instance-suffix", default="prod")
    parser.add_argument("--output-format", choices=("json", "shell"), default="json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        access = _resolve_service_plane(
            _load_yaml(ACCESS_MANIFEST),
            load_environment_topology(),
            args.instance_suffix,
        )
        payload = _run_remote_probe(access)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if args.output_format == "shell":
        print(f"RESOLVED_FROM_IMAGE={shlex.quote(payload['from_image'])}")
        print(f"RESOLVED_FROM_CONFIG={shlex.quote(payload['from_config'])}")
        print(f"RESOLVED_FROM_SOURCE_HOST={shlex.quote(payload['source_host'])}")
        print(f"RESOLVED_FROM_SOURCE_ACCOUNT={shlex.quote(payload['source_account'])}")
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
