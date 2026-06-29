part of 'entity_repository.dart';

class RemoteHomepageRepository implements HomepageRepository {
  RemoteHomepageRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

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
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(
        EntityApiMetadata.searchHomepagesPath,
        queryParameters: <String, String>{
          'query': query,
          if (homepageType != null && homepageType.isNotEmpty)
            'homepageType': homepageType,
          if (city != null && city.isNotEmpty) 'city': city,
          if (status != null && status.isNotEmpty) 'status': status,
          'limit': '$limit',
        },
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepagePicker,
        operationId: EntityApiMetadata.searchHomepagesOperation,
        clientPageId: EntityRequestPageIds.searchHomepages,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.homepagePicker,
        operationId: EntityApiMetadata.searchHomepagesOperation,
      ),
    );
    return page.items.map(HomepageSummary.fromMap).toList(growable: false);
  }

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final decoded = await _httpClient.getJson(
      _uri(EntityApiMetadata.getHomepageDetailPath(homepageId: homepageId)),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageDetailOperation,
        clientPageId: EntityRequestPageIds.getHomepageDetail,
      ),
    );
    return HomepageDetail.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.getHomepageDetailOperation,
        ),
      ),
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
    final decoded = await _httpClient.getJson(
      _uri(EntityApiMetadata.getHomepageShellPath(homepageId: homepageId)),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageShellOperation,
        clientPageId: EntityRequestPageIds.getHomepageShell,
      ),
    );
    return HomepageShellData.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.getHomepageShellOperation,
        ),
      ),
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
    final decoded = await _httpClient.getJson(
      _uri(
        EntityApiMetadata.getObjectPageBundlePath(homepageId: homepageId),
        queryParameters: <String, String>{
          if (referralSource.isNotEmpty) 'referralSource': referralSource,
          if (feedRequestId.isNotEmpty) 'feedRequestId': feedRequestId,
          if (recommendationTraceId.isNotEmpty)
            'recommendationTraceId': recommendationTraceId,
          if (experimentBucket.isNotEmpty) 'experimentBucket': experimentBucket,
          if (rolloutCohort.isNotEmpty) 'rolloutCohort': rolloutCohort,
        },
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getObjectPageBundleOperation,
        clientPageId: EntityRequestPageIds.getObjectPageBundle,
      ),
    );
    return ObjectPageBundle.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.getObjectPageBundleOperation,
        ),
      ),
    );
  }

  @override
  Future<HomepageReviewSummaryData> getHomepageReviewSummary(
    String homepageId,
  ) async {
    final decoded = await _httpClient.getJson(
      _uri(
        EntityApiMetadata.getHomepageReviewSummaryPath(homepageId: homepageId),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageReviewSummaryOperation,
        clientPageId: EntityRequestPageIds.getHomepageReviewSummary,
      ),
    );
    return HomepageReviewSummaryData.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.getHomepageReviewSummaryOperation,
        ),
      ),
    );
  }

  @override
  Future<EntityImpactSummary> getEntityImpact(String homepageId) async {
    final decoded = await _httpClient.getJson(
      _uri(EntityApiMetadata.getEntityImpactPath(homepageId: homepageId)),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getEntityImpactOperation,
        clientPageId: EntityRequestPageIds.getEntityImpact,
      ),
    );
    return EntityImpactSummary.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.homepageDetail,
          operationId: EntityApiMetadata.getEntityImpactOperation,
        ),
      ),
    );
  }

  @override
  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    final decoded = await _httpClient.getJson(
      _uri(
        EntityApiMetadata.getHomepageRelatedGroupsPath(homepageId: homepageId),
      ),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageRelatedGroupsOperation,
        clientPageId: EntityRequestPageIds.getHomepageRelatedGroups,
      ),
    );
    final object = CloudResponseDecoder.asObject(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageRelatedGroupsOperation,
      ),
    );
    final rows = CloudResponseDecoder.mapListFirstPresent(
      object,
      const <String>['groups', 'relatedGroups'],
    );
    return rows
        .map(HomepageRelatedGroupSummary.fromMap)
        .toList(growable: false);
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
