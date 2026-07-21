import '../operation_request_payload.dart';
import '../operation_cancellation.dart';
import '../structured_value.dart';
import 'homepage_models.dart';

export 'homepage_models.dart';

/// Homepage 查询目标不存在时的纯契约失败。
///
/// alpha/test adapter 以此表达 fixture 缺失，App projection 再映射为 metadata
/// 生成的实体错误码，避免 mock package 反向依赖 App runtime。
final class HomepageQueryNotFoundException implements Exception {
  const HomepageQueryNotFoundException(this.homepageId);

  final String homepageId;
}

/// Homepage 读模型的对象级 typed port。
///
/// Remote adapter 与 alpha/test adapter 均只实现此 pure-contract 边界；
/// App 再将 projection 映射为页面 DTO。
abstract interface class HomepageQueryFacet {
  Future<HomepageSearchSlice> searchHomepages(
    HomepageSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });

  Future<HomepageDetailProjection> getHomepageDetail(String homepageId);

  Future<HomepageShellProjection> getHomepageShell(String homepageId);

  Future<HomepageObjectPageBundleProjection> getObjectPageBundle(
    HomepageObjectPageBundleQuery query,
  );

  Future<HomepageReviewSummaryProjection> getHomepageReviewSummary(
    String homepageId,
  );

  Future<HomepageImpactSummaryProjection> getEntityImpact(String homepageId);

  Future<HomepageRelatedGroupsSlice> getHomepageRelatedGroups(
    String homepageId,
  );
}

/// Homepage 介绍页的独立 typed query port。
abstract interface class HomepageIntroductionQuery {
  Future<HomepageIntroductionProjection> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  });
}

final class HomepageSearchQuery {
  const HomepageSearchQuery({
    required this.query,
    this.homepageType,
    this.city,
    this.status,
    this.cursor,
    this.limit = 20,
  });

  final String query;
  final String? homepageType;
  final String? city;
  final String? status;
  final String? cursor;
  final int limit;
}

final class HomepageByIdQuery {
  const HomepageByIdQuery({required this.homepageId});

  final String homepageId;
}

final class HomepageObjectPageBundleQuery {
  const HomepageObjectPageBundleQuery({
    required this.homepageId,
    this.referralSource,
    this.feedRequestId,
    this.recommendationTraceId,
    this.experimentBucket,
    this.rolloutCohort,
  });

  final String homepageId;
  final String? referralSource;
  final String? feedRequestId;
  final String? recommendationTraceId;
  final String? experimentBucket;
  final String? rolloutCohort;
}

CloudOperationRequestPayload encodeHomepageSearchQuery(
  HomepageSearchQuery query,
) {
  final value = _requiredText(query.query, 'query');
  _validateLimit(query.limit);
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      'query': value,
      if (_optionalText(query.homepageType) case final homepageType?)
        'homepageType': homepageType,
      if (_optionalText(query.city) case final city?) 'city': city,
      if (_optionalText(query.status) case final status?) 'status': status,
      if (_optionalText(query.cursor) case final cursor?) 'cursor': cursor,
      'limit': '${query.limit}',
    },
  );
}

CloudOperationRequestPayload encodeHomepageByIdQuery(HomepageByIdQuery query) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'homepageId': _requiredText(query.homepageId, 'homepageId'),
    },
  );
}

CloudOperationRequestPayload encodeHomepageObjectPageBundleQuery(
  HomepageObjectPageBundleQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'homepageId': _requiredText(query.homepageId, 'homepageId'),
    },
    queryParameters: <String, String>{
      if (_optionalText(query.referralSource) case final value?)
        'referralSource': value,
      if (_optionalText(query.feedRequestId) case final value?)
        'feedRequestId': value,
      if (_optionalText(query.recommendationTraceId) case final value?)
        'recommendationTraceId': value,
      if (_optionalText(query.experimentBucket) case final value?)
        'experimentBucket': value,
      if (_optionalText(query.rolloutCohort) case final value?)
        'rolloutCohort': value,
    },
  );
}

HomepageSearchSlice decodeHomepageSearchSlice(Object? response) {
  final root = _expectObject(response, 'Homepage search response');
  return HomepageSearchSlice(
    items: _objectList(
      root['items'],
      'Homepage search response.items',
    ).map(_decodeSearchItem),
    nextCursor: _optionalText(root['nextCursor']),
  );
}

HomepageDetailProjection decodeHomepageDetail(Object? response) {
  return _decodeHomepageDetail(
    _expectObject(response, 'Homepage detail response'),
  );
}

HomepageShellProjection decodeHomepageShell(Object? response) {
  final root = _expectObject(response, 'Homepage shell response');
  return HomepageShellProjection(
    homepage: _decodeHomepageDetail(
      _expectObject(root['homepage'], 'Homepage shell response.homepage'),
    ),
    reviewSummary: _optionalReviewSummary(root['reviewSummary']),
    contentPreview: _structuredObjectList(
      root['contentPreview'],
      'Homepage shell response.contentPreview',
    ),
    questionPreview: _structuredObjectList(
      root['questionPreview'],
      'Homepage shell response.questionPreview',
    ),
    relatedGroups: _relatedGroups(root['relatedGroups']),
  );
}

HomepageIntroductionProjection decodeHomepageIntroduction(Object? response) {
  final root = _expectObject(response, 'Homepage introduction response');
  return HomepageIntroductionProjection(
    homepageId: _requiredText(root['homepageId'], 'homepageId'),
    displayName: _requiredText(root['displayName'], 'displayName'),
    homepageType: _requiredText(root['homepageType'], 'homepageType'),
    coverUrl: _optionalText(root['coverUrl']),
    summary: _optionalText(root['summary']) ?? '',
    sections: _objectList(root['sections'], 'sections').map(_decodeSection),
    relatedObjects: _relatedGroups(root['relatedObjects']),
    primarySource: root['primarySource'] == null
        ? null
        : _decodeHomepageSource(
            _expectObject(root['primarySource'], 'primarySource'),
          ),
    sourceUrls: _stringList(root['sourceUrls'], 'sourceUrls'),
    updatedAt: _optionalText(root['updatedAt']) ?? '',
  );
}

HomepageObjectPageBundleProjection decodeHomepageObjectPageBundle(
  Object? response,
) {
  final root = _expectObject(response, 'Homepage object page bundle response');
  return HomepageObjectPageBundleProjection(
    objectType: _requiredText(root['objectType'], 'objectType'),
    objectId: _requiredText(root['objectId'], 'objectId'),
    canonicalEntityId: _requiredText(
      root['canonicalEntityId'],
      'canonicalEntityId',
    ),
    title: _requiredText(root['title'], 'title'),
    subtitle: _optionalText(root['subtitle']),
    coverUrl: _optionalText(root['coverUrl']),
    objectPageTemplate: _optionalText(root['objectPageTemplate']) ?? 'standard',
    tagRefs: _stringList(root['tagRefs'], 'tagRefs'),
    stats: _optionalStructuredObject(root['stats'], 'stats'),
    intersectionReasons: _structuredObjectList(
      root['intersectionReasons'],
      'intersectionReasons',
    ),
    highlightItems: _structuredObjectList(
      root['highlightItems'],
      'highlightItems',
    ),
    contentSections: _optionalStructuredObject(
      root['contentSections'],
      'contentSections',
    ),
    relatedObjects: _relatedGroups(root['relatedObjects']),
    relationEdges: _structuredObjectList(
      root['relationEdges'],
      'relationEdges',
    ),
    assistantContext: _optionalStructuredObject(
      root['assistantContext'],
      'assistantContext',
    ),
    rolloutContext: _optionalStructuredObject(
      root['rolloutContext'],
      'rolloutContext',
    ),
  );
}

HomepageImpactSummaryProjection decodeHomepageImpactSummary(Object? response) {
  final root = _expectObject(response, 'Homepage impact response');
  return HomepageImpactSummaryProjection(
    homepageId: _requiredText(root['homepageId'], 'homepageId'),
    total: _optionalInt(root['total']) ?? 0,
    items: _objectList(root['items'], 'items').map(_decodeImpactItem),
  );
}

HomepageReviewSummaryProjection decodeHomepageReviewSummary(Object? response) {
  return _decodeReviewSummary(
    _expectObject(response, 'Homepage review summary response'),
  );
}

HomepageRelatedGroupsSlice decodeHomepageRelatedGroups(Object? response) {
  final root = _expectObject(response, 'Homepage related groups response');
  return HomepageRelatedGroupsSlice(_relatedGroups(root['groups']));
}

HomepageSearchItemProjection _decodeSearchItem(Map<Object?, Object?> item) {
  return HomepageSearchItemProjection(
    homepageId: _requiredText(item['homepageId'], 'homepageId'),
    homepageType: _requiredText(item['homepageType'], 'homepageType'),
    title: _requiredText(item['title'], 'title'),
    canonicalEntityId: _optionalText(item['canonicalEntityId']) ?? '',
    subtitle: _optionalText(item['subtitle']),
    coverUrl: _optionalText(item['coverUrl']),
    city: _optionalText(item['city']),
    address: _optionalText(item['address']),
    status: _optionalText(item['status']) ?? '',
    averageRating: _optionalDouble(item['averageRating']),
    ratingCount: _optionalInt(item['ratingCount']) ?? 0,
  );
}

HomepageDetailProjection _decodeHomepageDetail(Map<Object?, Object?> item) {
  return HomepageDetailProjection(
    homepageId: _requiredText(item['homepageId'], 'homepageId'),
    homepageType: _requiredText(item['homepageType'], 'homepageType'),
    title: _requiredText(item['title'], 'title'),
    subtitle: _optionalText(item['subtitle']),
    coverUrl: _optionalText(item['coverUrl']),
    status: _optionalText(item['status']) ?? '',
    canonicalEntityId: _optionalText(item['canonicalEntityId']) ?? '',
    objectPageTemplate: _optionalText(item['objectPageTemplate']) ?? 'standard',
    sourceType: _optionalText(item['sourceType']),
    claimStatus: _optionalText(item['claimStatus']),
    categoryTags: _stringList(item['categoryTags'], 'categoryTags'),
    address: _optionalText(item['address']),
    city: _optionalText(item['city']),
    location: _optionalStructuredObject(item['location'], 'location'),
    ownerUserId: _optionalText(item['ownerUserId']),
    ownerSubAccountId: _optionalText(item['ownerSubAccountId']),
    viewerFollowsHomepage:
        _optionalBool(item['viewerFollowsHomepage']) ?? false,
    followerCount: _optionalInt(item['followerCount']) ?? 0,
    averageRating: _optionalDouble(item['averageRating']),
    ratingCount: _optionalInt(item['ratingCount']) ?? 0,
    reviewSummary: _optionalReviewSummary(item['reviewSummary']),
    contentPreview: _structuredObjectList(
      item['contentPreview'],
      'contentPreview',
    ),
    questionPreview: _structuredObjectList(
      item['questionPreview'],
      'questionPreview',
    ),
    relatedGroups: _relatedGroups(item['relatedGroups']),
    createdAt: _optionalDateTime(item['createdAt'], 'createdAt'),
    updatedAt: _optionalDateTime(item['updatedAt'], 'updatedAt'),
    publishedAt: _optionalDateTime(item['publishedAt'], 'publishedAt'),
    offlineAt: _optionalDateTime(item['offlineAt'], 'offlineAt'),
  );
}

HomepageReviewSummaryProjection _decodeReviewSummary(
  Map<Object?, Object?> root,
) {
  return HomepageReviewSummaryProjection(
    averageRating: _optionalDouble(root['averageRating']),
    ratingCount: _optionalInt(root['ratingCount']) ?? 0,
    highlightTags: _stringList(root['highlightTags'], 'highlightTags'),
  );
}

HomepageReviewSummaryProjection? _optionalReviewSummary(Object? raw) {
  if (raw == null) return null;
  return _decodeReviewSummary(_expectObject(raw, 'reviewSummary'));
}

HomepageRelatedGroupProjection _decodeRelatedGroup(
  Map<Object?, Object?> group,
) {
  return HomepageRelatedGroupProjection(
    circleId: _requiredText(group['circleId'], 'circleId'),
    name: _requiredText(group['name'], 'name'),
    memberCount: _optionalInt(group['memberCount']) ?? 0,
    linkedHomepageId: _optionalText(group['linkedHomepageId']),
    linkedHomepageTitle: _optionalText(group['linkedHomepageTitle']),
    ownerUserId: _optionalText(group['ownerUserId']) ?? '',
    ownerDisplayNameSnapshot:
        _optionalText(group['ownerDisplayNameSnapshot']) ?? '',
    ownerAvatarUrlSnapshot:
        _optionalText(group['ownerAvatarUrlSnapshot']) ?? '',
    evidenceSnapshotId: _optionalText(group['evidenceSnapshotId']) ?? '',
  );
}

List<HomepageRelatedGroupProjection> _relatedGroups(Object? raw) {
  return _objectList(
    raw,
    'related groups',
  ).map(_decodeRelatedGroup).toList(growable: false);
}

HomepageIntroductionSectionProjection _decodeSection(
  Map<Object?, Object?> section,
) {
  return HomepageIntroductionSectionProjection(
    kind: _optionalText(section['kind']) ?? '',
    title: _optionalText(section['title']) ?? '',
    bodyMarkdown: _optionalText(section['bodyMarkdown']) ?? '',
    assets: _objectList(section['assets'], 'section.assets').map(
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
        _objectList(section['timelineItems'], 'section.timelineItems').map(
          (item) => HomepageIntroductionTimelineProjection(
            dateLabel: _optionalText(item['dateLabel']) ?? '',
            text: _optionalText(item['text']) ?? '',
          ),
        ),
  );
}

HomepageSourceProjection _decodeHomepageSource(Map<Object?, Object?> source) {
  return HomepageSourceProjection(
    sourceKind: _optionalText(source['sourceKind']) ?? '',
    sourceUrl: _optionalText(source['sourceUrl']) ?? '',
    title: _optionalText(source['title']) ?? '',
    fetchedAt: _optionalText(source['fetchedAt']) ?? '',
    snapshotHash: _optionalText(source['snapshotHash']) ?? '',
    policyRevision: _optionalText(source['policyRevision']) ?? '',
    sourceUseMode: _optionalText(source['sourceUseMode']) ?? '',
  );
}

HomepageImpactItemProjection _decodeImpactItem(Map<Object?, Object?> item) {
  return HomepageImpactItemProjection(
    helpType: _optionalText(item['helpType']) ?? '',
    action: _optionalText(item['action']) ?? '',
    intersectionDimension: _optionalText(item['intersectionDimension']) ?? '',
    tagRef: _optionalText(item['tagRef']) ?? '',
    source: _optionalText(item['source']) ?? '',
    count: _optionalInt(item['count']) ?? 0,
    primaryText: _optionalText(item['primaryText']) ?? '',
    subtitleText: _optionalText(item['subtitleText']) ?? '',
    impactId: _optionalText(item['impactId']) ?? '',
    primarySpans: _structuredObjectList(item['primarySpans'], 'primarySpans'),
    sampleVisuals: _structuredObjectList(
      item['sampleVisuals'],
      'sampleVisuals',
    ),
    representativeActor: _optionalStructuredObject(
      item['representativeActor'],
      'representativeActor',
    ),
    actionHints: _structuredObjectList(item['actionHints'], 'actionHints'),
    countTarget: _optionalStructuredObject(item['countTarget'], 'countTarget'),
    evidenceSnapshotId: _optionalText(item['evidenceSnapshotId']) ?? '',
    countObjectKind: _optionalText(item['countObjectKind']) ?? '',
    propagationPath: _optionalStructuredObject(
      item['propagationPath'],
      'propagationPath',
    ),
    iconKey: _optionalText(item['iconKey']) ?? '',
  );
}

CloudStructuredObject? _optionalStructuredObject(Object? raw, String context) {
  if (raw == null) return null;
  final value = _decodeStructuredValue(raw, context);
  if (value is! CloudStructuredObject) {
    throw FormatException('$context must be an object');
  }
  return value;
}

List<CloudStructuredObject> _structuredObjectList(Object? raw, String context) {
  return _objectList(raw, context)
      .map((item) => _decodeStructuredValue(item, context))
      .cast<CloudStructuredObject>()
      .toList(growable: false);
}

CloudStructuredValue _decodeStructuredValue(Object? raw, String context) {
  if (raw == null) return const CloudStructuredNull();
  if (raw is String) return CloudStructuredText(raw);
  if (raw is num) return CloudStructuredNumber(raw);
  if (raw is bool) return CloudStructuredBoolean(raw);
  if (raw is List<Object?>) {
    return CloudStructuredArray(
      raw.map((value) => _decodeStructuredValue(value, context)),
    );
  }
  if (raw is Map<Object?, Object?>) {
    final fields = <String, CloudStructuredValue>{};
    for (final entry in raw.entries) {
      if (entry.key is! String) {
        throw FormatException('$context keys must be strings');
      }
      fields[entry.key! as String] = _decodeStructuredValue(
        entry.value,
        context,
      );
    }
    return CloudStructuredObject(fields);
  }
  throw FormatException('$context contains unsupported JSON data');
}

Map<Object?, Object?> _expectObject(Object? value, String context) {
  if (value is Map<Object?, Object?>) return value;
  throw FormatException('$context must be an object');
}

List<Map<Object?, Object?>> _objectList(Object? value, String context) {
  if (value == null) return const <Map<Object?, Object?>>[];
  if (value is! List<Object?>) {
    throw FormatException('$context must be a list');
  }
  return value.map((item) => _expectObject(item, '$context item')).toList();
}

List<String> _stringList(Object? value, String context) {
  if (value == null) return const <String>[];
  if (value is! List<Object?> || value.any((item) => item is! String)) {
    throw FormatException('$context must be a string list');
  }
  return value.cast<String>().toList(growable: false);
}

String _requiredText(Object? value, String name) {
  final text = _optionalText(value);
  if (text == null) throw FormatException('$name must be a non-empty string');
  return text;
}

String? _optionalText(Object? value) {
  if (value == null) return null;
  if (value is! String) throw const FormatException('Expected a string');
  final text = value.trim();
  return text.isEmpty ? null : text;
}

int? _optionalInt(Object? value) {
  if (value == null) return null;
  if (value is! num) throw const FormatException('Expected a number');
  return value.toInt();
}

double? _optionalDouble(Object? value) {
  if (value == null) return null;
  if (value is! num) throw const FormatException('Expected a number');
  return value.toDouble();
}

bool? _optionalBool(Object? value) {
  if (value == null) return null;
  if (value is! bool) throw const FormatException('Expected a boolean');
  return value;
}

DateTime? _optionalDateTime(Object? value, String name) {
  final text = _optionalText(value);
  if (text == null) return null;
  final parsed = DateTime.tryParse(text);
  if (parsed == null) throw FormatException('$name must be RFC3339');
  return parsed.toUtc();
}

void _validateLimit(int limit) {
  if (limit <= 0) throw ArgumentError.value(limit, 'limit', 'must be positive');
}
