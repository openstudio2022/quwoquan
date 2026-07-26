#!/usr/bin/env python3
"""阻断生产服务中的 test double、fixture 与静默降级。

`NoopReceipt` 是幂等命令在目标态已满足时必须持久化的正式领域值对象，
不是 Noop adapter；扫描器必须显式区分两者。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_SOURCE_PATTERNS = (
    re.compile(
        r"\b(?:New)?(?:InMemory|Memory|Noop(?!Receipt\b)|Mock|Stub|Fake)[A-Za-z0-9_]*\s*\("
    ),
    re.compile(
        r"\b(?:InMemory|Memory|Noop(?!Receipt\b)|Mock|Stub|Fake)[A-Za-z0-9_]*\s*\{"
    ),
    re.compile(r'\bMode\s*:\s*"memory"'),
    re.compile(r"\bmode\s*:\s*memory\b", re.IGNORECASE),
    # File-backed control-plane state and test adapters must remain physically
    # unreachable from every production composition root.
    re.compile(r"\bNewFileStore\s*\("),
    re.compile(r'"quwoquan_service/runtime/controlplane/testsupport"'),
)
FORBIDDEN_TEST_SYMBOL_PATTERN = re.compile(
    r"\b(?:New)?(?:InMemory|Memory|Noop(?!Receipt\b)|Mock|Stub|Fake|Fixture|"
    r"Test(?:Double|Fixture|Helper|Only)?)[A-Z_][A-Za-z0-9_]*\s*(?:\(|\{)"
)
FORBIDDEN_TEST_IMPORT_PATTERN = re.compile(
    r"(?im)^\s*(?:from|import)\s+.*\b(?:tests?|testsupport|testkit|"
    r"fixtures?|mocks?)\b"
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


def _scan_source_patterns(path: Path, layer: str | None, issues: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    relative = path.relative_to(SERVICE_ROOT).as_posix()
    if _is_command_source(path):
        patterns = FORBIDDEN_SOURCE_PATTERNS + (
            FORBIDDEN_TEST_SYMBOL_PATTERN,
            FORBIDDEN_TEST_IMPORT_PATTERN,
        )
        scope = "生产装配"
    elif layer in {"domain", "application", "adapters"}:
        patterns = FORBIDDEN_SOURCE_PATTERNS[:2] + (
            FORBIDDEN_TEST_SYMBOL_PATTERN,
            FORBIDDEN_TEST_IMPORT_PATTERN,
        )
        scope = f"{layer} 生产路径"
    else:
        return

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
