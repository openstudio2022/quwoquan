import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_entity_contracts.dart'
    as wire;

HomepageSummary homepageSummaryFromContract(
  wire.HomepageSearchItemView source,
) {
  return HomepageSummary(
    id: source.homepageId,
    homepageType: source.homepageType.wireName,
    title: source.title,
    canonicalEntityId: source.canonicalEntityId,
    subtitle: source.subtitle,
    coverUrl: source.coverUrl,
    city: source.city,
    address: source.address,
    status: source.status.wireName,
    averageRating: source.averageRating,
    ratingCount: source.ratingCount,
  );
}

HomepageDetail homepageDetailFromContract(wire.HomepageDetailView source) {
  return HomepageDetail(
    id: source.homepageId,
    homepageType: source.homepageType,
    title: source.title,
    subtitle: source.subtitle,
    coverUrl: source.coverUrl,
    status: source.status,
    claimStatus: source.claimStatus,
    categoryTags: source.categoryTags,
    address: source.address,
    city: source.city,
    location: source.location,
    ownerUserId: source.ownerUserId,
    ownerPersonaId: source.ownerPersonaId,
    viewerFollowsHomepage: source.viewerFollow.viewerFollowsHomepage,
    followerCount: source.viewerFollow.followerCount,
    verified: source.verified,
    establishedYear: source.establishedYear,
    averageRating: source.averageRating,
    ratingCount: source.ratingCount,
    reviewSummary: source.reviewSummary == null
        ? null
        : _reviewSummaryViewFromWire(source.reviewSummary!),
    contentPreview: source.contentPreview,
    questionPreview: source.questionPreview,
    relatedGroups: source.relatedGroups,
    createdAt: source.createdAt,
    updatedAt: source.updatedAt,
    publishedAt: source.publishedAt,
    offlineAt: source.offlineAt,
  );
}

HomepageShellData homepageShellFromContract(wire.HomepageShellView source) {
  return HomepageShellData(
    homepage: homepageDetailFromContract(source.homepage),
    reviewSummary: source.reviewSummary,
    contentPreview:
        source.contentPreview ?? const <wire.HomepageContentPreview>[],
    questionPreview:
        source.questionPreview ?? const <wire.HomepageQuestionPreview>[],
    relatedGroups:
        source.relatedGroups ?? const <wire.HomepageRelatedGroupSummary>[],
  );
}

HomepageIntroduction homepageIntroductionFromContract(
  wire.HomepageIntroduction source,
) => source;

ObjectPageBundle objectPageBundleFromContract(wire.ObjectPageBundle source) =>
    source;

HomepageReviewSummaryData homepageReviewSummaryFromContract(
  wire.HomepageReviewSummaryView source,
) {
  return _reviewSummaryViewFromWire(source);
}

List<HomepageRelatedGroupSummary> homepageRelatedGroupsFromContract(
  wire.HomepageRelatedGroupSummaryView source,
) {
  return source.groups ?? const <wire.HomepageRelatedGroupSummary>[];
}

EntityImpactSummary homepageImpactFromContract(
  wire.EntityImpactSummary source,
) => source;

HomepageReviewSummaryData _reviewSummaryViewFromWire(
  wire.HomepageReviewSummaryView source,
) {
  return HomepageReviewSummaryData(
    averageRating: source.averageRating,
    ratingCount: source.ratingCount,
    highlightTags: source.highlightTags ?? const <String>[],
  );
}
