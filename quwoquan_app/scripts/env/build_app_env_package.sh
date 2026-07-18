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
  alpha|beta|gamma|prod) ;;
  *)
    echo "FAIL: --env must be one of alpha|beta|gamma|prod" >&2
    exit 2
    ;;
esac

cfg="quwoquan_app/configs/${env_name}/app_runtime.yaml"
if [[ ! -f "$cfg" ]]; then
  echo "FAIL: app runtime config not found: $cfg" >&2
  exit 1
fi
topology_manifest="quwoquan_ops/environments/environment_topology_manifest.yaml"
if [[ ! -f "$topology_manifest" ]]; then
  echo "FAIL: environment topology manifest not found: $topology_manifest" >&2
  exit 1
fi

cdn_domain="$(python3 - "$topology_manifest" "$env_name" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
env_name = sys.argv[2]
public_bases = ((manifest.get("environments") or {}).get(env_name) or {}).get("publicBases") or {}
media_image = str(public_bases.get("mediaImage") or "")
host = urlparse(media_image).hostname or media_image
host = host.strip()
if not host:
    print("")
elif host == "localhost" or all(part.isdigit() for part in host.split(".")):
    print(host)
else:
    parts = host.split(".")
    if host.endswith(".quwoquan-env.test") and len(parts) >= 3:
        print(".".join(parts[-3:]))
    else:
        print(".".join(parts[-2:]) if len(parts) >= 2 else host)
PY
)"

APP_RUNTIME_ENV="$env_name" CDN_DOMAIN="$cdn_domain" bash quwoquan_ops/cli/shared/verify_cdn_domain_injection.sh

python3 quwoquan_app/scripts/env/verify_app_seed_manifests.py >/dev/null

QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT/.qwq_output}"
out_dir="${QWQ_OUTPUT_ROOT}/env/${env_name}/release/app"
rm -rf "$out_dir"
mkdir -p "$out_dir"
cp "quwoquan_app/configs/default/app_runtime.yaml" "$out_dir/default_app_runtime.yaml"
cp "$cfg" "$out_dir/app_runtime.yaml"
cp "$topology_manifest" "$out_dir/environment_topology_manifest.yaml"

python3 - "$env_name" "$cfg" "$topology_manifest" "$out_dir/report.json" <<'PY'
import json
import hashlib
import subprocess
import re
import sys
from pathlib import Path

env_name, cfg_path, topology_path, report_path = sys.argv[1:5]
text = Path(cfg_path).read_text(encoding="utf-8")
topology = json.loads(Path(topology_path).read_text(encoding="utf-8"))
env_topology = ((topology.get("environments") or {}).get(env_name) or {})
public_bases = env_topology.get("publicBases") or {}
artifact_policy = ((env_topology.get("artifactPolicy") or {}).get("app") or {})

def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

revision = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    text=True,
    capture_output=True,
    check=False,
).stdout.strip()
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise SystemExit("unable to resolve package git revision")

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
legal_base = scalar("runtime.legalBaseUrl")
realtime = scalar("runtime.realtimeBaseUrl")
avatar_cdn = scalar("runtime.mediaAvatarCdnBaseUrl")
image_cdn = scalar("runtime.mediaImageCdnBaseUrl")
video_cdn = scalar("runtime.mediaVideoCdnBaseUrl")
upload_base = scalar("runtime.mediaUploadBaseUrl")
current_user_id = scalar("runtime.currentUserId")
seed_manifest = scalar("seed.manifest")
if runtime_env != env_name:
    raise SystemExit(f"runtime.appRuntimeEnv mismatch: {runtime_env} != {env_name}")
expected_data_source = artifact_policy.get("dataSource")
if expected_data_source and data_source != expected_data_source:
    raise SystemExit(
        f"{env_name} package dataSource mismatch: {data_source} != {expected_data_source}"
    )
if env_name in {"prod"} and ("test_fixtures" in text or "seedRefs" in text or "requiresSeedReset" in text):
    raise SystemExit(f"{env_name} app package config must not reference test fixtures or seed refs")
expected_urls = {
    "gatewayBaseUrl": public_bases.get("api", ""),
    "legalBaseUrl": (public_bases.get("api", "").rstrip("/") + "/legal") if env_name != "prod" else "https://quwoquan.com/legal",
    "realtimeBaseUrl": public_bases.get("realtime", ""),
    "mediaAvatarCdnBaseUrl": public_bases.get("mediaAvatar", ""),
    "mediaImageCdnBaseUrl": public_bases.get("mediaImage", ""),
    "mediaVideoCdnBaseUrl": public_bases.get("mediaVideo", ""),
    "mediaUploadBaseUrl": public_bases.get("mediaUpload", ""),
}
for label, value in {
    "gatewayBaseUrl": gateway,
    "legalBaseUrl": legal_base,
    "realtimeBaseUrl": realtime,
    "mediaAvatarCdnBaseUrl": avatar_cdn,
    "mediaImageCdnBaseUrl": image_cdn,
    "mediaVideoCdnBaseUrl": video_cdn,
    "mediaUploadBaseUrl": upload_base,
}.items():
    if not (value.startswith("http://") or value.startswith("https://")):
        if label == "realtimeBaseUrl" and (value.startswith("ws://") or value.startswith("wss://")):
            pass
        else:
            raise SystemExit(f"{label} must include http/https scheme")
    expected = str(expected_urls.get(label, "")).strip()
    if expected and value != expected:
        raise SystemExit(f"{label} mismatch: {value} != {expected}")
if env_name in {"prod"}:
    forbidden = tuple(env_topology.get("forbiddenHostTokens") or ()) or (
        ".example",
        ".test",
        "127.0.0.1",
        "10.0.2.2",
        "192.168.",
        "mock-cdn.example.com",
    )
    joined = "\n".join([gateway, legal_base, realtime, avatar_cdn, image_cdn, video_cdn, upload_base])
    if any(token in joined for token in forbidden):
        raise SystemExit(f"{env_name} app package contains forbidden local/test media or gateway URL")

report = {
    "status": "packaged",
    "env": env_name,
    "runtimeEnv": runtime_env,
    "dataSource": data_source,
    "gatewayBaseUrl": gateway,
    "legalBaseUrl": legal_base,
    "realtimeBaseUrl": realtime,
    "avatarCdnBaseUrl": avatar_cdn,
    "imageCdnBaseUrl": image_cdn,
    "videoCdnBaseUrl": video_cdn,
    "uploadBaseUrl": upload_base,
    "currentUserId": current_user_id,
    "seedManifest": seed_manifest,
    "topologySchemaVersion": topology.get("schema"),
    "artifactPolicy": artifact_policy,
    "publicBases": expected_urls,
    "provenance": {
        "gitRevision": revision,
        "files": {
            "defaultAppRuntime": digest(Path(report_path).parent / "default_app_runtime.yaml"),
            "appRuntime": digest(Path(report_path).parent / "app_runtime.yaml"),
            "topologyManifest": digest(Path(topology_path)),
        },
    },
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$env_name" == "prod" ]]; then
  python3 quwoquan_app/scripts/env/verify_prod_package_purity.py --scope app >/dev/null
fi

echo "app env package prepared: $out_dir"
