from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_business_object_design_freeze import collect_issues


def test_d0_business_object_design_freeze_contract() -> None:
    assert collect_issues() == []
