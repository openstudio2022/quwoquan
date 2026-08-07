#!/usr/bin/env python3
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-risky-config-gray-release/spec.md#gwt-001
"""验证服务运行时只消费自治包中的单一有效配置。"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "quwoquan_service"


def main() -> int:
    failures: list[str] = []

    config_path = SERVICE_ROOT / "runtime/configrelease/path.go"
    config_text = config_path.read_text(encoding="utf-8")
    required = ('filepath.Join(root, serviceName+".yaml")',)
    forbidden = (
        '"configs"',
        '"releases"',
        '"default"',
    )
    for token in required:
        if token not in config_text:
            failures.append(f"runtime config resolver missing canonical path: {token}")
    for token in forbidden:
        if token in config_text:
            failures.append(f"runtime config resolver retains layered path token: {token}")

    renderer = (ROOT / "quwoquan_ops/cli/render_runtime_config.py").read_text(
        encoding="utf-8"
    )
    for token in (
        'owner / "config/schema.yaml"',
        'owner / f"environments/{environment}/config.yaml"',
        'set_nested(rendered, "config.version", f"sha256:{digest}")',
    ):
        if token not in renderer:
            failures.append(f"runtime renderer missing single-track rule: {token}")

    packager = (
        ROOT / "quwoquan_service/scripts/runtime/packaging/build_service_env_package.sh"
    ).read_text(encoding="utf-8")
    for token in (
        '"$stage_dir/config/config.yaml"',
        'package / "provenance.json"',
        'config_version.startswith("sha256:")',
    ):
        if token not in packager:
            failures.append(f"service packager missing autonomous artifact: {token}")
    for token in ("configs/releases", "default_config.yaml", "release snapshot"):
        if token in packager:
            failures.append(f"service packager retains retired config layer: {token}")

    prod_renderer = (
        ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
    ).read_text(encoding="utf-8")
    for token in (
        'config_root / f"{service}.yaml"',
        'environment["CONFIG_VERSION"] = config_version',
    ):
        if token not in prod_renderer:
            failures.append(f"prod renderer missing effective config binding: {token}")
    for token in (
        'config_root / "releases" / "config"',
        'package_dir / "releases"',
    ):
        if token in prod_renderer:
            failures.append(f"prod renderer retains retired release snapshot path: {token}")

    snapshot_source = (
        SERVICE_ROOT
        / "control-plane/platform-ops/internal/ops/platform_ops/config_snapshot/application/platform_ops/config_layer/snapshot_source.go"
    ).read_text(encoding="utf-8")
    if 'filepath.Join(s.configRoot, service+".yaml")' not in snapshot_source:
        failures.append("platform ConfigSnapshot does not consume effective service config")
    if 'filepath.Join(s.configRoot, "releases", "config"' in snapshot_source:
        failures.append("platform ConfigSnapshot retains release directory lookup")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("OK: runtime config uses one service package snapshot with digest-derived CONFIG_VERSION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
