"""verifier 根发现与空扫描的负例契约。

本测试锁定「门禁必须诚实报错，而不是扫描到 0 个对象后报告通过」这一条地基约束：

1. 仓库根判据只有一份实现（`quwoquan_ops/cli/lib/repository_root.py`）；两棵脚本树
   （`quwoquan_ops/gate/**` 与 `quwoquan_service/scripts/verify/**`）的 bootstrap 只做转发，
   不得出现第二套推导算法。
2. 每个 verifier 推导出来的根必须真的是仓库根。历史缺陷形态是
   `Path(__file__).resolve().parents[N]` 在脚本被多包一层目录后 N 失配，推导出的根
   依然是一个真实存在的目录，于是扫描命中 0 个对象、门禁反而通过。
   本测试按物理树实时求值，覆盖 `parents[N]` 与 `os.path.dirname` 两种写法。
3. 扫描根不存在、扫描对象数为 0、输入目录传错时，verifier 必须 FAIL。
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.repository_root import (
    REPOSITORY_MARKERS,
    RepositoryRootNotFound,
    ScanRootUnusable,
    find_repository_root,
    is_repository_root,
    require_nonempty,
    require_scan_root,
)
from quwoquan_ops.gate.verify_observability_envelope import envelope_issues
from quwoquan_ops.gate.verify_observability_layout import layout_issues

CANONICAL_MODULE = ROOT / "quwoquan_ops/cli/lib/repository_root.py"
BOOTSTRAPS = (
    ROOT / "quwoquan_ops/gate/repository_root.py",
    ROOT / "quwoquan_service/scripts/verify/repository_root.py",
)
VERIFIER_TREES = (
    ROOT / "quwoquan_ops/gate",
    ROOT / "quwoquan_service/scripts/verify",
)

_PARENTS_RE = re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]")
_DIRNAME_RE = re.compile(r"os\.path\.dirname\(")


# --------------------------------------------------------------------------
# 1. 单一真相源
# --------------------------------------------------------------------------


def test_canonical_repository_root_module_exists() -> None:
    assert CANONICAL_MODULE.is_file(), "根发现的唯一实现缺失"


@pytest.mark.parametrize("bootstrap", BOOTSTRAPS, ids=lambda path: path.parent.name)
def test_bootstrap_delegates_without_reimplementing(bootstrap: Path) -> None:
    """两棵树的 bootstrap 只允许转发，不得自带 marker 判定或目录层数推导。"""
    assert bootstrap.is_file(), f"{bootstrap} 缺失"
    source = bootstrap.read_text(encoding="utf-8")
    assert not _PARENTS_RE.search(source), f"{bootstrap} 不得用目录层数推导仓库根"
    for marker in REPOSITORY_MARKERS:
        assert (
            f'"{marker}"' not in source
        ), f"{bootstrap} 重复声明了 marker {marker}，会与唯一实现漂移"


@pytest.mark.parametrize("bootstrap", BOOTSTRAPS, ids=lambda path: path.parent.name)
def test_bootstrap_resolves_to_the_same_repository_root(bootstrap: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        f"_bootstrap_{bootstrap.parent.name}", bootstrap
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.repository_root() == ROOT
    assert tuple(module.REPOSITORY_MARKERS) == tuple(REPOSITORY_MARKERS)
    # bootstrap 通过物理路径加载唯一实现，模块对象与包导入版本不同一，
    # 因此校验「转发到同一份源码」而不是对象同一性。
    assert (
        Path(module.find_repository_root.__code__.co_filename).resolve()
        == CANONICAL_MODULE.resolve()
    )
    assert (
        Path(module.require_scan_root.__code__.co_filename).resolve()
        == CANONICAL_MODULE.resolve()
    )


# --------------------------------------------------------------------------
# 2. 根发现算法本身的负例
# --------------------------------------------------------------------------


def test_find_repository_root_finds_the_real_root() -> None:
    assert find_repository_root(__file__) == ROOT
    assert find_repository_root(ROOT / "quwoquan_service/scripts/verify") == ROOT


def test_find_repository_root_blocks_when_no_marker_directory_exists(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    with pytest.raises(RepositoryRootNotFound):
        find_repository_root(nested)


def test_partial_markers_are_not_a_repository_root(tmp_path: Path) -> None:
    """只命中一个 marker 不算根——这正是 `quwoquan_service/` 被误判成根的形态。"""
    candidate = tmp_path / "fake"
    (candidate / "quwoquan_service").mkdir(parents=True)
    assert not is_repository_root(candidate)

    nested = candidate / "quwoquan_service" / "scripts" / "verify" / "structure"
    nested.mkdir(parents=True)
    with pytest.raises(RepositoryRootNotFound):
        find_repository_root(nested)


def test_require_scan_root_blocks_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ScanRootUnusable):
        require_scan_root(tmp_path / "absent", "demo")
    existing = tmp_path / "present"
    existing.mkdir()
    assert require_scan_root(existing, "demo") == existing


def test_require_nonempty_blocks_empty_scan(tmp_path: Path) -> None:
    with pytest.raises(ScanRootUnusable):
        require_nonempty([], "demo", root=tmp_path)
    assert require_nonempty([tmp_path], "demo") == [tmp_path]


# --------------------------------------------------------------------------
# 3. 全树守卫：任何 verifier 推导出的根都必须是真仓库根
# --------------------------------------------------------------------------


def _root_derivations(path: Path) -> list[tuple[int, int]]:
    """返回 (行号, parents 下标)。"""
    return [
        (index, int(match.group(1)))
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for match in [_PARENTS_RE.search(line)]
        if match
    ]


def _verifier_scripts() -> list[Path]:
    scripts: list[Path] = []
    for tree in VERIFIER_TREES:
        scripts.extend(sorted(tree.rglob("*.py")))
    assert scripts, "verifier 扫描根为空，守卫本身失效"
    return scripts


def test_every_parents_root_derivation_reaches_the_real_repository_root() -> None:
    """`parents[N]` 若被当作仓库根使用，必须真的指向仓库根。

    只对推导结果落在仓库内、且被命名为「根」的常量求值：这类常量一旦失配，
    扫描就会静默落空。
    """
    offenders: list[str] = []
    for script in _verifier_scripts():
        for line_number, depth in _root_derivations(script):
            line = script.read_text(encoding="utf-8").splitlines()[line_number - 1]
            name = line.split("=")[0].strip()
            if not re.fullmatch(r"_?(REPO(SITORY)?_ROOT|ROOT)", name):
                continue
            try:
                resolved = script.resolve().parents[depth]
            except IndexError:
                offenders.append(f"{script.relative_to(ROOT)}:{line_number}: parents[{depth}] 越界")
                continue
            if resolved != ROOT:
                offenders.append(
                    f"{script.relative_to(ROOT)}:{line_number}: {name} = parents[{depth}] "
                    f"-> {resolved}，不是仓库根 {ROOT}"
                )
    assert not offenders, "\n".join(offenders)


def test_no_verifier_derives_repository_root_via_nested_dirname() -> None:
    """`os.path.dirname` 嵌套是同一缺陷的另一种写法，必须一并禁止。

    只扫 `os.path.dirname` 嵌套 >= 3 层的赋值：这类写法等价于 `parents[N]`，
    但按 `parents[` 做文本扫描会整段漏掉。
    """
    offenders: list[str] = []
    for script in _verifier_scripts():
        source = script.read_text(encoding="utf-8")
        if "os.path.dirname" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover - 语法错误由 verify_python_syntax 负责
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or node.value is None:
                continue
            expression = ast.unparse(node.value)
            if len(_DIRNAME_RE.findall(expression)) < 3:
                continue
            offenders.append(
                f"{script.relative_to(ROOT)}:{node.lineno}: "
                "嵌套 os.path.dirname 推导仓库根，改用 repository_root()"
            )
    assert not offenders, "\n".join(offenders)


def test_guard_detects_the_off_by_one_introduced_by_a_directory_move() -> None:
    """守卫自身的检出能力，用合成输入证明，而不是依赖当前树恰好干净。

    历史形态：脚本原本平铺在 `scripts/verify/`（`parents[3]` 正好是仓库根），
    搬进 `verify/<theme>/` 主题口袋后多了一层，同一个 `parents[3]` 变成
    `quwoquan_service/`——依然是真实目录，扫描却全部落空。
    """
    flat = ROOT / "quwoquan_service/scripts/verify/verify_demo.py"
    pocketed = ROOT / "quwoquan_service/scripts/verify/structure/verify_demo.py"

    assert flat.resolve().parents[3] == ROOT
    assert pocketed.resolve().parents[3] != ROOT
    assert pocketed.resolve().parents[3].is_dir(), "错位后的根仍是真实目录，因此必须靠断言而非崩溃发现"
    assert pocketed.resolve().parents[4] == ROOT


def test_guard_flags_nested_dirname_root_derivation() -> None:
    source = (
        "import os\n"
        "REPO_ROOT = os.path.dirname(\n"
        "    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        ")\n"
    )
    flagged = [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Assign)
        and node.value is not None
        and len(_DIRNAME_RE.findall(ast.unparse(node.value))) >= 3
    ]
    assert flagged, "嵌套 os.path.dirname 必须被守卫检出（`parents[` 文本扫描会整段漏掉）"


def test_migrated_service_verifiers_resolve_root_independently_of_cwd() -> None:
    """服务侧 verifier 在任意工作目录下都必须解析出同一个仓库根。"""
    targets = sorted(
        (ROOT / "quwoquan_service/scripts/verify").rglob("verify_*.py")
    )
    assert targets, "服务侧 verifier 扫描为空"
    for target in targets:
        source = target.read_text(encoding="utf-8")
        if "from repository_root import" not in source:
            continue
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import importlib.util,sys;"
                    f"spec=importlib.util.spec_from_file_location('probe', r'{target}');"
                    "module=importlib.util.module_from_spec(spec);"
                    "sys.modules['probe']=module;"
                    "spec.loader.exec_module(module);"
                    "print(module.repository_root())"
                ),
            ],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, f"{target}: {result.stderr[-800:]}"
        assert result.stdout.strip().endswith(str(ROOT)), (
            f"{target}: 在 cwd=/ 下解析出的根是 {result.stdout.strip()!r}"
        )


# --------------------------------------------------------------------------
# 4. 空集假绿负例：observability 布局与信封
# --------------------------------------------------------------------------


def test_layout_blocks_when_scan_root_is_absent(tmp_path: Path) -> None:
    issues = layout_issues(tmp_path / "absent")
    assert issues, "扫描根不存在时必须 FAIL，不得返回空 issue 列表"
    assert any("不存在" in issue for issue in issues)


def test_layout_blocks_when_env_root_is_absent(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    root.mkdir()
    issues = layout_issues(root)
    assert issues, "缺少 env/ 时必须 FAIL"


def test_layout_blocks_when_zero_runs_are_scanned(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    (root / "env" / "gamma" / "observability").mkdir(parents=True)
    issues = layout_issues(root)
    assert any("0 个 observability run" in issue for issue in issues), issues


def test_layout_blocks_when_input_directory_is_wrong(tmp_path: Path) -> None:
    """把非 observability 目录当扫描根传入时不得报告通过。"""
    wrong = tmp_path / "some-other-tree"
    (wrong / "src").mkdir(parents=True)
    (wrong / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    assert layout_issues(wrong), "传错目录时必须 FAIL"


def test_envelope_blocks_when_scan_root_is_absent(tmp_path: Path) -> None:
    issues = envelope_issues(tmp_path / "absent")
    assert issues, "扫描根不存在时必须 FAIL"


def test_envelope_blocks_when_no_log_samples_exist(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    (root / "env" / "gamma" / "observability" / "run-1").mkdir(parents=True)
    issues = envelope_issues(root)
    assert any("0 份" in issue for issue in issues), issues


def test_envelope_blocks_when_log_files_yield_zero_records(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    logs = root / "env" / "gamma" / "observability" / "run-1" / "logs"
    logs.mkdir(parents=True)
    (logs / "deploy.log").write_text("", encoding="utf-8")
    issues = envelope_issues(root)
    assert any("0 条记录" in issue for issue in issues), issues


def test_envelope_blocks_when_input_directory_is_wrong(tmp_path: Path) -> None:
    wrong = tmp_path / "some-other-tree"
    wrong.mkdir()
    assert envelope_issues(wrong), "传错目录时必须 FAIL"
