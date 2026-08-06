import 'package:quwoquan_app/runtime/errors/generated/entity/entity_errors.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_contract_projection.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_facets.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_write_target_reader.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 将 pure-contract Homepage facets 投影为 App 页面 DTO。
///
/// 它不包含 transport、fixture 或运行环境分支；四环境统一注入 Remote facets，
/// local_contract 可在测试树内覆盖 typed port。页面始终只消费
/// [HomepageQuery] / [HomepageCommandWriter]。
class HomepageFacetProjectionAdapter
    implements HomepageFacetSet, HomepageWriteTargetReader {
  HomepageFacetProjectionAdapter({
    required this.query,
    required this.candidateWriter,
  });

  final HomepageQueryFacet query;
  final HomepageCandidateCommandWriter candidateWriter;

  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = HomepageSearchQuery.defaultLimit,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final page = await _execute(
      () => this.query.searchHomepages(
        HomepageSearchQuery(
          query: query,
          homepageType: homepageType,
          city: city,
          status: status,
          limit: limit,
        ),
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      ),
    );
    return page.items.map(homepageSummaryFromContract).toList(growable: false);
  }

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    return homepageDetailFromContract(
      await _execute(() => query.getHomepageDetail(homepageId)),
    );
  }

  @override
  Future<HomepageWriteTarget> getHomepageWriteTarget(String homepageId) async {
    final detail = await getHomepageDetail(homepageId);
    return HomepageWriteTarget(
      homepageId: detail.id,
      title: detail.title,
      status: detail.status ?? '',
      claimStatus: detail.claimStatus,
    );
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    return homepageShellFromContract(
      await _execute(() => query.getHomepageShell(homepageId)),
    );
  }

  @override
  Future<ObjectPageBundle> getObjectPageBundle(
    String homepageId, {
    String referralSource = '',
    String feedRequestId = '',
    String recommendationTraceId = '',
    String experimentBucket = '',
    String rolloutCohort = '',
  }) async {
    return objectPageBundleFromContract(
      await _execute(
        () => query.getObjectPageBundle(
          HomepageObjectPageBundleQuery(
            homepageId: homepageId,
            referralSource: referralSource,
            feedRequestId: feedRequestId,
            recommendationTraceId: recommendationTraceId,
            experimentBucket: experimentBucket,
            rolloutCohort: rolloutCohort,
          ),
        ),
      ),
    );
  }

  @override
  Future<HomepageReviewSummaryData> getHomepageReviewSummary(
    String homepageId,
  ) async {
    return homepageReviewSummaryFromContract(
      await _execute(() => query.getHomepageReviewSummary(homepageId)),
    );
  }

  @override
  Future<EntityImpactSummary> getEntityImpact(String homepageId) async {
    return homepageImpactFromContract(
      await _execute(() => query.getEntityImpact(homepageId)),
    );
  }

  @override
  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    return homepageRelatedGroupsFromContract(
      await _execute(() => query.getHomepageRelatedGroups(homepageId)),
    );
  }

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final projection = await _execute(
      () => candidateWriter.suggest(
        SuggestHomepageCandidateCommand(
          title: draft.title,
          homepageType: draft.homepageType,
          subtitle: draft.subtitle,
          categoryTags: draft.categoryTags,
          coverUrl: draft.coverUrl,
          address: draft.address,
          city: draft.city,
          sourcePlaceId: draft.sourcePlaceId,
          location: _geoPointInput(draft.location),
        ),
      ),
    );
    return homepageDetailFromContract(projection);
  }

  @override
  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  }) async {
    final projection = await _execute(
      () => candidateWriter.updateClaimedBasics(
        UpdateClaimedHomepageBasicsCommand(
          homepageId: homepageId,
          title: draft.title,
          subtitle: draft.subtitle,
          categoryTags: draft.categoryTags,
          coverUrl: draft.coverUrl,
          address: draft.address,
          city: draft.city,
          location: _geoPointInput(draft.location),
        ),
      ),
    );
    return homepageDetailFromContract(projection);
  }

  Future<T> _execute<T>(Future<T> Function() operation) async {
    try {
      return await operation();
    } on HomepageQueryNotFoundException catch (error) {
      throw _homepageNotFoundCloudException(error);
    }
  }
}

HomepageGeoPointInput? _geoPointInput(HomepageGeoPoint? location) {
  if (location == null) return null;
  return HomepageGeoPointInput(lat: location.latitude, lng: location.longitude);
}

CloudException _homepageNotFoundCloudException(
  HomepageQueryNotFoundException error,
) {
  final code = EntityErrorCode.homepageNotFound;
  final failure = RuntimeFailure(
    code: code.code,
    transportStatus: code.httpStatus,
    origin: RuntimeFailureOrigin.localClient,
    kind: RuntimeFailureKind.notFound,
    nature: RuntimeFailureNature.permanent,
    location: const RuntimeFailureLocation(
      businessObject: 'entity.homepage',
      functionModule: 'homepage_facet_projection_adapter',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'homepageId', value: error.homepageId),
      ],
    ),
    recovery: const RuntimeRecoveryDirective.none(),
  );
  return CloudException(
    type: CloudErrorType.notFound,
    message: code.defaultMessage,
    statusCode: code.httpStatus,
    code: code.code,
    domainErrorCode: DomainErrorCodeRegistry.fromCode(code.code),
    runtimeFailure: failure,
    userMessage: code.defaultMessage,
    cause: error,
  );
}
