from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.environment.release_runtime import (  # noqa: E402
    assert_environment_release_policy,
)


def _release(
    tmp_path: Path,
    release_class: str,
    *,
    target_environment: str = "",
    milestone: str = "",
) -> Path:
    release = tmp_path / "release"
    payload = release / "payload"
    payload.mkdir(parents=True)
    (payload / "release.json").write_text(
        json.dumps(
            {
                "releaseClass": release_class,
                **(
                    {"targetEnvironment": target_environment}
                    if target_environment
                    else {}
                ),
                **({"milestone": milestone} if milestone else {}),
            }
        ),
        encoding="utf-8",
    )
    return release


@pytest.mark.parametrize("environment", ["alpha", "beta", "gamma"])
def test_research_environments_accept_research_release(
    tmp_path: Path,
    environment: str,
) -> None:
    assert_environment_release_policy(
        release=_release(tmp_path, "research"),
        contract={"desiredRefs": {"posts": ["article/a"]}},
        environment=environment,
    )


def test_prod_requires_commercial_release(tmp_path: Path) -> None:
    release = _release(tmp_path, "research")
    with pytest.raises(SystemExit, match="DATA.RELEASE.USAGE_SCOPE_MISMATCH"):
        assert_environment_release_policy(
            release=release,
            contract={"desiredRefs": {"posts": ["article/a"]}},
            environment="prod",
        )


def test_prod_accepts_environment_neutral_research_milestone(tmp_path: Path) -> None:
    assert_environment_release_policy(
        release=_release(tmp_path, "research", milestone="M1000"),
        contract={"desiredRefs": {"posts": ["article/a"]}},
        environment="prod",
    )


def test_environment_specific_manifest_cannot_activate_elsewhere(tmp_path: Path) -> None:
    release = _release(
        tmp_path,
        "research",
        target_environment="alpha",
    )
    with pytest.raises(
        SystemExit,
        match="DATA.RELEASE.TARGET_ENVIRONMENT_MISMATCH",
    ):
        assert_environment_release_policy(
            release=release,
            contract={"desiredRefs": {"posts": ["article/a"]}},
            environment="beta",
        )


def test_alpha_cap_counts_only_data_posts(tmp_path: Path) -> None:
    release = _release(tmp_path, "research")
    with pytest.raises(SystemExit, match="DATA.RELEASE.POST_CAP_EXCEEDED"):
        assert_environment_release_policy(
            release=release,
            contract={
                "desiredRefs": {
                "posts": [f"article/{index}" for index in range(2_101)],
                    "creators": ["creator/a"],
                    "entities": ["entity/a"],
                    "tags": ["tag/a"],
                }
            },
            environment="alpha",
        )


def test_prod_has_no_data_post_cap(tmp_path: Path) -> None:
    assert_environment_release_policy(
        release=_release(tmp_path, "commercial"),
        contract={
            "desiredRefs": {
                "posts": [f"article/{index}" for index in range(100_001)]
            }
        },
        environment="prod",
    )
