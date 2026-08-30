"""Reachability-aware Python subprocess command projection."""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

_SUBPROCESS_EXECUTORS = {"call", "check_call", "check_output", "Popen", "run"}
_CONTINUES = "continues"
_SUBPROCESS_MODULE_MARKER = "__qwq_subprocess_module__"


@dataclass(frozen=True)
class _FlowSnapshot:
    bindings: dict[str, ast.AST]
    outcome: str = _CONTINUES


def reachable_subprocess_command_tokens(
    module: ast.Module,
    *,
    function_name: str,
    executable_parameter: str,
) -> tuple[tuple[str, ...], ...]:
    """Return every subprocess command reachable from one module function."""

    collector = _ReachableSubprocessCollector(module, executable_parameter)
    collector.walk_function(function_name)
    return tuple(collector.commands)


class _ReachableSubprocessCollector:
    def __init__(self, module: ast.Module, executable_parameter: str) -> None:
        self._executable_parameter = executable_parameter
        self._functions = {
            node.name: node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self._subprocess_modules: set[str] = set()
        self._subprocess_executors: set[str] = set()
        self._possible_subprocess_modules: set[str] = set()
        self._possible_subprocess_executors: set[str] = set()
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "subprocess":
                        self._possible_subprocess_modules.add(
                            alias.asname or alias.name
                        )
            elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                for alias in node.names:
                    if alias.name in _SUBPROCESS_EXECUTORS:
                        self._possible_subprocess_executors.add(
                            alias.asname or alias.name
                        )
        self._module_bindings: dict[str, ast.AST] = {}
        for statement in module.body:
            self._record_module_statement(statement)
        self._call_stack: list[int] = []
        self.commands: list[tuple[str, ...]] = []

    def _record_module_statement(self, statement: ast.stmt) -> None:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name == "subprocess":
                    name = alias.asname or alias.name
                    self._subprocess_modules.add(name)
                    self._module_bindings[name] = _subprocess_module_marker()
            return
        if isinstance(statement, ast.ImportFrom) and statement.module == "subprocess":
            for alias in statement.names:
                if alias.name in _SUBPROCESS_EXECUTORS:
                    name = alias.asname or alias.name
                    self._subprocess_executors.add(name)
                    self._module_bindings[name] = ast.Attribute(
                        value=_subprocess_module_marker(),
                        attr=alias.name,
                    )
            return
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                self._bind_target(self._module_bindings, target, statement.value)
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            self._bind_target(self._module_bindings, statement.target, statement.value)

    def walk_function(self, function_name: str) -> None:
        function = self._functions.get(function_name)
        if function is None:
            raise ValueError(f"module function {function_name!r} is missing")
        self._walk_function(function, dict(self._module_bindings))

    def _walk_function(
        self,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        bindings: dict[str, ast.AST],
    ) -> None:
        function_identity = id(function)
        if function_identity in self._call_stack:
            self.commands.append(("<dynamic>",))
            return
        self._call_stack.append(function_identity)
        try:
            self.walk_block(function.body, (_FlowSnapshot(bindings),))
        finally:
            self._call_stack.pop()

    def walk_block(
        self,
        statements: list[ast.stmt],
        snapshots: tuple[_FlowSnapshot, ...],
    ) -> tuple[_FlowSnapshot, ...]:
        current = snapshots
        for statement in statements:
            projected: list[_FlowSnapshot] = []
            for snapshot in current:
                if snapshot.outcome != _CONTINUES:
                    projected.append(snapshot)
                else:
                    projected.extend(self._walk_statement(statement, snapshot.bindings))
            current = tuple(projected)
        return current

    def _walk_statement(
        self,
        statement: ast.stmt,
        bindings: dict[str, ast.AST],
    ) -> tuple[_FlowSnapshot, ...]:
        updated = dict(bindings)
        if isinstance(statement, ast.Assign):
            self._visit_expression(statement.value, updated)
            for target in statement.targets:
                self._bind_target(updated, target, statement.value)
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                name = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "subprocess":
                    updated[name] = _subprocess_module_marker()
                else:
                    updated.pop(name, None)
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                name = alias.asname or alias.name
                if (
                    statement.module == "subprocess"
                    and alias.name in _SUBPROCESS_EXECUTORS
                ):
                    updated[name] = ast.Attribute(
                        value=_subprocess_module_marker(),
                        attr=alias.name,
                    )
                else:
                    updated.pop(name, None)
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.AnnAssign):
            if statement.value is not None:
                self._visit_expression(statement.value, updated)
                self._bind_target(updated, statement.target, statement.value)
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.AugAssign):
            self._visit_expression(statement.value, updated)
            self._drop_target(updated, statement.target)
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.If):
            self._visit_expression(statement.test, updated)
            truth = _static_truth(statement.test)
            if truth is True:
                blocks = (statement.body,)
            elif truth is False:
                blocks = (statement.orelse,)
            else:
                blocks = (statement.body, statement.orelse)
            return tuple(
                snapshot
                for block in blocks
                for snapshot in self.walk_block(block, (_FlowSnapshot(dict(updated)),))
            )
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._visit_expression(statement.iter, updated)
            body_bindings = dict(updated)
            self._drop_target(body_bindings, statement.target)
            body = self.walk_block(statement.body, (_FlowSnapshot(body_bindings),))
            loop_results = [_FlowSnapshot(dict(updated))]
            for snapshot in body:
                if snapshot.outcome in {"break", "continue", _CONTINUES}:
                    loop_results.append(_FlowSnapshot(snapshot.bindings))
                else:
                    loop_results.append(snapshot)
            return self._apply_loop_else(statement.orelse, tuple(loop_results))
        if isinstance(statement, ast.While):
            self._visit_expression(statement.test, updated)
            truth = _static_truth(statement.test)
            if truth is False:
                return self.walk_block(statement.orelse, (_FlowSnapshot(updated),))
            body = self.walk_block(statement.body, (_FlowSnapshot(updated),))
            loop_results: list[_FlowSnapshot] = []
            if truth is not True:
                loop_results.append(_FlowSnapshot(dict(updated)))
            for snapshot in body:
                if snapshot.outcome in {"break", "continue", _CONTINUES}:
                    loop_results.append(_FlowSnapshot(snapshot.bindings))
                else:
                    loop_results.append(snapshot)
            return self._apply_loop_else(statement.orelse, tuple(loop_results))
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            for item in statement.items:
                self._visit_expression(item.context_expr, updated)
                if item.optional_vars is not None:
                    self._drop_target(updated, item.optional_vars)
            return self.walk_block(statement.body, (_FlowSnapshot(updated),))
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in statement.decorator_list:
                self._visit_expression(decorator, updated)
            for default in (*statement.args.defaults, *statement.args.kw_defaults):
                if default is not None:
                    self._visit_expression(default, updated)
            updated[statement.name] = statement
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.ClassDef):
            for expression in (*statement.decorator_list, *statement.bases):
                self._visit_expression(expression, updated)
            for keyword in statement.keywords:
                self._visit_expression(keyword.value, updated)
            updated.pop(statement.name, None)
            return (_FlowSnapshot(updated),)
        if isinstance(statement, ast.Return):
            if statement.value is not None:
                self._visit_expression(statement.value, updated)
            return (_FlowSnapshot(updated, "return"),)
        if isinstance(statement, ast.Raise):
            for expression in (statement.exc, statement.cause):
                if expression is not None:
                    self._visit_expression(expression, updated)
            return (_FlowSnapshot(updated, "raise"),)
        if isinstance(statement, ast.Break):
            return (_FlowSnapshot(updated, "break"),)
        if isinstance(statement, ast.Continue):
            return (_FlowSnapshot(updated, "continue"),)
        if isinstance(statement, (ast.Try, ast.TryStar)):
            return self._walk_try(statement, updated)
        self._visit_statement_expressions(statement, updated)
        return (_FlowSnapshot(updated),)

    def _apply_loop_else(
        self,
        orelse: list[ast.stmt],
        snapshots: tuple[_FlowSnapshot, ...],
    ) -> tuple[_FlowSnapshot, ...]:
        projected: list[_FlowSnapshot] = []
        for snapshot in snapshots:
            if snapshot.outcome == _CONTINUES:
                projected.extend(self.walk_block(orelse, (snapshot,)))
            else:
                projected.append(snapshot)
        return tuple(projected)

    def _walk_try(
        self,
        statement: ast.Try | ast.TryStar,
        bindings: dict[str, ast.AST],
    ) -> tuple[_FlowSnapshot, ...]:
        body = self.walk_block(statement.body, (_FlowSnapshot(dict(bindings)),))
        outcomes: list[_FlowSnapshot] = []
        for snapshot in body:
            if snapshot.outcome == _CONTINUES:
                outcomes.extend(self.walk_block(statement.orelse, (snapshot,)))
            else:
                outcomes.append(snapshot)
        for handler in statement.handlers:
            handler_bindings = dict(bindings)
            if handler.type is not None:
                self._visit_expression(handler.type, handler_bindings)
            if handler.name:
                handler_bindings.pop(handler.name, None)
            outcomes.extend(
                self.walk_block(handler.body, (_FlowSnapshot(handler_bindings),))
            )
        if not statement.finalbody:
            return tuple(outcomes)

        finalized: list[_FlowSnapshot] = []
        for outcome in outcomes:
            final_paths = self.walk_block(
                statement.finalbody, (_FlowSnapshot(dict(outcome.bindings)),)
            )
            for final_path in final_paths:
                final_outcome = (
                    outcome.outcome
                    if final_path.outcome == _CONTINUES
                    else final_path.outcome
                )
                finalized.append(_FlowSnapshot(final_path.bindings, final_outcome))
        return tuple(finalized)

    def _visit_statement_expressions(
        self,
        statement: ast.stmt,
        bindings: dict[str, ast.AST],
    ) -> None:
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.expr):
                self._visit_expression(child, bindings)

    def _visit_expression(
        self,
        expression: ast.expr,
        bindings: dict[str, ast.AST],
    ) -> None:
        if isinstance(expression, ast.Lambda):
            for default in (*expression.args.defaults, *expression.args.kw_defaults):
                if default is not None:
                    self._visit_expression(default, bindings)
            return
        if isinstance(expression, ast.IfExp):
            self._visit_expression(expression.test, bindings)
            truth = _static_truth(expression.test)
            if truth is True:
                branches = (expression.body,)
            elif truth is False:
                branches = (expression.orelse,)
            else:
                branches = (expression.body, expression.orelse)
            for branch in branches:
                self._visit_expression(branch, bindings)
            return
        if isinstance(expression, ast.Call):
            self._visit_call(expression, bindings)
            return
        for child in ast.iter_child_nodes(expression):
            if isinstance(child, ast.expr):
                self._visit_expression(child, bindings)

    def _visit_call(
        self,
        call: ast.Call,
        bindings: dict[str, ast.AST],
    ) -> None:
        for child in (*call.args, *(item.value for item in call.keywords)):
            self._visit_expression(child, bindings)
        callable_expression = _resolve_expression(call.func, bindings)
        if isinstance(callable_expression, ast.Lambda):
            lambda_bindings = _lambda_call_bindings(
                callable_expression,
                call,
                bindings,
            )
            if lambda_bindings is None:
                self.commands.append(("<dynamic>",))
            else:
                self._visit_expression(callable_expression.body, lambda_bindings)
            return
        executor_kind = self._subprocess_executor_kind(call.func, bindings)
        if executor_kind is not None:
            if executor_kind == "dynamic":
                self.commands.append(("<dynamic>",))
                return
            command: ast.expr | None = call.args[0] if call.args else None
            if command is None:
                command = next(
                    (
                        keyword.value
                        for keyword in call.keywords
                        if keyword.arg == "args"
                    ),
                    None,
                )
            self.commands.append(
                _command_tokens(
                    command,
                    bindings,
                    executable_parameter=self._executable_parameter,
                )
            )
            return
        helper = self._helper_function(call.func, bindings)
        if helper is not None:
            self._walk_function(helper, _call_bindings(helper, call, bindings))

    def _subprocess_executor_kind(
        self,
        expression: ast.expr,
        bindings: dict[str, ast.AST],
    ) -> str | None:
        resolved = _resolve_expression(expression, bindings)
        if isinstance(resolved, ast.Name):
            if resolved.id in self._subprocess_executors:
                return "known"
            return (
                "dynamic"
                if resolved.id in self._possible_subprocess_executors
                else None
            )
        if isinstance(resolved, ast.Attribute) and _is_subprocess_module(
            resolved.value, self._subprocess_modules, bindings
        ):
            return "known" if resolved.attr in _SUBPROCESS_EXECUTORS else None
        if isinstance(resolved, ast.Attribute) and _is_possible_subprocess_module(
            resolved.value,
            self._possible_subprocess_modules,
            bindings,
        ):
            return "dynamic"
        if _is_subprocess_getattr(resolved, self._subprocess_modules, bindings):
            attribute = resolved.args[1]
            if isinstance(attribute, ast.Constant) and isinstance(attribute.value, str):
                return "known" if attribute.value in _SUBPROCESS_EXECUTORS else None
            return "dynamic"
        if _is_possible_subprocess_getattr(
            resolved,
            self._possible_subprocess_modules,
            bindings,
        ):
            return "dynamic"
        if _is_subprocess_dict_lookup(resolved, self._subprocess_modules, bindings):
            key = resolved.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return "known" if key.value in _SUBPROCESS_EXECUTORS else None
            return "dynamic"
        return None

    def _helper_function(
        self,
        expression: ast.expr,
        bindings: dict[str, ast.AST],
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        resolved = _resolve_expression(expression, bindings)
        if isinstance(resolved, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return resolved
        if isinstance(resolved, ast.Name):
            return self._functions.get(resolved.id)
        return None

    @staticmethod
    def _bind_target(
        bindings: dict[str, ast.AST], target: ast.expr, value: ast.AST
    ) -> None:
        if isinstance(target, ast.Name):
            bindings[target.id] = _snapshot_expression(value, bindings)
        else:
            _ReachableSubprocessCollector._drop_target(bindings, target)

    @staticmethod
    def _drop_target(bindings: dict[str, ast.AST], target: ast.expr) -> None:
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                bindings.pop(node.id, None)


def _call_bindings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    call: ast.Call,
    caller_bindings: dict[str, ast.AST],
) -> dict[str, ast.AST]:
    parameters = [*function.args.posonlyargs, *function.args.args]
    # Module aliases and lexically enclosing local helpers remain visible inside
    # a reached helper. Explicit call arguments then shadow that inherited scope.
    bound: dict[str, ast.AST] = dict(caller_bindings)
    all_parameters = [*parameters, *function.args.kwonlyargs]
    for parameter in all_parameters:
        bound.pop(parameter.arg, None)
    for parameter, argument in zip(parameters, call.args):
        resolved = _resolve_expression(argument, caller_bindings)
        bound[parameter.arg] = resolved if resolved is not None else argument
    for keyword in call.keywords:
        if keyword.arg is not None:
            resolved = _resolve_expression(keyword.value, caller_bindings)
            bound[keyword.arg] = resolved if resolved is not None else keyword.value
    default_start = len(parameters) - len(function.args.defaults)
    for index, parameter in enumerate(parameters):
        if parameter.arg not in bound and index >= default_start:
            bound[parameter.arg] = function.args.defaults[index - default_start]
    for parameter, default in zip(function.args.kwonlyargs, function.args.kw_defaults):
        if parameter.arg not in bound and default is not None:
            bound[parameter.arg] = default
    return bound


def _lambda_call_bindings(
    function: ast.Lambda,
    call: ast.Call,
    caller_bindings: dict[str, ast.AST],
) -> dict[str, ast.AST] | None:
    if function.args.vararg is not None or function.args.kwarg is not None:
        return None
    if any(isinstance(argument, ast.Starred) for argument in call.args):
        return None
    if any(keyword.arg is None for keyword in call.keywords):
        return None
    parameters = [*function.args.posonlyargs, *function.args.args]
    if len(call.args) > len(parameters):
        return None
    bound = dict(caller_bindings)
    all_parameters = [*parameters, *function.args.kwonlyargs]
    for parameter in all_parameters:
        bound.pop(parameter.arg, None)
    for parameter, argument in zip(parameters, call.args):
        bound[parameter.arg] = _snapshot_expression(argument, caller_bindings)
    for keyword in call.keywords:
        matching = next(
            (parameter for parameter in all_parameters if parameter.arg == keyword.arg),
            None,
        )
        if matching is None or matching.arg in bound:
            return None
        bound[matching.arg] = _snapshot_expression(keyword.value, caller_bindings)
    default_start = len(parameters) - len(function.args.defaults)
    for index, parameter in enumerate(parameters):
        if parameter.arg not in bound and index >= default_start:
            bound[parameter.arg] = _snapshot_expression(
                function.args.defaults[index - default_start], caller_bindings
            )
    for parameter, default in zip(function.args.kwonlyargs, function.args.kw_defaults):
        if parameter.arg not in bound:
            if default is None:
                return None
            bound[parameter.arg] = _snapshot_expression(default, caller_bindings)
    if any(parameter.arg not in bound for parameter in all_parameters):
        return None
    return bound


def _command_tokens(
    command: ast.expr | None,
    bindings: dict[str, ast.AST],
    *,
    executable_parameter: str,
) -> tuple[str, ...]:
    command = _resolve_expression(command, bindings)
    if not isinstance(command, (ast.List, ast.Tuple)):
        return ("<dynamic>",)
    tokens: list[str] = []
    for item in command.elts:
        item = _resolve_expression(item, bindings)
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            tokens.append(item.value)
        elif isinstance(item, ast.Name) and item.id == executable_parameter:
            tokens.append(f"<{executable_parameter}>")
        else:
            tokens.append("<dynamic>")
    return tuple(tokens)


def _resolve_expression(
    expression: ast.AST | None,
    bindings: dict[str, ast.AST],
) -> ast.AST | None:
    seen: set[str] = set()
    while isinstance(expression, ast.Name) and expression.id in bindings:
        if expression.id in seen:
            return None
        seen.add(expression.id)
        expression = bindings[expression.id]
    return expression


def _snapshot_expression(
    expression: ast.AST,
    bindings: dict[str, ast.AST],
) -> ast.AST:
    """Capture assignment-time identities instead of retaining live name links."""

    class _SnapshotTransformer(ast.NodeTransformer):
        def __init__(self) -> None:
            self._resolving: set[str] = set()

        def visit_Name(self, node: ast.Name) -> ast.AST:
            if node.id not in bindings or node.id in self._resolving:
                return node
            resolved = bindings[node.id]
            self._resolving.add(node.id)
            try:
                return self.visit(copy.deepcopy(resolved))
            finally:
                self._resolving.remove(node.id)

    return _SnapshotTransformer().visit(copy.deepcopy(expression))


def _is_subprocess_module(
    expression: ast.AST,
    module_names: set[str],
    bindings: dict[str, ast.AST],
) -> bool:
    resolved = _resolve_expression(expression, bindings)
    return isinstance(resolved, ast.Name) and resolved.id in {
        *module_names,
        _SUBPROCESS_MODULE_MARKER,
    }


def _is_possible_subprocess_module(
    expression: ast.AST,
    possible_module_names: set[str],
    bindings: dict[str, ast.AST],
) -> bool:
    resolved = _resolve_expression(expression, bindings)
    return (
        isinstance(resolved, ast.Name)
        and resolved.id in possible_module_names
        and resolved.id != _SUBPROCESS_MODULE_MARKER
    )


def _is_subprocess_getattr(
    expression: ast.AST | None,
    module_names: set[str],
    bindings: dict[str, ast.AST],
) -> bool:
    return (
        isinstance(expression, ast.Call)
        and _is_builtin_getattr(expression.func, bindings)
        and len(expression.args) >= 2
        and _is_subprocess_module(expression.args[0], module_names, bindings)
    )


def _is_possible_subprocess_getattr(
    expression: ast.AST | None,
    possible_module_names: set[str],
    bindings: dict[str, ast.AST],
) -> bool:
    return (
        isinstance(expression, ast.Call)
        and _is_builtin_getattr(expression.func, bindings)
        and len(expression.args) >= 2
        and _is_possible_subprocess_module(
            expression.args[0], possible_module_names, bindings
        )
    )


def _is_builtin_getattr(
    expression: ast.AST,
    bindings: dict[str, ast.AST],
) -> bool:
    resolved = _resolve_expression(expression, bindings)
    return isinstance(resolved, ast.Name) and resolved.id == "getattr"


def _is_subprocess_dict_lookup(
    expression: ast.AST | None,
    module_names: set[str],
    bindings: dict[str, ast.AST],
) -> bool:
    return (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "__dict__"
        and _is_subprocess_module(expression.value.value, module_names, bindings)
    )


def _static_truth(expression: ast.expr) -> bool | None:
    if isinstance(expression, ast.Constant):
        return bool(expression.value)
    if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
        value = _static_truth(expression.operand)
        return None if value is None else not value
    return None


def _subprocess_module_marker() -> ast.Name:
    return ast.Name(id=_SUBPROCESS_MODULE_MARKER)
