"""Go/Dart/Swift 生产源中 stable-code 字面量发射的扫描与注释剥离工具。"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Emission, ScanResult, _read
from .resolution import _dart_files, _go_files, _swift_files


def _strip_comments(text: str) -> str:
    """Strip // and /* */ comments while preserving quoted literals."""
    output: list[str] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if quote:
            output.append(char)
            if quote != "`" and escaped:
                escaped = False
            elif quote != "`" and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char in {'"', "'", "`"}:
            quote = char
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            end = text.find("\n", index + 2)
            if end < 0:
                break
            output.append("\n")
            index = end + 1
            continue
        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            if end < 0:
                break
            output.append("\n" * text[index : end + 2].count("\n"))
            index = end + 2
            continue
        output.append(char)
        index += 1
    return "".join(output)


_STABLE_CODE_LITERAL = re.compile(
    r"(?P<quote>['\"`])(?P<code>[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*)"
    r"(?P=quote)"
)


def _scan_stable_code_literals(root: Path, result: ScanResult) -> None:
    paths = [*_go_files(root), *_dart_files(root)]
    for path in paths:
        text = _strip_comments(_read(path))
        relative = path.relative_to(root).as_posix()
        is_app = relative.startswith("quwoquan_app/lib/")
        for match in _STABLE_CODE_LITERAL.finditer(text):
            prefix = text[max(0, match.start() - 100) : match.start()]
            line_prefix = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
            if is_app:
                if not re.search(
                    r"(?:failureCode|errorCode|code)\s*(?::|=)\s*$", prefix
                ):
                    continue
                form = "app_stable_code_emission"
            else:
                is_error_constructor = bool(
                    re.search(r"(?:errors\.New|NewCode|ParseCode)\(\s*$", prefix)
                )
                is_code_field = bool(
                    re.search(
                        r"(?:Code|ErrorCode|FailureCode)\s*:\s*(?:[^,]*,\s*)?$",
                        line_prefix,
                    )
                )
                is_code_map_value = bool(
                    re.search(r"['\"](?:code|errorCode|failureCode)['\"]\s*:\s*$", prefix)
                )
                is_returned_code = bool(re.search(r"\breturn\s*$", prefix))
                if not (
                    is_error_constructor
                    or is_code_field
                    or is_code_map_value
                    or is_returned_code
                ):
                    continue
                form = "stable_code_literal"
            result.emissions.append(
                Emission(
                    code=match.group("code"),
                    form=form,
                    path=relative,
                    function="<dart>" if is_app else "<literal>",
                )
            )


def _scan_swift_stable_code_emissions(root: Path, result: ScanResult) -> None:
    """Scan only production values assigned/passed as a native error code.

    A stable-code literal in a comment, allowlist, log string, or arbitrary
    constant is not emission evidence. Multiline ternaries are supported
    because the startup watchdog selects one of two canonical failure codes
    before passing the selected value to the telemetry journal.
    """
    assignment_prefix = re.compile(
        r"(?:let|var)\s+(?:failureCode|errorCode|code)\s*=\s*"
        r"(?:(?:[^\n;{}]*)\n\s*){0,4}[^;{}]*$"
    )
    argument_prefix = re.compile(r"(?:failureCode|errorCode|code)\s*:\s*$")
    for path in _swift_files(root):
        text = _strip_comments(_read(path))
        relative = path.relative_to(root).as_posix()
        for match in _STABLE_CODE_LITERAL.finditer(text):
            prefix = text[max(0, match.start() - 500) : match.start()]
            if assignment_prefix.search(prefix) is None and argument_prefix.search(prefix) is None:
                continue
            result.emissions.append(
                Emission(
                    code=match.group("code"),
                    form="app_native_stable_code_emission",
                    path=relative,
                    function="<swift>",
                )
            )
