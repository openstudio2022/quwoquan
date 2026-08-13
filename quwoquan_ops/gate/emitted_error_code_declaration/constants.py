"""扫描范围、发射形态清单与共享正则的唯一定义处。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = (
    Path(__file__).resolve().parents[3]
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
