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
    lifecycle: str | None = None,
) -> Path:
    """One immutable release header carrying its own usage authorization.

    ``lifecycle`` defaults to ``release_class`` because the header is the authorization:
    the pair is what the policy reads, and a release that declares only one half of it
    is refused rather than assumed. Tests that need the drift pass them apart.
    """

    release = tmp_path / "release"
    payload = release / "payload"
    payload.mkdir(parents=True)
    (payload / "release.json").write_text(
        json.dumps(
            {
                "releaseClass": release_class,
                "productLifecycleState": (
                    release_class if lifecycle is None else lifecycle
                ),
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


def test_a_release_declaring_half_its_authorization_is_refused(tmp_path: Path) -> None:
    """Authorization comes from the header pair, not from the environment it targets.

    `prod` does not by itself mean commercial — an environment-neutral research
    milestone activates there. What is refused is a header whose releaseClass and
    lifecycle disagree, because then no single answer to "may this be used
    commercially" exists and the environment name would have to invent one.
    """

    release = _release(tmp_path, "research", lifecycle="commercial")
    with pytest.raises(SystemExit, match="DATA.RELEASE.USAGE_SCOPE_MISMATCH"):
        assert_environment_release_policy(
            release=release,
            contract={"desiredRefs": {"posts": ["article/a"]}},
            environment="prod",
        )


def test_a_release_without_a_lifecycle_cannot_borrow_one(tmp_path: Path) -> None:
    release = _release(tmp_path, "research", lifecycle="")
    with pytest.raises(SystemExit, match="DATA.RELEASE.USAGE_SCOPE_MISMATCH"):
        assert_environment_release_policy(
            release=release,
            contract={"desiredRefs": {"posts": ["article/a"]}},
            environment="alpha",
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
