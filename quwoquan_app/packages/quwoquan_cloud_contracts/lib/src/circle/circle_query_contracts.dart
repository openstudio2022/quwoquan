import '../content/post_reader_queries.dart';
import '../operation_request_payload.dart';

final class CircleListQuery {
  const CircleListQuery({
    this.category,
    this.domainId,
    this.recommendFor,
    this.cursor,
    this.limit = 20,
    this.sort,
  });

  final String? category;
  final String? domainId;
  final String? recommendFor;
  final String? cursor;
  final int limit;
  final String? sort;
}

final class CircleSearchQuery {
  const CircleSearchQuery({
    required this.query,
    this.categoryId,
    this.subCategory,
    this.cursor,
    this.limit = 20,
  });

  final String query;
  final String? categoryId;
  final String? subCategory;
  final String? cursor;
  final int limit;
}

final class CircleDetailQuery {
  const CircleDetailQuery({required this.circleId});

  final String circleId;
}

final class CircleFeedQuery {
  const CircleFeedQuery({
    required this.circleId,
    this.identity,
    this.type,
    this.cursor,
    this.limit = 20,
    this.sort = 'latest',
  });

  final String circleId;
  final String? identity;
  final String? type;
  final String? cursor;
  final int limit;
  final String sort;
}

enum CircleDiscoveryFeedScope {
  recommended,
  mine;

  String get wireValue => name;
}

final class CircleDiscoveryFeedQuery {
  const CircleDiscoveryFeedQuery({
    this.category,
    this.subCategory,
    this.scope = CircleDiscoveryFeedScope.recommended,
    this.cursor,
    this.limit = 20,
    this.sort = 'recommended',
  });

  final String? category;
  final String? subCategory;
  final CircleDiscoveryFeedScope scope;
  final String? cursor;
  final int limit;
  final String sort;
}

final class CircleStatsQuery {
  const CircleStatsQuery({required this.circleId});

  final String circleId;
}

final class CircleImpactQuery {
  const CircleImpactQuery({required this.circleId});

  final String circleId;
}

final class CircleSectionProjection {
  const CircleSectionProjection({
    required this.sectionType,
    required this.visible,
    required this.order,
    this.customTitle,
  });

  final String sectionType;
  final bool visible;
  final int order;
  final String? customTitle;
}

final class CircleProjection {
  CircleProjection({
    required this.circleId,
    required this.name,
    this.description,
    this.rulesText,
    this.welcomeMessage,
    this.coverUrl,
    this.iconUrl,
    required this.ownerId,
    this.category,
    Iterable<String> tags = const <String>[],
    this.memberCount = 0,
    this.postCount = 0,
    this.weeklyActiveCount = 0,
    this.status = 'active',
    this.visibility = 'public',
    this.joinPolicy = 'open',
    this.kind = 'interest',
    this.displaySubjectType = 'circle',
    this.followEnabled = true,
    this.defaultPublicGroupId,
    this.conversationId,
    this.autoSyncChat = true,
    Iterable<CircleSectionProjection> sectionConfig =
        const <CircleSectionProjection>[],
    this.storageUsedBytes = 0,
    this.storageQuotaBytes = 0,
    this.domainId,
    this.subCategory,
    this.viewerRole,
    this.joinStatus,
    this.isFollowed,
    this.createdAt,
    this.updatedAt,
  }) : tags = List<String>.unmodifiable(tags),
       sectionConfig = List<CircleSectionProjection>.unmodifiable(
         sectionConfig,
       );

  final String circleId;
  final String name;
  final String? description;
  final String? rulesText;
  final String? welcomeMessage;
  final String? coverUrl;
  final String? iconUrl;
  final String ownerId;
  final String? category;
  final List<String> tags;
  final int memberCount;
  final int postCount;
  final int weeklyActiveCount;
  final String status;
  final String visibility;
  final String joinPolicy;
  final String kind;
  final String displaySubjectType;
  final bool followEnabled;
  final String? defaultPublicGroupId;
  final String? conversationId;
  final bool autoSyncChat;
  final List<CircleSectionProjection> sectionConfig;
  final int storageUsedBytes;
  final int storageQuotaBytes;
  final String? domainId;
  final String? subCategory;
  final String? viewerRole;
  final String? joinStatus;
  final bool? isFollowed;
  final DateTime? createdAt;
  final DateTime? updatedAt;
}

final class CirclePageSlice {
  CirclePageSlice({required Iterable<CircleProjection> items, this.nextCursor})
    : items = List<CircleProjection>.unmodifiable(items);

  final List<CircleProjection> items;
  final String? nextCursor;
}

final class CircleSearchItemProjection {
  const CircleSearchItemProjection({
    required this.circleId,
    required this.name,
    this.description,
    this.coverUrl,
    this.categoryId,
    this.subCategory,
    this.domainId,
    this.kind,
    this.displaySubjectType,
    this.memberCount = 0,
    this.postCount = 0,
    this.highlightText,
    this.matchedField,
    this.circleName,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
  });

  final String circleId;
  final String name;
  final String? description;
  final String? coverUrl;
  final String? categoryId;
  final String? subCategory;
  final String? domainId;
  final String? kind;
  final String? displaySubjectType;
  final int memberCount;
  final int postCount;
  final String? highlightText;
  final String? matchedField;
  final String? circleName;
  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;
}

final class CircleFacetBucketProjection {
  const CircleFacetBucketProjection({
    required this.facetKey,
    required this.label,
    this.categoryId,
    this.subCategory,
    this.facetCount = 0,
  });

  final String facetKey;
  final String label;
  final String? categoryId;
  final String? subCategory;
  final int facetCount;
}

final class CircleSearchResultSlice {
  CircleSearchResultSlice({
    required Iterable<CircleSearchItemProjection> items,
    required Iterable<CircleFacetBucketProjection> facetBuckets,
    this.nextCursor,
  }) : items = List<CircleSearchItemProjection>.unmodifiable(items),
       facetBuckets = List<CircleFacetBucketProjection>.unmodifiable(
         facetBuckets,
       );

  final List<CircleSearchItemProjection> items;
  final List<CircleFacetBucketProjection> facetBuckets;
  final String? nextCursor;
}

final class CircleFeedPostProjection {
  const CircleFeedPostProjection({
    required this.circleId,
    required this.placementId,
    required this.post,
    this.pinned = false,
    this.featured = false,
    this.pinnedAt,
    this.featuredAt,
  });

  final String circleId;
  final String placementId;
  final ContentPostProjection post;
  final bool pinned;
  final bool featured;
  final DateTime? pinnedAt;
  final DateTime? featuredAt;
}

final class CircleFeedPageSlice {
  CircleFeedPageSlice({
    required Iterable<CircleFeedPostProjection> items,
    this.nextCursor,
  }) : items = List<CircleFeedPostProjection>.unmodifiable(items);

  final List<CircleFeedPostProjection> items;
  final String? nextCursor;
}

final class CircleDiscoveryFeedPageSlice {
  CircleDiscoveryFeedPageSlice({
    required Iterable<CircleProjection> circles,
    required Iterable<CircleFeedPostProjection> items,
    this.nextCursor,
  }) : circles = List<CircleProjection>.unmodifiable(circles),
       items = List<CircleFeedPostProjection>.unmodifiable(items);

  final List<CircleProjection> circles;
  final List<CircleFeedPostProjection> items;
  final String? nextCursor;
}

final class CircleStatsSlice {
  const CircleStatsSlice({
    this.circleId = '',
    this.memberCount = 0,
    this.postCount = 0,
    this.discussionCount = 0,
    this.weeklyActiveCount = 0,
    this.likeCount = 0,
    this.storageUsedBytes = 0,
    this.storageQuotaBytes = 0,
  });

  final String circleId;
  final int memberCount;
  final int postCount;
  final int discussionCount;
  final int weeklyActiveCount;
  final int likeCount;
  final int storageUsedBytes;
  final int storageQuotaBytes;
}

final class CircleIntersectionTargetProjection {
  const CircleIntersectionTargetProjection({
    this.objectType = '',
    this.objectId = '',
    this.objectKind = '',
    this.routeId = '',
  });

  final String objectType;
  final String objectId;
  final String objectKind;
  final String routeId;
}

final class CircleIntersectionVisualProjection {
  const CircleIntersectionVisualProjection({
    this.assetKind = '',
    this.imageUrl = '',
    this.displayName = '',
    this.target,
  });

  final String assetKind;
  final String imageUrl;
  final String displayName;
  final CircleIntersectionTargetProjection? target;
}

final class CircleIntersectionTextSpanProjection {
  const CircleIntersectionTextSpanProjection({
    this.text = '',
    this.role = 'plain',
    this.target,
    this.visual,
  });

  final String text;
  final String role;
  final CircleIntersectionTargetProjection? target;
  final CircleIntersectionVisualProjection? visual;
}

final class CircleIntersectionRepresentativeActorProjection {
  const CircleIntersectionRepresentativeActorProjection({
    this.actorId = '',
    this.displayName = '',
    this.avatarUrl = '',
    this.relationLabel = '',
    this.privacyState = 'visible',
    this.target,
    this.evidenceRank = 0,
    this.snapshotVersion = '',
  });

  final String actorId;
  final String displayName;
  final String avatarUrl;
  final String relationLabel;
  final String privacyState;
  final CircleIntersectionTargetProjection? target;
  final int evidenceRank;
  final String snapshotVersion;
}

final class CircleIntersectionActionHintProjection {
  CircleIntersectionActionHintProjection({
    this.actionKey = '',
    this.label = '',
    this.target,
    this.isPrimary = false,
    this.priority = 0,
    this.actionTier = 'light',
    Iterable<String> requiredGates = const <String>[],
    this.targetAvailability = 'available',
    this.dispatch = 'navigate',
  }) : requiredGates = List<String>.unmodifiable(requiredGates);

  final String actionKey;
  final String label;
  final CircleIntersectionTargetProjection? target;
  final bool isPrimary;
  final int priority;
  final String actionTier;
  final List<String> requiredGates;
  final String targetAvailability;
  final String dispatch;
}

final class CircleIntersectionPropagationPathProjection {
  CircleIntersectionPropagationPathProjection({
    this.pathKind = '',
    this.hopCount = 0,
    this.secondarySpreadCount = 0,
    this.summaryText = '',
    this.summaryTarget,
    Iterable<CircleIntersectionVisualProjection> nodes =
        const <CircleIntersectionVisualProjection>[],
  }) : nodes = List<CircleIntersectionVisualProjection>.unmodifiable(nodes);

  final String pathKind;
  final int hopCount;
  final int secondarySpreadCount;
  final String summaryText;
  final CircleIntersectionTargetProjection? summaryTarget;
  final List<CircleIntersectionVisualProjection> nodes;
}

final class CircleImpactItemProjection {
  CircleImpactItemProjection({
    this.helpType = '',
    this.action = '',
    this.intersectionDimension = '',
    this.tagRef = '',
    this.source = '',
    this.count = 0,
    this.primaryText = '',
    this.subtitleText = '',
    this.impactId = '',
    Iterable<CircleIntersectionTextSpanProjection> primarySpans =
        const <CircleIntersectionTextSpanProjection>[],
    Iterable<CircleIntersectionVisualProjection> sampleVisuals =
        const <CircleIntersectionVisualProjection>[],
    this.representativeActor,
    Iterable<CircleIntersectionActionHintProjection> actionHints =
        const <CircleIntersectionActionHintProjection>[],
    this.countTarget,
    this.evidenceSnapshotId = '',
    this.countObjectKind = '',
    this.propagationPath,
    this.iconKey = '',
  }) : primarySpans = List<CircleIntersectionTextSpanProjection>.unmodifiable(
         primarySpans,
       ),
       sampleVisuals = List<CircleIntersectionVisualProjection>.unmodifiable(
         sampleVisuals,
       ),
       actionHints = List<CircleIntersectionActionHintProjection>.unmodifiable(
         actionHints,
       );

  final String helpType;
  final String action;
  final String intersectionDimension;
  final String tagRef;
  final String source;
  final int count;
  final String primaryText;
  final String subtitleText;
  final String impactId;
  final List<CircleIntersectionTextSpanProjection> primarySpans;
  final List<CircleIntersectionVisualProjection> sampleVisuals;
  final CircleIntersectionRepresentativeActorProjection? representativeActor;
  final List<CircleIntersectionActionHintProjection> actionHints;
  final CircleIntersectionTargetProjection? countTarget;
  final String evidenceSnapshotId;
  final String countObjectKind;
  final CircleIntersectionPropagationPathProjection? propagationPath;
  final String iconKey;
}

final class CircleImpactSlice {
  CircleImpactSlice({
    required this.circleId,
    required this.total,
    required Iterable<CircleImpactItemProjection> items,
  }) : items = List<CircleImpactItemProjection>.unmodifiable(items);

  final String circleId;
  final int total;
  final List<CircleImpactItemProjection> items;
}

abstract interface class CircleFeedQueryReader {
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query);
}

abstract interface class CircleQueryReader implements CircleFeedQueryReader {
  Future<CirclePageSlice> list(CircleListQuery query);

  Future<CircleSearchResultSlice> search(CircleSearchQuery query);

  Future<CircleProjection> get(CircleDetailQuery query);

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query);

  Future<CircleStatsSlice> stats(CircleStatsQuery query);

  Future<CircleImpactSlice> impact(CircleImpactQuery query);
}

abstract interface class CircleDiscoveryFeedQueryReader {
  Future<CircleDiscoveryFeedPageSlice> listDiscoveryFeed(
    CircleDiscoveryFeedQuery query,
  );
}

CloudOperationRequestPayload encodeCircleListQuery(CircleListQuery query) {
  _validateLimit(query.limit);
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (_optional(query.category) case final value?) 'category': value,
      if (_optional(query.domainId) case final value?) 'domainId': value,
      if (_optional(query.recommendFor) case final value?)
        'recommendFor': value,
      if (_optional(query.cursor) case final value?) 'cursor': value,
      'limit': '${query.limit}',
      if (_optional(query.sort) case final value?) 'sort': value,
    },
  );
}

CloudOperationRequestPayload encodeCircleSearchQuery(CircleSearchQuery query) {
  _validateLimit(query.limit);
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      'query': _required(query.query, 'query'),
      if (_optional(query.categoryId) case final value?) 'categoryId': value,
      if (_optional(query.subCategory) case final value?) 'subCategory': value,
      if (_optional(query.cursor) case final value?) 'cursor': value,
      'limit': '${query.limit}',
    },
  );
}

CloudOperationRequestPayload encodeCircleDetailQuery(CircleDetailQuery query) =>
    _circlePathPayload(query.circleId);

CloudOperationRequestPayload encodeCircleFeedQuery(CircleFeedQuery query) {
  _validateLimit(query.limit);
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'circleId': _required(query.circleId, 'circleId'),
    },
    queryParameters: <String, String>{
      if (_optional(query.identity) case final value?) 'identity': value,
      if (_optional(query.type) case final value?) 'type': value,
      if (_optional(query.cursor) case final value?) 'cursor': value,
      'limit': '${query.limit}',
      'sort': _required(query.sort, 'sort'),
    },
  );
}

CloudOperationRequestPayload encodeCircleDiscoveryFeedQuery(
  CircleDiscoveryFeedQuery query,
) {
  _validateLimit(query.limit);
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (_optional(query.category) case final value?) 'category': value,
      if (_optional(query.subCategory) case final value?) 'subCategory': value,
      'scope': query.scope.wireValue,
      if (_optional(query.cursor) case final value?) 'cursor': value,
      'limit': '${query.limit}',
      'sort': _required(query.sort, 'sort'),
    },
  );
}

CloudOperationRequestPayload encodeCircleStatsQuery(CircleStatsQuery query) =>
    _circlePathPayload(query.circleId);

CloudOperationRequestPayload encodeCircleImpactQuery(CircleImpactQuery query) =>
    _circlePathPayload(query.circleId);

CirclePageSlice decodeCirclePageSlice(Object? response) {
  final root = response is List<Object?> ? null : _object(response, 'circles');
  final rawItems = root == null ? response : root['items'];
  return CirclePageSlice(
    items: _list(rawItems, 'circles.items').map(_decodeCircle),
    nextCursor: root == null ? null : _optional(root['cursor']),
  );
}

CircleProjection decodeCircleProjection(Object? response) =>
    _decodeCircle(_object(response, 'circle'));

CircleSearchResultSlice decodeCircleSearchResultSlice(Object? response) {
  final root = _object(response, 'circle search');
  return CircleSearchResultSlice(
    items: _list(root['items'], 'circle search.items').map((item) {
      final value = _object(item, 'circle search item');
      return CircleSearchItemProjection(
        circleId: _requiredValue(value['circleId'], 'circleId'),
        name: _requiredValue(value['name'], 'name'),
        description: _optional(value['description']),
        coverUrl: _optional(value['coverUrl']),
        categoryId: _optional(value['categoryId']),
        subCategory: _optional(value['subCategory']),
        domainId: _optional(value['domainId']),
        kind: _optional(value['kind']),
        displaySubjectType: _optional(value['displaySubjectType']),
        memberCount: _integer(value['memberCount']),
        postCount: _integer(value['postCount']),
        highlightText: _optional(value['highlightText']),
        matchedField: _optional(value['matchedField']),
        circleName: _optional(value['circleName']),
        linkedHomepageId: _optional(value['linkedHomepageId']),
        linkedHomepageType: _optional(value['linkedHomepageType']),
        linkedHomepageTitle: _optional(value['linkedHomepageTitle']),
      );
    }),
    facetBuckets:
        _list(
          root['facetBuckets'],
          'circle search.facetBuckets',
          allowNull: true,
        ).map((item) {
          final value = _object(item, 'circle facet bucket');
          return CircleFacetBucketProjection(
            facetKey: _requiredValue(value['facetKey'], 'facetKey'),
            label: _requiredValue(value['label'], 'label'),
            categoryId: _optional(value['categoryId']),
            subCategory: _optional(value['subCategory']),
            facetCount: _integer(value['facetCount']),
          );
        }),
    nextCursor: _optional(root['cursor']),
  );
}

CircleFeedPageSlice decodeCircleFeedPageSlice(Object? response) {
  final root = response is List<Object?> ? null : _object(response, 'feed');
  final rawItems = root == null ? response : root['items'];
  return CircleFeedPageSlice(
    items: _list(rawItems, 'feed.items').map(_decodeCircleFeedPostProjection),
    nextCursor: root == null ? null : _optional(root['cursor']),
  );
}

CircleDiscoveryFeedPageSlice decodeCircleDiscoveryFeedPageSlice(
  Object? response,
) {
  final root = _object(response, 'circle discovery feed');
  return CircleDiscoveryFeedPageSlice(
    circles: _list(
      root['circles'],
      'circle discovery feed.circles',
    ).map(_decodeCircle),
    items: _list(
      root['items'],
      'circle discovery feed.items',
    ).map(_decodeCircleFeedPostProjection),
    nextCursor: _optional(root['cursor']),
  );
}

CircleFeedPostProjection _decodeCircleFeedPostProjection(Object? response) {
  final value = _object(response, 'circle feed item');
  final placementId = _requiredValue(value['placementId'], 'placementId');
  if (placementId.trim().isEmpty) {
    throw FormatException('circle feed item.placementId is required');
  }
  return CircleFeedPostProjection(
    circleId: _requiredValue(value['circleId'], 'circleId'),
    placementId: placementId,
    post: decodeContentPostProjection(value),
    pinned: _boolean(value['pinned'], fallback: false),
    featured: _boolean(value['featured'], fallback: false),
    pinnedAt: _date(value['pinnedAt']),
    featuredAt: _date(value['featuredAt']),
  );
}

CircleStatsSlice decodeCircleStatsSlice(Object? response) {
  final root = _object(response, 'circle stats');
  return CircleStatsSlice(
    circleId: _optional(root['circleId']) ?? '',
    memberCount: _integer(root['memberCount']),
    postCount: _integer(root['postCount']),
    discussionCount: _integer(root['discussionCount']),
    weeklyActiveCount: _integer(root['weeklyActiveCount']),
    likeCount: _integer(root['likeCount']),
    storageUsedBytes: _integer(root['storageUsedBytes']),
    storageQuotaBytes: _integer(root['storageQuotaBytes']),
  );
}

CircleImpactSlice decodeCircleImpactSlice(Object? response) {
  final root = _object(response, 'circle impact');
  return CircleImpactSlice(
    circleId: _requiredValue(root['circleId'], 'circleId'),
    total: _integer(root['total']),
    items: _list(root['items'], 'circle impact.items').map((item) {
      final value = _object(item, 'circle impact item');
      return CircleImpactItemProjection(
        helpType: _optional(value['helpType']) ?? '',
        action: _optional(value['action']) ?? '',
        intersectionDimension: _optional(value['intersectionDimension']) ?? '',
        tagRef: _optional(value['tagRef']) ?? '',
        source: _optional(value['source']) ?? '',
        count: _integer(value['count']),
        primaryText: _optional(value['primaryText']) ?? '',
        subtitleText: _optional(value['subtitleText']) ?? '',
        impactId: _optional(value['impactId']) ?? '',
        primarySpans: _list(
          value['primarySpans'],
          'circle impact item.primarySpans',
          allowNull: true,
        ).map(_decodeCircleIntersectionTextSpan),
        sampleVisuals: _list(
          value['sampleVisuals'],
          'circle impact item.sampleVisuals',
          allowNull: true,
        ).map(_decodeCircleIntersectionVisual),
        representativeActor:
            _decodeOptionalCircleIntersectionRepresentativeActor(
              value['representativeActor'],
            ),
        actionHints: _list(
          value['actionHints'],
          'circle impact item.actionHints',
          allowNull: true,
        ).map(_decodeCircleIntersectionActionHint),
        countTarget: _decodeOptionalCircleIntersectionTarget(
          value['countTarget'],
        ),
        evidenceSnapshotId: _optional(value['evidenceSnapshotId']) ?? '',
        countObjectKind: _optional(value['countObjectKind']) ?? '',
        propagationPath: _decodeOptionalCircleIntersectionPropagationPath(
          value['propagationPath'],
        ),
        iconKey: _optional(value['iconKey']) ?? '',
      );
    }),
  );
}

CircleIntersectionTargetProjection _decodeCircleIntersectionTarget(
  Map<Object?, Object?> value,
) => CircleIntersectionTargetProjection(
  objectType: _optional(value['objectType']) ?? '',
  objectId: _optional(value['objectId']) ?? '',
  objectKind: _optional(value['objectKind']) ?? '',
  routeId: _optional(value['routeId']) ?? '',
);

CircleIntersectionTargetProjection? _decodeOptionalCircleIntersectionTarget(
  Object? response,
) {
  final value = _optionalMap(response);
  return value == null ? null : _decodeCircleIntersectionTarget(value);
}

CircleIntersectionVisualProjection _decodeCircleIntersectionVisual(
  Object? response,
) {
  final value = _object(response, 'circle impact visual');
  return CircleIntersectionVisualProjection(
    assetKind: _optional(value['assetKind']) ?? '',
    imageUrl: _optional(value['imageUrl']) ?? '',
    displayName: _optional(value['displayName']) ?? '',
    target: _decodeOptionalCircleIntersectionTarget(value['target']),
  );
}

CircleIntersectionVisualProjection? _decodeOptionalCircleIntersectionVisual(
  Object? response,
) {
  final value = _optionalMap(response);
  return value == null ? null : _decodeCircleIntersectionVisual(value);
}

CircleIntersectionTextSpanProjection _decodeCircleIntersectionTextSpan(
  Object? response,
) {
  final value = _object(response, 'circle impact text span');
  return CircleIntersectionTextSpanProjection(
    text: _optional(value['text']) ?? '',
    role: _optional(value['role']) ?? 'plain',
    target: _decodeOptionalCircleIntersectionTarget(value['target']),
    visual: _decodeOptionalCircleIntersectionVisual(value['visual']),
  );
}

CircleIntersectionRepresentativeActorProjection
_decodeCircleIntersectionRepresentativeActor(Map<Object?, Object?> value) =>
    CircleIntersectionRepresentativeActorProjection(
      actorId: _optional(value['actorId']) ?? '',
      displayName: _optional(value['displayName']) ?? '',
      avatarUrl: _optional(value['avatarUrl']) ?? '',
      relationLabel: _optional(value['relationLabel']) ?? '',
      privacyState: _optional(value['privacyState']) ?? 'visible',
      target: _decodeOptionalCircleIntersectionTarget(value['target']),
      evidenceRank: _integer(value['evidenceRank']),
      snapshotVersion: _optional(value['snapshotVersion']) ?? '',
    );

CircleIntersectionRepresentativeActorProjection?
_decodeOptionalCircleIntersectionRepresentativeActor(Object? response) {
  final value = _optionalMap(response);
  return value == null
      ? null
      : _decodeCircleIntersectionRepresentativeActor(value);
}

CircleIntersectionActionHintProjection _decodeCircleIntersectionActionHint(
  Object? response,
) {
  final value = _object(response, 'circle impact action hint');
  return CircleIntersectionActionHintProjection(
    actionKey: _optional(value['actionKey']) ?? '',
    label: _optional(value['label']) ?? '',
    target: _decodeOptionalCircleIntersectionTarget(value['target']),
    isPrimary: _boolean(value['isPrimary'], fallback: false),
    priority: _integer(value['priority']),
    actionTier: _optional(value['actionTier']) ?? 'light',
    requiredGates: _stringList(value['requiredGates']),
    targetAvailability: _optional(value['targetAvailability']) ?? 'available',
    dispatch: _optional(value['dispatch']) ?? 'navigate',
  );
}

CircleIntersectionPropagationPathProjection
_decodeCircleIntersectionPropagationPath(Map<Object?, Object?> value) =>
    CircleIntersectionPropagationPathProjection(
      pathKind: _optional(value['pathKind']) ?? '',
      hopCount: _integer(value['hopCount']),
      secondarySpreadCount: _integer(value['secondarySpreadCount']),
      summaryText: _optional(value['summaryText']) ?? '',
      summaryTarget: _decodeOptionalCircleIntersectionTarget(
        value['summaryTarget'],
      ),
      nodes: _list(
        value['nodes'],
        'circle impact propagation path.nodes',
        allowNull: true,
      ).map(_decodeCircleIntersectionVisual),
    );

CircleIntersectionPropagationPathProjection?
_decodeOptionalCircleIntersectionPropagationPath(Object? response) {
  final value = _optionalMap(response);
  return value == null ? null : _decodeCircleIntersectionPropagationPath(value);
}

CircleProjection _decodeCircle(Object? response) {
  final value = _object(response, 'circle');
  return CircleProjection(
    circleId: _requiredValue(value['id'], 'id'),
    name: _requiredValue(value['name'], 'name'),
    description: _optional(value['description']),
    rulesText: _optional(value['rulesText']),
    welcomeMessage: _optional(value['welcomeMessage']),
    coverUrl: _optional(value['coverUrl']),
    iconUrl: _optional(value['iconUrl']),
    ownerId: _requiredValue(value['ownerId'], 'ownerId'),
    category: _optional(value['category']),
    tags: _stringList(value['tags']),
    memberCount: _integer(value['memberCount']),
    postCount: _integer(value['postCount']),
    weeklyActiveCount: _integer(value['weeklyActiveCount']),
    status: _optional(value['status']) ?? 'active',
    visibility: _optional(value['visibility']) ?? 'public',
    joinPolicy: _optional(value['joinPolicy']) ?? 'open',
    kind: _optional(value['kind']) ?? 'interest',
    displaySubjectType: _optional(value['displaySubjectType']) ?? 'circle',
    followEnabled: _boolean(value['followEnabled'], fallback: true),
    defaultPublicGroupId: _optional(value['defaultPublicGroupId']),
    conversationId: _optional(value['conversationId']),
    autoSyncChat: _boolean(value['autoSyncChat'], fallback: true),
    sectionConfig:
        _list(
          value['sectionConfig'],
          'circle.sectionConfig',
          allowNull: true,
        ).map((item) {
          final section = _object(item, 'circle.sectionConfig.item');
          return CircleSectionProjection(
            sectionType: _requiredValue(section['sectionType'], 'sectionType'),
            visible: _boolean(section['visible'], fallback: false),
            order: _integer(section['order']),
            customTitle: _optional(section['customTitle']),
          );
        }),
    storageUsedBytes: _integer(value['storageUsedBytes']),
    storageQuotaBytes: _integer(value['storageQuotaBytes']),
    domainId: _optional(value['domainId']),
    subCategory: _optional(value['subCategory']),
    viewerRole: _optional(value['role']),
    joinStatus: _optional(value['joinStatus']),
    isFollowed: _optionalBoolean(value['isFollowed']),
    createdAt: _date(value['createdAt']),
    updatedAt: _date(value['updatedAt']),
  );
}

CloudOperationRequestPayload _circlePathPayload(String circleId) =>
    CloudOperationRequestPayload(
      pathParameters: <String, String>{
        'circleId': _required(circleId, 'circleId'),
      },
    );

Map<Object?, Object?> _object(Object? value, String label) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$label must be an object');
  }
  return value;
}

Map<Object?, Object?>? _optionalMap(Object? value) =>
    value is Map<Object?, Object?> ? value : null;

List<Object?> _list(Object? value, String label, {bool allowNull = false}) {
  if (allowNull && value == null) return const <Object?>[];
  if (value is! List<Object?>) {
    throw FormatException('$label must be a list');
  }
  return value;
}

String _required(String value, String label) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, label, 'is blank');
  return normalized;
}

String _requiredValue(Object? value, String label) {
  final normalized = _optional(value);
  if (normalized == null) throw FormatException('$label must not be blank');
  return normalized;
}

String? _optional(Object? value) {
  if (value == null) return null;
  final normalized = value.toString().trim();
  return normalized.isEmpty ? null : normalized;
}

int _integer(Object? value) => value is num ? value.toInt() : 0;

bool _boolean(Object? value, {required bool fallback}) =>
    value is bool ? value : fallback;

bool? _optionalBoolean(Object? value) => value is bool ? value : null;

DateTime? _date(Object? value) =>
    value is String ? DateTime.tryParse(value)?.toUtc() : null;

List<String> _stringList(Object? value) {
  if (value is! List<Object?>) return const <String>[];
  return value.map(_optional).whereType<String>().toList(growable: false);
}

void _validateLimit(int limit) {
  if (limit < 1 || limit > 200) {
    throw ArgumentError.value(limit, 'limit', 'must be in 1..200');
  }
}
