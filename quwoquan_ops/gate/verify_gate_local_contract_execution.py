#!/usr/bin/env python3
"""门禁自证门禁：挂在 gate 链上的门禁，其配套 local_contract 测试必须也被 gate 链执行。

已发现的高危形态：某个门禁脚本每次 `make gate` 都跑，但它自己的 local_contract
测试长期没有任何 gate 链执行——门禁实现回退、判据失效、baseline 口径漂移都不会有
人看见，直到线上出事才被发现。

判据全部是结构性事实，不做关键词或上下文匹配：

* 「被 gate 链引用」= 从 `quwoquan_ops/gate/gate_repo.sh` 出发，按 shell 命令行与
  Make target 递归展开得到的可达命令集合；
* 「配套 local_contract 测试」= 测试文件名以门禁脚本的 canonical 名（去掉
  `verify_` 前缀）为词边界前缀，落在 canonical local_contract 测试树内；
* 「测试被执行」= 该测试文件出现在同一可达命令集合里，或落在某条可达 pytest
  目录参数之下，或被 `python3 -m unittest <module>` 直接点名。

存量缺口按 `owner` / `reason` / `expires_when` 登记基线，只减不增；新增即 BLOCK。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_ENTRY = ROOT / "quwoquan_ops/gate/gate_repo.sh"
BASELINE_PATH = ROOT / "quwoquan_ops/policies/gates/gate_local_contract_execution_baseline.yaml"

#: 门禁脚本的归属目录。两处都是「稳定门禁」的 canonical 存放位置。
GATE_SCRIPT_ROOTS = (
    "quwoquan_ops/gate/",
    "quwoquan_service/scripts/verify/",
)

#: canonical local_contract 测试树。App Dart 树不在此列——它没有 Python 门禁配套。
LOCAL_CONTRACT_TEST_ROOTS = (
    "quwoquan_ops/tests/local_contract",
    "quwoquan_data/tests/local_contract",
    "quwoquan_app/test/local_contract",
)

#: 可展开的 Makefile。`make -C <dir> <target>` 会解析到对应目录的 Makefile。
MAKEFILE_BY_DIR = {
    "": ROOT / "Makefile",
    ".": ROOT / "Makefile",
    "quwoquan_service": ROOT / "quwoquan_service/Makefile",
}

SHELL_SCRIPT_RE = re.compile(
    r"(?:^|[\s;(&|])(?:python3?|bash|sh)(?:\s+-[A-Za-z]+)*\s+"
    r"([A-Za-z0-9_./-]+\.(?:py|sh))"
)
UNITTEST_MODULE_RE = re.compile(r"-m\s+unittest\s+\\?\s*([A-Za-z0-9_.]+)")
PYTEST_ARG_RE = re.compile(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*)")
MAKE_TARGET_RE = re.compile(
    r"(?:^|[\s;(&|])(?:make|\$\(MAKE\))\s+(?:-C\s+\"?([A-Za-z0-9_./-]+)\"?\s+)?"
    r"((?!-)[A-Za-z0-9][A-Za-z0-9._-]*)"
)


@dataclass(frozen=True)
class Gap:
    gate: str
    test: str

    def key(self) -> str:
        return f"{self.gate} -> {self.test}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _makefile_recipes(makefile: Path) -> dict[str, list[str]]:
    """target -> recipe lines（含 prerequisite 行本身，用于解析依赖 target）。"""
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    for line in _read(makefile).splitlines():
        if line.startswith("\t"):
            if current is not None:
                recipes[current].append(line.strip())
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._%-]*)\s*:(?!=)(.*)$", line)
        if not match:
            if not line.strip():
                current = None
            continue
        current = match.group(1)
        recipes.setdefault(current, [])
        # prerequisite 也是被执行的 target。
        for prerequisite in match.group(2).split():
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", prerequisite):
                recipes[current].append(f"$(MAKE) {prerequisite}")
    return recipes


def _collect_reachable_commands() -> list[str]:
    """gate 链可达的全部命令行文本。"""
    lines: list[str] = _read(GATE_ENTRY).splitlines()
    seen_targets: set[tuple[str, str]] = set()
    pending = list(lines)
    collected: list[str] = []
    makefiles: dict[str, dict[str, list[str]]] = {}

    while pending:
        line = pending.pop()
        collected.append(line)
        for directory, target in MAKE_TARGET_RE.findall(line):
            makefile = MAKEFILE_BY_DIR.get(directory)
            if makefile is None or not makefile.is_file():
                continue
            key = (directory, target)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            if directory not in makefiles:
                makefiles[directory] = _makefile_recipes(makefile)
            recipe = makefiles[directory].get(target)
            if not recipe:
                continue
            prefix = "" if directory in {"", "."} else f"{directory}/"
            pending.extend(
                # Makefile 内的相对路径按其 Makefile 所在目录解析。
                re.sub(r"(?<=\s)(quwoquan_[a-z]+/)", rf"{prefix}\1", entry)
                if prefix
                else entry
                for entry in recipe
            )
    return collected


def _normalize(candidate: str) -> str:
    path = (ROOT / candidate).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return candidate


def _reachable_scripts_and_test_paths(
    commands: list[str],
) -> tuple[set[str], set[str], set[str]]:
    scripts: set[str] = set()
    pytest_paths: set[str] = set()
    unittest_modules: set[str] = set()
    for line in commands:
        for candidate in SHELL_SCRIPT_RE.findall(line):
            scripts.add(_normalize(candidate))
        for module in UNITTEST_MODULE_RE.findall(line):
            unittest_modules.add(module)
        if "pytest" in line:
            for candidate in PYTEST_ARG_RE.findall(line):
                resolved = _normalize(candidate)
                if (ROOT / resolved).exists():
                    pytest_paths.add(resolved)
        # 续行的 pytest 参数与 recipe 主体在同一 collected 列表里，因此
        # 目录参数即使换行也会被下面的 bare-path 分支捕获。
        for candidate in PYTEST_ARG_RE.findall(line):
            resolved = _normalize(candidate)
            if any(
                resolved == root or resolved.startswith(f"{root}/")
                for root in LOCAL_CONTRACT_TEST_ROOTS
            ) and (ROOT / resolved).exists():
                pytest_paths.add(resolved)
    return scripts, pytest_paths, unittest_modules


def _is_gate_script(rel: str) -> bool:
    return rel.endswith(".py") and any(
        rel.startswith(root) for root in GATE_SCRIPT_ROOTS
    )


def _subjects(name: str) -> set[str]:
    """仓库命名约定下该文件名可能表达的 subject 集合。

    canonical 测试名形如 `<subject>__<facet>__local_contract_test.py`，门禁脚本名
    形如 `verify_<subject>.py`。`verify_` / `test_` 前缀既可能是约定前缀，也可能是
    subject 自己的第一个词（例如 `verify_test_directory_layout.py` 的 subject 就是
    `test_directory_layout`），所以两种读法都保留，取交集判定配套。
    """
    head = name.split("__", 1)[0]
    subjects = {head}
    for prefix in ("verify_", "test_"):
        if head.startswith(prefix):
            subjects.add(head[len(prefix) :])
    return subjects


def _local_contract_tests() -> list[str]:
    tests: list[str] = []
    for root_name in LOCAL_CONTRACT_TEST_ROOTS:
        root = ROOT / root_name
        if not root.is_dir():
            continue
        tests.extend(
            path.relative_to(ROOT).as_posix()
            for path in sorted(root.rglob("*_test.py"))
        )
    return tests


def _companion_tests(gate_rel: str, tests: list[str]) -> list[str]:
    """配套测试：两侧 subject 集合相交。名字不同源的门禁/测试对不在判定范围内。"""
    subjects = _subjects(Path(gate_rel).stem)
    return [test for test in tests if _subjects(Path(test).stem) & subjects]


def _test_is_executed(
    test_rel: str,
    scripts: set[str],
    pytest_paths: set[str],
    unittest_modules: set[str],
) -> bool:
    if test_rel in scripts:
        return True
    module = test_rel[: -len(".py")].replace("/", ".")
    if module in unittest_modules:
        return True
    for candidate in pytest_paths:
        if test_rel == candidate or test_rel.startswith(f"{candidate}/"):
            return True
    return False


def _load_baseline() -> tuple[set[str], list[str]]:
    # 缺口容忍基线已在缺口归零后删除，本门禁转为零容忍：没有基线文件是正常状态，
    # 任何缺口都是新增缺口。重新引入基线文件只会被当成额外容忍面，不应该发生。
    if not BASELINE_PATH.is_file():
        return set(), []
    try:
        document = yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        return set(), [f"baseline 解析失败: {error}"]
    problems: list[str] = []
    governance = document.get("governance")
    if not isinstance(governance, dict):
        problems.append("baseline 缺少 governance 段")
        governance = {}
    for required in ("owner", "reason", "expires_when"):
        if not str(governance.get(required, "")).strip():
            problems.append(f"baseline governance 缺少 {required}")
    entries = document.get("unexecuted_companion_tests") or []
    keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"baseline 条目必须是映射: {entry!r}")
            continue
        gate = str(entry.get("gate", ""))
        test = str(entry.get("test", ""))
        if not gate or not test:
            problems.append(f"baseline 条目缺少 gate/test: {entry!r}")
            continue
        keys.add(Gap(gate, test).key())
    return keys, problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--print-current",
        action="store_true",
        help="打印当前实际缺口，用于生成或收紧基线",
    )
    args = parser.parse_args(argv)

    commands = _collect_reachable_commands()
    scripts, pytest_paths, unittest_modules = _reachable_scripts_and_test_paths(
        commands
    )
    gates = sorted(rel for rel in scripts if _is_gate_script(rel))
    if not gates:
        print(
            "[gate-local-contract] FAIL: 没有从 gate_repo.sh 解析出任何门禁脚本；"
            "解析器已失真，先修解析器，不要让门禁静默通过",
            file=sys.stderr,
        )
        return 1

    tests = _local_contract_tests()
    gaps: list[Gap] = []
    for gate in gates:
        for test in _companion_tests(gate, tests):
            if not _test_is_executed(
                test, scripts, pytest_paths, unittest_modules
            ):
                gaps.append(Gap(gate, test))

    if args.print_current:
        for gap in sorted(gaps, key=Gap.key):
            print(f"- gate: {gap.gate}\n  test: {gap.test}")
        return 0

    baseline_keys, baseline_problems = _load_baseline()
    current_keys = {gap.key() for gap in gaps}
    new_keys = sorted(current_keys - baseline_keys)
    stale_keys = sorted(baseline_keys - current_keys)

    print(
        f"[gate-local-contract] gates_on_chain={len(gates)} "
        f"companion_gaps={len(current_keys)} baseline={len(baseline_keys)}"
    )

    failed = False
    for problem in baseline_problems:
        print(f"[gate-local-contract] FAIL: {problem}", file=sys.stderr)
        failed = True
    if new_keys:
        failed = True
        print(
            "[gate-local-contract] FAIL: 门禁挂在 gate 链上，但其配套 "
            "local_contract 测试没有任何 gate 链执行——门禁回退将无人可见。"
            "把测试补进 Makefile 的 test-gate-companion-local-contract："
            "（禁止重新引入缺口容忍基线）",
            file=sys.stderr,
        )
        for key in new_keys:
            print(f"  {key}", file=sys.stderr)
    if stale_keys:
        failed = True
        print(
            "[gate-local-contract] FAIL: baseline 条目已不再成立，必须删除"
            "（只减不增）：",
            file=sys.stderr,
        )
        for key in stale_keys:
            print(f"  {key}", file=sys.stderr)

    if failed:
        return 1
    print("[gate-local-contract] OK: 无新增未执行的门禁配套 local_contract 测试")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
