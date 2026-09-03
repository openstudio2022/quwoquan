"""Public mechanical verification commands."""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from core import paths

_STATIC_GATES = {
    "cli-first": "verify_cli_first",
    "public-cli-live-import-zero": "verify_public_cli_live_import_zero",
    "data-layout": "verify_data_layout",
    "script-architecture": "verify_script_architecture",
    "python-symbols": "verify_python_symbols",
    "no-flat-roots": "verify_no_flat_roots",
    "tag-tree": "verify_tag_tree",
    "source-digest": "verify_source_digest",
    "content-execution-layout": "verify_content_execution_layout",
    "runtime-input-ownership": "verify_runtime_input_ownership",
    "output-root-isolation": "verify_output_root_isolation",
    "object-size-budget": "verify_object_size_budget",
    "publish-purity": "verify_publish_purity",
    "publish-closure": "verify_publish_closure",
}
_EXECUTION_GATES = {
    "task-init-contract": "verify_task_init_contract",
    "source-plan": "verify_source_plan",
}
_ARGV_STATIC_GATES = {
    "public-cli-live-import-zero",
    "tag-tree",
    "source-digest",
    "content-execution-layout",
}


def _run(name: str, argv: list[str] | None = None) -> int:
    module = import_module(f"verify.{_STATIC_GATES[name]}")
    main: Callable[..., int | None] = getattr(module, "main")
    try:
        result = main(argv) if argv is not None else main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return int(result or 0)


def _admit_carried_media_holdings() -> int:
    from content.release.canonical.rehydrate_media_holdings import main as rehydrate_main

    return int(rehydrate_main() or 0)


def handle_all() -> list[str]:
    # Closure gates resolve media through the repository-external content library.
    # A clean checkout starts with an empty library, so first admit the exact,
    # hash-verified bodies carried beside canonical publish in version control.
    if _admit_carried_media_holdings() != 0:
        raise SystemExit(1)

    failed = [
        name
        for name in _STATIC_GATES
        if _run(name, [] if name in _ARGV_STATIC_GATES else None)
    ]
    if failed:
        raise SystemExit(f"[verify all] FAIL: {', '.join(failed)}")
    print("[verify all] OK")
    return list(_STATIC_GATES)


def handle_verify(args: argparse.Namespace) -> None:
    command = str(args.verify_command)
    if command == "all":
        handle_all()
        return
    if command in _EXECUTION_GATES:
        module = import_module(f"verify.{_EXECUTION_GATES[command]}")
        main: Callable[..., int | None] = getattr(module, "main")
        raise SystemExit(int(main(["--execution-id", str(args.execution_id)]) or 0))
    if command == "stage-artifacts":
        from verify.stage_artifacts import verify_stage_artifacts
        report = verify_stage_artifacts(
            execution_id=str(args.execution_id),
            publish_root=Path(args.publish_root) if args.publish_root else paths.PUBLISH_ROOT,
            release_root=Path(args.release_root) if args.release_root else paths.RELEASE_ROOT,
            commercial=not bool(args.trial),
            through=args.through,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["passed"]:
            raise SystemExit(1)
        return
    if command == "release-integrity":
        from content.release.canonical.integrity import scan_release_integrity
        report = scan_release_integrity(args.release)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("passed"):
            raise SystemExit(1)
        return
    argv: list[str] | None = [] if command in _ARGV_STATIC_GATES else None
    if command == "content-execution-layout" and getattr(args, "execution_id", None):
        argv = ["--execution-id", str(args.execution_id)]
    raise SystemExit(_run(command, argv))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("verify", help="机械 schema、引用闭包与发布完整性校验")
    commands = parser.add_subparsers(dest="verify_command", required=True)
    commands.add_parser("all", help="运行仓内全部目标态静态门")
    for name in _STATIC_GATES:
        command = commands.add_parser(name)
        if name == "content-execution-layout":
            command.add_argument("--execution-id")
    for name in _EXECUTION_GATES:
        command = commands.add_parser(name)
        command.add_argument("--execution-id", required=True)
    stage = commands.add_parser(
        "stage-artifacts",
        help="按 target_set 校验阶段闭包；省略 --through 时校验 publish 后 final closure",
    )
    stage.add_argument("--execution-id", required=True)
    stage.add_argument("--publish-root")
    stage.add_argument("--release-root")
    stage.add_argument("--trial", action="store_true")
    stage.add_argument(
        "--through",
        choices=paths.OBJECT_STAGES,
        help="截止到指定对象阶段；省略表示 publish 后 final closure",
    )
    integrity = commands.add_parser("release-integrity")
    integrity.add_argument("--release", required=True)
    parser.set_defaults(handler=handle_verify)
