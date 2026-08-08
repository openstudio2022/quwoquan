#!/usr/bin/env python3
"""反向错误码治理门禁：实现发射了 stable code，但两个声明源都没有声明位。

现有契约校验（`quwoquan_service/internal/metadata/validate/governance_error.go`
的 `validateErrorGovernance`）两个循环都从声明出发：一个遍历 `Governance.Objects`
查 `emitted_by.operations`，一个遍历 `Operations` 把 `error_codes` 反查定义。
纯实现侧的事实既触不到 `CONTRACT.ERROR.UNKNOWN_OPERATION_CODE` 也触不到
`MISSING_OPERATION_EMISSION`，因此「实现了但契约没有声明位」这个方向没有任何
维度覆盖。本脚本补上这个方向。

判断放独立 verify 脚本而不是 validate 层：validate 的输入是 ContractGraph，
纯 metadata，没有源码树入口。把 Go 源码形态塞进去会让 `make verify-contract-graph`
的确定性依赖源码解析，不划算。

## 声明源（两个，都必须读）

1. 各对象 `quwoquan_service/**/contracts/**/errors.yaml`
2. `quwoquan_service/contracts/runtime_errors/errors/runtime_failure_codes.yaml`

## 声明形态（两种，都必须认）

块形态 `- code: X` 与 flow 形态 `- {code: X, kind: ...}`。仓内 668 个已声明码里
有 154 个只出现在 flow 形态；用 `^\\s*-?\\s*code:` 之类的行正则会把它们判成未声明，
这是本仓反复出现的假阳来源。所以声明侧一律用 YAML parser 解析，不用行正则。

## 发射形态

`EMISSION_FORMS` 同时覆盖 runtime `NewCode` 家族、生成的 `AppErrorFrom*`/`go_const`
调用、文件内局部构造器、跨包 config module 注入、领域 sentinel 到 handler factory
的映射，以及 App 生产 Dart 的 stable-code 发射。生成目录只用来确定 import target，
绝不把生成函数定义本身当成生产发射证据。

## 判据纪律

解析不出 module/kind 的发射位一律进 `unresolved_sites`，不做笛卡尔展开。
`writeRuntimeError` 那种 module/kind/reason 全是变量的站点，若按 file-wide 取值
集合做叉乘会从 6 个真实码变成 24 个组合码——那正是本仓要避免的弱判据。
未解析站点本身受基线管控：新增盲点同样 BLOCK，避免维度悄悄失去覆盖。

## 基线

历史只减不增基线已在 codes 与 unresolved_sites 同时清零后退休。默认文件缺席表示
严格零豁免：任何新未声明码或未解析站点都会直接 BLOCK，禁止重建空 policy 或把
declared-without-emission 债务吸收到反向基线。显式传入的迁移基线仍只接受精确
`MODULE.KIND.reason`，不接受通配符或 module 级批量豁免。

用法：
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py --report
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "quwoquan_ops"
    / "policies"
    / "gates"
    / "emitted_error_code_declaration_baseline.yaml"
)

SERVICE_DIR = "quwoquan_service"
RUNTIME_ERRORS_GO = "quwoquan_service/runtime/errors/errors.go"
RUNTIME_FAILURE_CODES_YAML = (
    "quwoquan_service/contracts/runtime_errors/errors/runtime_failure_codes.yaml"
)

# 当前覆盖的发射形态。扩形态时在这里登记，并同步 focused contract。
EMISSION_FORMS = (
    "runtime_new_code",  # rterr.NewCode(Module, Kind, reason)
    "runtime_helper_ctor",  # rterr.NewInvalidArgument / NewUnavailable(Module, ...)
    "local_error_ctor",  # releaseError("reason", ..., http.StatusConflict, err)
    "config_module_ctor",  # config.Module 从所有 typed config literal 装配点派生
    "generated_app_error_factory",  # owner generated AppErrorFrom* 的生产调用
    "go_const_identifier",  # owner generated Err* stable const 的生产调用
    "domain_sentinel_handler",  # errors.Is(domain.Err*) -> AppErrorFrom*
    "stable_code_literal",  # 生产 Go/Dart 中精确 MODULE.KIND.reason 字面量
    "app_stable_code_emission",  # App failureCode/code 字段发射
    "app_native_stable_code_emission",  # iOS Runner failureCode/code 发射
    "app_generated_error_symbol",  # App 生成 enum 成员流入 RuntimeFailure
    "python_stable_code_literal",  # production Python error-code 常量/response
)

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*$")
BASELINE_SCHEMA = "emitted-error-code-declaration-baseline"

_GO_SKIP_DIRS = {
    ".git",
    ".qwq_output",
    "node_modules",
    "vendor",
    "testdata",
    "generated",
}
_FUNC_SPLIT = re.compile(r"^func\s", re.M)
_NEW_CODE_CALL = re.compile(
    r"\bNewCode\(\s*(?P<module>[^,()]*?)\s*,\s*(?P<kind>[^,()]*?)\s*,\s*(?P<reason>[^()]*?)\s*\)",
    re.S,
)
_STRING_LITERAL = re.compile(r'^"([^"\\]*)"$')
_MODULE_CONVERSION = re.compile(r'^(?:\w+\.)?Module\(\s*"([A-Z][A-Z0-9_]*)"\s*\)$')
_KIND_CONVERSION = re.compile(r'^(?:\w+\.)?Kind\(\s*"([A-Z][A-Z0-9_]*)"\s*\)$')
_QUALIFIED_IDENT = re.compile(r"^(?:\w+\.)?(\w+)$")
_MAX_RESOLVE_DEPTH = 4


@dataclass(frozen=True)
class Emission:
    code: str
    form: str
    path: str
    function: str


@dataclass(frozen=True)
class ErrorDeclaration:
    code: str
    source_path: str
    go_const: str
    dart_const: str
    surfaces: tuple[str, ...]


@dataclass(frozen=True)
class UnresolvedSite:
    path: str
    function: str
    form: str
    expression: str


@dataclass
class ScanResult:
    emissions: list[Emission] = field(default_factory=list)
    unresolved: list[UnresolvedSite] = field(default_factory=list)
    scanned_files: int = 0


SOURCE_EVIDENCE_SURFACES = frozenset({"http", "gateway", "control_plane", "app"})


@dataclass
class RuntimeErrorVocabulary:
    """从 runtime/errors/errors.go 解析出的 module/kind/reason 常量与 helper 映射。

    不内置回退表：runtime errors 常量只有一个真相源，解析失败必须 fail-fast，
    否则门禁会在真相源改名后静默降级成一张过期的硬编码表。
    """

    modules: dict[str, str]
    kinds: dict[str, str]
    reasons: dict[str, str]
    helpers: dict[str, tuple[str, str]]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# 声明侧
# --------------------------------------------------------------------------


def _iter_declaration_entries(document: object) -> list[dict]:
    """吃下三种顶层形态：裸列表、`errors:` 键、`codes:` 键。

    条目内部的块形态与 flow 形态由 YAML parser 统一成 mapping，不需要区分。
    """
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict):
        items = document.get("errors")
        if items is None:
            items = document.get("codes")
        if items is None:
            items = []
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def declaration_sources(root: Path) -> list[Path]:
    sources: list[Path] = []
    service_root = root / SERVICE_DIR
    if service_root.is_dir():
        sources.extend(sorted(service_root.rglob("errors.yaml")))
    runtime_codes = root / RUNTIME_FAILURE_CODES_YAML
    if runtime_codes.is_file():
        sources.append(runtime_codes)
    return sources


def _entry_surfaces(entry: dict) -> tuple[str, ...]:
    surfaces: list[str] = []
    for emission in entry.get("emitted_by") or []:
        surface = emission if isinstance(emission, str) else emission.get("surface") if isinstance(emission, dict) else None
        if isinstance(surface, str) and surface.strip() and surface.strip() not in surfaces:
            surfaces.append(surface.strip())
    return tuple(surfaces)


def load_declarations(root: Path) -> tuple[dict[str, list[ErrorDeclaration]], list[Path]]:
    declarations: dict[str, list[ErrorDeclaration]] = {}
    sources = declaration_sources(root)
    for source in sources:
        try:
            document = yaml.safe_load(_read(source))
        except yaml.YAMLError as error:
            raise SystemExit(
                f"[emitted-error-code] FAIL: 无法解析声明源 {source}: {error}"
            )
        for entry in _iter_declaration_entries(document):
            code = entry.get("code")
            if isinstance(code, str) and code.strip():
                declaration = ErrorDeclaration(
                    code=code.strip(),
                    source_path=source.relative_to(root).as_posix(),
                    go_const=str(entry.get("go_const") or entry.get("goConst") or "").strip(),
                    dart_const=str(entry.get("dart_const") or entry.get("dartConst") or "").strip(),
                    surfaces=_entry_surfaces(entry),
                )
                declarations.setdefault(declaration.code, []).append(declaration)
    return declarations, sources


def load_declared_codes(root: Path) -> tuple[set[str], list[Path]]:
    declarations, sources = load_declarations(root)
    return set(declarations), sources


# --------------------------------------------------------------------------
# runtime errors 词表
# --------------------------------------------------------------------------


def load_runtime_vocabulary(root: Path) -> RuntimeErrorVocabulary:
    path = root / RUNTIME_ERRORS_GO
    if not path.is_file():
        raise SystemExit(
            f"[emitted-error-code] FAIL: 缺少 runtime errors 真相源 {path}"
        )
    text = _read(path)
    modules = dict(
        re.findall(r'\b(Module[A-Za-z0-9_]+)\s+Module\s*=\s*"([A-Z][A-Z0-9_]*)"', text)
    )
    kinds = dict(
        re.findall(r'\b(Kind[A-Za-z0-9_]+)\s+Kind\s*=\s*"([A-Z][A-Z0-9_]*)"', text)
    )
    reasons = dict(re.findall(r'\b(\w*Reason)\s*=\s*"([a-z][a-z0-9_]*)"', text))
    if not modules or not kinds:
        raise SystemExit(
            "[emitted-error-code] FAIL: 无法从 runtime errors 解析 Module/Kind 常量表"
        )
    helpers: dict[str, tuple[str, str]] = {}
    for match in re.finditer(
        r"func\s+(New[A-Za-z0-9_]+)\(\s*module\s+Module\b(?P<body>.*?)\n}", text, re.S
    ):
        name = match.group(1)
        inner = _NEW_CODE_CALL.search(match.group("body"))
        if inner is None:
            continue
        if inner.group("module").strip() != "module":
            continue
        kind_key = inner.group("kind").strip()
        reason_key = inner.group("reason").strip()
        kind_value = kinds.get(kind_key)
        reason_value = reasons.get(reason_key)
        if kind_value and reason_value:
            helpers[name] = (kind_value, reason_value)
    if not helpers:
        raise SystemExit(
            "[emitted-error-code] FAIL: 无法从 runtime errors 解析 helper 构造器映射"
        )
    return RuntimeErrorVocabulary(
        modules=modules, kinds=kinds, reasons=reasons, helpers=helpers
    )


# --------------------------------------------------------------------------
# 发射侧：作用域内标识符解析
# --------------------------------------------------------------------------


def _assignment_values(scope_text: str, ident: str) -> list[str]:
    """收集作用域内对 ident 的全部赋值右值（`=` / `:=`，排除 `==` 等比较）。"""
    pattern = re.compile(
        r"(?:^|[^\w.])" + re.escape(ident) + r"\s*(?<![=!<>])(?::=|=)(?!=)\s*(?P<rhs>[^\n]+)"
    )
    values: list[str] = []
    for match in pattern.finditer(scope_text):
        rhs = match.group("rhs").strip().rstrip(",").strip()
        if rhs and rhs not in values:
            values.append(rhs)
    return values


def _resolve_symbol(
    expression: str,
    scopes: tuple[str, ...],
    table: dict[str, str],
    converter: re.Pattern[str],
    depth: int = 0,
) -> set[str]:
    """把 module/kind 表达式解析成取值集合。空集合代表解析失败。"""
    expression = expression.strip()
    if not expression or depth > _MAX_RESOLVE_DEPTH:
        return set()
    conversion = converter.match(expression)
    if conversion:
        return {conversion.group(1)}
    literal = _STRING_LITERAL.match(expression)
    if literal:
        return {literal.group(1)}
    ident_match = _QUALIFIED_IDENT.match(expression)
    if ident_match is None:
        return set()
    ident = ident_match.group(1)
    if ident in table:
        return {table[ident]}
    resolved: set[str] = set()
    for scope_text in scopes:
        for value in _assignment_values(scope_text, ident):
            resolved |= _resolve_symbol(value, scopes, table, converter, depth + 1)
        if resolved:
            break
    return resolved


def _resolve_reason(
    expression: str,
    scopes: tuple[str, ...],
    reasons: dict[str, str],
    depth: int = 0,
) -> set[str]:
    expression = expression.strip().rstrip(",").strip()
    if not expression or depth > _MAX_RESOLVE_DEPTH:
        return set()
    literal = _STRING_LITERAL.match(expression)
    if literal:
        value = literal.group(1)
        return {value} if re.fullmatch(r"[a-z][a-z0-9_]*", value) else set()
    ident_match = _QUALIFIED_IDENT.match(expression)
    if ident_match is None:
        return set()
    ident = ident_match.group(1)
    if ident in reasons:
        return {reasons[ident]}
    resolved: set[str] = set()
    for scope_text in scopes:
        for value in _assignment_values(scope_text, ident):
            resolved |= _resolve_reason(value, scopes, reasons, depth + 1)
        if resolved:
            break
    return resolved


def _function_name(function_text: str) -> str:
    match = re.match(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z0-9_]+)", "func " + function_text)
    return match.group(1) if match else "<file-scope>"


def _split_functions(text: str) -> list[str]:
    parts = _FUNC_SPLIT.split(text)
    return parts[1:] if len(parts) > 1 else []


def _package_scope(text: str) -> str:
    """函数体之外的文本，用于解析包级 const/var 别名（moduleTag / moduleSearch）。"""
    parts = _FUNC_SPLIT.split(text)
    return parts[0] if parts else text


def _go_files(root: Path) -> list[Path]:
    service_root = root / SERVICE_DIR
    if not service_root.is_dir():
        return []
    files: list[Path] = []
    for path in service_root.rglob("*.go"):
        if path.name.endswith("_test.go"):
            continue
        if any(part in _GO_SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _dart_files(root: Path) -> list[Path]:
    app_root = root / "quwoquan_app" / "lib"
    if not app_root.is_dir():
        return []
    return sorted(
        path
        for path in app_root.rglob("*.dart")
        if "generated" not in path.parts
        and not any(part in _GO_SKIP_DIRS for part in path.parts)
    )


def _swift_files(root: Path) -> list[Path]:
    """Return first-party iOS production sources, excluding Pods/generated/tests."""
    runner_root = root / "quwoquan_app" / "ios" / "Runner"
    if not runner_root.is_dir():
        return []
    return sorted(
        path
        for path in runner_root.rglob("*.swift")
        if "generated" not in path.parts
        and "Tests" not in path.parts
        and not any(part in _GO_SKIP_DIRS for part in path.parts)
    )


def _python_files(root: Path) -> list[Path]:
    services_root = root / "quwoquan_service" / "services"
    if not services_root.is_dir():
        return []
    return sorted(
        path
        for path in services_root.rglob("*.py")
        if "internal" in path.parts
        and "generated" not in path.parts
        and "tests" not in path.parts
        and "test" not in path.parts
        and not path.name.startswith("test_")
        and not any(part in _GO_SKIP_DIRS for part in path.parts)
    )


def _generated_import_path(declaration: ErrorDeclaration) -> str:
    parts = declaration.source_path.split("/")
    try:
        contracts_index = parts.index("contracts")
    except ValueError:
        return ""
    if not parts or parts[-1] != "errors.yaml" or contracts_index + 2 >= len(parts):
        return ""
    return "/".join(
        [*parts[:contracts_index], "generated", *parts[contracts_index + 1 : -1]]
    )


def _generated_symbols(
    declarations: dict[str, list[ErrorDeclaration]],
) -> dict[tuple[str, str], tuple[str, str]]:
    """Return (import path, symbol) -> (stable code, form).

    A duplicate code owner is already rejected by metadata governance. A symbol
    collision inside one generated package is unsafe here as well, so ambiguous
    mappings are removed instead of guessed.
    """
    candidates: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for code, owned in declarations.items():
        for declaration in owned:
            import_path = _generated_import_path(declaration)
            if not import_path or not declaration.go_const:
                continue
            candidates.setdefault(
                (import_path, declaration.go_const), []
            ).append((code, "go_const_identifier"))
            if declaration.go_const.startswith("Err"):
                candidates.setdefault(
                    (import_path, "AppErrorFrom" + declaration.go_const[3:]), []
                ).append((code, "generated_app_error_factory"))
    return {
        key: values[0]
        for key, values in candidates.items()
        if len({value[0] for value in values}) == 1
    }


_GO_GENERATED_IMPORT = re.compile(
    r'^\s*(?:import\s+)?(?:(?P<alias>[A-Za-z_]\w*)\s+)?'
    r'"(?P<path>quwoquan_service/[^"\n]+/generated/[^"\n]+)"',
    re.M,
)


def _scan_generated_symbol_emissions(
    root: Path,
    declarations: dict[str, list[ErrorDeclaration]],
    result: ScanResult,
) -> None:
    symbols = _generated_symbols(declarations)
    for path in _go_files(root):
        text = _read(path)
        relative = path.relative_to(root).as_posix()
        imports: dict[str, str] = {}
        for match in _GO_GENERATED_IMPORT.finditer(text):
            import_path = match.group("path")
            alias = match.group("alias")
            if not alias:
                generated_dir = root / import_path
                for generated_source in sorted(generated_dir.glob("*.go")):
                    package_match = re.search(
                        r"^package\s+([A-Za-z_]\w*)", _read(generated_source), re.M
                    )
                    if package_match:
                        alias = package_match.group(1)
                        break
            alias = alias or import_path.rsplit("/", 1)[-1]
            imports[alias] = import_path
        if not imports:
            continue
        functions = _split_functions(text)
        for alias, import_path in imports.items():
            for match in re.finditer(
                rf"\b{re.escape(alias)}\.(?P<symbol>(?:AppErrorFrom|Err)[A-Za-z0-9_]+)\b",
                text,
            ):
                mapped = symbols.get((import_path, match.group("symbol")))
                if mapped is None:
                    continue
                code, form = mapped
                function = "<file-scope>"
                function_text = ""
                for candidate in functions:
                    start = text.find("func " + candidate)
                    end = start + len("func " + candidate)
                    if start <= match.start() <= end:
                        function = _function_name(candidate)
                        function_text = candidate
                        break
                if form == "generated_app_error_factory" and "errors.Is(" in function_text:
                    form = "domain_sentinel_handler"
                result.emissions.append(
                    Emission(code=code, form=form, path=relative, function=function)
                )


def _strip_comments(text: str) -> str:
    """Strip // and /* */ comments while preserving quoted literals."""
    output: list[str] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if quote:
            output.append(char)
            if quote != "`" and escaped:
                escaped = False
            elif quote != "`" and char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char in {'"', "'", "`"}:
            quote = char
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            end = text.find("\n", index + 2)
            if end < 0:
                break
            output.append("\n")
            index = end + 1
            continue
        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            if end < 0:
                break
            output.append("\n" * text[index : end + 2].count("\n"))
            index = end + 2
            continue
        output.append(char)
        index += 1
    return "".join(output)


_STABLE_CODE_LITERAL = re.compile(
    r"(?P<quote>['\"`])(?P<code>[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*)"
    r"(?P=quote)"
)


def _scan_stable_code_literals(root: Path, result: ScanResult) -> None:
    paths = [*_go_files(root), *_dart_files(root)]
    for path in paths:
        text = _strip_comments(_read(path))
        relative = path.relative_to(root).as_posix()
        is_app = relative.startswith("quwoquan_app/lib/")
        for match in _STABLE_CODE_LITERAL.finditer(text):
            prefix = text[max(0, match.start() - 100) : match.start()]
            line_prefix = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
            if is_app:
                if not re.search(
                    r"(?:failureCode|errorCode|code)\s*(?::|=)\s*$", prefix
                ):
                    continue
                form = "app_stable_code_emission"
            else:
                is_error_constructor = bool(
                    re.search(r"(?:errors\.New|NewCode|ParseCode)\(\s*$", prefix)
                )
                is_code_field = bool(
                    re.search(
                        r"(?:Code|ErrorCode|FailureCode)\s*:\s*(?:[^,]*,\s*)?$",
                        line_prefix,
                    )
                )
                is_code_map_value = bool(
                    re.search(r"['\"](?:code|errorCode|failureCode)['\"]\s*:\s*$", prefix)
                )
                is_returned_code = bool(re.search(r"\breturn\s*$", prefix))
                if not (
                    is_error_constructor
                    or is_code_field
                    or is_code_map_value
                    or is_returned_code
                ):
                    continue
                form = "stable_code_literal"
            result.emissions.append(
                Emission(
                    code=match.group("code"),
                    form=form,
                    path=relative,
                    function="<dart>" if is_app else "<literal>",
                )
            )


def _scan_swift_stable_code_emissions(root: Path, result: ScanResult) -> None:
    """Scan only production values assigned/passed as a native error code.

    A stable-code literal in a comment, allowlist, log string, or arbitrary
    constant is not emission evidence. Multiline ternaries are supported
    because the startup watchdog selects one of two canonical failure codes
    before passing the selected value to the telemetry journal.
    """
    assignment_prefix = re.compile(
        r"(?:let|var)\s+(?:failureCode|errorCode|code)\s*=\s*"
        r"(?:(?:[^\n;{}]*)\n\s*){0,4}[^;{}]*$"
    )
    argument_prefix = re.compile(r"(?:failureCode|errorCode|code)\s*:\s*$")
    for path in _swift_files(root):
        text = _strip_comments(_read(path))
        relative = path.relative_to(root).as_posix()
        for match in _STABLE_CODE_LITERAL.finditer(text):
            prefix = text[max(0, match.start() - 500) : match.start()]
            if assignment_prefix.search(prefix) is None and argument_prefix.search(prefix) is None:
                continue
            result.emissions.append(
                Emission(
                    code=match.group("code"),
                    form="app_native_stable_code_emission",
                    path=relative,
                    function="<swift>",
                )
            )


def _app_generated_error_symbols(root: Path) -> dict[str, dict[str, str]]:
    """Build generated-file -> (`ErrorEnum.member` -> stable code).

    App error generators currently emit either a const-enum constructor or a
    switch-backed `code` getter. Both are source-derived generated catalogs;
    only an import-bound use from non-generated production Dart can be emission
    evidence. Keeping the source file in the key prevents a same-named local
    object from borrowing a canonical enum's stable-code mapping.
    """
    generated_root = root / "quwoquan_app" / "lib" / "runtime" / "errors" / "generated"
    if not generated_root.is_dir():
        return {}
    symbols_by_file: dict[str, dict[str, str]] = {}
    for path in sorted(generated_root.rglob("*_errors.g.dart")):
        text = _read(path)
        enum_match = re.search(r"\benum\s+(?P<name>[A-Za-z_]\w*ErrorCode)\s*{", text)
        if enum_match is None:
            continue
        enum_name = enum_match.group("name")
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        symbols: dict[str, str] = {}
        ambiguous: set[str] = set()
        candidates: list[tuple[str, str]] = []
        candidates.extend(
            (match.group("member"), match.group("code"))
            for match in re.finditer(
                r"^\s*(?P<member>[a-zA-Z_]\w*)\(\s*'(?P<code>"
                r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*)'",
                text,
                re.M,
            )
        )
        candidates.extend(
            (match.group("member"), match.group("code"))
            for match in re.finditer(
                rf"\bcase\s+{re.escape(enum_name)}\.(?P<member>[a-zA-Z_]\w*)\s*:"
                r"\s*return\s+'(?P<code>"
                r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*)'",
                text,
            )
        )
        for member, code in candidates:
            symbol = f"{enum_name}.{member}"
            existing = symbols.get(symbol)
            if existing is not None and existing != code:
                ambiguous.add(symbol)
                continue
            symbols[symbol] = code
        for symbol in ambiguous:
            symbols.pop(symbol, None)
        if symbols:
            symbols_by_file[relative] = symbols
    return symbols_by_file


_DART_IMPORT_DIRECTIVE = re.compile(
    r"^import\s+['\"](?P<uri>[^'\"]+)['\"]"
    r"(?:\s+deferred)?(?:\s+as\s+(?P<alias>[A-Za-z_]\w*))?"
    r"(?:\s+(?:show|hide)\s+[^;]+)?\s*;$"
)


def _dart_import_directives(text: str) -> list[tuple[str, str]]:
    """Parse only the leading Dart directive section.

    Imports embedded in comments or later string literals cannot enter this
    section. Multiline/show directives are deliberately skipped rather than
    guessed; canonical generated error imports are single-line directives.
    """
    directives: list[tuple[str, str]] = []
    for raw_line in _strip_comments(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _DART_IMPORT_DIRECTIVE.fullmatch(line)
        if match is not None:
            directives.append((match.group("uri"), match.group("alias") or ""))
            continue
        if line.startswith(("library ", "export ", "part ")):
            continue
        break
    return directives


def _dart_library_source(app_lib: Path, path: Path, text: str) -> Path | None:
    """Resolve a part file to the library that owns its imports."""
    part_of = re.search(
        r"^\s*part\s+of\s+['\"](?P<uri>[^'\"]+)['\"]\s*;",
        _strip_comments(text),
        re.M,
    )
    if part_of is None:
        return path
    uri = part_of.group("uri")
    if uri.startswith("package:quwoquan_app/"):
        candidate = app_lib / uri.removeprefix("package:quwoquan_app/")
    elif ":" not in uri:
        candidate = path.parent / uri
    else:
        return None
    candidate = candidate.resolve()
    try:
        candidate.relative_to(app_lib.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _resolve_dart_import(app_lib: Path, library: Path, uri: str) -> Path | None:
    if uri.startswith("package:quwoquan_app/"):
        candidate = app_lib / uri.removeprefix("package:quwoquan_app/")
    elif ":" not in uri:
        candidate = library.parent / uri
    else:
        return None
    candidate = candidate.resolve()
    try:
        candidate.relative_to(app_lib.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _mask_dart_string_literals(text: str) -> str:
    """Mask Dart string contents while preserving offsets and newlines."""
    output = list(text)
    index = 0
    while index < len(text):
        raw_prefix = text[index] in {"r", "R"} and index + 1 < len(text)
        quote_index = index + 1 if raw_prefix else index
        if text[quote_index] not in {"'", '"'}:
            index += 1
            continue
        quote = text[quote_index]
        triple = text.startswith(quote * 3, quote_index)
        delimiter = quote * (3 if triple else 1)
        start = index
        cursor = quote_index + len(delimiter)
        while cursor < len(text):
            if not raw_prefix and text[cursor] == "\\":
                cursor += 2
                continue
            if text.startswith(delimiter, cursor):
                cursor += len(delimiter)
                break
            cursor += 1
        for position in range(start, min(cursor, len(output))):
            if output[position] != "\n":
                output[position] = " "
        index = max(cursor, index + 1)
    return "".join(output)


def _dart_generated_code_flows_to_error_field(
    code_text: str,
    expression: str,
) -> bool:
    """Prove a generated `.code` value flows through a local typed variable."""
    value_pattern = re.compile(rf"\b{re.escape(expression)}\.code\b")
    assignment_pattern = re.compile(
        r"\b(?:final|var|const)\s+"
        r"(?:[A-Za-z_]\w*(?:<[^;=]+>)?\??\s+)?"
        r"(?P<name>[A-Za-z_]\w*)\s*=\s*[^;]*$",
        re.S,
    )
    for value in value_pattern.finditer(code_text):
        prefix = code_text[max(0, value.start() - 4000) : value.start()]
        assignment = assignment_pattern.search(prefix)
        if assignment is None:
            continue
        variable = assignment.group("name")
        if re.search(
            rf"\b(?:failureCode|errorCode|code)\s*:\s*{re.escape(variable)}\b",
            code_text[value.end() :],
        ):
            return True
    return False


def _scan_app_generated_error_emissions(root: Path, result: ScanResult) -> None:
    symbols_by_file = _app_generated_error_symbols(root)
    if not symbols_by_file:
        return
    app_lib = root / "quwoquan_app" / "lib"
    for path in _dart_files(root):
        raw_text = _read(path)
        text = _strip_comments(raw_text)
        library = _dart_library_source(app_lib, path, raw_text)
        if library is None:
            continue
        imported_symbols: list[tuple[str, dict[str, str]]] = []
        for uri, alias in _dart_import_directives(_read(library)):
            imported = _resolve_dart_import(app_lib, library, uri)
            if imported is None:
                continue
            relative_import = imported.relative_to(root.resolve()).as_posix()
            symbols = symbols_by_file.get(relative_import)
            if symbols:
                imported_symbols.append(((alias + ".") if alias else "", symbols))
        if not imported_symbols:
            continue
        code_text = _mask_dart_string_literals(text)
        has_structured_failure = bool(
            re.search(r"\b(?:RuntimeFailure(?:Base)?|CloudException)\s*\(", code_text)
        )
        relative = path.relative_to(root).as_posix()
        for qualifier, symbols in imported_symbols:
            for symbol, code in sorted(symbols.items()):
                expression = re.escape(qualifier + symbol)
                is_typed_failure_field = bool(
                    re.search(
                        rf"\b(?:failureCode|errorCode|code)\s*:\s*{expression}\.code\b",
                        code_text,
                    )
                )
                is_typed_failure_flow = _dart_generated_code_flows_to_error_field(
                    code_text,
                    qualifier + symbol,
                )
                is_structured_failure_use = has_structured_failure and bool(
                    re.search(rf"\b{expression}\b", code_text)
                )
                if (
                    is_typed_failure_field
                    or is_typed_failure_flow
                    or is_structured_failure_use
                ):
                    result.emissions.append(
                        Emission(
                            code=code,
                            form="app_generated_error_symbol",
                            path=relative,
                            function="<dart-generated-symbol>",
                        )
                    )


def _scan_python_stable_code_literals(root: Path, result: ScanResult) -> None:
    """Scan only AST-backed production error-code assignments/response maps."""
    code_name = re.compile(r"(?:^|_)(?:ERROR_)?CODE$", re.I)
    response_keys = {"code", "errorCode", "failureCode"}
    for path in _python_files(root):
        try:
            tree = ast.parse(_read(path), filename=path.as_posix())
        except SyntaxError:
            continue
        relative = path.relative_to(root).as_posix()
        codes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                if not CODE_PATTERN.fullmatch(value.value):
                    continue
                if any(
                    isinstance(target, ast.Name) and code_name.search(target.id)
                    for target in targets
                ):
                    codes.add(value.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in response_keys
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and CODE_PATTERN.fullmatch(value.value)
                    ):
                        codes.add(value.value)
        for code in sorted(codes):
            result.emissions.append(
                Emission(
                    code=code,
                    form="python_stable_code_literal",
                    path=relative,
                    function="<python-ast>",
                )
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


def scan_emissions(
    root: Path,
    vocabulary: RuntimeErrorVocabulary,
    declarations: dict[str, list[ErrorDeclaration]],
) -> ScanResult:
    result = ScanResult()
    helper_pattern = re.compile(
        r"\b(?P<helper>" + "|".join(sorted(vocabulary.helpers)) + r")\(\s*(?P<module>[^,()]*?)\s*,"
    )
    for path in _go_files(root):
        text = _read(path)
        result.scanned_files += 1
        relative = path.relative_to(root).as_posix()
        local_constructors = _scan_local_error_constructors(
            root, path, text, vocabulary, result
        )
        if "NewCode(" not in text and not any(
            helper + "(" in text for helper in vocabulary.helpers
        ):
            continue
        # runtime errors 里 NewCode 与 helper 构造器的函数体是词表定义本身，
        # 不是发射位；把它们当未解析盲点登记会造成永久噪声。
        vocabulary_definitions = (
            {"NewCode", *vocabulary.helpers} if relative == RUNTIME_ERRORS_GO else set()
        )
        package_scope = _package_scope(text)
        # 包级别名可能声明在同包其他文件（moduleSearch / moduleTag 均是此形态）。
        sibling_scope = "".join(
            _package_scope(_read(sibling))
            for sibling in sorted(path.parent.glob("*.go"))
            if sibling != path and not sibling.name.endswith("_test.go")
        )
        for function_text in _split_functions(text):
            function = _function_name(function_text)
            if function in vocabulary_definitions or function in local_constructors:
                continue
            scopes = (function_text, package_scope, sibling_scope)
            calls = list(_NEW_CODE_CALL.finditer(function_text))
            for call in calls:
                _classify_new_code(
                    root,
                    call,
                    scopes,
                    vocabulary,
                    relative,
                    function,
                    len(calls),
                    result,
                )
            for call in helper_pattern.finditer(function_text):
                helper = call.group("helper")
                kind_value, reason_value = vocabulary.helpers[helper]
                modules = _resolve_symbol(
                    call.group("module"),
                    scopes,
                    vocabulary.modules,
                    _MODULE_CONVERSION,
                )
                form = "runtime_helper_ctor"
                if not modules:
                    modules = _config_selector_values(
                        root, call.group("module").strip(), vocabulary
                    )
                    if modules:
                        form = "config_module_ctor"
                if not modules:
                    result.unresolved.append(
                        UnresolvedSite(
                            path=relative,
                            function=function,
                            form="runtime_helper_ctor",
                            expression=f"{helper}({call.group('module').strip()}, ...)",
                        )
                    )
                    continue
                for module in sorted(modules):
                    result.emissions.append(
                        Emission(
                            code=f"{module}.{kind_value}.{reason_value}",
                            form=form,
                            path=relative,
                            function=function,
                        )
                    )
    _scan_generated_symbol_emissions(root, declarations, result)
    _scan_stable_code_literals(root, result)
    _scan_swift_stable_code_emissions(root, result)
    _scan_app_generated_error_emissions(root, result)
    _scan_python_stable_code_literals(root, result)
    # 多形态可能指向同一发射位（sentinel branch + generated factory）；报告与
    # declared-without-emission 只需要确定性集合，不把同一证据重复计数。
    result.emissions = sorted(
        set(result.emissions),
        key=lambda item: (item.code, item.path, item.function, item.form),
    )
    result.unresolved = sorted(
        set(result.unresolved),
        key=lambda item: (item.path, item.function, item.form, item.expression),
    )
    return result


def _classify_new_code(
    root: Path,
    call: re.Match[str],
    scopes: tuple[str, ...],
    vocabulary: RuntimeErrorVocabulary,
    relative: str,
    function: str,
    call_count: int,
    result: ScanResult,
) -> None:
    module_expression = call.group("module").strip()
    kind_expression = call.group("kind").strip()
    reason_expression = call.group("reason").strip()
    expression = f"NewCode({module_expression}, {kind_expression}, {reason_expression})"
    modules = _resolve_symbol(
        module_expression, scopes, vocabulary.modules, _MODULE_CONVERSION
    )
    form = "runtime_new_code"
    if not modules:
        modules = _config_selector_values(root, module_expression, vocabulary)
        if modules:
            form = "config_module_ctor"
    kinds = _resolve_symbol(kind_expression, scopes, vocabulary.kinds, _KIND_CONVERSION)
    reasons = _resolve_reason(reason_expression, scopes, vocabulary.reasons)
    # module 与 kind 必须唯一：多值时做叉乘会凭空造出从未发射过的组合码。
    if not modules or len(kinds) != 1 or not reasons:
        result.unresolved.append(
            UnresolvedSite(
                path=relative,
                function=function,
                form="runtime_new_code",
                expression=expression,
            )
        )
        return
    # reason 多值只在函数体内只有一个 NewCode 调用时可信；否则不同分支的 reason
    # 可能流向不同调用点，展开会产生假阳。
    if len(reasons) > 1 and call_count != 1:
        result.unresolved.append(
            UnresolvedSite(
                path=relative,
                function=function,
                form="runtime_new_code",
                expression=expression,
            )
        )
        return
    kind = next(iter(kinds))
    for module in sorted(modules):
        for reason in sorted(reasons):
            result.emissions.append(
                Emission(
                    code=f"{module}.{kind}.{reason}",
                    form=form,
                    path=relative,
                    function=function,
                )
            )


# --------------------------------------------------------------------------
# 基线
# --------------------------------------------------------------------------


@dataclass
class Baseline:
    codes: dict[str, dict]
    unresolved: dict[tuple[str, str], dict]


def _unresolved_key(path: str, expression: str) -> tuple[str, str]:
    return (path, re.sub(r"\s+", " ", expression).strip())


def load_baseline(path: Path) -> Baseline:
    if not path.is_file():
        # 零债务的 canonical 形态是不保留 allowance 文件。后续任何新未声明码或
        # 未解析站点都会因为空 baseline 直接进入 new_* 并 BLOCK；缺文件绝不能
        # 被解释成关闭扫描器。
        return Baseline(codes={}, unresolved={})
    document = yaml.safe_load(_read(path)) or {}
    if document.get("schema") != BASELINE_SCHEMA:
        raise SystemExit(
            f"[emitted-error-code] FAIL: 基线 schema 必须是 {BASELINE_SCHEMA}"
        )
    codes: dict[str, dict] = {}
    for entry in document.get("codes") or []:
        if not isinstance(entry, dict):
            raise SystemExit("[emitted-error-code] FAIL: 基线 codes 条目必须是 mapping")
        code = str(entry.get("code", "")).strip()
        if not CODE_PATTERN.fullmatch(code):
            raise SystemExit(
                "[emitted-error-code] FAIL: 基线只接受精确 MODULE.KIND.reason，"
                f"不接受通配符或前缀豁免：{code!r}"
            )
        if code in codes:
            raise SystemExit(f"[emitted-error-code] FAIL: 基线重复条目 {code}")
        codes[code] = entry
    unresolved: dict[tuple[str, str], dict] = {}
    for entry in document.get("unresolved_sites") or []:
        if not isinstance(entry, dict):
            raise SystemExit(
                "[emitted-error-code] FAIL: 基线 unresolved_sites 条目必须是 mapping"
            )
        key = _unresolved_key(str(entry.get("path", "")), str(entry.get("expression", "")))
        # 盲点必须写明手工枚举出的码与所依据的搜索范围；否则盲点条目会退化成
        # 无法复核的豁免。
        if not entry.get("attested_scope"):
            raise SystemExit(
                "[emitted-error-code] FAIL: unresolved_sites 条目必须写明 attested_scope"
                f"（手工枚举 emits 时所依据的搜索范围）：{key[0]}"
            )
        for code in entry.get("emits") or []:
            if not CODE_PATTERN.fullmatch(str(code)):
                raise SystemExit(
                    "[emitted-error-code] FAIL: unresolved_sites.emits 必须是精确"
                    f" MODULE.KIND.reason：{code!r}"
                )
        unresolved[key] = entry
    return Baseline(codes=codes, unresolved=unresolved)


def _baseline_order_issues(path: Path) -> list[str]:
    if not path.is_file():
        return []
    document = yaml.safe_load(_read(path)) or {}
    codes = [
        str(entry.get("code", ""))
        for entry in document.get("codes") or []
        if isinstance(entry, dict)
    ]
    if codes != sorted(codes):
        return ["基线 codes 必须按 code 升序排列，保证 diff 友好"]
    return []


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def evaluate(root: Path, baseline_path: Path) -> tuple[list[str], dict]:
    declarations, sources = load_declarations(root)
    declared = set(declarations)
    vocabulary = load_runtime_vocabulary(root)
    scan = scan_emissions(root, vocabulary, declarations)
    baseline = load_baseline(baseline_path)

    undeclared: dict[str, list[Emission]] = {}
    for emission in scan.emissions:
        if emission.code not in declared:
            undeclared.setdefault(emission.code, []).append(emission)

    failures: list[str] = []
    new_codes = sorted(code for code in undeclared if code not in baseline.codes)
    for code in new_codes:
        sites = undeclared[code]
        locations = sorted({f"{item.path}:{item.function}" for item in sites})
        failures.append(
            f"新增未声明错误码 {code}（{len(sites)} 处发射）：\n      "
            + "\n      ".join(locations)
            + "\n      修复：在所属对象 errors.yaml 声明该码（stable code / http_status /"
            " user_message / recovery.action / go_const / dart_const），或改用已声明码。"
        )

    emission_evidence_forms = {
        "runtime_new_code",
        "runtime_helper_ctor",
        "local_error_ctor",
        "config_module_ctor",
        "generated_app_error_factory",
        "go_const_identifier",
        "domain_sentinel_handler",
        "stable_code_literal",
        "app_stable_code_emission",
        "app_native_stable_code_emission",
        "app_generated_error_symbol",
        "python_stable_code_literal",
    }
    evidenced_codes = {
        emission.code
        for emission in scan.emissions
        if emission.form in emission_evidence_forms
    }
    declared_without_emission = sorted(
        code
        for code, owned in declarations.items()
        if any(SOURCE_EVIDENCE_SURFACES.intersection(item.surfaces) for item in owned)
        and code not in evidenced_codes
    )
    for code in declared_without_emission:
        owners = sorted({item.source_path for item in declarations[code]})
        failures.append(
            f"已声明错误码 {code} 的 emitted_by 包含可静态核验 surface，"
            "但生产源码没有发射证据：\n      "
            + "\n      ".join(owners)
            + "\n      修复：让真实 handler/App emission 使用 owner generated factory/"
            "stable code，或删除尚未实现的 emitted_by 声明；不得以 generated 定义"
            "本身充当发射证据。"
        )

    stale_codes = sorted(code for code in baseline.codes if code not in undeclared)
    for code in stale_codes:
        if code in declared:
            failures.append(
                f"基线条目 {code} 已经有声明位，必须从基线删除（基线只减不增，"
                "不留死豁免）。"
            )
        else:
            failures.append(
                f"基线条目 {code} 已不再被任何覆盖形态发射，必须从基线删除。"
                "若是改用了未覆盖的发射形态，请在同一轮登记新形态。"
            )

    scanned_unresolved = {
        _unresolved_key(site.path, site.expression): site for site in scan.unresolved
    }
    new_unresolved = sorted(key for key in scanned_unresolved if key not in baseline.unresolved)
    for key in new_unresolved:
        site = scanned_unresolved[key]
        failures.append(
            f"新增未解析发射位 {site.path}:{site.function} -> {site.expression}\n"
            "      该站点的 module/kind 不唯一，维度在此失去覆盖。修复：改成字面量"
            " module/kind，或在基线 unresolved_sites 登记并手工枚举它发射的码。"
        )

    stale_unresolved = sorted(
        key for key in baseline.unresolved if key not in scanned_unresolved
    )
    for path, expression in stale_unresolved:
        failures.append(
            f"基线 unresolved_sites 条目已消失，必须删除：{path} -> {expression}"
        )

    failures.extend(_baseline_order_issues(baseline_path))

    # 盲点内手工枚举出的未声明码：当前形态的扫描器无法重新推导它们，因此只报告、
    # 不阻断。把无法自动复核的手工事实做成阻断条件，等于把门禁绑在一份会腐烂的
    # 台账上——那是本仓已经吃过亏的形态。它们属于下一轮形态扩展的范围。
    blind_spot_undeclared: dict[str, list[str]] = {}
    for (path, _expression), entry in sorted(baseline.unresolved.items()):
        if (path, _expression) not in scanned_unresolved:
            continue
        for code in entry.get("emits") or []:
            if code not in declared and code not in undeclared:
                blind_spot_undeclared.setdefault(str(code), []).append(path)

    summary = {
        "declaration_sources": len(sources),
        "declared_codes": len(declared),
        "scanned_go_files": scan.scanned_files,
        "emissions": len(scan.emissions),
        "undeclared_codes": len(undeclared),
        "baselined_codes": sorted(code for code in undeclared if code in baseline.codes),
        "new_codes": new_codes,
        "unresolved_sites": len(scanned_unresolved),
        "new_unresolved_sites": len(new_unresolved),
        "blind_spot_undeclared": blind_spot_undeclared,
        "declared_without_emission": declared_without_emission,
        "emission_forms": {
            form: sum(1 for item in scan.emissions if item.form == form)
            for form in EMISSION_FORMS
        },
        "undeclared_detail": {
            code: sorted({f"{item.path}:{item.function}" for item in sites})
            for code, sites in sorted(undeclared.items())
        },
    }
    return failures, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    parser.add_argument(
        "--report",
        action="store_true",
        help="打印全部未声明码与发射位，用于维护基线",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline).resolve()

    failures, summary = evaluate(root, baseline_path)

    print("[emitted-error-code] 反向维度：实现发射但契约无声明位")
    print(f"  覆盖发射形态：{', '.join(EMISSION_FORMS)}")
    print(
        f"  声明源 {summary['declaration_sources']} 个，"
        f"已声明码 {summary['declared_codes']} 个"
    )
    print(
        f"  扫描 Go 文件 {summary['scanned_go_files']} 个，"
        f"解析出发射 {summary['emissions']} 处"
    )
    print(
        f"  未声明码 {summary['undeclared_codes']} 个："
        f"已在基线内 {len(summary['baselined_codes'])} 个，"
        f"新增 {len(summary['new_codes'])} 个"
    )
    print(
        f"  未解析发射位（维度盲点）{summary['unresolved_sites']} 处："
        f"新增 {summary['new_unresolved_sites']} 处"
    )
    print(
        "  可静态核验 emitted_by 但无生产发射证据 "
        f"{len(summary['declared_without_emission'])} 个"
    )
    print(
        "  各形态证据："
        + ", ".join(
            f"{form}={count}"
            for form, count in summary["emission_forms"].items()
        )
    )
    blind_spot = summary["blind_spot_undeclared"]
    print(
        f"  盲点内手工枚举出的未声明码 {len(blind_spot)} 个（只报告不阻断，"
        "属下一轮形态扩展范围）"
    )
    for code, paths in sorted(blind_spot.items()):
        print(f"      {code}  <- {', '.join(sorted(set(paths)))}")
    print(
        f"  未声明码合计（当前形态 {summary['undeclared_codes']} +"
        f" 盲点手工 {len(blind_spot)}）= "
        f"{summary['undeclared_codes'] + len(blind_spot)}"
    )

    if args.report:
        print("\n  == 未声明码明细 ==")
        for code, locations in summary["undeclared_detail"].items():
            marker = "baselined" if code in summary["baselined_codes"] else "NEW"
            print(f"  [{marker}] {code}")
            for location in locations:
                print(f"        {location}")
        print("\n  == 已声明但无生产发射证据 ==")
        for code in summary["declared_without_emission"]:
            print(f"  {code}")

    if failures:
        print("\n[emitted-error-code] FAIL")
        for index, failure in enumerate(failures, start=1):
            print(f"  {index}. {failure}")
        return 1
    print("[emitted-error-code] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
