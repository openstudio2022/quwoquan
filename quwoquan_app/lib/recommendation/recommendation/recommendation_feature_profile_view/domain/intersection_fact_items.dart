import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// Barrel re-export：消费者继续 import 本文件即可访问 kind 映射与句式合成公开 API；
// 拆分（R03 体量收敛）对 intersection_repository / T1 合约测试零改动。
export 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/domain/intersection_kind_mapping.dart';
export 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';

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

/// §22.3 默认交集 inbox 的生命周期显隐规则（端侧单一真相源）：
/// - `expired` 永不进 UI；
/// - `archived` 不进默认列表（仅在历史筛选下展示）。
/// mock 与 remote 列表路径共用本过滤，保证端云显隐一致。
const Set<String> defaultInboxHiddenLifecycleStates = {'expired', 'archived'};

List<IntersectionReason> filterDefaultInboxLifecycle(
  List<IntersectionReason> items,
) {
  return items
      .where(
        (item) => !defaultInboxHiddenLifecycleStates.contains(
          item.lifecycleState.trim(),
        ),
      )
      .toList(growable: false);
}

String dedupeKeyForIntersection(IntersectionReason item) {
  final explicit = item.dedupeKey.trim();
  if (explicit.isNotEmpty) return explicit;
  final objectId = item.actionTargetId.trim().isNotEmpty
      ? item.actionTargetId.trim()
      : item.relationObjectId.trim().isNotEmpty
      ? item.relationObjectId.trim()
      : item.intersectionId.trim();
  final objectType = item.objectKind.trim();
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

int _mutualCountFor(IntersectionReason item) {
  if (item.mutualCount > 0) return item.mutualCount;
  for (final point in item.intersectionPoints) {
    if (point.count > 0) return point.count;
  }
  if (item.totalPointCount > 0) return item.totalPointCount;
  return 0;
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
