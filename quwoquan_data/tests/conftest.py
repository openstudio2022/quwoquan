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


_PATHS_ROOT_CONSTANTS = ("DATA_ROOT", "OUTPUT_ROOT", "PUBLISH_ROOT")


def _snapshot_diff(now: dict, before: object) -> list[str]:
    if not isinstance(before, dict):
        before = {}
    added = sorted(set(now) - set(before))
    modified = sorted(
        key for key in set(now) & set(before) if now[key] != before[key]
    )
    if not added and not modified:
        return []
    return [f"+{item}" for item in added[:5]] + [f"~{item}" for item in modified[:5]]


def _isolation_breach_evidence(paths_module, isolated_env: dict) -> list[str]:
    """测试进程自证：隔离 env 与 ``core.paths`` root 常量必须仍指向隔离根。

    这是「常量冻结在真实根」历史缺陷的直接检测，与并行进程写入无关，
    因此没有并发误报。
    """
    breaches: list[str] = []
    isolated_root = isolated_env.get("QWQ_DATA_ROOT")
    if not isolated_root:
        return ["isolated QWQ_DATA_ROOT declaration is missing"]
    for key in _ROOT_ENV_KEYS:
        expected = isolated_env.get(key)
        actual = os.environ.get(key)
        if actual != expected:
            breaches.append(f"env {key} drifted: expected={expected} actual={actual}")
    isolated_base = Path(isolated_root).resolve()
    for name in _PATHS_ROOT_CONSTANTS:
        value = Path(getattr(paths_module, name)).resolve()
        if not value.is_relative_to(isolated_base):
            breaches.append(f"core.paths.{name} escaped the isolated root: {value}")
    return breaches


def pytest_sessionfinish(session, exitstatus):
    """把只读的 capsule / library 目录交还为可删除状态。

    冻结后的 capsule 与 content_library 条目按设计是只读的，这是防篡改语义的一
    部分，不能在生产路径上放宽。但只读**目录**会让 pytest 下一次会话启动时的
    basetemp 清理失败（`rm_rf` 报 `Directory not empty`），临时目录因此逐次累积。
    因此在会话结束时统一恢复写位：只读语义在被测树内已经被断言过，此时它只剩
    妨碍回收的作用。
    """
    factory = getattr(session.config, "_tmp_path_factory", None)
    basetemp = getattr(factory, "_basetemp", None)
    if basetemp is None:
        return
    # 同时放宽同级的 garbage-* 残留：那是前几次会话留下的、pytest 已放弃回收的
    # 目录，恢复写位后下一次会话的清理才能真正删掉它们。
    roots = [Path(basetemp)]
    roots.extend(sorted(Path(basetemp).parent.glob("garbage-*")))
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                path.chmod(path.stat().st_mode | 0o700)
            except OSError:
                # 回收是尽力而为：无法放宽的目录留给下一次会话，不能让清理动作
                # 反过来决定测试会话的成败。
                continue
        try:
            root.chmod(root.stat().st_mode | 0o700)
        except OSError:
            continue


def pytest_unconfigure(config):
    """pytest 落盘隔离门。

    判定分三级：
    1. 隔离机制自证失败（env/paths 常量逃出隔离根）→ FAIL，这是测试进程
       自己的强证据；
    2. 仓内 ``quwoquan_data/publish`` 出现 diff → FAIL，数据任务按契约不写
       仓内 publish，diff 只能来自测试进程；
    3. 真实 ``.qwq_output/data`` 根出现 diff 而隔离自证完好 → 降级 WARNING：
       文件系统快照无法区分写入者，并行数据任务运行期的写入会命中这里。
       残余漏检（测试硬编码绝对路径写真实根且隔离常量完好）已知且接受——
       并发误报会训练所有人忽略红灯，代价远大于该残余风险。
    """
    if os.environ.get("QWQ_PYTEST_ALLOW_ENV_ROOTS") == "1":
        return
    failures: list[str] = []
    warnings: list[str] = []

    breaches = _isolation_breach_evidence(_paths, _ISOLATED_ROOT_ENV)
    failures.extend(f"isolation breach: {item}" for item in breaches)

    baseline = getattr(config, "_qwq_output_baseline", {})
    for root in _REAL_DATA_OUTPUT_ROOTS:
        before = baseline.get(str(root), {}) if isinstance(baseline, dict) else {}
        details = _snapshot_diff(_snapshot_files(root), before)
        if not details:
            continue
        message = f"{root} changed files ({', '.join(details)})"
        if breaches:
            failures.append(message)
        else:
            warnings.append(message)

    publish_details = _snapshot_diff(
        _snapshot_files(DATA_ROOT / "publish"),
        getattr(config, "_qwq_publish_baseline", {}),
    )
    if publish_details:
        failures.append(
            f"{DATA_ROOT / 'publish'} changed files ({', '.join(publish_details)})"
        )

    for message in warnings:
        print(
            "[qwq-isolation-gate] WARNING: 真实输出根在测试期间出现写入但隔离"
            f"自证完好，可能来自并行数据任务：{message}"
        )
    if failures:
        raise RuntimeError(
            "pytest 落盘隔离门 FAIL：" + "; ".join(failures) + "。"
            "单元/合约测试必须只写 tempfile 临时根。"
        )
