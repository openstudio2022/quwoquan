"""公共可公示联系方式白名单加载（contact_info 门的真相源）。

`templates/_registry/catalogs/public_contacts.yaml` 是公共号码白名单唯一真相源：
紧急/公共服务短号、全国性公共热线、允许号段前缀。contact_info 门与 template lint
共用本模块，业务代码不另维护第二套号码清单。

committed 真相源按脚本相对路径定位，不随运行期 QWQ_DATA_ROOT 漂移。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

PUBLIC_CONTACTS_PATH = (
    Path(__file__).resolve().parents[2] / "templates" / "_registry" / "catalogs" / "public_contacts.yaml"
)

_DIGITS_RE = re.compile(r"\D+")


def normalize_number(raw: str) -> str:
    """归一化为纯数字串，便于与白名单比对（去掉 -、空格、括号等）。"""
    return _DIGITS_RE.sub("", str(raw or ""))


@lru_cache(maxsize=1)
def load_public_contacts() -> dict[str, Any]:
    if not PUBLIC_CONTACTS_PATH.is_file():
        return {}
    with PUBLIC_CONTACTS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def default_public_numbers() -> frozenset[str]:
    """默认放行的公共号码（归一化纯数字集合）：紧急短号 + 公共热线。"""
    cat = load_public_contacts()
    nums: set[str] = set()
    for n in cat.get("emergencyNumbers") or []:
        nums.add(normalize_number(n))
    for item in cat.get("publicHotlines") or []:
        if isinstance(item, dict) and item.get("number"):
            nums.add(normalize_number(item["number"]))
    return frozenset(n for n in nums if n)


@lru_cache(maxsize=1)
def default_allow_prefixes() -> tuple[str, ...]:
    cat = load_public_contacts()
    return tuple(normalize_number(p) for p in (cat.get("allowPrefixes") or []) if normalize_number(p))


def allowed_numbers(extra: Iterable[str] | None = None) -> frozenset[str]:
    """默认公共号码 + 调用方核实的景区官方电话（extra）。"""
    base = set(default_public_numbers())
    for e in extra or []:
        n = normalize_number(e)
        if n:
            base.add(n)
    return frozenset(base)


__all__ = [
    "PUBLIC_CONTACTS_PATH",
    "load_public_contacts",
    "normalize_number",
    "default_public_numbers",
    "default_allow_prefixes",
    "allowed_numbers",
]
