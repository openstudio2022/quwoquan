part of 'entity_repository.dart';

class RemoteHomepageRepository implements HomepageRepository {
  RemoteHomepageRepository({
    required this.queryAdapter,
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final RemoteHomepageQueryAdapter queryAdapter;
  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Map<String, String> _headersForSurface(
    AppUiSurface surface, {
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: surface.id,
      routeId: surface.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  String _contextForSurface(
    AppUiSurface surface, {
    required String operationId,
  }) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: surface.id,
      operationId: operationId,
    );
  }

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
  Future<HomepageDetail> followHomepage(String homepageId) async {
    final decoded = await _httpClient.postJson(
      _uri(EntityApiMetadata.followHomepagePath(homepageId: homepageId)),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.followHomepageOperation,
        clientPageId: EntityRequestPageIds.followHomepage,
      ),
      body: const <String, Object?>{},
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.followHomepageOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageDetail> unfollowHomepage(String homepageId) async {
    final decoded = await _httpClient.deleteJson(
      _uri(EntityApiMetadata.unfollowHomepagePath(homepageId: homepageId)),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.unfollowHomepageOperation,
        clientPageId: EntityRequestPageIds.unfollowHomepage,
      ),
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.unfollowHomepageOperation,
        ),
      ),
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
  Future<HomepageDetail> intakeHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final decoded = await _httpClient.postJson(
      _uri(EntityApiMetadata.intakeHomepageCandidatePath),
      headers: _headersForSurface(
        AppUiSurfaces.homepagePicker,
        operationId: EntityApiMetadata.intakeHomepageCandidateOperation,
        clientPageId: EntityRequestPageIds.intakeHomepageCandidate,
      ),
      body: draft.toMap(),
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepagePicker,
          operationId: EntityApiMetadata.intakeHomepageCandidateOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final decoded = await _httpClient.postJson(
      _uri(EntityApiMetadata.suggestHomepageCandidatePath),
      headers: _headersForSurface(
        AppUiSurfaces.suggestHomepage,
        operationId: EntityApiMetadata.suggestHomepageCandidateOperation,
        clientPageId: EntityRequestPageIds.suggestHomepageCandidate,
      ),
      body: draft.toMap(),
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.suggestHomepage,
          operationId: EntityApiMetadata.suggestHomepageCandidateOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageDetail> publishHomepageCandidate(String homepageId) async {
    final decoded = await _httpClient.postJson(
      _uri(
        EntityApiMetadata.publishHomepageCandidatePath(homepageId: homepageId),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepagePicker,
        operationId: EntityApiMetadata.publishHomepageCandidateOperation,
        clientPageId: EntityRequestPageIds.publishHomepageCandidate,
      ),
      body: PublishHomepageCandidateWire().toWire(),
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepagePicker,
          operationId: EntityApiMetadata.publishHomepageCandidateOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    final decoded = await _httpClient.postJson(
      _uri(
        EntityApiMetadata.createHomepageClaimRequestPath(
          homepageId: homepageId,
        ),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageClaim,
        operationId: EntityApiMetadata.createHomepageClaimRequestOperation,
        clientPageId: EntityRequestPageIds.createHomepageClaimRequest,
      ),
      body: draft.toMap(),
    );
    return HomepageClaimRequestRecord.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageClaim,
          operationId: EntityApiMetadata.createHomepageClaimRequestOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageClaimRequestRecord> reviewHomepageClaimRequest({
    required String homepageId,
    required String claimRequestId,
    required String status,
    String? reviewNote,
  }) async {
    final decoded = await _httpClient.postJson(
      _uri(
        EntityApiMetadata.reviewHomepageClaimRequestPath(
          homepageId: homepageId,
          claimRequestId: claimRequestId,
        ),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageClaim,
        operationId: EntityApiMetadata.reviewHomepageClaimRequestOperation,
        clientPageId: EntityRequestPageIds.reviewHomepageClaimRequest,
      ),
      body: ReviewHomepageClaimRequestWire(
        status: status,
        reviewNote: (reviewNote != null && reviewNote.isNotEmpty)
            ? reviewNote
            : null,
      ).toWire(),
    );
    return HomepageClaimRequestRecord.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageClaim,
          operationId: EntityApiMetadata.reviewHomepageClaimRequestOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  }) async {
    final decoded = await _httpClient.patchJson(
      _uri(
        EntityApiMetadata.updateClaimedHomepageBasicsPath(
          homepageId: homepageId,
        ),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageMaintenance,
        operationId: EntityApiMetadata.updateClaimedHomepageBasicsOperation,
        clientPageId: EntityRequestPageIds.updateClaimedHomepageBasics,
      ),
      body: draft.toMap(),
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageMaintenance,
          operationId: EntityApiMetadata.updateClaimedHomepageBasicsOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    final decoded = await _httpClient.postJson(
      _uri(
        EntityApiMetadata.createHomepageStatusReportPath(
          homepageId: homepageId,
        ),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageStatusReport,
        operationId: EntityApiMetadata.createHomepageStatusReportOperation,
        clientPageId: EntityRequestPageIds.createHomepageStatusReport,
      ),
      body: draft.toMap(),
    );
    return HomepageStatusReportRecord.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageStatusReport,
          operationId: EntityApiMetadata.createHomepageStatusReportOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageStatusReportRecord> reviewHomepageStatusReport({
    required String homepageId,
    required String reportId,
    required String status,
    String? reviewNote,
  }) async {
    final decoded = await _httpClient.postJson(
      _uri(
        EntityApiMetadata.reviewHomepageStatusReportPath(
          homepageId: homepageId,
          reportId: reportId,
        ),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageStatusReport,
        operationId: EntityApiMetadata.reviewHomepageStatusReportOperation,
        clientPageId: EntityRequestPageIds.reviewHomepageStatusReport,
      ),
      body: ReviewHomepageStatusReportWire(
        status: status,
        reviewNote: (reviewNote != null && reviewNote.isNotEmpty)
            ? reviewNote
            : null,
      ).toWire(),
    );
    return HomepageStatusReportRecord.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageStatusReport,
          operationId: EntityApiMetadata.reviewHomepageStatusReportOperation,
        ),
      ),
    );
  }
}
