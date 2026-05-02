import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_homepage_mutation_wires.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_mock_data.dart';

abstract class HomepageRepository {
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<HomepageDetail> getHomepageDetail(String homepageId);

  Future<HomepageShellData> getHomepageShell(String homepageId);

  Future<HomepageReviewSummaryData> getHomepageReviewSummary(String homepageId);

  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  );

  Future<HomepageDetail> intakeHomepageCandidate({
    required HomepageSuggestionDraft draft,
  });

  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  });

  Future<HomepageDetail> publishHomepageCandidate(String homepageId);

  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  });

  Future<HomepageClaimRequestRecord> reviewHomepageClaimRequest({
    required String homepageId,
    required String claimRequestId,
    required String status,
    String? reviewNote,
  });

  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  });

  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  });

  Future<HomepageStatusReportRecord> reviewHomepageStatusReport({
    required String homepageId,
    required String reportId,
    required String status,
    String? reviewNote,
  });
}

class MockHomepageRepository implements HomepageRepository {
  MockHomepageRepository() : _homepages = _repositorySeedHomepages();

  final List<HomepageDetail> _homepages;
  final List<HomepageClaimRequestRecord> _claimRequests =
      <HomepageClaimRequestRecord>[];
  final List<HomepageStatusReportRecord> _statusReports =
      <HomepageStatusReportRecord>[];

  static List<HomepageDetail>? _contractSeedHomepages() {
    final seed = ContractFixtureRuntimeLoader.entitySeedSet();
    final homepages = seed?['homepages'];
    if (homepages is! List) {
      return null;
    }
    return homepages
        .whereType<Map>()
        .map((item) {
          final map = item.cast<String, dynamic>();
          return HomepageDetail.fromMap(<String, dynamic>{
            ...map,
            'id': map['id'] ?? map['homepageId'],
            'homepageType': map['homepageType'] ?? map['type'],
            'status': map['status'] ?? 'published',
            'sourceType': map['sourceType'] ?? 'contract_fixture',
            'claimStatus': map['claimStatus'] ?? 'unclaimed',
            'categoryTags': map['categoryTags'] ?? const <String>['契约'],
            if (map['geo'] is Map) 'location': map['geo'],
          });
        })
        .toList(growable: true);
  }

  static List<HomepageDetail> _repositorySeedHomepages() {
    final byId = <String, HomepageDetail>{};
    void put(HomepageDetail homepage) {
      byId[homepage.id] = homepage;
    }

    for (final homepage
        in _contractSeedHomepages() ?? const <HomepageDetail>[]) {
      put(homepage);
    }
    for (final homepage in HomepageMockData.cloneHomepageSeeds()) {
      put(homepage);
    }
    return byId.values.toList(growable: true);
  }

  void _putHomepage(HomepageDetail next) {
    final i = _homepages.indexWhere((h) => h.id == next.id);
    if (i < 0) {
      throw StateError('homepage not found: ${next.id}');
    }
    _homepages[i] = next;
  }

  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = _normalize(query);
    final normalizedType = _normalize(homepageType);
    final normalizedCity = _normalize(city);
    final normalizedStatus = _normalize(status);
    final items = _homepages
        .where((h) {
          if (normalizedType.isNotEmpty &&
              _normalize(h.homepageType) != normalizedType) {
            return false;
          }
          if (normalizedCity.isNotEmpty &&
              _normalize(h.city) != normalizedCity) {
            return false;
          }
          if (normalizedStatus.isNotEmpty) {
            if (_normalize(h.status) != normalizedStatus) {
              return false;
            }
          } else if (_normalize(h.status) != 'published') {
            return false;
          }
          if (normalizedQuery.isEmpty) {
            return true;
          }
          final haystack = _normalize(
            <String>[
              h.title,
              h.subtitle ?? '',
              h.address ?? '',
              h.city ?? '',
              ...h.categoryTags,
            ].join(' '),
          );
          return haystack.contains(normalizedQuery);
        })
        .take(limit)
        .toList(growable: false);
    return items.map(HomepageSummary.fromDetail).toList(growable: false);
  }

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    return _requireHomepage(homepageId);
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    final homepage = _requireHomepage(homepageId);
    return HomepageShellData(
      homepage: homepage,
      reviewSummary: homepage.reviewSummary,
      contentPreview: homepage.contentPreview,
      questionPreview: homepage.questionPreview,
      relatedGroups: homepage.relatedGroups,
    );
  }

  @override
  Future<HomepageReviewSummaryData> getHomepageReviewSummary(
    String homepageId,
  ) async {
    final homepage = _requireHomepage(homepageId);
    final rs = homepage.reviewSummary;
    if (rs != null) {
      return rs;
    }
    return HomepageReviewSummaryData();
  }

  @override
  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    final homepage = _requireHomepage(homepageId);
    return List<HomepageRelatedGroupSummary>.from(homepage.relatedGroups);
  }

  @override
  Future<HomepageDetail> intakeHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final item = _createCandidateFromDraft(draft, sourceType: 'owner_created');
    _homepages.add(item);
    return item;
  }

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final item = _createCandidateFromDraft(draft, sourceType: 'user_suggested');
    _homepages.add(item);
    return item;
  }

  @override
  Future<HomepageDetail> publishHomepageCandidate(String homepageId) async {
    final h = _requireHomepage(homepageId);
    final now = DateTime.now().toUtc();
    final published = h.copyWith(
      status: 'published',
      updatedAt: now,
      publishedAt: now,
      reviewSummary: h.reviewSummary ?? _mockDefaultReviewSummary(h),
      contentPreview: h.contentPreview.isNotEmpty
          ? h.contentPreview
          : _mockDefaultContentPreview(h),
      questionPreview: h.questionPreview.isNotEmpty
          ? h.questionPreview
          : _mockDefaultQuestionPreview(h),
      relatedGroups: h.relatedGroups.isNotEmpty
          ? h.relatedGroups
          : _mockDefaultRelatedGroups(h),
    );
    _putHomepage(published);
    return published;
  }

  @override
  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    final homepage = _requireHomepage(homepageId);
    final now = DateTime.now().toUtc();
    final record = HomepageClaimRequestRecord(
      id: 'claim_${_claimRequests.length + 1}',
      homepageId: homepageId,
      requesterUserId: draft.requesterUserId.trim().isEmpty
          ? 'mock-user'
          : draft.requesterUserId.trim(),
      claimTier: draft.claimTier,
      status: 'pending_review',
      createdAt: now,
    );
    _claimRequests.add(record);
    _putHomepage(
      homepage.copyWith(claimStatus: 'pending_review', updatedAt: now),
    );
    return record;
  }

  @override
  Future<HomepageClaimRequestRecord> reviewHomepageClaimRequest({
    required String homepageId,
    required String claimRequestId,
    required String status,
    String? reviewNote,
  }) async {
    final homepage = _requireHomepage(homepageId);
    final idx = _claimRequests.indexWhere(
      (r) => r.id == claimRequestId && r.homepageId == homepageId,
    );
    if (idx < 0) {
      throw StateError('claim request not found: $claimRequestId');
    }
    final old = _claimRequests[idx];
    final now = DateTime.now().toUtc();
    final next = HomepageClaimRequestRecord(
      id: old.id,
      homepageId: old.homepageId,
      requesterUserId: old.requesterUserId,
      claimTier: old.claimTier,
      status: status,
      reviewNote: reviewNote,
      createdAt: old.createdAt,
      reviewedAt: now,
    );
    _claimRequests[idx] = next;
    final claimStatus = status == 'approved' ? 'claimed' : 'rejected';
    _putHomepage(
      homepage.copyWith(
        claimStatus: claimStatus,
        ownerUserId: status == 'approved'
            ? old.requesterUserId
            : homepage.ownerUserId,
        updatedAt: now,
      ),
    );
    return next;
  }

  @override
  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  }) async {
    final item = _requireHomepage(homepageId);
    final next = _mergeBasicDraft(item, draft);
    _putHomepage(next);
    return next;
  }

  @override
  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    _requireHomepage(homepageId);
    final now = DateTime.now().toUtc();
    final record = HomepageStatusReportRecord(
      id: 'report_${_statusReports.length + 1}',
      homepageId: homepageId,
      reporterUserId: draft.reporterUserId.trim().isEmpty
          ? 'mock-user'
          : draft.reporterUserId.trim(),
      reason: draft.reason,
      status: 'pending_review',
      description: draft.description.trim().isEmpty
          ? null
          : draft.description.trim(),
      evidenceUrls: List<String>.from(draft.evidenceUrls),
      createdAt: now,
    );
    _statusReports.add(record);
    return record;
  }

  @override
  Future<HomepageStatusReportRecord> reviewHomepageStatusReport({
    required String homepageId,
    required String reportId,
    required String status,
    String? reviewNote,
  }) async {
    final homepage = _requireHomepage(homepageId);
    final idx = _statusReports.indexWhere(
      (r) => r.id == reportId && r.homepageId == homepageId,
    );
    if (idx < 0) {
      throw StateError('status report not found: $reportId');
    }
    final old = _statusReports[idx];
    final now = DateTime.now().toUtc();
    final next = HomepageStatusReportRecord(
      id: old.id,
      homepageId: old.homepageId,
      reporterUserId: old.reporterUserId,
      reason: old.reason,
      status: status,
      description: old.description,
      evidenceUrls: old.evidenceUrls,
      reviewNote: reviewNote,
      createdAt: old.createdAt,
      reviewedAt: now,
    );
    _statusReports[idx] = next;
    if (status == 'confirmed_offline') {
      _putHomepage(
        homepage.copyWith(status: 'offline', offlineAt: now, updatedAt: now),
      );
    }
    return next;
  }

  HomepageDetail _requireHomepage(String homepageId) {
    return _homepages.firstWhere(
      (h) => h.id == homepageId,
      orElse: () => throw StateError('homepage not found: $homepageId'),
    );
  }

  HomepageDetail _createCandidateFromDraft(
    HomepageSuggestionDraft draft, {
    required String sourceType,
  }) {
    final now = DateTime.now().toUtc();
    return HomepageDetail(
      id: 'homepage_candidate_${_homepages.length + 1}',
      homepageType: draft.homepageType,
      title: draft.title,
      subtitle: draft.subtitle.trim().isEmpty ? null : draft.subtitle.trim(),
      coverUrl: draft.coverUrl.trim().isEmpty ? null : draft.coverUrl.trim(),
      categoryTags: List<String>.from(draft.categoryTags),
      address: draft.address.trim().isEmpty ? null : draft.address.trim(),
      city: draft.city.trim().isEmpty ? null : draft.city.trim(),
      location: draft.location,
      status: 'candidate',
      sourceType: sourceType,
      claimStatus: 'unclaimed',
      createdAt: now,
      updatedAt: now,
    );
  }
}

HomepageReviewSummaryData _mockDefaultReviewSummary(HomepageDetail homepage) {
  return HomepageReviewSummaryData(
    averageRating: homepage.averageRating ?? 4.6,
    ratingCount: homepage.ratingCount != 0 ? homepage.ratingCount : 18,
    highlightTags: homepage.categoryTags.isNotEmpty
        ? List<String>.from(homepage.categoryTags)
        : const <String>['体验稳定', '适合沉淀口碑'],
    dimensionScores: <HomepageReviewDimensionScore>[
      HomepageReviewDimensionScore(label: '环境', score: 4.6),
      HomepageReviewDimensionScore(label: '体验', score: 4.5),
      HomepageReviewDimensionScore(label: '推荐度', score: 4.7),
    ],
  );
}

List<HomepageContentPreview> _mockDefaultContentPreview(
  HomepageDetail homepage,
) {
  final title = homepage.title;
  return <HomepageContentPreview>[
    HomepageContentPreview(
      postId: '${homepage.id}_post_1',
      title: '$title 的体验笔记',
      summary: '从主页上下文进入内容挂载后的聚合。',
      contentType: 'article',
      coverUrl: homepage.coverUrl,
    ),
  ];
}

List<HomepageQuestionPreview> _mockDefaultQuestionPreview(
  HomepageDetail homepage,
) {
  final title = homepage.title;
  return <HomepageQuestionPreview>[
    HomepageQuestionPreview(
      postId: '${homepage.id}_question_1',
      title: '$title 值得什么时候去？',
      summary: '候选主页发布后也会得到基础问答壳层。',
    ),
  ];
}

List<HomepageRelatedGroupSummary> _mockDefaultRelatedGroups(
  HomepageDetail homepage,
) {
  final title = homepage.title;
  final id = homepage.id;
  return <HomepageRelatedGroupSummary>[
    HomepageRelatedGroupSummary(
      circleId: '${id}_group_1',
      name: '$title 讨论群',
      memberCount: 12,
      linkedHomepageId: id,
      linkedHomepageTitle: title,
    ),
  ];
}

HomepageDetail _mergeBasicDraft(HomepageDetail h, HomepageBasicDraft d) {
  final now = DateTime.now().toUtc();
  return HomepageDetail(
    id: h.id,
    homepageType: h.homepageType,
    title: d.title != null && d.title!.trim().isNotEmpty
        ? d.title!.trim()
        : h.title,
    subtitle: d.subtitle != null
        ? (d.subtitle!.trim().isEmpty ? null : d.subtitle!.trim())
        : h.subtitle,
    coverUrl: d.coverUrl != null && d.coverUrl!.trim().isNotEmpty
        ? d.coverUrl!.trim()
        : h.coverUrl,
    status: h.status,
    sourceType: h.sourceType,
    claimStatus: h.claimStatus,
    categoryTags: d.categoryTags ?? h.categoryTags,
    address: d.address != null && d.address!.trim().isNotEmpty
        ? d.address!.trim()
        : h.address,
    city: d.city != null && d.city!.trim().isNotEmpty ? d.city!.trim() : h.city,
    location: d.location ?? h.location,
    ownerUserId: h.ownerUserId,
    averageRating: h.averageRating,
    ratingCount: h.ratingCount,
    reviewSummary: h.reviewSummary,
    contentPreview: h.contentPreview,
    questionPreview: h.questionPreview,
    relatedGroups: h.relatedGroups,
    createdAt: h.createdAt,
    updatedAt: now,
    publishedAt: h.publishedAt,
    offlineAt: h.offlineAt,
  );
}

class RemoteHomepageRepository implements HomepageRepository {
  RemoteHomepageRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(client: http.Client()),
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

String _normalize(String? value) => (value ?? '').trim().toLowerCase();
