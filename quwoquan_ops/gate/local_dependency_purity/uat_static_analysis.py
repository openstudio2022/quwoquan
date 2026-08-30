"""Verify canonical UAT static-analysis coverage across Flutter package roots."""

from __future__ import annotations

from pathlib import Path

import yaml

from quwoquan_ops.gate.local_dependency_purity.shell_commands import (
    ShellCommandParseError,
    reachable_dispatched_shell_commands,
    shell_case_dispatches_function,
    unique_top_level_shell_function_identity,
)

ROOT = Path(__file__).resolve().parents[3]


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _append_failure(failures: list[str], path: Path, reason: str) -> None:
    failures.append(
        f"APP.PACKAGE.uat_static_analysis_uncovered: {_display_path(path)} {reason}"
    )


def verify_uat_static_analysis_coverage(
    failures: list[str],
    *,
    app_dir: Path = ROOT / "quwoquan_app",
    gate_script: Path = ROOT / "quwoquan_ops/gate/gate_repo.sh",
) -> None:
    """Prove the main-App exclusion never silently drops a canonical UAT.

    生产 pubspec 不含 patrol，因此 canonical UAT 与 Patrol support 只能在
    test host 的 package context 下静态分析。主 App 的排除因此必须与 test host
    的分析集合严格互补：每一个 canonical UAT 都要经 test/canonical symlink
    落进 test host 的分析根，否则排除就是假绿。
    """

    def uncovered(path: Path, reason: str) -> None:
        _append_failure(failures, path, reason)

    canonical_uat_root = app_dir / "test/user_acceptance"
    patrol_support_root = app_dir / "test/support/runtime/patrol"
    host_dir = app_dir / "test_host/patrol"
    canonical_link = host_dir / "test/canonical"

    production_options = app_dir / "analysis_options.yaml"
    if not production_options.is_file():
        uncovered(production_options, "is missing")
        return
    production_excludes = (
        yaml.safe_load(production_options.read_text(encoding="utf-8")) or {}
    ).get("analyzer", {}).get("exclude") or []
    for required_exclude in (
        "test/user_acceptance/**",
        "test/support/runtime/patrol/**",
    ):
        if required_exclude not in production_excludes:
            uncovered(
                production_options,
                f"must exclude {required_exclude} from the main-App analysis",
            )
    excluded_test_prefixes = tuple(
        sorted(
            {
                _excluded_test_prefix(str(pattern))
                for pattern in production_excludes
                if str(pattern).startswith("test/")
            }
        )
    )

    # canonical UAT 只允许被 symlink 引用；复制会立刻产生第二个真相源。
    if not canonical_link.is_symlink():
        uncovered(canonical_link, "must be a symlink to the main App test tree")
        return
    if canonical_link.resolve() != (app_dir / "test").resolve():
        uncovered(canonical_link, "must resolve to the main App test tree")
        return

    host_options = host_dir / "analysis_options.yaml"
    if host_options.is_file():
        host_excludes = (
            yaml.safe_load(host_options.read_text(encoding="utf-8")) or {}
        ).get("analyzer", {}).get("exclude") or []
        for host_exclude in host_excludes:
            if str(host_exclude).startswith("test/canonical"):
                uncovered(host_options, f"must not exclude {host_exclude}")

    if not gate_script.is_file():
        uncovered(gate_script, "is missing")
        return
    # 覆盖面只能从 test host 真实的 analyze 参数表派生：全文 substring 匹配会让
    # 一行注释就满足判据。
    try:
        analyzed_prefixes = _test_host_analysis_prefixes(
            gate_script.read_text(encoding="utf-8")
        )
    except ShellCommandParseError:
        uncovered(gate_script, "shell syntax cannot be parsed")
        return
    for analysis_root in ("user_acceptance", "support/runtime/patrol"):
        if not _prefix_is_analyzed(analysis_root, analyzed_prefixes):
            uncovered(
                gate_script,
                f"must analyze test/canonical/{analysis_root} in the test host",
            )

    # 主 App 每一条 test/** 排除都必须有等价证人。硬编码白名单挡不住第三条新增
    # 排除，集合互补才挡得住。
    for prefix in excluded_test_prefixes:
        if not _prefix_is_analyzed(prefix, analyzed_prefixes):
            uncovered(
                production_options,
                f"excludes test/{prefix}/** from the main-App analysis with no "
                "matching test host analysis root",
            )

    covered_sources = tuple(sorted(canonical_uat_root.rglob("*_test.dart"))) + tuple(
        sorted(patrol_support_root.rglob("*.dart"))
    )
    if not covered_sources:
        uncovered(canonical_uat_root, "exposes no canonical UAT to analyze")
    for source in covered_sources:
        relative = source.relative_to(app_dir / "test").as_posix()
        if not _prefix_is_analyzed(relative, analyzed_prefixes):
            uncovered(source, "is not reachable from the test host analysis root")


def _excluded_test_prefix(pattern: str) -> str:
    """Return the ``test/``-relative directory an analyzer exclude covers."""

    prefix = pattern[len("test/") :]
    for suffix in ("/**", "/*", "/**/*"):
        if prefix.endswith(suffix):
            prefix = prefix[: -len(suffix)]
            break
    return prefix.rstrip("/")


def _test_host_analysis_prefixes(gate_text: str) -> tuple[str, ...]:
    """Return the ``test/``-relative roots the test host actually analyzes."""

    commands = reachable_dispatched_shell_commands(gate_text)
    run_app_identity = unique_top_level_shell_function_identity(
        gate_text,
        function_name="run_app",
    )
    if run_app_identity is None:
        return ()
    run_app_is_dispatched = shell_case_dispatches_function(
        gate_text,
        variable="scope",
        function_name="run_app",
        required_labels=("all", "app"),
    )
    if not run_app_is_dispatched:
        return ()
    complete_commands: list[tuple[str, ...]] = []
    for index, command in enumerate(commands):
        arguments = command.argv
        if (
            arguments[:2] != ("flutter", "analyze")
            or command.function_scope != ("run_app",)
            or command.function_definition_scope != (run_app_identity,)
            or index == 0
        ):
            continue
        previous = commands[index - 1]
        if not (
            command.separator_before == "&&"
            and command.subshell_depth == previous.subshell_depth
            and previous.function_scope == command.function_scope
            and previous.argv == ("cd", "quwoquan_app/test_host/patrol")
        ):
            continue
        prefixes = tuple(
            argument[len("test/canonical/") :].rstrip("/")
            if argument.startswith("test/canonical/")
            else ""
            for argument in arguments[2:]
            if argument == "test/canonical" or argument.startswith("test/canonical/")
        )
        if all(
            _prefix_is_analyzed(required, prefixes)
            for required in ("user_acceptance", "support/runtime/patrol")
        ):
            complete_commands.append(prefixes)
    return tuple(
        sorted({prefix for command in complete_commands for prefix in command})
    )


def _prefix_is_analyzed(relative: str, analyzed_prefixes: tuple[str, ...]) -> bool:
    return any(
        prefix == "" or relative == prefix or relative.startswith(f"{prefix}/")
        for prefix in analyzed_prefixes
    )
