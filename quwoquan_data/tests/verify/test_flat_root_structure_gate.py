"""scripts/tests 根层级 flat-root 门禁契约。"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="flat_roots_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
os.environ["QWQ_RELEASE_ROOT"] = str(_TMP / "release")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

def _load_gate_module():
    import _common.paths as paths
    import verify.verify_no_flat_roots as gate
    importlib.reload(paths)
    return importlib.reload(gate)


def test_gate_flags_scripts_and_tests_root_flat_files():
    (_TMP / "scripts").mkdir(parents=True, exist_ok=True)
    (_TMP / "tests").mkdir(parents=True, exist_ok=True)
    (_TMP / "scripts" / "bad.py").write_text("print('bad')\n", encoding="utf-8")
    (_TMP / "tests" / "bad_test.py").write_text("print('bad')\n", encoding="utf-8")
    issues = _load_gate_module().verify_no_flat_roots()
    assert any("scripts root flat file" in item for item in issues), issues
    assert any("tests root flat file" in item for item in issues), issues


def test_gate_passes_when_roots_are_clean():
    clean = Path(tempfile.mkdtemp(prefix="flat_roots_clean_"))
    os.environ["QWQ_DATA_ROOT"] = str(clean)
    os.environ["QWQ_RUNTIME_ROOT"] = str(clean / "runtime")
    os.environ["QWQ_PUBLISH_ROOT"] = str(clean / "publish")
    os.environ["QWQ_RELEASE_ROOT"] = str(clean / "release")
    os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(clean / "tasks")
    (clean / "scripts").mkdir(parents=True, exist_ok=True)
    (clean / "tests").mkdir(parents=True, exist_ok=True)
    (clean / "scripts" / "cli.py").write_text("# cli\n", encoding="utf-8")
    (clean / "tests" / "conftest.py").write_text("# conftest\n", encoding="utf-8")
    assert _load_gate_module().verify_no_flat_roots() == []


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"flat-root gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
