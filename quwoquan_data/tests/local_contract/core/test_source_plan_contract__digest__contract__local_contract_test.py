from __future__ import annotations

import re
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.source_plan_contract import source_plan_rule_signature  # noqa: E402


def test_source_plan_rules_use_one_canonical_digest_without_version_label() -> None:
    signature = source_plan_rule_signature("travel", "/entity/地点/景区/杭州西湖")

    assert set(signature) == {"vertical", "entityId", "digest"}
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", signature["digest"])
    assert "version" not in signature
    assert "hash" not in signature
