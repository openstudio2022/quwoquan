part of 'entity_repository.dart';

typedef HomepageCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      AppUiSurface surface,
    );

/// Production-only adapter：查询经 RemoteHomepageQueryAdapter，
/// 写操作经 generated typed client；无裸 HTTP、无 fixture 回退。
class RemoteHomepageRepository implements HomepageFacetSet {
  factory RemoteHomepageRepository({
    required RemoteHomepageQueryAdapter queryAdapter,
    required GeneratedCloudOperationClient client,
    required HomepageCommandInvocationContextFactory commandContext,
  }) {
    return RemoteHomepageRepository._(queryAdapter, client, commandContext);
  }

  RemoteHomepageRepository._(
    this.queryAdapter,
    this._client,
    this._commandContext,
  );

  final RemoteHomepageQueryAdapter queryAdapter;
  final GeneratedCloudOperationClient _client;
  final HomepageCommandInvocationContextFactory _commandContext;

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
    final page = await queryAdapter.searchHomepages(
      HomepageSearchQuery(
        query: query,
        homepageType: homepageType,
        city: city,
        status: status,
        limit: limit,
      ),
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    return page.items.map(homepageSummaryFromContract).toList(growable: false);
  }

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    return homepageDetailFromContract(
      await queryAdapter.getHomepageDetail(homepageId),
    );
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    return homepageShellFromContract(
      await queryAdapter.getHomepageShell(homepageId),
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
      await queryAdapter.getObjectPageBundle(
        HomepageObjectPageBundleQuery(
          homepageId: homepageId,
          referralSource: referralSource,
          feedRequestId: feedRequestId,
          recommendationTraceId: recommendationTraceId,
          experimentBucket: experimentBucket,
          rolloutCohort: rolloutCohort,
        ),
      ),
    );
  }

  @override
  Future<HomepageReviewSummaryData> getHomepageReviewSummary(
    String homepageId,
  ) async {
    return homepageReviewSummaryFromContract(
      await queryAdapter.getHomepageReviewSummary(homepageId),
    );
  }

  @override
  Future<EntityImpactSummary> getEntityImpact(String homepageId) async {
    return homepageImpactFromContract(
      await queryAdapter.getEntityImpact(homepageId),
    );
  }

  @override
  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    return homepageRelatedGroupsFromContract(
      await queryAdapter.getHomepageRelatedGroups(homepageId),
    );
  }

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final projection = await _client.entityHomepageSuggestHomepageCandidate(
      SuggestHomepageCandidateCommand(
        title: draft.title,
        homepageType: draft.homepageType,
        subtitle: draft.subtitle,
        categoryTags: draft.categoryTags,
        coverUrl: draft.coverUrl,
        address: draft.address,
        city: draft.city,
        location: _geoPointInput(draft.location),
      ),
      context: _commandContext(
        EntityRequestPageIds.suggestHomepageCandidate,
        AppUiSurfaces.suggestHomepage,
      ),
    );
    return homepageDetailFromContract(projection);
  }

  @override
  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    final view = await _client
        .entityHomepageClaimRequestCreateHomepageClaimRequest(
          CreateHomepageClaimRequestCommand(
            homepageId: homepageId,
            claimTier: draft.claimTier,
            businessLicenseUrl: draft.businessLicenseUrl,
            contactPhone: draft.contactPhone,
            identityCardFrontUrl: draft.identityCardFrontUrl,
            identityCardBackUrl: draft.identityCardBackUrl,
            note: draft.note,
          ),
          context: _commandContext(
            EntityRequestPageIds.createHomepageClaimRequest,
            AppUiSurfaces.homepageClaim,
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
    final projection = await _client.entityHomepageUpdateClaimedHomepageBasics(
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
      context: _commandContext(
        EntityRequestPageIds.updateClaimedHomepageBasics,
        AppUiSurfaces.homepageMaintenance,
      ),
    );
    return homepageDetailFromContract(projection);
  }

  @override
  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    final view = await _client
        .entityHomepageStatusReportCreateHomepageStatusReport(
          CreateHomepageStatusReportCommand(
            homepageId: homepageId,
            reason: draft.reason,
            description: draft.description,
            evidenceUrls: draft.evidenceUrls,
          ),
          context: _commandContext(
            EntityRequestPageIds.createHomepageStatusReport,
            AppUiSurfaces.homepageStatusReport,
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
}

HomepageGeoPointInput? _geoPointInput(HomepageGeoPoint? location) {
  if (location == null) return null;
  return HomepageGeoPointInput(lat: location.latitude, lng: location.longitude);
}
