# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046.t5
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment._ship_consumer_verification import (  # noqa: E402
    _assert_core_diagnostic_scope,
    _diagnostic_case_results,
)
from content.release.environment.topology import (  # noqa: E402
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
)
from content.release.model import DeploymentEnvironment  # noqa: E402


def _target(environment: DeploymentEnvironment, target_name: str) -> EnvironmentReleaseTarget:
    return EnvironmentReleaseTarget(
        environment=environment,
        target_name=target_name,
        mode=EnvironmentReleaseMode.LOCAL_IMPORT,
        mongo_uri="mongodb://test",
        user_postgres_dsn="postgres://test",
        media_sync_root=None,
        media_delivery_base_url="https://media.test",
        api_base_url="https://api.test",
        missing_requirements=(),
    )


def _post_report(*, probes: bool = True) -> dict[str, object]:
    return {
        "guestLogin": {"status": 200},
        "creators": [{"personaId": "p1"}],
        "posts": [{"postId": "x", "mediaProbes": ([{"status": 206}] if probes else [])}],
        "feedQueries": [{"name": "discovery_work"}, {"name": "homepage_recommend"}],
        "searchQueries": [{"targetId": "x"}],
    }


def test_core_diagnostic_selected_data_features_pass_without_readiness() -> None:
    selected = ("identity", "feed-detail", "search-recommendation", "image-video-range")
    rows = _diagnostic_case_results(selected, post_report=_post_report())
    assert [row["status"] for row in rows[:4]] == ["passed"] * 4
    assert [row["status"] for row in rows[4:]] == ["not_executed"] * 2


def test_core_diagnostic_missing_required_case_fails() -> None:
    rows = _diagnostic_case_results(("image-video-range",), post_report=_post_report(probes=False))
    media = next(row for row in rows if row["feature"] == "image-video-range")
    assert media["status"] == "failed"


def test_core_diagnostic_prod_requires_isolated_prevalidate() -> None:
    target = _target(DeploymentEnvironment.PROD, "prod-hosted")
    with pytest.raises(SystemExit, match="prevalidate with isolated"):
        _assert_core_diagnostic_scope(
            argparse.Namespace(
                env="prod", feature=["identity"], deployment_instance="prod", data_mode="external"
            ),
            target=target,
        )
    selected = _assert_core_diagnostic_scope(
        argparse.Namespace(
            env="prod", feature=["identity"], deployment_instance="prevalidate", data_mode="isolated"
        ),
        target=target,
    )
    assert selected == ("identity",)
