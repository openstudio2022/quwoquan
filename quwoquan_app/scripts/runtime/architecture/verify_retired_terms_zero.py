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


def _is_comment_only(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith(("#", "//", "/*", "*", "<!--"))


def _self_test() -> None:
    rejected = (
        "final legacyAvailable = true;",
        'const wireKey = "legacyMedia";',
        "compatMode: enabled",
        "report_dir_legacy = output",
    )
    accepted = (
        "final availability = OneTapAvailability.available;",
        "compatibleRuntimeVersion: current",
        "final comparison = left == right;",
    )
    if not all(RETIRED_IDENTIFIER.search(value) for value in rejected):
        raise AssertionError("retired identifier detector missed a control fixture")
    if any(RETIRED_IDENTIFIER.search(value) for value in accepted):
        raise AssertionError("retired identifier detector rejected a current fixture")


def main() -> int:
    _self_test()
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
            # 文档字符串与纯注释相同，不是可执行兼容身份。
            for node in ast.walk(sources[rel]):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                        prose_lines.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
        for line_number, line in enumerate(lines, start=1):
            if _is_comment_only(line) or line_number in prose_lines:
                continue
            for match in RETIRED_IDENTIFIER.finditer(line):
                if (line_number, match.start(), match.group()) not in approved.get(rel, set()):
                    findings.append(f"{rel}:{line_number}:{match.group()}")

    if findings:
        print("verify_retired_terms_zero: FAIL")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
