#!/usr/bin/env python3
"""Root layout gate: quwoquan_data 根层目录 allowlist + scripts/tests 根平铺 ratchet.

- quwoquan_data 根层 tracked 条目必须在目录规范 allowlist 内
  （object-homepage-coverage-scaling/design.md 仓内层规范），禁止新开根层目录/平铺文件；
- 禁止 quwoquan_data/scripts/ 与 quwoquan_data/tests/ 根层级再次出现业务平铺文件。
  允许 scripts/ 根仅保留 cli.py；tests/ 根仅保留 conftest.py。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.paths import DATA_ROOT as _DATA_ROOT  # noqa: E402

ALLOWED_SCRIPT_ROOT_FILES = {"cli.py"}
ALLOWED_TEST_ROOT_FILES = {"conftest.py"}

# quwoquan_data 根层 tracked 目录规范（与 object-homepage-coverage-scaling/design.md 同源）。
ALLOWED_TRACKED_ROOT_DIRS = {
    "control_plane",  # 可复用 families、catalogs、governance policy 与 runtime profile
    "prompts",        # 提示词模板库
    "publish",        # canonical approved 对象真相源
    "reference",      # 长期静态参考数据（行政区划等）
    "schema",         # JSON schema 契约
    "scripts",        # 唯一 CLI 与能力实现
    "templates",      # 内容层可复用模板库
    "tests",          # 测试
    "verticals",      # 垂类资产（coverage/rights 等）
}
ALLOWED_TRACKED_ROOT_FILES = {"AGENTS.md", "README.md", "requirements.txt"}


def _tracked_root_entries() -> set[str]:
    """git 视角的仓内根层条目（运行期目录如 runtime/release 不在其列）。"""
    result = subprocess.run(
        ["git", "ls-files", "--", "."],
        cwd=DATA_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    entries: set[str] = set()
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        # 本地清债过程中，已删除但未暂存的历史 tracked 文件仍会出现在
        # git ls-files 中；目录门按当前工作树验证，提交后这些路径会从索引消失。
        if not (DATA_ROOT / rel).exists():
            continue
        entries.add(rel.split("/", 1)[0])
    return entries


def verify_no_flat_roots() -> list[str]:
    issues: list[str] = []
    allowed_root = ALLOWED_TRACKED_ROOT_DIRS | ALLOWED_TRACKED_ROOT_FILES
    for entry in sorted(_tracked_root_entries()):
        if entry not in allowed_root:
            issues.append(
                f"data root entry not in layout allowlist: quwoquan_data/{entry}"
                "（新增根层目录/文件须先改 object-homepage-coverage-scaling/design.md 与目录合同）"
            )
    scripts_root = _DATA_ROOT / "scripts"
    tests_root = _DATA_ROOT / "tests"
    if scripts_root.is_dir():
        for path in sorted(scripts_root.glob("*.py")):
            if path.name not in ALLOWED_SCRIPT_ROOT_FILES:
                issues.append(f"scripts root flat file: {path.relative_to(_DATA_ROOT)}")
    if tests_root.is_dir():
        for path in sorted(tests_root.glob("*.py")):
            if path.name not in ALLOWED_TEST_ROOT_FILES:
                issues.append(f"tests root flat file: {path.relative_to(_DATA_ROOT)}")
    return issues


def main() -> None:
    issues = verify_no_flat_roots()
    if issues:
        print("[verify-flat-roots] FAILED: root-level flat files remain", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[verify-flat-roots] PASSED")


if __name__ == "__main__":
    main()
