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

## 发射形态（当前只覆盖一种，27 不是上界）

只覆盖 `EMISSION_FORMS` 里登记的 runtime `NewCode` 家族。仓内已知至少还有五种
发射形态没有覆盖：`AppErrorFrom*` 生成构造器、错误码字面量、`go_const` 标识符、
文件内局部构造器（如 `releaseError("release_not_found", ...)`）、领域 sentinel 加
handler 状态码映射；端侧 `quwoquan_app/**` 的 Dart 发射也未覆盖。扩形态分轮做，
每扩一种都会抬高基线，分轮才看得清每一步新暴露了什么。

## 判据纪律

解析不出 module/kind 的发射位一律进 `unresolved_sites`，不做笛卡尔展开。
`writeRuntimeError` 那种 module/kind/reason 全是变量的站点，若按 file-wide 取值
集合做叉乘会从 6 个真实码变成 24 个组合码——那正是本仓要避免的弱判据。
未解析站点本身受基线管控：新增盲点同样 BLOCK，避免维度悄悄失去覆盖。

## 基线

`quwoquan_ops/policies/gates/emitted_error_code_declaration_baseline.yaml`
只减不增。基线只接受精确 `MODULE.KIND.reason`，不接受通配符或 module 级批量豁免。
基线条目一旦被声明或不再发射，必须删除，否则 BLOCK（防止死豁免长期挂账）。

用法：
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py --report
"""

from __future__ import annotations

import argparse
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

# 当前覆盖的发射形态。扩形态时在这里登记，并同步 --report 输出与基线说明。
EMISSION_FORMS = (
    "runtime_new_code",  # rterr.NewCode(Module, Kind, reason)
    "runtime_helper_ctor",  # rterr.NewInvalidArgument / NewUnavailable(Module, ...)
)

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*$")
BASELINE_SCHEMA = "emitted-error-code-declaration-baseline"

_GO_SKIP_DIRS = {".git", ".qwq_output", "node_modules", "vendor", "testdata"}
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


def load_declared_codes(root: Path) -> tuple[set[str], list[Path]]:
    declared: set[str] = set()
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
                declared.add(code.strip())
    return declared, sources


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


def scan_emissions(root: Path, vocabulary: RuntimeErrorVocabulary) -> ScanResult:
    result = ScanResult()
    helper_pattern = re.compile(
        r"\b(?P<helper>" + "|".join(sorted(vocabulary.helpers)) + r")\(\s*(?P<module>[^,()]*?)\s*,"
    )
    for path in _go_files(root):
        text = _read(path)
        if "NewCode(" not in text and not any(
            helper + "(" in text for helper in vocabulary.helpers
        ):
            continue
        result.scanned_files += 1
        relative = path.relative_to(root).as_posix()
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
            if function in vocabulary_definitions:
                continue
            scopes = (function_text, package_scope, sibling_scope)
            calls = list(_NEW_CODE_CALL.finditer(function_text))
            for call in calls:
                _classify_new_code(
                    call, scopes, vocabulary, relative, function, len(calls), result
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
                if len(modules) != 1:
                    result.unresolved.append(
                        UnresolvedSite(
                            path=relative,
                            function=function,
                            form="runtime_helper_ctor",
                            expression=f"{helper}({call.group('module').strip()}, ...)",
                        )
                    )
                    continue
                result.emissions.append(
                    Emission(
                        code=f"{next(iter(modules))}.{kind_value}.{reason_value}",
                        form="runtime_helper_ctor",
                        path=relative,
                        function=function,
                    )
                )
    return result


def _classify_new_code(
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
    kinds = _resolve_symbol(kind_expression, scopes, vocabulary.kinds, _KIND_CONVERSION)
    reasons = _resolve_reason(reason_expression, scopes, vocabulary.reasons)
    # module 与 kind 必须唯一：多值时做叉乘会凭空造出从未发射过的组合码。
    if len(modules) != 1 or len(kinds) != 1 or not reasons:
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
    module = next(iter(modules))
    kind = next(iter(kinds))
    for reason in sorted(reasons):
        result.emissions.append(
            Emission(
                code=f"{module}.{kind}.{reason}",
                form="runtime_new_code",
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
        raise SystemExit(f"[emitted-error-code] FAIL: 缺少基线文件 {path}")
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
    declared, sources = load_declared_codes(root)
    vocabulary = load_runtime_vocabulary(root)
    scan = scan_emissions(root, vocabulary)
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
        "  未覆盖形态（下一轮扩展，当前数字不是上界）："
        "AppErrorFrom* 生成构造器、错误码字面量、go_const 标识符、"
        "文件内局部构造器、领域 sentinel 状态码映射、quwoquan_app 端侧发射"
    )
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

    if failures:
        print("\n[emitted-error-code] FAIL")
        for index, failure in enumerate(failures, start=1):
            print(f"  {index}. {failure}")
        return 1
    print("[emitted-error-code] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
