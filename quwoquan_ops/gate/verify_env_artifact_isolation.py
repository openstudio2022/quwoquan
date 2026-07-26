#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    environment_url_values,
    forbidden_host_tokens,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_package_root,
    deployment_target_for_env,
    legal_static_deployment_package_dir,
    portal_deployment_package_dir,
    runtime_shared_deployment_package_dir,
)

# App 历史包仍保留默认基线文件；服务自治包只含当前环境渲染后的 config、resources、
# manifests 与 provenance，不再复制共享多环境 topology。
EXCLUDED_BASENAMES = frozenset(
    {
        "default_app_runtime.yaml",
        "default_config.yaml",
    }
)


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def artifact_files(env_name: str, *, target_name: str) -> list[Path]:
    files: list[Path] = []
    app_dir = app_deployment_package_dir(env_name, target=target_name)
    if app_dir.exists():
        files.extend(path for path in app_dir.rglob("*") if path.is_file())
    service_root = deployment_package_root(env_name, target=target_name) / "services"
    if service_root.exists():
        files.extend(path for path in service_root.rglob("*") if path.is_file())
    runtime_shared_root = runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if runtime_shared_root.exists():
        files.extend(path for path in runtime_shared_root.rglob("*") if path.is_file())
    legal_static_root = legal_static_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if legal_static_root.exists() or legal_static_root.is_symlink():
        # 法律正文可合法引用品牌/生产站点；环境隔离只检查最终发布 URL
        # 清单，正文完整性和 digest 由 packaging contract 负责。
        legal_public_manifest = (
            legal_static_root / "current" / "public" / "legal" / "manifest.json"
        )
        if legal_public_manifest.is_file():
            files.append(legal_public_manifest)
    portal_root = portal_deployment_package_dir(env_name, target=target_name)
    if portal_root.exists() or portal_root.is_symlink():
        files.extend(path for path in portal_root.rglob("*") if path.is_file())
    files = [path for path in files if path.name not in EXCLUDED_BASENAMES]
    deduped: dict[str, Path] = {str(path): path for path in files}
    return sorted(deduped.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify packaged env artifacts do not leak other env host tokens.")
    parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    parser.add_argument("--target", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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

    env_names = [args.env] if args.env else list(ENVIRONMENTS)
    for env_name in env_names:
        try:
            target_name = deployment_target_for_env(env_name, target=args.target)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        files = artifact_files(env_name, target_name=target_name)
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
                            f"{_display(path)} leaks {other_env} host token {token}"
                        )
            if env_name == "prod":
                for token in forbidden_host_tokens(manifest, env_name):
                    if token and token in text:
                        issues.append(
                            f"{_display(path)} contains forbidden prod token {token!r}"
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
