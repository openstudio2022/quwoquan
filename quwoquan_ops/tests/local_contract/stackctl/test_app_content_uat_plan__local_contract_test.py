"""Release-bound App content UAT plan consumes exact Data-owned bytes.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001.t6
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-004.t1
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.app_content_uat_plan import (
    build_app_content_uat_plan,
    load_release_uat_sample_plan,
)

from quwoquan_ops.tests.support.test_data_verification_test_support import (
    _readiness as release_readiness,
    _with_checksum,
)
from quwoquan_ops.tests.support.derivable_release_payload_test_support import (
    release_header_fixture,
)

CARRIERS = ("homepage", "article", "image", "video")
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
DIGESTS = {
    "manifest": "sha256:" + "1" * 64,
    "pool": "sha256:" + "2" * 64,
    "source": "sha256:" + "3" * 64,
    "merkle": "sha256:" + "4" * 64,
    "contents": "sha256:" + "5" * 64,
    "entities": "sha256:" + "6" * 64,
}


def _canonical_digest(document: object) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _readiness(
    *,
    release_id: str = "release-m100-a",
    eligible_homepages: int = 100,
) -> dict[str, object]:
    del eligible_homepages
    article_ids = [f"article-{index:03d}" for index in range(1, 101)]
    image_ids = [f"image-{index:03d}" for index in range(1, 101)]
    video_ids = [f"video-{index:03d}" for index in range(1, 11)]
    posts = [*article_ids, *image_ids, *video_ids]
    readiness = release_readiness(
        release_id=release_id, manifest_digest=DIGESTS["manifest"],
        post_ids=tuple(posts), entity_ref="/entity/place-001",
    )
    readiness["sourceIdentitySetDigest"] = DIGESTS["source"]
    readiness["activationEnvelope"]["sourceIdentitySetDigest"] = DIGESTS["source"]
    readiness["activationEnvelopeDigest"] = _canonical_digest(readiness["activationEnvelope"])
    readiness["entityRefs"] = [f"/entity/place-{index:03d}" for index in range(1, 101)]
    readiness["counts"].update(entities=100, premiumPlayableVideos=10)
    for query in readiness["feedQueries"]:
        query["matchedPostIds"] = {
            "typed_article": article_ids, "typed_image": image_ids,
            "typed_video": video_ids, "premium_stream": video_ids,
        }.get(query["name"], posts)
    return _with_checksum(readiness)

def _contents() -> list[dict[str, object]]:
    return [
        {
            "contentId": f"{carrier}-{index:03d}",
            "version": 1,
            "postRef": f"{carrier}/work-{index:03d}/1",
            "selectionIdentityDigest": DIGESTS["source"],
            "canonicalObjectDigest": DIGESTS["contents"],
            "contentLibraryBindingDigest": DIGESTS["pool"],
        }
        for carrier, count in (("article", 100), ("image", 100), ("video", 10))
        for index in range(1, count + 1)
    ]


def _selection_evidence() -> dict[str, str]:
    return {
        "poolDigest": DIGESTS["pool"],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "canonicalMerkle": DIGESTS["merkle"],
        "releaseContentsDigest": DIGESTS["contents"],
        "releaseEntityCohortDigest": DIGESTS["entities"],
    }


def _release_digest(release_id: str, evidence: dict[str, str]) -> str:
    return _canonical_digest(
        {
            "schema": "quwoquan_data.release_uat_sample_plan_identity",
            "releaseId": release_id,
            "canonicalMerkle": evidence["canonicalMerkle"],
            "selectionEvidence": evidence,
        }
    )


def _samples() -> list[dict[str, str]]:
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    rows: list[dict[str, str]] = []
    for carrier, count in distribution.items():
        for ordinal in range(1, count + 1):
            rows.append(
                {
                    "sampleId": f"m100-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "objectId": (
                        f"/entity/place-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"{carrier}-{ordinal:03d}"
                    ),
                    "objectRef": (
                        f"objects/entities/place-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"objects/posts/{carrier}/work-{ordinal:03d}/1"
                    ),
                    "objectDigest": _canonical_digest(
                        {"carrier": carrier, "ordinal": ordinal}
                    ),
                }
            )
    return rows


def _entry_carrier_cells() -> list[dict[str, str]]:
    return [
        {
            "entry": entry,
            "carrier": carrier,
            "applicability": "required",
            "specRef": "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006",
            "runnerClass": f"qwq.content_consumer.{entry}.{carrier}.v1",
        }
        for entry in ENTRIES
        for carrier in CARRIERS
    ]


def _sample_plan(*, eligible_homepages: int = 100) -> dict[str, object]:
    evidence = _selection_evidence()
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    release_digest = _release_digest("release-m100-a", evidence)
    return {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-m100-a",
        "releaseDigest": release_digest,
        "milestone": "M100",
        "selectionEvidence": evidence,
        "eligiblePopulationCounts": {
            "homepage": eligible_homepages,
            "article": 120,
            "image": 140,
            "video": 15,
        },
        "exactCohortCounts": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "entryCarrierCells": _entry_carrier_cells(),
        "sampleStrategy": {
            "name": "stratified_exact",
            "version": 1,
            "seedDigest": _canonical_digest(
                {
                    "releaseDigest": release_digest,
                    "sampleDistribution": distribution,
                }
            ),
            "carrierOrder": list(CARRIERS),
            "sortKey": "identity",
            "direction": "ascending",
            "objectDigestAlgorithm": "sha256-path-blob-merkle",
            "sampleDistribution": distribution,
        },
        "sampleCount": 100,
        "samples": _samples(),
    }


def _header() -> dict[str, object]:
    # producer detachment 禁止 header 携带 selectionScope/samplePlanRef/samplePlanDigest；
    # 下游派生 plan 只与 header 的 identity、digest 与 counts 对齐。
    return {
        **release_header_fixture(
            release_id="release-m100-a", contents=_contents(),
            source_identities=_readiness()["sourceIdentities"],
            source_identity_set_digest=DIGESTS["source"],
        ),
        "milestone": "M100",
        "milestoneTargets": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "counts": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
            "total": 310,
        },
        "poolDigest": DIGESTS["pool"],
        "canonicalMerkle": DIGESTS["merkle"],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "contents": _contents(),
    }


def _build(
    *,
    readiness: dict[str, object] | None = None,
    sample_plan: dict[str, object] | None = None,
    plan_digest: str | None = None,
) -> dict[str, object]:
    resolved_plan = sample_plan or _sample_plan()
    observed_digest = plan_digest or _canonical_digest(resolved_plan)
    return build_app_content_uat_plan(
        readiness or _readiness(),
        release_header=_header(),
        release_uat_sample_plan=resolved_plan,
        release_uat_sample_plan_digest=observed_digest,
        release_payload_sha256=DIGESTS["manifest"],
    )


def test_uat_plan__missing_header_and_sample_plan_fail_closed__local_contract() -> None:
    readiness = _readiness()
    readiness["counts"].update(entities=100, posts=210, premiumPlayableVideos=10)

    with pytest.raises(ValueError, match="explicit release header is missing"):
        build_app_content_uat_plan(readiness)
    with pytest.raises(ValueError, match="ReleaseUatSamplePlan is missing"):
        build_app_content_uat_plan(readiness, release_header=_header())


def test_uat_plan__retired_readiness_envelope_fails_closed__local_contract() -> None:
    readiness = _readiness()
    readiness["appUatEnvelope"] = {"releaseId": readiness["releaseId"]}

    with pytest.raises(ValueError, match="retired fields: appUatEnvelope"):
        _build(readiness=readiness)


def test_uat_plan__projects_canonical_samples_and_required_cells__local_contract() -> None:
    plan = _build(sample_plan=_sample_plan(eligible_homepages=130))

    assert plan["releaseIdentity"]["releaseId"] == "release-m100-a"
    assert plan["releaseIdentity"]["payloadSha256"] == DIGESTS["manifest"]
    assert "selectionScope" not in plan["releaseIdentity"]
    assert plan["releaseUatSamplePlanRef"] == (
        "data/releases/release-m100-a/uat/sample_plan.json"
    )
    assert len(plan["orderedSamples"]) == 100
    assert plan["orderedSamples"][0] == _samples()[0]
    assert len(plan["requiredCasePlan"]) == 16
    assert plan["requiredCasePlan"][0]["runnerClass"] == (
        "qwq.content_consumer.feed.homepage.v1"
    )
    assert len(plan["searchCanaries"]) == 4
    assert plan["videoPagination"]["expectedWorkIds"] == [
        f"video-{index:03d}" for index in range(1, 11)
    ]
    assert plan["mediaChecks"]["homepageRecommendation"]["expectedPostIds"] == [
        *[f"article-{index:03d}" for index in range(1, 101)],
        *[f"image-{index:03d}" for index in range(1, 101)],
        *[f"video-{index:03d}" for index in range(1, 11)],
    ]
    assert plan["mediaChecks"]["typedVideo"]["expectedPostIds"] == [
        f"video-{index:03d}" for index in range(1, 11)
    ]
    # 默认无类别路径只消费显式 premium_stream，不依赖旧 typed-video fallback。
    assert plan["mediaChecks"]["premiumVideo"]["expectedPostIds"] == [
        f"video-{index:03d}" for index in range(1, 11)
    ]
    assert "stratifiedSamples" not in plan
    assert "appUatEnvelope" not in plan


def test_uat_plan__eligible_overshoot_is_allowed_but_shortfall_fails__local_contract() -> None:
    _build(sample_plan=_sample_plan(eligible_homepages=130))

    with pytest.raises(ValueError, match="eligible population has a shortfall"):
        _build(sample_plan=_sample_plan(eligible_homepages=99))


def test_uat_plan__counts_cannot_infer_or_replace_explicit_plan__local_contract() -> None:
    readiness = _readiness()
    readiness["counts"].update(entities=999, posts=999, premiumPlayableVideos=99)

    with pytest.raises(ValueError, match="ReleaseUatSamplePlan is missing"):
        build_app_content_uat_plan(readiness, release_header=_header())


def test_uat_plan__rejects_digest_release_and_distribution_drift__local_contract() -> None:
    with pytest.raises(ValueError, match="not a canonical sha256 digest"):
        _build(plan_digest="sha256:not-a-digest")

    drifted_cohort = _sample_plan()
    drifted_cohort["exactCohortCounts"]["video"] = 9  # type: ignore[index]
    with pytest.raises(ValueError, match="exact cohort drifted"):
        _build(sample_plan=drifted_cohort)

    drifted_release = _sample_plan()
    drifted_release["releaseId"] = "release-other"
    with pytest.raises(ValueError, match="releaseId mismatch"):
        _build(sample_plan=drifted_release)

    drifted_distribution = _sample_plan()
    drifted_distribution["sampleStrategy"]["sampleDistribution"] = {  # type: ignore[index]
        "homepage": 25,
        "article": 26,
        "image": 39,
        "video": 10,
    }
    with pytest.raises(ValueError, match="distribution drifted"):
        _build(sample_plan=drifted_distribution)


def _write_release_fixture(output_root: Path, *, release_id: str) -> tuple[Path, dict[str, object]]:
    """一份最小 immutable release：每载体一个对象目录 + desired_state + header。"""

    payload = output_root / "data" / "releases" / release_id / "payload"
    entity_ref = "地点/景区/塘栖古镇"
    post_refs = {
        "article": "article/美食/塘栖枇杷漫谈/1",
        "image": "image/风光/广济桥上望塘栖/1",
        "video": "video/风光/塘栖古镇水乡漫步/1",
    }
    (payload / "objects" / "entities" / entity_ref).mkdir(parents=True)
    (payload / "objects" / "entities" / entity_ref / "_entity.json").write_text(
        '{"label":"塘栖古镇"}\n', encoding="utf-8"
    )
    for post_ref in post_refs.values():
        (payload / "objects" / "posts" / post_ref).mkdir(parents=True)
        (payload / "objects" / "posts" / post_ref / "manifest.json").write_text(
            json.dumps({"postRef": post_ref}) + "\n", encoding="utf-8"
        )
    (payload / "desired_state.json").write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": {
                    "creators": [],
                    "entities": [entity_ref],
                    "posts": list(post_refs.values()),
                    "tags": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    header = release_header_fixture(
        release_id=release_id,
        source_identities=_readiness()["sourceIdentities"],
        source_identity_set_digest=DIGESTS["source"],
        contents=[
            {"contentId": f"content-{carrier}", "version": 1, "postRef": post_ref}
            for carrier, post_ref in post_refs.items()
        ],
    )
    (payload / "release.json").write_text(
        json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload, header


@pytest.mark.parametrize("release_class", ["research", "commercial"])
def test_sample_derivation_rejects_retired_release_before_writing(tmp_path: Path, release_class: str) -> None:
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-044"""
    payload, header = _write_release_fixture(tmp_path, release_id="release-retired")
    header["releaseClass"] = release_class
    header["productLifecycleState"] = release_class
    original = (payload / "release.json").read_bytes()
    with pytest.raises(ValueError, match="Additional properties are not allowed"):
        load_release_uat_sample_plan(release_root=payload, release_header=header)
    assert not (payload.parent / "uat").exists()
    assert (payload / "release.json").read_bytes() == original


def test_load_release_uat_sample_plan__derives_create_once_from_release_bytes__local_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004"""

    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    payload, header = _write_release_fixture(tmp_path, release_id="release-derived-a")

    plan, ref, digest = load_release_uat_sample_plan(
        release_root=payload, release_header=header
    )
    assert ref == "data/releases/release-derived-a/uat/sample_plan.json"
    plan_path = tmp_path / ref
    assert plan_path.is_file() and (plan_path.parent / "derivation.json").is_file()
    assert "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest() == digest
    assert plan["milestone"] is None
    assert plan["sampleStrategy"]["name"] == "baseline_per_required_carrier"
    assert [row["carrier"] for row in plan["samples"]] == list(CARRIERS)
    assert plan["samples"][0]["objectId"] == "/entity/地点/景区/塘栖古镇"
    assert plan["samples"][0]["objectRef"] == "objects/entities/地点/景区/塘栖古镇"
    assert plan["samples"][3]["objectRef"] == "objects/posts/video/风光/塘栖古镇水乡漫步/1"
    assert plan["exactCohortCounts"] == {"homepage": 1, "article": 1, "image": 1, "video": 1}
    assert len(plan["entryCarrierCells"]) == 16
    # payload/ 之外落盘：immutable payload 字节不受派生影响。
    assert not (payload / "uat").exists()

    # 同字节重放幂等，且 App UAT plan 能直接消费派生结果。
    again, again_ref, again_digest = load_release_uat_sample_plan(
        release_root=payload, release_header=header
    )
    assert (again, again_ref, again_digest) == (plan, ref, digest)
    readiness = release_readiness(
        release_id="release-derived-a", manifest_digest=DIGESTS["manifest"],
        post_ids=("content-article", "content-image", "content-video"),
        entity_ref="/entity/地点/景区/塘栖古镇",
        source_identities=header["sourceIdentities"],
    )
    readiness["sourceIdentitySetDigest"] = header["sourceIdentitySetDigest"]
    readiness["activationEnvelope"]["sourceIdentitySetDigest"] = header["sourceIdentitySetDigest"]
    readiness["activationEnvelopeDigest"] = _canonical_digest(readiness["activationEnvelope"])
    readiness = _with_checksum(readiness)
    uat_plan = build_app_content_uat_plan(
        readiness,
        release_header=header,
        release_uat_sample_plan=plan,
        release_uat_sample_plan_digest=digest,
        release_payload_sha256=DIGESTS["manifest"],
    )
    assert uat_plan["releaseUatSamplePlanRef"] == ref
    assert uat_plan["releaseUatSamplePlanDigest"] == digest
    assert uat_plan["carrierIdentities"]["video"] == "content-video"

    # 已落盘字节被改写 → fail closed，不静默重派生覆盖。
    plan_path.write_bytes(plan_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="drifted from immutable release bytes"):
        load_release_uat_sample_plan(release_root=payload, release_header=header)


def test_load_release_uat_sample_plan__rejects_cross_release_receipt_and_noncanonical_root__local_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    payload, header = _write_release_fixture(tmp_path, release_id="release-derived-b")
    load_release_uat_sample_plan(release_root=payload, release_header=header)

    # 把另一个 release 的派生回执搬运过来：plan 字节相同也必须被 manifestDigest 绑定拒绝。
    receipt_path = tmp_path / "data/releases/release-derived-b/uat/derivation.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["manifestDigest"] = "sha256:" + "f" * 64
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not bound to this exact release"):
        load_release_uat_sample_plan(release_root=payload, release_header=header)

    # 非 canonical release root 不得派生。
    stray = tmp_path / "elsewhere" / "release-derived-b" / "payload"
    stray.mkdir(parents=True)
    with pytest.raises(ValueError, match="not the canonical data/releases"):
        load_release_uat_sample_plan(release_root=stray, release_header=header)



def test_uat_plan__default_feed_projection_rejects_missing_or_nonrelease_ids__local_contract() -> None:
    readiness = _readiness()
    premium = next(row for row in readiness["feedQueries"] if row["name"] == "premium_stream")
    premium["matchedPostIds"] = ["video-001"]
    plan = _build(readiness=_with_checksum(readiness))
    assert plan["mediaChecks"]["premiumVideo"]["expectedPostIds"] == ["video-001"]
    assert "releaseClass" not in plan["releaseIdentity"]

    premium["matchedPostIds"] = ["other-release-video"]
    with pytest.raises(ValueError, match="not release-bound"):
        _build(readiness=_with_checksum(readiness))
    readiness["feedQueries"].remove(premium)
    with pytest.raises(ValueError, match="Data environment_release_readiness schema"):
        _build(readiness=_with_checksum(readiness))


@pytest.mark.parametrize("field", ["releaseClass", "productLifecycleState", "readinessPhase"])
def test_uat_plan__research_categories_are_rejected__local_contract(field: str) -> None:
    readiness = _readiness()
    readiness[field] = "research"
    with pytest.raises(ValueError, match="Additional properties are not allowed"):
        _build(readiness=_with_checksum(readiness))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "empty_query"])
def test_uat_plan__rejects_retired_premium_feed_fallback__local_contract(mutation: str) -> None:
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-044"""
    readiness = _readiness()
    queries = readiness["feedQueries"]
    premium = next(row for row in queries if row["name"] == "premium_stream")
    if mutation == "missing":
        queries.remove(premium)
    elif mutation == "duplicate":
        queries.append(dict(premium))
    else:
        premium["query"] = ""
    with pytest.raises(ValueError, match="schema|premium_stream exact"):
        _build(readiness=readiness)


def test_uat_plan__rejects_retired_source_identity_shape__local_contract() -> None:
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-044"""
    readiness = _readiness()
    header = _header()
    for document in (readiness, header):
        document.pop("sourceIdentities")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
            document[field] = DIGESTS["source"]
    with pytest.raises(ValueError, match="schema|source identity set drifted"):
        build_app_content_uat_plan(
            readiness,
            release_header=header,
            release_uat_sample_plan=_sample_plan(),
            release_uat_sample_plan_digest=_canonical_digest(_sample_plan()),
            release_payload_sha256=DIGESTS["manifest"],
        )