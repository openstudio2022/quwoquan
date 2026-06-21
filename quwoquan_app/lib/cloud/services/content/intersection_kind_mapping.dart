import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

/// 交集共同实例数解析（point.count 真相源）。
///
/// §23 去桥接后，kind → iconKey / objectKind / routeId / tone / actionHints 的闭集映射
/// 一律查 codegen 下发的 `IntersectionKindMetadata`
/// （`cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart`），
/// 端不再维护第二份 switch。本文件只保留与 kind 元数据无关的共同数解析。
int intersectionMutualCountOf(IntersectionReason reason) {
  if (reason.mutualCount > 0) return reason.mutualCount;
  // 共同实例数真相在 point.count；totalPointCount 经 _withPoints 后是 point 条数（非共同数），
  // 故优先 point.count，再退 totalPointCount。
  for (final point in reason.intersectionPoints) {
    if (point.count > 0) return point.count;
  }
  if (reason.totalPointCount > 0) return reason.totalPointCount;
  return 1;
}
