#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

env_name="${1:-}"
if [[ "$env_name" == "--env" ]]; then
  env_name="${2:-}"
fi
if [[ -z "$env_name" ]]; then
  env_name="${ENV:-}"
fi
case "$env_name" in
  alpha|beta|gamma|prod-gray|prod) ;;
  *)
    echo "FAIL: --env must be one of alpha|beta|gamma|prod-gray|prod" >&2
    exit 2
    ;;
esac

cfg="quwoquan_app/configs/${env_name}/app_runtime.yaml"
if [[ ! -f "$cfg" ]]; then
  echo "FAIL: app runtime config not found: $cfg" >&2
  exit 1
fi

APP_RUNTIME_ENV="$env_name" bash agent_ops/deploy/shared/verify_cdn_domain_injection.sh

python3 scripts/verify_app_seed_manifests.py >/dev/null

out_dir="artifacts/app-env-packages/${env_name}"
rm -rf "$out_dir"
mkdir -p "$out_dir"
cp "quwoquan_app/configs/default/app_runtime.yaml" "$out_dir/default_app_runtime.yaml"
cp "$cfg" "$out_dir/app_runtime.yaml"

python3 - "$env_name" "$cfg" "$out_dir/report.json" <<'PY'
import json
import re
import sys
from pathlib import Path

env_name, cfg_path, report_path = sys.argv[1:4]
text = Path(cfg_path).read_text(encoding="utf-8")

def scalar(path):
    # Tiny YAML reader for the simple runtime config shape used here.
    parts = path.split(".")
    current_indent = -1
    section = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.endswith(":"):
            section = line[:-1]
            continue
        if section == parts[0] and indent == 2 and line.startswith(parts[1] + ":"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""

runtime_env = scalar("runtime.appRuntimeEnv")
data_source = scalar("runtime.appDataSource")
gateway = scalar("runtime.gatewayBaseUrl")
realtime = scalar("runtime.realtimeBaseUrl")
avatar_cdn = scalar("runtime.mediaAvatarCdnBaseUrl")
image_cdn = scalar("runtime.mediaImageCdnBaseUrl")
video_cdn = scalar("runtime.mediaVideoCdnBaseUrl")
upload_base = scalar("runtime.mediaUploadBaseUrl")
current_user_id = scalar("runtime.currentUserId")
seed_manifest = scalar("seed.manifest")
if runtime_env != env_name:
    raise SystemExit(f"runtime.appRuntimeEnv mismatch: {runtime_env} != {env_name}")
if env_name == "alpha" and data_source != "mock":
    raise SystemExit("alpha package must use mock data source")
if env_name in {"beta", "gamma", "prod-gray", "prod"} and data_source != "remote":
    raise SystemExit(f"{env_name} package must use remote data source")
if env_name in {"prod-gray", "prod"} and ("test_fixtures" in text or "seedRefs" in text or "requiresSeedReset" in text):
    raise SystemExit(f"{env_name} app package config must not reference test fixtures or seed refs")
for label, value in {
    "gatewayBaseUrl": gateway,
    "mediaAvatarCdnBaseUrl": avatar_cdn,
    "mediaImageCdnBaseUrl": image_cdn,
    "mediaVideoCdnBaseUrl": video_cdn,
    "mediaUploadBaseUrl": upload_base,
}.items():
    if not (value.startswith("http://") or value.startswith("https://")):
        raise SystemExit(f"{label} must include http/https scheme")
if env_name in {"prod-gray", "prod"}:
    forbidden = (".example", ".test", "127.0.0.1", "10.0.2.2", "192.168.", "mock-cdn.example.com")
    joined = "\n".join([gateway, realtime, avatar_cdn, image_cdn, video_cdn, upload_base])
    if any(token in joined for token in forbidden):
        raise SystemExit(f"{env_name} app package contains forbidden local/test media or gateway URL")

report = {
    "status": "packaged",
    "env": env_name,
    "runtimeEnv": runtime_env,
    "dataSource": data_source,
    "gatewayBaseUrl": gateway,
    "realtimeBaseUrl": realtime,
    "avatarCdnBaseUrl": avatar_cdn,
    "imageCdnBaseUrl": image_cdn,
    "videoCdnBaseUrl": video_cdn,
    "uploadBaseUrl": upload_base,
    "currentUserId": current_user_id,
    "seedManifest": seed_manifest,
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "app env package prepared: $out_dir"
