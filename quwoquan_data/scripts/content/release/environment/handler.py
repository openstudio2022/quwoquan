"""Release-first 环境执行：canonical 只读，所有运行证据 append-only。

环境证据根：`env/<env>/runs/data-release/<releaseId>/<runId>/`（"data-release" 生命周期类别）。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.environment.baseline_api_verification import (
    BaselineApiVerificationError,
    write_baseline_api_verification,
)
from content.release.environment.coverage_receipt import (
    write_environment_coverage_receipt,
)
from content.release.environment._ship_operations import (
    ShipOperationDependencies,
    apply_release,
    rollback_release,
    verify_release_consumers,
)
from content.release.environment.homepage_api_verification import (
    HomepageApiVerificationError,
    write_homepage_api_verification,
)
from content.release.environment.homepage_verification_cases import (
    HomepageVerificationCaseError,
    write_homepage_verification_case_manifest,
)
from content.release.environment.importers import (
    run_content_importer as _run_content_importer,
)
from content.release.environment.importers import (
    run_creator_importer as _run_creator_importer,
)
from content.release.environment.importers import (
    run_homepage_importer as _run_homepage_importer,
)
from content.release.environment.importers import (
    run_tag_importer as _run_tag_importer,
)
from content.release.environment.post_api_verification import (
    PostApiVerificationError,
    write_post_api_verification,
)
from content.release.environment.readiness import require_environment_readiness
from content.release.environment.research_isolation_verification import (
    write_research_isolation_verification,
)
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
    write_environment_release_readiness,
)
from content.release.environment.release_only_report import write_release_only_ship_report
from content.release.environment.ship_dispatch import dispatch_ship
from content.release.environment.release_runtime import (
    assert_target_action_allowed as _assert_environment_action_allowed,
)
from content.release.environment.release_runtime import (
    assert_environment_release_policy,
)
from content.release.environment.release_runtime import (
    load_release,
    release_has_posts,
    release_requires_full_sync,
    sync_media,
)
from content.release.environment.run_evidence import (
    create_run as _create_environment_run,
)
from content.release.environment.run_evidence import (
    write_applied_ref as _write_environment_applied_ref,
)
from content.release.environment.run_evidence import (
    write_release_evidence as _write_release_evidence,
)
from content.release.environment.run_evidence import (
    write_verification_result as _write_verification_result,
)
from content.release.environment.tag_consumer_verification import (
    write_tag_consumer_verification,
)
from content.release.environment.topology import (
    EnvironmentReleaseTarget,
    resolve_environment_release_target,
)
from content.release.model import (
    DEPLOYMENT_ENVIRONMENTS,
    ReleaseKind,
)
from core.control_types import ReleaseRunKind
from core.paths import (
    OUTPUT_ROOT,
    RELEASE_ROOT,
    env_data_release_run_root,
    release_ref,
)

VALID_ENVS = frozenset(DEPLOYMENT_ENVIRONMENTS)


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_tag_consumer_verification(
    *, environment: str, release_id: str, release_kind: ReleaseKind, run_id: str, release_contract: Mapping[str, Any], import_report_path: Path, output_path: Path
) -> Path:
    return write_tag_consumer_verification(
        output_root=OUTPUT_ROOT,
        environment=environment,
        release_id=release_id,
        release_kind=release_kind,
        run_id=run_id,
        release_contract=release_contract,
        import_report_path=import_report_path,
        output_path=output_path,
    )


def _run_root(env: str, release_id: str, run_id: str) -> Path:
    return env_data_release_run_root(env, release_id, run_id, output_root=OUTPUT_ROOT)


def _load_release(release_id: str) -> tuple[Path, dict[str, Any]]:
    return load_release(RELEASE_ROOT, release_id)


def _release_requires_full_sync(release: Path) -> bool:
    return release_requires_full_sync(release)


def _release_has_posts(contract: Mapping[str, Any]) -> bool:
    """Return whether this immutable release owns post consumers to verify."""
    return release_has_posts(contract)


def _create_run(env: str, release_id: str, run_id: str, *, kind: ReleaseRunKind) -> Path:
    return _create_environment_run(
        output_root=OUTPUT_ROOT,
        environment=env,
        release_id=release_id,
        run_id=run_id,
        kind=kind,
        valid_environments=VALID_ENVS,
    )


def _sync_media(*, release: Path, destination: str, run: Path) -> None:
    sync_media(release=release, destination=destination, run=run)


def _write_applied_ref(*, run: Path, env: str, release_id: str) -> None:
    _write_environment_applied_ref(
        output_root=OUTPUT_ROOT,
        run=run,
        environment=env,
        release_id=release_id,
        release_ref=release_ref(release_id),
    )


def _restore_previous_release(
    *,
    environment: str,
    failed_release_id: str,
    previous_release_id: str,
) -> None:
    """Replay a verified previous release through the formal importers."""

    rollback_release(
        argparse.Namespace(
            to_release=previous_release_id,
            from_release_id=failed_release_id,
            env=environment,
            run_id=f"restore-{_now_compact()}",
            import_to_db=True,
            dry_run=False,
            confirm_prod_apply=False,
        ),
        dependencies=_operation_dependencies(),
    )


def _assert_target_action_allowed(
    *,
    target: EnvironmentReleaseTarget,
    import_to_db: bool,
    dry_run: bool,
    action: str,
) -> None:
    _assert_environment_action_allowed(
        target=target,
        import_to_db=import_to_db,
        dry_run=dry_run,
        action=action,
    )


def _operation_dependencies() -> ShipOperationDependencies:
    return ShipOperationDependencies(
        output_root=OUTPUT_ROOT,
        load_release=_load_release,
        release_requires_full_sync=_release_requires_full_sync,
        release_has_posts=_release_has_posts,
        create_run=_create_run,
        run_root=_run_root,
        sync_media=_sync_media,
        write_applied_ref=_write_applied_ref,
        restore_previous_release=_restore_previous_release,
        assert_target_action_allowed=_assert_target_action_allowed,
        assert_environment_release_policy=assert_environment_release_policy,
        resolve_environment_release_target=resolve_environment_release_target,
        require_environment_readiness=require_environment_readiness,
        run_tag_importer=_run_tag_importer,
        run_creator_importer=_run_creator_importer,
        run_content_importer=_run_content_importer,
        run_homepage_importer=_run_homepage_importer,
        write_environment_coverage_receipt=(
            write_environment_coverage_receipt
        ),
        write_release_evidence=_write_release_evidence,
        write_verification_result=_write_verification_result,
        write_tag_consumer_verification=_write_tag_consumer_verification,
        write_homepage_verification_case_manifest=(
            write_homepage_verification_case_manifest
        ),
        write_baseline_api_verification=write_baseline_api_verification,
        write_post_api_verification=write_post_api_verification,
        write_homepage_api_verification=write_homepage_api_verification,
        write_research_isolation_verification=(
            write_research_isolation_verification
        ),
        write_environment_release_readiness=write_environment_release_readiness,
        now_compact=_now_compact,
    )


def _apply_release(args: argparse.Namespace) -> None:
    apply_release(args, dependencies=_operation_dependencies())


def _rollback_release(args: argparse.Namespace) -> None:
    rollback_release(args, dependencies=_operation_dependencies())


def _verify_release_consumers(args: argparse.Namespace) -> None:
    verify_release_consumers(args, dependencies=_operation_dependencies())


def handle_ship(args: argparse.Namespace) -> None:
    dispatch_ship(
        args,
        release_root=RELEASE_ROOT,
        apply=_apply_release,
        rollback=_rollback_release,
        verify=_verify_release_consumers,
    )
