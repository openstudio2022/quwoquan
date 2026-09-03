"""gate concern 共享 fixture。

`roster` 原属 test_object_path_map__derivation__local_contract_test.py 的
module-scoped fixture，1000 行硬顶拆分后被 object_path_map 三个拆分套件共用，
逐字下沉到本 conftest。
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm


@pytest.fixture(scope="module")
def isolated_qwq_output_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Path]:
    """Give one contract module a process-private output root."""

    output_root = tmp_path_factory.mktemp("qwq-output")
    previous = os.environ.get("QWQ_OUTPUT_ROOT")
    os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
    try:
        yield output_root
    finally:
        if previous is None:
            os.environ.pop("QWQ_OUTPUT_ROOT", None)
        else:
            os.environ["QWQ_OUTPUT_ROOT"] = previous


@pytest.fixture(scope="module")
def roster() -> opm.ObjectRoster:
    graph = json.loads((ROOT / opm.CONTRACT_GRAPH_PATH).read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)
