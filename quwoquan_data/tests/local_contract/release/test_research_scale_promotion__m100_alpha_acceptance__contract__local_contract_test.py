"""M100 Alpha acceptance is a product-stage gate on M1000, and only on M1000.

Before M1000 may be promoted, the same M100 Research release has to have been
activated and read back in Alpha and to have passed 100 App UAT cases. Two things
make that a gate rather than a checkbox. It is scoped: M100's own promotion, and
the source discovery, semantic and review work feeding M1000, run without it, so
supplying acceptance evidence anywhere else is a category error rather than extra
diligence. And it is bound: the evidence must name the exact M100 promotion
receipt, release and manifest, so a passing Alpha run of a neighbouring release
cannot be spent here.

A frozen binding is therefore a claim, never the proof. Every ref it carries is
re-read and re-derived from bytes, because a document that could vouch for itself
would let the gate be satisfied by writing a file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.research_scale_promotion import (  # noqa: E402
    ResearchScalePromotionError,
    write_research_scale_promotion,
)
from content.release.canonical.research_scale_promotion_acceptance import (  # noqa: E402
    ResearchScalePromotionAcceptanceError,
    bind_m1000_alpha_acceptance,
    validate_acceptance_input_mode,
)

from quwoquan_data.tests.support.m100_alpha_acceptance_fixture import (  # noqa: E402
    m100_predecessor_reference,
    m100_targets,
    unproven_acceptance_binding,
    write_m100_milestone_release,
    write_m100_promotion,
)

RELEASE_ID = "research-m100"
READINESS_REF = "env/alpha/runs/data-release/research-m100/verify/release-readiness.json"
APP_UAT_REF = "env/alpha/runs/data-release/research-m100/verify/app-content-uat.json"


def _receipt_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "output" / READINESS_REF, tmp_path / "output" / APP_UAT_REF


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_alpha_acceptance_gates_m1000_and_nothing_else(tmp_path: Path) -> None:
    """M100 and M10000 promotion do not consume this evidence at all."""

    readiness, app_uat = _receipt_paths(tmp_path)

    for scale in ("M100", "M10000"):
        with pytest.raises(
            ResearchScalePromotionAcceptanceError,
            match="ALPHA_M100_ACCEPTANCE_UNEXPECTED",
        ):
            validate_acceptance_input_mode(
                target_scale=scale,
                predecessor_promotion_path=None,
                readiness_receipt_path=readiness,
                app_uat_receipt_path=app_uat,
                binding_path=None,
            )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_a_scale_without_the_gate_accepts_no_acceptance_input(tmp_path: Path) -> None:
    """Absent evidence is the normal state for every scale but M1000."""

    validate_acceptance_input_mode(
        target_scale="M100",
        predecessor_promotion_path=None,
        readiness_receipt_path=None,
        app_uat_receipt_path=None,
        binding_path=None,
    )
    assert bind_m1000_alpha_acceptance(
        target_scale="M100",
        predecessor_promotion_path=None,
        predecessor_reference=None,
        readiness_receipt_path=None,
        app_uat_receipt_path=None,
        binding_path=None,
        output_root=tmp_path / "output",
    ) == (None, {})


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_m1000_without_alpha_acceptance_is_refused(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    predecessor = output_root / "promotions/research-m100.json"
    readiness, app_uat = _receipt_paths(tmp_path)

    for supplied in ({"readiness_receipt_path": readiness}, {"app_uat_receipt_path": app_uat}, {}):
        with pytest.raises(
            ResearchScalePromotionAcceptanceError,
            match="ALPHA_M100_ACCEPTANCE_MISSING",
        ):
            validate_acceptance_input_mode(
                target_scale="M1000",
                predecessor_promotion_path=predecessor,
                readiness_receipt_path=supplied.get("readiness_receipt_path"),
                app_uat_receipt_path=supplied.get("app_uat_receipt_path"),
                binding_path=None,
            )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
def test_acceptance_has_one_input_mode(tmp_path: Path) -> None:
    """A frozen binding and the raw receipts are two truths for one gate.

    Accepting both at once would leave which one decided the outcome unreadable
    from the receipt, so the ambiguity is refused instead of silently ranked.
    """

    output_root = tmp_path / "output"
    readiness, app_uat = _receipt_paths(tmp_path)

    with pytest.raises(
        ResearchScalePromotionAcceptanceError,
        match="ALPHA_M100_ACCEPTANCE_AMBIGUOUS",
    ):
        validate_acceptance_input_mode(
            target_scale="M1000",
            predecessor_promotion_path=output_root / "promotions/research-m100.json",
            readiness_receipt_path=readiness,
            app_uat_receipt_path=app_uat,
            binding_path=output_root / "acceptance/binding.json",
        )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_m1000_acceptance_requires_the_m100_promotion_it_accepts(
    tmp_path: Path,
) -> None:
    """Alpha acceptance is acceptance *of* an M100 cohort, not a standalone pass."""

    readiness, app_uat = _receipt_paths(tmp_path)

    with pytest.raises(
        ResearchScalePromotionAcceptanceError,
        match="PREDECESSOR_IDENTITY_DRIFT",
    ):
        bind_m1000_alpha_acceptance(
            target_scale="M1000",
            predecessor_promotion_path=None,
            predecessor_reference=None,
            readiness_receipt_path=readiness,
            app_uat_receipt_path=app_uat,
            binding_path=None,
            output_root=tmp_path / "output",
        )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
def test_a_frozen_binding_is_re_derived_from_the_bytes_it_names(
    tmp_path: Path,
) -> None:
    """A document that vouched for itself would make the gate self-signable."""

    output_root = tmp_path / "output"
    promotion_ref = "data/local/workspace/promotions/research-m100.json"
    binding_path = output_root / "acceptance/binding.json"
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text(
        json.dumps(
            unproven_acceptance_binding(
                promotion_receipt_ref=promotion_ref,
                readiness_receipt_ref=READINESS_REF,
                app_uat_receipt_ref=APP_UAT_REF,
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResearchScalePromotionAcceptanceError):
        bind_m1000_alpha_acceptance(
            target_scale="M1000",
            predecessor_promotion_path=output_root / promotion_ref,
            predecessor_reference={
                "promotionId": "promotion-m100",
                "releaseId": RELEASE_ID,
                "manifestDigest": "sha256:" + "b" * 64,
                "receiptRef": promotion_ref,
                "receiptDigest": "sha256:" + "c" * 64,
            },
            readiness_receipt_path=None,
            app_uat_receipt_path=None,
            binding_path=binding_path,
            output_root=output_root,
        )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_the_binding_cannot_claim_fewer_than_one_hundred_uat_cases(
    tmp_path: Path,
) -> None:
    """100 cases is the gate; 99 is not a smaller pass, it is not a pass."""

    output_root = tmp_path / "output"
    binding_path = output_root / "acceptance/binding.json"
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text(
        json.dumps(
            unproven_acceptance_binding(
                promotion_receipt_ref="data/local/workspace/promotions/m100.json",
                readiness_receipt_ref=READINESS_REF,
                app_uat_receipt_ref=APP_UAT_REF,
                overrides={"executedSampleCount": 99},
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResearchScalePromotionAcceptanceError) as failure:
        bind_m1000_alpha_acceptance(
            target_scale="M1000",
            predecessor_promotion_path=output_root
            / "data/local/workspace/promotions/m100.json",
            predecessor_reference={
                "promotionId": "promotion-m100",
                "releaseId": RELEASE_ID,
                "manifestDigest": "sha256:" + "b" * 64,
                "receiptRef": "data/local/workspace/promotions/m100.json",
                "receiptDigest": "sha256:" + "c" * 64,
            },
            readiness_receipt_path=None,
            app_uat_receipt_path=None,
            binding_path=binding_path,
            output_root=output_root,
        )

    assert "executedSampleCount" in str(failure.value)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_the_binding_cannot_claim_a_cohort_below_the_governed_target(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    binding_path = output_root / "acceptance/binding.json"
    binding_path.parent.mkdir(parents=True)
    short = {**m100_targets(), "video": 9}
    binding_path.write_text(
        json.dumps(
            unproven_acceptance_binding(
                promotion_receipt_ref="data/local/workspace/promotions/m100.json",
                readiness_receipt_ref=READINESS_REF,
                app_uat_receipt_ref=APP_UAT_REF,
                overrides={
                    "exactCounts": {
                        **short,
                        "posts": short["article"] + short["image"] + short["video"],
                    }
                },
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResearchScalePromotionAcceptanceError):
        bind_m1000_alpha_acceptance(
            target_scale="M1000",
            predecessor_promotion_path=output_root
            / "data/local/workspace/promotions/m100.json",
            predecessor_reference={
                "promotionId": "promotion-m100",
                "releaseId": RELEASE_ID,
                "manifestDigest": "sha256:" + "b" * 64,
                "receiptRef": "data/local/workspace/promotions/m100.json",
                "receiptDigest": "sha256:" + "c" * 64,
            },
            readiness_receipt_path=None,
            app_uat_receipt_path=None,
            binding_path=binding_path,
            output_root=output_root,
        )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_m100_promotion_needs_no_alpha_acceptance(tmp_path: Path) -> None:
    """The product-stage gate sits in front of M1000, never in front of M100."""

    output_root = tmp_path / "output"
    write_m100_milestone_release(output_root, release_id=RELEASE_ID)

    receipt, path = write_m100_promotion(output_root, release_id=RELEASE_ID)

    assert "m100AlphaAcceptanceBinding" not in receipt
    assert receipt["nextScaleEligible"] == "M1000"
    assert path.is_file()


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_a_refused_m1000_promotion_leaves_the_m100_cohort_intact(
    tmp_path: Path,
) -> None:
    """The gate withholds the next milestone; it does not revoke the last one."""

    output_root = tmp_path / "output"
    write_m100_milestone_release(output_root, release_id=RELEASE_ID)
    _, m100_path = write_m100_promotion(output_root, release_id=RELEASE_ID)
    before = m100_path.read_bytes()
    reference = m100_predecessor_reference(m100_path, output_root=output_root)
    write_m100_milestone_release(output_root, release_id="research-m1000")

    with pytest.raises(
        ResearchScalePromotionError, match="ALPHA_M100_ACCEPTANCE_MISSING"
    ):
        write_research_scale_promotion(
            release_id="research-m1000",
            promotion_id="promotion-m1000",
            target_scale="M1000",
            predecessor_promotion_path=m100_path,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )

    assert m100_path.read_bytes() == before
    assert reference["receiptRef"].endswith("research-m100.json")
    assert not (
        output_root / "data/local/workspace/research-scale-promotions/research-m1000"
    ).exists()
