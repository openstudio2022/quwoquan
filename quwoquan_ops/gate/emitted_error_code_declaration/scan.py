"""发射扫描主流程：聚合各形态扫描器并归一化 NewCode / helper 站点分类。"""

from __future__ import annotations

import re
from pathlib import Path

from .app_scan import (
    _scan_app_generated_error_emissions,
    _scan_python_stable_code_literals,
)
from .constants import (
    RUNTIME_ERRORS_GO,
    _KIND_CONVERSION,
    _MODULE_CONVERSION,
    _NEW_CODE_CALL,
)
from .go_generated_scan import _scan_generated_symbol_emissions
from .literal_scan import (
    _scan_stable_code_literals,
    _scan_swift_stable_code_emissions,
)
from .local_ctor_scan import (
    _config_selector_values,
    _scan_local_error_constructors,
)
from .models import (
    Emission,
    ErrorDeclaration,
    RuntimeErrorVocabulary,
    ScanResult,
    UnresolvedSite,
    _read,
)
from .resolution import (
    _function_name,
    _go_files,
    _package_scope,
    _resolve_reason,
    _resolve_symbol,
    _split_functions,
)


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
