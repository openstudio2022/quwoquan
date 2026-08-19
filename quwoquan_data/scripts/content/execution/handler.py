"""Public content-execution facade.

The data CLI deliberately exposes only durable end-to-end execution commands.
Stage runners and static task CRUD are implementation
details and must not become a second control plane.
"""
from __future__ import annotations

import argparse

from content.execution.campaign.failed_execution_reconciliation import (
    register_reconcile_failed_campaign_parser,
)
from content.execution.campaign.prepare import register_prepare_campaign_parser
from content.execution.campaign.submission_reconciliation import (
    register_reconcile_submissions_parser,
)
from content.execution.controller.execute.acquire_images import (
    register_acquire_images_parser,
)
from content.execution.controller.execute.acquire_videos import (
    register_acquire_videos_parser,
)
from content.execution.controller.execute.discard import register_task_discard_parser
from content.execution.controller.execute.drain_pool_delivery import (
    register_drain_pool_delivery_parser,
)
from content.execution.controller.execute.prepare_image_supported_api_input import (
    register_prepare_image_supported_api_input_parser,
)
from content.execution.controller.execute.prepare_video_manual_input import (
    register_prepare_video_manual_input_parser,
)
from content.execution.controller.execute.probe_images import (
    register_probe_images_parser,
)
from content.execution.controller.execute.reconcile import (
    register_reconcile_stale_parser,
)
from content.execution.controller.execute.review_asset import (
    register_review_asset_parser,
)
from content.execution.controller.execute.review_image_supported_api_input import (
    register_review_image_supported_api_input_parser,
)
from content.execution.controller.execute.author_image_supported_api_input import (
    register_author_image_supported_api_input_parser,
)
from content.execution.controller.execute.video_acquisition_agent_input import (
    register_video_acquisition_agent_input_parsers,
)
from content.execution.execution_supersession import (
    register_supersede_execution_parser,
)
from content.execution.planning.discover_image_supported_api_metadata import (
    register_discover_image_supported_api_metadata_parser,
)
from content.execution.planning.plan_images import register_plan_images_parser
from content.execution.planning.recipe.model import register_recipe_parser
from content.execution.preflight.handler import register_task_preflight_parser
from content.execution.runtime_evidence.cli import (
    register_runtime_evidence_parser,
)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "task",
        help="内容执行门面：唯一 execution 工作包编排",
    )
    commands = parser.add_subparsers(dest="task_command")
    register_task_preflight_parser(commands)
    register_prepare_campaign_parser(commands)
    register_recipe_parser(commands)
    register_drain_pool_delivery_parser(commands)
    register_task_discard_parser(commands)
    register_supersede_execution_parser(commands)
    register_plan_images_parser(commands)
    register_discover_image_supported_api_metadata_parser(commands)
    register_probe_images_parser(commands)
    register_acquire_images_parser(commands)
    register_prepare_image_supported_api_input_parser(commands)
    register_prepare_video_manual_input_parser(commands)
    register_acquire_videos_parser(commands)
    register_review_asset_parser(commands)
    register_review_image_supported_api_input_parser(commands)
    register_author_image_supported_api_input_parser(commands)
    register_video_acquisition_agent_input_parsers(commands)
    register_reconcile_stale_parser(commands)
    register_reconcile_failed_campaign_parser(commands)
    register_reconcile_submissions_parser(commands)
    register_runtime_evidence_parser(commands)
