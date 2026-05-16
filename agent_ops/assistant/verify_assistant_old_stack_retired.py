#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

SCAN_PATHS = [
    ROOT / "quwoquan_app" / "lib",
    ROOT / "quwoquan_app" / "test",
    ROOT / "quwoquan_app" / "tool",
    ROOT / "quwoquan_app" / "pubspec.yaml",
    ROOT / "scripts",
    ROOT / ".github" / "workflows",
    ROOT / "quwoquan_service" / "contracts" / "metadata" / "assistant",
    ROOT / "quwoquan_service" / "services" / "assistant-service",
    ROOT / "quwoquan_service" / "tools" / "codegen_app_metadata",
]

RETIRED_PATHS = [
    ROOT / "quwoquan_app" / "lib" / "ui" / "assistant" / "pages" / "assistant_conversation_page.dart",
    ROOT / "quwoquan_app" / "lib" / "ui" / "assistant" / "providers" / "assistant_conversation_controller.dart",
    ROOT / "quwoquan_app" / "lib" / "assistant" / "application" / "local_assistant_entry.dart",
    ROOT / "quwoquan_app" / "lib" / "assistant" / "infrastructure" / "openclaw_bridge.dart",
    ROOT / "quwoquan_app" / "lib" / "assistant" / "application" / "assistant_http_gateway.dart",
    ROOT / "quwoquan_app" / "lib" / "assistant" / "api" / "assistant_api_gateway.dart",
    ROOT / "quwoquan_app" / "assistant" / "docs",
    ROOT / "quwoquan_app" / "assistant" / "scripts",
    ROOT / "quwoquan_app" / "assets" / "assistant" / "prompts",
    ROOT / "quwoquan_app" / "assets" / "assistant" / "skills",
    ROOT / "quwoquan_app" / "assets" / "assistant" / "tools",
]

BLOCKED_PATTERNS = [
    re.compile(r"\bAssistantConversationPage\b"),
    re.compile(r"\bAssistantConversationController\b"),
    re.compile(r"\bCreateRunStream\b"),
    re.compile(r"\bCreateRun\b"),
    re.compile(r"assistant_conversation_controller\.dart"),
    re.compile(r"local_assistant_entry\.dart"),
    re.compile(r"openclaw_bridge\.dart"),
    re.compile(r"assistant_http_gateway\.dart"),
    re.compile(r"assistant_api_gateway\.dart"),
    re.compile(r"PERSONAL_ASSISTANT_OPENCLAW_"),
    re.compile(r"PERSONAL_ASSISTANT_ENABLE_API"),
    re.compile(r"assets/assistant/prompts/"),
    re.compile(r"assets/assistant/skills/"),
    re.compile(r"assets/assistant/tools/"),
]


def _iter_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*") if item.is_file())


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    failures: list[str] = []

    for path in RETIRED_PATHS:
        if path.exists():
            failures.append(
                f"[assistant-old-stack] retired path still exists: {path.relative_to(ROOT)}"
            )

    for scan_path in SCAN_PATHS:
        for file_path in _iter_files(scan_path):
            if file_path == SELF:
                continue
            text = _read_text(file_path)
            if text is None:
                continue
            rel = file_path.relative_to(ROOT)
            for line_no, line in enumerate(text.splitlines(), start=1):
                for pattern in BLOCKED_PATTERNS:
                    if pattern.search(line):
                        failures.append(
                            f"[assistant-old-stack] blocked token in {rel}:{line_no}: {line.strip()}"
                        )
                        break

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1

    print("[assistant-old-stack] OK: retired assistant stack stays removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
