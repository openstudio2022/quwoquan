#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
KEY_DIR="${PROD_SSH_KEY_DIR:-$HOME/.ssh/quwoquan-prod}"
HOST="${PROD_SSH_HOST:-118.31.239.122}"
ACCOUNT="prod-service-svc"
DEST_ROOT="/home/${ACCOUNT}/bootstrap/prod-build-workspace"
SERVICES="rec-model-service,content-service,chat-service,user-service,assistant-service,product-ops-service,tag-service"

usage() {
  cat <<'EOF'
Usage: sync_prod_build_workspace.sh [--host <host>] [--key-dir <dir>] [--dest-root <path>] [--services <csv>]

Sync the minimal repo subset required for remote prod service-plane native image builds.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --key-dir) KEY_DIR="$2"; shift 2 ;;
    --dest-root) DEST_ROOT="$2"; shift 2 ;;
    --services) SERVICES="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "FAIL: unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

KEY_FILE="${KEY_DIR%/}/${ACCOUNT}"
[[ -f "$KEY_FILE" ]] || { echo "FAIL: missing key file: $KEY_FILE" >&2; exit 2; }

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/prod-build-sync.XXXXXX")"
cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

export ROOT_DIR STAGE_DIR SERVICES
python3 - <<'PY'
import os
import shutil
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
stage = Path(os.environ["STAGE_DIR"])
services = [item.strip() for item in os.environ["SERVICES"].split(",") if item.strip()]

qwq = stage / "quwoquan_service"
(qwq / "contracts" / "metadata").mkdir(parents=True, exist_ok=True)
(stage / "deploy" / "service").mkdir(parents=True, exist_ok=True)
(stage / "releases" / "config").mkdir(parents=True, exist_ok=True)

def copy_file(src_rel: str, dst_rel: str | None = None) -> None:
    src = root / src_rel
    dst = stage / (dst_rel or src_rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

def copy_tree(src_rel: str, dst_rel: str | None = None) -> None:
    src = root / src_rel
    dst = stage / (dst_rel or src_rel)
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)

def copy_path(src_rel: str, dst_rel: str | None = None) -> None:
    src = root / src_rel
    if src.is_dir():
        copy_tree(src_rel, dst_rel)
        return
    copy_file(src_rel, dst_rel)

copy_file("quwoquan_service/go.mod")
copy_file("quwoquan_service/go.sum")
copy_file("quwoquan_service/docker-compose.gamma-local.yaml")
for tree in [
    "quwoquan_service/runtime",
    "quwoquan_service/generated",
    "quwoquan_service/api",
]:
    copy_path(tree)

service_dockerfile_roots = {
    "rec-model-service": "quwoquan_service/services/rec-model-service/Dockerfile",
    "user-service": "quwoquan_service/services/user-service/Dockerfile",
}
for service in services:
    copy_tree(f"quwoquan_service/services/{service}")
    dockerfile = service_dockerfile_roots.get(service)
    if dockerfile:
        copy_file(dockerfile)
    else:
        copy_file(f"deploy/service/{service}/Dockerfile")

metadata_roots = {
    "assistant-service": "assistant",
    "user-service": "user",
}
for service, metadata_dir in metadata_roots.items():
    if service in services:
        copy_tree(
            f"quwoquan_service/contracts/metadata/{metadata_dir}",
            f"quwoquan_service/contracts/metadata/{metadata_dir}",
        )

if "rec-model-service" in services:
    copy_file(
        "quwoquan_service/scripts/ml/artifact_store.py",
        "quwoquan_service/scripts/ml/artifact_store.py",
    )
    copy_file(
        "quwoquan_service/scripts/ml/model_registry.py",
        "quwoquan_service/scripts/ml/model_registry.py",
    )
    copy_tree(
        "releases/config/recommendation-service",
        "releases/config/recommendation-service",
    )
PY

COPYFILE_DISABLE=1 tar -C "$STAGE_DIR" -czf - . \
| ssh -i "$KEY_FILE" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=20 \
    "${ACCOUNT}@${HOST}" \
    "rm -rf '${DEST_ROOT}' && mkdir -p '${DEST_ROOT}' && tar -xzf - -C '${DEST_ROOT}'"

echo "${DEST_ROOT}"
