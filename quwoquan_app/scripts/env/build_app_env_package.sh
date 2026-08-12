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
target_name="${QWQ_DEPLOY_TARGET:-}"
if [[ -z "$target_name" ]]; then
  target_name="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$env_name" <<'PY'
import sys

from quwoquan_ops.cli.lib.output_paths import deployment_target_for_env

print(deployment_target_for_env(sys.argv[1]))
PY
)"
fi
out_dir="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$env_name" "$target_name" <<'PY'
import sys

from quwoquan_ops.cli.lib.output_paths import app_deployment_package_dir

print(app_deployment_package_dir(sys.argv[1], target=sys.argv[2]))
PY
)"
rm -rf "$out_dir"
mkdir -p "$out_dir"
environment_runtime="$out_dir/environment_runtime.yaml"
PYTHONDONTWRITEBYTECODE=1 python3 - "$env_name" "$target_name" "$environment_runtime" <<'PY'
import json
import sys
from pathlib import Path

from quwoquan_ops.cli.lib.environment_topology import (
    get_environment,
    get_target,
    load_environment_topology,
)

environment, target_name, output = sys.argv[1:4]
manifest = load_environment_topology()
runtime = get_environment(manifest, environment)
target = get_target(manifest, target_name)
if not isinstance(target, dict) or target.get("env") != environment:
    raise SystemExit(
        f"runtime target {target_name!r} does not belong to environment {environment!r}"
    )

resolved_roles = target["resolvedUrlRoles"]
tls_profiles = sorted(
    {
        str(role.get("tlsProfile") or "")
        for role in resolved_roles.values()
        if isinstance(role, dict) and str(role.get("tlsProfile") or "")
    }
)
projected = {
    "schema": "environment-runtime-package",
    "environment": environment,
    "target": target_name,
    "backend": target.get("backend"),
    "localResourceGroup": target.get("localResourceGroup", ""),
    "portProfile": target.get("portProfile"),
    "publicBases": target["publicBases"],
    "transportRequirements": {
        "publicCaRequired": True,
        "tlsProfiles": tls_profiles,
    },
    "artifactPolicy": runtime.get("artifactPolicy"),
    "dataRelease": target.get("dataRelease", {}),
}
Path(output).write_text(
    json.dumps(projected, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

cp "quwoquan_app/configs/default/app_runtime.yaml" "$out_dir/default_app_runtime.yaml"
PYTHONDONTWRITEBYTECODE=1 python3 - "$cfg" "$environment_runtime" "$out_dir/app_runtime.yaml" <<'PY'
import json
import sys
from pathlib import Path

source_path, runtime_path, output_path = map(Path, sys.argv[1:4])
topology = json.loads(runtime_path.read_text(encoding="utf-8"))
public_bases = topology.get("publicBases") or {}
target_name = str(topology.get("target") or "").strip()
api_base = str(public_bases.get("api") or "").rstrip("/")
runtime_values = {
    "gatewayBaseUrl": api_base,
    "legalBaseUrl": str(public_bases.get("legal") or "").rstrip("/"),
    "publicWebBaseUrl": str(public_bases.get("publicWeb") or "").rstrip("/"),
    "appDownloadBaseUrl": str(public_bases.get("appDownload") or "").rstrip("/"),
    "realtimeBaseUrl": str(public_bases.get("realtime") or "").rstrip("/"),
    "mediaAvatarCdnBaseUrl": str(public_bases.get("mediaAvatar") or "").rstrip("/"),
    "mediaImageCdnBaseUrl": str(public_bases.get("mediaImage") or "").rstrip("/"),
    "mediaVideoCdnBaseUrl": str(public_bases.get("mediaVideo") or "").rstrip("/"),
    "mediaUploadBaseUrl": str(public_bases.get("mediaUpload") or "").rstrip("/"),
    "rtcMediaConnectionUrl": str(public_bases.get("rtc") or "").rstrip("/"),
}
if any(not value for value in runtime_values.values()):
    missing = sorted(key for key, value in runtime_values.items() if not value)
    raise SystemExit("target app runtime endpoints missing: " + ", ".join(missing))

section = ""
rendered: list[str] = []
for raw in source_path.read_text(encoding="utf-8").splitlines():
    stripped = raw.strip()
    indent = len(raw) - len(raw.lstrip(" "))
    if indent == 0 and stripped.endswith(":"):
        section = stripped[:-1]
    if section == "runtime" and indent == 2 and ":" in stripped:
        key = stripped.split(":", 1)[0].strip()
        if key in runtime_values:
            raw = f"  {key}: {runtime_values[key]}"
    elif section == "gray" and indent == 2 and stripped.startswith("strategyEndpoint:"):
        raw = f"  strategyEndpoint: {api_base}/runtime/gray-strategy"
    rendered.append(raw)
Path(output_path).write_text("\n".join(rendered) + "\n", encoding="utf-8")
PY

python3 - "$env_name" "$out_dir/app_runtime.yaml" "$environment_runtime" "$out_dir/report.json" <<'PY'
import json
import hashlib
import os
import subprocess
import re
import sys
from pathlib import Path

env_name, cfg_path, runtime_path, report_path = sys.argv[1:5]
text = Path(cfg_path).read_text(encoding="utf-8")
env_topology = json.loads(Path(runtime_path).read_text(encoding="utf-8"))
if (
    env_topology.get("schema") != "environment-runtime-package"
    or env_topology.get("environment") != env_name
):
    raise SystemExit(f"environment runtime identity mismatch: {runtime_path}")
public_bases = env_topology.get("publicBases") or {}
artifact_policy = ((env_topology.get("artifactPolicy") or {}).get("app") or {})
target_name = str(env_topology.get("target") or "").strip()

def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

revision = os.environ.get("QWQ_PACKAGE_SOURCE_REVISION", "").strip()
if not revision:
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
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""

runtime_env = scalar("runtime.appRuntimeEnv")
gateway = scalar("runtime.gatewayBaseUrl")
legal_base = scalar("runtime.legalBaseUrl")
public_web = scalar("runtime.publicWebBaseUrl")
app_download = scalar("runtime.appDownloadBaseUrl")
realtime = scalar("runtime.realtimeBaseUrl")
avatar_cdn = scalar("runtime.mediaAvatarCdnBaseUrl")
image_cdn = scalar("runtime.mediaImageCdnBaseUrl")
video_cdn = scalar("runtime.mediaVideoCdnBaseUrl")
upload_base = scalar("runtime.mediaUploadBaseUrl")
rtc_media = scalar("runtime.rtcMediaConnectionUrl")
current_user_id = scalar("runtime.currentUserId")
seed_enabled = scalar("seed.enabled").lower()
seed_manifest = scalar("seed.manifest")
if runtime_env != env_name:
    raise SystemExit(f"runtime.appRuntimeEnv mismatch: {runtime_env} != {env_name}")
if seed_enabled or seed_manifest:
    raise SystemExit(f"{env_name} app package config must not carry runtime seed")
if "test_fixtures" in text or "seedRefs" in text or "requiresSeedReset" in text:
    raise SystemExit(f"{env_name} app package config must not reference seed or test fixtures")
expected_urls = {
    "gatewayBaseUrl": public_bases.get("api", ""),
    "legalBaseUrl": public_bases.get("legal", ""),
    "publicWebBaseUrl": public_bases.get("publicWeb", ""),
    "appDownloadBaseUrl": public_bases.get("appDownload", ""),
    "realtimeBaseUrl": public_bases.get("realtime", ""),
    "mediaAvatarCdnBaseUrl": public_bases.get("mediaAvatar", ""),
    "mediaImageCdnBaseUrl": public_bases.get("mediaImage", ""),
    "mediaVideoCdnBaseUrl": public_bases.get("mediaVideo", ""),
    "mediaUploadBaseUrl": public_bases.get("mediaUpload", ""),
    "rtcMediaConnectionUrl": public_bases.get("rtc", ""),
}
for label, value in {
    "gatewayBaseUrl": gateway,
    "legalBaseUrl": legal_base,
    "publicWebBaseUrl": public_web,
    "appDownloadBaseUrl": app_download,
    "realtimeBaseUrl": realtime,
    "mediaAvatarCdnBaseUrl": avatar_cdn,
    "mediaImageCdnBaseUrl": image_cdn,
    "mediaVideoCdnBaseUrl": video_cdn,
    "mediaUploadBaseUrl": upload_base,
    "rtcMediaConnectionUrl": rtc_media,
}.items():
    if not (value.startswith("http://") or value.startswith("https://")):
        if label in {"realtimeBaseUrl", "rtcMediaConnectionUrl"} and (
            value.startswith("ws://") or value.startswith("wss://")
        ):
            pass
        else:
            raise SystemExit(f"{label} must include http/https scheme")
    expected = str(expected_urls.get(label, "")).strip()
    if expected and value != expected:
        raise SystemExit(f"{label} mismatch: {value} != {expected}")
if env_name in {"prod"} and target_name == "prod-hosted":
    forbidden = tuple(env_topology.get("forbiddenHostTokens") or ()) or (
        ".example",
        ".test",
        "127.0.0.1",
        "10.0.2.2",
        "192.168.",
        "mock-cdn.example.com",
    )
    joined = "\n".join([gateway, legal_base, public_web, app_download, realtime, avatar_cdn, image_cdn, video_cdn, upload_base, rtc_media])
    if any(token in joined for token in forbidden):
        raise SystemExit(f"{env_name} app package contains forbidden local/test media or gateway URL")

report = {
    "status": "packaged",
    "env": env_name,
    "target": target_name,
    "runtimeEnv": runtime_env,
    "composition": "production_remote",
    "gatewayBaseUrl": gateway,
    "legalBaseUrl": legal_base,
    "publicWebBaseUrl": public_web,
    "appDownloadBaseUrl": app_download,
    "realtimeBaseUrl": realtime,
    "avatarCdnBaseUrl": avatar_cdn,
    "imageCdnBaseUrl": image_cdn,
    "videoCdnBaseUrl": video_cdn,
    "uploadBaseUrl": upload_base,
    "rtcMediaConnectionUrl": rtc_media,
    "currentUserId": current_user_id,
    "artifactPolicy": artifact_policy,
    "publicBases": expected_urls,
    "runtimeConfigDigest": digest(Path(cfg_path)),
    "provenance": {
        "gitRevision": revision,
        "files": {
            "defaultAppRuntime": digest(Path(report_path).parent / "default_app_runtime.yaml"),
            "appRuntime": digest(Path(report_path).parent / "app_runtime.yaml"),
            "environmentRuntime": digest(Path(runtime_path)),
        },
    },
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$env_name" == "prod" ]]; then
  python3 quwoquan_app/scripts/env/verify_prod_package_purity.py --scope app --target "$target_name" >/dev/null
fi

echo "app env package prepared: $out_dir"
