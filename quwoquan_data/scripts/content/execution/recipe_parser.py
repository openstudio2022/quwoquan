"""Argument registration for the single ``task execute`` facade."""
from __future__ import annotations

import argparse
from typing import Callable

from core.control_types import TargetSelector


def register_recipe_parser(
    sub: argparse._SubParsersAction,
    *,
    handler: Callable[[argparse.Namespace], None],
) -> None:
    parser = sub.add_parser(
        "execute",
        help="按 family 与运行 request 执行内容工作包（选择→准入→执行→readiness）",
    )
    parser.add_argument("--execution-id", required=True, help="唯一 executionId")
    parser.add_argument("--retry-of", help="新 sequence 重试时指向原 executionId")
    parser.add_argument(
        "--video-scale-promotion",
        help=(
            "travel/video M1000 的已批准 M100 promotion receipt；"
            "首次运行时冻结到当前 execution"
        ),
    )
    parser.add_argument(
        "--image-scale-promotion",
        help=(
            "travel/image M1000 的已批准 M100 promotion receipt；"
            "首次运行时冻结到当前 execution"
        ),
    )
    parser.add_argument(
        "--campaign-envelope",
        help=(
            "执行 M100 的 --stage promote-scale 时，提供该 execution 的冻结 campaign envelope"
        ),
    )
    parser.add_argument(
        "--campaign-root-execution-id",
        help="四载体所属 homepage executionId；只作为协调根",
    )
    parser.add_argument("--family", help="control_plane family recipe reference")
    parser.add_argument(
        "--region-ref",
        help="reference/<vertical>/entities 下的区域引用",
    )
    parser.add_argument(
        "--selector",
        choices=tuple(item.value for item in TargetSelector),
    )
    parser.add_argument("--quota", type=int, help="准出配额")
    parser.add_argument(
        "--count",
        type=int,
        help="候选池上限；省略时由 runtime policy oversampleFactor 推导",
    )
    parser.add_argument(
        "--target",
        dest="target_names",
        action="append",
        default=[],
        help="本次请求限定的候选实体；可重复",
    )
    parser.add_argument("--topic", help="文章、图片或视频的主题")
    parser.add_argument(
        "--source-provider",
        dest="source_providers",
        action="append",
        default=[],
        help="限制到已声明 provider，可重复",
    )
    parser.add_argument(
        "--stage",
        choices=[
            "run",
            "plan-only",
            "readiness-only",
            "submit-only",
            "review-only",
            "promote-scale",
            "campaign-run",
        ],
        default="run",
    )
    parser.add_argument(
        "--submission-timeout-seconds",
        type=int,
        help="campaign-run 等待四份 submission 的有限超时；默认取 runtime policy",
    )
    parser.add_argument(
        "--campaign-lane-timeout-seconds",
        type=int,
        help="campaign-run 每个 review/publish lane 的有限超时；默认取 runtime policy",
    )
    from content.execution.controller.dag import STAGE_NAMES

    parser.add_argument(
        "--recover-stage",
        choices=STAGE_NAMES,
        help="修复后的受审计恢复起点；必须同时提供 --recovery-reason",
    )
    parser.add_argument(
        "--recovery-reason",
        help="受审计恢复原因；必须同时提供 --recover-stage",
    )
    parser.set_defaults(handler=handler)


__all__ = ["register_recipe_parser"]
