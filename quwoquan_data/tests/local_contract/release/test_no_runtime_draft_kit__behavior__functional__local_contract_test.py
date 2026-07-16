"""verify_no_runtime_draft_kit contract tests.

可直接运行：python3 quwoquan_data/tests/local_contract/release/test_no_runtime_draft_kit__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from verify.verify_no_runtime_draft_kit import scan  # noqa: E402


def _with_file(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_repository_has_no_runtime_draft_kit_violations():
    issues = scan()
    assert issues == [], "runtime draft kit gate violations:\n" + "\n".join(issues)


def test_detects_write_agent_draft_call_in_regular_script():
    tmp = Path(tempfile.mkdtemp(prefix="runtime_draft_gate_"))
    _with_file(
        tmp,
        "quwoquan_data/scripts/verify/bad_writer.py",
        "from content.post.draft_io import write_agent_draft\n\n"
        "def run():\n"
        "    write_agent_draft('task', 'batch', 'ref', '# body', model='x', cited_source_paths=[], covered_facts=[])\n",
    )
    issues = scan(tmp)
    assert any("calls write_agent_draft directly" in issue for issue in issues), issues


def test_detects_mechanical_homepage_body_builder():
    """重新引入脚本拼主页正文骨架（如 _compose_homepage_body）→ FAIL。"""
    tmp = Path(tempfile.mkdtemp(prefix="runtime_draft_gate_hp_"))
    _with_file(
        tmp,
        "quwoquan_data/scripts/content/homepage/homepage.py",
        "def _compose_homepage_body(name, facts):\n"
        "    return '# ' + name + '\\n\\n' + '。'.join(facts)\n",
    )
    issues = scan(tmp)
    assert any("mechanical homepage body builder" in issue for issue in issues), issues


def test_allows_legit_homepage_helpers():
    """主页正当辅助（prompt 渲染 / summary 映射 / 门体）不得误伤。"""
    tmp = Path(tempfile.mkdtemp(prefix="runtime_draft_gate_hp_ok_"))
    _with_file(
        tmp,
        "quwoquan_data/scripts/content/homepage/homepage.py",
        "def _render_entity_page_prompt(payload):\n    return '写回 page.md'\n\n"
        "def _homepage_summary(name, facts):\n    return name + ' 概况'\n\n"
        "def _homepage_gate_body(page_text):\n    return page_text\n",
    )
    issues = scan(tmp)
    assert issues == [], issues


def test_allows_definition_module_and_tests():
    tmp = Path(tempfile.mkdtemp(prefix="runtime_draft_gate_ok_"))
    _with_file(
        tmp,
        "quwoquan_data/scripts/core/draft_io.py",
        "def write_agent_draft(*args, **kwargs):\n    return None\n",
    )
    _with_file(
        tmp,
        "quwoquan_data/tests/produce/test_ok.py",
        "from content.post.draft_io import write_agent_draft\nwrite_agent_draft('a', 'b', 'c', '# x', model='m', cited_source_paths=[], covered_facts=[])\n",
    )
    issues = scan(tmp)
    assert issues == [], issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"verify_no_runtime_draft_kit tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
