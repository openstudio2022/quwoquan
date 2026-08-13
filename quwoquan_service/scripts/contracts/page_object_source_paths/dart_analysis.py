"""页面 Dart library 的词法证据：import closure、identifier 消费与 public seam。

复用 App architecture 的 Dart 词法器（经 ``repo_reuse._importable`` 只读加载），
不复制 import/comment 规则；本模块只派生可安全审计的编译依赖证据。
"""

from __future__ import annotations

from pathlib import Path

from .models import REPOSITORY_ROOT, ContractError
from .repo_reuse import _importable


def _looks_like_object_presentation(path_parts: tuple[str, ...]) -> bool:
    """只识别当前 canonical service-root presentation 物理形状。

    ``lib/runtime/**/presentation`` 不是业务对象树，不能因为目录里恰好出现
    ``presentation`` token 就伪造 physical owner。旧 direct-domain 路径由 App
    architecture/object-path gate 负责阻断；本工具只审当前唯一目录合同。
    """

    return (
        len(path_parts) >= 7
        and path_parts[0] == "lib"
        and path_parts[1] == "service"
        and path_parts[5] == "presentation"
    )


def _parse_dart_uri_directives(source: str) -> tuple[tuple[str, str], ...]:
    """复用 App architecture 的 Dart 词法器，不复制 import/comment 规则。"""

    with _importable(REPOSITORY_ROOT / "quwoquan_ops" / "gate"):
        import verify_app_architecture  # type: ignore

    return tuple(
        (directive.kind, directive.uri)
        for directive in verify_app_architecture.parse_dart_uri_directives(source)
    )


def _dart_source_tokens(source: str) -> tuple[tuple[str, str], ...]:
    """复用同一 Dart 词法真相，供 behavioral symbol 消费判定。"""

    with _importable(REPOSITORY_ROOT / "quwoquan_ops" / "gate"):
        import verify_app_architecture  # type: ignore

    return tuple(verify_app_architecture._dart_source_tokens(source))  # noqa: SLF001


def _consumed_dart_identifiers(source: str) -> frozenset[str]:
    """返回代码真正引用的 identifier；排除 URI directive 的 ``show`` 等 token。"""

    tokens = _dart_source_tokens(source)
    identifiers: set[str] = set()
    index = 0
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    while index < len(tokens):
        token = tokens[index]
        at_statement_root = brace_depth == paren_depth == bracket_depth == 0
        if (
            at_statement_root
            and token[0] == "identifier"
            and token[1] in {"import", "export", "part"}
        ):
            while index < len(tokens) and tokens[index] != ("punctuation", ";"):
                index += 1
            index += 1
            continue

        if token[0] == "identifier":
            identifiers.add(token[1])
        elif token[0] == "punctuation":
            if token[1] == "{":
                brace_depth += 1
            elif token[1] == "}":
                brace_depth = max(0, brace_depth - 1)
            elif token[1] == "(":
                paren_depth += 1
            elif token[1] == ")":
                paren_depth = max(0, paren_depth - 1)
            elif token[1] == "[":
                bracket_depth += 1
            elif token[1] == "]":
                bracket_depth = max(0, bracket_depth - 1)
        index += 1
    return frozenset(identifiers)


def _public_named_declarations(source: str) -> frozenset[str]:
    """返回 authored library 的顶层公开类型声明。

    该集合只用于把同一 public seam 文件中的 typed intent 与实例行为 facade
    关联起来；它本身绝不构成 participant 证据。
    """

    tokens = _dart_source_tokens(source)
    symbols: set[str] = set()
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    for index, token in enumerate(tokens):
        at_declaration_root = brace_depth == paren_depth == bracket_depth == 0
        if (
            at_declaration_root
            and token == ("identifier", "class")
            and index + 1 < len(tokens)
            and tokens[index + 1][0] == "identifier"
            and not tokens[index + 1][1].startswith("_")
        ):
            symbols.add(tokens[index + 1][1])
        elif (
            at_declaration_root
            and token[0] == "identifier"
            and token[1] in {"enum", "mixin", "typedef"}
            and index + 1 < len(tokens)
            and tokens[index + 1][0] == "identifier"
            and not tokens[index + 1][1].startswith("_")
        ):
            symbols.add(tokens[index + 1][1])

        if token[0] != "punctuation":
            continue
        if token[1] == "{":
            brace_depth += 1
        elif token[1] == "}":
            brace_depth = max(0, brace_depth - 1)
        elif token[1] == "(":
            paren_depth += 1
        elif token[1] == ")":
            paren_depth = max(0, paren_depth - 1)
        elif token[1] == "[":
            bracket_depth += 1
        elif token[1] == "]":
            bracket_depth = max(0, bracket_depth - 1)
    return frozenset(symbols)


def _matching_paren_end(
    tokens: tuple[tuple[str, str], ...],
    start: int,
) -> int | None:
    depth = 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token == ("punctuation", "("):
            depth += 1
        elif token == ("punctuation", ")"):
            depth -= 1
            if depth == 0:
                return index
    return None


def _public_instance_behavior_symbols(source: str) -> frozenset[str]:
    """派生带实例行为方法的 authored public facade/coordinator。

    仅接受明确的 ``*Facade`` / ``*Coordinator``；普通 value/view/route 类型即使
    有辅助实例方法也不是对象行为入口。只有实例方法成立，纯静态 namespace 继续
    排除。这样可识别页面通过 typed intent + runtime presenter 消费的对象 facade，
    又不会把 route extra、static resolver 或 mapper 当 participant。
    """

    tokens = _dart_source_tokens(source)
    symbols: set[str] = set()
    root_brace_depth = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == ("punctuation", "{"):
            root_brace_depth += 1
            index += 1
            continue
        if token == ("punctuation", "}"):
            root_brace_depth = max(0, root_brace_depth - 1)
            index += 1
            continue
        if root_brace_depth != 0 or token != ("identifier", "class"):
            index += 1
            continue
        if index + 1 >= len(tokens) or tokens[index + 1][0] != "identifier":
            index += 1
            continue

        class_name = tokens[index + 1][1]
        if class_name.startswith("_") or not class_name.endswith(("Facade", "Coordinator")):
            index += 1
            continue

        body_start = next(
            (
                cursor
                for cursor in range(index + 2, len(tokens))
                if tokens[cursor] == ("punctuation", "{")
            ),
            None,
        )
        if body_start is None:
            break

        body_depth = 1
        statement_start = body_start + 1
        cursor = body_start + 1
        has_instance_behavior = False
        while cursor < len(tokens) and body_depth > 0:
            current = tokens[cursor]
            if current == ("punctuation", "{"):
                body_depth += 1
            elif current == ("punctuation", "}"):
                body_depth -= 1
                if body_depth == 1:
                    statement_start = cursor + 1
            elif body_depth == 1 and current == ("punctuation", ";"):
                statement_start = cursor + 1
            elif body_depth == 1 and current == ("punctuation", "("):
                prefix = tokens[statement_start:cursor]
                prefix_names = [item[1] for item in prefix if item[0] == "identifier"]
                method_name = prefix_names[-1] if prefix_names else ""
                paren_end = _matching_paren_end(tokens, cursor)
                if paren_end is None:
                    break
                suffix_cursor = paren_end + 1
                while (
                    suffix_cursor < len(tokens)
                    and tokens[suffix_cursor][0] == "identifier"
                    and tokens[suffix_cursor][1] in {"async", "sync"}
                ):
                    suffix_cursor += 1
                    if (
                        suffix_cursor < len(tokens)
                        and tokens[suffix_cursor] == ("punctuation", "*")
                    ):
                        suffix_cursor += 1
                suffix = tokens[suffix_cursor] if suffix_cursor < len(tokens) else None
                if (
                    method_name
                    and method_name != class_name
                    and not method_name.startswith("_")
                    and "static" not in prefix_names
                    and "factory" not in prefix_names
                    and ("punctuation", "=") not in prefix
                    and suffix
                    in {
                        ("punctuation", "{"),
                        ("punctuation", "=>"),
                        ("punctuation", ";"),
                    }
                ):
                    has_instance_behavior = True
                    break
                cursor = paren_end
            cursor += 1

        if has_instance_behavior:
            symbols.add(class_name)
        index = max(index + 1, cursor)
    return frozenset(symbols)


def _public_behavior_symbols(source: str) -> frozenset[str]:
    """派生 authored public behavioral port/provider 声明。

    ``abstract final class`` 是纯静态 namespace（例如 resolver），不是可装配 port；
    普通 class/enum/route extra/view data 也不因位于 public 目录就成为页面 participant。
    Provider 只在顶层变量 RHS 明确由 Riverpod ``*Provider`` factory 创建时认领。
    """

    tokens = _dart_source_tokens(source)
    symbols: set[str] = set(_public_instance_behavior_symbols(source))
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        at_declaration_root = brace_depth == paren_depth == bracket_depth == 0
        if at_declaration_root and token == ("identifier", "abstract"):
            cursor = index + 1
            modifiers: set[str] = set()
            while cursor < len(tokens) and tokens[cursor][0] == "identifier":
                value = tokens[cursor][1]
                if value == "class":
                    name_index = cursor + 1
                    if (
                        "final" not in modifiers
                        and name_index < len(tokens)
                        and tokens[name_index][0] == "identifier"
                    ):
                        symbols.add(tokens[name_index][1])
                    break
                modifiers.add(value)
                cursor += 1

        if at_declaration_root and token[0] == "identifier" and token[1] in {
            "final",
            "const",
            "late",
        }:
            cursor = index
            statement: list[tuple[str, str]] = []
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                statement.append(tokens[cursor])
                cursor += 1
            equals = next(
                (
                    position
                    for position, item in enumerate(statement)
                    if item == ("punctuation", "=")
                ),
                None,
            )
            if equals is not None:
                lhs_names = [
                    item[1] for item in statement[:equals] if item[0] == "identifier"
                ]
                rhs_names = {
                    item[1] for item in statement[equals + 1 :] if item[0] == "identifier"
                }
                variable_name = lhs_names[-1] if lhs_names else ""
                if (
                    "class" not in lhs_names
                    and variable_name.endswith("Provider")
                    and any(name.endswith("Provider") for name in rhs_names)
                ):
                    symbols.add(variable_name)

        if token[0] == "punctuation":
            if token[1] == "{":
                brace_depth += 1
            elif token[1] == "}":
                brace_depth = max(0, brace_depth - 1)
            elif token[1] == "(":
                paren_depth += 1
            elif token[1] == ")":
                paren_depth = max(0, paren_depth - 1)
            elif token[1] == "[":
                bracket_depth += 1
            elif token[1] == "]":
                bracket_depth = max(0, bracket_depth - 1)
        index += 1
    return frozenset(symbols)


def _resolve_app_dart_uri(app_root: Path, source: Path, uri: str) -> Path | None:
    """把 authored Dart URI 解析成 App ``lib/**`` 内真实文件。"""

    package_prefix = "package:quwoquan_app/"
    if uri.startswith(package_prefix):
        candidate = app_root / "lib" / uri[len(package_prefix) :]
    elif ":" in uri:
        return None
    else:
        candidate = source.parent / uri

    candidate = candidate.resolve()
    lib_root = (app_root / "lib").resolve()
    try:
        candidate.relative_to(lib_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _page_library_evidence(
    app_root: Path,
    source_path: str,
) -> tuple[tuple[str, ...], frozenset[str]]:
    """返回页面 library/part closure 的直接 imports 与实际消费 identifiers。

    不递归 imported library：传递依赖不能证明页面消费了那个对象。只有页面 library
    及其 Dart part 直接 authored 的 import 才是可安全审计的编译依赖。
    """

    app_root = app_root.resolve()
    source = (app_root / source_path).resolve()
    lib_root = (app_root / "lib").resolve()
    try:
        source.relative_to(lib_root)
    except ValueError:
        return (), frozenset()
    if not source.is_file():
        return (), frozenset()

    pending = [source]
    visited: set[Path] = set()
    imports: set[str] = set()
    consumed_identifiers: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        try:
            source_text = current.read_text(encoding="utf-8", errors="ignore")
            directives = _parse_dart_uri_directives(source_text)
            consumed_identifiers.update(_consumed_dart_identifiers(source_text))
        except ValueError as error:
            relative = current.relative_to(app_root).as_posix()
            raise ContractError(f"{relative}: Dart URI directive 无法解析: {error}") from error
        for kind, uri in directives:
            target = _resolve_app_dart_uri(app_root, current, uri)
            if target is None:
                continue
            if kind == "part":
                pending.append(target)
                continue
            if kind != "import":
                continue
            imports.add(target.relative_to(app_root).as_posix())
    return tuple(sorted(imports)), frozenset(consumed_identifiers)


def _is_application_public_path(source_path: str) -> bool:
    parts = Path(source_path).parts
    return "generated" not in parts and any(
        parts[index] == "application" and parts[index + 1] == "public"
        for index in range(len(parts) - 1)
    )


def _consumed_public_behavior_symbols(
    app_root: Path,
    imported_path: str,
    consumed_identifiers: frozenset[str],
) -> tuple[str, ...]:
    target = app_root / imported_path
    if not target.is_file():
        return ()
    source = target.read_text(encoding="utf-8", errors="ignore")
    declared = _public_behavior_symbols(source)
    consumed = set(declared & consumed_identifiers)

    # A page may construct a typed intent from the same public seam and hand it
    # to a runtime presenter/provider; the concrete coordinator remains behind
    # DI and is therefore not named by the page. A shared family prefix is the
    # narrow proof that the consumed typed intent belongs to that facade.
    named_declarations = _public_named_declarations(source)
    consumed_named = named_declarations & consumed_identifiers
    for behavior in _public_instance_behavior_symbols(source):
        suffix = "Coordinator" if behavior.endswith("Coordinator") else "Facade"
        family = behavior[: -len(suffix)]
        if family and any(symbol.startswith(family) for symbol in consumed_named):
            consumed.add(behavior)
    return tuple(sorted(consumed))
