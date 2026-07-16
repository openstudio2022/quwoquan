"""scripts/tests 根层级 flat-root 门禁契约。

隔离契约：本模块需要 reload `core.paths`（gate 按 env 重新推导根）。
reload 会替换整个 pytest 进程共享的 paths 常量 → 每个测试必须
（1）执行期显式声明自己的 env 根（不依赖导入期声明，防其它模块导入覆盖）；
（2）结束后恢复执行前 env 并 reload 回去，避免污染后续测试模块。
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_ENV_KEYS = (
    "QWQ_DATA_ROOT",
    "QWQ_RUNTIME_ROOT",
    "QWQ_PUBLISH_ROOT",
    "QWQ_RELEASE_ROOT",
    "QWQ_COMMITTED_TASKS_ROOT",
)


def _reload_paths_and_gate():
    import core.paths as paths
    import verify.verify_no_flat_roots as gate
    importlib.reload(paths)
    return importlib.reload(gate)


@contextmanager
def _isolated_root(prefix: str):
    """在独立临时根上运行 gate，退出时恢复 env 与共享 paths 常量。

    恢复采用「模块字典快照回写」而非再次 reload：reload 只能按当前 env 重算，
    无法还原进程内其它消费者在导入期绑定的冻结常量（`from paths import X` 副本），
    直接回写快照才能保证后续测试模块看到 reload 前的同一份共享状态。
    """
    import core.paths as paths

    saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
    saved_state = dict(paths.__dict__)
    root = Path(tempfile.mkdtemp(prefix=prefix))
    os.environ["QWQ_DATA_ROOT"] = str(root)
    os.environ["QWQ_RUNTIME_ROOT"] = str(root / "runtime")
    os.environ["QWQ_PUBLISH_ROOT"] = str(root / "publish")
    os.environ["QWQ_RELEASE_ROOT"] = str(root / "release")
    os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(root / "tasks")
    try:
        yield root, _reload_paths_and_gate()
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        paths.__dict__.update(saved_state)


def test_gate_flags_scripts_and_tests_root_flat_files():
    with _isolated_root("flat_roots_") as (root, gate):
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "bad.py").write_text("print('bad')\n", encoding="utf-8")
        (root / "tests" / "bad_test.py").write_text("print('bad')\n", encoding="utf-8")
        issues = gate.verify_no_flat_roots()
        assert any("scripts root flat file" in item for item in issues), issues
        assert any("tests root flat file" in item for item in issues), issues


def test_gate_passes_when_roots_are_clean():
    with _isolated_root("flat_roots_clean_") as (root, gate):
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "tests").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "cli.py").write_text("# cli\n", encoding="utf-8")
        (root / "tests" / "conftest.py").write_text("# conftest\n", encoding="utf-8")
        assert gate.verify_no_flat_roots() == []


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"flat-root gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
