"""Data ship 操作的注入边界。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShipOperationDependencies:
    """由公开 handler 注入的路径与边界操作，保留既有测试替换点。"""

    output_root: Path
    load_release: Callable[[str], tuple[Path, dict[str, Any]]]
    release_requires_full_sync: Callable[[Path], bool]
    release_has_posts: Callable[[Mapping[str, Any]], bool]
    create_run: Callable[..., Path]
    run_root: Callable[[str, str, str], Path]
    sync_media: Callable[..., None]
    write_applied_ref: Callable[..., None]
    assert_target_action_allowed: Callable[..., None]
    resolve_environment_release_target: Callable[..., Any]
    require_environment_readiness: Callable[..., None]
    run_tag_importer: Callable[..., Path]
    run_creator_importer: Callable[..., Path]
    run_content_importer: Callable[..., Any]
    run_homepage_importer: Callable[..., Any]
    write_release_evidence: Callable[..., Any]
    write_verification_result: Callable[..., Any]
    write_tag_consumer_verification: Callable[..., Path]
    write_homepage_verification_case_manifest: Callable[..., Path]
    write_baseline_api_verification: Callable[..., Path]
    write_post_api_verification: Callable[..., Path]
    write_homepage_api_verification: Callable[..., Path]
    write_environment_release_readiness: Callable[..., Path]
    now_compact: Callable[[], str]
