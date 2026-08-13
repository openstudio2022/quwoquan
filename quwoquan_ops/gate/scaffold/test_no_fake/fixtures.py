"""App 本地 fixture / typed double 的环境命名判定与字符串取值提取。"""

from __future__ import annotations

import ast
import io
import json
import tokenize
from pathlib import Path

import yaml

from .lexer import _c_style_tokens, _python_tree
from .patterns import (
    ENVIRONMENT_CLASS_NAME_RE,
    ENVIRONMENT_DATA_NAME_RE,
    ENVIRONMENT_PATH_SEGMENT_RE,
)


def is_app_user_acceptance_source(path: Path) -> bool:
    return (
        path.suffix == ".dart"
        and "quwoquan_app" in path.parts
        and "user_acceptance" in path.parts
    )


def is_app_local_fixture_source(path: Path) -> bool:
    parts = path.parts
    for index in range(len(parts) - 2):
        if parts[index : index + 3] == ("quwoquan_app", "test", "support"):
            return True
        if parts[index : index + 3] == (
            "quwoquan_app",
            "test",
            "local_contract",
        ):
            return True
    return False


def _source_string_literals(path: Path, text: str) -> list[str]:
    if path.suffix == ".py":
        values: list[str] = []
        try:
            stream = io.StringIO(text).readline
            for token in tokenize.generate_tokens(stream):
                if token.type != tokenize.STRING:
                    continue
                try:
                    value = ast.literal_eval(token.string)
                except (SyntaxError, ValueError):
                    continue
                if isinstance(value, str):
                    values.append(value)
        except (tokenize.TokenError, IndentationError):
            return values
        return values
    return [value for kind, value in _c_style_tokens(text) if kind == "string"]


def _structured_scalar_strings(path: Path, text: str) -> list[str]:
    try:
        if path.suffix == ".json":
            documents = [json.loads(text)]
        else:
            documents = list(yaml.safe_load_all(text))
    except (json.JSONDecodeError, yaml.YAMLError):
        return []
    values: list[str] = []
    pending = list(documents)
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set)):
            pending.extend(value)
        elif isinstance(value, str):
            values.append(value)
    return values


def _environment_class_names(path: Path, text: str) -> list[str]:
    names: set[str] = set()
    if path.suffix == ".py":
        tree = _python_tree(text)
        if tree is not None:
            names.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and ENVIRONMENT_CLASS_NAME_RE.fullmatch(node.name)
            )
        return sorted(names)
    tokens = _c_style_tokens(text)
    for index, token in enumerate(tokens[:-1]):
        if token == ("identifier", "class"):
            candidate = tokens[index + 1]
            if candidate[0] == "identifier" and ENVIRONMENT_CLASS_NAME_RE.fullmatch(candidate[1]):
                names.add(candidate[1])
    return sorted(names)


def app_local_fixture_environment_names(
    path: Path,
    text: str,
) -> tuple[list[str], list[str]]:
    """Return environment-shaped class/data names in ordinary local fixtures."""
    if not is_app_local_fixture_source(path):
        return [], []
    class_names = _environment_class_names(path, text)
    values = _source_string_literals(path, text)
    data_names = {
        match.group(0)
        for value in values
        for match in ENVIRONMENT_DATA_NAME_RE.finditer(value)
    }
    return class_names, sorted(data_names)


def app_local_fixture_environment_path_names(path: Path) -> list[str]:
    if not is_app_local_fixture_source(path):
        return []
    return sorted(
        segment
        for segment in path.parts
        if ENVIRONMENT_PATH_SEGMENT_RE.search(segment)
    )


def _environment_data_names_for_file(path: Path, text: str) -> list[str]:
    if path.suffix in {".json", ".yaml", ".yml"}:
        values = _structured_scalar_strings(path, text)
    elif path.suffix in {".dart", ".py", ".go", ".ts", ".txt"}:
        values = _source_string_literals(path, text)
    else:
        return []
    return sorted(
        {
            match.group(0)
            for value in values
            for match in ENVIRONMENT_DATA_NAME_RE.finditer(value)
        }
    )
