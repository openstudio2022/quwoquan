import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// SkillSurfacePlacement 的对象级 command/query facade。
///
/// Placement 只表达群聊/圈子的共享 Skill 策略（policy + disabledSkillIds），
/// 与 SkillUserSetting（个人启用与配置）、SkillConsent（数据授权）、
/// SkillSubscription（主动触达）分轨，任何一轨都不得替代另一轨。
abstract class AssistantSkillSurfacePlacementFacet {
  /// surface 成员读取共享 Skill 策略；响应不包含个人设置、记忆或 Connector。
  Future<SkillSurfacePlacement> getSkillSurfacePlacement({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
  });

  /// surface 管理员以 expectedRevision CAS 保存共享 Skill 策略。
  Future<SkillSurfacePlacement> putSkillSurfacePlacement({
    required SkillSurfaceKind surfaceKind,
    required String surfaceId,
    required SkillSurfacePlacementPolicy policy,
    required List<String> disabledSkillIds,
    required SkillSurfacePlacementStatus status,
    required int expectedRevision,
    required String clientRequestId,
  });
}
