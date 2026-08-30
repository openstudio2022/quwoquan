#!/usr/bin/env python3
"""UAT 引用的 Widget key ↔ App 实现同源门禁。

user_acceptance 层跑的是真实 App，它断言的每个 `ValueKey` 都必须能在
`quwoquan_app/lib/**` 找到产出方。一旦实现侧删除或改名某个 key 而 UAT 仍引用
旧字面量，`find.byKey` 只会永远 findsNothing——测试要么在等待里超时，要么
在「不存在即通过」的断言方向上把删除锁成正确行为。首页搜索与小趣入口被删
三个月无人发现，就是这样发生的：8 个 UAT 文件引用 `home-search-chrome`，
而实现侧早已没有这个 key。

真相源是两侧的实际代码（UAT 的 key 字面量 + lib 的 key 产出），实时扫描派生，
不建立第二份 key 注册表。

动态 key（`'home-feed-card-$index'`）在 lib 侧是插值模板，UAT 侧是具体值
（`home-feed-card-0`）。这类按模板前缀匹配，避免为了过闸把动态 key 写死。
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

APP_ROOT = REPO_ROOT / "quwoquan_app"
LIB_ROOT = APP_ROOT / "lib"
# UAT 与 patrol support：跑真实 App，不注入自有 widget，因此引用的 key 必须实存。
UAT_ROOTS = (
    APP_ROOT / "test" / "user_acceptance",
    APP_ROOT / "test" / "support" / "runtime" / "patrol",
)

# UAT 侧 key 字面量：ValueKey<String>('x') / ValueKey('x') / Key('x')。
_UAT_KEY = re.compile(r"""\b(?:Value)?Key(?:<String>)?\(\s*(['"])([^'"$]+)\1\s*\)""")
# lib 侧字符串字面量（含插值模板，用于派生动态 key 前缀）。
_LIB_STRING = re.compile(r"""(['"])((?:[^'"\\\n]|\\.)*)\1""")


def _dart_sources(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.dart") if path.is_file())


def _lib_key_universe() -> tuple[set[str], list[str]]:
    """返回 (lib 中出现的完整字符串集合, 插值模板的静态前缀列表)。"""
    literals: set[str] = set()
    prefixes: list[str] = []
    for source in _dart_sources(LIB_ROOT):
        text = source.read_text(encoding="utf-8")
        for _, value in _LIB_STRING.findall(text):
            if "$" in value:
                prefix = value.split("$", 1)[0]
                # 只有足够长的前缀才有区分度，避免 '$x' 这类前缀放行一切。
                if len(prefix) >= 4:
                    prefixes.append(prefix)
                continue
            literals.add(value)
    return literals, prefixes


def _uat_key_references() -> dict[str, list[str]]:
    """key 字面量 → 引用它的 UAT 文件（仓库相对路径）。"""
    references: dict[str, list[str]] = {}
    for root in UAT_ROOTS:
        if not root.exists():
            continue
        for source in _dart_sources(root):
            text = source.read_text(encoding="utf-8")
            relative = source.relative_to(REPO_ROOT).as_posix()
            for _, key in _UAT_KEY.findall(text):
                references.setdefault(key, [])
                if relative not in references[key]:
                    references[key].append(relative)
    return references


def _is_produced(key: str, literals: set[str], prefixes: list[str]) -> bool:
    if key in literals:
        return True
    return any(key.startswith(prefix) for prefix in prefixes)


def main() -> int:
    literals, prefixes = _lib_key_universe()
    references = _uat_key_references()
    dangling = {
        key: files
        for key, files in references.items()
        if not _is_produced(key, literals, prefixes)
    }
    if dangling:
        print("FAIL: UAT widget key references")
        for key, files in sorted(dangling.items()):
            print(f"  - '{key}' is referenced by UAT but no lib source produces it")
            for file in files:
                print(f"      {file}")
        print(
            "  Repair: 恢复实现侧 key，或把 UAT 改到当前实现真实产出的 key；"
            "不要靠 findsNothing 把删除锁成正确行为。"
        )
        return 1
    print("PASS: UAT widget key references")
    print(
        f"  - {len(references)} distinct keys referenced by user_acceptance "
        f"all resolve to lib sources"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
