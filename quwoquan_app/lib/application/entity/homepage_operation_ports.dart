import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Test adapters use this typed signal for the canonical homepage-not-found
/// error. Production adapters continue to surface the generated cloud error.
final class HomepageQueryNotFoundException implements Exception {
  const HomepageQueryNotFoundException(this.homepageId);

  final String homepageId;
}

abstract interface class HomepageQueryFacet {
  Future<HomepageSearchSlice> searchHomepages(
    HomepageSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });

  Future<HomepageDetailView> getHomepageDetail(String homepageId);

  Future<HomepageShellView> getHomepageShell(String homepageId);

  Future<ObjectPageBundle> getObjectPageBundle(
    HomepageObjectPageBundleQuery query,
  );

  Future<HomepageReviewSummaryView> getHomepageReviewSummary(
    String homepageId,
  );

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

abstract interface class HomepageClaimRequestCommandWriter {
  Future<HomepageClaimRequestView> createClaimRequest(
    CreateHomepageClaimRequestCommand command,
  );
}

abstract interface class HomepageStatusReportCommandWriter {
  Future<HomepageStatusReportView> createStatusReport(
    CreateHomepageStatusReportCommand command,
  );
}

