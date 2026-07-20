"""实体主页 compose 输入的现行工作包合同测试。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
for _path in (DATA_ROOT, DATA_ROOT / "tests", DATA_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="entity_object_stages_"))
os.environ["QWQ_OUTPUT_ROOT"] = str(_TMP / ".qwq_output")

from content.execution.runtime_state import write_execution_runtime_state  # noqa: E402
from core.io import read_json  # noqa: E402
from core.paths import (  # noqa: E402
    execution_entity_object_dir,
    execution_entity_page_input_path,
    ensure_execution_layout,
)
from content.homepage.homepage_prepare import prepare_entity_pages  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

_EXECUTION_ID = "20260712--travel-homepage-coverage--cn-sichuan--canary-999"
_DOMAIN, _ETYPE, _NAME = "地点", "景区", "稻城亚丁"


def _seed_spec() -> dict:
    build_execution_fixture(_EXECUTION_ID)
    ensure_execution_layout(_EXECUTION_ID)
    write_execution_runtime_state(_EXECUTION_ID, command="execution")
    return {
        "scope": {
            "coverageTargets": [
                {
                    "entityType": f"{_DOMAIN}/{_ETYPE}",
                    "name": _NAME,
                }
            ]
        }
    }


def test_entity_page_input__uses_execution_object_root_without_retired_sop__contract__local_contract_test():
    prepare_entity_pages(_EXECUTION_ID, _seed_spec())
    payload = read_json(
        execution_entity_page_input_path(
            _EXECUTION_ID,
            _DOMAIN,
            _ETYPE,
            _NAME,
        )
    )["payload"]

    expected = execution_entity_object_dir(
        _EXECUTION_ID,
        _DOMAIN,
        _ETYPE,
        _NAME,
    )
    assert payload["outputDir"] == str(expected)
    assert payload["executionId"] == _EXECUTION_ID
    assert not {"sopDir", "sopTemplate", "sopGuide", "sopExample"} & payload.keys()
    assert "SOP" not in payload["editingInstruction"]
