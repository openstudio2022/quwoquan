"""行级 / 上下文级判据：注释行、测试路径、拒绝语境与 sha256 负例识别。"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def python_digest_nonvalue_spans(text: str, *, test_path: bool) -> list[tuple[int, int]]:
    """只认可直接语法位置；不追踪未知别名、模型、参数化夹具或函数返回值。"""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    lines = text.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []

    def retain(node: ast.AST, *, diagnostic: bool = True) -> None:
        if not isinstance(node, (ast.Constant, ast.JoinedStr)):
            return
        start = sum(map(len, lines[:node.lineno - 1])) + len(lines[node.lineno - 1].encode()[:node.col_offset].decode())
        end = sum(map(len, lines[:node.end_lineno - 1])) + len(lines[node.end_lineno - 1].encode()[:node.end_col_offset].decode())
        # f-string 仅允许固定文字，插值表达式仍按实例值扫描。
        if isinstance(node, ast.JoinedStr):
            return
        if isinstance(node.value, str):
            literals = re.findall(r"sha256:[A-Za-z0-9._:-]+", node.value)
            if diagnostic and any(value not in {"sha256:digest", "sha256:DIGEST", "sha256:..."} for value in literals):
                return
            spans.append((start, end))

    stores: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            stores[node.id] = stores.get(node.id, 0) + 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stores[node.name] = stores.get(node.name, 0) + 1
        elif isinstance(node, ast.arg):
            stores[node.arg] = stores.get(node.arg, 0) + 1
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                stores[alias.asname or alias.name] = stores.get(alias.asname or alias.name, 0) + 1
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    stores[alias.asname] = stores.get(alias.asname, 0) + 1
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            receiver = node.value
            while isinstance(receiver, ast.Attribute):
                receiver = receiver.value
            if isinstance(receiver, ast.Name):
                stores[receiver.id] = stores.get(receiver.id, 0) + 1
    imports = {alias.name for node in tree.body if isinstance(node, ast.Import)
               for alias in node.names if alias.asname is None and stores.get(alias.name, 0) == 0}
    parsers: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        call = node.value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name) and call.func.value.id == "argparse"
                and call.func.attr == "ArgumentParser" and "argparse" in imports
                and stores.get(node.targets[0].id) == 1):
            parsers.add(node.targets[0].id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in parsers and node.func.attr == "add_argument":
                for keyword in node.keywords:
                    if keyword.arg == "help":
                        retain(keyword.value)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            call = node.exc
            if isinstance(call.func, ast.Name) and call.func.id in {"ValueError", "TypeError", "RuntimeError"} and stores.get(call.func.id, 0) == 0:
                for argument in call.args:
                    retain(argument)
        if not test_path or "pytest" not in imports or not isinstance(node, ast.With):
            continue
        if len(node.items) != 1 or len(node.body) != 1 or not isinstance(node.body[0], ast.Expr):
            continue
        assertion = node.items[0].context_expr
        if not (isinstance(assertion, ast.Call) and isinstance(assertion.func, ast.Attribute)
                and isinstance(assertion.func.value, ast.Name) and assertion.func.value.id == "pytest"
                and assertion.func.attr == "raises"):
            continue
        match = next((k.value for k in assertion.keywords if k.arg == "match"), None)
        if not isinstance(match, ast.Constant) or not isinstance(match.value, str):
            continue
        if not re.fullmatch(r"(?:not a canonical|invalid|malformed) (?:sha256 )?digest", match.value, re.I):
            continue
        call = node.body[0].value
        if not isinstance(call, ast.Call) or call.args or len(call.keywords) != 1:
            continue
        keyword = call.keywords[0]
        if keyword.arg and re.fullmatch(r"(?:[A-Za-z_]+_)?digest", keyword.arg, re.I):
            retain(keyword.value, diagnostic=False)
    return spans


def contract_negative_prose_lines(text: str) -> set[int]:
    """仅 YAML 描述标量中的明确否定句，不以旁边散文豁免声明或源码。"""
    import yaml

    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return set()
    result: set[int] = set()
    seen: set[int] = set()

    def visit(node: object) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if (isinstance(key, yaml.ScalarNode) and key.value == "description"
                        and isinstance(value, yaml.ScalarNode)
                        and not node.flow_style
                        and value.value.count("dual-read") == 1 and value.value.count("fallback") == 1
                        and re.search(r"不\s*dual-read[^。\n]*fallback", value.value)):
                    # 只覆盖实际包含该否定短句的物理行；不吞并整个文档。
                    for index in range(value.start_mark.line, value.end_mark.line + 1):
                        if index < len(text.splitlines()) and re.search(r"不\s*dual-read[^。\n]*fallback", text.splitlines()[index]):
                            result.add(index + 1)
                visit(value)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)
    visit(root)
    return result

from .constants import (
    CANONICAL_SHA256_DIGEST,
    CUSTOM_CONTROL_VERSION_FIELDS,
    EXPLICIT_INVALID_SHA256_FIXTURE,
    SHA256_ALGORITHM_IDENTITY_CONTEXT,
    SHA256_NEGATIVE_FIXTURE_CONTEXT,
    SHA256_REJECTION_ASSERTION,
)


def is_external_grafana_dashboard_schema(rel: str, field_name: str) -> bool:
    """Grafana dashboard schemaVersion belongs to the external JSON format."""
    return (
        field_name == "schemaVersion"
        and rel.startswith(
            "quwoquan_ops/observability/monitoring/dashboards/"
        )
    )


def _custom_control_version_fields(
    value: object,
    prefix: str = "",
) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            field_path = f"{prefix}.{key}" if prefix else key
            if key in CUSTOM_CONTROL_VERSION_FIELDS:
                findings.append((field_path, key))
            findings.extend(_custom_control_version_fields(child, field_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            field_path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            findings.extend(_custom_control_version_fields(child, field_path))
    return findings


def _is_comment_line(line: str, suffix: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if suffix in {".go", ".dart", ".js", ".ts"} and stripped.startswith("//"):
        return True
    if suffix == ".py" and stripped.startswith("#"):
        return True
    return False


def _is_persistence_go_path(rel: str) -> bool:
    return (
        "/infrastructure/" in rel
        or "/persistence/" in rel
        or "/runtime/search/es/" in rel
    )


def _is_mongo_seed_scenario(rel: str) -> bool:
    # 仅 _id 的 Mongo seed 可保留；双键由 T7 另拦
    return "/scenarios/" in rel and rel.endswith(".json")


def _is_test_path(rel: str) -> bool:
    return (
        "/test/" in rel
        or "/tests/" in rel
        or rel.endswith("_test.go")
        or rel.endswith("_test.dart")
        or rel.endswith("_test.py")
        or "__local_contract_test" in rel
        or "__api_integration_test" in rel
    )


def _is_elasticsearch_bulk_metadata_context(
    rel: str, lines: list[str], line_number: int
) -> bool:
    """Allow provider-owned Bulk API `_id`, never an App/HTTP DTO `_id`."""
    if not _is_test_path(rel) or "elasticsearch" not in Path(rel).name.lower():
        return False
    start = max(0, line_number - 8)
    end = min(len(lines), line_number + 8)
    context = "\n".join(lines[start:end])
    return 'json:"_index"' in context and 'json:"index"' in context


def _is_governance_scanner(rel: str) -> bool:
    """Separate policy implementation from runtime contract sources."""
    path = Path(rel)
    return (
        rel.startswith("quwoquan_ops/gate/")
        or "/scripts/verify/" in rel
        or ("/scripts/" in rel and path.name.startswith("verify_"))
    )


def _is_governance_test(rel: str) -> bool:
    return _is_test_path(rel) and "single_track_contracts" in Path(rel).name


def _is_rejection_context(lines: list[str], line_number: int) -> bool:
    start = max(0, line_number - 12)
    end = min(len(lines), line_number + 12)
    context = "\n".join(lines[start:end])
    return bool(
        re.search(
            r"reject|拒绝|forbidden|不得|禁止|旧|retired|退休|must not|must be rejected|"
            r"invalid|bad request|unknown field|fails closed|"
            r"not in |isdisjoint|does not contain|must not contain|never accepts",
            context,
            re.I,
        )
    )


def _is_sha256_algorithm_identity(lines: list[str], line_number: int) -> bool:
    """Allow named hash algorithms, never an ordinary digest-valued field."""
    start = max(0, line_number - 2)
    end = min(len(lines), line_number + 2)
    context = "\n".join(lines[start:end])
    return bool(SHA256_ALGORITHM_IDENTITY_CONTEXT.search(context))


def _is_sha256_documentation_placeholder(
    rel: str,
    lines: list[str],
    line_number: int,
    value: str,
) -> bool:
    """Allow the exact ellipsis syntax only when it documents a value shape."""
    if value != "sha256:...":
        return False
    line = lines[line_number - 1]
    suffix = Path(rel).suffix.lower()
    if suffix in {".md", ".mdx"}:
        return "`" in line or "@sha256:..." in line
    return bool(
        re.search(
            r"\b(?:help|usage|example|format)\b|\u9884\u671f|\u683c\u5f0f|\u4f8b\u5982|\u5f62\u5982|@sha256:\.\.\.",
            line,
            re.I,
        )
    )


def _is_explicit_sha256_negative_fixture(
    rel: str,
    lines: list[str],
    line_number: int,
) -> bool:
    if not _is_test_path(rel):
        return False
    line = lines[line_number - 1]
    if EXPLICIT_INVALID_SHA256_FIXTURE.search(line):
        return _is_rejection_context(lines, line_number)
    start = max(0, line_number - 10)
    end = min(len(lines), line_number + 20)
    context = "\n".join(lines[start:end])
    return bool(
        SHA256_NEGATIVE_FIXTURE_CONTEXT.search(context)
        and SHA256_REJECTION_ASSERTION.search(context)
    )


def _is_canonical_concatenated_sha256(
    lines: list[str],
    line_number: int,
) -> bool:
    """Recognize a canonical digest split across adjacent source literals."""
    context = "\n".join(lines[line_number - 1 : line_number + 4])
    string_parts = re.findall(r"[\"']([^\"']*)[\"']", context)
    for index, part in enumerate(string_parts):
        if "sha256:" not in part:
            continue
        candidate = part[part.index("sha256:") :]
        for continuation in string_parts[index + 1 :]:
            if not re.fullmatch(r"[0-9a-f]+", continuation):
                break
            candidate += continuation
            if CANONICAL_SHA256_DIGEST.fullmatch(candidate):
                return True
            if len(candidate) > len("sha256:") + 64:
                break
    return False


def _is_external_provider_path(rel: str) -> bool:
    """External wire revisions belong to the provider anticorruption boundary."""
    parts = set(Path(rel).parts)
    return bool(
        parts
        & {
            "external",
            "provider",
            "providers",
            "third_party",
            "third-party",
            "vendor",
        }
    )


def _json_object_has_dual_id(obj: object) -> bool:
    if isinstance(obj, dict):
        if "_id" in obj and "id" in obj:
            return True
        return any(_json_object_has_dual_id(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_json_object_has_dual_id(v) for v in obj)
    return False
