"""runtime errors 词表：module/kind/reason 常量与 helper 构造器映射。"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import RUNTIME_ERRORS_GO, _NEW_CODE_CALL
from .models import RuntimeErrorVocabulary, _read


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
