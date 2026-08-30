import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show SkillSurfaceKind;

/// 跨对象页面请求打开 Skill Surface Placement 的公开值契约。
///
/// 请求只描述目标 surface；具体 Flutter presentation 由 composition root 装配，
/// 调用方不得直接依赖 Assistant 对象的 presentation 实现。
final class AssistantSkillPlacementOpenRequest {
  const AssistantSkillPlacementOpenRequest({
    required this.surfaceKind,
    required this.surfaceId,
  });

  final SkillSurfaceKind surfaceKind;
  final String surfaceId;

  @override
  bool operator ==(Object other) {
    return other is AssistantSkillPlacementOpenRequest &&
        other.surfaceKind == surfaceKind &&
        other.surfaceId == surfaceId;
  }

  @override
  int get hashCode => Object.hash(surfaceKind, surfaceId);
}
