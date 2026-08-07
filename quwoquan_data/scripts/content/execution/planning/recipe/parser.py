"""Argument registration for the single ``task execute`` facade."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from core.control_types import TargetSelector
from content.execution.model_contract import SEMANTIC_SELECTION_IDS


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
        "--semantic-selection-id",
        choices=SEMANTIC_SELECTION_IDS,
        help=(
            "受治理语义执行选择；省略表示新 execution 使用 default，resume 使用"
            "已冻结 manifest 值。cursor_auto 只允许新的 retryOf execution"
        ),
    )
    parser.add_argument(
        "--semantic-preflight-receipt",
        help=(
            "受治理 semantic preflight/soak create-once receipt；cursor_auto "
            "必须提供并冻结到 execution manifest"
        ),
    )
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
            "submit-only 时冻结外部输入，或 M100 promote-scale 时提供当前 execution 的 "
            "immutable campaign envelope"
        ),
    )
    parser.add_argument(
        "--campaign-root-execution-id",
        help="四载体所属 homepage executionId；只作为协调根",
    )
    parser.add_argument(
        "--article-execution-id",
        help="adopt-reviewed-closure 的 article lane executionId",
    )
    parser.add_argument(
        "--image-execution-id",
        help="adopt-reviewed-closure 的 image lane executionId",
    )
    parser.add_argument(
        "--video-execution-id",
        help="adopt-reviewed-closure 的 video lane executionId",
    )
    parser.add_argument(
        "--adoption-id",
        help="reviewed closure adoption 的 create-once identity",
    )
    parser.add_argument(
        "--source-release-id",
        help="只读 reviewed source releaseId；不得等于未来新 releaseId",
    )
    parser.add_argument(
        "--identity-incident",
        help="release identity-incident create-once receipt 路径",
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
            "campaign-freeze",
            "campaign-lane-run",
            "campaign-finalize",
            "adopt-reviewed-closure",
        ],
        default="run",
    )
    parser.add_argument(
        "--submission-timeout-seconds",
        type=int,
        help="campaign-run/campaign-freeze 等待四份 submission 的有限超时；默认取 runtime policy",
    )
    parser.add_argument(
        "--campaign-lane-timeout-seconds",
        type=int,
        help="campaign-run/campaign-lane-run 每个 review/publish lane 的有限超时；默认取 runtime policy",
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
