"""Resolve and validate real reads for a milestone App content sample plan."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_DISTRIBUTIONS = {
    "M100": {"homepage": 25, "article": 25, "image": 40, "video": 10},
    "M1000": {"homepage": 25, "article": 25, "image": 25, "video": 25},
    "M10000": {"homepage": 25, "article": 25, "image": 25, "video": 25},
}
_SOURCE_READBACKS = {
    "homepage": "entityRefs",
    "article": "feedQueries.typed_article",
    "image": "feedQueries.typed_image",
    "video": "feedQueries.typed_video",
}
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_regular_json(path: Path, *, root: Path, label: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    try:
        ref = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value, ref


def _sample_cases(plan: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    raw = plan.get("orderedSamples")
    if not isinstance(raw, list) or not raw:
        raise ValueError("App content UAT ReleaseUatSamplePlan orderedSamples are missing")
    release_identity = plan.get("releaseIdentity")
    milestone = (
        str((plan.get("releaseUatSamplePlan") or {}).get("milestone") or "").strip()
        if isinstance(plan.get("releaseUatSamplePlan"), Mapping)
        else ""
    )
    if not milestone and isinstance(release_identity, Mapping):
        milestone = str(release_identity.get("milestone") or "").strip()
    # Milestone is optional for canary plans; distribution is carried by exact rows.
    normalized: list[dict[str, Any]] = []
    for index, raw_case in enumerate(raw):
        if not isinstance(raw_case, Mapping):
            raise ValueError(f"App content UAT sample {index} is invalid")
        carrier = str(raw_case.get("carrier") or "").strip()
        sample_id = str(raw_case.get("sampleId") or "").strip()
        object_id = str(raw_case.get("objectId") or "").strip()
        object_ref = str(raw_case.get("objectRef") or "").strip()
        object_digest = str(raw_case.get("objectDigest") or "").strip()
        if (
            carrier not in _SOURCE_READBACKS
            or not sample_id
            or not object_id
            or not object_ref
            or not object_digest.startswith("sha256:")
        ):
            raise ValueError(f"App content UAT sample {index} identity is invalid")
        normalized.append(
            {
                "sampleId": sample_id,
                "carrier": carrier,
                "sourceObjectId": object_id,
                "objectRef": object_ref,
                "objectDigest": object_digest,
            }
        )
    for field in ("sampleId", "sourceObjectId", "objectRef"):
        values = [str(case[field]) for case in normalized]
        if len(values) != len(set(values)):
            raise ValueError(f"App content UAT sample {field} values are duplicated")
    distribution = dict(Counter(case["carrier"] for case in normalized))
    if milestone and distribution != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT sample distribution drifted")
    return milestone, normalized


def _required_asset_identity(
    raw: Mapping[str, Any],
    *,
    label: str,
    release_class: str,
) -> dict[str, Any]:
    asset_id = str(raw.get("assetId") or "").strip()
    kind = str(raw.get("kind") or "").strip()
    content_type = str(raw.get("contentType") or "").strip().lower()
    expected_bytes = raw.get("bytes")
    expected_sha256 = str(raw.get("sha256") or "").strip()
    private_ref = str(raw.get("privateObjectKey") or "").strip().lstrip("/")
    owner_refs = raw.get("ownerRefs")
    if (
        not asset_id
        or kind not in {"avatar", "image", "video"}
        or not content_type.startswith("video/" if kind == "video" else "image/")
        or not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or _DIGEST_PATTERN.fullmatch(expected_sha256) is None
        or not isinstance(owner_refs, list)
        or not owner_refs
        or any(not str(value or "").strip() for value in owner_refs)
    ):
        raise ValueError(f"App content UAT {label} identity is invalid")
    if release_class == "research":
        if raw.get("publicSliceKey") is not None or not private_ref.startswith(
            "media/objects/sha256/"
        ):
            raise ValueError(f"App content UAT {label} private delivery is invalid")
    return {
        "assetId": asset_id,
        "kind": kind,
        "expectedBytes": expected_bytes,
        "expectedSha256": expected_sha256,
        "expectedMimeType": content_type,
        "privateDeliveryRef": private_ref,
        "ownerRefs": [str(value).strip().strip("/") for value in owner_refs],
    }


def _release_media_authority(
    *,
    readiness: Mapping[str, Any],
    root: Path,
    release_id: str,
) -> tuple[dict[str, dict[str, Any]], Path]:
    media_ref = str(readiness.get("mediaManifestRef") or "").strip()
    if not media_ref:
        raise ValueError("App content UAT media manifest ref is missing")
    media_manifest, observed_ref = _load_regular_json(
        root / media_ref,
        root=root,
        label="App content UAT release media manifest",
    )
    if observed_ref != media_ref:
        raise ValueError("App content UAT release media manifest ref drifted")
    media_path = (root / media_ref).resolve()
    observed_digest = _file_digest(media_path)
    if (
        media_manifest.get("schema") != "quwoquan_data.release_media_manifest"
        or media_manifest.get("releaseId") != release_id
        or media_manifest.get("sourceOwner") != "qwq_data"
        or observed_digest != readiness.get("mediaManifestDigest")
    ):
        raise ValueError("App content UAT release media manifest is not release-bound")
    release_class = str(readiness.get("releaseClass") or "").strip()
    raw_assets = media_manifest.get("assets")
    if release_class not in {"research", "commercial"} or not isinstance(
        raw_assets, list
    ):
        raise ValueError("App content UAT release media authority is incomplete")
    assets: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_assets):
        if not isinstance(raw, Mapping):
            raise ValueError(f"App content UAT release media asset {index} is invalid")
        asset = _required_asset_identity(
            raw, label=f"release media asset {index}", release_class=release_class
        )
        if asset["assetId"] in assets:
            raise ValueError("App content UAT release media asset IDs are duplicated")
        assets[str(asset["assetId"])] = asset
    readiness_asset_ids = {
        str(value).strip()
        for value in readiness.get("mediaAssetIds") or []
        if str(value).strip()
    }
    if set(assets) != readiness_asset_ids:
        raise ValueError("App content UAT release media assets drift from readiness")
    return assets, media_path.parent


def _release_creator_profiles(
    *,
    payload_root: Path,
    assets: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    creators_root = payload_root / "objects/creators"
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(creators_root.glob("*/profile.json")):
        profile, _raw = _load_regular_json(
            path, root=payload_root, label="App content UAT release creator profile"
        )
        creator_ref = path.parent.name
        author_id = str(profile.get("authorId") or "").strip()
        persona_id = str(profile.get("personaId") or "").strip()
        display_name = str(profile.get("displayName") or "").strip()
        if (
            profile.get("schema") != "quwoquan_data.creator_profile"
            or not creator_ref
            or not author_id
            or not persona_id
            or not display_name
            or author_id in profiles
        ):
            raise ValueError("App content UAT release creator profile identity drifted")
        raw_avatar = profile.get("avatarAsset")
        avatar_id = ""
        avatar_ref = ""
        if raw_avatar is not None:
            if not isinstance(raw_avatar, Mapping):
                raise ValueError("App content UAT release creator avatar binding is invalid")
            avatar_id = str(raw_avatar.get("assetId") or "").strip()
            avatar = assets.get(avatar_id)
            if (
                not avatar_id
                or not isinstance(avatar, Mapping)
                or avatar.get("kind") != "avatar"
                or f"creators/{creator_ref}" not in (avatar.get("ownerRefs") or [])
                or raw_avatar.get("sha256") != avatar.get("expectedSha256")
            ):
                raise ValueError("App content UAT release creator avatar is not release-bound")
            avatar_ref = str(avatar.get("privateDeliveryRef") or "")
        profiles[author_id] = {
            "creatorRef": creator_ref,
            "authorId": author_id,
            "personaId": persona_id,
            "displayName": display_name,
            "avatarAssetId": avatar_id,
            "avatarDeliveryRef": avatar_ref,
        }
    if not profiles:
        raise ValueError("App content UAT release creator profiles are missing")
    return profiles


def _strict_research_media_checks(
    *,
    plan: Mapping[str, Any],
    assets: Mapping[str, Mapping[str, Any]],
    bindings_by_post_id: Mapping[str, Mapping[str, Any]],
    creators_by_author: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    raw_media = plan.get("mediaChecks")
    if not isinstance(raw_media, Mapping):
        raise ValueError("App content UAT mediaChecks are missing")
    category_post_ids = {
        "image": {
            str(binding.get("postId") or "")
            for binding in bindings_by_post_id.values()
            if binding.get("contentId") == raw_media.get("imageWorkId")
        },
        "typed_video": {
            str(value).strip()
            for value in (raw_media.get("typedVideo") or {}).get("expectedPostIds", [])
            if str(value).strip()
        }
        if isinstance(raw_media.get("typedVideo"), Mapping)
        else set(),
        "premium_video": {
            str(value).strip()
            for value in (raw_media.get("premiumVideo") or {}).get("expectedPostIds", [])
            if str(value).strip()
        }
        if isinstance(raw_media.get("premiumVideo"), Mapping)
        else set(),
    }
    checks_by_asset: dict[str, dict[str, Any]] = {}

    def add(category: str, asset: Mapping[str, Any]) -> None:
        asset_id = str(asset.get("assetId") or "")
        row = checks_by_asset.setdefault(
            asset_id,
            {
                key: asset[key]
                for key in (
                    "assetId",
                    "kind",
                    "expectedBytes",
                    "expectedSha256",
                    "expectedMimeType",
                    "privateDeliveryRef",
                )
            },
        )
        row.setdefault("classifications", []).append(category)
        row["requireRange"] = row["kind"] == "video"

    avatar_assets = [
        assets[str(profile["avatarAssetId"])]
        for profile in creators_by_author.values()
        if str(profile.get("avatarAssetId") or "") in assets
    ]
    if not avatar_assets:
        raise ValueError("App content UAT private avatar classification is missing")
    add("avatar", sorted(avatar_assets, key=lambda row: str(row["assetId"]))[0])
    for category, post_ids in category_post_ids.items():
        expected_kind = "image" if category == "image" else "video"
        candidates = [
            asset
            for asset in assets.values()
            if asset.get("kind") == expected_kind
            and any(
                str(owner).removeprefix("posts/")
                == str(binding.get("postRef") or "").strip().strip("/")
                for owner in asset.get("ownerRefs") or []
                for post_id, binding in bindings_by_post_id.items()
                if post_id in post_ids
            )
        ]
        if not candidates:
            raise ValueError(
                f"App content UAT private {category} classification is missing"
            )
        add(category, sorted(candidates, key=lambda row: str(row["assetId"]))[0])
    required = {"avatar", "image", "typed_video", "premium_video"}
    observed = {
        classification
        for row in checks_by_asset.values()
        for classification in row["classifications"]
    }
    if observed != required:
        raise ValueError("App content UAT strict media classifications are incomplete")
    return [
        {**row, "classifications": sorted(set(row["classifications"]))}
        for _asset_id, row in sorted(checks_by_asset.items())
    ]


def resolve_release_sample_requests(
    *,
    readiness_path: Path,
    app_uat_plan: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    """Resolve plan identities to exact public read identities.

    Homepage samples originate in readiness ``entityRefs`` and resolve through
    the current release's homepage API verification. Post samples originate as
    immutable Data ``contentId`` values and resolve through the import report's
    exact ``contentId``/``postRef``/``postId`` binding; Ops never equates those
    owner-specific identities.
    """

    root = output_root.expanduser().resolve()
    readiness, readiness_ref = _load_regular_json(
        readiness_path,
        root=root,
        label="App content UAT readiness receipt",
    )
    milestone, cases = _sample_cases(app_uat_plan)
    release_id = str(readiness.get("releaseId") or "").strip()
    if (
        not release_id
        or not isinstance(app_uat_plan.get("releaseIdentity"), Mapping)
        or app_uat_plan["releaseIdentity"].get("releaseId") != release_id
    ):
        raise ValueError("App content UAT sample plan releaseId drifted")
    sample_plan_ref = str(app_uat_plan.get("releaseUatSamplePlanRef") or "").strip()
    sample_plan_digest = str(app_uat_plan.get("releaseUatSamplePlanDigest") or "").strip()
    if not sample_plan_ref or not sample_plan_digest.startswith("sha256:"):
        raise ValueError("App content UAT ReleaseUatSamplePlan binding is missing")

    homepage_ref = str(readiness.get("homepageApiVerificationRef") or "").strip()
    if not homepage_ref:
        raise ValueError("App content UAT homepage API verification ref is missing")
    homepage_report, observed_homepage_ref = _load_regular_json(
        root / homepage_ref,
        root=root,
        label="App content UAT homepage API verification",
    )
    if observed_homepage_ref != homepage_ref:
        raise ValueError("App content UAT homepage API verification ref drifted")
    if (
        homepage_report.get("schema") != "quwoquan_data.homepage_api_verification"
        or homepage_report.get("releaseId") != release_id
        or homepage_report.get("passed") is not True
        or homepage_report.get("issues") != []
    ):
        raise ValueError("App content UAT homepage API verification is not passed")
    raw_entities = homepage_report.get("entities")
    if not isinstance(raw_entities, list):
        raise ValueError("App content UAT homepage API verification entities are missing")
    homepage_ids: dict[str, str] = {}
    for row in raw_entities:
        if not isinstance(row, Mapping):
            raise ValueError("App content UAT homepage API verification entity is invalid")
        entity_ref = str(row.get("entityRef") or "").strip()
        homepage_id = str(row.get("homepageId") or "").strip()
        if (
            not entity_ref
            or not homepage_id
            or entity_ref in homepage_ids
            or row.get("detailStatus") != 200
            or row.get("introductionStatus") != 200
        ):
            raise ValueError("App content UAT homepage API verification identity drifted")
        for identity in {
            entity_ref,
            entity_ref.strip("/").removeprefix("entity/"),
            entity_ref.strip("/").removeprefix("entities/"),
        }:
            if identity in homepage_ids and homepage_ids[identity] != homepage_id:
                raise ValueError(
                    "App content UAT homepage API verification identity drifted"
                )
            homepage_ids[identity] = homepage_id

    import_ref = str(readiness.get("contentImportReportRef") or "").strip()
    if not import_ref:
        raise ValueError("App content UAT content import report ref is missing")
    import_report, observed_import_ref = _load_regular_json(
        root / import_ref,
        root=root,
        label="App content UAT content import report",
    )
    if observed_import_ref != import_ref:
        raise ValueError("App content UAT content import report ref drifted")
    if (
        import_report.get("schema") != "quwoquan.content_import_report"
        or import_report.get("releaseId") != release_id
        or import_report.get("status") != "imported"
        or import_report.get("manifestDigest") != readiness.get("manifestDigest")
    ):
        raise ValueError("App content UAT content import report is not release-bound")
    raw_bindings = import_report.get("postBindings")
    if not isinstance(raw_bindings, list):
        raise ValueError("App content UAT content import post bindings are missing")
    post_ids = {
        str(value).strip() for value in readiness.get("postIds") or [] if str(value).strip()
    }
    post_bindings: dict[tuple[str, str, str], str] = {}
    bindings_by_post_id: dict[str, dict[str, Any]] = {}
    observed_post_ids: set[str] = set()
    for index, raw_binding in enumerate(raw_bindings):
        if not isinstance(raw_binding, Mapping):
            raise ValueError(f"App content UAT content import binding {index} is invalid")
        content_id = str(raw_binding.get("contentId") or "").strip()
        post_ref = str(raw_binding.get("postRef") or "").strip()
        post_id = str(raw_binding.get("postId") or "").strip()
        content_type = str(raw_binding.get("contentType") or "").strip()
        key = (content_id, post_ref, content_type)
        if (
            not all(key)
            or not post_id
            or key in post_bindings
            or post_id in observed_post_ids
        ):
            raise ValueError("App content UAT content import binding identity drifted")
        post_bindings[key] = post_id
        bindings_by_post_id[post_id] = {
            "contentId": content_id,
            "postRef": post_ref,
            "postId": post_id,
            "contentType": content_type,
            "authorId": str(raw_binding.get("authorId") or "").strip(),
        }
        observed_post_ids.add(post_id)
    if observed_post_ids != post_ids:
        raise ValueError("App content UAT content import postIds drifted from readiness")

    strict_research = readiness.get("releaseClass") == "research"
    assets: dict[str, dict[str, Any]] = {}
    creators_by_author: dict[str, dict[str, Any]] = {}
    strict_media_checks: list[dict[str, Any]] = []
    if strict_research:
        assets, payload_root = _release_media_authority(
            readiness=readiness, root=root, release_id=release_id
        )
        creators_by_author = _release_creator_profiles(
            payload_root=payload_root, assets=assets
        )
        strict_media_checks = _strict_research_media_checks(
            plan=app_uat_plan,
            assets=assets,
            bindings_by_post_id=bindings_by_post_id,
            creators_by_author=creators_by_author,
        )

    samples: list[dict[str, Any]] = []
    carrier_ordinals: Counter[str] = Counter()
    for case in cases:
        carrier = str(case["carrier"])
        source_id = str(case["sourceObjectId"])
        carrier_ordinals[carrier] += 1
        if carrier == "homepage":
            normalized_source_id = source_id.strip("/")
            for prefix in ("entities/", "entity/"):
                if normalized_source_id.startswith(prefix):
                    normalized_source_id = normalized_source_id[len(prefix) :]
                    break
            read_object_id = homepage_ids.get(source_id, "") or homepage_ids.get(
                normalized_source_id, ""
            )
        else:
            object_ref = str(case["objectRef"])
            prefix = f"objects/posts/{carrier}/"
            if not object_ref.startswith(prefix):
                raise ValueError(
                    f"App content UAT immutable object ref is invalid for {source_id}"
                )
            post_ref = object_ref.removeprefix("objects/posts/")
            read_object_id = post_bindings.get((source_id, post_ref, carrier), "")
        if not read_object_id:
            raise ValueError(
                f"App content UAT runtime mapping is missing for {source_id}"
            )
        creator: Mapping[str, Any] = {}
        if strict_research and carrier != "homepage":
            binding = bindings_by_post_id[read_object_id]
            author_id = str(binding.get("authorId") or "")
            creator = creators_by_author.get(author_id, {})
            if not creator:
                raise ValueError(
                    f"App content UAT release creator mapping is missing for {source_id}"
                )
        samples.append(
            {
                "sampleId": case["sampleId"],
                "carrier": carrier,
                "sourceReadback": _SOURCE_READBACKS[carrier],
                "sourceObjectId": source_id,
                "objectRef": str(case["objectRef"]),
                "objectDigest": str(case["objectDigest"]),
                "ordinal": carrier_ordinals[carrier],
                "readObjectId": read_object_id,
                "expectedContentType": "" if carrier == "homepage" else carrier,
                "expectedAuthorId": str(creator.get("authorId") or ""),
                "expectedPersonaId": str(creator.get("personaId") or ""),
                "expectedAuthorDisplayName": str(creator.get("displayName") or ""),
                "expectedAvatarAssetId": str(creator.get("avatarAssetId") or ""),
                "expectedAvatarDeliveryRef": str(
                    creator.get("avatarDeliveryRef") or ""
                ),
            }
        )
    return {
        "releaseId": release_id,
        "milestone": milestone,
        "releaseUatSamplePlanRef": sample_plan_ref,
        "releaseUatSamplePlanDigest": sample_plan_digest,
        "readinessReceiptRef": readiness_ref,
        "readinessReceiptFileSha256": _file_digest((root / readiness_ref).resolve()),
        "homepageApiVerificationRef": homepage_ref,
        "homepageApiVerificationFileSha256": _file_digest((root / homepage_ref).resolve()),
        "contentImportReportRef": import_ref,
        "contentImportReportFileSha256": _file_digest((root / import_ref).resolve()),
        "mediaManifestRef": str(readiness.get("mediaManifestRef") or ""),
        "mediaManifestFileSha256": (
            _file_digest(
                (root / str(readiness.get("mediaManifestRef") or "")).resolve()
            )
            if strict_research
            else ""
        ),
        "creatorProfiles": [
            dict(row)
            for _author_id, row in sorted(creators_by_author.items())
            if row.get("avatarAssetId")
        ],
        "strictMediaChecks": strict_media_checks,
        "samples": samples,
    }


def validate_release_strict_probe(
    *,
    report: Mapping[str, Any],
    resolved: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate fresh Research creator/avatar and signed-media evidence."""

    checks = report.get("checks")
    if report.get("status") != "passed" or not isinstance(checks, list):
        raise ValueError("App content UAT strict Research probe did not pass")
    expected_profiles = {
        str(row.get("personaId") or ""): row
        for row in resolved.get("creatorProfiles") or []
        if isinstance(row, Mapping)
    }
    profile_checks = [
        row
        for row in checks
        if isinstance(row, Mapping) and row.get("name") == "release_creator_profile"
    ]
    if len(profile_checks) != len(expected_profiles):
        raise ValueError("App content UAT creator profile coverage is incomplete")
    observed_profiles: set[str] = set()
    for row in profile_checks:
        persona_id = str(row.get("personaId") or "")
        expected = expected_profiles.get(persona_id)
        if (
            expected is None
            or persona_id in observed_profiles
            or row.get("ok") is not True
            or row.get("statusCode") != 200
            or row.get("returnedPersonaId") != persona_id
            or row.get("returnedAvatarDeliveryRef")
            != expected.get("avatarDeliveryRef")
            or not str(row.get("responseDigest") or "").startswith("sha256:")
            or not isinstance(row.get("responseBytes"), int)
            or row.get("responseBytes", 0) <= 0
        ):
            raise ValueError("App content UAT creator/profile/avatar evidence drifted")
        observed_profiles.add(persona_id)
    expected_assets = {
        str(row.get("assetId") or ""): row
        for row in resolved.get("strictMediaChecks") or []
        if isinstance(row, Mapping)
    }
    media_checks = [
        row
        for row in checks
        if isinstance(row, Mapping) and row.get("name") == "release_signed_media"
    ]
    if len(media_checks) != 1 or media_checks[0].get("ok") is not True:
        raise ValueError("App content UAT signed media execution is missing")
    evidence_rows = media_checks[0].get("assets")
    if not isinstance(evidence_rows, list) or len(evidence_rows) != len(expected_assets):
        raise ValueError("App content UAT signed media coverage is incomplete")
    observed_assets: set[str] = set()
    observed_categories: set[str] = set()
    for row in evidence_rows:
        if not isinstance(row, Mapping):
            raise ValueError("App content UAT signed media evidence is invalid")
        asset_id = str(row.get("assetId") or "")
        expected = expected_assets.get(asset_id)
        categories = row.get("classifications")
        if (
            expected is None
            or asset_id in observed_assets
            or row.get("statusCode") != 200
            or row.get("kind") != expected.get("kind")
            or row.get("bytes") != expected.get("expectedBytes")
            or row.get("sha256") != expected.get("expectedSha256")
            or row.get("mimeType") != expected.get("expectedMimeType")
            or row.get("hashVerified") is not True
            or categories != expected.get("classifications")
            or (
                expected.get("requireRange") is True
                and (
                    row.get("rangeRequested") is not True
                    or row.get("rangeStatusCode") != 206
                    or not str(row.get("contentRange") or "").startswith("bytes 0-")
                    or not isinstance(row.get("rangeBytes"), int)
                    or row.get("rangeBytes", 0) <= 0
                )
            )
        ):
            raise ValueError(
                f"App content UAT signed media {asset_id or '<unknown>'} evidence drifted"
            )
        observed_assets.add(asset_id)
        observed_categories.update(str(value) for value in categories or [])
    required_categories = {"avatar", "image", "typed_video", "premium_video"}
    if observed_categories != required_categories:
        raise ValueError("App content UAT signed media classifications are incomplete")
    return {
        "creatorProfileCount": len(observed_profiles),
        "signedMediaAssetCount": len(observed_assets),
        "classifications": sorted(observed_categories),
    }


def validate_release_sample_probe(
    *,
    report: Mapping[str, Any],
    resolved: Mapping[str, Any],
    app_uat_plan_digest: str,
    readiness_receipt_digest: str,
) -> dict[str, Any]:
    """Return compact per-sample evidence only after 100 exact HTTP reads pass."""

    expected = resolved.get("samples")
    if not isinstance(expected, list) or not expected:
        raise ValueError("App content UAT resolved sample set is incomplete")
    expected_by_id = {str(row["sampleId"]): row for row in expected if isinstance(row, Mapping)}
    raw_checks = report.get("checks")
    if report.get("status") != "passed" or not isinstance(raw_checks, list):
        raise ValueError("App content UAT release sample probe did not pass")
    checks = [
        row
        for row in raw_checks
        if isinstance(row, Mapping) and row.get("name") == "release_sample"
    ]
    if len(checks) != len(expected):
        raise ValueError(
            f"App content UAT release sample probe did not execute {len(expected)} reads"
        )

    evidence: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    for check in checks:
        sample_id = str(check.get("sampleId") or "").strip()
        sample = expected_by_id.get(sample_id)
        if sample is None or sample_id in observed_ids:
            raise ValueError("App content UAT release sample execution identity drifted")
        observed_ids.add(sample_id)
        expected_fields = {
            "carrier": sample["carrier"],
            "sourceObjectId": sample["sourceObjectId"],
            "readObjectId": sample["readObjectId"],
            "expectedContentType": sample["expectedContentType"],
            "returnedObjectId": sample["readObjectId"],
            "returnedContentType": sample["expectedContentType"],
        }
        if (
            check.get("ok") is not True
            or check.get("statusCode") != 200
            or any(check.get(field) != value for field, value in expected_fields.items())
            or not str(check.get("url") or "").strip()
            or not str(check.get("responseDigest") or "").startswith("sha256:")
            or not isinstance(check.get("responseBytes"), int)
            or int(check["responseBytes"]) <= 0
        ):
            raise ValueError(f"App content UAT release sample {sample_id} read evidence drifted")
        evidence.append(
            {
                "sampleId": sample_id,
                "carrier": sample["carrier"],
                "sourceObjectId": sample["sourceObjectId"],
                "readObjectId": sample["readObjectId"],
                "statusCode": 200,
                "returnedObjectId": check["returnedObjectId"],
                "returnedContentType": check["returnedContentType"],
                "responseDigest": check["responseDigest"],
                "responseBytes": check["responseBytes"],
            }
        )
    if observed_ids != set(expected_by_id):
        raise ValueError("App content UAT release sample execution coverage is incomplete")
    distribution = dict(Counter(str(row["carrier"]) for row in evidence))
    milestone = str(resolved.get("milestone") or "")
    if milestone and distribution != _DISTRIBUTIONS.get(milestone):
        raise ValueError("App content UAT release sample evidence distribution drifted")
    evidence.sort(key=lambda row: str(row["sampleId"]))
    return {
        "milestone": milestone,
        "executedSampleCount": len(evidence),
        "distribution": distribution,
        "releaseUatSamplePlanRef": resolved["releaseUatSamplePlanRef"],
        "releaseUatSamplePlanDigest": resolved["releaseUatSamplePlanDigest"],
        "appUatPlanDigest": app_uat_plan_digest,
        "readinessReceiptDigest": readiness_receipt_digest,
        "readinessReceiptRef": resolved["readinessReceiptRef"],
        "readinessReceiptFileSha256": resolved["readinessReceiptFileSha256"],
        "homepageApiVerificationRef": resolved["homepageApiVerificationRef"],
        "homepageApiVerificationFileSha256": resolved[
            "homepageApiVerificationFileSha256"
        ],
        "contentImportReportRef": resolved["contentImportReportRef"],
        "contentImportReportFileSha256": resolved[
            "contentImportReportFileSha256"
        ],
        "samples": evidence,
    }


__all__ = [
    "document_digest",
    "resolve_release_sample_requests",
    "validate_release_sample_probe",
    "validate_release_strict_probe",
]
