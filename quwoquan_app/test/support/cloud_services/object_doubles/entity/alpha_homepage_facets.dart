import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

/// 由不可变 entity fixture 驱动的 alpha/test Homepage typed adapter。
///
/// 不依赖 Flutter 或 App DTO；调用方只能通过 pure-contract projection 与 command
/// port 访问，避免 production App → mock → App 的反向依赖。
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
    final items = _records.values
        .where((record) {
          final homepage = record.detail;
          if (normalizedType.isNotEmpty &&
              _normalize(homepage.homepageType) != normalizedType) {
            return false;
          }
          if (normalizedCity.isNotEmpty &&
              _normalize(homepage.city) != normalizedCity) {
            return false;
          }
          if (normalizedStatus.isNotEmpty) {
            if (_normalize(homepage.status) != normalizedStatus) {
              return false;
            }
          } else if (_normalize(homepage.status) != 'published') {
            return false;
          }
          if (normalizedQuery.isEmpty) {
            return true;
          }
          return _searchHaystack(homepage).contains(normalizedQuery);
        })
        .take(query.limit)
        .map(
          (record) => HomepageSearchItemProjection(
            homepageId: record.detail.homepageId,
            homepageType: record.detail.homepageType,
            title: record.detail.title,
            canonicalEntityId: record.detail.canonicalEntityId,
            subtitle: record.detail.subtitle,
            coverUrl: record.detail.coverUrl,
            city: record.detail.city,
            address: record.detail.address,
            status: record.detail.status,
            averageRating: record.detail.averageRating,
            ratingCount: record.detail.ratingCount,
          ),
        )
        .toList(growable: false);
    cancellation?.throwIfCancelled();
    return HomepageSearchSlice(items: items);
  }

  @override
  Future<HomepageDetailProjection> getHomepageDetail(String homepageId) async {
    return _require(homepageId).detail;
  }

  @override
  Future<HomepageShellProjection> getHomepageShell(String homepageId) async {
    final detail = _require(homepageId).detail;
    return HomepageShellProjection(
      homepage: detail,
      reviewSummary: detail.reviewSummary,
      contentPreview: detail.contentPreview,
      questionPreview: detail.questionPreview,
      relatedGroups: detail.relatedGroups,
    );
  }

  @override
  Future<HomepageObjectPageBundleProjection> getObjectPageBundle(
    HomepageObjectPageBundleQuery query,
  ) async {
    final detail = _require(query.homepageId).detail;
    final canonicalEntityId = detail.canonicalEntityId.trim();
    if (canonicalEntityId.isEmpty) {
      throw StateError(
        'entity fixture homepage "${detail.homepageId}" lacks canonicalEntityId',
      );
    }
    final related = detail.relatedGroups;
    return HomepageObjectPageBundleProjection(
      objectType: 'homepage',
      objectId: detail.homepageId,
      canonicalEntityId: canonicalEntityId,
      title: detail.title,
      subtitle: detail.subtitle,
      coverUrl: detail.coverUrl,
      objectPageTemplate: detail.objectPageTemplate,
      tagRefs: detail.categoryTags,
      stats: CloudStructuredObject(<String, CloudStructuredValue>{
        'ratingCount': CloudStructuredNumber(detail.ratingCount),
        'relatedGroupCount': CloudStructuredNumber(related.length),
        'highlightCount': CloudStructuredNumber(detail.contentPreview.length),
      }),
      highlightItems: detail.contentPreview,
      contentSections: CloudStructuredObject(<String, CloudStructuredValue>{
        'home': CloudStructuredArray(detail.contentPreview),
        'related': CloudStructuredArray(
          related.map(_relatedGroupToStructuredObject),
        ),
      }),
      relatedObjects: related,
      assistantContext: CloudStructuredObject(<String, CloudStructuredValue>{
        'objectType': const CloudStructuredText('homepage'),
        'objectId': CloudStructuredText(detail.homepageId),
        'canonicalEntityId': CloudStructuredText(canonicalEntityId),
        'tagRefs': CloudStructuredArray(
          detail.categoryTags.map(CloudStructuredText.new),
        ),
        'entityRefs': CloudStructuredArray(<CloudStructuredValue>[
          CloudStructuredText(canonicalEntityId),
        ]),
        'referralSource': CloudStructuredText(query.referralSource ?? ''),
        'feedRequestId': CloudStructuredText(query.feedRequestId ?? ''),
        'recommendationTraceId': CloudStructuredText(
          query.recommendationTraceId ?? '',
        ),
        'experimentBucket': CloudStructuredText(query.experimentBucket ?? ''),
        'rolloutCohort': CloudStructuredText(query.rolloutCohort ?? ''),
      }),
      rolloutContext: CloudStructuredObject(<String, CloudStructuredValue>{
        'enabled': const CloudStructuredBoolean(true),
        'cohort': CloudStructuredText(query.rolloutCohort ?? ''),
        'city': CloudStructuredText(detail.city ?? ''),
        'objectType': CloudStructuredText(detail.homepageType),
      }),
    );
  }

  @override
  Future<HomepageReviewSummaryProjection> getHomepageReviewSummary(
    String homepageId,
  ) async {
    return _require(homepageId).detail.reviewSummary ??
        HomepageReviewSummaryProjection();
  }

  @override
  Future<HomepageImpactSummaryProjection> getEntityImpact(
    String homepageId,
  ) async {
    final record = _require(homepageId);
    return record.impact ??
        HomepageImpactSummaryProjection(homepageId: record.detail.homepageId);
  }

  @override
  Future<HomepageRelatedGroupsSlice> getHomepageRelatedGroups(
    String homepageId,
  ) async {
    return HomepageRelatedGroupsSlice(
      _require(homepageId).detail.relatedGroups,
    );
  }

  @override
  Future<HomepageIntroductionProjection> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    cancellation?.throwIfCancelled();
    final record = _require(homepageId);
    final raw = record.introduction;
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
  Future<HomepageDetailProjection> suggest(
    SuggestHomepageCandidateCommand command,
  ) async {
    final now = _clock();
    final homepageId = 'alpha_homepage_candidate_${_records.length + 1}';
    final detail = HomepageDetailProjection(
      homepageId: homepageId,
      homepageType: command.homepageType,
      title: command.title,
      subtitle: command.subtitle,
      coverUrl: command.coverUrl,
      status: 'candidate',
      sourceType: 'user_suggested',
      claimStatus: 'unclaimed',
      categoryTags: command.categoryTags,
      address: command.address,
      city: command.city,
      location: command.location == null
          ? null
          : _geoPointToStructuredObject(command.location!),
      createdAt: now,
      updatedAt: now,
    );
    _records[homepageId] = _AlphaHomepageRecord(detail: detail);
    return detail;
  }

  @override
  Future<HomepageDetailProjection> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  ) async {
    final currentRecord = _require(command.homepageId);
    final current = currentRecord.detail;
    final updated = HomepageDetailProjection(
      homepageId: current.homepageId,
      homepageType: current.homepageType,
      title: command.title ?? current.title,
      subtitle: command.subtitle ?? current.subtitle,
      coverUrl: command.coverUrl ?? current.coverUrl,
      status: current.status,
      canonicalEntityId: current.canonicalEntityId,
      objectPageTemplate: current.objectPageTemplate,
      sourceType: current.sourceType,
      claimStatus: current.claimStatus,
      categoryTags: command.categoryTags ?? current.categoryTags,
      address: command.address ?? current.address,
      city: command.city ?? current.city,
      location: command.location == null
          ? current.location
          : _geoPointToStructuredObject(command.location!),
      ownerUserId: current.ownerUserId,
      ownerSubAccountId: current.ownerSubAccountId,
      viewerFollowsHomepage: current.viewerFollowsHomepage,
      followerCount: current.followerCount,
      averageRating: current.averageRating,
      ratingCount: current.ratingCount,
      reviewSummary: current.reviewSummary,
      contentPreview: current.contentPreview,
      questionPreview: current.questionPreview,
      relatedGroups: current.relatedGroups,
      createdAt: current.createdAt,
      updatedAt: _clock(),
      publishedAt: current.publishedAt,
      offlineAt: current.offlineAt,
    );
    _records[updated.homepageId] = _AlphaHomepageRecord(
      detail: updated,
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
      claimTier: command.claimTier,
      status: 'pending_review',
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
      reason: command.reason,
      status: 'pending_review',
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
    if (direct != null) {
      return direct;
    }
    for (final record in _records.values) {
      if (record.detail.canonicalEntityId == lookup) {
        return record;
      }
    }
    throw HomepageQueryNotFoundException(lookup);
  }
}

final class _AlphaHomepageRecord {
  const _AlphaHomepageRecord({
    required this.detail,
    this.introduction,
    this.impact,
  });

  final HomepageDetailProjection detail;
  final Map<String, Object?>? introduction;
  final HomepageImpactSummaryProjection? impact;
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

HomepageDetailProjection _detailFromFixture(Map<String, Object?> row) {
  return HomepageDetailProjection(
    homepageId: _requiredText(row['homepageId'], 'homepageId'),
    homepageType: _requiredText(row['homepageType'], 'homepageType'),
    title: _requiredText(row['title'], 'title'),
    subtitle: _optionalText(row['subtitle']),
    coverUrl: _optionalText(row['coverUrl']),
    status: _optionalText(row['status']) ?? 'published',
    canonicalEntityId: _optionalText(row['canonicalEntityId']) ?? '',
    objectPageTemplate: _optionalText(row['objectPageTemplate']) ?? 'standard',
    sourceType: _optionalText(row['sourceType']),
    claimStatus: _optionalText(row['claimStatus']),
    categoryTags: _stringList(row['categoryTags'], 'categoryTags'),
    address: _optionalText(row['address']),
    city: _optionalText(row['city']),
    location: _optionalObject(row['geo']) == null
        ? null
        : _structuredObject(_optionalObject(row['geo'])!),
    ownerUserId: _optionalText(row['ownerUserId']),
    ownerSubAccountId: _optionalText(row['ownerSubAccountId']),
    viewerFollowsHomepage: row['viewerFollowsHomepage'] == true,
    followerCount: _optionalInt(row['followerCount']) ?? 0,
    averageRating: _optionalDouble(row['averageRating']),
    ratingCount: _optionalInt(row['ratingCount']) ?? 0,
    reviewSummary: _optionalReviewSummary(row['reviewSummary']),
    contentPreview: _structuredObjectList(
      row['contentPreview'],
      'contentPreview',
    ),
    questionPreview: _structuredObjectList(
      row['questionPreview'],
      'questionPreview',
    ),
    relatedGroups: _relatedGroups(row['relatedGroups']),
    createdAt: _optionalDateTime(row['createdAt'], 'createdAt'),
    updatedAt: _optionalDateTime(row['updatedAt'], 'updatedAt'),
    publishedAt: _optionalDateTime(row['publishedAt'], 'publishedAt'),
    offlineAt: _optionalDateTime(row['offlineAt'], 'offlineAt'),
  );
}

HomepageImpactSummaryProjection _impactSummaryFromFixture(
  Map<String, Object?> raw, {
  required String homepageId,
}) {
  final items = _objectList(raw['items'], 'impactSummary.items')
      .map(
        (item) => HomepageImpactItemProjection(
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
          primarySpans: _structuredObjectList(
            item['primarySpans'],
            'impactSummary.item.primarySpans',
          ),
          sampleVisuals: _structuredObjectList(
            item['sampleVisuals'],
            'impactSummary.item.sampleVisuals',
          ),
          representativeActor:
              _optionalObject(item['representativeActor']) == null
              ? null
              : _structuredObject(
                  _optionalObject(item['representativeActor'])!,
                ),
          actionHints: _structuredObjectList(
            item['actionHints'],
            'impactSummary.item.actionHints',
          ),
          countTarget: _optionalObject(item['countTarget']) == null
              ? null
              : _structuredObject(_optionalObject(item['countTarget'])!),
          evidenceSnapshotId: _optionalText(item['evidenceSnapshotId']) ?? '',
          countObjectKind: _optionalText(item['countObjectKind']) ?? '',
          propagationPath: _optionalObject(item['propagationPath']) == null
              ? null
              : _structuredObject(_optionalObject(item['propagationPath'])!),
          iconKey: _optionalText(item['iconKey']) ?? '',
        ),
      )
      .toList(growable: false);
  return HomepageImpactSummaryProjection(
    homepageId: _optionalText(raw['homepageId']) ?? homepageId,
    total: _optionalInt(raw['total']) ?? items.length,
    items: items,
  );
}

HomepageIntroductionProjection _introductionFromFixture(
  Map<String, Object?> raw,
) {
  return HomepageIntroductionProjection(
    homepageId: _requiredText(raw['homepageId'], 'introduction.homepageId'),
    displayName: _requiredText(raw['displayName'], 'introduction.displayName'),
    homepageType: _requiredText(
      raw['homepageType'],
      'introduction.homepageType',
    ),
    coverUrl: _optionalText(raw['coverUrl']),
    summary: _optionalText(raw['summary']) ?? '',
    sections: _objectList(raw['sections'], 'introduction.sections').map(
      (section) => HomepageIntroductionSectionProjection(
        kind: _optionalText(section['kind']) ?? '',
        title: _optionalText(section['title']) ?? '',
        bodyMarkdown: _optionalText(section['bodyMarkdown']) ?? '',
        assets: _objectList(section['assets'], 'introduction.section.assets')
            .map(
              (asset) => HomepageIntroductionAssetProjection(
                assetId: _optionalText(asset['assetId']) ?? '',
                url: _optionalText(asset['url']) ?? '',
                caption: _optionalText(asset['caption']) ?? '',
                role: _optionalText(asset['role']) ?? '',
                sourceUrl: _optionalText(asset['sourceUrl']) ?? '',
                width: _optionalInt(asset['width']),
                height: _optionalInt(asset['height']),
              ),
            ),
        timelineItems:
            _objectList(
              section['timelineItems'],
              'introduction.section.timelineItems',
            ).map(
              (item) => HomepageIntroductionTimelineProjection(
                dateLabel: _optionalText(item['dateLabel']) ?? '',
                text: _optionalText(item['text']) ?? '',
              ),
            ),
      ),
    ),
    relatedObjects: _relatedGroups(raw['relatedObjects']),
    sourceUrls: _stringList(raw['sourceUrls'], 'introduction.sourceUrls'),
    updatedAt: _optionalText(raw['updatedAt']) ?? '',
  );
}

HomepageReviewSummaryProjection? _optionalReviewSummary(Object? raw) {
  final row = _optionalObject(raw);
  if (row == null) return null;
  return HomepageReviewSummaryProjection(
    averageRating: _optionalDouble(row['averageRating']),
    ratingCount: _optionalInt(row['ratingCount']) ?? 0,
    highlightTags: _stringList(
      row['highlightTags'],
      'reviewSummary.highlightTags',
    ),
  );
}

List<HomepageRelatedGroupProjection> _relatedGroups(Object? raw) {
  return _objectList(raw, 'relatedGroups')
      .map(
        (row) => HomepageRelatedGroupProjection(
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

CloudStructuredObject _relatedGroupToStructuredObject(
  HomepageRelatedGroupProjection group,
) {
  return CloudStructuredObject(<String, CloudStructuredValue>{
    'circleId': CloudStructuredText(group.circleId),
    'name': CloudStructuredText(group.name),
    'memberCount': CloudStructuredNumber(group.memberCount),
    if (group.linkedHomepageId case final value?)
      'linkedHomepageId': CloudStructuredText(value),
    if (group.linkedHomepageTitle case final value?)
      'linkedHomepageTitle': CloudStructuredText(value),
    'ownerUserId': CloudStructuredText(group.ownerUserId),
    'ownerDisplayNameSnapshot': CloudStructuredText(
      group.ownerDisplayNameSnapshot,
    ),
    'ownerAvatarUrlSnapshot': CloudStructuredText(group.ownerAvatarUrlSnapshot),
    'evidenceSnapshotId': CloudStructuredText(group.evidenceSnapshotId),
  });
}

CloudStructuredObject _geoPointToStructuredObject(HomepageGeoPointInput point) {
  return CloudStructuredObject(<String, CloudStructuredValue>{
    'lat': CloudStructuredNumber(point.lat),
    'lng': CloudStructuredNumber(point.lng),
  });
}

List<CloudStructuredObject> _structuredObjectList(Object? raw, String context) {
  return _objectList(
    raw,
    context,
  ).map(_structuredObject).toList(growable: false);
}

CloudStructuredObject _structuredObject(Map<String, Object?> raw) {
  return CloudStructuredObject(
    raw.map((key, value) => MapEntry(key, _structuredValue(value))),
  );
}

CloudStructuredValue _structuredValue(Object? value) {
  return switch (value) {
    null => const CloudStructuredNull(),
    String() => CloudStructuredText(value),
    num() => CloudStructuredNumber(value),
    bool() => CloudStructuredBoolean(value),
    List<Object?>() => CloudStructuredArray(value.map(_structuredValue)),
    Map<Object?, Object?>() => _structuredObject(
      value.map((key, value) => MapEntry(key.toString(), value)),
    ),
    _ => throw FormatException(
      'entity fixture contains unsupported structured value ${value.runtimeType}',
    ),
  };
}

String _searchHaystack(HomepageDetailProjection homepage) {
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
  if (value == null) {
    throw FormatException('$context must be an object');
  }
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

DateTime? _optionalDateTime(Object? raw, String context) {
  final value = _optionalText(raw);
  if (value == null) return null;
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('$context must be ISO-8601');
  }
  return parsed.toUtc();
}
