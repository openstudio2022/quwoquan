import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class HomepageQuery {
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = HomepageSearchQuery.defaultLimit,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });

  Future<HomepageDetail> getHomepageDetail(String homepageId);

  Future<HomepageShellData> getHomepageShell(String homepageId);

  Future<ObjectPageBundle> getObjectPageBundle(
    String homepageId, {
    String referralSource = '',
    String feedRequestId = '',
    String recommendationTraceId = '',
    String experimentBucket = '',
    String rolloutCohort = '',
  });

  Future<HomepageReviewSummaryData> getHomepageReviewSummary(String homepageId);

  Future<EntityImpactSummary> getEntityImpact(String homepageId);

  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  );
}

abstract interface class HomepageCommandWriter {
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  });

  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  });
}

/// Composition marker implemented by adapters that provide both narrow facets.
/// UI consumers must not depend on this combined capability.
abstract interface class HomepageFacetSet
    implements HomepageQuery, HomepageCommandWriter {}
