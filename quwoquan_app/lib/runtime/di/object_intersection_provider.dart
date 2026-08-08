import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_reason_selection.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';

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
    final kind = primaryIntersectionReasonKind(reasons);
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

/// 对象页「你和这里 / 你们」的交集唯一来源：后端 intersectionRepository。
/// App 不再在 provider 层把 tag-service/shared-tags 合并成第二条 reason 主链。
final objectSharedReasonsProvider = FutureProvider.autoDispose
    .family<List<IntersectionReason>, ObjectIntersectionQuery>((ref, q) async {
      if (!q.isResolvable) {
        return const <IntersectionReason>[];
      }
      final intersectionRepo = ref.watch(intersectionRepositoryProvider);
      return intersectionRepo.getObjectIntersections(
        objectId: q.objectBId,
        objectType: q.objectBType,
        limit: q.limit,
      );
    });
