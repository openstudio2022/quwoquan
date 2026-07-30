#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    app_deployment_package_dir,
    deployment_package_root,
    deployment_target_for_env,
)
FORBIDDEN_TOKENS = (
    "APP_DATA_SOURCE=mock",
    "test_fixtures",
    "seedRefs",
    "requiresSeedReset",
    ".example",
    ".test",
    ".sim.",
    "127.0.0.1",
    "10.0.2.2",
    "192.168.",
    "mock-cdn.example.com",
)
PROD_SIM_PACKAGE_ALLOWED_HOST_TOKENS = frozenset(
    {".test", ".sim.", "127.0.0.1", "10.0.2.2", "192.168."}
)
PROD_SOURCES = [
    ROOT / "quwoquan_app" / "configs" / "prod" / "app_runtime.yaml",
]
PROD_SOURCE_GLOBS = [
    ROOT.glob("quwoquan_service/services/*/environments/prod/config.yaml"),
]
# 纯度校验对象是 prod「生效配置」（env overlay），不是配置分层的 dev 默认基层：
#   - default_app_runtime.yaml / default_config.yaml 是 config-provider-layering 的
#     dev 默认基层，运行期被 env overlay 覆盖；打包契约（verify_environment_packaging_contract）
#     强制 service 包为 default+env 布局，故基层必须随包存在、且合法包含本地默认值。
# 单环境 environment_runtime.yaml 属于 prod 生效事实，必须参与扫描。
# 默认基层不代表 prod 运行时实际使用的端点，故排除出禁用 token 扫描；
# prod 生效配置（app_runtime.yaml / service config.yaml / configs/prod/*）仍严格校验。
EXCLUDED_BASENAMES = frozenset(
    {
        "default_app_runtime.yaml",
        "default_config.yaml",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("app", "all"), default="all")
    parser.add_argument("--target", default="")
    return parser.parse_args()


def iter_text_files(*, scope: str, target: str) -> list[Path]:
    files = [path for path in PROD_SOURCES if path.is_file()]
    target_name = deployment_target_for_env("prod", target=target)
    artifact_groups = [
        app_deployment_package_dir("prod", target=target_name).glob("**/*"),
    ]
    if scope != "app":
        artifact_groups.append(
            (deployment_package_root("prod", target=target_name) / "services").glob(
                "**/*"
            )
        )
    for group in [*PROD_SOURCE_GLOBS, *artifact_groups]:
        for path in group:
            if path.is_file() and path.name not in EXCLUDED_BASENAMES:
                files.append(path)
    deduped: dict[str, Path] = {str(path): path for path in files}
    return sorted(deduped.values())


def main() -> int:
    args = parse_args()
    issues: list[str] = []
    target_name = deployment_target_for_env("prod", target=args.target)
    app_package_root = app_deployment_package_dir(
        "prod",
        target=target_name,
    ).resolve()
    for path in iter_text_files(scope=args.scope, target=args.target):
        text = path.read_text(encoding="utf-8", errors="replace")
        resolved = path.resolve()
        try:
            is_app_package = resolved.is_relative_to(app_package_root)
        except AttributeError:
            is_app_package = app_package_root in resolved.parents
        forbidden_tokens = (
            tuple(
                token
                for token in FORBIDDEN_TOKENS
                if token not in PROD_SIM_PACKAGE_ALLOWED_HOST_TOKENS
            )
            if target_name == "prod-sim" and is_app_package
            else FORBIDDEN_TOKENS
        )
        for token in forbidden_tokens:
            if token in text:
                try:
                    display = path.relative_to(ROOT).as_posix()
                except ValueError:
                    display = path.as_posix()
                issues.append(f"{display} contains forbidden token {token!r}")

    if issues:
        print("[verify_prod_package_purity] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_prod_package_purity] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
