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
    deduped: dict[str, Path] = {str(path): path for path in files}
    return sorted(deduped.values())


def main() -> int:
    manifest = load_environment_topology()
    issues: list[str] = []
    env_urls = {env: set(environment_url_values(manifest, env)) for env in ENVIRONMENTS}

    for env_name in ENVIRONMENTS:
        files = artifact_files(env_name)
        if not files:
            issues.append(f"no artifact files found for {env_name}")
            continue
        foreign_urls = {
            other_env: urls for other_env, urls in env_urls.items() if other_env != env_name
        }
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for other_env, urls in foreign_urls.items():
                for url in urls:
                    if url and url in text:
                        issues.append(
                            f"{path.relative_to(ROOT)} leaks {other_env} URL {url}"
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
