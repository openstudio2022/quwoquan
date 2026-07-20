#!/usr/bin/env python3
"""校验受 Git 跟踪 Markdown 中的仓内相对链接。"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*]\(([^)\n]+)\)")
FENCED_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:")
URI_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _tracked_markdown_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.md", "*.mdc"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / value.decode("utf-8", errors="surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    ]


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        target = target.split(" ", 1)[0]
    return unquote(target).split("#", 1)[0].split("?", 1)[0]


def markdown_link_issues() -> list[str]:
    issues: list[str] = []
    for source in _tracked_markdown_paths():
        if (
            not source.is_file()
            or source.is_relative_to(ROOT / "quwoquan_app/vendor")
        ):
            continue
        raw_text = source.read_text(encoding="utf-8")
        text = FENCED_BLOCK_PATTERN.sub(
            lambda match: "\n" * match.group(0).count("\n"),
            raw_text,
        )
        for match in MARKDOWN_LINK_PATTERN.finditer(text):
            target = _link_target(match.group(1))
            if (
                not target
                or target.startswith(("#", "/", *SCHEMES))
                or URI_SCHEME_PATTERN.match(target)
                or any(marker in target for marker in ("${", "{{", "<path>"))
            ):
                continue
            destination = (source.parent / target).resolve()
            try:
                destination.relative_to(ROOT)
            except ValueError:
                continue
            if destination.exists() or (ROOT / target).exists():
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            issues.append(
                f"{source.relative_to(ROOT)}:{line_number}: "
                f"missing local link target {target}"
            )
    return issues


def main() -> int:
    issues = markdown_link_issues()
    if issues:
        print("[verify_markdown_local_links] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_markdown_local_links] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
