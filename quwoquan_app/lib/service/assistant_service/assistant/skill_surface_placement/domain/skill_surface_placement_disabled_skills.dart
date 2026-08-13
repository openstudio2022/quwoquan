/// SkillSurfacePlacement 的 `disabledSkillIds` 领域规则。
///
/// Placement 只表达 surface 的共享 Skill 策略，禁用集合的形状由契约约束：
/// 规范化去重、稳定排序，且只能引用 active package 目录内的 Skill。把规则放在
/// domain 层，读取面板、保存路径与测试共用同一份判定。
abstract final class SkillSurfacePlacementDisabledSkills {
  /// 把编辑中的禁用集合收敛为可提交形状。
  ///
  /// 目录外的 skillId 会被丢弃：Skill 退出 active package 后，它的禁用项不再有
  /// 意义，继续提交会让 placement 保留无法被用户看见也无法被解除的残留。
  static List<String> normalizeForSubmit({
    required Iterable<String> edited,
    required Set<String> activeSkillIds,
  }) {
    final retained = edited.where(activeSkillIds.contains).toSet().toList();
    retained.sort();
    return List<String>.unmodifiable(retained);
  }

  /// 按开关语义返回新的禁用集合；`enabled` 为真表示该 Skill 可用。
  static Set<String> toggle({
    required Set<String> disabled,
    required String skillId,
    required bool enabled,
  }) {
    final next = disabled.toSet();
    if (enabled) {
      next.remove(skillId);
    } else {
      next.add(skillId);
    }
    return next;
  }

  static bool isDisabled({
    required Iterable<String> disabledSkillIds,
    required String skillId,
  }) {
    return disabledSkillIds.contains(skillId);
  }
}
