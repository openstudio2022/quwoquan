"""Fail-closed shell command projection for dependency-purity checks."""

from __future__ import annotations

import shlex
from dataclasses import dataclass


class ShellCommandParseError(ValueError):
    """Raised when executable commands cannot be projected without ambiguity."""


@dataclass(frozen=True)
class ShellCommand:
    argv: tuple[str, ...]
    separator_before: str
    subshell_depth: int


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
_COMMAND_BOUNDARIES = {"\n", ";", ";;", ";&", ";;&", "&&", "||", "|", "&", "(", ")"}


def parse_shell_commands(shell_text: str) -> tuple[ShellCommand, ...]:
    """Project executable simple commands, excluding comments and heredoc data."""

    lexer = shlex.shlex(
        _collapse_line_continuations(shell_text),
        posix=True,
        punctuation_chars=_PUNCTUATION,
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        raw_tokens = list(lexer)
    except ValueError as error:
        raise ShellCommandParseError(str(error)) from error
    tokens = tuple(
        projected
        for raw_token in raw_tokens
        for projected in _split_punctuation(raw_token)
    )
    executable_tokens = _remove_heredoc_bodies(tokens)
    return _commands_from_tokens(executable_tokens)


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


def _remove_heredoc_bodies(tokens: tuple[str, ...]) -> tuple[str, ...]:
    projected: list[str] = []
    pending_delimiters: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "<<":
            if index + 1 >= len(tokens) or tokens[index + 1] in _COMMAND_BOUNDARIES:
                raise ShellCommandParseError("heredoc delimiter is missing")
            raw_delimiter = tokens[index + 1]
            delimiter = raw_delimiter.removeprefix("-")
            if not delimiter:
                raise ShellCommandParseError("heredoc delimiter is empty")
            pending_delimiters.append(delimiter)
            projected.extend((token, raw_delimiter))
            index += 2
            continue
        projected.append(token)
        index += 1
        if token != "\n" or not pending_delimiters:
            continue
        for delimiter in pending_delimiters:
            terminated = False
            while index < len(tokens):
                line: list[str] = []
                while index < len(tokens) and tokens[index] != "\n":
                    line.append(tokens[index])
                    index += 1
                if index < len(tokens):
                    index += 1
                if line == [delimiter]:
                    terminated = True
                    break
            if not terminated:
                raise ShellCommandParseError(f"heredoc {delimiter!r} is unterminated")
        pending_delimiters = []
    return tuple(projected)


def _commands_from_tokens(tokens: tuple[str, ...]) -> tuple[ShellCommand, ...]:
    commands: list[ShellCommand] = []
    current: list[str] = []
    separator = "\n"
    current_separator = separator
    depth = 0
    current_depth = depth

    def flush() -> None:
        if current:
            commands.append(
                ShellCommand(tuple(current), current_separator, current_depth)
            )
            current.clear()

    for token in tokens:
        if token in _COMMAND_BOUNDARIES:
            flush()
            if token == "(":
                depth += 1
            elif token == ")":
                depth = max(0, depth - 1)
            separator = token
            continue
        if not current:
            current_separator = separator
            current_depth = depth
        current.append(token)
    flush()
    return tuple(commands)
