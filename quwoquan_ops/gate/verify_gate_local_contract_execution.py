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

## 判据 B：本次改动的门禁必须有 companion

上面那条判据只在「恰好有同名测试」时才生效——一个门禁完全没有配套测试时，
`_companion_tests` 返回空列表，循环体一次都不执行，门禁反而静默放行。越是新写的、
判据最没被验证过的门禁，越容易掉进这个缺口。`verify_nil_semantics.py` 的 wire 判定
早先用目录名近似，全仓扫描一直是绿的，缺陷却在现网——正是这个形态。

所以补一条独立判据：**本次改动（相对 base）的门禁脚本必须至少有一个 companion，且
它必须被 gate 链执行。** 只约束改动面，因此可以用比判据 A 更宽的脚本范围
（含 `quwoquan_app` / `quwoquan_data` 的门禁树）而不误伤存量——存量的 96 处缺口需要
逐个补测试，那是独立工作项，不能挂在任何一次无关改动上。

CI 调用方必须传入已经校验过的 exact `base_sha` / `head_sha`，判据 B 只看这一条 PR 或
promotion 边的**已提交**增量；本地未显式传参时才保守回退到 `origin/main` / `main`。
显式范围缺键、不是完整 commit SHA、head 不是当前 checkout 或 base 不是 head 祖先时一律
fail closed，不能静默回退到本地分支。这样 `codex/* -> dev1.0` 不会重复审计历史增量，
而 `dev1.0 -> main` 仍会完整审计 promotion 范围。

改动面不含未提交工作树。这里不是漏了一种情况：本仓库脏工作树是常态，一次会话里往往
同时躺着好几个域的并行改动，把工作树计入会让判据 B 长期为别人的改动报红——而持续
假红最终只会被 `--no-verify` 绕过，比没有这条判据更糟。

仓库不是 git 工作副本时（打包产物、tarball）判据 B 静默跳过——那种环境里 diff 无从
计算，强行报错只会制造另一种假红灯。
"""

from __future__ import annotations

import argparse
import re
import subprocess
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

#: 判据 B 的脚本范围。比 `GATE_SCRIPT_ROOTS` 宽：判据 B 只看本次改动，把 App / Data
#: 的门禁树纳进来不会翻出存量缺口。
CHANGED_GATE_SCRIPT_ROOTS = GATE_SCRIPT_ROOTS + (
    "quwoquan_app/scripts/",
    "quwoquan_data/scripts/verify/",
)

#: 判据 B 的 base。`origin/main` 缺失时退回单看工作树。
BASE_CANDIDATES = ("origin/main", "main")
EXACT_SHA_RE = re.compile(r"[0-9a-f]{40}")

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


def _git(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return completed.stdout if completed.returncode == 0 else None


class ChangeRangeError(ValueError):
    """显式 CI 改动范围非法，调用方必须 fail closed。"""


def _validate_explicit_change_range(base_sha: str, head_sha: str) -> None:
    for label, sha in (("base", base_sha), ("head", head_sha)):
        if EXACT_SHA_RE.fullmatch(sha) is None:
            raise ChangeRangeError(f"{label}_sha 必须是 40 位小写 commit SHA")
        if _git("cat-file", "-e", f"{sha}^{{commit}}") is None:
            raise ChangeRangeError(f"{label}_sha 不是当前 checkout 可达的 commit: {sha}")

    checked_out = _git("rev-parse", "HEAD")
    if checked_out is None or checked_out.strip() != head_sha:
        raise ChangeRangeError("head_sha 必须精确等于当前 checkout HEAD")
    if _git("merge-base", "--is-ancestor", base_sha, head_sha) is None:
        raise ChangeRangeError("base_sha 必须是 head_sha 的祖先")


def changed_gate_scripts(
    base_sha: str | None = None,
    head_sha: str | None = None,
) -> list[str] | None:
    """本次已提交增量里的门禁脚本。不是 git 工作副本时返回 `None`（判据 B 跳过）。"""
    if _git("rev-parse", "--git-dir") is None:
        if base_sha is not None or head_sha is not None:
            raise ChangeRangeError("显式改动范围只能在 git checkout 中验证")
        return None
    paths: set[str] = set()
    if base_sha is not None or head_sha is not None:
        if base_sha is None or head_sha is None:
            raise ChangeRangeError("base_sha 与 head_sha 必须成对提供")
        _validate_explicit_change_range(base_sha, head_sha)
        committed = _git("diff", "--name-only", f"{base_sha}...{head_sha}")
        if committed is None:
            raise ChangeRangeError("git diff 无法读取显式 base/head 改动范围")
        if committed:
            paths.update(committed.split())
    else:
        for candidate in BASE_CANDIDATES:
            merge_base = _git("merge-base", "HEAD", candidate)
            if merge_base is None:
                continue
            committed = _git("diff", "--name-only", f"{merge_base.strip()}...HEAD")
            if committed:
                paths.update(committed.split())
            break
    return sorted(
        path
        for path in paths
        if path.endswith(".py")
        and any(path.startswith(root) for root in CHANGED_GATE_SCRIPT_ROOTS)
        and Path(path).name.startswith("verify_")
        and (ROOT / path).is_file()
    )


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
    parser.add_argument("--base-sha", help="CI 已校验的 exact base commit SHA")
    parser.add_argument("--head-sha", help="CI 已校验且已 checkout 的 exact head commit SHA")
    args = parser.parse_args(argv)

    if (args.base_sha is None) != (args.head_sha is None):
        print(
            "[gate-local-contract] GATE_BLOCK: --base-sha 与 --head-sha 必须成对提供",
            file=sys.stderr,
        )
        return 2

    try:
        changed = changed_gate_scripts(args.base_sha, args.head_sha)
    except ChangeRangeError as error:
        print(f"[gate-local-contract] GATE_BLOCK: {error}", file=sys.stderr)
        return 2

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

    if changed is None:
        print("[gate-local-contract] 非 git 工作副本，跳过改动面判据")
    else:
        unproven: list[str] = []
        for gate in changed:
            companions = _companion_tests(gate, tests)
            executed = [
                test
                for test in companions
                if _test_is_executed(test, scripts, pytest_paths, unittest_modules)
            ]
            if not executed:
                reason = (
                    "没有任何同名 companion 测试"
                    if not companions
                    else "companion 存在但没有任何 gate 链执行："
                    + "、".join(companions)
                )
                unproven.append(f"{gate}（{reason}）")
        print(f"[gate-local-contract] changed_gates={len(changed)}")
        if unproven:
            failed = True
            print(
                "[gate-local-contract] FAIL: 本次改动的门禁没有被执行的 companion "
                "测试——判据是否还成立无从证明。companion 命名须为 "
                "`test_<门禁名去掉 verify_ 前缀>__<facet>__local_contract_test.py`，"
                "并挂进 Makefile 的 test-gate-companion-local-contract：",
                file=sys.stderr,
            )
            for item in unproven:
                print(f"  {item}", file=sys.stderr)

    if failed:
        return 1
    print("[gate-local-contract] OK: 无新增未执行的门禁配套 local_contract 测试")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
