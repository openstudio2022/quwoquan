#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.environment_topology import (
    ENVIRONMENTS,
    environment_url_values,
    forbidden_host_tokens,
    load_environment_topology,
)

# 隔离校验对象是每个环境包的「生效配置」（env overlay），不是 config-provider-layering
# 的 dev 默认基层，也不是共享的多环境拓扑清单：
#   - default_app_runtime.yaml / default_config.yaml 是 default+env 分层的基层（打包契约
#     verify_environment_packaging_contract 强制其随包存在），运行期被 env overlay 覆盖，
#     其 dev 默认 URL（127.0.0.1 等）在 prod 不生效。
#   - environment_topology_manifest.yaml 是所有环境包内容相同的共享多环境参考清单，
#     天然含各环境 URL，并非「本环境包泄漏他环境」语义。
# 故隔离/纯度校验只针对生效 env 配置（app_runtime.yaml / service config.yaml / report.json）。
EXCLUDED_BASENAMES = frozenset(
    {
        "default_app_runtime.yaml",
        "default_config.yaml",
        "environment_topology_manifest.yaml",
    }
)


def artifact_files(env_name: str) -> list[Path]:
    files: list[Path] = []
    app_dir = ROOT / "artifacts" / "app-env-packages" / env_name
    if app_dir.exists():
        files.extend(path for path in app_dir.rglob("*") if path.is_file())
    service_root = ROOT / "artifacts" / "service-env-packages"
    if service_root.exists():
        files.extend(
            path
            for path in service_root.glob(f"*/{env_name}/**/*")
            if path.is_file()
        )
    files = [path for path in files if path.name not in EXCLUDED_BASENAMES]
    deduped: dict[str, Path] = {str(path): path for path in files}
    return sorted(deduped.values())


def main() -> int:
    manifest = load_environment_topology()
    issues: list[str] = []
    env_allowed_tokens = {
        env: set(environment_url_values(manifest, env)).union(
            {
                str(item).strip()
                for item in manifest["environments"][env].get("hostAllowlist", [])
                if str(item).strip()
            }
        )
        for env in ENVIRONMENTS
    }

    for env_name in ENVIRONMENTS:
        files = artifact_files(env_name)
        if not files:
            issues.append(f"no artifact files found for {env_name}")
            continue
        current_allowed_tokens = env_allowed_tokens.get(env_name, set())
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for other_env, tokens in env_allowed_tokens.items():
                if other_env == env_name:
                    continue
                for token in tokens:
                    if not token or token in current_allowed_tokens:
                        continue
                    if token in text:
                        issues.append(
                            f"{path.relative_to(ROOT)} leaks {other_env} host token {token}"
                        )
            if env_name == "prod":
                for token in forbidden_host_tokens(manifest, env_name):
                    if token and token in text:
                        issues.append(
                            f"{path.relative_to(ROOT)} contains forbidden prod token {token!r}"
                        )

    if issues:
        print("[verify_env_artifact_isolation] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_env_artifact_isolation] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
