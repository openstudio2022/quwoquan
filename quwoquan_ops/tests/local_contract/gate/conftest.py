"""gate concern 共享 fixture。

`roster` 原属 test_object_path_map__derivation__local_contract_test.py 的
module-scoped fixture，1000 行硬顶拆分后被 object_path_map 三个拆分套件共用，
逐字下沉到本 conftest。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm


@pytest.fixture(scope="module")
def roster() -> opm.ObjectRoster:
    graph = json.loads((ROOT / opm.CONTRACT_GRAPH_PATH).read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)
