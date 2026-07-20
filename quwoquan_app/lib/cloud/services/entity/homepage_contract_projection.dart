import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

HomepageSummary homepageSummaryFromContract(
  HomepageSearchItemProjection source,
) {
  return HomepageSummary(
    id: source.homepageId,
    homepageType: source.homepageType,
    title: source.title,
    canonicalEntityId: source.canonicalEntityId,
    subtitle: source.subtitle,
    coverUrl: source.coverUrl,
    city: source.city,
    address: source.address,
    status: source.status,
    averageRating: source.averageRating,
    ratingCount: source.ratingCount,
  );
}

HomepageDetail homepageDetailFromContract(HomepageDetailProjection source) {
  return HomepageDetail.fromMap(<String, dynamic>{
    'homepageId': source.homepageId,
    'homepageType': source.homepageType,
    'title': source.title,
    'subtitle': source.subtitle,
    'coverUrl': source.coverUrl,
    'status': source.status,
    'canonicalEntityId': source.canonicalEntityId,
    'objectPageTemplate': source.objectPageTemplate,
    'sourceType': source.sourceType,
    'claimStatus': source.claimStatus,
    'categoryTags': source.categoryTags,
    'address': source.address,
    'city': source.city,
    'location': _optionalStructuredObjectToWire(source.location),
    'ownerUserId': source.ownerUserId,
    'ownerSubAccountId': source.ownerSubAccountId,
    'viewerFollowsHomepage': source.viewerFollowsHomepage,
    'followerCount': source.followerCount,
    'averageRating': source.averageRating,
    'ratingCount': source.ratingCount,
    'reviewSummary': _reviewSummaryToWire(source.reviewSummary),
    'contentPreview': source.contentPreview
        .map(_structuredObjectToWire)
        .toList(),
    'questionPreview': source.questionPreview
        .map(_structuredObjectToWire)
        .toList(),
    'relatedGroups': source.relatedGroups.map(_relatedGroupToWire).toList(),
    'createdAt': source.createdAt?.toIso8601String(),
    'updatedAt': source.updatedAt?.toIso8601String(),
    'publishedAt': source.publishedAt?.toIso8601String(),
    'offlineAt': source.offlineAt?.toIso8601String(),
  });
}

HomepageShellData homepageShellFromContract(HomepageShellProjection source) {
  return HomepageShellData.fromMap(<String, dynamic>{
    'homepage': _homepageDetailToWire(source.homepage),
    'reviewSummary': _reviewSummaryToWire(source.reviewSummary),
    'contentPreview': source.contentPreview
        .map(_structuredObjectToWire)
        .toList(),
    'questionPreview': source.questionPreview
        .map(_structuredObjectToWire)
        .toList(),
    'relatedGroups': source.relatedGroups.map(_relatedGroupToWire).toList(),
  });
}

HomepageIntroduction homepageIntroductionFromContract(
  HomepageIntroductionProjection source,
) {
  return HomepageIntroduction.fromMap(<String, dynamic>{
    'homepageId': source.homepageId,
    'displayName': source.displayName,
    'homepageType': source.homepageType,
    'coverUrl': source.coverUrl,
    'summary': source.summary,
    'sections': source.sections
        .map(
          (section) => <String, dynamic>{
            'kind': section.kind,
            'title': section.title,
            'bodyMarkdown': section.bodyMarkdown,
            'assets': section.assets
                .map(
                  (asset) => <String, dynamic>{
                    'assetId': asset.assetId,
                    'url': asset.url,
                    'caption': asset.caption,
                    'role': asset.role,
                    'sourceUrl': asset.sourceUrl,
                    'width': asset.width,
                    'height': asset.height,
                  },
                )
                .toList(),
            'timelineItems': section.timelineItems
                .map(
                  (item) => <String, dynamic>{
                    'dateLabel': item.dateLabel,
                    'text': item.text,
                  },
                )
                .toList(),
          },
        )
        .toList(),
    'relatedObjects': source.relatedObjects.map(_relatedGroupToWire).toList(),
    'primarySource': source.primarySource == null
        ? null
        : <String, dynamic>{
            'sourceKind': source.primarySource!.sourceKind,
            'sourceUrl': source.primarySource!.sourceUrl,
            'title': source.primarySource!.title,
            'fetchedAt': source.primarySource!.fetchedAt,
            'snapshotHash': source.primarySource!.snapshotHash,
            'policyRevision': source.primarySource!.policyRevision,
            'sourceUseMode': source.primarySource!.sourceUseMode,
          },
    'sourceUrls': source.sourceUrls,
    'updatedAt': source.updatedAt,
  });
}

ObjectPageBundle objectPageBundleFromContract(
  HomepageObjectPageBundleProjection source,
) {
  return ObjectPageBundle.fromMap(<String, dynamic>{
    'objectType': source.objectType,
    'objectId': source.objectId,
    'canonicalEntityId': source.canonicalEntityId,
    'title': source.title,
    'subtitle': source.subtitle,
    'coverUrl': source.coverUrl,
    'objectPageTemplate': source.objectPageTemplate,
    'tagRefs': source.tagRefs,
    'stats': _structuredObjectToWire(source.stats),
    'intersectionReasons': source.intersectionReasons
        .map(_structuredObjectToWire)
        .toList(),
    'highlightItems': source.highlightItems
        .map(_structuredObjectToWire)
        .toList(),
    'contentSections': _structuredObjectToWire(source.contentSections),
    'relatedObjects': source.relatedObjects.map(_relatedGroupToWire).toList(),
    'relationEdges': source.relationEdges.map(_structuredObjectToWire).toList(),
    'assistantContext': _optionalStructuredObjectToWire(
      source.assistantContext,
    ),
    'rolloutContext': _optionalStructuredObjectToWire(source.rolloutContext),
  });
}

HomepageReviewSummaryData homepageReviewSummaryFromContract(
  HomepageReviewSummaryProjection source,
) {
  return HomepageReviewSummaryData.fromMap(_reviewSummaryToWire(source)!);
}

List<HomepageRelatedGroupSummary> homepageRelatedGroupsFromContract(
  HomepageRelatedGroupsSlice source,
) {
  return source.groups
      .map(
        (group) =>
            HomepageRelatedGroupSummary.fromMap(_relatedGroupToWire(group)),
      )
      .toList(growable: false);
}

EntityImpactSummary homepageImpactFromContract(
  HomepageImpactSummaryProjection source,
) {
  return EntityImpactSummary.fromMap(<String, dynamic>{
    'homepageId': source.homepageId,
    'total': source.total,
    'items': source.items
        .map(
          (item) => <String, dynamic>{
            'helpType': item.helpType,
            'action': item.action,
            'intersectionDimension': item.intersectionDimension,
            'tagRef': item.tagRef,
            'source': item.source,
            'count': item.count,
            'primaryText': item.primaryText,
            'subtitleText': item.subtitleText,
            'impactId': item.impactId,
            'primarySpans': item.primarySpans
                .map(_structuredObjectToWire)
                .toList(),
            'sampleVisuals': item.sampleVisuals
                .map(_structuredObjectToWire)
                .toList(),
            'representativeActor': _optionalStructuredObjectToWire(
              item.representativeActor,
            ),
            'actionHints': item.actionHints
                .map(_structuredObjectToWire)
                .toList(),
            'countTarget': _optionalStructuredObjectToWire(item.countTarget),
            'evidenceSnapshotId': item.evidenceSnapshotId,
            'countObjectKind': item.countObjectKind,
            'propagationPath': _optionalStructuredObjectToWire(
              item.propagationPath,
            ),
            'iconKey': item.iconKey,
          },
        )
        .toList(),
  });
}

Map<String, dynamic> _homepageDetailToWire(HomepageDetailProjection source) {
  return <String, dynamic>{
    'homepageId': source.homepageId,
    'homepageType': source.homepageType,
    'title': source.title,
    'subtitle': source.subtitle,
    'coverUrl': source.coverUrl,
    'status': source.status,
    'canonicalEntityId': source.canonicalEntityId,
    'objectPageTemplate': source.objectPageTemplate,
    'sourceType': source.sourceType,
    'claimStatus': source.claimStatus,
    'categoryTags': source.categoryTags,
    'address': source.address,
    'city': source.city,
    'location': _optionalStructuredObjectToWire(source.location),
    'ownerUserId': source.ownerUserId,
    'ownerSubAccountId': source.ownerSubAccountId,
    'viewerFollowsHomepage': source.viewerFollowsHomepage,
    'followerCount': source.followerCount,
    'averageRating': source.averageRating,
    'ratingCount': source.ratingCount,
    'reviewSummary': _reviewSummaryToWire(source.reviewSummary),
    'contentPreview': source.contentPreview
        .map(_structuredObjectToWire)
        .toList(),
    'questionPreview': source.questionPreview
        .map(_structuredObjectToWire)
        .toList(),
    'relatedGroups': source.relatedGroups.map(_relatedGroupToWire).toList(),
    'createdAt': source.createdAt?.toIso8601String(),
    'updatedAt': source.updatedAt?.toIso8601String(),
    'publishedAt': source.publishedAt?.toIso8601String(),
    'offlineAt': source.offlineAt?.toIso8601String(),
  };
}

Map<String, dynamic>? _reviewSummaryToWire(
  HomepageReviewSummaryProjection? source,
) {
  if (source == null) return null;
  return <String, dynamic>{
    'averageRating': source.averageRating,
    'ratingCount': source.ratingCount,
    'highlightTags': source.highlightTags,
  };
}

Map<String, dynamic> _relatedGroupToWire(
  HomepageRelatedGroupProjection source,
) {
  return <String, dynamic>{
    'circleId': source.circleId,
    'name': source.name,
    'memberCount': source.memberCount,
    'linkedHomepageId': source.linkedHomepageId,
    'linkedHomepageTitle': source.linkedHomepageTitle,
    'ownerUserId': source.ownerUserId,
    'ownerDisplayNameSnapshot': source.ownerDisplayNameSnapshot,
    'ownerAvatarUrlSnapshot': source.ownerAvatarUrlSnapshot,
    'evidenceSnapshotId': source.evidenceSnapshotId,
  };
}

Map<String, dynamic>? _optionalStructuredObjectToWire(
  CloudStructuredObject? source,
) {
  return source == null ? null : _structuredObjectToWire(source);
}

Map<String, dynamic> _structuredObjectToWire(CloudStructuredObject source) {
  return source.fields.map(
    (key, value) => MapEntry(key, _structuredValueToWire(value)),
  );
}

Object? _structuredValueToWire(CloudStructuredValue value) {
  return switch (value) {
    CloudStructuredObject() => _structuredObjectToWire(value),
    CloudStructuredArray() => value.values.map(_structuredValueToWire).toList(),
    CloudStructuredText() => value.value,
    CloudStructuredNumber() => value.value,
    CloudStructuredBoolean() => value.value,
    CloudStructuredNull() => null,
  };
}
