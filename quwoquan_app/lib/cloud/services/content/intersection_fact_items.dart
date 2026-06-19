import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';

List<IntersectionReason> rankAndDedupeIntersections(
  List<IntersectionReason> items,
) {
  final chosen = <String, IntersectionReason>{};
  for (final item in items) {
    final key = dedupeKeyForIntersection(item);
    final existing = chosen[key];
    if (existing == null || compareIntersectionRank(item, existing) < 0) {
      chosen[key] = item;
    }
  }
  final ranked = chosen.values.toList(growable: false);
  ranked.sort(compareIntersectionRank);
  return ranked;
}

String dedupeKeyForIntersection(IntersectionReason item) {
  final explicit = item.dedupeKey.trim();
  if (explicit.isNotEmpty) return explicit;
  final objectId = item.actionTargetId.trim().isNotEmpty
      ? item.actionTargetId.trim()
      : item.relationObjectId.trim().isNotEmpty
      ? item.relationObjectId.trim()
      : item.intersectionId.trim();
  final objectType = item.objectKind.trim().isNotEmpty
      ? item.objectKind.trim()
      : item.relationKind.trim();
  return 'viewer:$objectId:$objectType';
}

int compareIntersectionRank(IntersectionReason a, IntersectionReason b) {
  final byStrength = b.strength.compareTo(a.strength);
  if (byStrength != 0) return byStrength;
  final byBucket = timeBucketPriority(
    timeBucketForIntersection(a),
  ).compareTo(timeBucketPriority(timeBucketForIntersection(b)));
  if (byBucket != 0) return byBucket;
  final byAnchor = b.anchorUserWeight.compareTo(a.anchorUserWeight);
  if (byAnchor != 0) return byAnchor;
  final byCount = _mutualCountFor(b).compareTo(_mutualCountFor(a));
  if (byCount != 0) return byCount;
  final byType = _objectTypePriority(
    b.objectKind,
  ).compareTo(_objectTypePriority(a.objectKind));
  if (byType != 0) return byType;
  return dedupeKeyForIntersection(a).compareTo(dedupeKeyForIntersection(b));
}

String timeBucketForIntersection(IntersectionReason item) {
  final explicit = item.timeBucket.trim();
  if (explicit.isNotEmpty) return explicit;
  final freshAt = DateTime.tryParse(item.freshAt);
  if (freshAt == null) return 'lastMonth';
  final diff = DateTime.now().toUtc().difference(freshAt.toUtc());
  if (diff.inHours < 24) return 'today';
  if (diff.inHours < 48) return 'yesterday';
  if (diff.inDays < 7) return 'last7Days';
  if (diff.inDays < 31) return 'thisMonth';
  return 'lastMonth';
}

int timeBucketPriority(String bucket) {
  switch (bucket) {
    case 'today':
      return 0;
    case 'yesterday':
      return 1;
    case 'last7Days':
      return 2;
    case 'thisMonth':
      return 3;
    case 'lastMonth':
      return 4;
    default:
      return 5;
  }
}

List<IntersectionReason> fallbackInboxReasons() {
  return _withDefaultPointSummaries(<IntersectionReason>[
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_1',
      intersectionClass: 'fact',
      displayName: '林清越',
      objectKind: 'person',
      primaryText: '4位关注对象正在讨论黄金投资',
      secondaryText: '都在黄金投资圈',
      weightTier: 'heavy',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1494790108377-be9c29b29330/v1/avatar.jpg',
      totalPointCount: 4,
      strength: 0.9,
      relationKind: 'person',
      actionType: 'view',
      actionTargetId: 'u_lin',
      source: 'relationship',
      freshAt: _isoMinusHours(3),
    ),
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_2',
      intersectionClass: 'fact',
      displayName: '周屿',
      objectKind: 'person',
      primaryText: '你们互相关注',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1500648767791-00dcc994a43e/v1/avatar.jpg',
      totalPointCount: 2,
      strength: 0.7,
      relationKind: 'person',
      actionType: 'view',
      actionTargetId: 'u_zhou',
      source: 'relationship',
      freshAt: _isoMinusHours(96),
    ),
    IntersectionReason(
      dimension: 'identity',
      intersectionId: 'ix_id_1',
      intersectionClass: 'fact',
      displayName: '新东方校友会',
      objectKind: 'school',
      primaryText: '同校校友',
      secondaryText: '3位校友最近活跃',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1523050854058-8df90110c9f1/v1/avatar.jpg',
      totalPointCount: 3,
      strength: 0.82,
      relationKind: 'org',
      actionType: 'view',
      actionTargetId: 'fixture_homepage_university_pku',
      source: 'identity',
      freshAt: _isoMinusHours(10),
    ),
    IntersectionReason(
      dimension: 'content',
      intersectionId: 'ix_ct_1',
      intersectionClass: 'fact',
      displayName: '黄金投资圈',
      objectKind: 'circle',
      primaryText: '8人和你共看黄金内容',
      weightTier: 'heavy',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1611974789855-9c2a0a7236a3/v1/avatar.jpg',
      totalPointCount: 8,
      strength: 0.88,
      relationKind: 'circle',
      actionType: 'join',
      actionTargetId: 'circle_gold_invest',
      source: 'content',
      freshAt: _isoMinusHours(30),
    ),
    IntersectionReason(
      dimension: 'location',
      intersectionId: 'ix_loc_1',
      intersectionClass: 'fact',
      displayName: '西湖',
      objectKind: 'place',
      primaryText: '5人有相同旅行足迹',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1606767341197-3d8e6f0a2a9b/v1/avatar.jpg',
      totalPointCount: 5,
      strength: 0.76,
      relationKind: 'place',
      actionType: 'view',
      actionTargetId: 'homepage_sight_west_lake',
      source: 'location',
      freshAt: _isoMinusHours(2),
    ),
    IntersectionReason(
      dimension: 'interest',
      intersectionId: 'ix_int_1',
      intersectionClass: 'affinity',
      displayName: '陆衡',
      objectKind: 'person',
      primaryText: '可能合得来',
      secondaryText: '兴趣相似',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1507003211169-0a1dd7228f2d/v1/avatar.jpg',
      totalPointCount: 0,
      strength: 0.61,
      confidenceLabel: '推荐',
      modelReasonBucket: 'friend_suggestion',
      relationKind: 'person',
      actionType: 'view',
      actionTargetId: 'u_lu',
      source: 'interest',
      freshAt: _isoMinusHours(20),
    ),
  ]).map(normalizeInboxReason).toList(growable: false);
}

IntersectionReason normalizeInboxReason(IntersectionReason reason) {
  switch (reason.intersectionId) {
    case 'ix_rel_1':
      return _hifiReason(
        reason,
        text: '你和林清越等4位用户都关注「黄金投资圈」',
        iconKey: 'interest',
        objectKind: 'circle',
        sourceRef: 'sharedEntityAttention',
        objectId: 'fixture_circle_gold_invest',
        objectName: '黄金投资圈',
        anchorId: 'fixture_user_lin',
        anchorName: '林清越',
        countText: '4',
        mutualCount: 4,
        timeBucket: 'today',
        anchorWeight: 0.96,
      );
    case 'ix_id_1':
      return _hifiReason(
        reason,
        text: '你和新东方校友等3位用户都来自「新东方」',
        iconKey: 'alumni',
        objectKind: 'school',
        sourceRef: 'sameSchool',
        objectId: 'fixture_homepage_university_pku',
        objectName: '新东方',
        anchorId: 'fixture_user_article',
        anchorName: '新东方校友',
        countText: '3',
        mutualCount: 3,
        timeBucket: 'today',
        anchorWeight: 0.82,
      );
    case 'ix_ct_1':
      return _hifiReason(
        reason,
        text: '你和王然等8位用户都参与「黄金投资圈」',
        iconKey: 'discussion',
        objectKind: 'circle',
        sourceRef: 'coCommented',
        objectId: 'fixture_circle_gold_invest',
        objectName: '黄金投资圈',
        anchorId: 'fixture_user_photo',
        anchorName: '王然',
        countText: '8',
        mutualCount: 8,
        timeBucket: 'yesterday',
        anchorWeight: 0.74,
      );
    case 'ix_loc_1':
      return _hifiReason(
        reason,
        text: '你和张可等5位校友都去过「西湖」',
        iconKey: 'place',
        objectKind: 'place',
        sourceRef: 'coVisitedEntity',
        objectId: 'homepage_sight_west_lake',
        objectName: '西湖',
        anchorId: 'fixture_user_travel',
        anchorName: '张可',
        countText: '5',
        mutualCount: 5,
        timeBucket: 'today',
        anchorWeight: 0.78,
      );
    case 'ix_circle_1':
      return _hifiReason(
        reason,
        text: '你和周屿等2位用户都在「城市漫游圈」',
        iconKey: 'circle',
        objectKind: 'circle',
        sourceRef: 'sharedCircle',
        objectId: 'fixture_circle_city',
        objectName: '城市漫游圈',
        anchorId: 'fixture_user_zhou',
        anchorName: '周屿',
        countText: '2',
        mutualCount: 2,
        timeBucket: 'last7Days',
        anchorWeight: 0.70,
      );
    case 'ix_tag_1':
      return _hifiReason(
        reason,
        text: '你和林清越等1位用户都关注「胶片摄影」',
        iconKey: 'interest',
        objectKind: 'tag',
        sourceRef: 'sharedTagSample',
        objectId: 'tag_film_photo',
        objectName: '胶片摄影',
        anchorId: 'fixture_user_lin',
        anchorName: '林清越',
        countText: '1',
        mutualCount: 1,
        timeBucket: 'last7Days',
        anchorWeight: 0.68,
      );
    default:
      return reason;
  }
}

IntersectionReason _hifiReason(
  IntersectionReason reason, {
  required String text,
  required String iconKey,
  required String objectKind,
  required String sourceRef,
  required String objectId,
  required String objectName,
  required String anchorId,
  required String anchorName,
  required String countText,
  required int mutualCount,
  required String timeBucket,
  required double anchorWeight,
}) {
  return reason.copyWith(
    primaryText: text,
    secondaryText: '',
    primarySpans: <IntersectionTextSpan>[
      _plain('你和'),
      IntersectionTextSpan(
        text: anchorName,
        role: 'object',
        target: IntersectionTarget(
          objectId: anchorId,
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      ),
      _plain('等'),
      IntersectionTextSpan(
        text: countText,
        role: 'count',
        target: IntersectionTarget(
          objectId: reason.dimension,
          routeId: 'myIntersections',
        ),
      ),
      _plain(_tailBeforeObject(sourceRef)),
      IntersectionTextSpan(
        text: objectName,
        role: 'object',
        target: IntersectionTarget(
          objectId: objectId,
          objectKind: objectKind,
          routeId: _routeIdForObjectKind(objectKind),
        ),
      ),
      _plain('」'),
    ],
    objectKind: objectKind,
    source: sourceRef,
    actionTargetId: objectId,
    iconKey: iconKey,
    timeBucket: timeBucket,
    dedupeKey: 'viewer:$objectId:$objectKind',
    anchorUserWeight: anchorWeight,
    mutualCount: mutualCount,
  );
}

IntersectionTextSpan _plain(String text) =>
    IntersectionTextSpan(text: text, role: 'plain');

String _tailBeforeObject(String sourceRef) {
  switch (sourceRef) {
    case 'sharedCircle':
      return '位用户都在「';
    case 'coVisitedEntity':
      return '位校友都去过「';
    case 'coCommented':
      return '位用户都参与「';
    case 'sameSchool':
      return '位用户都来自「';
    default:
      return '位用户都关注「';
  }
}

IntersectionPoint _point({
  required String id,
  required String pointClass,
  required String dimension,
  required String label,
  required String displayText,
  String sourceRef = '',
  int count = 0,
  String sampleText = '',
  List<String> sampleAvatarUrls = const <String>[],
}) {
  return IntersectionPoint(
    pointId: id,
    pointClass: pointClass,
    dimension: dimension,
    label: label,
    displayText: displayText,
    sourceRef: sourceRef,
    visibility: 'public',
    count: count,
    sampleText: sampleText,
    sampleAvatarUrls: sampleAvatarUrls,
  );
}

IntersectionReason _withPoints(
  IntersectionReason reason,
  List<IntersectionPoint> points,
) {
  final visible = points
      .where((point) => point.visibility != 'hidden')
      .toList();
  final factCount = visible
      .where((point) => point.pointClass != 'recommended')
      .length;
  final recommendedCount = visible.length - factCount;
  final byDimension = <String, int>{};
  for (final point in visible) {
    byDimension[point.dimension] = (byDimension[point.dimension] ?? 0) + 1;
  }
  return reason.copyWith(
    intersectionPoints: visible,
    pointSummarySnapshotId: reason.intersectionId,
    factPointCount: factCount,
    recommendedPointCount: recommendedCount,
    totalPointCount: visible.length,
    dimensionPointSummary: byDimension.entries
        .map(
          (entry) => IntersectionDimensionTally(
            dimension: entry.key,
            count: entry.value,
          ),
        )
        .toList(growable: false),
    pointClassLabel: recommendedCount > 0 && factCount == 0 ? '推荐交集' : '事实交集',
    rankState: 'fresh',
  );
}

IntersectionReason _withDefaultPointSummary(IntersectionReason reason) {
  final pointClass = reason.intersectionClass == 'affinity'
      ? 'recommended'
      : 'fact';
  final shortLabel = reason.primaryText.trim().isNotEmpty
      ? reason.primaryText.trim()
      : reason.connectionSummary.trim();
  return _withPoints(reason, <IntersectionPoint>[
    _point(
      id: '${reason.intersectionId}_point',
      pointClass: pointClass,
      dimension: reason.dimension,
      label: shortLabel,
      displayText: shortLabel,
      sourceRef: reason.source,
      count: reason.totalPointCount,
      sampleText: reason.displayName,
      sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
          ? <String>[reason.avatarUrl.trim()]
          : const <String>[],
    ),
  ]);
}

List<IntersectionReason> _withDefaultPointSummaries(
  List<IntersectionReason> reasons,
) {
  return reasons.map(_withDefaultPointSummary).toList(growable: false);
}

String _isoMinusHours(int hours) =>
    DateTime.now().toUtc().subtract(Duration(hours: hours)).toIso8601String();

String _routeIdForObjectKind(String objectKind) {
  switch (objectKind) {
    case 'person':
      return 'userProfile';
    case 'circle':
      return 'circleDetail';
    case 'school':
    case 'place':
    case 'enterprise':
      return 'homepageDetail';
    default:
      return '';
  }
}

int _mutualCountFor(IntersectionReason item) {
  if (item.mutualCount > 0) return item.mutualCount;
  if (item.totalPointCount > 0) return item.totalPointCount;
  if (item.intersectionPoints.isEmpty) return 0;
  return item.intersectionPoints.fold<int>(
    0,
    (sum, point) => sum + (point.count > 0 ? point.count : 1),
  );
}

int _objectTypePriority(String objectKind) {
  switch (objectKind.trim()) {
    case 'circle':
      return 5;
    case 'place':
      return 4;
    case 'content':
      return 3;
    case 'tag':
    case 'interest':
      return 2;
    case 'school':
      return 1;
    default:
      return 0;
  }
}
