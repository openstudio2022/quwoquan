#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("FAIL: PyYAML required")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.prod_management_access import prod_management_ssh_host

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh" / "quwoquan-prod"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect prod plane rootless runtime.")
    parser.add_argument("--plane", default="service", choices=["service", "edge"])
    parser.add_argument(
        "--instance",
        default="prod",
        choices=["prod", "gray", "prevalidate"],
    )
    parser.add_argument("--host", default="")
    parser.add_argument("--key-dir", default=os.environ.get("PROD_SSH_KEY_DIR", ""))
    parser.add_argument("--output", default="")
    return parser.parse_args()


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL: {path} must parse as object")
    return data


def _resolve_plane_spec(plane_name: str) -> dict:
    access = _load_yaml(ACCESS_MANIFEST)
    for plane in access.get("planes") or []:
        if str(plane.get("plane")) == plane_name:
            return plane
    raise SystemExit(f"FAIL: plane not found in access manifest: {plane_name}")


def _resolve_host(override: str) -> str:
    try:
        return prod_management_ssh_host(override=override)
    except RuntimeError as error:
        raise SystemExit(f"FAIL: {error}") from error


def _resolve_key_source(secret_name: str, account: str, key_dir: Path) -> tuple[list[str], str]:
    for suffix in ("_FILE", "_PATH"):
        raw = os.environ.get(f"{secret_name}{suffix}", "").strip()
        if raw:
            path = Path(raw).expanduser()
            if path.is_file():
                return (["-i", str(path)], f"explicit-file:{path}")
            raise SystemExit(f"FAIL: key path is invalid: {path}")
    candidate = key_dir / account
    if candidate.is_file():
        return (["-i", str(candidate)], f"key-dir-file:{candidate}")
    public_key = candidate.with_suffix(".pub")
    if os.environ.get("SSH_AUTH_SOCK", "").strip() and public_key.is_file():
        expected = public_key.read_text(encoding="utf-8").strip().split()
        if len(expected) >= 2:
            check = subprocess.run(
                ["ssh-add", "-L"],
                text=True,
                capture_output=True,
                check=False,
            )
            if check.returncode == 0:
                expected_key = f"{expected[0]} {expected[1]}"
                for line in check.stdout.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and f"{parts[0]} {parts[1]}" == expected_key:
                        return ([], f"ssh-agent:{public_key}")
    raise SystemExit(
        f"FAIL: missing SSH credential for {secret_name} ({candidate} / {public_key})"
    )


def _remote_python() -> str:
    return r"""
import json
import os
import pathlib
import subprocess

compose_root = pathlib.Path(os.environ["COMPOSE_ROOT"])
compose_file = compose_root / os.environ.get("COMPOSE_FILE_NAME", "docker-compose.prod-hosted.yaml")
env_file = compose_root / os.environ.get("ENV_FILE_NAME", "stack.env")
project = os.environ["COMPOSE_PROJECT"]
unit_name = os.environ["SYSTEMD_UNIT"]

def run(argv):
    result = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    return {
        "argv": argv,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

ps_result = run(["podman", "ps", "--all", "--format", "json"])
containers = []
if ps_result["returncode"] == 0 and ps_result["stdout"].strip():
    try:
        containers = json.loads(ps_result["stdout"])
    except json.JSONDecodeError:
        containers = []

container_ids = [item.get("Id") for item in containers if item.get("Id")]
inspect_payload = []
if container_ids:
    inspect_result = run(["podman", "inspect", *container_ids])
    if inspect_result["returncode"] == 0 and inspect_result["stdout"].strip():
        try:
            inspect_payload = json.loads(inspect_result["stdout"])
        except json.JSONDecodeError:
            inspect_payload = []
else:
    inspect_result = {"argv": ["podman", "inspect"], "returncode": 0, "stdout": "[]", "stderr": ""}

listener_result = run(["bash", "-lc", "ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null || true"])
unit_enabled = run(["systemctl", "--user", "is-enabled", unit_name])
unit_active = run(["systemctl", "--user", "is-active", unit_name])

selected_inspect = []
for item in inspect_payload:
    labels = ((item.get("Config") or {}).get("Labels") or {})
    names = item.get("Name") or ""
    if (
        labels.get("com.docker.compose.project") == project
        or labels.get("io.podman.compose.project") == project
        or str(names).lstrip("/").startswith(project + "-")
    ):
        selected_inspect.append(item)

runtime_containers = []
for item in selected_inspect:
    state = item.get("State") or {}
    health = state.get("Health") or {}
    runtime_containers.append({
        "id": item.get("Id"),
        "name": str(item.get("Name") or "").lstrip("/"),
        "composeService": (
            ((item.get("Config") or {}).get("Labels") or {}).get("com.docker.compose.service")
            or ((item.get("Config") or {}).get("Labels") or {}).get("io.podman.compose.service")
        ),
        "image": (item.get("Config") or {}).get("Image"),
        "imageId": item.get("Image"),
        "status": state.get("Status"),
        "running": bool(state.get("Running")),
        "exitCode": state.get("ExitCode"),
        "health": health.get("Status") or "not-configured",
    })

payload = {
    "account": subprocess.run(
        ["whoami"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=True,
    ).stdout.strip(),
    "composeRoot": str(compose_root),
    "composeFile": str(compose_file),
    "composeFileExists": compose_file.is_file(),
    "envFile": str(env_file),
    "envFileExists": env_file.is_file(),
    "project": project,
    "unit": {
        "name": unit_name,
        "enabled": unit_enabled["returncode"] == 0 and unit_enabled["stdout"].strip() == "enabled",
        "active": unit_active["returncode"] == 0 and unit_active["stdout"].strip() == "active",
        "enabledReadback": unit_enabled,
        "activeReadback": unit_active,
    },
    "containerCount": len(runtime_containers),
    "containers": runtime_containers,
    "inspect": selected_inspect,
    "listeners": listener_result["stdout"],
    "podmanPs": ps_result,
    "podmanInspect": inspect_result,
}
print(json.dumps(payload, ensure_ascii=False))
"""


def main() -> int:
    args = parse_args()
    plane = _resolve_plane_spec(args.plane)
    host = _resolve_host(args.host)
    key_dir = Path(args.key_dir).expanduser() if args.key_dir else DEFAULT_KEY_DIR
    ssh_args, key_source = _resolve_key_source(
        str(plane.get("sshKeySecret")),
        str(plane.get("account")),
        key_dir,
    )
    layout = plane.get("rootlessRuntimeLayout") or {}
    compose_root = str(plane.get("composeProjectRoot"))
    if args.instance == "prevalidate":
        compose_root = f"{compose_root.rstrip('/')}/prevalidate"
    compose_file_name = str(layout.get("composeFile") or "docker-compose.prod-hosted.yaml")
    env_file_name = str(layout.get("envFile") or "stack.env")

    result = subprocess.run(
        [
            "ssh",
            *ssh_args,
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "BatchMode=yes",
            f"{plane['account']}@{host}",
            (
                f"COMPOSE_ROOT={json.dumps(compose_root)} "
                f"COMPOSE_FILE_NAME={json.dumps(compose_file_name)} "
                f"ENV_FILE_NAME={json.dumps(env_file_name)} "
                f"COMPOSE_PROJECT={json.dumps(f'quwoquan-{args.plane}-{args.instance}')} "
                f"SYSTEMD_UNIT={json.dumps(f'quwoquan-{args.plane}-{args.instance}.service')} "
                "python3 -"
            ),
        ],
        input=_remote_python(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode or 2

    payload = json.loads(result.stdout)
    payload["plane"] = args.plane
    payload["instance"] = args.instance
    payload["host"] = host
    payload["keySource"] = key_source
    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
