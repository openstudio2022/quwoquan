import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_homepage_mutation_wires.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_section.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_bundle.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_context.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_page_rollout_context.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/object_relation_edge.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

part 'entity_object_page_bundle_mock.dart';
part 'entity_introduction_repository.dart';
part 'entity_repository_homepage_helpers.dart';

abstract class HomepageRepository {
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<HomepageDetail> getHomepageDetail(String homepageId);

  Future<HomepageDetail> followHomepage(String homepageId);

  Future<HomepageDetail> unfollowHomepage(String homepageId);

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
          final homepage = HomepageDetail.fromMap(<String, dynamic>{
            ...map,
            'id': map['id'] ?? map['homepageId'],
            'homepageType': map['homepageType'] ?? map['type'],
            'status': map['status'] ?? 'published',
            'sourceType': map['sourceType'] ?? 'contract_fixture',
            'claimStatus': map['claimStatus'] ?? 'unclaimed',
            'categoryTags': map['categoryTags'] ?? const <String>['契约'],
            if (map['geo'] is Map) 'location': map['geo'],
          });
          return _withContractShellDefaults(homepage, map);
        })
        .toList(growable: true);
  }

  static HomepageDetail _withContractShellDefaults(
    HomepageDetail homepage,
    Map<String, dynamic> raw,
  ) {
    final intro = raw['introduction'];
    final introMap = intro is Map ? intro.cast<String, dynamic>() : null;
    final introRelated = introMap?['relatedObjects'];
    final relatedGroups = homepage.relatedGroups.isNotEmpty
        ? homepage.relatedGroups
        : introRelated is List
        ? introRelated
              .whereType<Map>()
              .map(
                (item) => HomepageRelatedGroupSummary.fromMap(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false)
        : _mockDefaultRelatedGroups(homepage);
    final coverUrl =
        homepage.coverUrl ?? introMap?['coverUrl']?.toString().trim();
    if ((homepage.status ?? '').trim() != 'published') {
      return homepage.copyWith(
        coverUrl: coverUrl,
        relatedGroups: relatedGroups,
      );
    }
    return homepage.copyWith(
      coverUrl: coverUrl,
      reviewSummary:
          homepage.reviewSummary ?? _mockDefaultReviewSummary(homepage),
      contentPreview: homepage.contentPreview.isNotEmpty
          ? homepage.contentPreview
          : _mockDefaultContentPreview(homepage),
      questionPreview: homepage.questionPreview.isNotEmpty
          ? homepage.questionPreview
          : _mockDefaultQuestionPreview(homepage),
      relatedGroups: relatedGroups,
    );
  }

  static List<HomepageDetail> _repositorySeedHomepages() {
    return List<HomepageDetail>.from(
      _contractSeedHomepages() ?? const <HomepageDetail>[],
      growable: true,
    );
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
  Future<HomepageDetail> followHomepage(String homepageId) async {
    final homepage = _requireHomepage(homepageId);
    if (homepage.viewerFollowsHomepage) {
      return homepage;
    }
    final next = homepage.copyWith(
      viewerFollowsHomepage: true,
      followerCount: homepage.followerCount + 1,
    );
    _putHomepage(next);
    return next;
  }

  @override
  Future<HomepageDetail> unfollowHomepage(String homepageId) async {
    final homepage = _requireHomepage(homepageId);
    if (!homepage.viewerFollowsHomepage) {
      return homepage;
    }
    final next = homepage.copyWith(
      viewerFollowsHomepage: false,
      followerCount: homepage.followerCount > 0
          ? homepage.followerCount - 1
          : 0,
    );
    _putHomepage(next);
    return next;
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
  Future<ObjectPageBundle> getObjectPageBundle(
    String homepageId, {
    String referralSource = '',
    String feedRequestId = '',
    String recommendationTraceId = '',
    String experimentBucket = '',
    String rolloutCohort = '',
  }) async {
    final homepage = _requireHomepage(homepageId);
    return _objectPageBundleFromHomepage(
      homepage,
      referralSource: referralSource,
      feedRequestId: feedRequestId,
      recommendationTraceId: recommendationTraceId,
      experimentBucket: experimentBucket,
      rolloutCohort: rolloutCohort,
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
    final resolved = _findHomepage(homepageId);
    if (resolved != null) {
      return resolved;
    }
    throw StateError('homepage not found: $homepageId');
  }

  HomepageDetail? _findHomepage(String rawId) {
    final candidates = _homepageLookupCandidates(rawId);
    for (final homepage in _homepages) {
      final homepageCandidates = _homepageLookupCandidates(homepage.id);
      homepageCandidates.addAll(
        _homepageLookupCandidates(_canonicalEntityId(homepage)),
      );
      homepageCandidates.addAll(_homepageDataEntityRefs(homepage));
      if (homepageCandidates.intersection(candidates).isNotEmpty) {
        return homepage;
      }
    }
    return null;
  }

  Set<String> _homepageLookupCandidates(String rawId) {
    final normalized = _normalizeHomepageLookupId(rawId);
    if (normalized.isEmpty) {
      return <String>{};
    }
    final parts = normalized.split('/').where((p) => p.isNotEmpty).toList();
    final last = parts.isEmpty ? null : parts.last;
    return <String>{
      normalized,
      ?last,
      if (normalized.startsWith('entity/homepage/'))
        normalized.substring('entity/homepage/'.length),
      if (normalized.startsWith('entity/'))
        normalized.substring('entity/'.length),
      if (normalized.startsWith('entities/'))
        normalized.substring('entities/'.length),
      if (normalized.startsWith('entity:') && normalized.contains(':homepage:'))
        normalized.substring(
          normalized.lastIndexOf(':homepage:') + ':homepage:'.length,
        ),
      if (normalized.startsWith('entity:') && normalized.contains(':'))
        normalized.substring(normalized.lastIndexOf(':') + 1),
      if (normalized.startsWith('entity:homepage:'))
        normalized.substring('entity:homepage:'.length),
    }.where((item) => item.trim().isNotEmpty).toSet();
  }

  String _normalizeHomepageLookupId(String rawId) {
    return rawId
        .trim()
        .replaceAll('\\', '/')
        .replaceFirst(RegExp(r'^/+'), '')
        .replaceFirst(RegExp(r'^entity/'), 'Entity/')
        .toLowerCase();
  }

  Set<String> _homepageDataEntityRefs(HomepageDetail homepage) {
    final title = homepage.title.trim();
    final type = homepage.homepageType.trim();
    final domain = switch (type) {
      'sight' || 'travel_photo' || 'hotel' || 'restaurant' => '旅行',
      'university' => '校园',
      _ => '通用',
    };
    final entityType = switch (type) {
      'sight' => '景区',
      'travel_photo' => '机位',
      'hotel' => '住宿',
      'restaurant' => '餐饮',
      'university' => '学校',
      _ => '主页',
    };
    return <String>{
      if (title.isNotEmpty) 'entity/$domain/$entityType/$title',
      if (title.isNotEmpty) 'entities/$domain/$entityType/$title',
      if (title.isNotEmpty) '$domain/$entityType/$title',
      if (title.isNotEmpty) title,
    }.map(_normalizeHomepageLookupId).toSet();
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
