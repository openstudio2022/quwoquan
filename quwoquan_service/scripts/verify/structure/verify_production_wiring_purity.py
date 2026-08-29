#!/usr/bin/env python3
"""阻断生产服务中的 test double、fixture 与静默降级。

判据是结构事实，不是命名：一个类型是不是替身，由「它声明在哪」「生产装配是否
真的依赖它」「文件是否带测试构建约束」决定，与类型名里有没有 `Memory` / `Mock`
无关。业务概念（如 assistant 长期记忆的 `MemoryProfile`、幂等命令的 `NoopReceipt`）
不因为撞词被判违规；真替身也不因为改名叫 `Store` 而漏判。

替身检测的三条判据：

* `TEST_ONLY_PACKAGE_SEGMENTS`：声明位置。Go/Python 都必须先 import 才能引用，
  因此「生产源码 import 了 test-only 包」对这两种语言既 sound 又 complete。
* `TEST_FRAMEWORK_IMPORTS`：测试框架与 mock 库是专有 API，判定对象本身就是这些
  包名，属于正当的文本规则。
* `TEST_BUILD_TAG`：构建约束是编译器可见的结构事实。

配置值（`mode: memory`）、特定已知 API（`NewFileStore(`）、特定字面量
(`*.invalid` URL) 这类判定对象本身就是文本，保留文本匹配。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root, require_scan_root  # noqa: E402

SERVICE_ROOT = require_scan_root(
    repository_root() / "quwoquan_service", "production-wiring-purity service root"
)

FORBIDDEN_SOURCE_PATTERNS = (
    re.compile(r'\bMode\s*:\s*"memory"'),
    re.compile(r"\bmode\s*:\s*memory\b", re.IGNORECASE),
    # File-backed control-plane state must remain physically unreachable from
    # every production composition root.
    re.compile(r"\bNewFileStore\s*\("),
)

# 声明位置：包路径里出现这些段，说明该包是测试专用装配面。
TEST_ONLY_PACKAGE_SEGMENTS = frozenset(
    {"testsupport", "testdata", "testkit", "testutil", "testdouble", "tests", "fixtures"}
)
# 测试框架与 mock 库：判定对象就是这些专有包名本身。
TEST_FRAMEWORK_IMPORTS = (
    "testing",
    "net/http/httptest",
    "github.com/stretchr/testify",
    "github.com/golang/mock",
    "go.uber.org/mock",
    "github.com/alicebob/miniredis",
    "unittest",
    "unittest.mock",
    "pytest",
    "mock",
)
TEST_BUILD_TAG = re.compile(
    r"(?m)^//\s*(?:go:build|\+build)\b.*\b(?:test|testing|fake|mock|stub)\b"
)
GO_IMPORT_BLOCK = re.compile(r"(?ms)^import\s*\((.*?)^\)")
GO_IMPORT_SINGLE = re.compile(r'(?m)^import\s+(?:[\w.]+\s+)?"([^"]+)"')
GO_IMPORT_PATH = re.compile(r'"([^"]+)"')
PY_IMPORT = re.compile(
    r"(?m)^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\b|import\s+([A-Za-z_][\w.]*))"
)
FORBIDDEN_API_PATTERNS = (
    re.compile(r"\b(?:DefaultSeed|Seed)[A-Za-z0-9_]*\s*\("),
)
FORBIDDEN_APPLICATION_PATTERNS = (
    re.compile(r"""["']https?://[^"']*\.invalid(?:[/:"']|$)"""),
)
FORBIDDEN_CONFIG_TOKENS = (
    "test_fixtures",
    "seedRefs",
    "requiresSeedReset",
    "prod-gray",
)
FORBIDDEN_CHAT_RETIRED_PATTERNS = (
    re.compile(r"/chat/media/uploads"),
    re.compile(r"\bChatMediaUpload[A-Za-z0-9_]*\b"),
    re.compile(r"\bchat_media_(?:upload_sessions|assets)\b"),
    re.compile(r'''["']conversation_members["']'''),
)


def _services_root() -> Path:
    return SERVICE_ROOT / "services"


def _is_production_source(path: Path) -> bool:
    if path.suffix not in {".go", ".py"}:
        return False
    if "tests" in path.parts or "testdata" in path.parts:
        return False
    if path.name.endswith("_test.go"):
        return False
    return not (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def _production_source_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for pattern in ("*.go", "*.py")
        for path in sorted(root.rglob(pattern))
        if _is_production_source(path)
    )


def _source_layer(path: Path) -> str | None:
    try:
        parts = path.relative_to(_services_root()).parts
    except ValueError:
        return None
    try:
        internal_index = parts.index("internal")
    except ValueError:
        return None
    if len(parts) <= internal_index + 3:
        return None
    layer = parts[internal_index + 3]
    if layer not in {"domain", "application", "adapters", "infrastructure"}:
        return None
    return layer


def _is_command_source(path: Path) -> bool:
    try:
        relative = path.relative_to(_services_root())
    except ValueError:
        return False
    return len(relative.parts) >= 3 and relative.parts[1] == "cmd"


def _imported_modules(path: Path, text: str) -> tuple[str, ...]:
    """文件真实声明的 import 边。Go 与 Python 都必须先 import 才能引用符号，

    所以这条边对「生产是否依赖测试装配」既充分又必要，不需要猜名字。
    """
    if path.suffix == ".go":
        modules: list[str] = []
        for block in GO_IMPORT_BLOCK.findall(text):
            modules.extend(GO_IMPORT_PATH.findall(block))
        modules.extend(GO_IMPORT_SINGLE.findall(text))
        return tuple(modules)
    return tuple(
        module for group in PY_IMPORT.findall(text) for module in group if module
    )


def _test_only_module(module: str) -> bool:
    separators = "/" if "/" in module else "."
    return any(
        segment in TEST_ONLY_PACKAGE_SEGMENTS for segment in module.split(separators)
    )


def _test_framework_module(module: str) -> bool:
    return any(
        module == framework or module.startswith(f"{framework}/")
        or module.startswith(f"{framework}.")
        for framework in TEST_FRAMEWORK_IMPORTS
    )


def _scan_substitute_reachability(
    path: Path, text: str, relative: str, scope: str, issues: list[str]
) -> None:
    """替身判定：声明位置 + 依赖边 + 构建约束，全部是结构事实，不看类型名。"""
    for module in _imported_modules(path, text):
        if _test_only_module(module):
            issues.append(
                f"{relative}: {scope}依赖测试专用包 {module!r}；"
                "生产装配不得引用 test 目录下声明的替身"
            )
        elif _test_framework_module(module):
            issues.append(
                f"{relative}: {scope}依赖测试框架/mock 库 {module!r}"
            )
    if TEST_BUILD_TAG.search(text):
        issues.append(f"{relative}: {scope}携带测试构建约束，不属于生产构建面")


def _scan_source_patterns(path: Path, layer: str | None, issues: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    relative = path.relative_to(SERVICE_ROOT).as_posix()
    if _is_command_source(path):
        patterns = FORBIDDEN_SOURCE_PATTERNS
        scope = "生产装配"
    elif layer in {"domain", "application", "adapters"}:
        patterns = FORBIDDEN_SOURCE_PATTERNS[:2]
        scope = f"{layer} 生产路径"
    else:
        return

    _scan_substitute_reachability(path, text, relative, scope, issues)

    for pattern in patterns:
        if pattern.search(text):
            issues.append(f"{relative}: {scope}命中 {pattern.pattern!r}")

    if path.parent.name == "api":
        for pattern in FORBIDDEN_API_PATTERNS:
            if pattern.search(text):
                issues.append(
                    f"{relative}: 生产 API 装配命中 {pattern.pattern!r}"
                )


def collect_issues() -> list[str]:
    issues: list[str] = []
    services_root = _services_root()
    for path in _production_source_files(services_root):
        layer = _source_layer(path)
        _scan_source_patterns(path, layer, issues)
        if layer in {"domain", "application", "adapters"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_APPLICATION_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                        f"{layer} 生产默认值命中 {pattern.pattern!r}"
                    )

    for path in sorted(
        services_root.glob("*/environments/*/config.yaml")
    ):
        environment = path.parent.name
        if environment not in {"beta", "gamma", "prod"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        if environment == "prod":
            for token in FORBIDDEN_CONFIG_TOKENS:
                if token.lower() in lowered:
                    issues.append(
                        f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                        f"prod 配置包含 {token!r}"
                    )
        for forbidden in ("mode: memory", "mode: noop", "mode: mock"):
            if forbidden in lowered:
                issues.append(
                    f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                    f"{environment} 配置包含 {forbidden!r}"
                )

    chat_root = services_root / "chat-service"
    chat_sources = [
        path
        for pattern in ("*.go", "*.py", "*.yaml")
        for path in chat_root.rglob(pattern)
        if path.suffix == ".yaml" or _is_production_source(path)
    ]
    for path in sorted(chat_sources):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_CHAT_RETIRED_PATTERNS:
            if pattern.search(text):
                issues.append(
                    f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                    f"Chat 退场路径命中 {pattern.pattern!r}"
                )
    return sorted(set(issues))


def main() -> int:
    issues = collect_issues()
    if issues:
        for issue in issues:
            print(f"[production-wiring-purity] FAIL: {issue}", file=sys.stderr)
        print(
            f"[production-wiring-purity] FAIL: 共 {len(issues)} 个生产纯度违规",
            file=sys.stderr,
        )
        return 1
    print(
        "[production-wiring-purity] OK: "
        "Go/Python 生产路径无 test double/fixture/FileStore/testsupport"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
