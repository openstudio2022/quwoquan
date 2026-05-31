import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/tag_intersection_mapper.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 对象页交集卡「对象对直打」查询参数（当前主体 A × 被看对象 B）。
class ObjectIntersectionQuery {
  const ObjectIntersectionQuery({
    required this.objectAId,
    required this.objectAType,
    required this.objectBId,
    required this.objectBType,
    this.limit = 6,
  });

  final String objectAId;
  final String objectAType;
  final String objectBId;
  final String objectBType;
  final int limit;

  bool get isResolvable =>
      objectAId.isNotEmpty &&
      objectBId.isNotEmpty &&
      !(objectAId == objectBId && objectAType == objectBType);

  @override
  bool operator ==(Object other) =>
      other is ObjectIntersectionQuery &&
      other.objectAId == objectAId &&
      other.objectAType == objectAType &&
      other.objectBId == objectBId &&
      other.objectBType == objectBType &&
      other.limit == limit;

  @override
  int get hashCode =>
      Object.hash(objectAId, objectAType, objectBId, objectBType, limit);
}

/// 对象页「你和这里 / 你们」的交集来源：经 tag-service shared-tags 直打，
/// 规范化为只读 [IntersectionReason] 列表供 ObjectIntersectionCard 消费。
/// 通过 [tagRepositoryProvider] 透明 Mock/Remote 切换，无效查询返回空。
final objectSharedReasonsProvider = FutureProvider.family<
    List<IntersectionReason>,
    ObjectIntersectionQuery>((ref, q) async {
  if (!q.isResolvable) {
    return const <IntersectionReason>[];
  }
  final repo = ref.watch(tagRepositoryProvider);
  final shared = await repo.sharedTags(
    objectAId: q.objectAId,
    objectAType: q.objectAType,
    objectBId: q.objectBId,
    objectBType: q.objectBType,
    limit: q.limit,
  );
  return sharedTagsToReasons(shared);
});
