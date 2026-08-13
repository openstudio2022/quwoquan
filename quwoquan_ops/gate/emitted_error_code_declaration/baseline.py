"""迁移基线：精确 MODULE.KIND.reason 豁免与 unresolved_sites 盲点登记的加载校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .constants import BASELINE_SCHEMA, CODE_PATTERN
from .models import _read


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
