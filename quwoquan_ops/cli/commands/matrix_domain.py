"""stackctl `matrix` 子命令域: 串行 Alpha/Beta/Gamma 本地门禁矩阵编排。

从 stackctl.py 逐字迁出 `command_matrix`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse

from typing import Any


def command_matrix(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    profile = str(getattr(args, "profile", _stackctl.PROFILE_LOCAL_ENV_GATE) or _stackctl.PROFILE_LOCAL_ENV_GATE)
    if profile != _stackctl.PROFILE_LOCAL_ENV_GATE:
        return {
            "exitCode": 2,
            "summary": f"unsupported matrix profile: {profile}",
            "details": [f"supported: {_stackctl.PROFILE_LOCAL_ENV_GATE}"],
        }
    targets = tuple(
        item.strip()
        for item in str(getattr(args, "targets", "") or "").split(",")
        if item.strip()
    )
    request_by_target: dict[str, str] = {}
    evidence_by_target: dict[str, str] = {}
    handoff_by_target: dict[str, str] = {}
    evidence_issues: list[str] = []
    for raw in list(getattr(args, "test_data_request", []) or []):
        target, separator, path = str(raw).partition("=")
        target = target.strip()
        path = path.strip()
        if not separator or target not in _stackctl.CANONICAL_LOCAL_GATE_TARGETS or not path:
            evidence_issues.append(
                "--test-data-request must use alpha-local|beta-local|gamma-local=PATH"
            )
            continue
        if target in request_by_target:
            evidence_issues.append(f"duplicate test-data request target: {target}")
            continue
        request_by_target[target] = path
    for raw in list(getattr(args, "test_data_evidence", []) or []):
        target, separator, path = str(raw).partition("=")
        target = target.strip()
        path = path.strip()
        if not separator or target not in _stackctl.CANONICAL_LOCAL_GATE_TARGETS or not path:
            evidence_issues.append(
                "--test-data-evidence must use alpha-local|beta-local|gamma-local=PATH"
            )
            continue
        if target in evidence_by_target:
            evidence_issues.append(f"duplicate test-data evidence target: {target}")
            continue
        evidence_by_target[target] = path
    for raw in list(getattr(args, "test_data_handoff", []) or []):
        target, separator, path = str(raw).partition("=")
        target = target.strip()
        path = path.strip()
        if not separator or target not in _stackctl.CANONICAL_LOCAL_GATE_TARGETS or not path:
            evidence_issues.append(
                "--test-data-handoff must use alpha-local|beta-local|gamma-local=PATH"
            )
            continue
        if target in handoff_by_target:
            evidence_issues.append(f"duplicate test-data handoff target: {target}")
            continue
        handoff_by_target[target] = path
    if evidence_issues:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix test-data input is GATE_BLOCK",
            "details": evidence_issues,
        }
    return _stackctl.run_local_env_gate_matrix(
        package_fn=_stackctl.command_package,
        up_fn=_stackctl.command_up,
        health_fn=_stackctl.command_health,
        verify_fn=_stackctl.command_verify,
        down_fn=_stackctl.command_down,
        telemetry_fn=_stackctl.command_product_telemetry_log_sink,
        provider_fn=_stackctl.command_provider_conformance,
        app_uat_fn=_stackctl.command_app_content_uat,
        filter_catalog_fn=_stackctl.command_filter_catalog,
        targets=targets,
        include_l0=not bool(getattr(args, "skip_l0", False)),
        release_attestation=str(
            getattr(args, "release_attestation", "") or ""
        ),
        rollback_release_attestation=str(
            getattr(args, "rollback_release_attestation", "") or ""
        ),
        test_data_request=request_by_target,
        test_data_evidence=evidence_by_target,
        test_data_handoff=handoff_by_target,
        ios_simulator_device=str(
            getattr(args, "ios_simulator_device", "") or ""
        ),
        android_emulator_device=str(
            getattr(args, "android_emulator_device", "") or ""
        ),
        android_physical_device=str(
            getattr(args, "android_physical_device", "") or ""
        ),
        device_profile=str(
            getattr(args, "device_profile", _stackctl.LOCAL_GATE_DEVICE_PROFILE_FULL)
            or _stackctl.LOCAL_GATE_DEVICE_PROFILE_FULL
        ),
    )


def register_parser(subparsers: "argparse._SubParsersAction") -> None:
    """向 stackctl build_parser 注册本域子命令（从 build_parser 逐字迁出）。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    matrix_parser = subparsers.add_parser(
        "matrix",
        help="串行 Alpha/Beta/Gamma 本地门禁矩阵（local-env-gate）",
    )
    matrix_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    matrix_parser.add_argument(
        "--profile",
        choices=(_stackctl.PROFILE_LOCAL_ENV_GATE,),
        default=_stackctl.PROFILE_LOCAL_ENV_GATE,
    )
    matrix_parser.add_argument(
        "--targets",
        required=True,
        help="必须为 alpha-local,beta-local,gamma-local",
    )
    matrix_parser.add_argument(
        "--skip-l0",
        action="store_true",
        help="跳过 make commit-gate（仅编排环境段）",
    )
    matrix_parser.add_argument("--release-attestation", required=True)
    matrix_parser.add_argument("--rollback-release-attestation", required=True)
    matrix_parser.add_argument(
        "--test-data-request",
        action="append",
        metavar="TARGET=PATH",
        required=True,
        help="Alpha/Beta/Gamma 各自选中用例的强类型 request graph",
    )
    matrix_parser.add_argument(
        "--test-data-evidence",
        action="append",
        metavar="TARGET=PATH",
        default=[],
        help="仅为实际请求的外部 Provider 依赖提供候选绑定 evidence",
    )
    matrix_parser.add_argument(
        "--test-data-handoff",
        action="append",
        metavar="TARGET=PATH",
        required=True,
        help="Alpha/Beta/Gamma 各自 environment-bound exact handoff",
    )
    matrix_parser.add_argument("--ios-simulator-device", required=True)
    matrix_parser.add_argument("--android-emulator-device", required=True)
    matrix_parser.add_argument(
        "--device-profile",
        choices=_stackctl.LOCAL_GATE_DEVICE_PROFILES,
        default=_stackctl.LOCAL_GATE_DEVICE_PROFILE_FULL,
        help=(
            "full 要求 Android 真机并可形成正式 Green claim；"
            "emulator_only 只做 Simulator/Emulator non-promotable 功能验收"
        ),
    )
    matrix_parser.add_argument("--android-physical-device", default="")

