"""Per-target quota and source-asset reuse checks for content plans."""
from __future__ import annotations

from typing import Any, Mapping


def validate_per_target_quotas(
    *,
    per_entity: Mapping[str, Mapping[str, list[Mapping[str, Any]]]],
    per_target_articles: int,
    per_target_images: int,
    per_target_videos: int,
    separated_research: bool,
    required_article_intents: list[str],
) -> list[str]:
    issues: list[str] = []
    for target, buckets in per_entity.items():
        articles = buckets["article"]
        image_works = buckets["image"]
        video_works = buckets["video"]
        if per_target_articles:
            if len(articles) > per_target_articles:
                issues.append(
                    f"{target}: entityArticlesPerTarget ceiling {per_target_articles} "
                    f"but packet has {len(articles)}"
                )
            elif len(articles) < per_target_articles:
                issues.append(
                    f"{target}: entityArticlesPerTarget quota {per_target_articles} "
                    f"but packet has {len(articles)}"
                )
        if per_target_images:
            if len(image_works) > per_target_images:
                issues.append(
                    f"{target}: imageWorksPerTarget ceiling {per_target_images} "
                    f"but packet has {len(image_works)}"
                )
            elif len(image_works) < per_target_images:
                issues.append(
                    f"{target}: imageWorksPerTarget quota {per_target_images} "
                    f"but packet has {len(image_works)}"
                )
        if per_target_videos and len(video_works) != per_target_videos:
            issues.append(
                f"{target}: videoWorksPerTarget quota {per_target_videos} "
                f"but packet has {len(video_works)}"
            )
        if (
            not separated_research
            and required_article_intents
            and per_target_articles == len(required_article_intents)
        ):
            intents = sorted(str(item.get("writingIntent") or "") for item in articles)
            expected = sorted(required_article_intents)
            if intents != expected:
                issues.append(
                    f"{target}: entity articles must match acceptance.requiredAngles "
                    f"{expected}, got {intents}"
                )
        if len(image_works) > 1:
            collection_asset_sets: dict[str, set[str]] = {}
            for image_work in image_works:
                collection = str(image_work.get("sourceCollectionId") or "")
                assets = {str(asset) for asset in (image_work.get("assetRefs") or [])}
                previous = collection_asset_sets.setdefault(collection, set())
                if previous & assets:
                    issues.append(
                        f"{target}: image works reuse assets from collection {collection!r}"
                    )
                previous.update(assets)
    return issues


__all__ = ["validate_per_target_quotas"]
