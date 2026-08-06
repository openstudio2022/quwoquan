import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_search_reader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Test adapters use this typed signal for the canonical homepage-not-found
/// error. Production adapters continue to surface the generated cloud error.
final class HomepageQueryNotFoundException implements Exception {
  const HomepageQueryNotFoundException(this.homepageId);

  final String homepageId;
}

abstract interface class HomepageQueryFacet implements HomepageSearchReader {
  Future<HomepageDetailView> getHomepageDetail(String homepageId);

  Future<HomepageShellView> getHomepageShell(String homepageId);

  Future<ObjectPageBundle> getObjectPageBundle(
    HomepageObjectPageBundleQuery query,
  );

  Future<HomepageReviewSummaryView> getHomepageReviewSummary(String homepageId);

  Future<EntityImpactSummary> getEntityImpact(String homepageId);

  Future<HomepageRelatedGroupSummaryView> getHomepageRelatedGroups(
    String homepageId,
  );
}

abstract interface class HomepageIntroductionQuery {
  Future<HomepageIntroduction> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  });
}

abstract interface class HomepageCandidateCommandWriter {
  Future<HomepageDetailView> suggest(SuggestHomepageCandidateCommand command);

  Future<HomepageDetailView> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  );
}
