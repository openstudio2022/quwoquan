"""Shared test configuration.

单元/合约测试落盘隔离契约（数据输出规范）：
- pytest 进程内所有 data-owned 运行期输出只允许写 tempfile 临时根，跑完即弃；
- 仓内根（quwoquan_data/publish 等）与真实 data-owned 输出根
  在 pytest 全量跑完后不得出现新增文件；
- conftest 导入期先于一切测试模块执行 → 在这里强制注入隔离根，
  保证首个导入 `core.paths` 的模块把常量冻结在临时根上
  （历史缺陷：不设 env 的测试模块先导入 paths 会把常量冻结在真实根，
  之后整个 pytest 进程的落盘全部泄漏到真实输出根）。
显式 opt-out：设 QWQ_PYTEST_ALLOW_ENV_ROOTS=1（仅限人工调试，门禁不放行）。
"""
import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Tests are disposable executions. Importing production modules must not create
# bytecode caches inside the source tree, regardless of the caller's cwd or
# shell environment.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
REPO_ROOT = DATA_ROOT.parent
_PYTHON_CACHE_ROOT = Path(tempfile.gettempdir()) / "quwoquan-pytest-bytecode"
sys.pycache_prefix = str(_PYTHON_CACHE_ROOT)
os.environ["PYTHONPYCACHEPREFIX"] = str(_PYTHON_CACHE_ROOT)
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (REPO_ROOT, DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_REAL_OUTPUT_ROOT = REPO_ROOT / ".qwq_output"
_REAL_DATA_OUTPUT_ROOTS = (
    _REAL_OUTPUT_ROOT / "data" / "tasks",
    _REAL_OUTPUT_ROOT / "data" / "releases",
    _REAL_OUTPUT_ROOT / "data" / "local",
)
_SNAPSHOT_IGNORED_DIRECTORIES = {"cache", "__pycache__"}

if os.environ.get("QWQ_PYTEST_ALLOW_ENV_ROOTS") != "1":
    # 清除运行器/外部会话遗留的真实输出根声明，防止测试跟随其落盘。
    for _key in (
        "QWQ_OUTPUT_ROOT",
        "QWQ_PUBLISH_ROOT",
        "QWQ_EXECUTION_PHASE",
        "QWQ_EXECUTION_CONTENT_TYPE",
        "QWQ_EXECUTION_SUPPLY_MODE",
        "QWQ_EXECUTION_SOURCE_KEY",
    ):
        os.environ.pop(_key, None)
    # 强制隔离数据根：即使个别测试模块忘记自建 tempfile 根，
    # paths 常量也只会冻结在这里，绝不落真实根。
    _ISOLATED_ROOT = tempfile.mkdtemp(prefix="qwq_pytest_isolated_")
    os.environ["QWQ_DATA_ROOT"] = _ISOLATED_ROOT
    os.environ["QWQ_OUTPUT_ROOT"] = str(Path(_ISOLATED_ROOT) / "output")
    os.environ["QWQ_PUBLISH_ROOT"] = str(Path(_ISOLATED_ROOT) / "publish")
    # startup probe cache 是运行期降本缓存；pytest 默认关闭，避免环境预检类测试
    # 误把 cache 写入真实 .qwq_output/data/local/workspace/runtime/env。
    os.environ.setdefault("QWQ_CURSOR_STARTUP_PROBE_CACHE_TTL_SECONDS", "0")

_ROOT_ENV_KEYS = (
    "QWQ_DATA_ROOT",
    "QWQ_OUTPUT_ROOT",
    "QWQ_PUBLISH_ROOT",
)
_ISOLATED_ROOT_ENV = {
    key: os.environ[key]
    for key in _ROOT_ENV_KEYS
    if key in os.environ
}

# Import before pytest collects test modules. This freezes every ``from
# core.paths import ...`` binding against the canonical isolated test root,
# rather than whichever test module happened to assign an environment value
# first during collection.
from core import paths as _paths  # noqa: E402


def _restore_isolated_paths() -> None:
    for key in _ROOT_ENV_KEYS:
        value = _ISOLATED_ROOT_ENV.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(_paths)


@pytest.fixture(autouse=True)
def _isolate_data_paths_per_test():
    """Prevent path/env mutation in one test from changing later tests."""
    if os.environ.get("QWQ_PYTEST_ALLOW_ENV_ROOTS") == "1":
        yield
        return
    _restore_isolated_paths()
    try:
        yield
    finally:
        _restore_isolated_paths()


def _snapshot_files(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    snapshot: dict[str, tuple[int, int]] = {}
    for current, directories, files in os.walk(root):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if name not in _SNAPSHOT_IGNORED_DIRECTORIES
        ]
        relative_parent = current_path.relative_to(root)
        for name in files:
            path = current_path / name
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[(relative_parent / name).as_posix()] = (
                stat.st_mtime_ns,
                stat.st_size,
            )
    return snapshot


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "api_integration: requires a real or protocol-compatible external service",
    )
    config._qwq_output_baseline = {
        str(root): _snapshot_files(root) for root in _REAL_DATA_OUTPUT_ROOTS
    }
    config._qwq_publish_baseline = _snapshot_files(DATA_ROOT / "publish")


def pytest_unconfigure(config):
    """pytest 落盘隔离门：session 结束时真实输出根与仓内 publish 不得新增文件。"""
    if os.environ.get("QWQ_PYTEST_ALLOW_ENV_ROOTS") == "1":
        return
    leaks: list[str] = []
    baseline = getattr(config, "_qwq_output_baseline", {})
    for root in _REAL_DATA_OUTPUT_ROOTS:
        output_now = _snapshot_files(root)
        before = baseline.get(str(root), {}) if isinstance(baseline, dict) else {}
        if not isinstance(before, dict):
            before = {}
        added = sorted(set(output_now) - set(before))
        modified = sorted(key for key in set(output_now) & set(before) if output_now[key] != before[key])
        if added or modified:
            details = [f"+{item}" for item in added[:5]] + [f"~{item}" for item in modified[:5]]
            leaks.append(f"{root} changed files={len(added) + len(modified)} ({', '.join(details)})")
    publish_now = _snapshot_files(DATA_ROOT / "publish")
    publish_baseline = getattr(config, "_qwq_publish_baseline", {})
    if not isinstance(publish_baseline, dict):
        publish_baseline = {}
    added = sorted(set(publish_now) - set(publish_baseline))
    modified = sorted(key for key in set(publish_now) & set(publish_baseline) if publish_now[key] != publish_baseline[key])
    if added or modified:
        details = [f"+{item}" for item in added[:5]] + [f"~{item}" for item in modified[:5]]
        leaks.append(
            f"{DATA_ROOT / 'publish'} changed files={len(added) + len(modified)} ({', '.join(details)})"
        )
    if leaks:
        raise RuntimeError(
            "pytest 落盘隔离门 FAIL：测试进程向真实输出根/仓内 publish 泄漏了文件（"
            + "; ".join(leaks)
            + "）。单元/合约测试必须只写 tempfile 临时根。"
        )
