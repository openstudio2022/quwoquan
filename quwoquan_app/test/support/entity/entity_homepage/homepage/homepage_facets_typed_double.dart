import 'package:quwoquan_app/application/entity/homepage_operation_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_entity_contracts.dart'
    as wire;

import '../../../cloud_services/object_doubles/object_scenario_seed_reader.dart';

/// 由不可变 Entity 场景数据驱动的 local_contract typed adapter。
///
/// 该替身只实现 canonical generated ports，环境 App 与生产 composition 不可达。
final class AlphaHomepageFacet
    implements
        HomepageQueryFacet,
        HomepageIntroductionQuery,
        HomepageCandidateCommandWriter,
        HomepageClaimRequestCommandWriter,
        HomepageStatusReportCommandWriter {
  AlphaHomepageFacet({
    ObjectScenarioSeedReader? seedReader,
    DateTime Function()? clock,
  }) : _clock = clock ?? (() => DateTime.now().toUtc()),
       _records = _recordsFromFixture(
         (seedReader ?? objectScenarioSeedReader).requireSeedSet(
           'entity',
           'entity_homepage_core',
         ),
       );

  final DateTime Function() _clock;
  final Map<String, _AlphaHomepageRecord> _records;
  final List<HomepageClaimRequestView> _claimRequests =
      <HomepageClaimRequestView>[];
  final List<HomepageStatusReportView> _statusReports =
      <HomepageStatusReportView>[];

  @override
  Future<HomepageSearchSlice> searchHomepages(
    HomepageSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    cancellation?.throwIfCancelled();
    if (query.limit <= 0) {
      throw ArgumentError.value(query.limit, 'limit', 'must be positive');
    }
    final normalizedQuery = _normalize(query.query);
    final normalizedType = _normalize(query.homepageType);
    final normalizedCity = _normalize(query.city);
    final normalizedStatus = _normalize(query.status);
    final items = <HomepageSearchItemView>[];
    for (final record in _records.values) {
      final homepage = record.detail;
      if (normalizedType.isNotEmpty &&
          _normalize(homepage.homepageType) != normalizedType) {
        continue;
      }
      if (normalizedCity.isNotEmpty &&
          _normalize(homepage.city) != normalizedCity) {
        continue;
      }
      if (normalizedStatus.isNotEmpty) {
        if (_normalize(homepage.status) != normalizedStatus) continue;
      } else if (_normalize(homepage.status) != 'published') {
        continue;
      }
      if (normalizedQuery.isNotEmpty &&
          !_searchHaystack(homepage).contains(normalizedQuery)) {
        continue;
      }
      final homepageType = _canonicalHomepageType(homepage.homepageType);
      if (homepageType == null) {
        continue;
      }
      items.add(
        HomepageSearchItemView(
          homepageId: homepage.homepageId,
          homepageType: homepageType,
          title: homepage.title,
          canonicalEntityId: record.canonicalEntityId,
          subtitle: homepage.subtitle,
          coverUrl: homepage.coverUrl,
          city: homepage.city,
          address: homepage.address,
          status: HomepageStatus.fromWire(
            homepage.status,
            'AlphaHomepageFacet.status',
          ),
          averageRating: homepage.averageRating,
          ratingCount: homepage.ratingCount,
        ),
      );
      if (items.length == query.limit) break;
    }
    cancellation?.throwIfCancelled();
    return HomepageSearchSlice(items: items);
  }

  @override
  Future<HomepageDetailView> getHomepageDetail(String homepageId) async {
    return _require(homepageId).detail;
  }

  @override
  Future<HomepageShellView> getHomepageShell(String homepageId) async {
    final detail = _require(homepageId).detail;
    final summary = detail.reviewSummary;
    return HomepageShellView(
      homepage: detail,
      reviewSummary: summary == null
          ? null
          : HomepageReviewSummaryData(
              averageRating: summary.averageRating,
              ratingCount: summary.ratingCount,
              highlightTags: summary.highlightTags ?? const <String>[],
            ),
      contentPreview: detail.contentPreview,
      questionPreview: detail.questionPreview,
      relatedGroups: detail.relatedGroups,
    );
  }

  @override
  Future<ObjectPageBundle> getObjectPageBundle(
    HomepageObjectPageBundleQuery query,
  ) async {
    final record = _require(query.homepageId);
    final detail = record.detail;
    final canonicalEntityId = record.canonicalEntityId.trim();
    if (canonicalEntityId.isEmpty) {
      throw StateError(
        'entity fixture homepage "${detail.homepageId}" lacks canonicalEntityId',
      );
    }
    final related = detail.relatedGroups;
    return ObjectPageBundle(
      objectType: 'homepage',
      objectId: detail.homepageId,
      canonicalEntityId: canonicalEntityId,
      title: detail.title,
      subtitle: detail.subtitle,
      coverUrl: detail.coverUrl,
      objectPageTemplate: record.objectPageTemplate,
      tagRefs: detail.categoryTags,
      stats: <String, Object?>{
        'ratingCount': detail.ratingCount,
        'relatedGroupCount': related.length,
        'highlightCount': detail.contentPreview.length,
      },
      intersectionReasons: const <wire.IntersectionReason>[],
      highlightItems: detail.contentPreview,
      contentSections: <String, Object?>{
        'home': detail.contentPreview.map((item) => item.toWire()).toList(),
        'related': related.map((item) => item.toWire()).toList(),
      },
      relatedObjects: related,
      relationEdges: const <ObjectRelationEdge>[],
      assistantContext: ObjectPageContext(
        objectType: 'homepage',
        objectId: detail.homepageId,
        canonicalEntityId: canonicalEntityId,
        tagRefs: detail.categoryTags,
        entityRefs: <String>[canonicalEntityId],
        relationEdgeIds: const <String>[],
        referralSource: query.referralSource ?? '',
        feedRequestId: query.feedRequestId ?? '',
        recommendationTraceId: query.recommendationTraceId ?? '',
        experimentBucket: query.experimentBucket ?? '',
        rolloutCohort: query.rolloutCohort ?? '',
      ),
      rolloutContext: ObjectPageRolloutContext(
        enabled: true,
        cohort: query.rolloutCohort ?? '',
        region: '',
        city: detail.city ?? '',
        campus: '',
        appVersion: '',
        experimentBucket: query.experimentBucket ?? '',
        objectType: detail.homepageType,
        assistantProactiveEnabled: false,
        relationEvidenceEnabled: false,
      ),
    );
  }

  @override
  Future<HomepageReviewSummaryView> getHomepageReviewSummary(
    String homepageId,
  ) async {
    return _require(homepageId).detail.reviewSummary ??
        const HomepageReviewSummaryView(
          ratingCount: 0,
          highlightTags: <String>[],
        );
  }

  @override
  Future<EntityImpactSummary> getEntityImpact(String homepageId) async {
    final record = _require(homepageId);
    return record.impact ??
        EntityImpactSummary(
          homepageId: record.detail.homepageId,
          total: 0,
          items: const <EntityImpactItem>[],
        );
  }

  @override
  Future<HomepageRelatedGroupSummaryView> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    return HomepageRelatedGroupSummaryView(
      groups: _require(homepageId).detail.relatedGroups,
    );
  }

  @override
  Future<HomepageIntroduction> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    final raw = _require(homepageId).introduction;
    if (raw == null) {
      throw StateError(
        'entity fixture homepage "$homepageId" lacks introduction projection',
      );
    }
    final result = _introductionFromFixture(raw);
    cancellation?.throwIfCancelled();
    return result;
  }

  @override
  Future<HomepageDetailView> suggest(
    SuggestHomepageCandidateCommand command,
  ) async {
    final now = _clock();
    final homepageId = 'alpha_homepage_candidate_${_records.length + 1}';
    final detail = HomepageDetailView(
      homepageId: homepageId,
      homepageType: command.homepageType,
      title: command.title,
      subtitle: command.subtitle,
      coverUrl: command.coverUrl,
      status: 'candidate',
      claimStatus: 'unclaimed',
      categoryTags: command.categoryTags,
      address: command.address,
      city: command.city,
      location: command.location == null
          ? null
          : HomepageGeoPoint(
              latitude: command.location!.lat,
              longitude: command.location!.lng,
            ),
      viewerFollow: const HomepageViewerFollowSlice(
        viewerFollowsHomepage: false,
        followerCount: 0,
      ),
      verified: false,
      ratingCount: 0,
      contentPreview: const <HomepageContentPreview>[],
      questionPreview: const <HomepageQuestionPreview>[],
      relatedGroups: const <HomepageRelatedGroupSummary>[],
      relationEdges: const <ObjectRelationEdge>[],
      introductionAssets: const <HomepageIntroductionAsset>[],
      sourceUrls: const <String>[],
      createdAt: now,
      updatedAt: now,
    );
    _records[homepageId] = _AlphaHomepageRecord(
      detail: detail,
      canonicalEntityId: '',
      objectPageTemplate: 'standard',
    );
    return detail;
  }

  @override
  Future<HomepageDetailView> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  ) async {
    final currentRecord = _require(command.homepageId);
    final current = currentRecord.detail;
    final updated = HomepageDetailView(
      homepageId: current.homepageId,
      homepageType: current.homepageType,
      title: command.title ?? current.title,
      subtitle: command.subtitle ?? current.subtitle,
      coverUrl: command.coverUrl ?? current.coverUrl,
      status: current.status,
      claimStatus: current.claimStatus,
      categoryTags: command.categoryTags ?? current.categoryTags,
      address: command.address ?? current.address,
      city: command.city ?? current.city,
      location: command.location == null
          ? current.location
          : HomepageGeoPoint(
              latitude: command.location!.lat,
              longitude: command.location!.lng,
            ),
      ownerUserId: current.ownerUserId,
      ownerPersonaId: current.ownerPersonaId,
      viewerFollow: current.viewerFollow,
      verified: current.verified,
      establishedYear: current.establishedYear,
      averageRating: current.averageRating,
      ratingCount: current.ratingCount,
      reviewSummary: current.reviewSummary,
      contentPreview: current.contentPreview,
      questionPreview: current.questionPreview,
      relatedGroups: current.relatedGroups,
      structuredFacts: current.structuredFacts,
      relationEdges: current.relationEdges,
      assistantContext: current.assistantContext,
      introductionMarkdown: current.introductionMarkdown,
      introductionAssets: current.introductionAssets,
      primarySource: current.primarySource,
      sourceUrls: current.sourceUrls,
      createdAt: current.createdAt,
      updatedAt: _clock(),
      publishedAt: current.publishedAt,
      offlineAt: current.offlineAt,
    );
    _records[updated.homepageId] = _AlphaHomepageRecord(
      detail: updated,
      canonicalEntityId: currentRecord.canonicalEntityId,
      objectPageTemplate: currentRecord.objectPageTemplate,
      introduction: currentRecord.introduction,
      impact: currentRecord.impact,
    );
    return updated;
  }

  @override
  Future<HomepageClaimRequestView> createClaimRequest(
    CreateHomepageClaimRequestCommand command,
  ) async {
    _require(command.homepageId);
    final record = HomepageClaimRequestView(
      claimRequestId: 'alpha_homepage_claim_${_claimRequests.length + 1}',
      homepageId: command.homepageId,
      requesterPersonaId: 'alpha-persona',
      claimTier: HomepageClaimTier.fromWire(
        command.claimTier,
        'AlphaHomepageFacet.claimTier',
      ),
      status: HomepageClaimReviewStatus.pendingReview,
      createdAt: _clock(),
    );
    _claimRequests.add(record);
    return record;
  }

  @override
  Future<HomepageStatusReportView> createStatusReport(
    CreateHomepageStatusReportCommand command,
  ) async {
    _require(command.homepageId);
    final record = HomepageStatusReportView(
      reportId: 'alpha_homepage_report_${_statusReports.length + 1}',
      homepageId: command.homepageId,
      reporterPersonaId: 'alpha-persona',
      reason: HomepageStatusReportReason.fromWire(
        command.reason,
        'AlphaHomepageFacet.reason',
      ),
      status: HomepageStatusReportStatus.pendingReview,
      description: command.description,
      evidenceUrls: command.evidenceUrls,
      createdAt: _clock(),
    );
    _statusReports.add(record);
    return record;
  }

  _AlphaHomepageRecord _require(String homepageId) {
    final lookup = homepageId.trim();
    final direct = _records[lookup];
    if (direct != null) return direct;
    for (final record in _records.values) {
      if (record.canonicalEntityId == lookup) return record;
    }
    throw HomepageQueryNotFoundException(lookup);
  }
}

final class _AlphaHomepageRecord {
  const _AlphaHomepageRecord({
    required this.detail,
    required this.canonicalEntityId,
    required this.objectPageTemplate,
    this.introduction,
    this.impact,
  });

  final HomepageDetailView detail;
  final String canonicalEntityId;
  final String objectPageTemplate;
  final Map<String, Object?>? introduction;
  final EntityImpactSummary? impact;
}

Map<String, _AlphaHomepageRecord> _recordsFromFixture(
  Map<String, Object?> seed,
) {
  final rawRows = seed['homepages'];
  if (rawRows is! List<Object?>) {
    throw const FormatException('entity fixture homepages must be a list');
  }
  final records = <String, _AlphaHomepageRecord>{};
  for (final raw in rawRows) {
    final row = _requiredObject(raw, 'entity fixture homepage');
    final detail = _detailFromFixture(row);
    records[detail.homepageId] = _AlphaHomepageRecord(
      detail: detail,
      canonicalEntityId: _optionalText(row['canonicalEntityId']) ?? '',
      objectPageTemplate:
          _optionalText(row['objectPageTemplate']) ?? 'standard',
      introduction: _optionalObject(row['introduction']),
      impact: _optionalObject(row['impactSummary']) == null
          ? null
          : _impactSummaryFromFixture(
              _optionalObject(row['impactSummary'])!,
              homepageId: detail.homepageId,
            ),
    );
  }
  return records;
}

HomepageDetailView _detailFromFixture(Map<String, Object?> row) {
  final summary = _optionalReviewSummary(row['reviewSummary']);
  final introduction = _optionalObject(row['introduction']);
  return HomepageDetailView(
    homepageId: _requiredText(row['homepageId'], 'homepageId'),
    homepageType: _requiredText(row['homepageType'], 'homepageType'),
    title: _requiredText(row['title'], 'title'),
    subtitle: _optionalText(row['subtitle']),
    coverUrl: _optionalText(row['coverUrl']),
    status: _optionalText(row['status']) ?? 'published',
    claimStatus: _optionalText(row['claimStatus']) ?? 'unclaimed',
    categoryTags: _stringList(row['categoryTags'], 'categoryTags'),
    address: _optionalText(row['address']),
    city: _optionalText(row['city']),
    location: _optionalGeoPoint(row['geo']),
    ownerUserId: _optionalText(row['ownerUserId']),
    ownerPersonaId: _optionalText(row['ownerPersonaId']),
    viewerFollow: HomepageViewerFollowSlice(
      viewerFollowsHomepage: row['viewerFollowsHomepage'] == true,
      followerCount: _optionalInt(row['followerCount']) ?? 0,
    ),
    verified: row['verified'] == true,
    establishedYear: _optionalInt(row['establishedYear']),
    averageRating: _optionalDouble(row['averageRating']),
    ratingCount: _optionalInt(row['ratingCount']) ?? 0,
    reviewSummary: summary,
    contentPreview: _contentPreviews(row['contentPreview']),
    questionPreview: _questionPreviews(row['questionPreview']),
    relatedGroups: _relatedGroups(row['relatedGroups']),
    relationEdges: const <ObjectRelationEdge>[],
    introductionMarkdown: introduction == null
        ? null
        : _optionalText(introduction['summary']),
    introductionAssets: const <HomepageIntroductionAsset>[],
    sourceUrls: const <String>[],
    createdAt: _dateTimeOrEpoch(row['createdAt'], 'createdAt'),
    updatedAt: _dateTimeOrEpoch(row['updatedAt'], 'updatedAt'),
    publishedAt: _optionalDateTime(row['publishedAt'], 'publishedAt'),
    offlineAt: _optionalDateTime(row['offlineAt'], 'offlineAt'),
  );
}

List<HomepageContentPreview> _contentPreviews(Object? raw) {
  return _objectList(raw, 'contentPreview')
      .map(
        (row) => HomepageContentPreview(
          postId: _requiredText(row['postId'], 'contentPreview.postId'),
          title: _requiredText(row['title'], 'contentPreview.title'),
          summary: _optionalText(row['summary']),
          contentType: _optionalText(row['contentType']),
          coverUrl: _optionalText(row['coverUrl']),
          authorName: _optionalText(row['authorName']),
          likeCount: _optionalInt(row['likeCount']) ?? 0,
          intersectionReasons: _objectList(
            row['intersectionReasons'],
            'contentPreview.intersectionReasons',
          ).map(_intersectionReasonFromFixture).toList(growable: false),
        ),
      )
      .toList(growable: false);
}

wire.IntersectionReason _intersectionReasonFromFixture(
  Map<String, Object?> row,
) {
  return wire.IntersectionReason(
    kind: _optionalText(row['kind']) ?? '',
    vertical: _optionalText(row['vertical']) ?? 'general',
    dimension: _optionalText(row['dimension']) ?? '',
    tagRefs: _stringList(row['tagRefs'], 'intersectionReason.tagRefs'),
    relationKind: _optionalText(row['relationKind']) ?? '',
    objectKind: _optionalText(row['objectKind']) ?? '',
    relationObjectId: _optionalText(row['relationObjectId']) ?? '',
    strength: _optionalDouble(row['strength']) ?? 0,
    primaryText: _optionalText(row['primaryText']) ?? '',
    primaryTextL10nKey: _optionalText(row['primaryTextL10nKey']) ?? '',
    displayBinding: _optionalText(row['displayBinding']) ?? 'host_plain',
    secondaryText: _optionalText(row['secondaryText']) ?? '',
    weightTier: _optionalText(row['weightTier']) ?? '',
    actionType: _optionalText(row['actionType']) ?? '',
    actionTargetId: _optionalText(row['actionTargetId']) ?? '',
    source: _optionalText(row['source']) ?? '',
    intersectionId: _optionalText(row['intersectionId']) ?? '',
    intersectionClass: _optionalText(row['intersectionClass']) ?? 'fact',
    avatarUrl: _optionalText(row['avatarUrl']) ?? '',
    displayName: _optionalText(row['displayName']) ?? '',
    confidenceLabel: _optionalText(row['confidenceLabel']) ?? '',
    modelReasonBucket: _optionalText(row['modelReasonBucket']) ?? '',
    freshAt: _optionalText(row['freshAt']) ?? '',
    expiresAt: _optionalText(row['expiresAt']) ?? '',
    intersectionPoints: const <wire.IntersectionPoint>[],
    pointSummarySnapshotId: _optionalText(row['pointSummarySnapshotId']) ?? '',
    actorEvidenceTotalCount: _optionalInt(row['actorEvidenceTotalCount']) ?? 0,
    actorEvidenceCompleteness:
        _optionalText(row['actorEvidenceCompleteness']) ?? 'unknown',
    actorEvidence: const <wire.IntersectionActorEvidence>[],
    factPointCount: _optionalInt(row['factPointCount']) ?? 0,
    recommendedPointCount: _optionalInt(row['recommendedPointCount']) ?? 0,
    totalPointCount: _optionalInt(row['totalPointCount']) ?? 0,
    dimensionPointSummary: const <wire.IntersectionDimensionTally>[],
    pointClassLabel: _optionalText(row['pointClassLabel']) ?? '',
    connectionSummary: _optionalText(row['connectionSummary']) ?? '',
    lastRecommendedAt: _optionalText(row['lastRecommendedAt']) ?? '',
    seenAt: _optionalText(row['seenAt']) ?? '',
    rankState: _optionalText(row['rankState']) ?? 'fresh',
    primarySpans: const <wire.IntersectionTextSpan>[],
    sampleVisuals: const <wire.IntersectionVisual>[],
    actionHints: const <wire.IntersectionActionHint>[],
    lifecycleState: _optionalText(row['lifecycleState']) ?? '',
    previousStrength: _optionalDouble(row['previousStrength']) ?? 0,
    strengthDelta: _optionalDouble(row['strengthDelta']) ?? 0,
    edgeWeight: _optionalDouble(row['edgeWeight']) ?? 0,
    iconKey: _optionalText(row['iconKey']) ?? '',
    tone: _optionalText(row['tone']) ?? '',
    timeBucket: _optionalText(row['timeBucket']) ?? '',
    dedupeKey: _optionalText(row['dedupeKey']) ?? '',
    anchorUserWeight: _optionalDouble(row['anchorUserWeight']) ?? 0,
    mutualCount: _optionalInt(row['mutualCount']) ?? 0,
    moment: _optionalText(row['moment']) ?? 'current',
    subjectId: _optionalText(row['subjectId']) ?? '',
    subjectContext: _optionalText(row['subjectContext']) ?? '',
  );
}

List<HomepageQuestionPreview> _questionPreviews(Object? raw) {
  return _objectList(raw, 'questionPreview')
      .map(
        (row) => HomepageQuestionPreview(
          postId: _requiredText(row['postId'], 'questionPreview.postId'),
          title: _requiredText(row['title'], 'questionPreview.title'),
          summary: _optionalText(row['summary']),
        ),
      )
      .toList(growable: false);
}

EntityImpactSummary _impactSummaryFromFixture(
  Map<String, Object?> raw, {
  required String homepageId,
}) {
  final items = _objectList(raw['items'], 'impactSummary.items')
      .map(
        (item) => EntityImpactItem(
          helpType: _optionalText(item['helpType']) ?? '',
          action: _optionalText(item['action']) ?? '',
          intersectionDimension:
              _optionalText(item['intersectionDimension']) ?? '',
          tagRef: _optionalText(item['tagRef']) ?? '',
          source: _optionalText(item['source']) ?? '',
          count: _optionalInt(item['count']) ?? 0,
          primaryText: _optionalText(item['primaryText']) ?? '',
          subtitleText: _optionalText(item['subtitleText']) ?? '',
          impactId: _optionalText(item['impactId']) ?? '',
          primarySpans: const <wire.IntersectionTextSpan>[],
          sampleVisuals: const <wire.IntersectionVisual>[],
          actionHints: const <wire.IntersectionActionHint>[],
          evidenceSnapshotId: _optionalText(item['evidenceSnapshotId']) ?? '',
          countObjectKind: _optionalText(item['countObjectKind']) ?? '',
          iconKey: _optionalText(item['iconKey']) ?? '',
        ),
      )
      .toList(growable: false);
  return EntityImpactSummary(
    homepageId: _optionalText(raw['homepageId']) ?? homepageId,
    total: _optionalInt(raw['total']) ?? items.length,
    items: items,
  );
}

HomepageIntroduction _introductionFromFixture(Map<String, Object?> raw) {
  return HomepageIntroduction(
    homepageId: _requiredText(raw['homepageId'], 'introduction.homepageId'),
    displayName: _requiredText(raw['displayName'], 'introduction.displayName'),
    homepageType: _requiredText(
      raw['homepageType'],
      'introduction.homepageType',
    ),
    coverUrl: _optionalText(raw['coverUrl']),
    summary: _optionalText(raw['summary']) ?? '',
    sections: _objectList(raw['sections'], 'introduction.sections')
        .map(
          (section) => HomepageIntroductionSection(
            kind: _optionalText(section['kind']) ?? '',
            title: _optionalText(section['title']) ?? '',
            bodyMarkdown: _optionalText(section['bodyMarkdown']),
            assets:
                _objectList(section['assets'], 'introduction.section.assets')
                    .map(
                      (asset) => HomepageIntroductionAsset(
                        assetId: _optionalText(asset['assetId']) ?? '',
                        url: _optionalText(asset['url']) ?? '',
                        caption: _optionalText(asset['caption']),
                        role: _optionalText(asset['role']) ?? '',
                      ),
                    )
                    .toList(growable: false),
            timelineItems:
                _objectList(
                      section['timelineItems'],
                      'introduction.section.timelineItems',
                    )
                    .map(
                      (item) => HomepageIntroductionTimelineItem(
                        dateLabel: _optionalText(item['dateLabel']) ?? '',
                        text: _optionalText(item['text']) ?? '',
                        assetUrl: _optionalText(item['assetUrl']),
                      ),
                    )
                    .toList(growable: false),
          ),
        )
        .toList(growable: false),
    relatedObjects: _relatedGroups(raw['relatedObjects']),
    sourceUrls: _stringList(raw['sourceUrls'], 'introduction.sourceUrls'),
    updatedAt: _optionalText(raw['updatedAt']) ?? '',
  );
}

HomepageReviewSummaryView? _optionalReviewSummary(Object? raw) {
  final row = _optionalObject(raw);
  if (row == null) return null;
  return HomepageReviewSummaryView(
    averageRating: _optionalDouble(row['averageRating']),
    ratingCount: _optionalInt(row['ratingCount']) ?? 0,
    highlightTags: _stringList(
      row['highlightTags'],
      'reviewSummary.highlightTags',
    ),
  );
}

List<HomepageRelatedGroupSummary> _relatedGroups(Object? raw) {
  return _objectList(raw, 'relatedGroups')
      .map(
        (row) => HomepageRelatedGroupSummary(
          circleId: _requiredText(row['circleId'], 'relatedGroups.circleId'),
          name: _requiredText(row['name'], 'relatedGroups.name'),
          memberCount: _optionalInt(row['memberCount']) ?? 0,
          linkedHomepageId: _optionalText(row['linkedHomepageId']),
          linkedHomepageTitle: _optionalText(row['linkedHomepageTitle']),
          ownerUserId: _optionalText(row['ownerUserId']) ?? '',
          ownerDisplayNameSnapshot:
              _optionalText(row['ownerDisplayNameSnapshot']) ?? '',
          ownerAvatarUrlSnapshot:
              _optionalText(row['ownerAvatarUrlSnapshot']) ?? '',
          evidenceSnapshotId: _optionalText(row['evidenceSnapshotId']) ?? '',
        ),
      )
      .toList(growable: false);
}

HomepageGeoPoint? _optionalGeoPoint(Object? raw) {
  final row = _optionalObject(raw);
  if (row == null) return null;
  return HomepageGeoPoint(
    latitude: _optionalDouble(row['lat']) ?? 0,
    longitude: _optionalDouble(row['lng']) ?? 0,
  );
}

HomepageType? _canonicalHomepageType(String raw) {
  try {
    return HomepageType.fromWire(raw, 'AlphaHomepageFacet.homepageType');
  } on FormatException {
    return null;
  }
}

String _searchHaystack(HomepageDetailView homepage) {
  return _normalize(
    <String>[
      homepage.title,
      homepage.subtitle ?? '',
      homepage.address ?? '',
      homepage.city ?? '',
      ...homepage.categoryTags,
    ].join(' '),
  );
}

String _normalize(String? value) => (value ?? '').trim().toLowerCase();

Map<String, Object?> _requiredObject(Object? raw, String context) {
  final value = _optionalObject(raw);
  if (value == null) throw FormatException('$context must be an object');
  return value;
}

Map<String, Object?>? _optionalObject(Object? raw) {
  if (raw == null) return null;
  if (raw is! Map<Object?, Object?>) {
    throw const FormatException('entity fixture object must be a map');
  }
  return raw.map((key, value) => MapEntry(key.toString(), value));
}

List<Map<String, Object?>> _objectList(Object? raw, String context) {
  if (raw == null) return const <Map<String, Object?>>[];
  if (raw is! List<Object?>) {
    throw FormatException('$context must be a list');
  }
  return raw
      .map((item) => _requiredObject(item, context))
      .toList(growable: false);
}

List<String> _stringList(Object? raw, String context) {
  if (raw == null) return const <String>[];
  if (raw is! List<Object?> || raw.any((item) => item is! String)) {
    throw FormatException('$context must be a string list');
  }
  return raw.cast<String>().toList(growable: false);
}

String _requiredText(Object? raw, String context) {
  final value = _optionalText(raw);
  if (value == null) {
    throw FormatException('$context must be a non-empty string');
  }
  return value;
}

String? _optionalText(Object? raw) {
  if (raw == null) return null;
  if (raw is! String) {
    throw const FormatException('entity fixture text value must be a string');
  }
  final value = raw.trim();
  return value.isEmpty ? null : value;
}

int? _optionalInt(Object? raw) {
  if (raw == null) return null;
  if (raw is! num) {
    throw const FormatException('entity fixture integer value must be numeric');
  }
  return raw.toInt();
}

double? _optionalDouble(Object? raw) {
  if (raw == null) return null;
  if (raw is! num) {
    throw const FormatException('entity fixture decimal value must be numeric');
  }
  return raw.toDouble();
}

DateTime _dateTimeOrEpoch(Object? raw, String context) {
  return _optionalDateTime(raw, context) ??
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
}

DateTime? _optionalDateTime(Object? raw, String context) {
  final value = _optionalText(raw);
  if (value == null) return null;
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw FormatException('$context must be ISO-8601');
  return parsed.toUtc();
}
