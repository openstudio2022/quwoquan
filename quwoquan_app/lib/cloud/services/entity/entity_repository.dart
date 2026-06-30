import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
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
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_mock_data.dart';

part 'entity_object_page_bundle_mock.dart';
part 'entity_introduction_repository.dart';
part 'entity_repository_homepage_helpers.dart';
part 'entity_repository_remote.dart';

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

  Future<EntityImpactSummary> getEntityImpact(String homepageId);

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
    final byId = <String, HomepageDetail>{};
    void put(HomepageDetail homepage) {
      byId[homepage.id] = homepage;
    }

    for (final homepage in HomepageMockData.cloneHomepageSeeds()) {
      put(homepage);
    }
    for (final homepage
        in _contractSeedHomepages() ?? const <HomepageDetail>[]) {
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
  Future<EntityImpactSummary> getEntityImpact(String homepageId) async {
    final homepage = _requireHomepage(homepageId);
    return _entityImpactFromHomepage(homepage);
  }

  /// 由已 contract-seed 的 [HomepageDetail] 真实字段派生「影响力」事实行，
  /// 与圈子影响卡同源（从 stats 派生）：关注连接 / 口碑评价 / 相关圈子讨论。
  /// 不伪造数字——无可派生事实（候选主页无口碑/相关圈子）时返回空 items，端侧整卡不展示（G2）。
  static EntityImpactSummary _entityImpactFromHomepage(
    HomepageDetail homepage,
  ) {
    final followerCount = homepage.followerCount;
    final ratingCount = homepage.reviewSummary?.ratingCount ?? 0;
    final discussionCount = homepage.relatedGroups.fold<int>(
      0,
      (sum, group) => sum + group.memberCount,
    );
    final items = <EntityImpactItem>[
      if (followerCount > 0)
        EntityImpactItem(
          helpType: 'relationship',
          action: 'establish_connection',
          intersectionDimension: 'relationship',
          source: 'homepage_followers',
          count: followerCount,
          primaryText: '$followerCount人因这里建立了关注连接',
          subtitleText: '关注的人也在看这里',
          iconKey: 'connect',
          impactId: 'homepage_${homepage.id}_relationship',
          countObjectKind: 'user',
          primarySpans: <IntersectionTextSpan>[
            IntersectionTextSpan(text: '$followerCount', role: 'count'),
            IntersectionTextSpan(text: '人因这里建立了关注连接', role: 'plain'),
          ],
        ),
      if (ratingCount > 0)
        EntityImpactItem(
          helpType: 'decision',
          action: 'leave_review',
          intersectionDimension: 'decision',
          source: 'homepage_reviews',
          count: ratingCount,
          primaryText: '$ratingCount人为这里留下了真实评价',
          subtitleText: '帮助更多人做决定',
          iconKey: 'star',
          impactId: 'homepage_${homepage.id}_decision',
          countObjectKind: 'review',
          primarySpans: <IntersectionTextSpan>[
            IntersectionTextSpan(text: '$ratingCount', role: 'count'),
            IntersectionTextSpan(text: '人为这里留下了真实评价', role: 'plain'),
          ],
        ),
      if (discussionCount > 0)
        EntityImpactItem(
          helpType: 'community',
          action: 'start_discussion',
          intersectionDimension: 'content',
          source: 'homepage_related_groups',
          count: discussionCount,
          primaryText: '$discussionCount人在相关圈子里讨论这里',
          subtitleText: '讨论在这里沉淀',
          iconKey: 'discussion',
          impactId: 'homepage_${homepage.id}_community',
          countObjectKind: 'user',
          primarySpans: <IntersectionTextSpan>[
            IntersectionTextSpan(text: '$discussionCount', role: 'count'),
            IntersectionTextSpan(text: '人在相关圈子里讨论这里', role: 'plain'),
          ],
        ),
    ];
    return EntityImpactSummary(
      homepageId: homepage.id,
      total: followerCount + ratingCount + discussionCount,
      items: items,
    );
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
    throw CloudErrorMapper.fromStatusCode(
      404,
      body:
          '{"code":"${EntityErrorCode.homepageNotFound.code}","userMessage":"${EntityErrorMessages.zh[EntityErrorCode.homepageNotFound]}"}',
      requestPath: EntityApiMetadata.getHomepageDetailPath(
        homepageId: homepageId,
      ),
    );
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
