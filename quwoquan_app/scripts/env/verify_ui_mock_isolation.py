#!/usr/bin/env python3
"""
阻断 production lib 对 Mock、fixture runtime helper 与 UI prototype 域名行的依赖。

规格：feature-tree 的 app-cloud-business-object-commercial-closure REQ-004。
豁免：quwoquan_ops/policies/gates/ui_mock_isolation_allowlist.yaml（过渡期，只缩不扩）。

用法（仓库根）:
  python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
ALLOW = ROOT / "quwoquan_ops" / "policies" / "gates" / "ui_mock_isolation_allowlist.yaml"
PRODUCTION_SERVICE_MOCK_ROOT = APP_LIB / "cloud" / "services"
RETIRED_PRODUCTION_FIXTURE_TOKENS = (
    "contract_fixture_runtime_loader",
    "prefab_user_resolver",
    "mock_session_identity",
    "kMockCurrentOwnerId",
    "kMockCurrentSubAccountId",
    "PrefabUserMetadata",
    "prefab_user_metadata",
    "prefab_user_provenance",
    "QWQ_REPO_ROOT",
    "contract_fixtures",
    "test_fixtures",
    "fixture_user_",
    "fixture_persona_",
)

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

    # 生产 lib 不得保留业务 Mock 源文件。alpha/test 必须转入独立 mock package，
    # 不能只靠 import allowlist 或 tree-shaking 隐藏可达实现。
    if PRODUCTION_SERVICE_MOCK_ROOT.is_dir():
        for path in sorted(PRODUCTION_SERVICE_MOCK_ROOT.glob("**/mock/*.dart")):
            rel = path.relative_to(APP_LIB).as_posix()
            errors.append(
                f"{rel}: production lib 禁止保留 cloud/services/*/mock 源文件"
            )

    # P0: production lib（包括 generated）不能通过运行时 loader / resolver、
    # mock identity、环境变量或仓库相对路径读取 fixture，也不得承载 fixture
    # user/persona 数据。alpha runner、Mock package 和 test/support 不在 APP_LIB，
    # 因而只能在这些物理隔离目录持有 fixture 读取逻辑。
    for path in scan_dart_files(APP_LIB):
        rel = path.relative_to(APP_LIB).as_posix()
        text = path.read_text(encoding="utf-8")
        for token in RETIRED_PRODUCTION_FIXTURE_TOKENS:
            if token in text:
                errors.append(
                    f"{rel}: production lib 禁止 fixture/Mock runtime token {token!r}"
                )

    # lib/cloud 纳入扫描（B2）：production adapter/provider 同样禁止 import
    # …/mock/ 本体；mock 承接只允许 test/support 与 runners/alpha。
    roots = [
        APP_LIB / "ui",
        APP_LIB / "app",
        APP_LIB / "core",
        APP_LIB / "cloud",
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
        print("说明见 app-cloud-business-object-commercial-closure REQ-004", file=sys.stderr)
        print(f"豁免仅来自: {ALLOW}（禁止为新增页面加行）", file=sys.stderr)
        return 1

    print("ui_mock_isolation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
