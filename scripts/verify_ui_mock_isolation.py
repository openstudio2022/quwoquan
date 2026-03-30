#!/usr/bin/env python3
"""
阻断 lib/ui、lib/app、lib/core 直接依赖 cloud/services/*/mock 或 UI 模型内嵌 prototype 域名行。

真相源：specs/gates/mock_data_cloud_integration_policy.md
豁免：specs/gates/ui_mock_isolation_allowlist.yaml（过渡期，只缩不扩）

用法（仓库根）:
  python3 scripts/verify_ui_mock_isolation.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOW = ROOT / "specs" / "gates" / "ui_mock_isolation_allowlist.yaml"

# package:quwoquan_app/.../mock/ 或 .../mock/xxx.dart
IMPORT_MOCK = re.compile(
    r"""import\s+['"]package:quwoquan_app/[^'"]*/mock/[^'"]*['"]\s*;"""
)
# 域名占位行（与 ChatContactsRow 等对齐）
PROTOTYPE_RE = re.compile(
    r"\bprototype(Circles|Groups)\b",
)


def _norm_rel_path(p: str) -> str:
    p = p.replace("\\", "/")
    if p.startswith("lib/"):
        return p[4:]
    return p


def load_allowed() -> set[tuple[str, str]]:
    if yaml is None or not ALLOW.is_file():
        return set()
    data = yaml.safe_load(ALLOW.read_text(encoding="utf-8")) or {}
    out: set[tuple[str, str]] = set()
    for row in data.get("allowed", []) or []:
        p = row.get("path")
        r = row.get("rule")
        if isinstance(p, str) and isinstance(r, str):
            out.add((_norm_rel_path(p), r))
    return out


def scan_dart_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.dart"))


def main() -> int:
    if yaml is None:
        print("BLOCK: PyYAML missing — pip install pyyaml or use CI image with yaml", file=sys.stderr)
        return 2

    allowed = load_allowed()
    errors: list[str] = []

    roots = [
        APP_LIB / "ui",
        APP_LIB / "app",
        APP_LIB / "core",
    ]
    for base in roots:
        for path in scan_dart_files(base):
            rel = path.relative_to(APP_LIB).as_posix()
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if IMPORT_MOCK.search(line):
                    key = (rel, "import_cloud_mock")
                    if key not in allowed:
                        errors.append(f"{rel}:{i}: 禁止 import cloud …/mock/（{line.strip()}）")
            # 仅扫描 UI 模型文件，避免 provider 引用 ChatContactsRow.prototype* 误报
            if "/models/" in rel and PROTOTYPE_RE.search(text):
                key = (rel, "embedded_prototype_rows")
                if key not in allowed:
                    errors.append(
                        f"{rel}: 禁止在 UI 模型中内嵌 prototypeCircles/prototypeGroups 等域名占位"
                    )

    if errors:
        print("ui_mock_isolation 校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"说明见: specs/gates/mock_data_cloud_integration_policy.md", file=sys.stderr)
        print(f"豁免仅来自: {ALLOW}（禁止为新增页面加行）", file=sys.stderr)
        return 1

    print("ui_mock_isolation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
