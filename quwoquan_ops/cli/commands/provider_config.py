"""stackctl `provider-config` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；Binding/topology/
Secret Bundle 编译与校验逻辑保持在 stackctl 命名空间共享 helper
（`_provider_config` / `_active_provider_runtime` /
`compile_provider_runtime_composition`）。stackctl 命名空间符号一律经
函数内延迟导入 `_stackctl` 属性访问，保持 monkeypatch 语义并避免
顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    provider_config_parser = subparsers.add_parser(
        "provider-config",
        help="校验、物化或比对 Binding/topology/Secret Bundle 编译结果",
    )
    provider_config_parser.add_argument(
        "provider_config_action",
        choices=("validate", "render", "diff"),
    )
    provider_config_parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma", "prod"),
        required=True,
    )
    provider_config_parser.add_argument(
        "--target",
        choices=(
            "alpha-local",
            "beta-local",
            "gamma-local",
            "prod-hosted",
        ),
        required=True,
    )
    provider_config_parser.add_argument(
        "--runtime-mode",
        choices=("active_candidate", "test_live"),
        default="active_candidate",
        help=(
            "active_candidate 校验 immutable package；test_live 编译并校验当前工作树，"
            "不读取或伪造 candidate identity"
        ),
    )


def command_provider_config(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        environment = str(args.env)
        target = str(args.target)
        runtime_mode = str(
            getattr(args, "runtime_mode", "active_candidate") or "active_candidate"
        )
        if runtime_mode == "test_live":
            if environment == "prod" or target == "prod-hosted":
                raise ValueError("test_live Provider config is limited to local nonprod")
            runtime_composition = _stackctl.compile_provider_runtime_composition(
                environment=environment,
                target=target,
            )
        elif runtime_mode == "active_candidate":
            active_runtime = _stackctl._active_provider_runtime(environment, target)
            runtime_composition = active_runtime["composition"]
        else:
            raise ValueError("Provider config runtime mode is invalid")
        return _stackctl._provider_config().compile_provider_config(
            action=str(args.provider_config_action),
            environment=environment,
            target=target,
            runtime_composition=runtime_composition,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl provider-config is GATE_BLOCK",
            "details": [str(exc)],
        }
