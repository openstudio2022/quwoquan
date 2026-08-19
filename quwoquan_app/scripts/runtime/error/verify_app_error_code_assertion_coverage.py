#!/usr/bin/env python3
"""App 侧生成错误码的测试断言覆盖棘轮。

`lib/runtime/errors/generated/**` 的每个错误码承载「App 收到该码时的用户
可见语义」（恢复动作、打断级别、文案）；没有测试断言的码意味着其 UI
错误链路（mapper -> UiErrorSemantic -> 错误态组件）从未被证明。

规则：全 App「声明但未在 test/** 中出现」的错误码数量只减不增；断言
证据 token 为码字符串字面量或生成 enum 值引用（``.enumValueName``）。
确属 App 不可触达的码（如服务侧内部专用）按码登记豁免理由。

规格：specs/feature-tree/runtime/runtime-test-pyramid/spec.md#open-003
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT  # noqa: E402

GENERATED_ROOT = APP_ROOT / "lib" / "runtime" / "errors" / "generated"
TEST_ROOT = APP_ROOT / "test"

ENUM_ENTRY_RE = re.compile(r"^\s*(\w+)\('([A-Z_]+\.[A-Z_]+\.[a-z_]+)'", re.M)

#: 确属 App 不可触达的码；每条豁免必须写明理由。
EXEMPT_CODES: dict[str, str] = {}

#: 未断言码数棘轮基线；只减不增，消化批次同步下调。
#: 建门实扫 178 → 首批五域 32 码锁零 → 分域批次(user/content/assistant/
#: chat/tag/notification/entity)全数消化后锁零。新增错误码必须随断言测试合入。
MISSING_CEILING = 0


def declared_codes() -> dict[str, set[str]]:
    """返回 code -> 断言证据 token 集合（码字面量 + `.enum值名` 引用）。"""
    codes: dict[str, set[str]] = {}
    for generated in sorted(GENERATED_ROOT.rglob("*.g.dart")):
        text = generated.read_text(encoding="utf-8", errors="ignore")
        for name, code in ENUM_ENTRY_RE.findall(text):
            codes.setdefault(code, {code}).add(f".{name}")
    return codes


def asserted_text() -> str:
    chunks: list[str] = []
    for test_file in TEST_ROOT.rglob("*_test.dart"):
        try:
            chunks.append(test_file.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def main() -> int:
    if not GENERATED_ROOT.is_dir():
        print(
            "[verify-app-error-code-assertion-coverage] FAIL: missing "
            f"{GENERATED_ROOT}"
        )
        return 1
    codes = declared_codes()
    text = asserted_text()
    missing = sorted(
        code
        for code, tokens in codes.items()
        if code not in EXEMPT_CODES and not any(token in text for token in tokens)
    )
    if len(missing) > MISSING_CEILING:
        print(
            "[verify-app-error-code-assertion-coverage] FAIL: unasserted app "
            f"error codes grew to {len(missing)} (> {MISSING_CEILING}); new "
            "error codes must ship with a test asserting the mapped UI "
            f"semantics, sample: {missing[:5]}"
        )
        return 1
    print(
        "[verify-app-error-code-assertion-coverage] OK: declared="
        f"{len(codes)} missing={len(missing)} (ceiling={MISSING_CEILING}, "
        f"exempt={len(EXEMPT_CODES)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
