#!/usr/bin/env python3
"""阻断生产服务装配中的 Memory/Noop/Mock 与静默降级。

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


def collect_issues() -> list[str]:
    issues: list[str] = []
    for cmd_dir in sorted((SERVICE_ROOT / "services").glob("*/cmd")):
        for path in sorted(cmd_dir.rglob("*.go")):
            if path.name.endswith("_test.go"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_SOURCE_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                        f"生产装配命中 {pattern.pattern!r}"
                    )
            if path.parent.name == "api":
                for pattern in FORBIDDEN_API_PATTERNS:
                    if pattern.search(text):
                        issues.append(
                            f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                            f"生产 API 装配命中 {pattern.pattern!r}"
                        )

    for layer_dir in sorted((SERVICE_ROOT / "services").glob("*/internal/*")):
        layer = layer_dir.name
        if layer not in {"domain", "application", "adapters"}:
            continue
        for path in sorted(layer_dir.rglob("*.go")):
            if path.name.endswith("_test.go"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_SOURCE_PATTERNS[:2]:
                if pattern.search(text):
                    issues.append(
                        f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                        f"{layer} 生产路径命中 {pattern.pattern!r}"
                    )
            for pattern in FORBIDDEN_APPLICATION_PATTERNS:
                if pattern.search(text):
                    issues.append(
                        f"{path.relative_to(SERVICE_ROOT).as_posix()}: "
                        f"{layer} 生产默认值命中 {pattern.pattern!r}"
                    )

    for path in sorted(
        (SERVICE_ROOT / "services").glob("*/configs/*/config.yaml")
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

    chat_root = SERVICE_ROOT / "services" / "chat-service"
    chat_sources = list(chat_root.rglob("*.go")) + list(chat_root.rglob("*.yaml"))
    for path in sorted(chat_sources):
        if path.name.endswith("_test.go"):
            continue
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
        "服务生产装配无 Memory/Noop/Mock/FileStore/testsupport"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
