from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


class ShellCommandParseError(ValueError):
    pass


@dataclass(frozen=True)
class ShellCommand:
    argv: tuple[str, ...]
    separator_before: str
    subshell_depth: int
    function_scope: tuple[str, ...] = ()
    function_definition_scope: tuple[int, ...] = ()
    brace_depth: int = 0


@dataclass(frozen=True)
class _ShellCommandSpan:
    command: ShellCommand
    start_index: int
    end_index: int


@dataclass(frozen=True)
class _Heredoc:
    delimiter: str
    strip_tabs: bool


_PUNCTUATION = ";&|()<>\n"
_MULTI_OPERATORS = (
    ";;&",
    "<<<",
    "&&",
    "||",
    ";;",
    ";&",
    "<<",
    ">>",
    "&>",
    "<>",
    ">|",
)
_COMMAND_BOUNDARIES = {
    "\n",
    ";",
    ";;",
    ";&",
    ";;&",
    "&&",
    "||",
    "|",
    "&",
    "(",
    ")",
    "{",
    "}",
}
_SHELL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def parse_shell_commands(shell_text: str) -> tuple[ShellCommand, ...]:
    return _commands_from_tokens(_shell_tokens(shell_text))


def reachable_shell_command_tokens(
    shell_text: str,
    *,
    command_prefix: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    spans = _command_spans(_shell_tokens(shell_text))
    return tuple(
        span.command.argv
        for span in spans
        if span.command.argv[: len(command_prefix)] == command_prefix
        and _is_definitely_reached_top_level(spans, span)
    )


def reachable_dispatched_shell_commands(shell_text: str) -> tuple[ShellCommand, ...]:
    tokens = _shell_tokens(shell_text)
    spans = _command_spans(tokens)
    definitions = _top_level_function_definitions(tokens)
    unique_definitions = {
        name: items[0] for name, items in definitions.items() if len(items) == 1
    }
    dispatched: set[int] = set()
    for name, definition_id in unique_definitions.items():
        if any(
            span.command.argv == (name,)
            and _is_definitely_reached_top_level(spans, span)
            for span in spans
        ) or _function_is_reached_from_top_level_case(
            tokens,
            spans,
            function_name=name,
        ):
            dispatched.add(definition_id)

    reachable: list[ShellCommand] = []
    for span in spans:
        command = span.command
        if not command.function_scope:
            if _is_definitely_reached_top_level(spans, span):
                reachable.append(command)
            continue
        if (
            len(command.function_definition_scope) == 1
            and command.function_definition_scope[0] in dispatched
            and _is_reachable_in_dispatched_function(tokens, spans, span)
        ):
            reachable.append(command)
    return tuple(reachable)


def unique_top_level_shell_function_identity(
    shell_text: str,
    *,
    function_name: str,
) -> int | None:
    if _SHELL_NAME.fullmatch(function_name) is None:
        raise ShellCommandParseError("function name is not a shell identifier")
    definitions = _top_level_function_definitions(_shell_tokens(shell_text)).get(
        function_name, ()
    )
    return definitions[0] if len(definitions) == 1 and definitions[0] >= 0 else None


def shell_case_dispatches_function(
    shell_text: str,
    *,
    variable: str,
    function_name: str,
    required_labels: tuple[str, ...],
) -> bool:
    if _SHELL_NAME.fullmatch(variable) is None:
        raise ShellCommandParseError("case variable is not a shell identifier")
    if _SHELL_NAME.fullmatch(function_name) is None:
        raise ShellCommandParseError("function name is not a shell identifier")
    tokens = _shell_tokens(shell_text)
    spans = _command_spans(tokens)
    definition_identity = unique_top_level_shell_function_identity(
        shell_text,
        function_name=function_name,
    )
    if definition_identity is None:
        return False
    case_headers = [
        span
        for span in spans
        if span.command.argv == ("case", f"${variable}", "in")
        and not span.command.function_scope
        and span.command.subshell_depth == 0
        and _control_depth_before(spans, stop_index=span.start_index) == 0
        and not _sequence_definitely_terminates(
            spans,
            start_index=0,
            stop_index=span.start_index,
        )
        and definition_identity < span.start_index
    ]
    matching_cases = 0
    for header in case_headers:
        branches = _case_branches(tokens, start_index=header.end_index)
        if branches is None:
            continue
        if all(
            (bounds := branches.get(label)) is not None
            and _branch_directly_calls(
                spans,
                bounds=bounds,
                function_name=function_name,
            )
            for label in required_labels
        ):
            matching_cases += 1
    return matching_cases == 1


def _control_depth_before(
    spans: tuple[_ShellCommandSpan, ...],
    *,
    stop_index: int,
) -> int:
    controls: list[str] = []
    for span in spans:
        if span.start_index >= stop_index:
            break
        command = span.command.argv[0] if span.command.argv else ""
        if command in {"if", "for", "while", "until", "select", "case"}:
            controls.append(command)
        elif command in {"fi", "done", "esac"} and controls:
            controls.pop()
    return len(controls)


def reachable_shell_array_tokens(
    shell_text: str,
    *,
    array_name: str,
    consumer_prefix: tuple[str, ...],
) -> tuple[str, ...]:
    from quwoquan_ops.gate.local_dependency_purity.shell_arrays import (
        project_reachable_shell_array_tokens,
    )

    return project_reachable_shell_array_tokens(
        shell_text,
        array_name=array_name,
        consumer_prefix=consumer_prefix,
    )


def _shell_tokens(shell_text: str) -> tuple[str, ...]:
    projected = _without_shell_comments(_without_heredoc_bodies(shell_text))
    lexer = shlex.shlex(
        _collapse_line_continuations(projected),
        posix=True,
        punctuation_chars=_PUNCTUATION,
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        raw_tokens = list(lexer)
    except ValueError as error:
        raise ShellCommandParseError(str(error)) from error
    return tuple(
        projected
        for raw_token in raw_tokens
        for projected in _split_punctuation(raw_token)
    )


def _case_branches(
    tokens: tuple[str, ...],
    *,
    start_index: int,
) -> dict[str, tuple[int, int]] | None:
    branches: dict[str, tuple[int, int]] = {}
    index = start_index
    while index < len(tokens):
        while index < len(tokens) and tokens[index] in {"\n", ";;"}:
            index += 1
        if index >= len(tokens) or tokens[index] == "esac":
            return branches if index < len(tokens) else None
        labels = [tokens[index]]
        while index + 1 < len(tokens) and tokens[index + 1] == "|":
            if index + 2 >= len(tokens):
                return None
            labels.append(tokens[index + 2])
            index += 2
        if index + 1 >= len(tokens) or tokens[index + 1] != ")":
            return None
        if any(label in branches for label in labels):
            return None
        body_start = index + 2
        depth = 0
        index = body_start
        while index < len(tokens):
            token = tokens[index]
            if token == "case":
                depth += 1
            elif token == "esac":
                if depth == 0:
                    return None
                depth -= 1
            elif token == ";;" and depth == 0:
                for label in labels:
                    branches[label] = (body_start, index)
                index += 1
                break
            index += 1
        else:
            return None
    return None


def _branch_directly_calls(
    spans: tuple[_ShellCommandSpan, ...],
    *,
    bounds: tuple[int, int],
    function_name: str,
) -> bool:
    start, end = bounds
    controls: list[tuple[str, bool | None]] = []
    previous_status: bool | None = None
    for span in spans:
        if span.start_index < start:
            continue
        if span.start_index >= end:
            break
        argv, control_changed = _project_control_argv(span.command.argv, controls)
        if control_changed:
            previous_status = None
        if not argv:
            continue
        if not argv or span.command.function_scope or span.command.subshell_depth:
            continue
        if any(active is False for _, active in controls):
            continue
        execution = _command_execution(
            separator=span.command.separator_before,
            previous_status=previous_status,
        )
        if execution is False:
            continue
        if (
            argv == (function_name,)
            and execution is True
            and span.command.separator_before in {"\n", ";", ")"}
            and not _is_pipeline_or_background_member(spans, span)
        ):
            return True
        if (
            _is_shell_terminator(argv)
            and execution is True
            and all(active is True for _, active in controls)
        ):
            return False
        previous_status = _known_command_status(argv) if execution is True else None
    return False


def _sequence_definitely_terminates(
    spans: tuple[_ShellCommandSpan, ...],
    *,
    start_index: int,
    stop_index: int,
) -> bool:
    controls: list[tuple[str, bool | None]] = []
    previous_status: bool | None = None
    for span in spans:
        if span.start_index < start_index:
            continue
        if span.start_index >= stop_index:
            break
        argv, control_changed = _project_control_argv(span.command.argv, controls)
        if control_changed:
            previous_status = None
        if not argv:
            continue
        if not argv or span.command.function_scope or span.command.subshell_depth:
            continue
        if any(active is False for _, active in controls):
            continue
        execution = _command_execution(
            separator=span.command.separator_before,
            previous_status=previous_status,
        )
        if execution is False:
            continue
        if (
            _is_shell_terminator(argv)
            and execution is True
            and all(active is True for _, active in controls)
        ):
            return True
        previous_status = _known_command_status(argv) if execution is True else None
    return False


def _command_execution(
    *,
    separator: str,
    previous_status: bool | None,
) -> bool | None:
    if separator == "&&":
        return previous_status
    if separator == "||":
        return None if previous_status is None else not previous_status
    return True


def _project_control_argv(
    argv: tuple[str, ...],
    controls: list[tuple[str, bool | None]],
) -> tuple[tuple[str, ...], bool]:
    name = argv[0] if argv else ""
    if name == "if":
        controls.append((name, _known_command_status(argv[1:])))
        return (), True
    if name in {"for", "while", "until", "select", "case"}:
        controls.append((name, None))
        return (), True
    if name == "else" and controls and controls[-1][0] == "if":
        kind, active = controls[-1]
        controls[-1] = (kind, None if active is None else not active)
        return argv[1:], True
    if name in {"then", "do"}:
        return argv[1:], False
    if name in {"fi", "done", "esac"}:
        if controls:
            controls.pop()
        return (), True
    return argv, False


def _known_command_status(argv: tuple[str, ...]) -> bool | None:
    if argv in {("true",), (":",)}:
        return True
    if argv == ("false",):
        return False
    return None


def _is_shell_terminator(argv: tuple[str, ...]) -> bool:
    return bool(argv) and argv[0] in {"exit", "return"}


def _is_definitely_reached_top_level(
    spans: tuple[_ShellCommandSpan, ...],
    target: _ShellCommandSpan,
) -> bool:
    command = target.command
    if command.function_scope or command.subshell_depth:
        return False
    if _is_pipeline_or_background_member(spans, target):
        return False
    controls: list[tuple[str, bool | None]] = []
    previous_status: bool | None = None
    for span in spans:
        if span.start_index > target.start_index:
            break
        current = span.command
        if current.function_scope or current.subshell_depth:
            continue
        if span is target:
            return (
                not controls
                and _command_execution(
                    separator=current.separator_before,
                    previous_status=previous_status,
                )
                is True
            )
        argv, control_changed = _project_control_argv(current.argv, controls)
        if control_changed:
            previous_status = None
        if not argv:
            continue
        if not argv or any(active is False for _, active in controls):
            continue
        execution = _command_execution(
            separator=current.separator_before,
            previous_status=previous_status,
        )
        if (
            execution is True
            and _is_shell_terminator(argv)
            and all(active is True for _, active in controls)
        ):
            return False
        previous_status = _known_command_status(argv) if execution is True else None
    return False


def _function_is_reached_from_top_level_case(
    tokens: tuple[str, ...],
    spans: tuple[_ShellCommandSpan, ...],
    *,
    function_name: str,
) -> bool:
    for header in spans:
        if (
            header.command.argv[:1] != ("case",)
            or header.command.function_scope
            or header.command.subshell_depth
            or _sequence_definitely_terminates(
                spans,
                start_index=0,
                stop_index=header.start_index,
            )
        ):
            continue
        branches = _case_branches(tokens, start_index=header.end_index)
        if branches is not None and any(
            _branch_directly_calls(
                spans,
                bounds=bounds,
                function_name=function_name,
            )
            for bounds in branches.values()
        ):
            return True
    return False


def _is_reachable_in_dispatched_function(
    tokens: tuple[str, ...],
    spans: tuple[_ShellCommandSpan, ...],
    target: _ShellCommandSpan,
) -> bool:
    if (
        _is_pipeline_or_background_member(spans, target)
        or _static_case_excludes_target(tokens, spans, target)
        or _static_group_skips_target(tokens, spans, target)
    ):
        return False
    identity = target.command.function_definition_scope
    previous_status: bool | None = None
    controls: list[tuple[str, bool | None]] = []
    for span in spans:
        current = span.command
        if current.function_definition_scope != identity:
            continue
        if span is target:
            if any(active is False for _, active in controls):
                return False
            execution = _command_execution(
                separator=current.separator_before,
                previous_status=previous_status,
            )
            return execution is not False
        argv, control_changed = _project_control_argv(current.argv, controls)
        if control_changed:
            previous_status = None
        if not argv:
            continue
        if not argv or any(active is False for _, active in controls):
            continue
        execution = _command_execution(
            separator=current.separator_before,
            previous_status=previous_status,
        )
        if (
            all(active is True for _, active in controls)
            and not current.subshell_depth
            and current.brace_depth == len(identity)
            and execution is True
            and _is_shell_terminator(argv)
        ):
            return False
        previous_status = _known_command_status(argv) if execution is True else None
    return False


def _is_pipeline_or_background_member(
    spans: tuple[_ShellCommandSpan, ...],
    target: _ShellCommandSpan,
) -> bool:
    if target.command.separator_before in {"|", "&"}:
        return True
    for index, span in enumerate(spans):
        if span is target and index + 1 < len(spans):
            return spans[index + 1].command.separator_before in {"|", "&"}
    return False


def _static_case_excludes_target(
    tokens: tuple[str, ...],
    spans: tuple[_ShellCommandSpan, ...],
    target: _ShellCommandSpan,
) -> bool:
    """Reject targets in a statically non-matching literal ``case`` branch."""

    for header in spans:
        if (
            header.command.function_definition_scope
            != target.command.function_definition_scope
            or header.command.argv[:1] != ("case",)
            or len(header.command.argv) != 3
            or header.command.argv[2] != "in"
            or header.start_index >= target.start_index
        ):
            continue
        value = header.command.argv[1]
        if value.startswith("$"):
            continue
        branches = _case_branches(tokens, start_index=header.end_index)
        if branches is None:
            continue
        containing = [
            label
            for label, (start, end) in branches.items()
            if start <= target.start_index < end
        ]
        if containing and value not in containing and "*" not in containing:
            return True
    return False


def _static_group_skips_target(
    tokens: tuple[str, ...],
    spans: tuple[_ShellCommandSpan, ...],
    target: _ShellCommandSpan,
) -> bool:
    if target.command.subshell_depth == 0:
        return False
    openings: list[int] = []
    for index, token in enumerate(tokens[: target.start_index]):
        if token == "(":
            openings.append(index)
        elif token == ")" and openings:
            openings.pop()
    for opening in reversed(openings):
        if opening == 0 or tokens[opening - 1] not in {"&&", "||"}:
            continue
        previous = next(
            (
                span
                for span in reversed(spans)
                if span.end_index <= opening - 1
                and span.command.function_definition_scope
                == target.command.function_definition_scope
            ),
            None,
        )
        if previous is None:
            continue
        status = _known_command_status(previous.command.argv)
        if (tokens[opening - 1] == "&&" and status is False) or (
            tokens[opening - 1] == "||" and status is True
        ):
            return True
    return False


def _without_heredoc_bodies(shell_text: str) -> str:
    """Blank heredoc bodies while preserving raw physical-line semantics."""

    output: list[str] = []
    pending: list[_Heredoc] = []
    active: list[_Heredoc] = []
    quote = ""
    for line in shell_text.splitlines(keepends=True):
        if active:
            heredoc = active[0]
            content = _line_content(line)
            candidate = content.lstrip("\t") if heredoc.strip_tabs else content
            if candidate == heredoc.delimiter:
                active.pop(0)
            output.append(_blank_line(line))
            continue

        output.append(line)
        declarations, quote, escaped_newline = _heredocs_on_line(line, quote=quote)
        pending.extend(declarations)
        if not quote and not escaped_newline and pending:
            active = pending
            pending = []

    if active:
        raise ShellCommandParseError(f"heredoc {active[0].delimiter!r} is unterminated")
    if pending:
        raise ShellCommandParseError(f"heredoc {pending[0].delimiter!r} has no body")
    return "".join(output)


def _without_shell_comments(shell_text: str) -> str:
    """Remove real shell comments without consuming ``#`` inside shell words."""

    output: list[str] = []
    quote = ""
    for line in shell_text.splitlines(keepends=True):
        content = _line_content(line)
        index = 0
        while index < len(content):
            character = content[index]
            if quote == "'":
                if character == "'":
                    quote = ""
                index += 1
                continue
            if character == "\\":
                index += 2
                continue
            if quote:
                if character == quote:
                    quote = ""
                index += 1
                continue
            if character in {"'", '"'}:
                quote = character
                index += 1
                continue
            if character == "#" and _starts_comment(content, index):
                output.append(content[:index] + _blank_line(line))
                break
            index += 1
        else:
            output.append(line)
    return "".join(output)


def _heredocs_on_line(
    line: str,
    *,
    quote: str,
) -> tuple[list[_Heredoc], str, bool]:
    content = _line_content(line)
    declarations: list[_Heredoc] = []
    escaped_newline = False
    index = 0
    while index < len(content):
        character = content[index]
        if quote == "'":
            if character == "'":
                quote = ""
            index += 1
            continue
        if character == "\\":
            if index + 1 == len(content):
                escaped_newline = True
                break
            index += 2
            continue
        if quote:
            if character == quote:
                quote = ""
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "#" and _starts_comment(content, index):
            break
        if content.startswith("<<<", index):
            index += 3
            continue
        if content.startswith("<<", index):
            word_start = index + 2
            strip_tabs = word_start < len(content) and content[word_start] == "-"
            if strip_tabs:
                word_start += 1
            delimiter, index = _read_heredoc_word(content, word_start)
            declarations.append(_Heredoc(delimiter, strip_tabs))
            continue
        index += 1
    return declarations, quote, escaped_newline


def _read_heredoc_word(content: str, start: int) -> tuple[str, int]:
    if start >= len(content):
        raise ShellCommandParseError("heredoc delimiter is missing")
    word: list[str] = []
    quote = ""
    index = start
    while index < len(content):
        character = content[index]
        if quote == "'":
            if character == "'":
                quote = ""
            else:
                word.append(character)
            index += 1
            continue
        if character == "\\":
            if index + 1 >= len(content):
                raise ShellCommandParseError("heredoc delimiter ends with escape")
            word.append(content[index + 1])
            index += 2
            continue
        if quote:
            if character == quote:
                quote = ""
            else:
                word.append(character)
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character.isspace() or character in ";&|()<>":
            break
        word.append(character)
        index += 1
    if quote:
        raise ShellCommandParseError("heredoc delimiter has an unterminated quote")
    delimiter = "".join(word)
    if not delimiter:
        raise ShellCommandParseError("heredoc delimiter is empty")
    return delimiter, index


def _starts_comment(content: str, index: int) -> bool:
    return index == 0 or content[index - 1].isspace() or content[index - 1] in ";&|()<>"


def _line_content(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith(("\n", "\r")):
        return line[:-1]
    return line


def _blank_line(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def _collapse_line_continuations(shell_text: str) -> str:
    output: list[str] = []
    quote = ""
    index = 0
    while index < len(shell_text):
        character = shell_text[index]
        if character == "\\" and quote != "'":
            if index + 1 < len(shell_text) and shell_text[index + 1] == "\n":
                index += 2
                continue
            output.append(character)
            if index + 1 < len(shell_text):
                output.append(shell_text[index + 1])
                index += 2
                continue
        elif character in {"'", '"'}:
            if not quote:
                quote = character
            elif quote == character:
                quote = ""
        output.append(character)
        index += 1
    return "".join(output)


def _split_punctuation(token: str) -> tuple[str, ...]:
    if not token or any(character not in _PUNCTUATION for character in token):
        return (token,)
    projected: list[str] = []
    index = 0
    while index < len(token):
        operator = next(
            (
                candidate
                for candidate in _MULTI_OPERATORS
                if token.startswith(candidate, index)
            ),
            token[index],
        )
        projected.append(operator)
        index += len(operator)
    return tuple(projected)


def _is_function_header(tokens: tuple[str, ...], index: int) -> bool:
    return (
        index + 3 < len(tokens)
        and _SHELL_NAME.fullmatch(tokens[index]) is not None
        and tokens[index + 1 : index + 4] == ("(", ")", "{")
    )


def _commands_from_tokens(tokens: tuple[str, ...]) -> tuple[ShellCommand, ...]:
    return tuple(span.command for span in _command_spans(tokens))


def _top_level_function_definitions(
    tokens: tuple[str, ...],
) -> dict[str, tuple[int, ...]]:
    definitions: dict[str, list[int]] = {}
    subshell_depth = 0
    brace_depth = 0
    function_stack: list[int] = []
    controls: list[str] = []
    at_command_start = True
    index = 0
    while index < len(tokens):
        if _is_function_header(tokens, index):
            identity = index
            valid = (
                not function_stack
                and not subshell_depth
                and not brace_depth
                and not controls
            )
            definitions.setdefault(tokens[index], []).append(
                identity if valid else -identity - 1
            )
            brace_depth += 1
            function_stack.append(brace_depth)
            index += 4
            at_command_start = True
            continue
        token = tokens[index]
        if at_command_start and token in {
            "if",
            "for",
            "while",
            "until",
            "select",
            "case",
        }:
            controls.append(token)
        elif at_command_start and token in {"fi", "done", "esac"} and controls:
            controls.pop()
        if token == "(":
            subshell_depth += 1
        elif token == ")":
            subshell_depth = max(0, subshell_depth - 1)
        elif token == "{":
            brace_depth += 1
        elif token == "}" and not _is_parameter_expansion_closer(tokens, index):
            if function_stack and function_stack[-1] == brace_depth:
                function_stack.pop()
            brace_depth = max(0, brace_depth - 1)
        at_command_start = token in _COMMAND_BOUNDARIES or token in {
            "then",
            "do",
            "else",
        }
        index += 1
    if function_stack:
        raise ShellCommandParseError("shell function body is unterminated")
    return {name: tuple(items) for name, items in definitions.items()}


def _is_parameter_expansion_closer(tokens: tuple[str, ...], index: int) -> bool:
    return index > 0 and "${" in tokens[index - 1]


def _command_spans(tokens: tuple[str, ...]) -> tuple[_ShellCommandSpan, ...]:
    spans: list[_ShellCommandSpan] = []
    current: list[str] = []
    current_start = 0
    separator = "\n"
    current_separator = separator
    depth = 0
    current_depth = depth
    brace_depth = 0
    current_brace_depth = brace_depth
    function_stack: list[tuple[str, int, int]] = []

    def flush(end_index: int) -> None:
        if current:
            command = ShellCommand(
                tuple(current),
                current_separator,
                current_depth,
                tuple(name for name, _, _ in function_stack),
                tuple(identity for _, _, identity in function_stack),
                current_brace_depth,
            )
            spans.append(_ShellCommandSpan(command, current_start, end_index))
            current.clear()

    index = 0
    while index < len(tokens):
        if not current and _is_function_header(tokens, index):
            brace_depth += 1
            function_stack.append((tokens[index], brace_depth, index))
            separator = "{"
            index += 4
            continue
        token = tokens[index]
        if token == "}" and current and any("${" in item for item in current):
            current.append(token)
            index += 1
            continue
        if token in _COMMAND_BOUNDARIES:
            flush(index)
            if token == "(":
                depth += 1
            elif token == ")":
                depth = max(0, depth - 1)
            elif token == "{":
                brace_depth += 1
            elif token == "}":
                if function_stack and function_stack[-1][1] == brace_depth:
                    function_stack.pop()
                brace_depth = max(0, brace_depth - 1)
            separator = token
            index += 1
            continue
        if not current:
            current_separator = separator
            current_depth = depth
            current_brace_depth = brace_depth
            current_start = index
        current.append(token)
        index += 1
    flush(len(tokens))
    if function_stack:
        raise ShellCommandParseError("shell function body is unterminated")
    return tuple(spans)
