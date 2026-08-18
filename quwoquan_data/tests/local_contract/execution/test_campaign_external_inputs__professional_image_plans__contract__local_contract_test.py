# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
)
from content.execution.campaign.external_inputs import (
    bind_external_input_refs,
    materialize_external_input_bundle,
)
from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)
from content.source.external_acquisition_inputs import (
    professional_image_context_binding,
)
from content.source.research import auto_plan_homepage
from content.source.research.auto_plan_homepage import (
    HomepageResearchInput,
    write_homepage_lane,
)
from content.source.research.auto_plan_lanes import write_image_lane
from core.io import read_json
from support.campaign_external_inputs_fixture import (  # noqa: F401
    CATALOG_DIGEST,
    EXECUTION_IDS,
    SOURCE_DIGEST,
    SOURCE_REVISION,
    _acquisition,
    _governed_acquisition_handoff,
)


def _external_context(
    root: Path,
    refs: list[dict[str, object]],
    *,
    execution_id: str,
    carrier: str,
) -> ExternalInputRuntimeContext:
    blobs = {
        str(blob["contentSha256"]): (
            Path(str(row["acquisitionRootRef"])) / str(blob["blobRef"])
        ).as_posix()
        for row in refs
        for blob in row["blobRefs"]
    }
    return ExternalInputRuntimeContext(
        root=root,
        envelope={"executionId": execution_id, "carrier": carrier},
        refs=tuple(dict(row) for row in refs),
        blob_refs_by_digest=blobs,
    )




def test_frozen_professional_images_drive_homepage_and_image_plans_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    bundles = {
        "homepage": tmp_path / "capsule/external-inputs/homepage",
        "image": tmp_path / "capsule/external-inputs/image",
    }
    for carrier, refs in (("homepage", homepage_refs), ("image", image_refs)):
        materialize_external_input_bundle(
            bundles[carrier],
            refs,
            acquisition_root=acquisition_root,
            carrier=carrier,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
            library_root=acquisition_root.parent / "content_library",
        )

    image_context = _external_context(
        bundles["image"],
        image_refs,
        execution_id=EXECUTION_IDS["image"],
        carrier="image",
    )
    receipt_refs, image_specs = professional_image_context_binding(
        execution_id=EXECUTION_IDS["image"],
        entity_id="九寨沟",
        carrier="image",
        external_input_context=image_context,
    )
    assert receipt_refs == [image_refs[0]["receiptRef"]]
    assert len(image_specs) == 1
    wiki_candidate = {
        "url": "https://upload.wikimedia.org/wiki/fallback.jpg",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Fallback.jpg",
        "platform": "Wikimedia Commons",
        "creator": "Fallback Creator",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Fallback.jpg",
        "caption": "九寨沟 fallback",
        "relevance": "九寨沟 fallback",
        "width": 1600,
        "height": 1000,
    }
    image_plan_dir = tmp_path / "image-plan"
    image_report: dict[str, object] = {"sourceUnavailable": []}
    write_image_lane(
        entity_id="九寨沟",
        entity_aliases=["九寨沟风景名胜区"],
        vertical="travel",
        plan_dir=image_plan_dir,
        force=True,
        report=image_report,
        updated=[],
        prior_image_collections=[],
        prior_image_pool=[],
        openverse=[wiki_candidate],
        commons=[wiki_candidate],
        hint_commons=[],
        wikidata_commons=[],
        wiki_page_images=[wiki_candidate],
        voyage_page_images=[],
        open_license_image_pool=[wiki_candidate],
        homepage_image_urls=set(),
        required_publishable_images=1,
        required_article_bases=1,
        desired_image_works=1,
        hard_image_works=1,
        image_bonus_saturation_count=1,
        image_policy="hard_quota",
        image_strategy="downloaded_source_assets",
        requires_publishable_images=True,
        qid="",
        wiki_title="",
        voyage_title="",
        professional_image_specs=image_specs,
        acquisition_receipt_refs=receipt_refs,
    )
    image_plan = read_json(image_plan_dir / "image_source_plan.json")
    image_payload = image_plan["payload"]
    assert image_plan["acquisitionReceiptRefs"] == receipt_refs
    assert "acquisitionReceiptRefs" not in image_payload
    image_collection = image_payload["collections"][0]
    assert image_collection["platform"] == "Pinterest"
    assert image_collection["authorizationProof"].startswith("https://")
    assert image_collection["rightsStatus"] == "verified"
    assert image_collection["authorizationRequired"] is False
    assert image_collection["distributionDecision"] == "commercial_allowed"
    assert image_collection["rightsIssues"] == []
    assert image_collection["images"][0]["authorizationProof"].startswith("https://")
    assert not any(
        image["url"] == wiki_candidate["url"]
        for collection in image_payload["collections"]
        for image in collection["images"]
    )

    homepage_context = _external_context(
        bundles["homepage"],
        homepage_refs,
        execution_id=EXECUTION_IDS["homepage"],
        carrier="homepage",
    )
    homepage_receipt_refs, homepage_specs = professional_image_context_binding(
        execution_id=EXECUTION_IDS["homepage"],
        entity_id="九寨沟",
        carrier="homepage",
        external_input_context=homepage_context,
    )
    monkeypatch.setattr(
        auto_plan_homepage,
        "_candidate_sources",
        lambda _spec: [
            {
                "source_id": "home_wikipedia",
                "sourceKind": "wikipedia",
                "platform": "维基百科",
                "url": "https://zh.wikipedia.org/wiki/九寨沟",
                "category": "encyclopedia",
                "sourceRole": "primary",
                "matchConfidence": 1.0,
                "discoveryProvider": "mediawiki_exact_title",
                "extractor": "wikipedia_api",
                "policyRevision": "encyclopedia-primary",
            }
        ],
    )
    homepage_plan_dir = tmp_path / "homepage-plan"
    write_homepage_lane(
        HomepageResearchInput(
            execution_id=EXECUTION_IDS["homepage"],
            entity_id="九寨沟",
            entity_aliases=("九寨沟风景名胜区",),
            vertical="travel",
            plan_dir=homepage_plan_dir,
            report={"sourceUnavailable": []},
            updated=[],
            qualified_homepage_source=QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title="九寨沟",
                url="https://zh.wikipedia.org/wiki/九寨沟",
            ),
            wiki_page_images=(wiki_candidate,),
            prior_image_pool=(),
            voyage_page_images=(),
            commons=(wiki_candidate,),
            hint_commons=(),
            wikidata_commons=(),
            openverse=(wiki_candidate,),
            rejected_source_urls=frozenset(),
            force=True,
            professional_image_specs=tuple(homepage_specs),
            acquisition_receipt_refs=tuple(homepage_receipt_refs),
        )
    )
    homepage_plan = read_json(homepage_plan_dir / "homepage_source_plan.json")
    homepage_payload = homepage_plan["payload"]
    assert homepage_plan["acquisitionReceiptRefs"] == homepage_receipt_refs
    assert "acquisitionReceiptRefs" not in homepage_payload
    homepage_collection = homepage_payload["homepageMediaCollections"][0]
    assert homepage_collection["platform"] == "Pinterest"
    assert homepage_collection["authorizationProof"].startswith("https://")
    assert homepage_collection["rightsStatus"] == "verified"
    assert homepage_collection["rightsIssues"] == []
    assert homepage_collection["images"][0]["url"] == homepage_specs[0]["url"]
