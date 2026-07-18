import '../structured_value.dart';

final class HomepageSearchItemProjection {
  const HomepageSearchItemProjection({
    required this.homepageId,
    required this.homepageType,
    required this.title,
    this.canonicalEntityId = '',
    this.subtitle,
    this.coverUrl,
    this.city,
    this.address,
    this.status = '',
    this.averageRating,
    this.ratingCount = 0,
  });

  final String homepageId;
  final String homepageType;
  final String title;
  final String canonicalEntityId;
  final String? subtitle;
  final String? coverUrl;
  final String? city;
  final String? address;
  final String status;
  final double? averageRating;
  final int ratingCount;
}

final class HomepageSearchSlice {
  HomepageSearchSlice({
    required Iterable<HomepageSearchItemProjection> items,
    this.nextCursor,
  }) : items = List<HomepageSearchItemProjection>.unmodifiable(items);

  final List<HomepageSearchItemProjection> items;
  final String? nextCursor;
}

final class HomepageReviewDimensionProjection {
  const HomepageReviewDimensionProjection({
    required this.label,
    required this.score,
  });

  final String label;
  final double score;
}

final class HomepageReviewSummaryProjection {
  HomepageReviewSummaryProjection({
    this.averageRating,
    this.ratingCount = 0,
    Iterable<String> highlightTags = const <String>[],
    Iterable<HomepageReviewDimensionProjection> dimensionScores =
        const <HomepageReviewDimensionProjection>[],
  }) : highlightTags = List<String>.unmodifiable(highlightTags),
       dimensionScores = List<HomepageReviewDimensionProjection>.unmodifiable(
         dimensionScores,
       );

  final double? averageRating;
  final int ratingCount;
  final List<String> highlightTags;
  final List<HomepageReviewDimensionProjection> dimensionScores;
}

final class HomepageRelatedGroupProjection {
  const HomepageRelatedGroupProjection({
    required this.circleId,
    required this.name,
    this.memberCount = 0,
    this.linkedHomepageId,
    this.linkedHomepageTitle,
    this.ownerUserId = '',
    this.ownerDisplayNameSnapshot = '',
    this.ownerAvatarUrlSnapshot = '',
    this.evidenceSnapshotId = '',
  });

  final String circleId;
  final String name;
  final int memberCount;
  final String? linkedHomepageId;
  final String? linkedHomepageTitle;
  final String ownerUserId;
  final String ownerDisplayNameSnapshot;
  final String ownerAvatarUrlSnapshot;
  final String evidenceSnapshotId;
}

final class HomepageRelatedGroupsSlice {
  HomepageRelatedGroupsSlice(Iterable<HomepageRelatedGroupProjection> groups)
    : groups = List<HomepageRelatedGroupProjection>.unmodifiable(groups);

  final List<HomepageRelatedGroupProjection> groups;
}

final class HomepageDetailProjection {
  HomepageDetailProjection({
    required this.homepageId,
    required this.homepageType,
    required this.title,
    this.subtitle,
    this.coverUrl,
    this.status = '',
    this.canonicalEntityId = '',
    this.objectPageTemplate = 'standard',
    this.sourceType,
    this.claimStatus,
    Iterable<String> categoryTags = const <String>[],
    this.address,
    this.city,
    this.location,
    this.ownerUserId,
    this.ownerSubAccountId,
    this.viewerFollowsHomepage = false,
    this.followerCount = 0,
    this.averageRating,
    this.ratingCount = 0,
    this.reviewSummary,
    Iterable<CloudStructuredObject> contentPreview =
        const <CloudStructuredObject>[],
    Iterable<CloudStructuredObject> questionPreview =
        const <CloudStructuredObject>[],
    Iterable<HomepageRelatedGroupProjection> relatedGroups =
        const <HomepageRelatedGroupProjection>[],
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.offlineAt,
  }) : categoryTags = List<String>.unmodifiable(categoryTags),
       contentPreview = List<CloudStructuredObject>.unmodifiable(
         contentPreview,
       ),
       questionPreview = List<CloudStructuredObject>.unmodifiable(
         questionPreview,
       ),
       relatedGroups = List<HomepageRelatedGroupProjection>.unmodifiable(
         relatedGroups,
       );

  final String homepageId;
  final String homepageType;
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final String status;
  final String canonicalEntityId;
  final String objectPageTemplate;
  final String? sourceType;
  final String? claimStatus;
  final List<String> categoryTags;
  final String? address;
  final String? city;
  final CloudStructuredObject? location;
  final String? ownerUserId;
  final String? ownerSubAccountId;
  final bool viewerFollowsHomepage;
  final int followerCount;
  final double? averageRating;
  final int ratingCount;
  final HomepageReviewSummaryProjection? reviewSummary;
  final List<CloudStructuredObject> contentPreview;
  final List<CloudStructuredObject> questionPreview;
  final List<HomepageRelatedGroupProjection> relatedGroups;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final DateTime? offlineAt;
}

final class HomepageShellProjection {
  HomepageShellProjection({
    required this.homepage,
    this.reviewSummary,
    Iterable<CloudStructuredObject> contentPreview =
        const <CloudStructuredObject>[],
    Iterable<CloudStructuredObject> questionPreview =
        const <CloudStructuredObject>[],
    Iterable<HomepageRelatedGroupProjection> relatedGroups =
        const <HomepageRelatedGroupProjection>[],
  }) : contentPreview = List<CloudStructuredObject>.unmodifiable(
         contentPreview,
       ),
       questionPreview = List<CloudStructuredObject>.unmodifiable(
         questionPreview,
       ),
       relatedGroups = List<HomepageRelatedGroupProjection>.unmodifiable(
         relatedGroups,
       );

  final HomepageDetailProjection homepage;
  final HomepageReviewSummaryProjection? reviewSummary;
  final List<CloudStructuredObject> contentPreview;
  final List<CloudStructuredObject> questionPreview;
  final List<HomepageRelatedGroupProjection> relatedGroups;
}

final class HomepageSourceProjection {
  const HomepageSourceProjection({
    this.sourceKind = '',
    this.sourceUrl = '',
    this.title = '',
    this.fetchedAt = '',
    this.snapshotHash = '',
    this.policyRevision = '',
    this.sourceUseMode = '',
  });

  final String sourceKind;
  final String sourceUrl;
  final String title;
  final String fetchedAt;
  final String snapshotHash;
  final String policyRevision;
  final String sourceUseMode;
}

final class HomepageIntroductionAssetProjection {
  const HomepageIntroductionAssetProjection({
    this.assetId = '',
    this.url = '',
    this.caption = '',
    this.role = '',
    this.sourceUrl = '',
    this.width,
    this.height,
  });

  final String assetId;
  final String url;
  final String caption;
  final String role;
  final String sourceUrl;
  final int? width;
  final int? height;
}

final class HomepageIntroductionTimelineProjection {
  const HomepageIntroductionTimelineProjection({
    this.dateLabel = '',
    this.text = '',
  });

  final String dateLabel;
  final String text;
}

final class HomepageIntroductionSectionProjection {
  HomepageIntroductionSectionProjection({
    this.kind = '',
    this.title = '',
    this.bodyMarkdown = '',
    Iterable<HomepageIntroductionAssetProjection> assets =
        const <HomepageIntroductionAssetProjection>[],
    Iterable<HomepageIntroductionTimelineProjection> timelineItems =
        const <HomepageIntroductionTimelineProjection>[],
  }) : assets = List<HomepageIntroductionAssetProjection>.unmodifiable(assets),
       timelineItems =
           List<HomepageIntroductionTimelineProjection>.unmodifiable(
             timelineItems,
           );

  final String kind;
  final String title;
  final String bodyMarkdown;
  final List<HomepageIntroductionAssetProjection> assets;
  final List<HomepageIntroductionTimelineProjection> timelineItems;
}

final class HomepageIntroductionProjection {
  HomepageIntroductionProjection({
    required this.homepageId,
    required this.displayName,
    required this.homepageType,
    this.coverUrl,
    this.summary = '',
    Iterable<HomepageIntroductionSectionProjection> sections =
        const <HomepageIntroductionSectionProjection>[],
    Iterable<HomepageRelatedGroupProjection> relatedObjects =
        const <HomepageRelatedGroupProjection>[],
    this.primarySource,
    Iterable<String> sourceUrls = const <String>[],
    this.updatedAt = '',
  }) : sections = List<HomepageIntroductionSectionProjection>.unmodifiable(
         sections,
       ),
       relatedObjects = List<HomepageRelatedGroupProjection>.unmodifiable(
         relatedObjects,
       ),
       sourceUrls = List<String>.unmodifiable(sourceUrls);

  final String homepageId;
  final String displayName;
  final String homepageType;
  final String? coverUrl;
  final String summary;
  final List<HomepageIntroductionSectionProjection> sections;
  final List<HomepageRelatedGroupProjection> relatedObjects;
  final HomepageSourceProjection? primarySource;
  final List<String> sourceUrls;
  final String updatedAt;
}

final class HomepageImpactItemProjection {
  HomepageImpactItemProjection({
    this.helpType = '',
    this.action = '',
    this.intersectionDimension = '',
    this.tagRef = '',
    this.source = '',
    this.count = 0,
    this.primaryText = '',
    this.subtitleText = '',
    this.impactId = '',
    Iterable<CloudStructuredObject> primarySpans =
        const <CloudStructuredObject>[],
    Iterable<CloudStructuredObject> sampleVisuals =
        const <CloudStructuredObject>[],
    this.representativeActor,
    Iterable<CloudStructuredObject> actionHints =
        const <CloudStructuredObject>[],
    this.countTarget,
    this.evidenceSnapshotId = '',
    this.countObjectKind = '',
    this.propagationPath,
    this.iconKey = '',
  }) : primarySpans = List<CloudStructuredObject>.unmodifiable(primarySpans),
       sampleVisuals = List<CloudStructuredObject>.unmodifiable(sampleVisuals),
       actionHints = List<CloudStructuredObject>.unmodifiable(actionHints);

  final String helpType;
  final String action;
  final String intersectionDimension;
  final String tagRef;
  final String source;
  final int count;
  final String primaryText;
  final String subtitleText;
  final String impactId;
  final List<CloudStructuredObject> primarySpans;
  final List<CloudStructuredObject> sampleVisuals;
  final CloudStructuredObject? representativeActor;
  final List<CloudStructuredObject> actionHints;
  final CloudStructuredObject? countTarget;
  final String evidenceSnapshotId;
  final String countObjectKind;
  final CloudStructuredObject? propagationPath;
  final String iconKey;
}

final class HomepageImpactSummaryProjection {
  HomepageImpactSummaryProjection({
    required this.homepageId,
    this.total = 0,
    Iterable<HomepageImpactItemProjection> items =
        const <HomepageImpactItemProjection>[],
  }) : items = List<HomepageImpactItemProjection>.unmodifiable(items);

  final String homepageId;
  final int total;
  final List<HomepageImpactItemProjection> items;
}

final class HomepageObjectPageBundleProjection {
  HomepageObjectPageBundleProjection({
    required this.objectType,
    required this.objectId,
    required this.canonicalEntityId,
    required this.title,
    this.subtitle,
    this.coverUrl,
    this.objectPageTemplate = 'standard',
    Iterable<String> tagRefs = const <String>[],
    CloudStructuredObject? stats,
    Iterable<CloudStructuredObject> intersectionReasons =
        const <CloudStructuredObject>[],
    Iterable<CloudStructuredObject> highlightItems =
        const <CloudStructuredObject>[],
    CloudStructuredObject? contentSections,
    Iterable<HomepageRelatedGroupProjection> relatedObjects =
        const <HomepageRelatedGroupProjection>[],
    Iterable<CloudStructuredObject> relationEdges =
        const <CloudStructuredObject>[],
    this.assistantContext,
    this.rolloutContext,
  }) : tagRefs = List<String>.unmodifiable(tagRefs),
       stats = stats ?? CloudStructuredObject(const {}),
       intersectionReasons = List<CloudStructuredObject>.unmodifiable(
         intersectionReasons,
       ),
       highlightItems = List<CloudStructuredObject>.unmodifiable(
         highlightItems,
       ),
       contentSections = contentSections ?? CloudStructuredObject(const {}),
       relatedObjects = List<HomepageRelatedGroupProjection>.unmodifiable(
         relatedObjects,
       ),
       relationEdges = List<CloudStructuredObject>.unmodifiable(relationEdges);

  final String objectType;
  final String objectId;
  final String canonicalEntityId;
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final String objectPageTemplate;
  final List<String> tagRefs;
  final CloudStructuredObject stats;
  final List<CloudStructuredObject> intersectionReasons;
  final List<CloudStructuredObject> highlightItems;
  final CloudStructuredObject contentSections;
  final List<HomepageRelatedGroupProjection> relatedObjects;
  final List<CloudStructuredObject> relationEdges;
  final CloudStructuredObject? assistantContext;
  final CloudStructuredObject? rolloutContext;
}
