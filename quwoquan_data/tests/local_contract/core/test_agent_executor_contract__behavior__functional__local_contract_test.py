"""会话 agent = 唯一模型执行者 契约门 红绿测试。

覆盖：当前仓库零违规；外部 LLM SDK import / LLM 端点 / 削弱交付防线均可被检出。
可直接运行：python3 quwoquan_data/tests/local_contract/core/test_agent_executor_contract__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

from core.agent_executor_contract import scan_agent_executor_contract  # noqa: E402


def test_repository_has_no_executor_violations():
    issues = scan_agent_executor_contract()
    assert issues == [], "agent-executor 契约违规:\n" + "\n".join(issues)


def test_detects_forbidden_llm_sdk_import():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "bad.py").write_text("import openai\nx = 1\n", encoding="utf-8")
    issues = scan_agent_executor_contract(tmp)
    assert any("forbidden LLM SDK import 'openai'" in i for i in issues), issues


def test_detects_forbidden_from_import():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "bad.py").write_text("from anthropic import Anthropic\n", encoding="utf-8")
    issues = scan_agent_executor_contract(tmp)
    assert any("forbidden LLM SDK import 'anthropic'" in i for i in issues), issues


def test_detects_forbidden_endpoint_literal():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "bad.py").write_text('URL = "https://api.openai.com/v1/chat"\n', encoding="utf-8")
    issues = scan_agent_executor_contract(tmp)
    assert any("forbidden LLM endpoint 'api.openai.com'" in i for i in issues), issues


def test_flags_missing_delivery_guard_anchor():
    # 空目录缺少当前 materialize/draft_io/entity_extract 防线锚点 → 必须报缺失。
    tmp = Path(tempfile.mkdtemp())
    issues = scan_agent_executor_contract(tmp)
    assert any("materialize_apply.py" in i for i in issues), issues
    assert any("draft_io.py" in i for i in issues), issues


def test_cv_image_libs_not_flagged():
    # CV/图像库（cv2/numpy/PIL）不是 LLM 执行者，不得误伤。
    tmp = Path(tempfile.mkdtemp())
    (tmp / "ok.py").write_text("import cv2\nimport numpy as np\nfrom PIL import Image\n", encoding="utf-8")
    issues = scan_agent_executor_contract(tmp)
    assert not any("forbidden LLM" in i for i in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"agent executor contract tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
