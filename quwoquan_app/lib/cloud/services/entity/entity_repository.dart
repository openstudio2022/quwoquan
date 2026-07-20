import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_contract_projection.dart';
import 'package:quwoquan_app/cloud/services/entity/remote/homepage_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'entity_introduction_repository.dart';
part 'entity_repository_remote.dart';

abstract interface class HomepageQuery {
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = CloudApiDefaults.pageLimit,
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

  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  });

  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  });

  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  });
}

/// Composition marker implemented by adapters that provide both narrow facets.
/// UI consumers must not depend on this combined capability.
abstract interface class HomepageFacetSet
    implements HomepageQuery, HomepageCommandWriter {}
