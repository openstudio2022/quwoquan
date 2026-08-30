# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` 端侧分片采集的本地契约。

全量一次 `flutter test --coverage --branch-coverage test/local_contract` 会把全部
测试文件的覆盖率累积在同一个进程里，内存 + swap 耗尽后被 OS 杀死。分片把它拆成
若干次顺序执行再合并。这么做的风险是显而易见的：分片可能变成「少跑一些测试」的
后门，合并可能悄悄丢掉只在某一片被触达的文件，红片可能被当成噪声跳过。本测试就
按这三条风险线组织，每条都用负例证明：

1. **分片是全集的确定性划分**：同样输入切两次完全一致；每个测试文件恰好出现在
   一片里；片数只影响执行方式，不影响 `unit_scope`，也不能小于 1。
2. **合并取并集且命中数累加**：只在 A 片被触达的文件必须留在结果里（不是后者
   覆盖前者），同一文件同一行在两片的命中次数相加（不是简单拼接把分母翻倍），
   分支按 `BRDA` 明细合并且 `-`（未求值）不得抹掉另一片的实测命中。
3. **红片照样阻断**：任一片非零退出即 `RedTestRun`，产物 receipt 记
   ``testsGreen=false``，`--write-baseline` 被拒绝且 tracked baseline 字节不变；
   红片不进断点续跑缓存，下次必须重跑。

这里不跑真实 `flutter test`：`vcr._run` 被替换成产出确定性 lcov 的替身，因此断言
的是分片/合并/阻断这套机制本身，而不是某次真实采集的数字。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_canonical_coverage as vcr

APP_UNIT = "app:probe_domain/probe_context/probe_object"


# ---------------------------------------------------------------------------
# 合并语义：并集 + 命中累加
# ---------------------------------------------------------------------------
#
# 两片都触达 `lib/shared.dart`，但覆盖到的行与分支各不相同；`lib/only_in_a.dart`
# 只在 A 片出现，`lib/only_in_b.dart` 只在 B 片出现。每片自身的 LF/LH 都与它自己
# 的 DA 明细自洽，合并结果的 LF/LH 由合并后的 DA 重新推导。

_SHARD_A_LCOV = "\n".join(
    [
        "SF:lib/shared.dart",
        "DA:1,1",
        "DA:2,0",
        "DA:3,2",
        "LF:3",
        "LH:2",
        "BRDA:1,0,0,1",
        "BRDA:1,0,1,0",
        "BRDA:9,0,0,-",
        "BRDA:11,0,0,-",
        "BRDA:13,0,0,7",
        "end_of_record",
        "SF:lib/only_in_a.dart",
        "DA:1,4",
        "LF:1",
        "LH:1",
        "end_of_record",
        "",
    ]
)

_SHARD_B_LCOV = "\n".join(
    [
        "SF:lib/shared.dart",
        "DA:2,5",
        "DA:3,0",
        "DA:4,0",
        "LF:3",
        "LH:1",
        "BRDA:1,0,0,0",
        "BRDA:1,0,1,3",
        "BRDA:9,0,0,2",
        "BRDA:11,0,0,-",
        "BRDA:13,0,0,-",
        "end_of_record",
        "SF:lib/only_in_b.dart",
        "DA:1,0",
        "LF:1",
        "LH:0",
        "end_of_record",
        "",
    ]
)


def _merged(*texts: str) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for text in texts:
        vcr.merge_lcov_records(records, vcr.parse_lcov_records(text))
    return records


def test_merging_two_shards_takes_the_union_of_files_not_the_last_one_wins() -> None:
    """只在一片被触达的文件必须留在合并结果里。

    「后者覆盖前者」是这里最容易写出来的错：合并结果会丢掉 `only_in_a.dart`，
    该对象的 `file` 轴分母不变而分子掉一个，覆盖率静默下降却看不出原因。
    """
    merged = vcr.parse_lcov(vcr.render_lcov(_merged(_SHARD_A_LCOV, _SHARD_B_LCOV)))

    assert sorted(merged) == [
        "lib/only_in_a.dart",
        "lib/only_in_b.dart",
        "lib/shared.dart",
    ]
    assert merged["lib/only_in_a.dart"]["line"] == (1, 1)
    assert merged["lib/only_in_b.dart"]["line"] == (0, 1)
    # 两片共有的文件同样不是「后者赢」：若 B 片整条记录顶掉 A 片，这里会退化成
    # B 片自己的 (1, 3)。
    assert merged["lib/shared.dart"]["line"] == (3, 4)


def test_merging_sums_line_hits_instead_of_concatenating_denominators() -> None:
    """同一文件在两片的明细取并集：分母是行号并集，不是两片分母相加。

    简单拼接两份 lcov 会让 `lib/shared.dart` 出现两个 `LF:3`，分母翻倍成 6；
    该文件所属对象的行覆盖率会被凭空腰斩。
    """
    merged = vcr.parse_lcov(vcr.render_lcov(_merged(_SHARD_A_LCOV, _SHARD_B_LCOV)))

    # 行号并集 {1,2,3,4}；命中并集 {1(A 命中), 2(B 命中), 3(A 命中)}。
    assert merged["lib/shared.dart"]["line"] == (3, 4)
    naive_concatenation = 3 + 3
    assert merged["lib/shared.dart"]["line"][1] != naive_concatenation


def test_a_line_covered_in_one_shard_stays_covered_after_merging() -> None:
    """A 片命中、B 片没命中的行，合并后仍然算命中——这正是「并集而非覆盖」。"""
    records = _merged(_SHARD_A_LCOV, _SHARD_B_LCOV)

    # 第 3 行：A 片 2 次、B 片 0 次 → 合并 2 次。
    assert records["lib/shared.dart"]["lines"][3] == 2
    # 第 2 行：A 片 0 次、B 片 5 次 → 合并 5 次。
    assert records["lib/shared.dart"]["lines"][2] == 5
    # 第 4 行只有 B 片报告过，且从未命中：它进分母不进分子。
    assert records["lib/shared.dart"]["lines"][4] == 0


def test_branch_merging_keeps_a_hit_that_only_one_shard_observed() -> None:
    """分支合并比行合并更容易出错：`-`（未求值）不得抹掉另一片的实测命中。

    `BRDA` 的 `taken` 有三种状态：`-` 表示这一片根本没求值过该分支，`0` 表示
    求值过但没走到，正整数表示走到过。把 `-` 当成 `0` 直接相加在本例里恰好也
    得到同一个数，但会让「两片都没求值」退化成「求值过但没走到」——分母不变、
    语义却从「测不到」变成「测到了没覆盖」。因此这里同时锁住四种组合。
    """
    branches = _merged(_SHARD_A_LCOV, _SHARD_B_LCOV)["lib/shared.dart"]["branches"]

    assert branches[(1, "0", "0")] == 1  # 命中 + 未命中 → 命中
    assert branches[(1, "0", "1")] == 3  # 未命中 + 命中 → 命中
    assert branches[(9, "0", "0")] == 2  # 未求值 + 命中 → 命中
    assert branches[(11, "0", "0")] is None  # 未求值 + 未求值 → 仍然未求值
    assert branches[(13, "0", "0")] == 7  # 命中 + 未求值 → 命中

    merged = vcr.parse_lcov(vcr.render_lcov(_merged(_SHARD_A_LCOV, _SHARD_B_LCOV)))
    # 分母是 BRDA 键的并集（5 条），分子是合并后命中的 4 条。
    assert merged["lib/shared.dart"]["branch"] == (4, 5)


def test_merging_is_order_independent_so_shard_scheduling_cannot_move_the_number() -> None:
    """合并必须可交换：换个顺序跑分片不许改变覆盖率数字。"""
    forward = vcr.render_lcov(_merged(_SHARD_A_LCOV, _SHARD_B_LCOV))
    backward = vcr.render_lcov(_merged(_SHARD_B_LCOV, _SHARD_A_LCOV))

    assert forward == backward


def test_merged_output_has_the_same_record_shape_flutter_itself_writes() -> None:
    """合并产物必须与全量运行同形，`parse_lcov` 才会走完全相同的代码路径。

    Flutter 3.44 的 `--branch-coverage` 写 `SF / DA* / LF / LH / BRDA*`，不写
    `BRF`/`BRH`。合并结果若额外写出汇总行，同一维度就出现了第二套口径。
    """
    rendered = vcr.render_lcov(_merged(_SHARD_A_LCOV, _SHARD_B_LCOV))

    assert "BRF:" not in rendered
    assert "BRH:" not in rendered
    kinds = [
        line.split(":", 1)[0] if ":" in line else line
        for line in rendered.splitlines()
        if line.startswith(("SF:", "DA:", "LF:", "LH:", "BRDA:")) or line == "end_of_record"
    ]
    assert kinds[:8] == ["SF", "DA", "LF", "LH", "end_of_record", "SF", "DA", "LF"]
    assert rendered.count("SF:") == rendered.count("end_of_record")


def test_a_shard_summary_disagreeing_with_its_own_details_blocks() -> None:
    """输入分片自身 LF/LH 与 DA 不自洽时阻断，而不是替它挑一套口径。"""
    drifted = "SF:lib/a.dart\nDA:1,1\nLF:9\nLH:1\nend_of_record\n"

    with pytest.raises(vcr.CoverageError, match="LF=9"):
        vcr.parse_lcov_records(drifted)

    with pytest.raises(vcr.CoverageError, match="LH=9"):
        vcr.parse_lcov_records("SF:lib/a.dart\nDA:1,1\nLF:1\nLH:9\nend_of_record\n")


def test_an_empty_shard_lcov_contributes_nothing_and_does_not_block() -> None:
    """某一片可能一个 `lib/**` 文件都没加载到，`flutter test` 产出零字节 lcov。

    实测：只测跨 package generated contracts 的测试文件就是这种情况。这是分片
    下的真实事实，不是采集失败；整体合并为空才是失败，由 `collect_app` 阻断。
    """
    assert vcr.parse_lcov_records("") == {}
    assert _merged("", _SHARD_A_LCOV, "") == _merged(_SHARD_A_LCOV)


# ---------------------------------------------------------------------------
# 分片确定性与完整性
# ---------------------------------------------------------------------------


def _partition_facts(
    plan: Sequence[Sequence[str]], test_files: Sequence[str]
) -> tuple[list[str], int]:
    flattened = [name for shard in plan for name in shard]
    return flattened, len(flattened)


def test_the_same_input_always_produces_the_same_shards() -> None:
    """分片只依赖 `(排序后的文件清单, 片数)`；连切两次必须完全一致。

    仓库刚因为 ContractGraph 非确定性吃过亏：切分只要带一点顺序不稳定，覆盖率
    数字就会在两次采集之间抖动，棘轮的「只增不减」立刻失去意义。
    """
    test_files = tuple(f"test/local_contract/{index:03d}_test.dart" for index in range(23))

    for shard_count in (1, 2, 3, 5, 23):
        first = vcr.app_shard_plan(test_files, shard_count)
        second = vcr.app_shard_plan(test_files, shard_count)
        assert first == second
        # 顺序反过来喂进去也必须先经排序：切分是清单内容的函数，不是遍历顺序的函数。
        assert vcr.app_shard_plan(sorted(test_files), shard_count) == first


def test_every_test_file_lands_in_exactly_one_shard() -> None:
    """分片是全集的划分：既不重复也不遗漏，因此不构成任何跳过名单。"""
    test_files = tuple(f"test/local_contract/{index:03d}_test.dart" for index in range(23))

    for shard_count in (1, 2, 3, 5, 7, 23):
        plan = vcr.app_shard_plan(test_files, shard_count)
        flattened, total = _partition_facts(plan, test_files)

        assert len(plan) == shard_count
        assert total == len(test_files), "有文件被重复执行或漏执行"
        assert sorted(flattened) == sorted(test_files)
        assert all(shard for shard in plan), "不允许空片"
        sizes = {len(shard) for shard in plan}
        assert max(sizes) - min(sizes) <= 1, "片间大小相差不得超过一个文件"


def test_the_real_repository_test_roster_is_sorted_and_stable() -> None:
    """真实仓库的测试清单必须稳定有序，且只收 `_test.dart`。"""
    first = vcr.app_test_files()
    second = vcr.app_test_files()

    assert first == second
    assert first == tuple(sorted(first))
    assert first, "App L0 套件不得为空"
    assert all(name.endswith(vcr.APP_TEST_FILE_SUFFIX) for name in first)
    assert all(name.startswith(f"{vcr.APP_TEST_TARGET}/") for name in first)
    # 默认片数由文件数派生，不写死；它必须是一个真正会分片的值。
    assert vcr.default_app_shard_count(first) == max(
        1, -(-len(first) // vcr.APP_SHARD_MAX_TEST_FILES)
    )
    assert vcr.app_shard_plan(first, vcr.default_app_shard_count(first))


def test_a_shard_count_that_could_skip_tests_is_rejected() -> None:
    """片数不是逃逸口：0 片、负片、多于文件数的片都必须阻断。"""
    test_files = ("a_test.dart", "b_test.dart")

    for shard_count in (0, -1):
        with pytest.raises(vcr.CoverageError, match=">= 1"):
            vcr.app_shard_plan(test_files, shard_count)
    with pytest.raises(vcr.CoverageError, match="空片"):
        vcr.app_shard_plan(test_files, 3)
    # CLI 层同样拒绝，且在跑任何测试之前就返回。
    assert vcr.main(["--collect", "--scope", "app", "--app-shards", "0"]) == 2


def test_shard_count_is_a_capacity_knob_and_never_enters_the_comparable_scope() -> None:
    """片数不进 `scope`：合并结果与全量运行等价，换片数不该让基线不可比。

    反过来说，片数也因此不能被用来解释覆盖率变化——它必须真的不影响数字。
    """
    scope = vcr.unit_scope(APP_UNIT)

    assert "shard" not in scope
    assert vcr.APP_TEST_TARGET in scope
    assert "--branch-coverage" in scope


# ---------------------------------------------------------------------------
# 采集编排：断点续跑与红片阻断
# ---------------------------------------------------------------------------


def _fake_app_tree(app_root: Path, test_file_count: int) -> list[str]:
    """造一棵最小 App 测试树，返回 canonical 相对路径清单。"""
    directory = app_root / vcr.APP_TEST_TARGET
    directory.mkdir(parents=True)
    names = []
    for index in range(test_file_count):
        path = directory / f"probe_{index:03d}{vcr.APP_TEST_FILE_SUFFIX}"
        path.write_text("void main() {}\n", encoding="utf-8")
        names.append(path.relative_to(app_root).as_posix())
    return sorted(names)


def _shard_lcov_for(test_file: str) -> str:
    """每个测试文件触达一个专属源文件，便于逐片核对合并结果。"""
    stem = Path(test_file).stem
    return (
        f"SF:lib/{stem}.dart\n"
        "DA:1,1\n"
        "DA:2,0\n"
        "LF:2\n"
        "LH:1\n"
        "BRDA:1,0,0,1\n"
        "BRDA:1,0,1,0\n"
        "end_of_record\n"
    )


def _install_fake_flutter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    red_test_files: Iterable[str] = (),
    invocations: list[tuple[str, ...]] | None = None,
) -> None:
    """把 `flutter test` 替换成产出确定性 lcov 的替身。

    替身按传入的测试文件拼出 lcov（各文件源文件互不重叠，所以拼接即真值），
    命中 `red_test_files` 的片以非零码退出——与真实 `flutter test` 一样，红的
    时候照样写出覆盖率产物。
    """
    red = set(red_test_files)

    def fake_run(
        command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        coverage_path = next(
            argument[len("--coverage-path=") :]
            for argument in command
            if argument.startswith("--coverage-path=")
        )
        test_files = tuple(
            argument
            for argument in command
            if argument.endswith(vcr.APP_TEST_FILE_SUFFIX)
        )
        if invocations is not None:
            invocations.append(test_files)
        Path(coverage_path).write_text(
            "".join(_shard_lcov_for(name) for name in test_files), encoding="utf-8"
        )
        failed = sorted(red.intersection(test_files))
        return subprocess.CompletedProcess(
            list(command),
            1 if failed else 0,
            stdout=f"probe shard: {len(failed)} failing\n",
            stderr="",
        )

    monkeypatch.setattr(vcr, "_run", fake_run)


def _identity() -> dict[str, str]:
    return {
        "headCommit": "1" * 40,
        "headTree": "1" * 40,
        "sourceTreeDigest": "sha256:" + "1" * 64,
        "testTreeDigest": "sha256:" + "1" * 64,
        "attributionDigest": "sha256:" + "1" * 64,
        "configDigest": "sha256:" + "1" * 64,
        "toolchainDigest": "sha256:" + "1" * 64,
        "collectionScopeDigest": "sha256:" + "1" * 64,
    }


def test_real_app_shard_uses_the_guarded_runner_with_a_closed_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage owns runtime identity and cannot inherit CI shard/tag filters."""

    destination = tmp_path / "coverage.lcov.info"
    test_files = (
        "test/local_contract/ordinary__local_contract_test.dart",
        "test/local_contract/serial__local_contract_test.dart",
    )
    app_root = tmp_path / "quwoquan_app"
    for test_file, source in (
        (test_files[0], "void main() {}\n"),
        (test_files[1], "@Tags(<String>['serial'])\nvoid main() {}\n"),
    ):
        path = app_root / test_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    captured: list[dict[str, object]] = []

    def fake_run(
        command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        captured.append(
            {"command": list(command), "cwd": cwd, "env": dict(env or {})}
        )
        phase_path = Path(
            next(
                argument.removeprefix("--coverage-path=")
                for argument in command
                if argument.startswith("--coverage-path=")
            )
        )
        phase_path.write_text(_SHARD_A_LCOV, encoding="utf-8")
        return subprocess.CompletedProcess(list(command), 0, stdout="", stderr="")

    forced_environment = {
        "FLUTTER_TEST_GUARD_MAX_ATTEMPTS": "1",
        "FLUTTER_TEST_GUARD_TIMEOUT_SECONDS": "1800",
        "QWQ_APP_RUNTIME_ENV": "alpha",
    }
    for key in set(vcr.APP_COVERAGE_CLEARED_ENV_KEYS) | set(forced_environment):
        monkeypatch.setenv(key, "ambient-invalid")
    monkeypatch.setattr(vcr, "APP_ROOT", app_root)
    monkeypatch.setattr(vcr, "_run", fake_run)

    assert vcr._run_app_shard(destination, test_files) == ""
    assert destination.is_file()
    assert len(captured) == 2
    nonserial_command = captured[0]["command"]
    serial_command = captured[1]["command"]
    assert isinstance(nonserial_command, list)
    assert isinstance(serial_command, list)
    assert nonserial_command[:2] == [
        sys.executable,
        str(vcr.APP_ROOT / vcr.APP_FLUTTER_TEST_RUNNER),
    ]
    assert "--coverage" in nonserial_command
    assert "--branch-coverage" in nonserial_command
    assert "--reporter=compact" in nonserial_command
    assert "--dart-define=APP_RUNTIME_ENV=alpha" in nonserial_command
    assert "--concurrency=4" in nonserial_command
    assert "--exclude-tags" in nonserial_command
    assert "serial" in nonserial_command
    assert "--concurrency=1" in serial_command
    assert "--tags" in serial_command
    assert "--exclude-tags" not in serial_command
    assert not any(
        argument == "--total-shards"
        or argument.startswith("--total-shards=")
        or argument == "--shard-index"
        or argument.startswith("--shard-index=")
        for command in (nonserial_command, serial_command)
        for argument in command
    )
    assert tuple(
        argument
        for argument in nonserial_command
        if argument.endswith(vcr.APP_TEST_FILE_SUFFIX)
    ) == test_files
    assert tuple(
        argument
        for argument in serial_command
        if argument.endswith(vcr.APP_TEST_FILE_SUFFIX)
    ) == (test_files[1],)

    for invocation in captured:
        environment = invocation["env"]
        assert isinstance(environment, dict)
        for key in vcr.APP_COVERAGE_CLEARED_ENV_KEYS:
            assert key not in environment
        for key, expected in forced_environment.items():
            assert environment[key] == expected


def _environment_read_keys(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            is_os_getenv = (
                isinstance(owner, ast.Name)
                and owner.id == "os"
                and node.func.attr == "getenv"
            )
            is_environ_get = (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "os"
                and owner.attr == "environ"
                and node.func.attr == "get"
            )
            if is_os_getenv or is_environ_get:
                if not node.args:
                    raise AssertionError(f"{path}: environment selector 缺少 key")
                key = node.args[0]
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    raise AssertionError(
                        f"{path}: environment selector key 必须是静态字符串"
                    )
                keys.add(key.value)
        if isinstance(node, ast.Subscript):
            owner = node.value
            if (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "os"
                and owner.attr == "environ"
            ):
                if not isinstance(node.slice, ast.Constant) or not isinstance(
                    node.slice.value, str
                ):
                    raise AssertionError(
                        f"{path}: environment selector key 必须是静态字符串"
                    )
                keys.add(node.slice.value)
    return keys


@pytest.mark.parametrize(
    "expression",
    (
        'os.environ.get("NEW_TEST_SELECTOR")',
        "os.environ.get('NEW_TEST_SELECTOR')",
        "os.getenv('NEW_TEST_SELECTOR')",
        "os.environ['NEW_TEST_SELECTOR']",
    ),
)
def test_environment_selector_scanner_recognizes_supported_python_reads(
    expression: str,
    tmp_path: Path,
) -> None:
    source = tmp_path / "selector.py"
    source.write_text(f"import os\nVALUE = {expression}\n", encoding="utf-8")
    assert _environment_read_keys(source) == {"NEW_TEST_SELECTOR"}


@pytest.mark.parametrize(
    "expression",
    (
        "os.environ.get(KEY)",
        "os.getenv(KEY)",
        "os.environ[KEY]",
    ),
)
def test_environment_selector_scanner_rejects_dynamic_keys(
    expression: str,
    tmp_path: Path,
) -> None:
    source = tmp_path / "selector.py"
    source.write_text(
        f"import os\nKEY = 'NEW_TEST_SELECTOR'\nVALUE = {expression}\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="key 必须是静态字符串"):
        _environment_read_keys(source)


def test_app_coverage_environment_clears_or_forces_every_owned_selector() -> None:
    forced = {
        "FLUTTER_TEST_GUARD_MAX_ATTEMPTS": "1",
        "FLUTTER_TEST_GUARD_TIMEOUT_SECONDS": "1800",
        "QWQ_APP_RUNTIME_ENV": "alpha",
    }
    hostile = {
        key: "ambient-invalid"
        for key in set(vcr.APP_COVERAGE_CLEARED_ENV_KEYS) | set(forced)
    }
    environment = vcr.canonical_app_coverage_environment(hostile)
    assert set(vcr.APP_COVERAGE_CLEARED_ENV_KEYS).isdisjoint(environment)
    for key, expected in forced.items():
        assert environment[key] == expected


def test_app_coverage_environment_owns_every_downstream_selector() -> None:
    forced = {
        "FLUTTER_TEST_GUARD_MAX_ATTEMPTS",
        "FLUTTER_TEST_GUARD_TIMEOUT_SECONDS",
        "QWQ_APP_RUNTIME_ENV",
    }
    downstream_paths = (
        vcr.APP_ROOT / vcr.APP_FLUTTER_TEST_RUNNER,
        vcr.APP_ROOT / vcr.APP_RUNTIME_DEFINE_RESOLVER,
        vcr.APP_ROOT / vcr.APP_TEST_SELECTION_POLICY,
    )
    observed = {key for path in downstream_paths for key in _environment_read_keys(path)}
    assert observed == (
        set(vcr.APP_COVERAGE_CLEARED_ENV_KEYS) - {"QWQ_DEPLOY_TARGET"}
    ) | forced


def test_app_coverage_config_identity_contains_the_runner_and_topology_closure() -> None:
    inputs = set(vcr._collection_config_inputs(vcr.APP_COLLECTION_TARGET))
    environment_root = vcr.ROOT / "quwoquan_ops" / "environments"
    expected = {
        vcr.APP_ROOT / vcr.APP_FLUTTER_TEST_RUNNER,
        vcr.APP_ROOT / vcr.APP_RUNTIME_DEFINE_RESOLVER,
        vcr.APP_ROOT / vcr.APP_TEST_SELECTION_POLICY,
        vcr.APP_ROOT / "scripts/_common/__init__.py",
        vcr.ROOT / "quwoquan_ops/cli/lib/common.py",
        vcr.ROOT / "quwoquan_ops/cli/lib/environment_topology.py",
        vcr.ROOT / "quwoquan_ops/cli/lib/output_paths.py",
        vcr.ROOT / "quwoquan_ops/cli/lib/port_manifest.py",
        environment_root / "domain_governance.yaml",
        environment_root / "local_env_port_manifest.yaml",
        *environment_root.glob("*/runtime.yaml"),
    }
    assert expected <= inputs
    policy = vcr.app_coverage_policy_identity()
    assert policy["runtimeEnvironment"] == "alpha"
    assert policy["launchPolicy"] == "test_live"
    assert policy["concurrency"] == "4"
    assert policy["serialConcurrency"] == "1"
    assert policy["phases"] == ["exclude-serial", "serial-only"]
    assert policy["maxAttempts"] == "1"
    assert policy["resolvedDartDefines"]["PUBLIC_WEB_BASE_URL"].startswith(
        "https://"
    )


def test_selector_byte_drift_changes_the_app_config_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_root = tmp_path / "quwoquan_app"
    ops_root = tmp_path / "quwoquan_ops"
    required = (
        app_root / ".flutter-version",
        app_root / "pubspec.yaml",
        app_root / "pubspec.lock",
        app_root / vcr.APP_FLUTTER_TEST_RUNNER,
        app_root / vcr.APP_RUNTIME_DEFINE_RESOLVER,
        app_root / vcr.APP_TEST_SELECTION_POLICY,
        app_root / "scripts/_common/__init__.py",
        ops_root / "cli/lib/common.py",
        ops_root / "cli/lib/environment_topology.py",
        ops_root / "cli/lib/output_paths.py",
        ops_root / "cli/lib/port_manifest.py",
        ops_root / "environments/domain_governance.yaml",
        ops_root / "environments/local_env_port_manifest.yaml",
        ops_root / "environments/alpha/runtime.yaml",
    )
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture:{path.name}\n", encoding="utf-8")
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(vcr, "APP_ROOT", app_root)

    inputs = vcr._collection_config_inputs(vcr.APP_COLLECTION_TARGET)
    before = vcr._tree_digest(inputs, label="fixture App coverage config")
    selector = app_root / vcr.APP_TEST_SELECTION_POLICY
    selector.write_text("fixture:selector-drift\n", encoding="utf-8")
    after = vcr._tree_digest(
        vcr._collection_config_inputs(vcr.APP_COLLECTION_TARGET),
        label="fixture App coverage config",
    )

    assert before != after


@pytest.fixture()
def sharded_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., list[str]]:
    """把 App 根与覆盖率缓存都指向 tmp，返回建树函数。"""
    app_root = tmp_path / "quwoquan_app"
    monkeypatch.setattr(vcr, "APP_ROOT", app_root)
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(vcr, "current_collection_identity", lambda _target: _identity())
    return lambda count: _fake_app_tree(app_root, count)


def test_sharded_collection_merges_into_one_artifact_covering_every_test_file(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分片跑完的合并产物必须覆盖全部测试文件触达的源文件，一个都不少。"""
    test_files = sharded_app(6)
    invocations: list[tuple[str, ...]] = []
    _install_fake_flutter(monkeypatch, invocations=invocations)
    destination = vcr.artifact_path(vcr.APP_COLLECTION_TARGET)

    vcr.collect_app(destination, shards=3)

    assert len(invocations) == 3
    assert sorted(name for shard in invocations for name in shard) == test_files
    measured = vcr.parse_lcov(destination.read_text(encoding="utf-8"))
    assert sorted(measured) == sorted(
        f"lib/{Path(name).stem}.dart" for name in test_files
    )
    # 每个源文件 2 行 1 命中、2 分支 1 命中；分片不改变逐文件的数字。
    assert all(values["line"] == (1, 2) for values in measured.values())
    assert all(values["branch"] == (1, 2) for values in measured.values())


def test_changing_the_shard_count_does_not_change_the_merged_coverage(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一棵测试树切 2 片和切 6 片必须得到字节相同的合并产物。

    这是「分片与全量语义等价」最直接的可执行证据：如果片数能移动数字，那么片数
    就必须进 scope；它不进 scope 的前提正是这条断言成立。
    """
    sharded_app(6)
    _install_fake_flutter(monkeypatch)
    destination = vcr.artifact_path(vcr.APP_COLLECTION_TARGET)

    vcr.collect_app(destination, shards=2)
    two_shards = destination.read_text(encoding="utf-8")
    vcr.collect_app(destination, shards=6)
    six_shards = destination.read_text(encoding="utf-8")
    vcr.collect_app(destination, shards=1)
    single_shard = destination.read_text(encoding="utf-8")

    assert two_shards == six_shards == single_shard


def test_a_green_shard_is_reused_on_resume_and_a_red_shard_is_not(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """断点续跑只复用绿片：红片必须重跑，否则一次偶然的红会被永久缓存。"""
    test_files = sharded_app(6)
    invocations: list[tuple[str, ...]] = []
    # 第 5 个文件落在第 3 片（每片两个文件），让那一片红。
    _install_fake_flutter(
        monkeypatch, red_test_files=[test_files[4]], invocations=invocations
    )
    destination = vcr.artifact_path(vcr.APP_COLLECTION_TARGET)

    with pytest.raises(vcr.RedTestRun):
        vcr.collect_app(destination, shards=3)
    assert len(invocations) == 3

    invocations.clear()
    with pytest.raises(vcr.RedTestRun):
        vcr.collect_app(destination, shards=3)

    # 两片绿的被复用，只有红的那片重跑。
    assert invocations == [(test_files[4], test_files[5])]


def test_resume_reruns_everything_when_the_shard_plan_or_sources_change(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """片数变化或采集 identity 漂移时，旧片一律作废并清理，不得混进合并结果。"""
    sharded_app(6)
    invocations: list[tuple[str, ...]] = []
    _install_fake_flutter(monkeypatch, invocations=invocations)
    destination = vcr.artifact_path(vcr.APP_COLLECTION_TARGET)

    vcr.collect_app(destination, shards=3)
    assert len(invocations) == 3
    invocations.clear()
    vcr.collect_app(destination, shards=3)
    assert invocations == [], "未漂移时应当整体复用"

    # 片数变化 → 分片边界变了，旧片不可复用，且旧文件被清理。
    vcr.collect_app(destination, shards=2)
    assert len(invocations) == 2
    assert sorted(
        path.name for path in vcr.app_shard_directory().iterdir()
    ) == sorted(
        path.name
        for index in range(2)
        for path in vcr._app_shard_artifact_paths(index, 2)
    )

    # 源码漂移 → identity 变了，同一套分片方案也必须重跑。
    invocations.clear()
    drifted = dict(_identity(), sourceTreeDigest="sha256:" + "9" * 64)
    monkeypatch.setattr(vcr, "current_collection_identity", lambda _target: drifted)
    vcr.collect_app(destination, shards=2)
    assert len(invocations) == 2


def test_a_tampered_shard_lcov_is_not_reused(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中间产物被改写后必须重跑；否则分片缓存就成了注入覆盖率的入口。"""
    sharded_app(4)
    invocations: list[tuple[str, ...]] = []
    _install_fake_flutter(monkeypatch, invocations=invocations)
    destination = vcr.artifact_path(vcr.APP_COLLECTION_TARGET)

    vcr.collect_app(destination, shards=2)
    invocations.clear()
    lcov_path, _state_path = vcr._app_shard_artifact_paths(0, 2)
    lcov_path.write_text(
        "SF:lib/injected.dart\nDA:1,1\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )

    vcr.collect_app(destination, shards=2)

    assert len(invocations) == 1
    assert "lib/injected.dart" not in destination.read_text(encoding="utf-8")


def test_a_shard_that_produces_no_lcov_blocks_as_a_collection_failure(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """片被 OOM 杀掉、连 lcov 都没写出来时是采集失败，不是「红测试」。

    两者的处置不同：红测试仍会落一份带 ``testsGreen=false`` 的完整产物供诊断，
    采集失败则连产物都不可信，必须以 `CoverageError` 直接中断。
    """
    sharded_app(2)

    def fake_run(
        command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
    ):
        return subprocess.CompletedProcess(list(command), 137, stdout="", stderr="Killed")

    monkeypatch.setattr(vcr, "_run", fake_run)

    with pytest.raises(vcr.CoverageError, match="未产出 lcov"):
        vcr.collect_app(vcr.artifact_path(vcr.APP_COLLECTION_TARGET), shards=2)


def test_an_all_empty_sharded_run_blocks_instead_of_producing_an_empty_artifact(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每片都空 = 采集没有真正生效，必须阻断而不是写一份空 lcov。"""
    sharded_app(4)

    def fake_run(
        command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
    ):
        coverage_path = next(
            argument[len("--coverage-path=") :]
            for argument in command
            if argument.startswith("--coverage-path=")
        )
        Path(coverage_path).write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(list(command), 0, stdout="", stderr="")

    monkeypatch.setattr(vcr, "_run", fake_run)

    with pytest.raises(vcr.CoverageError, match="没有产出任何 lcov 记录"):
        vcr.collect_app(vcr.artifact_path(vcr.APP_COLLECTION_TARGET), shards=2)


# ---------------------------------------------------------------------------
# 红片阻断（防止分片变成绕过绿测要求的后门）
# ---------------------------------------------------------------------------


def _receipts_for_app_unit() -> list[dict]:
    return [
        {
            "schema": vcr.ARTIFACT_RECEIPT_SCHEMA,
            "ruleId": vcr.RULE_ID,
            "target": target,
            "artifactRef": vcr._display(vcr.artifact_path(target)),
            "artifactDigest": "sha256:" + "2" * 64,
            **{key: value.replace("1", "2") for key, value in _identity().items()},
            "testsGreen": True,
        }
        for target in vcr.collection_targets([APP_UNIT])
    ]


def _tracked_baseline() -> dict:
    metrics = {
        metric: {"covered": 40, "total": 100, "percent": 40.0}
        for metric in vcr.METRICS_BY_KIND[vcr.KIND_FLUTTER_LCOV]
    }
    receipts = _receipts_for_app_unit()
    return {
        "_governance": {
            "owner": "o",
            "reason": "r",
            "expires_when": "w",
            "measure": "m",
        },
        "schema": vcr.BASELINE_SCHEMA,
        "ruleId": vcr.RULE_ID,
        "policy": {
            "tolerance_percentage_points": 0.3,
            "tolerance_reason": "r",
            "improvement_slack_percentage_points": 3.0,
            "improvement_slack_reason": "r",
            "granularity_units": 2.0,
            "granularity_units_reason": "r",
        },
        "receipts": {vcr.receipt_digest(receipt): receipt for receipt in receipts},
        "units": {APP_UNIT: vcr.unit_entry(metrics, APP_UNIT, receipts=receipts)},
    }


def test_one_red_shard_blocks_the_baseline_write_and_leaves_it_byte_identical(
    tmp_path: Path,
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分片下的 `measuredFromGreenTests` 语义：一片红 = 整次不绿。

    这是本批最重要的负例。分片最危险的失效模式不是数字算错，而是「部分片绿」
    被悄悄当成「本次实跑全绿」——那样 `--write-baseline` 就能在有红测试的情况下
    写进基线，canonical rule 从此建立在一个假的 provenance 上。这里断言三件事同时成立：
    退出码非 0、tracked baseline 字节不变、产物 receipt 记 ``testsGreen=false``
    且任何复用路径都拒绝它。
    """
    test_files = sharded_app(6)
    _install_fake_flutter(monkeypatch, red_test_files=[test_files[3]])
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(vcr, "resolve_units", lambda _scope, _requested: [APP_UNIT])
    baseline_path.write_text(
        json.dumps(_tracked_baseline(), ensure_ascii=False), encoding="utf-8"
    )
    original = baseline_path.read_bytes()

    exit_code = vcr.main(
        ["--collect", "--write-baseline", "--unit", APP_UNIT, "--app-shards", "3"]
    )

    assert exit_code == 1
    assert baseline_path.read_bytes() == original, "红片绝不能改写 tracked baseline"

    # 与全量运行同形：产物照样落盘供诊断，但 provenance 如实记为不绿。
    receipt = json.loads(
        vcr.artifact_receipt_path(vcr.APP_COLLECTION_TARGET).read_text(encoding="utf-8")
    )
    assert receipt["testsGreen"] is False
    with pytest.raises(vcr.CoverageError, match="未全绿"):
        vcr.validate_artifact_receipt(vcr.APP_COLLECTION_TARGET)


def test_a_red_shard_still_blocks_plain_verification_not_only_baseline_writes(
    tmp_path: Path,
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """求值路径同样阻断：红片测出来的覆盖率不是准出证据。

    这里必须核对阻断理由而不只是退出码：红片被吞掉后求值照样会因为别的原因失败，
    只断言 `== 1` 的话这条测试就通不过判别力。
    """
    test_files = sharded_app(4)
    _install_fake_flutter(monkeypatch, red_test_files=[test_files[0]])
    monkeypatch.setattr(
        vcr, "BASELINE_PATH", tmp_path / "canonical_coverage_baseline.json"
    )
    monkeypatch.setattr(vcr, "resolve_units", lambda _scope, _requested: [APP_UNIT])

    assert vcr.main(["--collect", "--unit", APP_UNIT, "--app-shards", "2"]) == 1

    reported = capsys.readouterr().err
    assert "1/2 片红" in reported
    assert "覆盖率必须来自绿的测试" in reported


def test_every_red_shard_is_reported_not_just_the_first(
    sharded_app: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一片红之后仍要跑完剩余分片，与全量运行「跑完全部再退出」同形。

    提前中断会让每次修复都只暴露下一片的第一个问题，也会让合并产物残缺却仍被
    写进 receipt。
    """
    test_files = sharded_app(6)
    invocations: list[tuple[str, ...]] = []
    _install_fake_flutter(
        monkeypatch,
        red_test_files=[test_files[0], test_files[5]],
        invocations=invocations,
    )

    with pytest.raises(vcr.RedTestRun) as failure:
        vcr.collect_app(vcr.artifact_path(vcr.APP_COLLECTION_TARGET), shards=3)

    assert len(invocations) == 3, "红片之后必须继续跑完剩余分片"
    assert "2/3 片红" in str(failure.value)
    assert "shard 1/3" in str(failure.value)
    assert "shard 3/3" in str(failure.value)
