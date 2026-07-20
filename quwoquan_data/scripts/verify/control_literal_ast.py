"""AST predicates shared by the control-literal verifier."""
from __future__ import annotations

import ast


def qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def uses_closed_type(node: ast.AST, type_name: str) -> bool:
    qualified = qualified_name(node)
    return qualified.startswith(f"{type_name}.") or (
        isinstance(node, ast.Call) and qualified_name(node.func) == type_name
    )


def uses_execution_state_status(node: ast.AST) -> bool:
    if isinstance(node, ast.IfExp):
        return uses_execution_state_status(node.body) and uses_execution_state_status(
            node.orelse
        )
    qualified = qualified_name(node)
    return qualified.startswith("ExecutionStateStatus.") and not qualified.endswith(
        ".value"
    )


def uses_queue_job_state(node: ast.AST) -> bool:
    qualified = qualified_name(node)
    return qualified.startswith("QueueJobState.") or qualified.startswith("STATE_")


def document_field(node: ast.AST, field: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == field
    ) or (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == field
    )


def contains_string_membership(node: ast.AST) -> bool:
    return any(
        isinstance(candidate, ast.Compare)
        and any(isinstance(operator, (ast.In, ast.NotIn)) for operator in candidate.ops)
        and any(
            isinstance(value, ast.Constant) and isinstance(value.value, str)
            for value in ast.walk(candidate)
        )
        for candidate in ast.walk(node)
    )


def looks_like_message_control(node: ast.AST) -> bool:
    names = {
        candidate.id.lower()
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Name)
    }
    attributes = {
        candidate.attr.lower()
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Attribute)
    }
    return bool(
        attributes & {"message", "issues"}
        or any(
            token in name
            for name in names
            for token in ("issue", "message", "reason", "combined")
        )
    )
