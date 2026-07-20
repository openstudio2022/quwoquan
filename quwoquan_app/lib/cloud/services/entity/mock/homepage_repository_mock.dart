/// Alpha/local_contract 专用 Homepage mock 装配。
/// production composition 不 import 本文件；只允许 alpha runner 与测试注入。
library;

import 'package:quwoquan_app/cloud/entity/generated/entity_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_section.g.dart';
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
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_mock_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal;

class MockHomepageRepository implements HomepageFacetSet {
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
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    cancellation?.throwIfCancelled();
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
    cancellation?.throwIfCancelled();
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

  /// 由已 contract-seed 的 [HomepageDetail] 真实字段派生「打动」事实行，
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
  Future<HomepageDetail> suggestHomepageCandidate({
    required HomepageSuggestionDraft draft,
  }) async {
    final item = _createCandidateFromDraft(draft, sourceType: 'user_suggested');
    _homepages.add(item);
    return item;
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
      requesterPersonaId: draft.requesterPersonaId.trim().isEmpty
          ? 'alpha-persona'
          : draft.requesterPersonaId.trim(),
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
      reporterPersonaId: draft.reporterPersonaId.trim().isEmpty
          ? 'alpha-persona'
          : draft.reporterPersonaId.trim(),
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

class MockHomepageIntroductionRepository
    implements HomepageIntroductionRepository {
  const MockHomepageIntroductionRepository();

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    final resolvedHomepage = MockHomepageRepository()._findHomepage(homepageId);
    final resolvedHomepageId = resolvedHomepage?.id ?? homepageId;
    final seed = ContractFixtureRuntimeLoader.entitySeedSet();
    final homepages = seed?['homepages'];
    if (homepages is List) {
      for (final raw in homepages) {
        if (raw is! Map) {
          continue;
        }
        final map = raw.cast<String, dynamic>();
        final id = (map['homepageId'] ?? '').toString();
        if (id != resolvedHomepageId) {
          continue;
        }
        final intro = map['introduction'];
        if (intro is Map<String, dynamic>) {
          return HomepageIntroduction.fromMap(intro);
        }
        if (intro is Map) {
          return HomepageIntroduction.fromMap(Map<String, dynamic>.from(intro));
        }
      }
    }
    final homepage = resolvedHomepage;
    if (homepage == null) {
      return null;
    }
    return _fallbackIntroductionFromHomepage(homepage);
  }
}

HomepageIntroduction _fallbackIntroductionFromHomepage(
  HomepageDetail homepage,
) {
  final summaryParts = <String>[
    if ((homepage.subtitle ?? '').trim().isNotEmpty) homepage.subtitle!.trim(),
    if (homepage.categoryTags.isNotEmpty)
      homepage.categoryTags.take(3).join('、'),
    if ((homepage.city ?? '').trim().isNotEmpty) homepage.city!.trim(),
  ];
  final summary = summaryParts.isEmpty
      ? '${homepage.title} 的基础信息、内容和讨论正在持续整理中。'
      : summaryParts.join(' · ');
  return HomepageIntroduction(
    homepageId: homepage.id,
    displayName: homepage.title,
    homepageType: homepage.homepageType,
    coverUrl: homepage.coverUrl,
    summary: summary,
    sections: <HomepageIntroductionSection>[
      HomepageIntroductionSection(
        kind: 'overview',
        title: '概况',
        bodyMarkdown:
            '$summary\n\n这个页面用于长期整理与 ${homepage.title} 相关的基础信息、内容、讨论和兴趣圈。随着更多真实内容与来源进入，介绍页会继续补充时间线、关键事实与相关对象。',
      ),
      HomepageIntroductionSection(
        kind: 'keyFacts',
        title: '核心信息',
        bodyMarkdown: <String>[
          '- 类型：${homepage.homepageType}',
          if ((homepage.city ?? '').trim().isNotEmpty)
            '- 所在城市：${homepage.city}',
          if (homepage.categoryTags.isNotEmpty)
            '- 关键词：${homepage.categoryTags.join('、')}',
        ].join('\n'),
      ),
    ],
    relatedObjects: homepage.relatedGroups,
    updatedAt: homepage.updatedAt?.toUtc().toIso8601String() ?? '',
  );
}

HomepageReviewSummaryData _mockDefaultReviewSummary(HomepageDetail homepage) {
  return HomepageReviewSummaryData(
    averageRating: homepage.averageRating ?? 4.6,
    ratingCount: homepage.ratingCount != 0 ? homepage.ratingCount : 18,
    highlightTags: homepage.categoryTags.isNotEmpty
        ? List<String>.from(homepage.categoryTags)
        : const <String>['体验稳定', '适合沉淀口碑'],
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
      name: '$title 讨论',
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
    canonicalEntityId: h.canonicalEntityId,
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

String _normalize(String? value) => (value ?? '').trim().toLowerCase();

ObjectPageBundle _objectPageBundleFromHomepage(
  HomepageDetail homepage, {
  required String referralSource,
  required String feedRequestId,
  required String recommendationTraceId,
  required String experimentBucket,
  required String rolloutCohort,
}) {
  final canonicalEntityId = _canonicalEntityId(homepage);
  final relationEdges = _mockRelationEdges(homepage, canonicalEntityId);
  final relationEdgeIds = relationEdges.map((edge) => edge.edgeId).toList();
  final relatedGroups = homepage.relatedGroups.isNotEmpty
      ? homepage.relatedGroups
      : _mockDefaultRelatedGroups(homepage);
  final highlights = homepage.contentPreview.isNotEmpty
      ? homepage.contentPreview
      : _mockDefaultContentPreview(homepage);
  return ObjectPageBundle(
    objectType: 'homepage',
    objectId: homepage.id,
    canonicalEntityId: canonicalEntityId,
    title: homepage.title,
    subtitle: homepage.subtitle,
    coverUrl: homepage.coverUrl,
    objectPageTemplate: _objectPageTemplate(homepage),
    tagRefs: homepage.categoryTags,
    stats: <String, dynamic>{
      'ratingCount': homepage.ratingCount,
      'relatedGroupCount': relatedGroups.length,
      'highlightCount': highlights.length,
    },
    intersectionReasons: _mockIntersectionReasons(homepage, relationEdges),
    highlightItems: highlights,
    contentSections: <String, dynamic>{
      'home': highlights.map((item) => item.toMap()).toList(growable: false),
      if (homepage.reviewSummary != null)
        'reviews': homepage.reviewSummary!.toMap(),
      'related': relatedGroups
          .map((item) => item.toMap())
          .toList(growable: false),
    },
    relatedObjects: relatedGroups,
    relationEdges: relationEdges,
    assistantContext: ObjectPageContext(
      objectType: 'homepage',
      objectId: homepage.id,
      canonicalEntityId: canonicalEntityId,
      tagRefs: homepage.categoryTags,
      entityRefs: <String>[canonicalEntityId],
      relationEdgeIds: relationEdgeIds,
      referralSource: referralSource,
      feedRequestId: feedRequestId,
      recommendationTraceId: recommendationTraceId,
      experimentBucket: experimentBucket,
      rolloutCohort: rolloutCohort,
    ),
    rolloutContext: ObjectPageRolloutContext(
      enabled: true,
      cohort: rolloutCohort.isEmpty ? 'object-homepage-alpha' : rolloutCohort,
      city: homepage.city ?? '',
      campus: homepage.homepageType == 'university' ? homepage.title : '',
      experimentBucket: experimentBucket,
      objectType: homepage.homepageType,
      assistantProactiveEnabled: true,
      relationEvidenceEnabled: true,
    ),
  );
}

List<ObjectRelationEdge> _mockRelationEdges(
  HomepageDetail homepage,
  String canonicalEntityId,
) {
  final relatedGroups = homepage.relatedGroups.isNotEmpty
      ? homepage.relatedGroups
      : _mockDefaultRelatedGroups(homepage);
  if (relatedGroups.isEmpty) {
    return <ObjectRelationEdge>[
      ObjectRelationEdge(
        edgeId: '${homepage.id}_co_tagged',
        edgeType: 'co_tagged',
        sourceObjectType: 'homepage',
        sourceObjectId: homepage.id,
        targetObjectType: 'homepage',
        targetObjectId: homepage.id,
        canonicalEntityId: canonicalEntityId,
        tagRefs: homepage.categoryTags,
        evidenceRefs: <String>[homepage.id],
        confidence: 0.72,
        createdAt: homepage.updatedAt,
      ),
    ];
  }
  return <ObjectRelationEdge>[
    for (final group in relatedGroups)
      ObjectRelationEdge(
        edgeId: '${homepage.id}_${group.circleId}_edge',
        edgeType: 'circle_under_entity',
        sourceObjectType: 'circle',
        sourceObjectId: group.circleId,
        targetObjectType: 'homepage',
        targetObjectId: homepage.id,
        canonicalEntityId: canonicalEntityId,
        tagRefs: homepage.categoryTags,
        evidenceRefs: <String>[group.circleId, homepage.id],
        confidence: 0.92,
        createdAt: homepage.updatedAt,
      ),
  ];
}

List<IntersectionReason> _mockIntersectionReasons(
  HomepageDetail homepage,
  List<ObjectRelationEdge> relationEdges,
) {
  final interestLabel = switch (homepage.homepageType) {
    'university' => '校园交集',
    'travel_photo' || 'sight' => '共同足迹',
    _ => '共同关注',
  };
  final firstEdge = relationEdges.isNotEmpty ? relationEdges.first : null;
  return <IntersectionReason>[
    _mockReasonWithPoint(
      IntersectionReason(
        dimension: 'interest',
        tagRefs: homepage.categoryTags,
        relationKind: 'mutual',
        relationObjectId: homepage.id,
        totalPointCount: homepage.categoryTags.length,
        strength: 0.86,
        primaryText: interestLabel,
        actionType: 'view_object',
        actionTargetId: homepage.id,
        source: 'tagRef',
      ),
      pointClass: 'recommended',
    ),
    _mockReasonWithPoint(
      IntersectionReason(
        dimension: 'relationship',
        tagRefs: homepage.categoryTags,
        relationKind: 'mutual',
        relationObjectId: firstEdge?.sourceObjectId ?? '',
        totalPointCount: relationEdges.length,
        strength: 0.78,
        primaryText: '相关圈子',
        actionType: 'join',
        actionTargetId: firstEdge?.sourceObjectId ?? '',
        source: 'followEdge',
      ),
      pointClass: 'fact',
    ),
  ];
}

IntersectionReason _mockReasonWithPoint(
  IntersectionReason reason, {
  required String pointClass,
}) {
  final point = IntersectionPoint(
    pointId: '${reason.actionTargetId}_${reason.dimension}',
    pointClass: pointClass,
    dimension: reason.dimension,
    label: reason.primaryText,
    displayText: reason.primaryText,
    sourceRef: reason.source,
    count: reason.totalPointCount,
    sampleText: reason.displayName,
    sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
        ? <String>[reason.avatarUrl.trim()]
        : const <String>[],
  );
  final isRecommended = pointClass == 'recommended';
  return reason.copyWith(
    intersectionClass: isRecommended ? 'affinity' : 'fact',
    intersectionPoints: <IntersectionPoint>[point],
    pointSummarySnapshotId: reason.actionTargetId,
    factPointCount: isRecommended ? 0 : 1,
    recommendedPointCount: isRecommended ? 1 : 0,
    totalPointCount: 1,
    dimensionPointSummary: <IntersectionDimensionTally>[
      IntersectionDimensionTally(
        dimension: reason.dimension,
        label: reason.primaryText,
        count: 1,
      ),
    ],
    pointClassLabel: isRecommended ? '推荐交集' : '事实交集',
    rankState: 'fresh',
  );
}

String _canonicalEntityId(HomepageDetail homepage) {
  final explicit = homepage.canonicalEntityId?.trim() ?? '';
  if (explicit.isNotEmpty) {
    return explicit;
  }
  final type = homepage.homepageType.trim();
  final slug = _canonicalSlug(homepage.title);
  if (type.isEmpty || slug.isEmpty) {
    return '';
  }
  return 'entity:$type:$slug';
}

String _canonicalSlug(String value) {
  final trimmed = value.trim().toLowerCase();
  if (trimmed.isEmpty) {
    return '';
  }
  final normalized = trimmed.replaceAll(RegExp(r'[\s/-]+'), '_');
  return normalized
      .replaceAll(RegExp(r'_+'), '_')
      .replaceAll(RegExp(r'^_|_$'), '');
}

String _objectPageTemplate(HomepageDetail homepage) {
  return switch (homepage.homepageType) {
    'university' => 'campus',
    'travel_photo' || 'sight' => 'travel_photo',
    _ => 'standard',
  };
}
