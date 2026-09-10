# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
"""默认 release 不借环境名称生成权利授权；环境只约束投放容量。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.release.environment.release_runtime import assert_environment_release_policy
from quwoquan_data.tests.local_contract.release.test_release_header__typed_identity__contract__local_contract_test import _header


def _release(tmp_path: Path, **fields: object) -> Path:
    release = tmp_path / "release"
    payload = release / "payload"
    payload.mkdir(parents=True)
    document = _header(release_id="release-policy-001")
    document.update(fields)
    (payload / "release.json").write_text(json.dumps(document), encoding="utf-8")
    return release


@pytest.mark.parametrize("environment", ("alpha", "beta", "gamma", "prod"))
def test_every_environment_accepts_the_same_classless_release(tmp_path: Path, environment: str) -> None:
    assert_environment_release_policy(
        release=_release(tmp_path),
        contract={"desiredRefs": {"posts": ["article/a"]}},
        environment=environment,
    )


@pytest.mark.parametrize("field", ("releaseClass", "productLifecycleState", "readinessPhase", "targetEnvironment"))
def test_release_rejects_retired_category_and_environment_fields(tmp_path: Path, field: str) -> None:
    with pytest.raises(SystemExit, match="DATA.RELEASE.ENVIRONMENT_POLICY_INVALID"):
        assert_environment_release_policy(
            release=_release(tmp_path, **{field: "production"}),
            contract={"desiredRefs": {"posts": ["article/a"]}},
            environment="prod",
        )


def test_alpha_cap_counts_only_data_posts(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="DATA.RELEASE.POST_CAP_EXCEEDED"):
        assert_environment_release_policy(
            release=_release(tmp_path),
            contract={"desiredRefs": {
                "posts": [f"article/{index}" for index in range(2_101)],
                "creators": ["creator/a"], "entities": ["entity/a"], "tags": ["tag/a"],
            }},
            environment="alpha",
        )


def test_prod_has_no_data_post_cap(tmp_path: Path) -> None:
    assert_environment_release_policy(
        release=_release(tmp_path),
        contract={"desiredRefs": {"posts": [f"article/{index}" for index in range(100_001)]}},
        environment="prod",
    )
