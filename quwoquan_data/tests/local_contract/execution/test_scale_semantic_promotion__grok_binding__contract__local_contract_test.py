# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
"""Governed `cursor_grok` author/reviewer binding for scale promotion evidence.

`REQ-004` freezes the governed production primary as `cursor_grok`, with the
exact model and parameters declared by the current runtime profile rather than
by a spec-side version constant, and forbids a silent in-execution fallback or
an SDK Auto first route standing in for Grok evidence.  `cursor_auto` is only
reachable as an explicit new `retryOf` after the parent execution terminated on
an allowed typed provider/model failure.

The calibration sample rate, its minimum count and the calibration model are
not stated in `specs/`, so no test here asserts those values; only the
order-independence and closure properties of the selection are locked.
"""
from __future__ import annotations

import pytest
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    CURSOR_GROK_SEMANTIC_SELECTION_ID,
    governed_cursor_grok_model,
)
from content.execution.scale.semantic_promotion import (
    SCALE_SEMANTIC_PROMOTION_ISSUE_CODE,
    ScaleSemanticPromotionError,
    require_scale_promotion_model_binding,
    scale_calibration_sample_count,
    select_scale_calibration_refs,
)
from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID


def _grok_binding() -> dict[str, str]:
    model = governed_cursor_grok_model(DEFAULT_RUNTIME_PROFILE_ID)
    return {
        "provider": "cursor_sdk",
        "authorModel": model,
        "authorModelFamily": "grok",
        "reviewerModel": model,
        "reviewerModelFamily": "grok",
    }


def test_the_governed_primary_model_comes_from_the_runtime_profile() -> None:
    """`REQ-004` forbids a spec-side version constant for the Grok model."""

    model = governed_cursor_grok_model(DEFAULT_RUNTIME_PROFILE_ID)

    assert model.startswith("grok")
    assert model == governed_cursor_grok_model(DEFAULT_RUNTIME_PROFILE_ID)


def test_the_frozen_grok_binding_is_promotable() -> None:
    """The governed `cursor_grok` selection is the accepted production primary."""

    frozen = require_scale_promotion_model_binding(
        _grok_binding(),
        label="video M100 promotion",
    )

    assert frozen == _grok_binding()
    assert frozen["provider"] == "cursor_sdk"
    assert frozen["authorModelFamily"] == "grok"


def test_a_reviewer_model_diverging_from_the_author_fails_closed() -> None:
    """A silent swap of the reviewer route may not stand in for Grok evidence."""

    binding = _grok_binding()
    binding["reviewerModel"] = "gpt-5.6-sol"
    binding["reviewerModelFamily"] = "gpt"

    with pytest.raises(ScaleSemanticPromotionError) as excinfo:
        require_scale_promotion_model_binding(binding, label="video M100 promotion")

    assert SCALE_SEMANTIC_PROMOTION_ISSUE_CODE in str(excinfo.value)


def test_an_auto_family_binding_is_not_a_governed_primary() -> None:
    """`cursor_auto` is a typed `retryOf` path, never the frozen primary."""

    binding = _grok_binding()
    binding["authorModelFamily"] = "auto"
    binding["reviewerModelFamily"] = "auto"
    binding["authorModel"] = CURSOR_AUTO_SEMANTIC_SELECTION_ID
    binding["reviewerModel"] = CURSOR_AUTO_SEMANTIC_SELECTION_ID

    frozen = require_scale_promotion_model_binding(
        binding,
        label="video M100 promotion",
    )

    assert frozen["authorModel"] != governed_cursor_grok_model(
        DEFAULT_RUNTIME_PROFILE_ID
    )
    assert CURSOR_GROK_SEMANTIC_SELECTION_ID not in frozen["authorModel"]


def test_an_absent_binding_fails_closed_instead_of_defaulting() -> None:
    """A missing binding is a failure, not an implicit governed default."""

    with pytest.raises(ScaleSemanticPromotionError, match="modelBinding is missing"):
        require_scale_promotion_model_binding(None, label="video M100 promotion")


@pytest.mark.parametrize("field", [
    "provider",
    "authorModel",
    "authorModelFamily",
    "reviewerModel",
    "reviewerModelFamily",
])
def test_every_binding_field_must_be_present_and_non_empty(field: str) -> None:
    """An empty scalar may not collapse into an accepted governed binding."""

    binding = _grok_binding()
    binding[field] = "   "

    with pytest.raises(ScaleSemanticPromotionError):
        require_scale_promotion_model_binding(binding, label="video M100 promotion")


def test_an_ungoverned_provider_fails_closed() -> None:
    """Only the governed SDK adapters may carry promotion evidence."""

    binding = _grok_binding()
    binding["provider"] = "http_api"

    with pytest.raises(ScaleSemanticPromotionError):
        require_scale_promotion_model_binding(binding, label="video M100 promotion")


def test_calibration_selection_ignores_candidate_list_order() -> None:
    """Promotion evidence must be replayable from the frozen object closure."""

    refs = tuple(f"posts/video/v{index}" for index in range(20))
    forward = select_scale_calibration_refs(
        carrier="video",
        object_refs=refs,
        accepted_count=20,
    )
    reversed_order = select_scale_calibration_refs(
        carrier="video",
        object_refs=tuple(reversed(refs)),
        accepted_count=20,
    )

    assert forward == reversed_order
    assert set(forward) <= set(refs)
    assert len(set(forward)) == len(forward)
    assert len(forward) == scale_calibration_sample_count(20)


def test_the_selection_is_carrier_scoped() -> None:
    """A carrier is part of the selection identity, not a shared ordering."""

    refs = tuple(f"posts/v{index}" for index in range(30))

    assert select_scale_calibration_refs(
        carrier="video",
        object_refs=refs,
        accepted_count=30,
    ) != select_scale_calibration_refs(
        carrier="image",
        object_refs=refs,
        accepted_count=30,
    )


def test_duplicate_candidates_fail_closed() -> None:
    """`REQ-004` does not count exact duplicates toward cumulative scale."""

    with pytest.raises(ScaleSemanticPromotionError, match="unique"):
        select_scale_calibration_refs(
            carrier="video",
            object_refs=("posts/video/v1", "posts/video/v1"),
            accepted_count=2,
        )


def test_an_empty_candidate_ref_fails_closed() -> None:
    """A blank ref may not silently shrink the published object closure."""

    with pytest.raises(ScaleSemanticPromotionError, match="non-empty"):
        select_scale_calibration_refs(
            carrier="video",
            object_refs=("posts/video/v1", "   "),
            accepted_count=2,
        )


def test_accepted_count_may_not_exceed_the_published_closure() -> None:
    """Promotion only verifies cumulative unique objects actually published."""

    with pytest.raises(ScaleSemanticPromotionError, match="exceeds published"):
        select_scale_calibration_refs(
            carrier="video",
            object_refs=("posts/video/v1",),
            accepted_count=2,
        )


def test_zero_accepted_objects_selects_nothing() -> None:
    """Present-and-empty stays empty; it does not become a sampled batch."""

    assert scale_calibration_sample_count(0) == 0
    assert select_scale_calibration_refs(
        carrier="video",
        object_refs=("posts/video/v1",),
        accepted_count=0,
    ) == ()


@pytest.mark.parametrize("value", [-1, True, 1.0, "10"])
def test_a_non_integer_accepted_count_fails_closed(value: object) -> None:
    """The accepted object count is a governed integer, never coerced."""

    with pytest.raises(ScaleSemanticPromotionError):
        scale_calibration_sample_count(value)  # type: ignore[arg-type]


def test_the_sample_never_exceeds_the_accepted_object_count() -> None:
    """A calibration sample is a subset of the accepted closure."""

    for accepted in (1, 2, 5, 9, 10, 11, 37, 100, 1000):
        assert 0 < scale_calibration_sample_count(accepted) <= accepted
