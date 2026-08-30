"""Fail-closed static shell-array projection."""

from __future__ import annotations

import re

from quwoquan_ops.gate.local_dependency_purity.shell_commands import (
    ShellCommandParseError,
    _command_spans,
    _is_definitely_reached_top_level,
    _is_reachable_in_dispatched_function,
    _shell_tokens,
    _ShellCommandSpan,
    _top_level_function_definitions,
)

_SHELL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def project_reachable_shell_array_tokens(
    shell_text: str,
    *,
    array_name: str,
    consumer_prefix: tuple[str, ...],
) -> tuple[str, ...]:
    """Return values reaching exactly one canonical top-level consumer."""

    if _SHELL_NAME.fullmatch(array_name) is None:
        raise ShellCommandParseError("array name is not a shell identifier")
    tokens = _shell_tokens(shell_text)
    spans = _command_spans(tokens)
    definitions = _top_level_function_definitions(tokens)
    reference = f"${{{array_name}[@]}}"
    consumers = [
        span
        for span in spans
        if not span.command.function_scope
        and span.command.subshell_depth == 0
        and span.command.argv[: len(consumer_prefix)] == consumer_prefix
        and reference in span.command.argv[len(consumer_prefix) :]
        and _is_definitely_reached_top_level(spans, span)
    ]
    if len(consumers) != 1:
        raise ShellCommandParseError(
            "shell array must have exactly one reachable canonical consumer"
        )
    return _top_level_array_values(
        tokens,
        array_name=array_name,
        stop_index=consumers[0].start_index,
        spans=spans,
        definitions=definitions,
    )


def _top_level_array_values(
    tokens: tuple[str, ...],
    *,
    array_name: str,
    stop_index: int,
    spans: tuple[_ShellCommandSpan, ...],
    definitions: dict[str, tuple[int, ...]],
) -> tuple[str, ...]:
    values: list[str] = []
    initialized = False
    assignments = {f"{array_name}=", f"{array_name}+="}
    for span in spans:
        if span.start_index >= stop_index:
            break
        if span.command.function_scope or span.command.subshell_depth:
            continue
        if _is_definitely_reached_top_level(spans, span):
            _reject_reachable_helper_mutation(
                tokens,
                spans,
                definitions,
                span.command.argv,
                array_name=array_name,
                visited=set(),
            )
        if _ambiguous_array_mutation(span.command.argv, array_name=array_name):
            raise ShellCommandParseError(
                "shell array may be mutated outside the canonical static forms"
            )
        indices = [
            index
            for index in range(span.start_index, span.end_index)
            if tokens[index] in assignments
        ]
        if not indices:
            continue
        if not _is_definitely_reached_top_level(spans, span) or (
            span.end_index < len(tokens) and tokens[span.end_index] in {"|", "&"}
        ):
            continue
        if len(indices) != 1 or tokens[span.start_index : indices[0]]:
            raise ShellCommandParseError("shell array assignment is not static")
        index = indices[0]
        if index + 1 >= stop_index or tokens[index + 1] != "(":
            raise ShellCommandParseError("shell array assignment is not static")
        arguments, next_index = _array_arguments(tokens, index + 1)
        if next_index > stop_index:
            raise ShellCommandParseError("shell array assignment crosses its consumer")
        if tokens[index] == f"{array_name}=":
            values = list(arguments)
            initialized = True
        else:
            if not initialized:
                raise ShellCommandParseError(
                    "shell array append precedes its canonical initialization"
                )
            values.extend(arguments)
    if not initialized:
        raise ShellCommandParseError(
            "shell array has no reachable static initialization"
        )
    return tuple(values)


def _reject_reachable_helper_mutation(
    tokens: tuple[str, ...],
    spans: tuple[_ShellCommandSpan, ...],
    definitions: dict[str, tuple[int, ...]],
    argv: tuple[str, ...],
    *,
    array_name: str,
    visited: set[int],
) -> None:
    if not argv:
        return
    helper_name = argv[0]
    if helper_name.startswith("$"):
        raise ShellCommandParseError("dynamic shell helper may mutate the array")
    identities = definitions.get(helper_name)
    if identities is None:
        return
    if len(identities) != 1:
        raise ShellCommandParseError("shell helper identity is ambiguous")
    identity = identities[0]
    if identity in visited:
        raise ShellCommandParseError("recursive shell helper may mutate the array")
    reached = {*visited, identity}
    assignments = {f"{array_name}=", f"{array_name}+="}
    for span in spans:
        if span.command.function_definition_scope != (identity,):
            continue
        if not _is_reachable_in_dispatched_function(tokens, spans, span):
            continue
        command = span.command.argv
        if _ambiguous_array_mutation(command, array_name=array_name) or any(
            token in assignments or token.startswith(f"{array_name}[")
            for token in command
        ):
            raise ShellCommandParseError("reachable shell helper mutates the array")
        _reject_reachable_helper_mutation(
            tokens,
            spans,
            definitions,
            command,
            array_name=array_name,
            visited=reached,
        )


def _ambiguous_array_mutation(
    argv: tuple[str, ...],
    *,
    array_name: str,
) -> bool:
    if not argv:
        return False
    command = argv[0]
    if command in {f"{array_name}=", f"{array_name}+="}:
        return False
    if command in {"eval", "source", ".", "read", "readarray", "mapfile", "unset"}:
        return True
    if command == "printf" and "-v" in argv[1:]:
        return True
    if command in {"declare", "typeset", "local"} and any(
        option == "-n" or (option.startswith("-") and "n" in option[1:])
        for option in argv[1:]
    ):
        return True
    array_write = re.compile(rf"{re.escape(array_name)}(?:\[[^]]*\])?(?:\+)?=")
    return any(
        token not in {f"{array_name}=", f"{array_name}+="}
        and (
            array_write.fullmatch(token) is not None
            or token.startswith(f"{array_name}[")
        )
        for token in argv
    )


def _array_arguments(
    tokens: tuple[str, ...],
    opening_index: int,
) -> tuple[tuple[str, ...], int]:
    arguments: list[str] = []
    depth = 1
    index = opening_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth == 0:
                return tuple(arguments), index + 1
        if depth == 1 and token != "\n":
            arguments.append(token)
        index += 1
    raise ShellCommandParseError("shell array assignment is unterminated")
