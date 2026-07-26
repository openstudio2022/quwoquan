"""公共可公示联系方式白名单加载（contact_info 门的真相源）。

`control_plane/_shared/catalogs/public_contacts.yaml` 是公共号码白名单唯一真相源：
紧急/公共服务短号、全国性公共热线、允许号段前缀。contact_info 门与 template lint
共用本模块，业务代码不另维护第二套号码清单。

committed 真相源按脚本相对路径定位，不随运行期 QWQ_DATA_ROOT 漂移。
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Iterable, Iterator

import yaml

from core.paths import CONTROL_PLANE_CATALOGS_ROOT

PUBLIC_CONTACTS_PATH = CONTROL_PLANE_CATALOGS_ROOT / "public_contacts.yaml"

_DIGITS_RE = re.compile(r"\D+")

PHONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)"),
    re.compile(r"(?<!\d)(?:400|800)[-\s]?\d{3,4}[-\s]?\d{3,4}(?!\d)"),
)

SOURCE_CONTACT_CONTEXT_MARKERS: tuple[str, ...] = (
    "景区官方电话",
    "景区电话",
    "官方咨询电话",
    "官方联系电话",
    "票务咨询",
    "游客中心电话",
    "游客中心热线",
    "场馆电话",
    "园区电话",
    "接待电话",
)

SOURCE_CONTACT_CONTEXT_RADIUS = 32


def normalize_number(raw: str) -> str:
    """归一化为纯数字串，便于与白名单比对（去掉 -、空格、括号等）。"""
    return _DIGITS_RE.sub("", str(raw or ""))


def iter_phone_numbers(text: str) -> Iterator[re.Match[str]]:
    """Yield supported phone-number matches in source order without duplicates."""
    matches = [match for pattern in PHONE_PATTERNS for match in pattern.finditer(text or "")]
    seen: set[tuple[int, int]] = set()
    for match in sorted(matches, key=lambda item: (item.start(), item.end())):
        location = (match.start(), match.end())
        if location in seen:
            continue
        seen.add(location)
        yield match


def verified_contact_numbers_from_source(text: str) -> tuple[str, ...]:
    """Extract phone numbers explicitly identified as public venue contacts.

    A number is not trusted merely because it occurs in a source. The nearby
    source text must identify it as an official venue, ticketing, visitor
    center, venue, park, or reception contact. This keeps platform and private
    contact numbers out of the article allow set without entity-specific lists.
    """
    source = str(text or "")
    verified: list[str] = []
    for match in iter_phone_numbers(source):
        line_start = source.rfind("\n", 0, match.start()) + 1
        context_start = max(line_start, match.start() - SOURCE_CONTACT_CONTEXT_RADIUS)
        context = source[context_start : match.end()]
        if not any(marker in context for marker in SOURCE_CONTACT_CONTEXT_MARKERS):
            continue
        normalized = normalize_number(match.group(0))
        if normalized and normalized not in verified:
            verified.append(normalized)
    return tuple(verified)


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
    "PHONE_PATTERNS",
    "SOURCE_CONTACT_CONTEXT_MARKERS",
    "load_public_contacts",
    "normalize_number",
    "iter_phone_numbers",
    "verified_contact_numbers_from_source",
    "default_public_numbers",
    "default_allow_prefixes",
    "allowed_numbers",
]
