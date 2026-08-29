"""Reachability-aware Python subprocess command projection."""

from __future__ import annotations

import ast


def reachable_subprocess_command_tokens(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    executable_parameter: str,
) -> tuple[tuple[str, ...], ...]:
    """Return commands consumed by reachable direct ``subprocess.run`` calls."""

    collector = _ReachableSubprocessCollector(executable_parameter)
    collector.walk_block(function.body, {})
    return tuple(collector.commands)


class _ReachableSubprocessCollector:
    def __init__(self, executable_parameter: str) -> None:
        self._executable_parameter = executable_parameter
        self.commands: list[tuple[str, ...]] = []

    def walk_block(
        self,
        statements: list[ast.stmt],
        bindings: dict[str, ast.expr],
    ) -> None:
        for statement in statements:
            self._walk_statement(statement, bindings)

    def _walk_statement(
        self,
        statement: ast.stmt,
        bindings: dict[str, ast.expr],
    ) -> None:
        if isinstance(statement, ast.Assign):
            self._visit_expression(statement.value, bindings)
            for target in statement.targets:
                self._bind_target(bindings, target, statement.value)
            return
        if isinstance(statement, ast.AnnAssign):
            if statement.value is not None:
                self._visit_expression(statement.value, bindings)
                self._bind_target(bindings, statement.target, statement.value)
            return
        if isinstance(statement, ast.AugAssign):
            self._visit_expression(statement.value, bindings)
            self._drop_target(bindings, statement.target)
            return
        if isinstance(statement, ast.If):
            self._visit_expression(statement.test, bindings)
            truth = _static_truth(statement.test)
            if truth is not None:
                self.walk_block(statement.body if truth else statement.orelse, bindings)
                return
            body_bindings = dict(bindings)
            else_bindings = dict(bindings)
            self.walk_block(statement.body, body_bindings)
            self.walk_block(statement.orelse, else_bindings)
            _merge_bindings(bindings, body_bindings, else_bindings)
            return
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._visit_expression(statement.iter, bindings)
            body_bindings = dict(bindings)
            self._drop_target(body_bindings, statement.target)
            self.walk_block(statement.body, body_bindings)
            else_bindings = dict(bindings)
            self.walk_block(statement.orelse, else_bindings)
            _merge_bindings(bindings, bindings, body_bindings, else_bindings)
            return
        if isinstance(statement, ast.While):
            self._visit_expression(statement.test, bindings)
            truth = _static_truth(statement.test)
            if truth is False:
                self.walk_block(statement.orelse, bindings)
                return
            body_bindings = dict(bindings)
            self.walk_block(statement.body, body_bindings)
            else_bindings = dict(bindings)
            self.walk_block(statement.orelse, else_bindings)
            _merge_bindings(bindings, bindings, body_bindings, else_bindings)
            return
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            for item in statement.items:
                self._visit_expression(item.context_expr, bindings)
                if item.optional_vars is not None:
                    self._drop_target(bindings, item.optional_vars)
            self.walk_block(statement.body, bindings)
            return
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in statement.decorator_list:
                self._visit_expression(decorator, bindings)
            for default in (*statement.args.defaults, *statement.args.kw_defaults):
                if default is not None:
                    self._visit_expression(default, bindings)
            bindings.pop(statement.name, None)
            return
        if isinstance(statement, ast.ClassDef):
            for expression in (*statement.decorator_list, *statement.bases):
                self._visit_expression(expression, bindings)
            for keyword in statement.keywords:
                self._visit_expression(keyword.value, bindings)
            class_bindings: dict[str, ast.expr] = {}
            self.walk_block(statement.body, class_bindings)
            bindings.pop(statement.name, None)
            return
        if isinstance(statement, ast.Try):
            alternatives: list[dict[str, ast.expr]] = []
            body_bindings = dict(bindings)
            self.walk_block(statement.body, body_bindings)
            self.walk_block(statement.orelse, body_bindings)
            alternatives.append(body_bindings)
            for handler in statement.handlers:
                handler_bindings = dict(bindings)
                if handler.type is not None:
                    self._visit_expression(handler.type, handler_bindings)
                if handler.name:
                    handler_bindings.pop(handler.name, None)
                self.walk_block(handler.body, handler_bindings)
                alternatives.append(handler_bindings)
            final_bindings = dict(bindings)
            self.walk_block(statement.finalbody, final_bindings)
            alternatives.append(final_bindings)
            _merge_bindings(bindings, *alternatives)
            return
        self._visit_statement_expressions(statement, bindings)

    def _visit_statement_expressions(
        self,
        statement: ast.stmt,
        bindings: dict[str, ast.expr],
    ) -> None:
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.expr):
                self._visit_expression(child, bindings)
            elif isinstance(child, ast.stmt):
                self._walk_statement(child, bindings)

    def _visit_expression(
        self,
        expression: ast.expr,
        bindings: dict[str, ast.expr],
    ) -> None:
        collector = _ExpressionCallCollector(bindings, self._executable_parameter)
        collector.visit(expression)
        self.commands.extend(collector.commands)

    @staticmethod
    def _bind_target(
        bindings: dict[str, ast.expr], target: ast.expr, value: ast.expr
    ) -> None:
        if isinstance(target, ast.Name):
            bindings[target.id] = value
        else:
            _ReachableSubprocessCollector._drop_target(bindings, target)

    @staticmethod
    def _drop_target(bindings: dict[str, ast.expr], target: ast.expr) -> None:
        for node in ast.walk(target):
            if isinstance(node, ast.Name):
                bindings.pop(node.id, None)


class _ExpressionCallCollector(ast.NodeVisitor):
    def __init__(
        self, bindings: dict[str, ast.expr], executable_parameter: str
    ) -> None:
        self._bindings = bindings
        self._executable_parameter = executable_parameter
        self.commands: list[tuple[str, ...]] = []

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_subprocess_run(node):
            command: ast.expr | None = node.args[0] if node.args else None
            if command is None:
                command = next(
                    (
                        keyword.value
                        for keyword in node.keywords
                        if keyword.arg == "args"
                    ),
                    None,
                )
            self.commands.append(
                _command_tokens(
                    command,
                    self._bindings,
                    executable_parameter=self._executable_parameter,
                )
            )
        self.generic_visit(node)


def _is_subprocess_run(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "run"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "subprocess"
    )


def _command_tokens(
    command: ast.expr | None,
    bindings: dict[str, ast.expr],
    *,
    executable_parameter: str,
) -> tuple[str, ...]:
    seen: set[str] = set()
    while isinstance(command, ast.Name) and command.id in bindings:
        if command.id in seen:
            return ()
        seen.add(command.id)
        command = bindings[command.id]
    if not isinstance(command, (ast.List, ast.Tuple)):
        return ()
    tokens: list[str] = []
    for item in command.elts:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            tokens.append(item.value)
        elif isinstance(item, ast.Name) and item.id == executable_parameter:
            tokens.append(f"<{executable_parameter}>")
        else:
            tokens.append("<dynamic>")
    return tuple(tokens)


def _static_truth(expression: ast.expr) -> bool | None:
    if isinstance(expression, ast.Constant):
        return bool(expression.value)
    if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
        value = _static_truth(expression.operand)
        return None if value is None else not value
    return None


def _merge_bindings(
    destination: dict[str, ast.expr],
    *alternatives: dict[str, ast.expr],
) -> None:
    if not alternatives:
        destination.clear()
        return
    shared: dict[str, ast.expr] = {}
    for name in set.intersection(*(set(alternative) for alternative in alternatives)):
        values = [alternative[name] for alternative in alternatives]
        if all(ast.dump(value) == ast.dump(values[0]) for value in values[1:]):
            shared[name] = values[0]
    destination.clear()
    destination.update(shared)
