"""Typed source identity checks shared by source admission and download gates."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
import json
from pathlib import Path
import re


class SourceIdentityIssueKind(StrEnum):
    PROVINCE_MISMATCH = "province_mismatch"


@dataclass(frozen=True, slots=True)
class SourceIdentityIssue:
    kind: SourceIdentityIssueKind
    expected: str
    actual: str
    evidence: str

    @property
    def code(self) -> str:
        return self.kind.value


_REFERENCE_FILE = (
    Path(__file__).resolve().parents[2] / "reference" / "admin_regions" / "pca.json"
)
_LOCATION_CLAIM_RE = re.compile(
    r"[^。！？!?\n]{0,80}(?:位于|位於|位在|坐落(?:于|於)?|地处|地處)[^。！？!?\n]{0,120}"
)


@lru_cache(maxsize=1)
def _province_aliases() -> dict[str, str]:
    data = json.loads(_REFERENCE_FILE.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for official_name in data:
        name = str(official_name).strip()
        if not name:
            continue
        aliases[name] = name
        if name.endswith(("省", "市")):
            aliases[name[:-1]] = name
    return aliases


def source_geography_issue(
    text: str,
    *,
    expected_province: str,
) -> SourceIdentityIssue | None:
    """Return a hard mismatch only for an explicit location claim in another province."""
    expected = str(expected_province or "").strip()
    if not expected:
        return None
    aliases = _province_aliases()
    expected_official = aliases.get(expected, expected)
    for match in _LOCATION_CLAIM_RE.finditer(str(text or "")[:5000]):
        evidence = re.sub(r"\s+", " ", match.group(0)).strip()
        mentioned = {
            official
            for alias, official in aliases.items()
            if len(alias) >= 2 and alias in evidence
        }
        if expected_official in mentioned or not mentioned:
            continue
        actual = sorted(mentioned)[0]
        return SourceIdentityIssue(
            kind=SourceIdentityIssueKind.PROVINCE_MISMATCH,
            expected=expected_official,
            actual=actual,
            evidence=evidence,
        )
    return None


__all__ = [
    "SourceIdentityIssue",
    "SourceIdentityIssueKind",
    "source_geography_issue",
]
