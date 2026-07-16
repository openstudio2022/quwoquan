from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.source_identity import (  # noqa: E402
    SourceIdentityIssueKind,
    source_geography_issue,
)


def test_source_geography_issue_is_typed_for_explicit_cross_province_location():
    issue = source_geography_issue(
        "姊妹桥又名五福桥，位于四川绵阳市安州区晓坝镇五福村茶坪河上。",
        expected_province="浙江省",
    )

    assert issue is not None
    assert issue.kind is SourceIdentityIssueKind.PROVINCE_MISMATCH
    assert issue.expected == "浙江省"
    assert issue.actual == "四川省"
    assert issue.code == "province_mismatch"


def test_source_geography_issue_allows_matching_or_non_location_mentions():
    assert source_geography_issue(
        "五福桥位于浙江省嘉善县，相关研究也比较了四川省廊桥。",
        expected_province="浙江省",
    ) is None
    assert source_geography_issue(
        "本文比较浙江省与四川省的桥梁保护政策。",
        expected_province="浙江省",
    ) is None
