# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import request_envelope as campaign_request_envelope
from content.execution.campaign import (
    request_envelope_build as campaign_request_envelope_build,
)
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign.external_inputs import (
    CampaignExternalInputError,
    bind_external_input_refs,
    external_inputs_digest,
    verify_external_input_refs,
)
from core.io import write_json
from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot
from support.capacity_calibration_fixture import synthetic_capacity_source_binding
from support.campaign_external_inputs_fixture import (  # noqa: F401
    CATALOG_DIGEST,
    SOURCE_DIGEST,
    SOURCE_REVISION,
    _acquisition,
    _governed_acquisition_handoff,
)


BUNDLE_DIGEST = "sha256:" + "b" * 64


class _FrozenSourceDigest:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def to_document(self) -> dict[str, object]:
        return self._document


def _bind_observed_identities(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source: dict[str, object],
    bundle: dict[str, object],
) -> None:
    """Pin what the repository currently observes for both frozen identities."""

    monkeypatch.setattr(
        campaign_submission,
        "current_source_definition_snapshot",
        lambda **_kwargs: _FrozenSourceDigest(source),
    )
    monkeypatch.setattr(
        campaign_submission,
        "current_execution_bundle_identity",
        lambda **_kwargs: _FrozenSourceDigest(bundle),
    )


def test_campaign_submission_accepts_stable_dirty_source_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(BUNDLE_DIGEST).to_document()
    _bind_observed_identities(monkeypatch, source=source, bundle=bundle)

    campaign_submission._require_stable_source_inputs(
        source,
        execution_bundle=bundle,
        repo_root=tmp_path,
    )


def test_campaign_submission_rejects_source_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(BUNDLE_DIGEST).to_document()
    observed = {**frozen, "digest": "sha256:" + ("f" * 64)}
    _bind_observed_identities(monkeypatch, source=observed, bundle=bundle)

    with pytest.raises(ValueError, match="changed during freeze"):
        campaign_submission._require_stable_source_inputs(
            frozen,
            execution_bundle=bundle,
            repo_root=tmp_path,
        )


def test_campaign_submission_rejects_execution_bundle_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An executor change must invalidate the freeze on its own."""

    frozen = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(BUNDLE_DIGEST).to_document()
    observed_bundle = {**bundle, "digest": "sha256:" + ("c" * 64)}
    _bind_observed_identities(monkeypatch, source=frozen, bundle=observed_bundle)

    with pytest.raises(ValueError, match="changed during freeze"):
        campaign_submission._require_stable_source_inputs(
            frozen,
            execution_bundle=bundle,
            repo_root=tmp_path,
        )



def test_external_inputs_reject_path_escape_and_content_replacement(
    tmp_path: Path,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    with pytest.raises(CampaignExternalInputError, match="PATH_ESCAPE"):
        bind_external_input_refs(
            "image",
            [
                {
                    "kind": "professional_image_acquisition",
                    "manifestRef": "../manifest.json",
                    "receiptRef": refs[0]["receiptRef"],
                }
            ],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )

    blob = acquisition_root / str(refs[0]["blobRefs"][0]["blobRef"])
    blob.write_bytes(blob.read_bytes() + b"tamper")
    with pytest.raises(
        CampaignExternalInputError, match="DIGEST_DRIFT|digest mismatch"
    ):
        verify_external_input_refs(
            "image",
            refs,
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )




def test_professional_image_input_is_limited_to_homepage_and_image(
    tmp_path: Path,
) -> None:
    acquisition_root, image_refs = _acquisition(tmp_path)
    declaration = {
        "kind": image_refs[0]["kind"],
        "manifestRef": image_refs[0]["manifestRef"],
        "receiptRef": image_refs[0]["receiptRef"],
    }
    homepage_refs = bind_external_input_refs(
        "homepage",
        [declaration],
        acquisition_root=acquisition_root,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    assert homepage_refs[0]["carrier"] == "homepage"
    with pytest.raises(CampaignExternalInputError, match="not admitted for article"):
        bind_external_input_refs(
            "article",
            [declaration],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )




def test_request_envelope_freezes_content_addressed_external_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    repo = tmp_path / "repo"
    (repo / "quwoquan_data/reference/travel/entities/china").mkdir(parents=True)

    for module in (campaign_request_envelope, campaign_request_envelope_build):
        monkeypatch.setattr(
            module,
            "current_source_definition_snapshot",
            lambda **_kwargs: SourceDefinitionSnapshot(SOURCE_DIGEST),
        )
        monkeypatch.setattr(
            module,
            "current_execution_bundle_identity",
            lambda **_kwargs: ExecutionBundleIdentity(BUNDLE_DIGEST),
        )
    monkeypatch.setattr(
        campaign_request_envelope_build,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_require_stable_source_inputs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_git_branch",
        lambda _repo: "dev1.0",
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_git_commit",
        lambda _repo: "c" * 40,
    )
    capacity_ref = Path("data/local/tests/capacity/local-contract-capacity.json")
    monkeypatch.setattr(
        campaign_request_envelope_build,
        "resolve_capacity_calibration_ref",
        lambda ref: Path(ref),
    )
    monkeypatch.setattr(
        campaign_request_envelope_build,
        "bind_capacity_calibration_source",
        lambda **_kwargs: synthetic_capacity_source_binding(),
    )
    envelope = campaign_request_envelope.build_envelope(
        quota=1,
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260805",
        capacity_calibration_receipt=capacity_ref,
        external_input_refs=[
            {
                "kind": refs[0]["kind"],
                "manifestRef": refs[0]["manifestRef"],
                "receiptRef": refs[0]["receiptRef"],
            }
        ],
        acquisition_root=acquisition_root,
    )
    assert envelope["sourceRevision"] == SOURCE_REVISION
    assert envelope["externalInputRefs"] == refs
    assert envelope["externalInputsDigest"] == external_inputs_digest(refs)
    path = tmp_path / "image-envelope.json"
    write_json(path, envelope)
    assert campaign_request_envelope.load_campaign_envelope(path) == envelope
