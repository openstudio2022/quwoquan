part of 'entity_repository.dart';

/// 将 pure-contract Homepage facets 投影为 App 页面 DTO。
///
/// 它不包含 transport、fixture 或运行环境分支，因此 production 可注入 Remote
/// facets，alpha/test 则在 production 图外注入 `quwoquan_cloud_mock` 的 typed
/// adapter。页面始终只消费 [HomepageQuery] / [HomepageCommandWriter]。
class HomepageFacetProjectionAdapter implements HomepageFacetSet {
  HomepageFacetProjectionAdapter({
    required this.query,
    required this.candidateWriter,
    required this.claimRequestWriter,
    required this.statusReportWriter,
  });

  final HomepageQueryFacet query;
  final HomepageCandidateCommandWriter candidateWriter;
  final HomepageClaimRequestCommandWriter claimRequestWriter;
  final HomepageStatusReportCommandWriter statusReportWriter;

  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = CloudApiDefaults.pageLimit,
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
  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    final view = await _execute(
      () => claimRequestWriter.createClaimRequest(
        CreateHomepageClaimRequestCommand(
          homepageId: homepageId,
          claimTier: draft.claimTier,
          businessLicenseUrl: draft.businessLicenseUrl,
          contactPhone: draft.contactPhone,
          identityCardFrontUrl: draft.identityCardFrontUrl,
          identityCardBackUrl: draft.identityCardBackUrl,
          note: draft.note,
        ),
      ),
    );
    return HomepageClaimRequestRecord(
      id: view.claimRequestId,
      homepageId: view.homepageId,
      requesterPersonaId: view.requesterPersonaId,
      claimTier: view.claimTier,
      status: view.status,
      reviewNote: view.reviewNote,
      createdAt: view.createdAt,
      reviewedAt: view.reviewedAt,
    );
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

  @override
  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    final view = await _execute(
      () => statusReportWriter.createStatusReport(
        CreateHomepageStatusReportCommand(
          homepageId: homepageId,
          reason: draft.reason,
          description: draft.description,
          evidenceUrls: draft.evidenceUrls,
        ),
      ),
    );
    return HomepageStatusReportRecord(
      id: view.reportId,
      homepageId: view.homepageId,
      reporterPersonaId: view.reporterPersonaId,
      reason: view.reason,
      status: view.status,
      description: view.description,
      evidenceUrls: view.evidenceUrls,
      reviewNote: view.reviewNote,
      createdAt: view.createdAt,
      reviewedAt: view.reviewedAt,
    );
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
