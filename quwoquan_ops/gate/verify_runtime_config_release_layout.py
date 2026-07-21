#!/usr/bin/env python3
"""阻断运行时配置根重新使用仓库形状的 release 路径。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "quwoquan_service" / "services"

# 发布包的 config-root 是独立、只读的运行时工件，不包含仓库目录层级。
# 这些模式一旦回归，prod 会在 CONFIG_VERSION 非空时读取不存在的文件。
LEGACY_GO_CONFIG_ROOT = re.compile(
    r'filepath\.Join\(\s*configRoot,\s*"quwoquan_service"\s*,',
    re.DOTALL,
)
LEGACY_PY_CONFIG_ROOT = re.compile(
    r'config_root\s*\)\s*/\s*"quwoquan_service"|'
    r'root\s*/\s*"quwoquan_service"',
    re.DOTALL,
)


def main() -> int:
    failures: list[str] = []

    for source in SERVICE_ROOT.rglob("*.go"):
        if source.name.endswith("_test.go"):
            continue
        content = source.read_text(encoding="utf-8")
        if LEGACY_GO_CONFIG_ROOT.search(content):
            failures.append(
                f"{source.relative_to(ROOT)} uses repository-shaped release path under CONFIG_ROOT"
            )

    rec_runtime = SERVICE_ROOT / "rec-model-service" / "runtime_contract.py"
    if LEGACY_PY_CONFIG_ROOT.search(rec_runtime.read_text(encoding="utf-8")):
        failures.append(
            f"{rec_runtime.relative_to(ROOT)} uses repository-shaped release path under CONFIG_ROOT"
        )

    renderer = (
        ROOT / "quwoquan_ops" / "cli" / "prod" / "render_prod_plane_stack.py"
    ).read_text(encoding="utf-8")
    if 'config_root / "releases" / "config" / service' not in renderer:
        failures.append(
            "prod renderer does not materialize releases/config/<service>/<version>.yaml"
        )

    snapshot_source = (
        SERVICE_ROOT
        / "platform-ops-service"
        / "internal"
        / "application"
        / "platform_ops"
        / "config_layer"
        / "snapshot_source.go"
    ).read_text(encoding="utf-8")
    if 'filepath.Join(s.configRoot, "releases", "config", service)' not in snapshot_source:
        failures.append(
            "platform ConfigSnapshot does not consume canonical runtime release path"
        )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(
        "OK: runtime CONFIG_ROOT and ConfigSnapshot consume the canonical "
        "releases/config/<service>/<version>.yaml layout"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
