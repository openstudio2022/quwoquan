import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/tag_intersection_mapper.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// post → 作者主页的交集高亮意图（§7.3 旅程无断点）。
///
/// post 作者信任徽标点击时写入 `{objectId, kind}`；作者主页交集卡读取后
/// 自动展开并高亮同一证据组，落地即见同一份列表（同 pointSummarySnapshotId）。
/// 端内导航意图，不进路由契约；消费后由对象页清空。
class IntersectionHighlightIntent {
  const IntersectionHighlightIntent({
    required this.objectId,
    required this.kind,
  });

  final String objectId;
  final String kind;
}

/// 当前待消费的交集高亮意图（跨页一次性传递）。
class IntersectionHighlightNotifier
    extends Notifier<IntersectionHighlightIntent?> {
  @override
  IntersectionHighlightIntent? build() => null;

  void set(IntersectionHighlightIntent intent) => state = intent;

  void clear() => state = null;

  /// 全 feed 作者/对象跳转点统一入口（§7.3 旅程无断点 · 杜绝各页各写）。
  ///
  /// 跳转对象主页前调用：取 [reasons] 最强证据组 kind 写入意图，对象页交集卡
  /// 据此自动展开并高亮同一证据组；无可用 kind 或无 objectId 时清空（不残留旧意图）。
  void primeFromReasons(String objectId, List<IntersectionReason>? reasons) {
    if (objectId.trim().isEmpty) {
      clear();
      return;
    }
    final kind = IntersectionReasonChip.primaryKind(reasons);
    if (kind == null) {
      clear();
      return;
    }
    set(IntersectionHighlightIntent(objectId: objectId, kind: kind));
  }
}

final intersectionHighlightIntentProvider =
    NotifierProvider<
      IntersectionHighlightNotifier,
      IntersectionHighlightIntent?
    >(IntersectionHighlightNotifier.new);

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

/// 对象页「你和这里 / 你们」的交集来源：
/// - 关系类交集（共同关注/联系人来过/圈子加入等，§2 闭集）经 intersectionRepository；
/// - 标签类交集经 tag-service shared-tags 直打。
/// 二者在端合并为只读 [IntersectionReason] 列表供 ObjectIntersectionCard 消费，
/// 关系类排在标签类之前（§9.8 挖掘强度：人物/事物 > 兴趣标签）。
/// 通过 provider 透明 Mock/Remote 切换，无效查询返回空。
final objectSharedReasonsProvider = FutureProvider.family<
    List<IntersectionReason>,
    ObjectIntersectionQuery>((ref, q) async {
  if (!q.isResolvable) {
    return const <IntersectionReason>[];
  }
  final tagRepo = ref.watch(tagRepositoryProvider);
  final intersectionRepo = ref.watch(intersectionRepositoryProvider);

  final relationFuture = intersectionRepo.getObjectIntersections(
    objectId: q.objectBId,
    objectType: q.objectBType,
    limit: q.limit,
  );
  final sharedFuture = tagRepo.sharedTags(
    objectAId: q.objectAId,
    objectAType: q.objectAType,
    objectBId: q.objectBId,
    objectBType: q.objectBType,
    limit: q.limit,
  );

  final relationReasons = await relationFuture;
  final shared = await sharedFuture;
  final tagReasons = sharedTagsToReasons(shared);

  return <IntersectionReason>[...relationReasons, ...tagReasons];
});
