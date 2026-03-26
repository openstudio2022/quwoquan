import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/entity/homepage_models.dart';
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
  MockHomepageRepository()
    : _homepages = HomepageMockData.homepages
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: true);

  final List<Map<String, dynamic>> _homepages;
  final List<Map<String, dynamic>> _claimRequests = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> _statusReports = <Map<String, dynamic>>[];

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
        .where((item) {
          if (normalizedType.isNotEmpty &&
              _normalize(item['homepageType']?.toString()) != normalizedType) {
            return false;
          }
          if (normalizedCity.isNotEmpty &&
              _normalize(item['city']?.toString()) != normalizedCity) {
            return false;
          }
          if (normalizedStatus.isNotEmpty) {
            if (_normalize(item['status']?.toString()) != normalizedStatus) {
              return false;
            }
          } else if (_normalize(item['status']?.toString()) != 'published') {
            return false;
          }
          if (normalizedQuery.isEmpty) {
            return true;
          }
          final haystack = _normalize(
            <String>[
              item['title']?.toString() ?? '',
              item['subtitle']?.toString() ?? '',
              item['address']?.toString() ?? '',
              item['city']?.toString() ?? '',
              ...(item['categoryTags'] as List? ?? const <String>[]).map(
                (tag) => tag.toString(),
              ),
            ].join(' '),
          );
          return haystack.contains(normalizedQuery);
        })
        .take(limit)
        .toList(growable: false);
    return items
        .map((item) => HomepageSummary.fromMap(item))
        .toList(growable: false);
  }

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    return HomepageDetail.fromMap(_requireHomepage(homepageId));
  }

  @override
  Future<HomepageShellData> getHomepageShell(String homepageId) async {
    final homepage = _requireHomepage(homepageId);
    return HomepageShellData.fromMap(<String, dynamic>{
      'homepage': homepage,
      'reviewSummary': homepage['reviewSummary'],
      'contentPreview': homepage['contentPreview'],
      'questionPreview': homepage['questionPreview'],
      'relatedGroups': homepage['relatedGroups'],
    });
  }

  @override
  Future<HomepageReviewSummaryData> getHomepageReviewSummary(
    String homepageId,
  ) async {
    final homepage = _requireHomepage(homepageId);
    return HomepageReviewSummaryData.fromMap(
      Map<String, dynamic>.from(
        homepage['reviewSummary'] as Map? ?? const <String, dynamic>{},
      ),
    );
  }

  @override
  Future<List<HomepageRelatedGroupSummary>> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    final homepage = _requireHomepage(homepageId);
    return (homepage['relatedGroups'] as List? ?? const <dynamic>[])
        .whereType<Map>()
        .map(
          (item) =>
              HomepageRelatedGroupSummary.fromMap(item.cast<String, dynamic>()),
        )
        .toList(growable: false);
  }

  @override
  Future<HomepageDetail> intakeHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final item = _createCandidateFromDraft(draft, sourceType: 'owner_created');
    _homepages.add(item);
    return HomepageDetail.fromMap(item);
  }

  @override
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final item = _createCandidateFromDraft(draft, sourceType: 'user_suggested');
    _homepages.add(item);
    return HomepageDetail.fromMap(item);
  }

  @override
  Future<HomepageDetail> publishHomepageCandidate(String homepageId) async {
    final item = _requireHomepage(homepageId);
    final now = DateTime.now().toUtc().toIso8601String();
    item['status'] = 'published';
    item['updatedAt'] = now;
    item['publishedAt'] = now;
    item.putIfAbsent('reviewSummary', () => _defaultReviewSummary(item));
    item.putIfAbsent('contentPreview', () => _defaultContentPreview(item));
    item.putIfAbsent('questionPreview', () => _defaultQuestionPreview(item));
    item.putIfAbsent('relatedGroups', () => _defaultRelatedGroups(item));
    return HomepageDetail.fromMap(item);
  }

  @override
  Future<HomepageClaimRequestRecord> createHomepageClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) async {
    final homepage = _requireHomepage(homepageId);
    final now = DateTime.now().toUtc().toIso8601String();
    final item = <String, dynamic>{
      '_id': 'claim_${_claimRequests.length + 1}',
      'homepageId': homepageId,
      'requesterUserId': draft.requesterUserId.trim().isEmpty
          ? 'mock-user'
          : draft.requesterUserId.trim(),
      'claimTier': draft.claimTier,
      'contactPhone': draft.contactPhone,
      'businessLicenseUrl': draft.businessLicenseUrl,
      'identityCardFrontUrl': draft.identityCardFrontUrl,
      'identityCardBackUrl': draft.identityCardBackUrl,
      'note': draft.note,
      'status': 'pending_review',
      'createdAt': now,
    };
    _claimRequests.add(item);
    homepage['claimStatus'] = 'pending_review';
    homepage['updatedAt'] = now;
    return HomepageClaimRequestRecord.fromMap(item);
  }

  @override
  Future<HomepageClaimRequestRecord> reviewHomepageClaimRequest({
    required String homepageId,
    required String claimRequestId,
    required String status,
    String? reviewNote,
  }) async {
    final homepage = _requireHomepage(homepageId);
    final item = _claimRequests.firstWhere(
      (request) =>
          request['_id']?.toString() == claimRequestId &&
          request['homepageId']?.toString() == homepageId,
    );
    final now = DateTime.now().toUtc().toIso8601String();
    item['status'] = status;
    item['reviewNote'] = reviewNote;
    item['reviewedAt'] = now;
    homepage['claimStatus'] = status == 'approved' ? 'claimed' : 'rejected';
    if (status == 'approved') {
      homepage['ownerUserId'] = item['requesterUserId'];
    }
    homepage['updatedAt'] = now;
    return HomepageClaimRequestRecord.fromMap(item);
  }

  @override
  Future<HomepageDetail> updateClaimedHomepageBasics({
    required String homepageId,
    required HomepageBasicDraft draft,
  }) async {
    final item = _requireHomepage(homepageId);
    final payload = draft.toMap();
    payload.forEach((key, value) {
      item[key] = value;
    });
    item['updatedAt'] = DateTime.now().toUtc().toIso8601String();
    return HomepageDetail.fromMap(item);
  }

  @override
  Future<HomepageStatusReportRecord> createHomepageStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) async {
    _requireHomepage(homepageId);
    final item = <String, dynamic>{
      '_id': 'report_${_statusReports.length + 1}',
      'homepageId': homepageId,
      'reporterUserId': draft.reporterUserId.trim().isEmpty
          ? 'mock-user'
          : draft.reporterUserId.trim(),
      'reason': draft.reason,
      'description': draft.description,
      'evidenceUrls': draft.evidenceUrls,
      'status': 'pending_review',
      'createdAt': DateTime.now().toUtc().toIso8601String(),
    };
    _statusReports.add(item);
    return HomepageStatusReportRecord.fromMap(item);
  }

  @override
  Future<HomepageStatusReportRecord> reviewHomepageStatusReport({
    required String homepageId,
    required String reportId,
    required String status,
    String? reviewNote,
  }) async {
    final homepage = _requireHomepage(homepageId);
    final item = _statusReports.firstWhere(
      (report) =>
          report['_id']?.toString() == reportId &&
          report['homepageId']?.toString() == homepageId,
    );
    final now = DateTime.now().toUtc().toIso8601String();
    item['status'] = status;
    item['reviewNote'] = reviewNote;
    item['reviewedAt'] = now;
    if (status == 'confirmed_offline') {
      homepage['status'] = 'offline';
      homepage['offlineAt'] = now;
      homepage['updatedAt'] = now;
    }
    return HomepageStatusReportRecord.fromMap(item);
  }

  Map<String, dynamic> _requireHomepage(String homepageId) {
    return _homepages.firstWhere(
      (item) => item['_id']?.toString() == homepageId,
      orElse: () => throw StateError('homepage not found: $homepageId'),
    );
  }

  Map<String, dynamic> _createCandidateFromDraft(
    HomepageSuggestionDraft draft, {
    required String sourceType,
  }) {
    final now = DateTime.now().toUtc().toIso8601String();
    return <String, dynamic>{
      '_id': 'homepage_candidate_${_homepages.length + 1}',
      ...draft.toMap(),
      'status': 'candidate',
      'sourceType': sourceType,
      'claimStatus': 'unclaimed',
      'createdAt': now,
      'updatedAt': now,
    };
  }

  Map<String, dynamic> _defaultReviewSummary(Map<String, dynamic> homepage) {
    return <String, dynamic>{
      'averageRating': homepage['averageRating'] ?? 4.6,
      'ratingCount': homepage['ratingCount'] ?? 18,
      'highlightTags':
          homepage['categoryTags'] ?? const <String>['体验稳定', '适合沉淀口碑'],
      'dimensionScores': <Map<String, dynamic>>[
        <String, dynamic>{'label': '环境', 'score': 4.6},
        <String, dynamic>{'label': '体验', 'score': 4.5},
        <String, dynamic>{'label': '推荐度', 'score': 4.7},
      ],
    };
  }

  List<Map<String, dynamic>> _defaultContentPreview(
    Map<String, dynamic> homepage,
  ) {
    final title = homepage['title']?.toString() ?? '';
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'postId': '${homepage['_id']}_post_1',
        'title': '$title 的体验笔记',
        'summary': '从主页上下文进入内容挂载后的聚合。',
        'contentType': 'article',
        'coverUrl': homepage['coverUrl'],
      },
    ];
  }

  List<Map<String, dynamic>> _defaultQuestionPreview(
    Map<String, dynamic> homepage,
  ) {
    final title = homepage['title']?.toString() ?? '';
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'postId': '${homepage['_id']}_question_1',
        'title': '$title 值得什么时候去？',
        'summary': '候选主页发布后也会得到基础问答壳层。',
      },
    ];
  }

  List<Map<String, dynamic>> _defaultRelatedGroups(
    Map<String, dynamic> homepage,
  ) {
    final title = homepage['title']?.toString() ?? '';
    final id = homepage['_id']?.toString() ?? '';
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'circleId': '${id}_group_1',
        'name': '$title 讨论群',
        'memberCount': 12,
        'linkedHomepageId': id,
        'linkedHomepageTitle': title,
      },
    ];
  }
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
    required String legacyPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: surface.id,
      routeId: surface.routeId,
      operationId: operationId,
      legacyPageId: legacyPageId,
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
        legacyPageId: EntityRequestPageIds.searchHomepages,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.homepagePicker,
        operationId: EntityApiMetadata.searchHomepagesOperation,
      ),
    );
    return page.items
        .map((item) => HomepageSummary.fromMap(item))
        .toList(growable: false);
  }

  @override
  Future<HomepageDetail> getHomepageDetail(String homepageId) async {
    final decoded = await _httpClient.getJson(
      _uri(EntityApiMetadata.getHomepageDetailPath(homepageId: homepageId)),
      headers: _headersForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageDetailOperation,
        legacyPageId: EntityRequestPageIds.getHomepageDetail,
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
        legacyPageId: EntityRequestPageIds.getHomepageShell,
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
        legacyPageId: EntityRequestPageIds.getHomepageReviewSummary,
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
        legacyPageId: EntityRequestPageIds.getHomepageRelatedGroups,
      ),
    );
    final object = CloudResponseDecoder.asObject(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.homepageDetail,
        operationId: EntityApiMetadata.getHomepageRelatedGroupsOperation,
      ),
    );
    return (object['groups'] as List? ?? const <dynamic>[])
        .whereType<Map>()
        .map(
          (item) =>
              HomepageRelatedGroupSummary.fromMap(item.cast<String, dynamic>()),
        )
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
        legacyPageId: EntityRequestPageIds.intakeHomepageCandidate,
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
        legacyPageId: EntityRequestPageIds.suggestHomepageCandidate,
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
        legacyPageId: EntityRequestPageIds.publishHomepageCandidate,
      ),
      body: const <String, dynamic>{},
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
        legacyPageId: EntityRequestPageIds.createHomepageClaimRequest,
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
        legacyPageId: EntityRequestPageIds.reviewHomepageClaimRequest,
      ),
      body: <String, dynamic>{
        'status': status,
        if (reviewNote != null && reviewNote.isNotEmpty)
          'reviewNote': reviewNote,
      },
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
        legacyPageId: EntityRequestPageIds.updateClaimedHomepageBasics,
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
        legacyPageId: EntityRequestPageIds.createHomepageStatusReport,
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
        legacyPageId: EntityRequestPageIds.reviewHomepageStatusReport,
      ),
      body: <String, dynamic>{
        'status': status,
        if (reviewNote != null && reviewNote.isNotEmpty)
          'reviewNote': reviewNote,
      },
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
