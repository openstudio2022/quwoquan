#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.environment_topology import ENVIRONMENTS, load_environment_topology


APP_RUNTIME_KEYS = {
    "gatewayBaseUrl": ("publicBases", "api"),
    "realtimeBaseUrl": ("publicBases", "realtime"),
    "mediaAvatarCdnBaseUrl": ("publicBases", "mediaAvatar"),
    "mediaImageCdnBaseUrl": ("publicBases", "mediaImage"),
    "mediaVideoCdnBaseUrl": ("publicBases", "mediaVideo"),
    "mediaUploadBaseUrl": ("publicBases", "mediaUpload"),
}
ALLOWED_SERVICE_PUBLIC_KEYS = {"mediaAvatar", "mediaImage", "mediaVideo", "mediaUpload"}


def parse_runtime_yaml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            continue
        if section != "runtime" or indent != 2 or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    manifest = load_environment_topology()
    issues: list[str] = []

    env_public_bases: dict[str, dict[str, str]] = {}
    env_allowed_host_tokens: dict[str, set[str]] = {}
    for env_name in ENVIRONMENTS:
        env_cfg = manifest["environments"][env_name]
        env_public_bases[env_name] = dict(env_cfg["publicBases"])
        env_allowed_host_tokens[env_name] = {
            str(item).strip()
            for item in env_cfg.get("hostAllowlist", [])
            if str(item).strip()
        }

        runtime_path = ROOT / "quwoquan_app" / "configs" / env_name / "app_runtime.yaml"
        runtime_values = parse_runtime_yaml(runtime_path)
        for runtime_key, manifest_path in APP_RUNTIME_KEYS.items():
            section_key, value_key = manifest_path
            expected = str(env_cfg[section_key][value_key]).strip()
            actual = str(runtime_values.get(runtime_key, "")).strip()
            if actual != expected:
                issues.append(
                    f"{runtime_path.relative_to(ROOT)}: {runtime_key} mismatch, expected {expected}, got {actual}"
                )

    service_configs = sorted(
        ROOT.glob("quwoquan_service/services/*/configs/*/config.yaml")
    )
    for cfg in service_configs:
        env_name = cfg.parent.name
        if env_name not in ENVIRONMENTS:
            continue
        text = cfg.read_text(encoding="utf-8")

        for key, value in env_public_bases[env_name].items():
            if not value or value not in text:
                continue
            if key not in ALLOWED_SERVICE_PUBLIC_KEYS:
                issues.append(
                    f"{cfg.relative_to(ROOT)} references service-forbidden public base {key}={value}"
                )

        current_allowed_tokens = env_allowed_host_tokens.get(env_name, set())
        for other_env in ENVIRONMENTS:
            if other_env == env_name:
                continue
            for token in env_allowed_host_tokens.get(other_env, set()):
                if not token or token in current_allowed_tokens:
                    continue
                if token in text:
                    issues.append(
                        f"{cfg.relative_to(ROOT)} references {other_env} host token {token}"
                    )

        if env_name == "prod":
            forbidden = (".test", ".example", "127.0.0.1", "10.0.2.2", "192.168.")
            if any(token in text for token in forbidden):
                issues.append(
                    f"{cfg.relative_to(ROOT)} contains local/test host token in prod config"
                )

    if issues:
        print("[verify_public_vs_upstream_url_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_public_vs_upstream_url_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
