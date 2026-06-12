"""verify_no_runtime_draft_kit contract tests.

可直接运行：python3 quwoquan_data/tests/verify/test_no_runtime_draft_kit.py
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
        "from _common.draft_io import write_agent_draft\n\n"
        "def run():\n"
        "    write_agent_draft('task', 'batch', 'ref', '# body', model='x', cited_source_paths=[], covered_facts=[])\n",
    )
    issues = scan(tmp)
    assert any("calls write_agent_draft directly" in issue for issue in issues), issues


def test_allows_definition_module_and_tests():
    tmp = Path(tempfile.mkdtemp(prefix="runtime_draft_gate_ok_"))
    _with_file(
        tmp,
        "quwoquan_data/scripts/_common/draft_io.py",
        "def write_agent_draft(*args, **kwargs):\n    return None\n",
    )
    _with_file(
        tmp,
        "quwoquan_data/tests/produce/test_ok.py",
        "from _common.draft_io import write_agent_draft\nwrite_agent_draft('a', 'b', 'c', '# x', model='m', cited_source_paths=[], covered_facts=[])\n",
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
