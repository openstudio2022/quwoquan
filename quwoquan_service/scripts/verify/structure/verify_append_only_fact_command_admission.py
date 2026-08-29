#!/usr/bin/env python3
"""阻断未经判据评估的 append_only_fact 公开 command。

判据（两条必须同时成立，并在对象契约内显式正向声明）：

1. 对象声明为不可变：``lifecycle.immutable: true``。
2. 无实例级可变不变式：``lifecycle.append_command_admission.instance_invariant: none``。

声明写在对象自己的 ``object.yaml`` 里，不是集中 allowlist；每条 command 必须逐条登记
并给出评估理由。任何新增 command 未登记、登记为存在实例级不变式，或对象不是不可变，
一律 BLOCK —— 该 command 属于聚合根写入口，应改挂对应 aggregate_root。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root  # noqa: E402

REPO_ROOT = repository_root()
SERVICE_ROOT = REPO_ROOT / "quwoquan_service"

APPEND_ONLY_FACT = "append_only_fact"
ADMISSION_KEY = "append_command_admission"
REQUIRED_STATUS = "evaluated"
REQUIRED_INSTANCE_INVARIANT = "none"
MIN_RATIONALE_LENGTH = 16


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _object_contract_files(service_root: Path) -> tuple[Path, ...]:
    return tuple(sorted(service_root.glob("services/*/contracts/*/*/object.yaml")))


def _load_yaml(path: Path) -> dict:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:  # pragma: no cover - 解析失败即阻断
        raise RuntimeError(f"{_relative(path)}: YAML 解析失败：{error}") from error
    return loaded if isinstance(loaded, dict) else {}


def _public_commands(operations_path: Path) -> tuple[str, ...]:
    if not operations_path.is_file():
        return ()
    document = _load_yaml(operations_path)
    commands: list[str] = []
    for route in document.get("api_routes") or []:
        if not isinstance(route, dict):
            continue
        application = route.get("application")
        if not isinstance(application, dict):
            continue
        if application.get("kind") != "command":
            continue
        operation = route.get("operation")
        if isinstance(operation, str) and operation:
            commands.append(operation)
    return tuple(sorted(set(commands)))


def _object_id(object_path: Path) -> str:
    # services/<service>/contracts/<context>/<object>/object.yaml
    parts = object_path.parts
    return f"{parts[-3]}.{parts[-2]}"


def _check_admission(
    object_path: Path,
    lifecycle: dict,
    commands: tuple[str, ...],
) -> list[str]:
    label = f"{_relative(object_path)} [{_object_id(object_path)}]"
    issues: list[str] = []

    if lifecycle.get("immutable") is not True:
        issues.append(
            f"{label}: append_only_fact 暴露公开 command "
            f"{list(commands)}，但未声明 lifecycle.immutable: true（判据 1 不成立）"
        )

    admission = lifecycle.get(ADMISSION_KEY)
    if not isinstance(admission, dict):
        issues.append(
            f"{label}: append_only_fact 暴露公开 command {list(commands)}，"
            f"但缺少 lifecycle.{ADMISSION_KEY} 正向声明；"
            "请评估是否存在实例级可变不变式，若存在则改挂 aggregate_root"
        )
        return issues

    if admission.get("status") != REQUIRED_STATUS:
        issues.append(
            f"{label}: lifecycle.{ADMISSION_KEY}.status 必须为 "
            f"'{REQUIRED_STATUS}'，实际为 {admission.get('status')!r}"
        )

    instance_invariant = admission.get("instance_invariant")
    if instance_invariant != REQUIRED_INSTANCE_INVARIANT:
        issues.append(
            f"{label}: lifecycle.{ADMISSION_KEY}.instance_invariant 为 "
            f"{instance_invariant!r}（判据 2 不成立）；存在实例级可变不变式的写入口"
            "必须归属 aggregate_root，不允许留在 append_only_fact"
        )

    rationale = admission.get("rationale")
    if not isinstance(rationale, str) or len(rationale.strip()) < MIN_RATIONALE_LENGTH:
        issues.append(
            f"{label}: lifecycle.{ADMISSION_KEY}.rationale 必须给出不少于 "
            f"{MIN_RATIONALE_LENGTH} 字的判据理由"
        )

    if not admission.get("evaluated_at"):
        issues.append(
            f"{label}: lifecycle.{ADMISSION_KEY}.evaluated_at 缺失，无法追溯评估时间"
        )

    declared = admission.get("commands")
    if not isinstance(declared, list) or not declared:
        issues.append(
            f"{label}: lifecycle.{ADMISSION_KEY}.commands 必须逐条列出已评估的公开 command"
        )
        return issues

    declared_set = {item for item in declared if isinstance(item, str)}
    for missing in sorted(set(commands) - declared_set):
        issues.append(
            f"{label}: 公开 command '{missing}' 未在 lifecycle.{ADMISSION_KEY}.commands 登记"
        )
    for stale in sorted(declared_set - set(commands)):
        issues.append(
            f"{label}: lifecycle.{ADMISSION_KEY}.commands 登记了不存在的 command "
            f"'{stale}'，请清理陈旧声明"
        )
    return issues


def collect_issues() -> list[str]:
    services_root = SERVICE_ROOT / "services"
    if not services_root.is_dir():
        return [
            f"append_only_fact command 判据门禁扫描根不存在：{_relative(services_root)}"
        ]

    object_paths = _object_contract_files(SERVICE_ROOT)
    if not object_paths:
        return [
            "append_only_fact command 判据门禁扫描到 0 个对象契约，扫描器必须 fail-closed："
            f"{_relative(services_root)}"
        ]

    issues: list[str] = []
    for object_path in object_paths:
        document = _load_yaml(object_path)
        if document.get("kind") != APPEND_ONLY_FACT:
            continue
        commands = _public_commands(object_path.parent / "operations.yaml")
        lifecycle = document.get("lifecycle")
        lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
        if not commands:
            if isinstance(lifecycle.get(ADMISSION_KEY), dict):
                issues.append(
                    f"{_relative(object_path)} [{_object_id(object_path)}]: "
                    f"对象已无公开 command，请删除 lifecycle.{ADMISSION_KEY} 陈旧声明"
                )
            continue
        issues.extend(_check_admission(object_path, lifecycle, commands))
    return issues


def main() -> int:
    try:
        issues = collect_issues()
    except RuntimeError as error:
        print(f"GATE_BLOCK append_only_fact command 判据门禁：{error}")
        return 1
    if issues:
        print("GATE_BLOCK append_only_fact command 判据门禁失败：")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("append_only_fact command 判据门禁通过：所有公开 command 均已完成不变式归属评估")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
