"""Post targets may only parent homepages that actually reached canonical publish."""
from __future__ import annotations

import pytest

from content.execution.homepage_binding import PublishedHomepageBinding
from content.execution.workspace import FrozenTarget


EXECUTION_ID = "20260711--travel-homepage-coverage--test-region-a--pilot-001"
REGION_REF = "test-region-a"


def _binding(published: tuple[str, ...], *, pool: int = 5) -> PublishedHomepageBinding:
    targets = tuple(
        FrozenTarget(name=f"过采对象{index}", entity_type="地点/景区")
        for index in range(pool)
    )
    return PublishedHomepageBinding(
        execution_id=EXECUTION_ID,
        region_ref=REGION_REF,
        targets=targets,
        published_refs=frozenset(f"地点/景区/{name}" for name in published),
    )


def test_partial_publish_above_quota_binds_only_published_homepages() -> None:
    """候选池 5、发布 3、配额 3：放行，且返回的必须全部是已发布对象。"""
    binding = _binding(("过采对象0", "过采对象2", "过采对象4"))

    names = binding.target_names(region_ref=REGION_REF, count=5, quota=3)

    assert names == ("过采对象0", "过采对象2", "过采对象4")
    assert "过采对象1" not in names  # 被丢弃的对象绝不能成为文章父对象


def test_binding_never_returns_unpublished_targets_when_count_exceeds_supply() -> None:
    binding = _binding(("过采对象3",), pool=5)

    names = binding.target_names(region_ref=REGION_REF, count=5, quota=1)

    assert names == ("过采对象3",)


def test_publish_below_quota_is_blocked() -> None:
    binding = _binding(("过采对象0", "过采对象1"))

    with pytest.raises(ValueError, match="below the approved quota 4"):
        binding.target_names(region_ref=REGION_REF, count=5, quota=4)


def test_publish_closure_outside_the_frozen_target_set_is_blocked() -> None:
    """完整性校验保留：发布集合必须是冻结目标集的子集。"""
    binding = _binding(("过采对象0", "过采对象1"))
    contaminated = PublishedHomepageBinding(
        execution_id=binding.execution_id,
        region_ref=binding.region_ref,
        targets=binding.targets,
        published_refs=binding.published_refs | {"地点/景区/走私对象"},
    )

    with pytest.raises(ValueError, match="outside its\n?\\s*frozen target set"):
        contaminated.target_names(region_ref=REGION_REF, count=5, quota=1)


def test_region_mismatch_is_blocked() -> None:
    binding = _binding(("过采对象0",))

    with pytest.raises(ValueError, match="post region must equal"):
        binding.target_names(region_ref="test-region-b", count=5, quota=1)
