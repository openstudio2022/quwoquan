"""文件内局部错误构造器与跨包 config module 注入的发射解析。"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import _KIND_CONVERSION, _MODULE_CONVERSION, _NEW_CODE_CALL
from .literal_scan import _strip_comments
from .models import Emission, RuntimeErrorVocabulary, ScanResult, UnresolvedSite, _read
from .resolution import (
    _assignment_values,
    _function_name,
    _go_files,
    _package_scope,
    _resolve_reason,
    _resolve_symbol,
    _split_functions,
)


def _split_call_arguments(arguments: str) -> list[str]:
    values: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(arguments):
        if quote:
            if quote != "`" and escaped:
                escaped = False
            elif quote != "`" and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}" and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            values.append(arguments[start:index].strip())
            start = index + 1
    tail = arguments[start:].strip()
    if tail:
        values.append(tail)
    return values


def _iter_named_calls(text: str, name: str) -> list[list[str]]:
    calls: list[list[str]] = []
    for match in re.finditer(rf"\b{re.escape(name)}\s*\(", text):
        start = match.end()
        depth = 1
        index = start
        quote = ""
        escaped = False
        while index < len(text) and depth:
            char = text[index]
            if quote:
                if quote != "`" and escaped:
                    escaped = False
                elif quote != "`" and char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
            elif char in {'"', "'", "`"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            calls.append(_split_call_arguments(text[start : index - 1]))
    return calls


def _function_parameters(function_text: str) -> dict[str, int]:
    open_paren = function_text.find("(")
    if open_paren < 0:
        return {}
    depth = 1
    index = open_paren + 1
    while index < len(function_text) and depth:
        if function_text[index] == "(":
            depth += 1
        elif function_text[index] == ")":
            depth -= 1
        index += 1
    if depth:
        return {}
    params: dict[str, int] = {}
    pending_names: list[str] = []
    position = 0
    for value in _split_call_arguments(function_text[open_paren + 1 : index - 1]):
        fields = value.split()
        if len(fields) == 1:
            pending_names.append(fields[0])
            continue
        names = [*pending_names, *fields[:-1]]
        pending_names = []
        for name in names:
            params[name] = position
            position += 1
    return params


_HTTP_STATUS_VALUES = {
    "StatusBadRequest": 400,
    "StatusUnauthorized": 401,
    "StatusForbidden": 403,
    "StatusNotFound": 404,
    "StatusMethodNotAllowed": 405,
    "StatusConflict": 409,
    "StatusInternalServerError": 500,
    "StatusBadGateway": 502,
    "StatusServiceUnavailable": 503,
    "StatusGatewayTimeout": 504,
}


def _status_value(expression: str) -> int | None:
    expression = expression.strip()
    if expression.isdigit():
        return int(expression)
    ident = expression.rsplit(".", 1)[-1]
    return _HTTP_STATUS_VALUES.get(ident)


def _resolve_local_ctor_kind(
    function_text: str,
    kind_expression: str,
    params: dict[str, int],
    arguments: list[str],
    vocabulary: RuntimeErrorVocabulary,
    scopes: tuple[str, ...],
) -> set[str]:
    direct = _resolve_symbol(
        kind_expression, scopes, vocabulary.kinds, _KIND_CONVERSION
    )
    if len(direct) == 1:
        return direct
    status_match = re.search(
        rf"\b(?P<kind>{re.escape(kind_expression)})\s*:=\s*(?P<low>(?:\w+\.)?Kind\w+)"
        r".*?if\s+(?P<status>\w+)\s*>=\s*500\s*{"
        rf".*?\b(?P=kind)\s*=\s*(?P<high>(?:\w+\.)?Kind\w+)",
        function_text,
        re.S,
    )
    if status_match is None:
        return set()
    status_position = params.get(status_match.group("status"))
    if status_position is None or status_position >= len(arguments):
        return set()
    status = _status_value(arguments[status_position])
    if status is None:
        return set()
    selected = status_match.group("high") if status >= 500 else status_match.group("low")
    return _resolve_symbol(selected, scopes, vocabulary.kinds, _KIND_CONVERSION)


def _balanced_brace_body(text: str, open_brace: int) -> tuple[str, int] | None:
    """Return the body/end of one Go brace block without guessing on nesting."""
    depth = 1
    index = open_brace + 1
    quote = ""
    escaped = False
    while index < len(text) and depth:
        char = text[index]
        if quote:
            if quote != "`" and escaped:
                escaped = False
            elif quote != "`" and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {'"', "'", "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth:
        return None
    return text[open_brace + 1 : index - 1], index


def _apply_local_assignments(
    text: str,
    variables: set[str],
    bindings: dict[str, str],
) -> None:
    """Apply simple Go single/parallel assignments in source order."""
    pattern = re.compile(
        r"(?m)^\s*(?P<lhs>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)"
        r"\s*(?::=|=)\s*(?P<rhs>[^\n]+)$"
    )
    for match in pattern.finditer(text):
        left = [value.strip() for value in match.group("lhs").split(",")]
        right = _split_call_arguments(match.group("rhs"))
        if len(left) != len(right):
            continue
        for name, value in zip(left, right):
            if name in variables:
                bindings[name] = value.strip()


def _resolve_local_ctor_switch_bindings(
    function_text: str,
    params: dict[str, int],
    arguments: list[str],
    variables: set[str],
) -> dict[str, str] | None:
    """Resolve a local error constructor's status switch for one call site.

    The old scanner collected every assignment to module/kind/reason and then
    happened to retain only the initializer.  That made a constructor such as
    `writeRuntimeError(status)` look like it emitted only its default 500 code,
    while reachable 400/404 branches disappeared from the dimension.  Here we
    evaluate only a call site's literal HTTP status and apply exactly one Go
    switch clause.  Dynamic status expressions remain unresolved/fail-closed.
    """
    for switch in re.finditer(
        r"\bswitch\s+(?P<status>[A-Za-z_]\w*)\s*\{", function_text
    ):
        status_name = switch.group("status")
        status_position = params.get(status_name)
        if status_position is None or status_position >= len(arguments):
            continue
        status = _status_value(arguments[status_position])
        if status is None:
            return None
        block = _balanced_brace_body(function_text, switch.end() - 1)
        if block is None:
            return None
        body, _ = block
        bindings: dict[str, str] = {}
        _apply_local_assignments(function_text[: switch.start()], variables, bindings)

        clauses = list(
            re.finditer(
                r"(?m)^\s*(?:case\s+(?P<labels>[^:]+)|(?P<default>default))\s*:",
                body,
            )
        )
        selected = ""
        fallback = ""
        for index, clause in enumerate(clauses):
            end = clauses[index + 1].start() if index + 1 < len(clauses) else len(body)
            clause_body = body[clause.end() : end]
            if clause.group("default") is not None:
                fallback = clause_body
                continue
            labels = _split_call_arguments(clause.group("labels") or "")
            if any(_status_value(label) == status for label in labels):
                selected = clause_body
                break
        _apply_local_assignments(selected or fallback, variables, bindings)
        return bindings
    return {}


def _scan_local_error_constructors(
    root: Path,
    path: Path,
    text: str,
    vocabulary: RuntimeErrorVocabulary,
    result: ScanResult,
) -> set[str]:
    relative = path.relative_to(root).as_posix()
    package_scope = _package_scope(text)
    sibling_sources = [
        _read(sibling)
        for sibling in sorted(path.parent.glob("*.go"))
        if sibling != path and not sibling.name.endswith("_test.go")
    ]
    sibling_scope = "".join(
        _package_scope(source) for source in sibling_sources
    )
    constructor_names: set[str] = set()
    for function_text in _split_functions(text):
        calls = list(_NEW_CODE_CALL.finditer(function_text))
        if len(calls) != 1:
            continue
        params = _function_parameters(function_text)
        call = calls[0]
        expressions = (
            call.group("module").strip(),
            call.group("kind").strip(),
            call.group("reason").strip(),
        )
        if not any(expression in params for expression in expressions) and not any(
            _assignment_values(function_text, expression) for expression in expressions
        ):
            continue
        name = _function_name(function_text)
        # A package-private constructor is commonly defined beside its route
        # handlers and called from sibling files.  Scanning only the defining
        # file was the exact false-green that hid Product Ops 400 branches.
        caller_text = _strip_comments(
            "\n".join(
                [text.replace("func " + function_text, "", 1), *sibling_sources]
            )
        )
        constructor_calls = _iter_named_calls(caller_text, name)
        if not constructor_calls:
            continue
        constructor_names.add(name)
        for arguments in constructor_calls:
            scopes = (function_text, package_scope, sibling_scope)
            module_expression, kind_expression, reason_expression = expressions
            switch_bindings = _resolve_local_ctor_switch_bindings(
                function_text,
                params,
                arguments,
                {module_expression, kind_expression, reason_expression},
            )
            if switch_bindings is None:
                result.unresolved.append(
                    UnresolvedSite(
                        path=relative,
                        function=name,
                        form="local_error_ctor",
                        expression=f"{name}({', '.join(arguments)})",
                    )
                )
                continue
            if module_expression in params and params[module_expression] < len(arguments):
                module_expression = arguments[params[module_expression]]
            elif module_expression in switch_bindings:
                module_expression = switch_bindings[module_expression]
            if kind_expression in params and params[kind_expression] < len(arguments):
                kind_expression = arguments[params[kind_expression]]
            elif kind_expression in switch_bindings:
                kind_expression = switch_bindings[kind_expression]
            if reason_expression in params and params[reason_expression] < len(arguments):
                reason_expression = arguments[params[reason_expression]]
            elif reason_expression in switch_bindings:
                reason_expression = switch_bindings[reason_expression]
            modules = _resolve_symbol(
                module_expression, scopes, vocabulary.modules, _MODULE_CONVERSION
            )
            kinds = _resolve_symbol(
                kind_expression, scopes, vocabulary.kinds, _KIND_CONVERSION
            )
            if len(kinds) != 1:
                kinds = _resolve_local_ctor_kind(
                    function_text,
                    kind_expression,
                    params,
                    arguments,
                    vocabulary,
                    scopes,
                )
            reasons = _resolve_reason(reason_expression, scopes, vocabulary.reasons)
            if len(modules) == 1 and len(kinds) == 1 and len(reasons) == 1:
                result.emissions.append(
                    Emission(
                        code=(
                            f"{next(iter(modules))}.{next(iter(kinds))}."
                            f"{next(iter(reasons))}"
                        ),
                        form="local_error_ctor",
                        path=relative,
                        function=name,
                    )
                )
            else:
                result.unresolved.append(
                    UnresolvedSite(
                        path=relative,
                        function=name,
                        form="local_error_ctor",
                        expression=f"{name}({', '.join(arguments)})",
                    )
                )
    return constructor_names


def _config_selector_values(
    root: Path,
    selector_expression: str,
    vocabulary: RuntimeErrorVocabulary,
) -> set[str]:
    selector = re.fullmatch(r"(?P<param>\w+)\.(?P<field>\w+)", selector_expression)
    if selector is None:
        return set()
    values: set[str] = set()
    field = selector.group("field")
    for path in _go_files(root):
        text = _read(path)
        for match in re.finditer(
            rf"\b\w*(?:Config|Options)\s*{{(?P<body>.*?)\n\s*}}", text, re.S
        ):
            field_match = re.search(
                rf"\b{re.escape(field)}\s*:\s*(?P<value>[^,\n}}]+)",
                match.group("body"),
            )
            if field_match is None:
                continue
            values |= _resolve_symbol(
                field_match.group("value"),
                (_package_scope(text),),
                vocabulary.modules,
                _MODULE_CONVERSION,
            )
    return values
