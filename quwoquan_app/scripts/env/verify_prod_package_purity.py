#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_TOKENS = (
    "APP_DATA_SOURCE=mock",
    "test_fixtures",
    "seedRefs",
    "requiresSeedReset",
    ".example",
    ".test",
    "127.0.0.1",
    "10.0.2.2",
    "192.168.",
    "mock-cdn.example.com",
)
PROD_SOURCES = [
    ROOT / "quwoquan_app" / "configs" / "prod" / "app_runtime.yaml",
]
PROD_SOURCE_GLOBS = [
    ROOT.glob("quwoquan_service/services/*/configs/prod/config.yaml"),
]
PROD_ARTIFACT_GLOBS = [
    ROOT.glob(".qwq_output/env/prod/release/app/**/*"),
    ROOT.glob(".qwq_output/env/prod/release/service/*/**/*"),
]
# 纯度校验对象是 prod「生效配置」（env overlay），不是配置分层的 dev 默认基层，
# 也不是天然多环境的拓扑清单：
#   - default_app_runtime.yaml / default_config.yaml 是 config-provider-layering 的
#     dev 默认基层，运行期被 env overlay 覆盖；打包契约（verify_environment_packaging_contract）
#     强制 service 包为 default+env 布局，故基层必须随包存在、且合法包含本地默认值。
#   - environment_topology_manifest.yaml 是共享的多环境拓扑清单，必然含 alpha/beta 本地 token。
# 这些 scaffolding 不代表 prod 运行时实际使用的端点，故排除出禁用 token 扫描；
# prod 生效配置（app_runtime.yaml / service config.yaml / configs/prod/*）仍严格校验。
EXCLUDED_BASENAMES = frozenset(
    {
        "default_app_runtime.yaml",
        "default_config.yaml",
        "environment_topology_manifest.yaml",
    }
)


def iter_text_files() -> list[Path]:
    files = [path for path in PROD_SOURCES if path.is_file()]
    for group in PROD_SOURCE_GLOBS + PROD_ARTIFACT_GLOBS:
        for path in group:
            if path.is_file() and path.name not in EXCLUDED_BASENAMES:
                files.append(path)
    deduped: dict[str, Path] = {str(path): path for path in files}
    return sorted(deduped.values())


def main() -> int:
    issues: list[str] = []
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                issues.append(f"{path.relative_to(ROOT)} contains forbidden token {token!r}")

    if issues:
        print("[verify_prod_package_purity] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_prod_package_purity] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
