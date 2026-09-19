#!/usr/bin/env python3
"""Reject retired runtime identifiers without prose scans or path allowlists."""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import ast
import json
import re
from urllib.parse import unquote

POLICY = "quwoquan_ops/policies/gates/governed_schema_migration_boundaries.json"


class BoundaryError(ValueError):
    """迁移声明未被当前源码证明，不授予任何退役身份认可。"""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise BoundaryError(message)


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    return ""


def _literal(node: ast.AST | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _imports(tree: ast.AST) -> dict[str, str]:
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                result[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name] = alias.name
    return result


def _resolved(node: ast.AST, bindings: dict[str, str]) -> str:
    name = _name(node)
    first, _, rest = name.partition(".")
    return bindings.get(first, first) + ("." + rest if rest else "")


def _loads_implementation(value: str, implementation: str) -> bool:
    return value == implementation or value.startswith(implementation + ".")


def _prefix_can_load(prefix: str, implementation: str) -> bool:
    if not prefix:
        return True
    stem = prefix[:-1] if prefix.endswith(".") else prefix
    return implementation == stem or implementation.startswith(stem + ".")


def _leading_prefixes(node: ast.AST, tree: ast.Module) -> set[str]:
    """无法穷举时只取静态前缀；空前缀视为开放加载。"""
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                break
        text = "".join(parts)
        return {text} if text else set()
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_strings(node.left, tree)
        if left:
            return left
        return _leading_prefixes(node.left, tree)
    return set()


def _static_strings(node: ast.AST, tree: ast.Module, seen: frozenset[str] = frozenset()) -> set[str] | None:
    """只解释有限字符串表达式及同模块 literal 参数，不执行被扫描代码。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.JoinedStr):
        parts: list[set[str]] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append({value.value})
                continue
            if isinstance(value, ast.FormattedValue):
                resolved = _static_strings(value.value, tree, seen)
                if resolved is None:
                    return None
                parts.append(resolved)
                continue
            return None
        result = {""}
        for part in parts:
            result = {left + right for left in result for right in part}
        return result
    if isinstance(node, ast.IfExp):
        left, right = _static_strings(node.body, tree, seen), _static_strings(node.orelse, tree, seen)
        return left | right if left is not None and right is not None else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static_strings(node.left, tree, seen), _static_strings(node.right, tree, seen)
        return {a + b for a in left for b in right} if left is not None and right is not None else None
    if not isinstance(node, ast.Name) or node.id in seen:
        return None
    scopes = [item for item in ast.walk(tree) if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in set(ast.walk(item))]
    scope = min(scopes, key=lambda item: item.end_lineno - item.lineno) if scopes else tree
    loops = [item for item in ast.walk(scope) if isinstance(item, ast.For) and node in set(ast.walk(item))
             and isinstance(item.target, ast.Tuple) and isinstance(item.iter, (ast.Tuple, ast.List))
             and node.id in [_name(target) for target in item.target.elts]]
    if len(loops) == 1:
        index = [_name(target) for target in loops[0].target.elts].index(node.id)
        rows = loops[0].iter.elts
        if all(isinstance(row, (ast.Tuple, ast.List)) and len(row.elts) > index and isinstance(_literal(row.elts[index]), str) for row in rows):
            return {_literal(row.elts[index]) for row in rows}
    assignments = [item for item in ast.walk(scope) if isinstance(item, ast.Assign)
                   and any(_name(target) == node.id for target in item.targets)]
    if len(assignments) == 1:
        value = assignments[0].value
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "get" and isinstance(value.func.value, ast.Name):
            mappings = [item.value for item in tree.body if isinstance(item, (ast.Assign, ast.AnnAssign))
                        and ((isinstance(item, ast.Assign) and any(_name(target) == value.func.value.id for target in item.targets))
                             or (isinstance(item, ast.AnnAssign) and _name(item.target) == value.func.value.id))]
            if len(mappings) == 1 and isinstance(mappings[0], ast.Dict) and all(isinstance(_literal(item), str) for item in mappings[0].values):
                return {_literal(item) for item in mappings[0].values}
    owners = [item for item in ast.walk(tree) if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
              and node in set(ast.walk(item))]
    if owners:
        owner = min(owners, key=lambda item: item.end_lineno - item.lineno)
        parameters = [arg.arg for arg in owner.args.args]
        if node.id in parameters or node.id in {arg.arg for arg in owner.args.kwonlyargs}:
            calls = [item for item in ast.walk(tree) if isinstance(item, ast.Call) and _name(item.func) == owner.name]
            values = []
            for call in calls:
                keywords = {keyword.arg: keyword.value for keyword in call.keywords}
                value = keywords.get(node.id)
                if value is None and node.id in parameters and parameters.index(node.id) < len(call.args):
                    value = call.args[parameters.index(node.id)]
                if value is None:
                    return None
                resolved = _static_strings(value, tree, seen | {node.id})
                if resolved is None:
                    return None
                values.extend(resolved)
            return set(values) if calls else None
    return None


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    bindings = _imports(tree)
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and _resolved(node.func, bindings) == name]


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    _require(len(matches) == 1, f"FUNCTION_IDENTITY:{name}")
    return matches[0]


def _module(path: str) -> str:
    return path.split("/scripts/", 1)[-1].removesuffix(".py").replace("/", ".")


def _literal_schema_pair(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 2:
        return None
    if not all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts):
        return None
    return node.elts[0].value, node.elts[1].value


def _closed_schema_registry_targets(tree: ast.AST) -> dict[str, set[str]]:
    """与 contract-closure 相同：模块内封闭 `*_SCHEMAS` 字面量登记表可展开为 schema 路径。"""
    registries: dict[str, set[str]] = {}
    for assignment in ast.walk(tree):
        if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
            continue
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        names = [
            item.id
            for item in targets
            if isinstance(item, ast.Name) and item.id.endswith("_SCHEMAS")
        ]
        if not names or not isinstance(assignment.value, ast.Dict):
            continue
        entries: set[str] | None = set()
        for key, value in zip(assignment.value.keys, assignment.value.values):
            pair = _literal_schema_pair(value)
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or pair is None:
                entries = None
                break
            entries.add(f"{pair[0]}/{pair[1]}.schema.json")
        if not entries:
            continue
        for name in names:
            registries[name] = entries
    aliases: dict[str, str] = {}
    for assignment in ast.walk(tree):
        if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
            continue
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        call = assignment.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "get"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in registries
        ):
            continue
        aliases[targets[0].id] = call.func.value.id
    resolved = dict(registries)
    for alias, name in aliases.items():
        resolved[alias] = registries[name]
    return resolved


def _starred_schema_targets(call: ast.Call, tree: ast.AST) -> set[str] | None:
    starred = [arg.value for arg in call.args if isinstance(arg, ast.Starred)]
    if len(starred) != 1:
        return None
    names = _closed_schema_registry_targets(tree)
    node = starred[0]
    if isinstance(node, ast.Name) and node.id in names:
        return set(names[node.id])
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in names
    ):
        return set(names[node.value.id])
    return None


def _schema_calls(tree: ast.AST, bindings: dict[str, str]) -> list[tuple[ast.Call, str]]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _resolved(node.func, bindings) != "core.schema.assert_valid":
            continue
        _require(len(node.args) >= 3 and all(isinstance(_literal(arg), str) for arg in node.args[1:3]),
                 "DYNAMIC_SCHEMA_SELECTOR")
        calls.append((node, f"{_literal(node.args[1])}/{_literal(node.args[2])}.schema.json"))
    return calls


def _schema_graph(root: Path) -> dict[str, set[str]]:
    graph = {}
    for path in sorted(root.rglob("*.schema.json")):
        _require(not path.is_symlink(), f"SCHEMA_SYMLINK:{path}")
        document = json.loads(path.read_text())
        refs = set()
        pending = [document]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"$ref", "$dynamicRef"}:
                        _require(isinstance(child, str) and "://" not in child, f"REMOTE_SCHEMA_REF:{path}")
                        target = unquote(child.split("#", 1)[0])
                        if target:
                            resolved = (path.parent / target).resolve()
                            _require(resolved.is_relative_to(root.resolve()) and resolved.is_file(),
                                     f"SCHEMA_REF_ESCAPE:{path}:{child}")
                            refs.add(resolved.relative_to(root.resolve()).as_posix())
                    pending.append(child)
            elif isinstance(value, list):
                pending.extend(value)
        graph[path.relative_to(root).as_posix()] = refs
    return graph


def _closure(graph: dict[str, set[str]], roots: list[str]) -> set[str]:
    pending, seen = list(roots), set()
    while pending:
        node = pending.pop()
        _require(node in graph, f"SCHEMA_MISSING:{node}")
        if node not in seen:
            seen.add(node)
            pending.extend(graph[node])
    return seen


def _load_tree(root: Path, relative: str) -> ast.Module:
    path = root / relative
    _require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
             f"SOURCE_MISSING_OR_ESCAPE:{relative}")
    return ast.parse(path.read_text(), filename=relative)


def _validate_boundary(root: Path, policy: dict, sources: dict[str, ast.Module]) -> dict[str, set[tuple[int, int, str]]]:
    """仅返回被声明及实际引用共同证明的节点，不返回文件/函数豁免。"""
    expected = {"spec_ref", "cli", "command", "subcommand", "registration", "register_function",
                "handler", "handler_function", "governed_call", "authority_verifier", "authority_purpose", "input_error_codes", "implementation", "freeze_function",
                "writer_function", "schema_root", "input_schemas", "input_closure", "evidence_schema",
                "lineage_schema", "output_schemas", "current_builder", "current_writer", "current_reader"}
    _require(set(policy) == expected, "POLICY_SHAPE")
    spec, anchor = policy["spec_ref"].split("#")
    _require(f'id="{anchor}"' in (root / spec).read_text(), "SPEC_ANCHOR_MISSING")
    impl_path, handler_path, cli_path = (policy[key] for key in ("implementation", "handler", "registration"))
    impl, handler, cli = (sources.get(path) or _load_tree(root, path) for path in (impl_path, handler_path, cli_path))
    module = _module(impl_path)
    handler_module = _module(handler_path)
    handler_name = policy["handler_function"]
    freeze = _function(impl, policy["freeze_function"])
    writer = _function(impl, policy["writer_function"])
    dispatch = _function(handler, handler_name)
    registration = _function(cli, policy["register_function"])
    bindings = _imports(impl)
    graph = _schema_graph(root / policy["schema_root"])
    old = set(policy["input_closure"])
    _require(_closure(graph, policy["input_schemas"]) == old, "INPUT_SCHEMA_CLOSURE_DRIFT")
    for schema, refs in graph.items():
        _require(schema in old or not refs & old, f"CURRENT_SCHEMA_REFERENCES_INPUT:{schema}")
    _require(not _closure(graph, policy["output_schemas"]) & old, "OUTPUT_SCHEMA_DUAL_READ")
    schema_calls = _schema_calls(impl, bindings)
    freeze_nodes = set(ast.walk(freeze))
    _require({name for _, name in _schema_calls(freeze, bindings)} == set(policy["input_schemas"]),
             "FREEZE_SCHEMA_DRIFT")
    _require(all(call in freeze_nodes for call, name in schema_calls if name in old), "OLD_SCHEMA_OUTSIDE_FREEZE")
    _require({name for _, name in schema_calls} == set(policy["input_schemas"] + [policy["evidence_schema"], policy["output_schemas"][-1]]),
             "IMPLEMENTATION_SCHEMA_DRIFT")
    for schema in old:
        document = json.loads((root / policy["schema_root"] / schema).read_text())
        _require(document.get("additionalProperties") is False, f"INPUT_SCHEMA_NOT_CLOSED:{schema}")

    # 唯一 CLI command 从现有 _COMMANDS 反推，不建立第二入口分发器。
    facade = _load_tree(root, policy["cli"])
    declarations = [node for node in ast.walk(facade) if isinstance(node, ast.Dict)]
    definitions = [value for node in declarations for key, value in zip(node.keys, node.values)
                   if _literal(key) == policy["command"] and isinstance(value, ast.Call)]
    _require(len(definitions) == 1 and [_literal(arg) for arg in definitions[0].args[:2]] ==
             [handler_module, policy["register_function"]], "CLI_FACADE_DRIFT")
    _require(_imports(handler).get(policy["register_function"]) ==
             f'{_module(cli_path)}.{policy["register_function"]}', "CLI_REGISTRATION_DRIFT")
    parser_assignments = [node for node in ast.walk(registration) if isinstance(node, ast.Assign)
                          and isinstance(node.value, ast.Call) and _name(node.value.func).endswith(".add_parser")
                          and node.value.args and _literal(node.value.args[0]) == policy["subcommand"]]
    _require(len(parser_assignments) == 1, "MIGRATION_COMMAND_MISSING")
    assignment = parser_assignments[0]
    _require(len(assignment.targets) == 1 and isinstance(assignment.targets[0], ast.Name), "CLI_DYNAMIC_PARSER")
    parser_name = assignment.targets[0].id
    registrations = [node for node in ast.walk(cli) if isinstance(node, ast.Call)
                     and any(keyword.arg == "handler" and _resolved(keyword.value, _imports(cli)) ==
                             f"{handler_module}.{handler_name}" for keyword in node.keywords)]
    _require(len(registrations) == 1 and _name(registrations[0].func) == f"{parser_name}.set_defaults",
             "CLI_HANDLER_NOT_ISOLATED")
    dispatch_bindings = _imports(dispatch)
    for function in (policy["freeze_function"], policy["writer_function"]):
        _require(dispatch_bindings.get(function) == f"{module}.{function}", "HANDLER_IMPORT_DRIFT")
    governed = _calls(dispatch, policy["governed_call"])
    _require(len(governed) == 1 and governed[0].args and isinstance(governed[0].args[0], ast.Name), "GOVERNED_CALL_MISSING")
    callback_name = governed[0].args[0].id
    callbacks = [node for node in ast.walk(dispatch) if isinstance(node, ast.FunctionDef) and node.name == callback_name]
    _require(len(callbacks) == 1, "GOVERNED_CALLBACK_MISSING")
    callback = callbacks[0]
    for function in (policy["freeze_function"], policy["writer_function"]):
        calls = [node for node in ast.walk(dispatch) if isinstance(node, ast.Call)
                 and _resolved(node.func, dispatch_bindings) == f"{module}.{function}"]
        _require(len(calls) == 1 and calls[0] in list(ast.walk(callback)), "UNFENCED_MIGRATION_CALL")

    # 当前固定代码形态的身份 guard 必须在任何 writer 调用之前且直接 raise。
    guards = [node for node in writer.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Compare) and len(node.test.ops) == 1
              and isinstance(node.test.ops[0], ast.Eq)
              and {_name(node.test.left), _name(node.test.comparators[0])} == {"source.release_id", "target_id"}
              and len(node.body) == 1 and isinstance(node.body[0], ast.Raise)]
    _require(len(guards) == 1, "TARGET_ID_NOT_PROVEN_FRESH")
    _require(not any(isinstance(node, (ast.Return, ast.Try, ast.With, ast.For, ast.While))
                     for node in writer.body[:writer.body.index(guards[0])]), "IDENTITY_GUARD_NOT_DOMINATING")
    target_assignments = [node for node in writer.body if isinstance(node, ast.Assign)
                          and any(_name(target) == "target_id" for target in node.targets)]
    _require(len(target_assignments) == 1 and isinstance(target_assignments[0].value, ast.Call)
             and _name(target_assignments[0].value.func) == "safe_release_id"
             and _name(target_assignments[0].value.args[0]) == "target_release_id", "TARGET_ID_BINDING_DRIFT")
    for identity in (policy["current_builder"], policy["current_writer"], policy["current_reader"]):
        calls = [node for node in ast.walk(writer) if isinstance(node, ast.Call) and _resolved(node.func, bindings) == identity]
        _require(calls and all(node.lineno > guards[0].lineno for node in calls), f"CURRENT_OUTPUT_CALL_MISSING:{identity}")
        if identity != policy["current_reader"]:
            _require(all(any(key.arg == "release_id" and _name(key.value) == "target_id" for key in call.keywords)
                         for call in calls), "OUTPUT_IDENTITY_DRIFT")
    _require(any(name == policy["output_schemas"][-1] and call.lineno > guards[0].lineno
                 for call, name in _schema_calls(writer, bindings)), "CURRENT_OUTPUT_VALIDATION_MISSING")

    # current reader/writer 必须确实可达现役 schema 校验，不只匹配调用名称。
    for identity in (policy["current_reader"], policy["current_writer"]):
        module_name, _, function_name = identity.rpartition(".")
        path = "quwoquan_data/scripts/" + module_name.replace(".", "/") + ".py"
        current = sources.get(path) or _load_tree(root, path)
        current_bindings = _imports(current)
        functions = {node.name: node for node in current.body if isinstance(node, ast.FunctionDef)}
        pending, visited, schemas = [function_name], set(), set()
        while pending:
            name = pending.pop()
            _require(name in functions, f"CURRENT_FUNCTION_MISSING:{identity}")
            if name in visited:
                continue
            visited.add(name)
            function = functions[name]
            schemas.update(schema for _, schema in _schema_calls(function, current_bindings))
            pending.extend(node.func.id for node in ast.walk(function) if isinstance(node, ast.Call)
                           and isinstance(node.func, ast.Name) and node.func.id in functions)
        _require(set(policy["output_schemas"]) <= schemas and not schemas & old,
                 f"CURRENT_SCHEMA_VALIDATION_UNPROVEN:{identity}")

    # 只认可专用实现声明的导出类型/函数/常量及它们的 AST 引用。
    approved: dict[str, set[tuple[int, int, str]]] = {}
    def approve(path: str, node: ast.AST, text: str) -> None:
        # 绑定 token 的行列，而不是整行；同一行追加同名旁路也不获准。
        lines = (root / path).read_text().splitlines()
        for number in range(node.lineno, node.end_lineno + 1):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and number != node.lineno:
                break
            line = lines[number - 1]
            left = len(line.encode()[:node.col_offset].decode()) if number == node.lineno else 0
            right = len(line.encode()[:node.end_col_offset].decode()) if number == node.end_lineno else len(line)
            fragment = line[left:right]
            position = fragment.find(text)
            if position >= 0:
                approved.setdefault(path, set()).update((number, left + position + match.start(), match.group())
                                                        for match in RETIRED_IDENTIFIER.finditer(text))

    symbols = {policy["freeze_function"], policy["writer_function"]}
    _require(isinstance(freeze.returns, ast.Name), "FROZEN_SOURCE_TYPE_MISSING")
    frozen_type = freeze.returns.id
    classes = {node.name: node for node in impl.body if isinstance(node, ast.ClassDef)}
    _require(frozen_type in classes and any(isinstance(node, ast.Call) and _name(node.func) == "dataclass"
             and any(key.arg == "frozen" and _literal(key.value) is True for key in node.keywords)
             for node in classes[frozen_type].decorator_list), "SOURCE_NOT_FROZEN")
    symbols.add(frozen_type)
    error_helper = _function(impl, "_error")
    _require(isinstance(error_helper.returns, ast.Name), "TYPED_ERROR_MISSING")
    error_type = error_helper.returns.id
    _require(error_type in classes and any(_name(base) == "ObjectTransactionError" for base in classes[error_type].bases), "TYPED_ERROR_BASE_DRIFT")
    symbols.add(error_type)
    for node in impl.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(item, ast.Name) and item.id == node.targets[0].id for item in ast.walk(freeze)):
                source_schema = json.loads((root / policy["schema_root"] / policy["input_schemas"][0]).read_text())["properties"]["schema"]["const"]
                if node.value.value == source_schema and isinstance(node.targets[0], ast.Name):
                    symbols.add(node.targets[0].id)
    for node in ast.walk(impl):
        if isinstance(node, ast.Name) and node.id in symbols:
            approve(impl_path, node, node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in symbols:
            approve(impl_path, node, node.name)
        elif isinstance(node, ast.Call) and _name(node.func) == "_error" and node.args:
            code = _literal(node.args[0])
            if code in policy["input_error_codes"] and node in list(ast.walk(freeze)):
                approve(impl_path, node.args[0], code)
    for call, schema in schema_calls:
        approve(impl_path, call.args[2], str(_literal(call.args[2])))
        for keyword in call.keywords:
            if keyword.arg == "label" and isinstance(keyword.value, ast.Constant):
                approve(impl_path, keyword.value, str(keyword.value.value))
    # lineage 是现役事实，不是旧输入 schema；只能位于 schema 判别字段。
    lineage = json.loads((root / policy["schema_root"] / policy["lineage_schema"]).read_text())
    for node in ast.walk(impl):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _literal(key) == "schema" and _literal(value) == lineage["properties"]["schema"]["const"]:
                    approve(impl_path, value, str(_literal(value)))
        if isinstance(node, ast.Call) and _name(node.func) == frozen_type:
            for arg in node.args:
                if _literal(arg) == Path(policy["input_schemas"][0]).name.removesuffix(".schema.json"):
                    approve(impl_path, arg, str(_literal(arg)))
        if isinstance(node, ast.Call) and _resolved(node.func, bindings) == policy["authority_verifier"]:
            for keyword in node.keywords:
                if keyword.arg == "purpose" and _literal(keyword.value) == policy["authority_purpose"]:
                    approve(impl_path, keyword.value, str(_literal(keyword.value)))
    approve(handler_path, dispatch, handler_name)
    for node in ast.walk(dispatch):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            approve(handler_path, node, node.module)
            for alias in node.names:
                _require(alias.name in {policy["freeze_function"], policy["writer_function"]}, "HANDLER_EXPORT_DRIFT")
                approve(handler_path, node, alias.name)
        if isinstance(node, ast.Name) and node.id in {policy["freeze_function"], policy["writer_function"]}:
            approve(handler_path, node, node.id)
    approve(cli_path, assignment.value.args[0], policy["subcommand"])
    for keyword in assignment.value.keywords:
        if keyword.arg == "help" and isinstance(keyword.value, ast.Constant):
            approve(cli_path, keyword.value, str(keyword.value.value))
    for keyword in registrations[0].keywords:
        if keyword.arg == "handler":
            approve(cli_path, keyword.value, handler_name)

    # 所有普通源文件（含别名 import）均不得消费隔离旧输入或迁移实现。
    old_names = {Path(name).name.removesuffix(".schema.json") for name in old}
    forbidden_modules = {module, f"{handler_module}.{handler_name}"}
    for path, tree in sources.items():
        source_bindings = _imports(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = _resolved(node.func, source_bindings)
                if callee in {"importlib.import_module", "__import__"}:
                    argument = node.args[0] if node.args else None
                    exact = _static_strings(argument, tree) if argument is not None else None
                    if exact is not None:
                        _require(not any(_loads_implementation(value, module) for value in exact),
                                 f"DYNAMIC_IMPORTS_MIGRATION:{path}:{node.lineno}")
                        continue
                    prefixes = _leading_prefixes(argument, tree) if argument is not None else set()
                    if prefixes:
                        _require(not any(_prefix_can_load(prefix, module) for prefix in prefixes),
                                 f"DYNAMIC_IMPORTS_MIGRATION:{path}:{node.lineno}")
                        continue
                    # Data 的 content.* 就在 scripts import 根上；无法证明的开放加载 fail closed。
                    # 其它树只有可证明目标/前缀命中实现模块才算双读，避免把 Ops 插件加载器当成 schema reader。
                    _require(not path.startswith("quwoquan_data/scripts/"),
                             f"DYNAMIC_IMPORT_UNPROVEN:{path}:{node.lineno}")
                    continue
                if callee in {"exec", "eval"}:
                    raise BoundaryError(f"DYNAMIC_EXECUTION_UNPROVEN:{path}:{node.lineno}")
                if callee == "core.schema.assert_valid":
                    registry_targets = _starred_schema_targets(node, tree)
                    if registry_targets is not None:
                        _require(
                            path == impl_path or not registry_targets & old,
                            f"RUNTIME_SCHEMA_DUAL_READ:{path}:{node.lineno}",
                        )
                        _require(
                            all(".." not in Path(name).parts for name in registry_targets),
                            f"SCHEMA_SELECTOR_ESCAPE:{path}:{node.lineno}",
                        )
                        continue
                    namespaces = _static_strings(node.args[1], tree) if len(node.args) > 1 else None
                    selectors = _static_strings(node.args[2], tree) if len(node.args) > 2 else None
                    if namespaces is not None and selectors is not None:
                        resolved_schemas = {f"{namespace}/{selector}.schema.json" for namespace in namespaces for selector in selectors}
                        _require(path == impl_path or not resolved_schemas & old, f"RUNTIME_SCHEMA_DUAL_READ:{path}:{node.lineno}")
                        _require(all(".." not in Path(name).parts for name in resolved_schemas), f"SCHEMA_SELECTOR_ESCAPE:{path}:{node.lineno}")
                        continue
                    namespace = _literal(node.args[1]) if len(node.args) > 1 else None
                    selector = node.args[2] if len(node.args) > 2 else None
                    if isinstance(namespace, str) and namespace not in {name.split("/", 1)[0] for name in old}:
                        # 仅无路径分隔的 literal 或唯一 Path.stem 赋值可证明不穿越 namespace。
                        literal = _literal(selector)
                        assignments = [item for item in ast.walk(tree) if isinstance(item, ast.Assign)
                                       and isinstance(selector, ast.Name) and any(_name(target) == selector.id for target in item.targets)]
                        stem_only = len(assignments) == 1 and isinstance(assignments[0].value, ast.Attribute) and assignments[0].value.attr == "stem"
                        owners = [item for item in tree.body if isinstance(item, ast.FunctionDef) and node in set(ast.walk(item))]
                        callers = [item for item in ast.walk(tree) if isinstance(item, ast.Call) and owners and _name(item.func) == owners[0].name]
                        values = [keyword.value for caller in callers for keyword in caller.keywords
                                  if isinstance(selector, ast.Name) and keyword.arg == selector.id]
                        finite_arguments = bool(callers) and len(values) == len(callers) and all(isinstance(_literal(value), str)
                                           and "/" not in _literal(value) and "\\\\" not in _literal(value) for value in values)
                        if (isinstance(literal, str) and "/" not in literal and "\\\\" not in literal) or stem_only or finite_arguments:
                            continue
                    try:
                        calls = _schema_calls(node, source_bindings)
                    except BoundaryError as error:
                        raise BoundaryError(f"{error}:{path}:{node.lineno}") from error
                    _require(path == impl_path or all(schema not in old for _, schema in calls),
                             f"RUNTIME_SCHEMA_DUAL_READ:{path}:{node.lineno}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = _imports(node).values()
                for identity in imported:
                    if any(identity == item or identity.startswith(item + ".") for item in forbidden_modules):
                        _require(path == handler_path and node in list(ast.walk(dispatch)) and isinstance(node, ast.ImportFrom)
                                 and node.module == module, f"RUNTIME_IMPORTS_MIGRATION:{path}:{node.lineno}")
            if isinstance(node, ast.Attribute) and _resolved(node, source_bindings) == f"{handler_module}.{handler_name}":
                _require(path == cli_path and node in list(ast.walk(registrations[0])), f"RUNTIME_CALLS_HANDLER:{path}:{node.lineno}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                sensitive = value in old_names or any(name in value for name in old) or module in value
                if sensitive:
                    _require(path == impl_path and any(item[0] == node.lineno and item[2] in RETIRED_IDENTIFIER.findall(value) for item in approved.get(path, set())),
                             f"RUNTIME_REFERENCES_INPUT:{path}:{node.lineno}")
    return approved


def _migration_boundaries(root: Path, sources: dict[str, ast.Module]) -> tuple[dict[str, set[tuple[int, int, str]]], list[str]]:
    path = root / POLICY
    if not path.exists():
        return {}, []  # 无声明不认可任何迁移身份，词法门仍严格执行。
    try:
        document = json.loads(path.read_text())
        _require(set(document) == {"schema_version", "_governance", "boundaries"} and document["schema_version"] == 1, "POLICY_VERSION")
        approved: dict[str, set[tuple[int, int, str]]] = {}
        for boundary in document["boundaries"]:
            for source, values in _validate_boundary(root, boundary, sources).items():
                approved.setdefault(source, set()).update(values)
        return approved, []
    except (BoundaryError, OSError, SyntaxError, ValueError, KeyError, TypeError, IndexError) as error:
        return {}, [f"MIGRATION_BOUNDARY_INVALID:{error}"]

import yaml

ROOT = REPO_ROOT
RUNTIME_ROOTS = (
    "quwoquan_app/lib",
    "quwoquan_app/android/app/src",
    "quwoquan_app/ios/Runner",
    "quwoquan_service/contracts/metadata",
    "quwoquan_service/runtime",
    "quwoquan_service/services",
    "quwoquan_data/control_plane",
    "quwoquan_data/scripts/core",
    "quwoquan_data/scripts/content",
    "quwoquan_data/scripts/governance",
    "quwoquan_ops/cli",
    "quwoquan_ops/environments",
    "quwoquan_ops/observability",
    "quwoquan_ops/portal/src",
)

SKIP_DIR_NAMES = {
    ".dart_tool",
    ".qwq_output",
    "__pycache__",
    "build",
    "node_modules",
    "test",
    "tests",
    "testdata",
    "vendor",
}

SOURCE_SUFFIXES = {
    ".dart",
    ".go",
    ".java",
    ".json",
    ".kt",
    ".mjs",
    ".py",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

# This gate targets executable compatibility identities, not natural-language
# history. Negative tests and governance scanners have their own contract gates.
RETIRED_IDENTIFIER = re.compile(
    r"\b(?:"
    r"(?i:legacy)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]+(?:Legacy|_legacy)[A-Za-z0-9_]*|"
    r"compat(?:Mode|Parser|Shim|Alias|Fallback)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]+Compat(?:Mode|Parser|Shim|Alias|Fallback)[A-Za-z0-9_]*"
    r")\b"
)

# 退役内容轴身份：ContentType.micro、ContentIdentity.moment、Post.contentIdentity、
# 读侧派生 displayFormat、点滴升级作品命令与事件。同上只认可执行的兼容身份，
# 中文说明与散文历史不在范围内。
RETIRED_CONTENT_AXIS = re.compile(
    # ContentType 退役成员只作为独立 token 出现（'micro'、ContentType.micro、YAML
    # 闭集项）。micro-batch、microseconds、microtask、microphone、microblog 是别的
    # 词，不是该成员，因此边界同时排除连字符与下划线。
    r"(?<![A-Za-z0-9_-])micro(?![A-Za-z0-9_-])"
    r"|(?i:content_?(?:type|surface_?kind)_?micro)"
    # ContentIdentity 退役成员只作为值位置的字面量或 Identity 族成员访问出现。
    # 字段名位置是别的字段：intersection 的意图时态 moment 就住在 JSON/YAML key 与
    # 序列化 tag 里，本地时间戳变量同样不带引号。
    r"|(?<![A-Za-z0-9_])(?<!json:)(?<!bson:)(?<!yaml:)(?<!db:)(?<!form:)(?<!query:)"
    r"(?P<moment_quote>['\"])moment(?P=moment_quote)(?!\s*:)"
    r"|[A-Za-z0-9_]*Identity\.moment(?![A-Za-z0-9_])"
    # ContentIdentity 本体，含 codegen 的 ContentIDentity 拼写。snake_case
    # content_identity 在本仓另有语义（release 内容身份、ops 样本身份校验），
    # 不是该枚举的兼容身份。要求标识符右边界，避免将独立 assistant indexing
    # 开关中的 ContentIdentityIndex 当成枚举；规格明确退役的 Outcome 投影仍阻断。
    r"|[Cc]ontent(?:Id|ID)entity(?:Outcome)?(?![A-Za-z0-9_])"
    # 读侧派生轴。
    r"|(?i:display_?format)"
    # 点滴升级作品命令 PromotePostToWork 与事件 PostPromotedToWork；尾部排除小写
    # 续写，避免误伤 to_workspace 一类无关词。
    r"|(?i:promoted?_?(?:post_?)?to_?work)(?![a-z])"
    # 按类型拆分的互动指标不能保留退役类型的组合名；只匹配完整指标标识符，
    # 不把意图时态、WechatMoments、Momentary 或 photo library 当作内容类型。
    r"|(?<![A-Za-z0-9_])(?i:(?:impression|deep_?engage|click|like|share|comment)_?(?:moment|photo))(?![A-Za-z0-9_])"
)

# ContentIdentity 闭集是 {moment, work}：同一行同时出现两个裸成员即闭集声明。
# 单独的意图时态 moment 与工作流语义 work 不会同行出现。
IDENTITY_MEMBER_MOMENT = re.compile(r"(?<![A-Za-z0-9_-])moment(?![A-Za-z0-9_-])")
IDENTITY_MEMBER_WORK = re.compile(r"(?<![A-Za-z0-9_-])work(?![A-Za-z0-9_-])")

# displayFormat 语义下的 note 才是退役展示形态。笔记字段、gathering plan 的
# PlanItemKindNote、认领备注与 JSON 注记都不是展示形态，因此要求同一展示形态
# 词表就在附近：displayFormat 本体，或同一映射里的 photo / micro 兄弟取值。
DISPLAY_FORMAT_NOTE = re.compile(r"(?<![A-Za-z0-9_])(?P<note_quote>['\"])note(?P=note_quote)")
DISPLAY_FORMAT_CONTEXT = re.compile(
    r"(?i:display_?format)|(?P<sibling_quote>['\"])(?:photo|micro)(?P=sibling_quote)"
)
DISPLAY_FORMAT_WINDOW = 6

# 退役取值的 canonical 声明点是共享 enum owner 的 `retired_enum_values`，生成链把
# 同一条记录投影成 Go 记录。两种形态都把 enum 与退役取值绑在同一行，所以退役取值
# 永远不会作为裸字面量出现，而形态里没有第三个键可以夹带别的语义。
RETIRED_VALUE_SOURCE = "quwoquan_service/contracts/metadata/_shared/types.yaml"
RETIRED_VALUE_DECLARATION = re.compile(
    r"\{\s*enum:\s*(?P<enum>[A-Za-z][A-Za-z0-9_]*)\s*,"
    r"\s*retired_value:\s*(?P<value>[A-Za-z0-9_]+)\s*\}"
)
RETIRED_VALUE_PROJECTION = re.compile(
    r"\{\s*Enum:\s*\"(?P<enum>[A-Za-z][A-Za-z0-9_]*)\"\s*,"
    r"\s*RetiredValue:\s*\"(?P<value>[A-Za-z0-9_]+)\"\s*\}"
)


def _declared_retired_values(document: object) -> frozenset[tuple[str, str]]:
    """把 canonical 声明化为被接受的 (enum, 退役取值) 对。

    这不是按位置豁免：声明自身不成立的对根本不进集合，它在任何位置（包括声明
    文件本身与生成投影）都照旧 BLOCK。记录形态不完整、取值空白、enum 未声明，
    以及取值仍在该 enum 的合法闭集内，都不产生任何接受。
    """
    if not isinstance(document, dict):
        return frozenset()
    enums = document.get("enums")
    records = document.get("retired_enum_values")
    if not isinstance(enums, dict) or not isinstance(records, list):
        return frozenset()
    declared: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"enum", "retired_value"}:
            continue
        name, value = record["enum"], record["retired_value"]
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        name, value = name.strip(), value.strip()
        closed_set = enums.get(name)
        if not name or not value or not isinstance(closed_set, list):
            continue
        if value in closed_set:
            continue
        declared.add((name, value))
    return frozenset(declared)


def _canonical_retired_values(root: Path) -> frozenset[tuple[str, str]]:
    """读取 canonical 声明；缺失或无法解析时返回空集合，于是不接受任何退役取值。"""
    source = root / RETIRED_VALUE_SOURCE
    if not source.is_file():
        return frozenset()
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        return frozenset()
    return _declared_retired_values(document)


def _without_retired_value_records(
    line: str, declared: frozenset[tuple[str, str]]
) -> str:
    """只屏蔽 canonical 记录里的那一个退役取值，行内其余内容照常受全部判据约束。"""

    def mask(match: re.Match[str]) -> str:
        if (match.group("enum"), match.group("value")) not in declared:
            return match.group(0)
        record = match.group(0)
        start, end = match.span("value")
        offset = match.start()
        return record[: start - offset] + " " * (end - start) + record[end - offset :]

    for pattern in (RETIRED_VALUE_DECLARATION, RETIRED_VALUE_PROJECTION):
        line = pattern.sub(mask, line)
    return line


def _is_runtime_source(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if path.name == "package-lock.json":
        return False
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    return not (
        path.name.endswith("_test.go")
        or path.name.endswith("_test.dart")
        or path.name.startswith("test_")
    )


# 字符串优先于注释，保留 URL、wire 字面量及 Go struct tag；屏蔽时保留换行以维持定位。
QUOTED_TOKEN = r'''"""[\s\S]*?"""|\x27\x27\x27[\s\S]*?\x27\x27\x27|"(?:\\.|[^"\\])*"|'(?:\\.|''|[^'\\])*'|`[^`]*`'''
YAML_DESCRIPTION = re.compile(r'''(?<![^\s{,?])(?:description|"description"|'description')[ \t]*:[ \t]*''')
YAML_TOKEN = re.compile(QUOTED_TOKEN + r"|[^\s]")


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _without_comments(text: str, suffix: str) -> str:
    comments = r"\#[^\n]*" if suffix in {".py", ".sh", ".yaml", ".yml"} else r"//[^\n]*|/\*[\s\S]*?\*/"
    if suffix in {".yaml", ".yml"}:
        comments = r"(?<!\S)\#[^\n]*"
    if suffix == ".json":
        return text
    tokens = re.compile(f"({QUOTED_TOKEN})|(?:{comments})")
    return tokens.sub(lambda match: match.group(0) if match.group(1) else _blank(match.group(0)), text)


def _yaml_description_end(text: str, token: re.Match[str], flow_depth: int) -> int:
    if flow_depth:
        return next(
            (part.start() for part in YAML_TOKEN.finditer(text, token.end())
             if part.group(0) in {",", "}", "]"}),
            len(text),
        )
    # block scalar、折叠标量、普通多行标量均由缩进决定边界。
    line_start = text.rfind("\n", 0, token.start()) + 1
    prefix = text[line_start:token.start()]
    indent = len(prefix) if prefix.strip() == "-" else len(prefix) - len(prefix.lstrip())
    end = text.find("\n", token.end())
    if end < 0:
        return len(text)
    end += 1
    for line in text[end:].splitlines(keepends=True):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        end += len(line)
    return end


def _without_yaml_descriptions(text: str) -> str:
    """只移除 description 的标量值，绝不忽略整行或同行其他映射成员。"""
    tokens = re.compile(YAML_DESCRIPTION.pattern + "|" + QUOTED_TOKEN + r"|[^\s]")
    masked = list(text)
    flow_depth = 0
    skip_until = 0
    for token in tokens.finditer(text):
        if token.start() < skip_until:
            continue
        value = token.group(0)
        if value in {"{", "["}:
            flow_depth += 1
        elif value in {"}", "]"}:
            flow_depth -= 1
        elif YAML_DESCRIPTION.fullmatch(value):
            start = token.end()
            # 容器值不是自然语言描述；必须继续扫描其中的 executable 内容。
            if text[start:start + 1] in {"{", "["}:
                continue
            end = _yaml_description_end(text, token, flow_depth)
            masked[start:end] = _blank(text[start:end])
            skip_until = end
    return "".join(masked)


def _findings(
    relative_path: str,
    lines: list[str],
    declared_retired: frozenset[tuple[str, str]],
) -> list[str]:
    suffix = Path(relative_path).suffix
    text = _without_comments("\n".join(lines), suffix)
    if suffix in {".yaml", ".yml"}:
        text = _without_yaml_descriptions(text)
    lines = [
        _without_retired_value_records(line, declared_retired)
        for line in text.split("\n")
    ]
    findings: list[str] = []
    for index, line in enumerate(lines):
        line_number = index + 1
        for pattern in (RETIRED_IDENTIFIER, RETIRED_CONTENT_AXIS):
            match = pattern.search(line)
            if match:
                findings.append(f"{relative_path}:{line_number}:{match.group(0)}")
        # 下面两条判据各自都要求行内出现字面子串，所以先做子串预筛与直接跑正则等价，
        # 只是省掉大部分行的回溯开销。
        if ("moment" in line and "work" in line
                and IDENTITY_MEMBER_MOMENT.search(line) and IDENTITY_MEMBER_WORK.search(line)):
            findings.append(f"{relative_path}:{line_number}:ContentIdentity{{moment,work}}")
        note = DISPLAY_FORMAT_NOTE.search(line) if "note" in line else None
        window = lines[max(0, index - DISPLAY_FORMAT_WINDOW) : index + DISPLAY_FORMAT_WINDOW + 1]
        if note and any(DISPLAY_FORMAT_CONTEXT.search(near) for near in window):
            findings.append(f"{relative_path}:{line_number}:displayFormat={note.group(0)}")
    return findings


def _self_test() -> None:
    declared = frozenset({("ContentType", "micro")})
    rejected = (
        ("final legacyAvailable = true;",),
        ('const wireKey = "legacyMedia";',),
        ("compatMode: enabled",),
        ("ImpressionMoment atomic.Int64",),
        ('"deep_engage_moment": counter.Load(),',),
        ("ClickPhoto atomic.Int64",),
        ('"comment_photo": counter.Load(),',),
        ("report_dir_legacy = output",),
        ("      case ContentType.micro:",),
        ("enum ContentSurfaceKind { micro, image, video, article }",),
        ("      'contentType': 'micro',",),
        ('  static const String searchContentTypeMicro = "text";',),
        ("      identity: 'moment',",),
        ('	if p.ContentIdentity != "moment" {',),
        ("        return CreateContentIdentity.moment;",),
        ("enum CreateContentIdentity { moment, work }",),
        ('VALID_WORKS_AFFINITIES = ("work_strong", "work", "neutral", "moment")',),
        ("  final identity = wire.contentIdentity?.trim() ?? '';",),
        ("	ContentIdentity   string   `json:\"contentIdentity\"`",),
        ("      - {name: contentIdentity, type: ContentIdentity}",),
        ("type ContentIDentity string",),
        ("String? contentIdentityOutcome;",),
        ("class AppTelemetryValueContentIdentityOutcome {}",),
        ("- {description: 'micro 已退役', values: [micro, image]}",),
        ("- {values: [micro, image], description: micro 已退役}",),
        ("- {description: '不用 micro', type: ContentIDentity}",),
        ("        displayFormat: switch (type) {",),
        ("  bool get isTextOnly => displayFormat == 'note' && !hasAnyMedia;",),
        ('	case "PromotePostToWork":',),
        ("      metric: 'content_post_promote_to_work',",),
        ("	OperationID: \"content.post.PostPromotedToWork\",",),
        ("        displayFormat: switch (type) {", "          'article' => 'note',", "        };"),
        ('	case "photo":', '		return "image"', '	case "note":', '		return "article"'),
        # canonical 记录的近似形态不构成声明：键名不对、缺 enum 归属、夹带第三个
        # 键、记录外的裸键，以及手写常量，都必须照旧命中。
        ("  - {enum: ContentType, value: micro}",),
        ("  - {enum: ContentType, retired: micro}",),
        ("  - {retired_value: micro}",),
        ("  - {enum: ContentType, retired_value: micro, accept_on_wire: true}",),
        ("  retired_value: micro",),
        ('	const retiredContentType = "micro"',),
        ('	{RetiredValue: "micro"},',),
        ('	{Enum: "ContentType", RetiredValue: "micro", Accept: true},',),
        # 形态正确但这一对没有 canonical 声明：别的 enum 借不到 ContentType 的声明。
        ("  - {enum: MediaType, retired_value: micro}",),
        ('	{Enum: "MediaType", RetiredValue: "micro"},',),
        # 整个 enum 已退役时不得借退役槽复活它的成员。
        ("  - {enum: ContentIdentity, retired_value: moment}",),
    )
    accepted = (
        ("- {name: enableAssistantContentIdentityIndex, type: bool}",),
        ("EnableAssistantContentIdentityIndex *bool",),
        ("?flags.enableAssistantContentIdentityIndex,",),
        ("description: micro 与 ContentIdentity 已退役",),
        ("- {name: contentType, description: micro 已退役}",),
        ("description: |", "  micro 已退役", "type: string"),
        ("final availability = OneTapAvailability.available;",),
        ("compatibleRuntimeVersion: current",),
        ("final comparison = left == right;",),
        ("        - micro_batch_window_2ms          # micro-batch merge",),
        ("    microblog: { baseTier: tier4_casual }",),
        ("final ts = DateTime.now().microsecondsSinceEpoch;",),
        ("    Future<void>.microtask(_load);",),
        ("      AppPermissionKind.microphone,",),
        ("	issuedAt := time.Now().UTC().Truncate(time.Microsecond)",),
        ("	elapsed := float64(time.Since(started).Microseconds()) / 1000.0",),
        ("	return strconv.FormatInt(now.UnixMicro(), 36)",),
        ("    moment: retrospective",),
        ('  "moment": "prospective",',),
        ("	Moment  string  `json:\"moment\"`",),
        ("- name: moment",),
        ("    moment: str",),
        ("    moment = now if now is not None else int(time.time())",),
        ('        "checkedAt": moment,',),
        ("enum NativeShareTarget { wechatFriend, wechatMoments }",),
        ("                    : 'wechat_moments',",),
        ("        readback.createdAt.isAtSameMomentAs(receipt.createdAt);",),
        ("          momentId: marker['momentId'] as String,",),
        ('  "trip-moment-content-link": { "owner": "content" }',),
        ('var IntersectionMoments = []string{"retrospective", "current"}',),
        ("def _content_identity(value: object, *, field: str) -> str:",),
        ("    identity = load_release_content_identity(release_root)",),
        ("	PlanItemKindNote PlanItemKind = \"note\"",),
        ("      note: (json['note'] as String?)?.trim() ?? '',",),
        ("	Note  string  `json:\"note\"`",),
        ('  "notes": ["first"],',),
        ("    await center.publish(Notification.draftSaved);",),
        ("    articleTemplate: ArticleTemplate.notePaper,",),
        ('    summary["note"] = "lane acceptance only"',),
        ("    workspacePromotion = resolve_promote_to_workspace(plan)",),
    )
    for fixture in rejected:
        if not _findings("self_test.yaml", list(fixture), declared):
            raise AssertionError(
                f"retired identifier detector missed a control fixture: {fixture!r}"
            )
    for fixture in accepted:
        rejections = _findings("self_test.yaml", list(fixture), declared)
        if rejections:
            raise AssertionError(
                f"retired identifier detector rejected a current fixture: {rejections}"
            )
    _self_test_retired_declaration(declared)


def _self_test_retired_declaration(declared: frozenset[tuple[str, str]]) -> None:
    """canonical 声明与其生成投影必须成对成立：声明在，两者都通过；声明不在，
    两者都 BLOCK。缺了后半句，任何文件抄一份记录形态就能自行豁免。"""
    canonical = (
        ("self_test.yaml", ("  - {enum: ContentType, retired_value: micro}",)),
        ("self_test.go", ('\t{Enum: "ContentType", RetiredValue: "micro"},',)),
    )
    for path, fixture in canonical:
        rejections = _findings(path, list(fixture), declared)
        if rejections:
            raise AssertionError(
                f"retired value declaration missed a control fixture: {rejections}"
            )
        if not _findings(path, list(fixture), frozenset()):
            raise AssertionError(
                "retired value declaration missed a control fixture: "
                f"{fixture!r} was accepted without a canonical declaration"
            )
    live = {"enums": {"ContentType": ["image", "video", "article"]}}
    valid = {**live, "retired_enum_values": [{"enum": "ContentType", "retired_value": "micro"}]}
    if _declared_retired_values(valid) != declared:
        raise AssertionError(
            "retired value declaration missed a control fixture: canonical record was not resolved"
        )
    invalid = {
        "blank value": [{"enum": "ContentType", "retired_value": "  "}],
        "still in closed set": [{"enum": "ContentType", "retired_value": "article"}],
        "unknown enum": [{"enum": "MediaType", "retired_value": "micro"}],
        "missing enum": [{"retired_value": "micro"}],
        "extra key": [{"enum": "ContentType", "retired_value": "micro", "accept_on_wire": True}],
        "mapping instead of records": {"ContentType": ["micro"]},
    }
    for name, records in invalid.items():
        if _declared_retired_values({**live, "retired_enum_values": records}):
            raise AssertionError(
                f"retired value declaration missed a control fixture: {name} was accepted"
            )


def main() -> int:
    _self_test()
    declared_retired = _canonical_retired_values(ROOT)
    files: dict[str, list[str]] = {}
    sources: dict[str, ast.Module] = {}
    findings: list[str] = []
    for relative_root in RUNTIME_ROOTS:
        source_root = ROOT / relative_root
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or not _is_runtime_source(path):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(ROOT).as_posix()
            files[rel] = lines
            if path.suffix == ".py":
                try:
                    sources[rel] = ast.parse("\n".join(lines), filename=rel)
                except SyntaxError as error:
                    findings.append(f"SOURCE_PARSE_FAILED:{rel}:{error.lineno}")
    approved, boundary_findings = _migration_boundaries(ROOT, sources)
    findings.extend(boundary_findings)
    for rel, lines in files.items():
        prose_lines: set[int] = set()
        if rel in sources:
            for node in ast.walk(sources[rel]):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        prose_lines.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
        allowed = approved.get(rel, set())
        for finding in _findings(rel, lines, declared_retired):
            _, line_s, token = finding.rsplit(":", 2)
            line_no = int(line_s)
            if line_no in prose_lines:
                continue
            line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            identifier_cols = [
                match.start()
                for match in RETIRED_IDENTIFIER.finditer(line)
                if match.group() == token
            ]
            if identifier_cols and all(
                (line_no, column, token) in allowed for column in identifier_cols
            ):
                continue
            findings.append(finding)

    if findings:
        print("verify_retired_terms_zero: FAIL")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
